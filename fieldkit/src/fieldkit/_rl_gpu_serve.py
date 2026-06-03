# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""The **torch-free** half of the RLVR GPU backend (`fieldkit[rl]`, RV-1/RV-5).

This module vendors the two GPU-*adjacent* halves of the proven
`clawgym-on-spark-grpo` loop that need **no torch**: the **rollout sampler**
(HTTP against a local pinned-vLLM OpenAI endpoint via the already-shipped
`fieldkit.nim.NIMClient` — the GPU lives in a *separate* vLLM server process)
and the **vLLM serve lifecycle** (the kill-and-restart that reloads the updated
LoRA between steps — `start_vllm` / `stop_vllm` in the original `grpo_loop.sh`).

Keeping it torch-free means it imports cleanly on any box and is fully
unit-testable without a GPU — the sampler over a fake client, the serve-command
construction as a pure function, the `_GpuRollout` carrier. The torch-bound
REINFORCE-with-KL step lives in the sibling :mod:`fieldkit._rl_gpu_trainer`
(the actual `fieldkit[rl]` install gate); :func:`fieldkit.rl.gpu_seams` wires
the two together lazily so plain ``import fieldkit.rl`` stays stdlib-cheap.

Runtime knobs come from the environment so the seam signature
``gpu_seams(config)`` stays stable (the operator tunes the box, not the API):

- ``FK_RL_VLLM_URL``     — the local vLLM OpenAI base (default ``http://localhost:8000/v1``)
- ``FK_RL_BASE_MODEL``   — the HF base id to serve + train (default ``Qwen/Qwen2.5-7B-Instruct``)
- ``FK_RL_ADAPTER_INIT`` — the SFT-init LoRA the run starts from (required for a real run)
- ``FK_RL_WORK_DIR``     — where per-step adapters are written (default ``~/.fieldkit/rl``)
- ``FK_RL_LORA_NAME``    — the served LoRA module name == the chat ``model`` (default ``policy``)
- ``FK_RL_SYSTEM_PROMPT``— optional system message prepended to each rollout prompt
- ``FK_RL_MAX_TOKENS``   — rollout completion budget (default 512)
- ``FK_RL_MAX_LORA_RANK``— vLLM ``--max-lora-rank`` (default mirrors ``GRPOConfig.lora_rank``)
- ``FK_RL_GPU_UTIL``     — vLLM ``--gpu-memory-utilization`` (default 0.55 — one-lane envelope, RV-10)
- ``FK_RL_MAX_MODEL_LEN``— vLLM ``--max-model-len`` (default 8192)
- ``FK_RL_HELDOUT_TEMP`` — held-out-eval sampling temperature (default 0.2 — stable, < train temp)
- ``FK_RL_SERVE_CMD``    — full serve command override (e.g. a ``docker exec`` wrapper)
- ``FK_RL_STOP_CMD``     — full stop command override (default the `pkill` line, RV-R4)

Per `feedback_llm_skill_pattern`: deterministic Python only, no LLM call of its
own (the sampler asks the *policy* to generate; the reward is the verifier).
The `pkill -9 -f 'vllm|EngineCore'` teardown honours
`[[feedback_vllm_engine_core_orphan]]` (the bare ``vllm.entrypoints`` pattern
orphans the ~108 GB EngineCore worker).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from fieldkit.nim import NIMClient, wait_for_warm

__all__ = [
    "RLBackendConfig",
    "VLLMLane",
    "build_serve_seams",
    "serve_command",
    "stop_command",
]

DEFAULT_VLLM_URL = "http://localhost:8000/v1"
DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
DEFAULT_LORA_NAME = "policy"
# The EngineCore-aware teardown (RV-R4 / feedback_vllm_engine_core_orphan): the
# bare `vllm.entrypoints` pattern leaves the ~108 GB worker resident.
DEFAULT_STOP_CMD = (
    "pkill -9 -f 'vllm|EngineCore' ; sleep 2 ; "
    "pkill -9 -f 'multiprocessing.resource_tracker' || true"
)


@dataclass(frozen=True, slots=True)
class _GpuRollout:
    """A sampled rollout that *also* carries its prompt (the trainer needs it).

    Duck-types :class:`fieldkit.reward.Rollout` — ``prediction`` / ``expected``
    / ``rubric`` / ``task_id`` — so :meth:`fieldkit.reward.RewardAdapter.score`
    grades it unchanged. The extra ``prompt`` field is the user-question text
    the sampler sent; the REINFORCE step rebuilds the exact
    ``(system?, user, assistant=prediction)`` token sequence from it without
    needing the bench, mirroring `grpo_train.py`'s `reconstruct_messages` for
    the single-turn QA case.
    """

    prediction: str
    expected: str = ""
    rubric: Mapping[str, Any] | None = None
    task_id: str = ""
    prompt: str = ""


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """Read `name` off a VerticalQA-like object OR a mapping (duck-typed)."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass
class RLBackendConfig:
    """Box-level runtime config for the GPU backend, resolved from the env.

    Distinct from :class:`fieldkit.rl.GRPOConfig` (the *hyperparameters*): this
    is the *where* — endpoint, base weights, serve flags — that the operator
    sets per box. :meth:`from_env` reads the ``FK_RL_*`` variables, falling back
    to the `GRPOConfig` for the LoRA rank and the proven-run defaults otherwise.
    """

    vllm_url: str = DEFAULT_VLLM_URL
    base_model: str = DEFAULT_BASE_MODEL
    adapter_init: str = ""
    work_dir: Path = field(default_factory=lambda: Path("~/.fieldkit/rl").expanduser())
    lora_name: str = DEFAULT_LORA_NAME
    system_prompt: str = ""
    max_tokens: int = 512
    max_lora_rank: int = 16
    gpu_util: float = 0.55
    max_model_len: int = 8192
    heldout_temp: float = 0.2
    startup_timeout: float = 360.0
    serve_cmd_override: str = ""
    stop_cmd: str = DEFAULT_STOP_CMD

    @classmethod
    def from_env(cls, grpo_config: Any) -> "RLBackendConfig":
        env = os.environ.get
        return cls(
            vllm_url=env("FK_RL_VLLM_URL", DEFAULT_VLLM_URL),
            base_model=env("FK_RL_BASE_MODEL", DEFAULT_BASE_MODEL),
            adapter_init=env("FK_RL_ADAPTER_INIT", ""),
            work_dir=Path(env("FK_RL_WORK_DIR", "~/.fieldkit/rl")).expanduser(),
            lora_name=env("FK_RL_LORA_NAME", DEFAULT_LORA_NAME),
            system_prompt=env("FK_RL_SYSTEM_PROMPT", ""),
            max_tokens=int(env("FK_RL_MAX_TOKENS", "512")),
            max_lora_rank=int(
                env("FK_RL_MAX_LORA_RANK", str(getattr(grpo_config, "lora_rank", 16)))
            ),
            gpu_util=float(env("FK_RL_GPU_UTIL", "0.55")),
            max_model_len=int(env("FK_RL_MAX_MODEL_LEN", "8192")),
            heldout_temp=float(env("FK_RL_HELDOUT_TEMP", "0.2")),
            startup_timeout=float(env("FK_RL_STARTUP_TIMEOUT", "360")),
            serve_cmd_override=env("FK_RL_SERVE_CMD", ""),
            stop_cmd=env("FK_RL_STOP_CMD", DEFAULT_STOP_CMD),
        )

    def messages_for(self, question: str) -> list[dict[str, str]]:
        """The single-turn QA prompt the sampler sends + the trainer rebuilds."""
        msgs: list[dict[str, str]] = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        msgs.append({"role": "user", "content": question})
        return msgs


def serve_command(cfg: RLBackendConfig, adapter_path: str) -> list[str]:
    """The vLLM OpenAI server argv for serving `base_model` + the policy LoRA.

    A **pure function** (no side effects) so the construction is unit-testable.
    Mirrors `grpo_loop.sh start_vllm`: ``--enable-lora --lora-modules
    <name>=<path> --max-lora-rank`` so the updated adapter is the chat ``model``.
    If ``FK_RL_SERVE_CMD`` is set it is used verbatim with ``{adapter}`` /
    ``{port}`` substituted (e.g. to wrap the launch in ``docker exec``).
    """
    port = cfg.vllm_url.rstrip("/").rsplit(":", 1)[-1].split("/")[0]
    if cfg.serve_cmd_override:
        return shlex.split(
            cfg.serve_cmd_override.format(adapter=adapter_path, port=port, name=cfg.lora_name)
        )
    return [
        "python3", "-m", "vllm.entrypoints.openai.api_server",
        "--model", cfg.base_model,
        "--port", str(port),
        "--max-model-len", str(cfg.max_model_len),
        "--gpu-memory-utilization", str(cfg.gpu_util),
        "--enable-lora",
        "--lora-modules", f"{cfg.lora_name}={adapter_path}",
        "--max-lora-rank", str(cfg.max_lora_rank),
    ]


def stop_command(cfg: RLBackendConfig) -> str:
    """The shell teardown line (EngineCore-aware — RV-R4)."""
    return cfg.stop_cmd


@dataclass
class VLLMLane:
    """The single serving lane: kill-and-restart vLLM to swap the LoRA (RV-5).

    The eliminable quarter of the ~15-min step (≈3.5 min restart). v1 ships the
    proven kill-and-restart; the hot-LoRA-swap (``/v1/load_lora_adapter``) is
    the tracked fast-follow. `restart` is what the trainer seam calls after it
    writes the new adapter.
    """

    cfg: RLBackendConfig
    _proc: "subprocess.Popen[bytes] | None" = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None

    def ensure_started(self, adapter_path: str) -> None:
        """Start the lane only if it isn't already up (step-0 idempotency)."""
        if not self.is_running:
            if not adapter_path:
                raise RuntimeError(
                    "no initial LoRA to serve — set FK_RL_ADAPTER_INIT to the "
                    "SFT-init adapter the run starts from (RV-1)."
                )
            self.start(adapter_path)

    def start(self, adapter_path: str) -> None:
        """Launch the vLLM server with `adapter_path` as the policy LoRA, then
        block until ``/v1/models`` reports the LoRA id (or `startup_timeout`)."""
        argv = serve_command(self.cfg, adapter_path)
        log = self.cfg.work_dir / "vllm-serve.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(  # operator-controlled argv, not shell
            argv,
            stdout=log.open("ab"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self._await_lora_ready()

    def _await_lora_ready(self) -> None:
        warmed = wait_for_warm(
            self.cfg.vllm_url, timeout=self.cfg.startup_timeout, api_key="local"
        )
        if not warmed:
            raise RuntimeError(
                f"vLLM did not warm within {self.cfg.startup_timeout:.0f}s at "
                f"{self.cfg.vllm_url} — check {self.cfg.work_dir / 'vllm-serve.log'}"
            )

    def stop(self) -> None:
        """Tear the lane down (EngineCore-aware) and verify memory is released."""
        subprocess.run(  # operator-controlled teardown line (shell by design)
            stop_command(self.cfg), shell=True, check=False
        )
        time.sleep(3)
        self._proc = None

    def restart(self, adapter_path: str) -> None:
        self.stop()
        self.start(adapter_path)


def _make_sampler(
    cfg: RLBackendConfig,
    temperature: float,
    client_factory: Callable[[], Any],
) -> Callable[[Sequence[Any], int], "list[list[_GpuRollout]]"]:
    """Build a sampler closure: K rollouts/task over the local vLLM endpoint.

    `client_factory` returns a `.chat(messages, *, max_tokens, temperature)`
    client (real: :class:`fieldkit.nim.NIMClient`; tests pass a fake). Each task
    becomes a single-turn QA prompt; the policy generates `k` completions; each
    completion is a :class:`_GpuRollout` carrying the prompt for the trainer.
    """

    def sampler(tasks: Sequence[Any], k: int) -> "list[list[_GpuRollout]]":
        client = client_factory()
        groups: list[list[_GpuRollout]] = []
        try:
            for task in tasks:
                question = _field(task, "question", "") or ""
                expected = _field(task, "expected", "") or ""
                rubric = _field(task, "rubric", None)
                if rubric is None:
                    rubric = _field(task, "tags", None)
                task_id = _field(task, "qid", "") or _field(task, "task_id", "") or ""
                messages = cfg.messages_for(question)
                rolls: list[_GpuRollout] = []
                for _ in range(k):
                    resp = client.chat(
                        messages, max_tokens=cfg.max_tokens, temperature=temperature
                    )
                    text = resp["choices"][0]["message"]["content"]
                    rolls.append(
                        _GpuRollout(
                            prediction=text,
                            expected=expected,
                            rubric=rubric,
                            task_id=task_id,
                            prompt=question,
                        )
                    )
                groups.append(rolls)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        return groups

    return sampler


def _make_heldout_eval(
    heldout_sampler: Callable[[Sequence[Any], int], "list[list[_GpuRollout]]"],
    reward: Any,
) -> Callable[[int, Sequence[Any]], float]:
    """Build the held-out gate (RV-4): one greedy-ish sample/question, scored by
    the reward adapter, mean scalar returned. Needs the `RewardAdapter` — the
    held-out score is the *verifier's* score on a frozen split, never the pool.
    """

    def heldout_eval(step: int, tasks: Sequence[Any]) -> float:
        if reward is None:
            raise RuntimeError(
                "gpu_seams needs `reward=` to score the held-out split — pass "
                "the RewardAdapter (run_rl_loop wires it)."
            )
        groups = heldout_sampler(tasks, 1)
        scalars = [reward.score(g[0]).scalar for g in groups if g]
        return sum(scalars) / len(scalars) if scalars else 0.0

    return heldout_eval


def build_serve_seams(
    grpo_config: Any,
    make_trainer: Callable[[RLBackendConfig, VLLMLane, Any], Any],
    *,
    reward: Any = None,
    client_factory: Callable[[RLBackendConfig], Any] | None = None,
) -> tuple[Any, Any, Any]:
    """Wire `(sampler, trainer, heldout_eval)` over one shared `VLLMLane`.

    `make_trainer` is :func:`fieldkit._rl_gpu_trainer.make_trainer` (the torch
    half), injected so this module stays torch-free. The trainer closes over the
    same `lane` it restarts after each step. `client_factory` builds the per-call
    HTTP client (default a real :class:`fieldkit.nim.NIMClient`); tests pass a
    fake to exercise the sampler without a server.
    """
    cfg = RLBackendConfig.from_env(grpo_config)
    lane = VLLMLane(cfg)

    def _default_client(_cfg: RLBackendConfig) -> Any:
        return NIMClient(base_url=_cfg.vllm_url, model=_cfg.lora_name)

    cf = client_factory or _default_client
    _train_sampler = _make_sampler(cfg, getattr(grpo_config, "temp", 0.8), lambda: cf(cfg))
    _heldout_sampler = _make_sampler(cfg, cfg.heldout_temp, lambda: cf(cfg))

    def train_sampler(tasks: Sequence[Any], k: int) -> "list[list[_GpuRollout]]":
        # Step-0 boot: serve the SFT-init adapter before the first rollout; the
        # trainer's restart() owns every swap thereafter.
        lane.ensure_started(cfg.adapter_init)
        return _train_sampler(tasks, k)

    def heldout_sampler(tasks: Sequence[Any], k: int) -> "list[list[_GpuRollout]]":
        lane.ensure_started(cfg.adapter_init)
        return _heldout_sampler(tasks, k)

    trainer = make_trainer(cfg, lane, grpo_config)
    heldout_eval = _make_heldout_eval(heldout_sampler, reward)
    return train_sampler, trainer, heldout_eval
