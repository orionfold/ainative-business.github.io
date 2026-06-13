---
module: field_edition
title: fieldkit.field_edition
summary: The installer / orchestration surface for the Arena Field Edition — the self-serve DGX Spark distributable. Ships the support-matrix check (`fieldkit field-edition doctor`), the checkpointed Compose bring-up (`fieldkit field-edition up`), and the first-boot eval gate + receipt (`fieldkit field-edition verify`); the signed update channel lands at a later milestone.
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
job. (The tested baseline is pinned to the dogfood clean-wipe target: DGX OS
7.4.0 — the running `DGX_SWBUILD_VERSION`, with 7.5.0 the pending OTA — driver
580.159.03, CUDA 13.0.)

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

## The first-boot eval gate (live today)

`fieldkit field-edition verify` implements §8 — the customer-visible eval gate
that runs at first boot (AC-3) and after every update (§9). It walks the five
component gates, applies the **published floors** (no vanity passes), and
**always emits the receipt — pass or fail** (a failed-but-honest receipt is the
brand) to `~/.orionfold/receipts/` (a stable `verify-latest.json` the cockpit
can always read, plus a timestamped archival copy):

| gate | what it measures | floor |
|------|------------------|-------|
| `fieldkit` | import + version + the `doctor` matrix check | all green |
| `advisor` | curveball-v0.2 held-out + the refusal/private-state floor | curveball-v0.2 ≥80%; refusals 9/9 |
| `cortex` | frozen recall set (recall@5) + grounded-contract over live retrieval | recall@5 ≥0.95; citation + refusal contract pass |
| `lane` | resident-lane smoke: reachable + one generation (warm-resident) | lane up + 1 gen (warm default stays resident) |
| `hermes` *(optional, `--hermes`)* | one MCP-driven `fieldkit` tool round-trip | tool call returns |

Same pure-core / thin-I/O split as `doctor`/`up`:

- **`GateRunner` / `LiveGateRunner`** (`fieldkit.field_edition.verify`) — the
  measurement layer (the only I/O): `measure(key, config)` runs one gate and
  returns a raw **`GateOutcome`** (measured `metrics` + an optional `error`),
  never deciding pass/fail. Tests inject a fake runner.
- **`assess_gate(key, metrics)`** — the pure per-gate floor: measured metrics in,
  `(passed, detail)` out. Each floor is a small, individually unit-tested
  function (`ADVISOR_CURVEBALL_FLOOR`, `CORTEX_RECALL_FLOOR`).
- **`evaluate_gates(outcomes, with_hermes=…)`** — the pure verdict: turns the
  measured outcomes into a **`VerifyReport`** (`.ok`, `.failures`, `.summary()`).
  A gate that errored becomes an honest `error` verdict carrying the fix — never
  a silent pass.
- **`VerifyReport.receipt(generated_at=…, **meta)`** — renders the receipt dict
  without a clock (the writer stamps the time), so the receipt shape is pure and
  testable. **`write_receipt(...)` / `run_verify(...)`** are the thin I/O:
  measure → evaluate → always write the receipt → return `(report, path)`.

Every failing gate names the **component, the gate, and the fix** (the §8 failure
UX); the report renders in the Arena cockpit's eval drawer at M2.

**Status:** four of the five gates are measured **live** against the running
stack — the first-boot receipt goes **near-all-green** (4 pass / 0 fail / 0 error
/ 1 skip, live-smoked end-to-end on the box in ~86 s):

- **`fieldkit`** — import + version + the `doctor` matrix (no live stack needed).
- **`advisor`** — `fieldkit.field_edition.advisor` ships a sha-pinned vendored
  frozen curveball-v0.2 set (`data/advisor-curveball-mini.json` — the 21 scored
  packets behind the published 85.7% run, with their BM25 context baked in so the
  gate is corpus-drift-immune) + a pure `score_curveball_set()` (a faithful port
  of the `preflight` scorer); `LiveGateRunner.advisor` replays them through the
  resident lane and applies the floor (curveball ≥80% + refusals 9/9).
- **`cortex`** — **both halves** measured live. The **recall-half**
  (`fieldkit.field_edition.recall`) scores source_recall@5 over a sha-pinned
  vendored frozen recall set against pgvector + embedder (0.977/87 rows). The
  **grounded-contract half** (`fieldkit.field_edition.grounded`) reuses those
  frozen probes (no new artifact) + a faithful port of the Advisor grounded
  prompt: for a deterministic stratified slice, the lane answers over
  live-retrieved context and the shared `advisor.score_output` scores citation
  integrity + refusal hygiene (`contract_pass` = all refuse rows refuse **and**
  the answer/route citation rate ≥ `GROUNDED_CONTRACT_FLOOR`). Live-smoked: recall
  0.977 + citation 19/23 + refusals 16/16 → contract PASS in ~56 s.
- **`lane`** — `LiveGateRunner.lane` proves the resident Advisor lane is reachable
  + serves one generation. Per the §6/§8 reconciliation the warm default is **not**
  torn down at first boot (teardown-clean is the `down`/`repair` gates' job).

Every live gate returns an honest `error` (naming the missing piece + fix) when
its slice of the stack is down — never a vanity pass. The optional `hermes` gate
is `skipped` unless `--hermes` is passed (its MCP round-trip is the remaining
generation-half to wire). `up --verify` runs this gate as its final phase,
collapsing §7 steps 2–3 into one command. `verify` flags:
`--json`, `--hermes`.

## CLI surface

`fieldkit field-edition <cmd>`:

- **`doctor`** — live: print the matrix verdict (`--json` for machine output);
  exit 0 when satisfied, exit 1 when any check is too-old or missing.
- **`up`** — live: the checkpointed Compose bring-up (above).
- **`verify`** — live: the §8 first-boot eval gate + receipt (`--json`,
  `--hermes`); exit 0 when every gate passes/skips, exit 1 otherwise.
- **`down`** — live: the §7 / AC-6 uninstall. Default stops + removes the
  containers + network but **preserves** the Cortex pgdata volume, model store,
  and `arena.db`; `--purge` additionally drops those (explicit opt-in). The
  Arena cockpit is a pipx host process, so its uninstall is printed as the final
  manual step rather than self-destructing the running CLI.
- **`repair <advisor|cortex|lane>`** — live: the §8 failure-UX escape hatch.
  Force-recreates one component's container(s) (re-pulling the pinned image),
  re-pulls its model weights if it owns any, then re-runs only that component's
  §8 gate and prints a fresh honest receipt-line.
- **`update` / `rollback`** — live: the §9 eval-gated, rollback-safe
  proven-matrix channel (fetch → cosign-verify → apply → §8 gate → receipt, with
  auto-rollback to the prior matrix on failure; `rollback` is the manual escape
  hatch). The signed GHCR channel is the only external boundary — `update`
  aborts honestly ("no published channel yet — M3") until the proven-matrix
  images + cosign signatures are published.

**M2/M3 boundaries (honest, not stubbed):** `down`/`repair`/`update` reach real
Docker / HF / channel operations, so on this pre-launch box they stop at the same
unbuilt-infra boundaries `up` does (the unpinned Orionfold images, the
unpublished signed channel) — each with a named fix, never a vanity success. The
orchestration, retention, and auto-rollback logic are complete and unit-tested
now; the live operations light up as the M2/M3 infra lands.

## The AC-7 license file (`fieldkit.field_edition.license`)

The Field Edition license is an **offline-verifiable** entitlement file the
bootstrap drops at `~/.orionfold/license` — a JSON `payload` of claims + a
detached **Ed25519** `signature`, verified locally against a **public key
embedded in the module** (`TRUSTED_KEYS`). No license-server round-trip on every
boot (AC-7: the privacy stance is the brand); the math is the gate.

- **What it carries** — identity + term (`license_id`, `issued_to`, `not_before`
  / `expires_at`, `seats`), coarse `entitlements`, and the **paid boundary**:
  `registry.pull_token` (a GHCR read-scoped token for the private proven-matrix
  images, §9). The signature **binds the token to the license** — that token is
  the entire DRM (no token → no proven-matrix images, but the open repos stay
  usable; revocation = rotating the GHCR token).
- **The signing contract** — `canonical_bytes(payload)` is the exact bytes the
  signature covers, and the Mac/ops `fulfillLicense` issuer must reproduce them:
  `json.dumps(payload, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False).encode()` — compact, **recursively key-sorted**, UTF-8,
  **no floats** anywhere in the payload. The signature value + the embedded
  public key are standard base64.
- **The gate** — `load_license()` parses → `verify_signature()` → enforces the
  term, raising an actionable `LicenseError` on any failure (never a silent pass
  to an unentitled pull). `sign_payload()` is the issuer-side reference (the
  TS port).
- **Keys** — the **production** signing key (`of-license-prod-2026`) is a
  `PROD_KEY_PENDING` slot until ops generates the keypair and embeds its public
  half; the committed **dev-only** key signs the vendored `data/license-sample.json`
  so the schema + tests self-validate. `cryptography` ships in the `arena` extra.
