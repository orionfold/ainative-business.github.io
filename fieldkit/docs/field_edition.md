---
module: field_edition
title: fieldkit.field_edition
summary: The installer / orchestration surface for the Arena Field Edition — the self-serve DGX Spark distributable. Ships the support-matrix check (`fieldkit field-edition doctor`) and the checkpointed Compose bring-up (`fieldkit field-edition up`); the eval gate and signed update channel land at later milestones.
order: 19
---

<!--
  DEFERRED — NOT YET PUBLIC. This page lives in fieldkit/docs/ (one level above
  the website-globbed fieldkit/docs/api/) on purpose: the Field Edition is an
  unlaunched commercial product, and surfacing a public docs card is an M4
  launch-handoff item (Mac-controlled). The `fieldkit.field_edition` module
  itself ships in the public wheel as released code; only the website card is
  deferred. To publish at launch: move this file into fieldkit/docs/api/ and
  add `field_edition` to FIELDKIT_MODULES (src/content.config.ts + the
  arena-app copy + audit_docs.py MODULES — the three-place enum).
-->


## What it is

The engineering side of **Orionfold Arena Field Edition** — the commercial,
self-serve DGX Spark distributable that bundles the proven studio stack
(Arena + Advisor + Cortex + fieldkit + quants + Hermes) behind a ≤3-command
install. The product spec is `_SPECS/arena-field-edition-v1.md`; this module
owns the **installer / orchestration** surface from §7.

It is deliberately **separate from the model + eval work** (the Advisor v0.3
road does not touch this machinery), so the installer can be built on its own
track. The package is pure-stdlib + Typer at import time — the heavy lifting
(Docker Compose bring-up, eval gates, the signed update channel) stays lazy and
lands across M1→M3.

## The matrix check (live today)

`fieldkit field-edition doctor` implements §7's gate: the bootstrap **refuses
on an unmatched DGX OS / driver / CUDA / Container-Toolkit matrix rather than
installing onto an untested base**, naming the failure and the fix.

Following the deterministic-scripts invariant, the verdict logic is a **pure
function** and the I/O is a thin separate layer:

- **`evaluate_matrix(probes, matrix=TESTED_MATRIX)`** — the pure verdict. Takes
  a mapping of already-probed raw strings and returns a **`DoctorReport`**. No
  I/O, fully unit-testable without a DGX box.
- **`probe_environment()`** — the only I/O: best-effort shells out (`nvidia-smi`,
  `docker --version`, `nvidia-ctk --version`) and reads `/etc/dgx-release`,
  returning one raw string per matrix key (or `None`). Never raises.
- **`run_doctor(matrix=TESTED_MATRIX)`** — probe + evaluate in one call (what the
  CLI command uses).
- **`parse_version(value)`** — extract the first dotted-numeric run as an int
  tuple (`"580.159.03"` → `(580, 159, 3)`), so an unparseable probe reads as
  "not detected".

### The data classes

- **`MatrixCheck`** — one requirement in the tested matrix: `key`, `label`,
  `kind` (`"version_min"` or `"present"`), the `tested` baseline, and the `fix`
  to print on failure.
- **`TESTED_MATRIX`** — the five §7 axes: DGX OS, NVIDIA driver, CUDA runtime,
  Docker CE, NVIDIA Container Toolkit.
- **`CheckResult`** — the per-axis verdict: `found`, `status`
  (`"ok"` / `"too_old"` / `"missing"`), `reason`, and `fix`.
- **`DoctorReport`** — the aggregate: `.ok` is true only when every check
  passes; `.failures` lists the ones that don't.

## Minimum-version, not exact-match

Version axes are **minimum-version gates**: a box on a *newer* DGX OS / driver
than the tested baseline passes (refusing a customer for being too new is the
wrong failure), while a too-old base hard-fails with the fix. Each
`MatrixCheck` carries its tested baseline so the report can show "found X,
tested against Y" — making matrix drift visible without making it an error.
Keeping the baseline current against DGX OS churn is the §9 update channel's
job. (At authoring time the dogfood box already ran DGX OS 7.4.0/7.5.0 against
a 7.2.3 baseline — and passed.)

## The bring-up (live today)

`fieldkit field-edition up` implements §7 step 2 — a **checkpointed, re-entrant
phase machine** that brings up the stack and loads the resident Advisor. It
walks an ordered phase list, persists a checkpoint after each, and on a re-run
**resumes from the last good phase** (the box runs ~4.77 MB/s, so a failed pull
must not redo prior work):

`matrix → bundle → pull → stack → sidecar → resident → [verify]`

Same pure-core / thin-I/O split as `doctor`:

- **`render_compose(config)`** (`fieldkit.field_edition.compose`) — the pure
  renderer: config in, the Docker Compose document out as a plain `dict`. Three
  services — pgvector Postgres (`of-cortex-db`), the open embedder
  (`of-embedder`), and a llama.cpp CUDA-13/SM121 lane (`of-advisor-lane`) — on a
  shared bridge, model store mounted read-only, GPU reserved for the CUDA
  services. The Arena cockpit is **not** here: it is the pipx `fieldkit[arena]`
  process on `:7866` (§5), started by the `sidecar` phase.
- **`compose_yaml(config)` / `write_bundle(config)`** — serialize / write
  `compose.yaml` + `.env` into `~/.orionfold/` (lazy `pyyaml`, an `[arena]`-extra
  dep, so `import fieldkit.field_edition` stays core-only).
- **`ImagePin`** — a digest-pinnable image reference. **Pin discipline:** the §9
  "proven matrix" is only proven once every pin is a real `sha256:` digest.
  pgvector is digest-pinned; the Orionfold-built images (open embedder, the
  CUDA-13 lane) are not built yet and carry `PIN_PENDING`. **`unpinned_images()`**
  surfaces them, and the `stack` phase refuses to launch against unbuilt images
  with a named fix rather than a cryptic registry 404.
- **`plan_remaining(state, ...)`** / **`run_up(config, executor=…)`**
  (`fieldkit.field_edition.up`) — the pure planner + the runner loop. Execution
  lives behind an injectable **`Executor`** (`LiveExecutor` shells to Docker /
  HF / the cockpit; tests use a fake), and **`InstallState`** is the
  `state.json` checkpoint.

**M1 status:** `matrix` + `bundle` run for real; `up --dry-run` writes the bundle
and prints the plan without pulling or launching (validated against Docker's own
`docker compose config`). The live phases fail honestly until the proven-matrix
images + a published Q4_K_M GGUF exist (M2). `up` flags: `--dry-run`, `--force`
(ignore the checkpoint), `--verify` (run the §8 gate after bring-up — the next
increment), `--nim-embedder` (the BYO-NGC-key embedder instead of the open
default).

## CLI surface

`fieldkit field-edition <cmd>`:

- **`doctor`** — live: print the matrix verdict (`--json` for machine output);
  exit 0 when satisfied, exit 1 when any check is too-old or missing.
- **`up`** — live: the checkpointed Compose bring-up (above).
- **`verify`** — the next increment: the §8 first-boot eval gate + receipt.
- **`down` / `repair` / `rollback`** and the top-level-style **`update`** —
  milestone-marked stubs so `--help` lists the full surface from day one; each
  body lands at its milestone.
