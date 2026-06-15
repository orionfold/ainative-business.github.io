# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""`fieldkit field-edition up` — bring up the stack + load the resident Advisor.

Implements §7 step 2 of ``_SPECS/arena-field-edition-v1.md``. ``up`` is a
**checkpointed, re-entrant phase machine**: it walks an ordered list of phases,
persists a checkpoint after each, and on a re-run **resumes from the last good
phase** rather than restarting (the spec's idempotency / partial-failure
contract — the box runs ~4.77 MB/s, so a failed pull must not redo the work
already done).

Phases (ordered)::

    matrix    re-run the §7 support-matrix gate (refuse an untested base)
    bundle    render + write the digest-pinned Compose bundle into ~/.orionfold
    pull      pull the default Advisor GGUF + embedder weights (resumable)
    stack     `docker compose up -d`  →  pgvector + embedder + the llama.cpp lane
    ingest    seed the Cortex corpus (the vendored Advisor demo pack) into pgvector
    sidecar   start the pipx Arena cockpit on :7866 and wait for health
    resident  point Arena at the lane and warm the default model
    verify    (only with --verify) run the §8 first-boot eval gate + emit receipt

Design (the deterministic-scripts invariant): the **planning** is pure —
:func:`plan_remaining` decides which phases run from a state dict, with no I/O —
and the **execution** lives behind an injectable :class:`Executor` so the live
shell-outs (Docker, HF, the cockpit) are isolated and the runner is testable
with a fake. :func:`run_up` is the loop that ties them together and checkpoints.

**M1 status.** The orchestration, the Compose bundle (:mod:`.compose`), and the
``matrix``/``bundle`` phases run for real today; ``--dry-run`` writes the bundle
and prints the remaining plan. The live phases (``pull``/``stack``/``resident``)
fail honestly until the proven-matrix images + the published Q4_K_M GGUF exist
(M2) — :data:`compose.unpinned_images` is checked up front so the failure names
the missing artifact and the fix instead of a cryptic registry error. ``verify``
is the next increment (§8 eval gate); ``--verify`` reports that honestly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fieldkit.field_edition import compose as _compose
from fieldkit.field_edition.compose import FieldEditionConfig

__all__ = [
    "PHASES",
    "Phase",
    "PhaseError",
    "InstallState",
    "Executor",
    "LiveExecutor",
    "UpResult",
    "plan_remaining",
    "run_up",
]


class PhaseError(RuntimeError):
    """A phase failed. Carries the operator-facing ``fix`` (the §8 failure-UX
    contract: name the component, the gate, and the fix)."""

    def __init__(self, message: str, *, fix: str = "") -> None:
        super().__init__(message)
        self.fix = fix


@dataclass(frozen=True)
class Phase:
    """One step in the ``up`` sequence."""

    key: str
    label: str
    detail: str
    #: A "safe" phase only touches the local box (matrix gate, file writes) and
    #: runs under ``--dry-run``; non-safe phases pull/launch and are skipped.
    safe: bool = False
    #: Optional phases (``verify``) only run when explicitly requested.
    optional: bool = False


PHASES: tuple[Phase, ...] = (
    Phase("matrix", "Matrix gate", "verify the DGX OS / driver / CUDA / Docker matrix", safe=True),
    Phase("bundle", "Compose bundle", "render + write ~/.orionfold/compose.yaml + .env", safe=True),
    Phase("pull", "Model pull", "pull the default Advisor GGUF + embedder weights (resumable)"),
    Phase("stack", "Container stack", "docker compose up -d (pgvector + embedder + lane)"),
    Phase("ingest", "Cortex corpus", "ingest the vendored Advisor demo corpus into pgvector"),
    Phase("sidecar", "Arena cockpit", "start the pipx Arena sidecar on :7866"),
    Phase("resident", "Resident model", "point Arena at the lane and warm the default model"),
    Phase("verify", "First-boot gate", "run the §8 eval gate + emit the receipt", optional=True),
)

_DONE = "done"
_FAILED = "failed"
_PENDING = "pending"

#: AD-FK-ε: how long ``resident`` waits for the serving lane to load its GGUF
#: before failing. The lane container starts in ``stack``, but llama-server
#: needs ~60-90 s on the Spark to map the 2.84 GB Q4_K_M weights before
#: ``:{port}/v1/models`` answers. A single probe here deterministically FAILs on
#: a cold lane and forces a re-run, so we poll (the pattern ``sidecar`` uses for
#: :7866) with ~150 s of headroom over the observed warm time.
_LANE_POLL_INTERVAL_S = 1.0
_LANE_WARM_POLLS = 150


# --- State (the checkpoint) --------------------------------------------------


@dataclass
class InstallState:
    """The on-disk checkpoint at ``~/.orionfold/state.json``.

    Maps each phase key to ``"done"``/``"failed"``/``"pending"``; ``done``
    phases are skipped on a re-run (unless ``--force``)."""

    version: int = 1
    phases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "InstallState":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(version=int(data.get("version", 1)), phases=dict(data.get("phases", {})))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": self.version, "phases": self.phases}, indent=2) + "\n",
            encoding="utf-8",
        )

    def status(self, key: str) -> str:
        return self.phases.get(key, _PENDING)

    def mark(self, key: str, status: str) -> None:
        self.phases[key] = status


def plan_remaining(
    state: InstallState,
    *,
    phases: tuple[Phase, ...] = PHASES,
    force: bool = False,
    with_verify: bool = False,
    safe_only: bool = False,
) -> list[Phase]:
    """Pure: the phases this run will execute, in order (no I/O).

    Skips ``done`` phases (re-entrancy) unless ``force``; drops optional phases
    unless requested (``with_verify``); under ``safe_only`` (dry-run) keeps only
    the local-touch phases."""
    chosen: list[Phase] = []
    for p in phases:
        if p.optional and not (p.key == "verify" and with_verify):
            continue
        if safe_only and not p.safe:
            continue
        if not force and state.status(p.key) == _DONE:
            continue
        chosen.append(p)
    return chosen


# --- Execution (the only I/O) ------------------------------------------------


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def _run(
    cmd: list[str], *, timeout: int = 600, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env
    )


class Executor:
    """The phase actions. Subclass / fake for tests; :meth:`dispatch` maps a
    phase key to its method so the runner stays dispatch-agnostic."""

    def dispatch(self, key: str, config: FieldEditionConfig) -> None:
        getattr(self, key)(config)

    # Each method runs one phase and raises PhaseError on failure.
    def matrix(self, config: FieldEditionConfig) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def bundle(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def pull(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def stack(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def ingest(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def sidecar(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def resident(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError

    def verify(self, config: FieldEditionConfig) -> None:  # pragma: no cover
        raise NotImplementedError


class LiveExecutor(Executor):
    """Runs the phases against the real box."""

    def matrix(self, config: FieldEditionConfig) -> None:
        from fieldkit.field_edition.doctor import run_doctor

        report = run_doctor()
        if not report.ok:
            failed = ", ".join(f"{r.label} ({r.status})" for r in report.failures)
            raise PhaseError(
                f"support matrix failed: {failed}",
                fix="run `fieldkit field-edition doctor` to see each reason + fix",
            )

    def bundle(self, config: FieldEditionConfig) -> None:
        _compose.write_bundle(config)

    def pull(self, config: FieldEditionConfig) -> None:
        lane = config.lane
        gguf = config.model_store / lane.gguf_name
        if gguf.exists():
            return  # idempotent — a resumed `up` does not redownload
        # The GGUF source rev must be a published commit, not the REV_PENDING
        # sentinel (the repo ships Q8_0 only today). Refuse honestly otherwise —
        # an operator can still drop the file in the store manually meanwhile.
        if not lane.gguf_pinned:
            raise PhaseError(
                f"default model not present at {gguf} and no pinned GGUF rev to pull",
                fix=(
                    "publish + pin a Q4_K_M rev of "
                    f"{lane.gguf_repo} (set LaneConfig.gguf_revision to its commit "
                    "sha), or place the GGUF in the model store manually"
                ),
            )
        from huggingface_hub import hf_hub_download  # core dep
        # `hf_hub_download` resumes a partial download by default — load-bearing
        # at the box's ~4.77 MB/s (a Q4_K_M 4B is ~2.6 GB). Pin by `revision` (a
        # commit sha) so an upstream re-tag can never silently change the bytes.
        gguf.parent.mkdir(parents=True, exist_ok=True)
        try:
            fetched = hf_hub_download(
                repo_id=lane.gguf_repo,
                filename=lane.gguf_file,
                revision=lane.gguf_revision,
                local_dir=str(gguf.parent),
            )
        except Exception as exc:  # network / auth / missing-rev
            raise PhaseError(
                f"GGUF pull from {lane.gguf_repo}@{lane.gguf_revision[:12]} failed: {exc}",
                fix="check connectivity + that the pinned rev publishes the file; the download resumes on re-run",
            ) from exc
        # Land it at the bundle's expected path if the repo layout differs.
        fetched_path = Path(fetched)
        if fetched_path.resolve() != gguf.resolve():
            gguf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fetched_path, gguf)

    def stack(self, config: FieldEditionConfig) -> None:
        unpinned = _compose.unpinned_images(config)
        if unpinned:
            names = ", ".join(p.reference() for p in unpinned)
            raise PhaseError(
                f"{len(unpinned)} image(s) not yet published/pinned: {names}",
                fix=(
                    "build + push + digest-pin the Orionfold proven-matrix images "
                    "(open embedder, CUDA-13 llama.cpp lane) before a live `up` — "
                    "M2; the bundle is rendered and `docker compose config`-valid now"
                ),
            )
        if not _which("docker"):
            raise PhaseError("docker not found", fix="install Docker CE (preinstalled on DGX OS 7.x)")
        # AD-FK-α: the NIM embedder's compose service interpolates
        # ${NGC_API_KEY:?…}. Source the operator's key (env → ~/.nim/secrets.env)
        # into the compose environment so an unattended `up` works, and refuse
        # with a named fix up front rather than letting Docker error cryptically.
        env = _compose.compose_env(config)
        if config.embedder.needs_ngc_key and not env.get("NGC_API_KEY"):
            raise PhaseError(
                "the NIM embedder needs an NGC API key but none was found",
                fix=(
                    "export NGC_API_KEY=… or create ~/.nim/secrets.env with a "
                    "`NGC_API_KEY=…` line (the Field Edition box already runs NGC), "
                    "then re-run `up`; or select the open embedder with "
                    "`up --open-embedder` (v1.1)"
                ),
            )
        compose_path = config.home / "compose.yaml"
        proc = _run(["docker", "compose", "-f", str(compose_path), "up", "-d"], env=env)
        if proc.returncode != 0:
            raise PhaseError(
                f"`docker compose up -d` failed (exit {proc.returncode})",
                fix=(proc.stderr or proc.stdout).strip()[:400] or "inspect `docker compose logs`",
            )

    def ingest(self, config: FieldEditionConfig) -> None:
        # AD-FK-β: a fresh box boots an empty pgvector, so the §8 Cortex gate
        # can't pass until the Advisor demo corpus is ingested. Seed it from the
        # vendored pack (offline). Idempotent: a non-empty corpus is left as-is
        # so a re-run / a customer's own ingest is never clobbered.
        from fieldkit.field_edition.ingest import run_ingest

        result = run_ingest(config)
        if not result.ok:
            raise PhaseError(
                f"Cortex corpus ingest failed: {result.error}",
                fix=(
                    f"check the embedder (:{config.embedder.port}) + pgvector "
                    f"(:{config.postgres.port}) are healthy, then re-run `up` "
                    "(or `fieldkit field-edition ingest`) to resume"
                ),
            )
        if not result.skipped and result.chunks_written == 0:
            raise PhaseError(
                "Cortex corpus ingest wrote 0 chunks",
                fix="the vendored pack may be empty/corrupt — reinstall `fieldkit[arena]`",
            )

    @staticmethod
    def _cockpit_command(repo_root: Path) -> list[str]:
        """The argv that starts the Arena cockpit. Prefer the ``fieldkit``
        console script that sits beside the running interpreter (the venv/pipx
        install ``up`` is itself running from), falling back to one on PATH.
        ``fieldkit`` ships no ``python -m`` entry, so the console script is the
        only invocation.

        Pins ``--repo-root`` (repo_root leak fix): ``arena up`` defaults its
        repo root to the CWD, so launching the installer from inside a monorepo
        would leak that repo's artifacts/articles/leaderboard/models into the
        customer cockpit. A fresh customer-owned root yields the honest
        first-boot empty state regardless of where ``up`` is invoked."""
        sibling = Path(sys.executable).with_name("fieldkit")
        fk = str(sibling) if sibling.exists() else (shutil.which("fieldkit") or "fieldkit")
        return [fk, "arena", "up", "--no-open", "--repo-root", str(repo_root)]

    def _cockpit_healthy(self) -> bool:
        import httpx  # core dep

        try:
            return httpx.get("http://127.0.0.1:7866/healthz", timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False

    def sidecar(self, config: FieldEditionConfig) -> None:
        # AD-FK-γ: the Arena cockpit is the pipx/venv fieldkit[arena] process
        # (§5), not a compose service — but an unattended `up` (`curl … | sh`)
        # must START it, not just health-poll and bail. `fieldkit arena up`
        # blocks (uvicorn), so spawn it detached, log to ~/.orionfold/cockpit.log,
        # record the pid, and poll :7866/healthz until ready.
        if self._cockpit_healthy():
            return  # already up (re-entrant re-run)
        config.home.mkdir(parents=True, exist_ok=True)
        log_path = config.home / "cockpit.log"
        # repo_root leak fix: pin the cockpit's repo root to a fresh
        # customer-owned dir (never the CWD), so dev-monorepo data can't leak in.
        arena_root = config.home / "arena-root"
        arena_root.mkdir(parents=True, exist_ok=True)
        cmd = self._cockpit_command(arena_root)
        try:
            log = open(log_path, "ab")  # noqa: SIM115 — handed to the child, stays open
            proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # survive `up` exiting (it's the long-lived cockpit)
            )
        except OSError as exc:
            raise PhaseError(
                f"could not start the Arena cockpit: {exc}",
                fix="start it by hand with `fieldkit arena up --no-open`",
            ) from exc
        (config.home / "cockpit.pid").write_text(f"{proc.pid}\n", encoding="utf-8")
        # Poll up to ~30 s for health; bail early if the process dies.
        for _ in range(60):
            if proc.poll() is not None:
                raise PhaseError(
                    f"the Arena cockpit exited early (rc={proc.returncode})",
                    fix=f"inspect {log_path}; common cause: the `[arena]` extra is not installed",
                )
            if self._cockpit_healthy():
                return
            time.sleep(0.5)
        raise PhaseError(
            "Arena cockpit did not become healthy on :7866 within 30s",
            fix=f"inspect {log_path}; it may still be warming — re-run `up` to resume",
        )

    def _lane_healthy(self, config: FieldEditionConfig) -> bool:
        import httpx  # core dep

        try:
            url = f"http://127.0.0.1:{config.lane.port}/v1/models"
            return httpx.get(url, timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False

    def resident(self, config: FieldEditionConfig) -> None:
        # AD-FK-ε: the lane container starts in `stack`, but llama-server needs
        # ~60-90 s to load the GGUF before :{port}/v1/models answers. A single
        # probe deterministically FAILs on a cold lane and forces a re-run, so
        # poll until the model is loaded (the pattern `sidecar` uses for :7866),
        # failing honestly only on a real timeout.
        for _ in range(_LANE_WARM_POLLS):
            if self._lane_healthy(config):
                break
            time.sleep(_LANE_POLL_INTERVAL_S)
        else:
            budget = int(_LANE_WARM_POLLS * _LANE_POLL_INTERVAL_S)
            raise PhaseError(
                f"serving lane did not become healthy on :{config.lane.port} within {budget}s",
                fix=(
                    "the lane loads the GGUF on first boot (~60-90s) and may still "
                    "be warming; check `docker logs of-advisor-lane` and re-run `up` to resume"
                ),
            )

    def verify(self, config: FieldEditionConfig) -> None:
        # The §8 first-boot eval gate. `up --verify` collapses steps 2-3 into
        # one command (§7): bring the stack up, then run the gate + emit the
        # receipt. The receipt is always written (pass or fail); a failing gate
        # raises so the phase is marked `failed` and `up` resumes here.
        from fieldkit.field_edition.verify import run_verify

        report, path = run_verify(config)
        if not report.ok:
            failed = ", ".join(f"{r.label} ({r.status})" for r in report.failures)
            raise PhaseError(
                f"first-boot eval gate failed: {failed}",
                fix=f"see the receipt at {path}; run `fieldkit field-edition verify` for per-gate fixes",
            )


@dataclass
class UpResult:
    """The outcome of a :func:`run_up`."""

    ran: list[str]
    skipped: list[str]
    planned: list[str]  # safe-only / dry-run: phases not executed, just reported
    failed: str | None
    fix: str
    dry_run: bool

    @property
    def ok(self) -> bool:
        return self.failed is None


def run_up(
    config: FieldEditionConfig | None = None,
    *,
    executor: Executor | None = None,
    force: bool = False,
    with_verify: bool = False,
    dry_run: bool = False,
    on_event: Callable[[str], None] | None = None,
) -> UpResult:
    """Run the phase machine; checkpoint after each phase; resume on re-run.

    Stops at the first phase that raises :class:`PhaseError`, leaving it marked
    ``failed`` so a later ``up`` resumes there. ``dry_run`` runs only the safe
    (local) phases and reports the rest as planned."""
    cfg = config or _compose.default_config()
    exe = executor or LiveExecutor()
    emit = on_event or (lambda _msg: None)
    state_path = cfg.home / "state.json"
    state = InstallState.load(state_path)

    def _eligible(p: Phase) -> bool:
        """A phase that this invocation considers at all (optional/verify gate)."""
        return not p.optional or (p.key == "verify" and with_verify)

    chosen = plan_remaining(
        state, force=force, with_verify=with_verify, safe_only=dry_run
    )
    chosen_keys = {p.key for p in chosen}
    # "skipped" = eligible phases not run this invocation because they are
    # already `done` (re-entrancy) — excludes the live phases a dry-run defers.
    skipped = [
        p.key
        for p in PHASES
        if _eligible(p)
        and p.key not in chosen_keys
        and not (dry_run and not p.safe)
        and state.status(p.key) == _DONE
    ]

    ran: list[str] = []
    for phase in chosen:
        emit(f"▶ {phase.label}: {phase.detail}")
        try:
            exe.dispatch(phase.key, cfg)
        except PhaseError as err:
            state.mark(phase.key, _FAILED)
            state.save(state_path)
            emit(f"✗ {phase.label}: {err}")
            return UpResult(
                ran=ran, skipped=skipped, planned=[], failed=phase.key, fix=err.fix, dry_run=dry_run
            )
        state.mark(phase.key, _DONE)
        state.save(state_path)
        ran.append(phase.key)
        emit(f"✓ {phase.label}")

    planned: list[str] = []
    if dry_run:
        # Report (don't run) the live phases that a real `up` would do next.
        planned = [p.key for p in PHASES if not p.safe and _eligible(p)]

    return UpResult(ran=ran, skipped=skipped, planned=planned, failed=None, fix="", dry_run=dry_run)
