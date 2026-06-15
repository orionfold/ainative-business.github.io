# Changelog

All notable changes to `fieldkit` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the package is on `0.x`, minor versions may include breaking changes. `1.0` will mark API stability.

## [Unreleased]

## [0.33.1] — 2026-06-15

> The first-customer install is now **one-shot**. v0.33.0's `up` reached
> all-green but forced a re-run and left the cockpit idle on a confusing first
> screen; this patch closes the three onboarding gaps the end-to-end
> first-customer run surfaced (AD-FK-ε / AD-AE / repo_root leak) so a single
> `curl … | sh` lands on a warm, auto-armed Advisor with no hand-driving. Patch
> bump — bug fixes to existing modules, no new public symbol. Offline suite
> green; +5 regression tests. No `--spark` tests (the fixes are offline
> orchestration: a lane health-poll, lane-discovery filtering, and a launch arg).

### Fixed

- **First-customer install is now one-shot — the three onboarding gaps the
  end-to-end first-customer run surfaced (AD-FK-ε / AD-AE / repo_root leak).**
  The v0.33.0 `up` reached all-green but was *not* one-shot: it forced a re-run
  and left the cockpit idle on a confusing first screen. Fixed:
  - **AD-FK-ε — `up.resident` now health-polls the serving lane** instead of
    probing it once. The lane container starts in `stack`, but llama-server
    needs ~60-90 s to load the 2.84 GB GGUF before `:{port}/v1/models` answers;
    a single probe deterministically FAILed on a cold lane and forced the
    customer to re-run `up`. `resident` now polls until the model is loaded
    (the pattern `sidecar` already uses for `:7866`), with ~150 s of headroom
    and an honest timeout fix (`docker logs of-advisor-lane` + re-run).
  - **AD-AE — chat-lane discovery now excludes the Cortex embedder.** The NIM
    embedder (`:8001`) answers OpenAI-compat `/v1/models`, so it was enumerated
    as a selectable *chat* lane → the cockpit saw "2 lanes", resolved the active
    lane "ambiguous", and landed **idle** (the customer had to hand-pick the
    Advisor). `lanes.lane_ports()` now filters the infra ports
    (`launcher.infra_ports()` — the same set the ONE-LANE guard already treats
    as not-a-chat-lane), so the lone Advisor lane auto-resolves
    (`resolve_active_lane` → `source="discovered"`) and the cockpit lands warm.
    Fixes every launch path, not just the installer.
  - **repo_root leak — `up.sidecar` now pins the cockpit's `--repo-root`** to a
    fresh customer-owned dir (`~/.orionfold/arena-root`) instead of letting
    `arena up` default it to the CWD. Launching the installer from a dev
    monorepo would otherwise leak that repo's artifacts/articles/leaderboard/
    models into the customer cockpit; the pinned root yields the honest
    first-boot empty state regardless of where `up` is invoked.

  Patch bump — bug fixes to existing modules, no new public symbol. Offline
  suite green; +5 regression tests (resident warm-poll + honest timeout,
  sidecar repo_root pin, lane_ports infra exclusion + exemption-off).

## [0.33.0] — 2026-06-15

> AD-FK-α/β/γ — the three unattended-orchestration findings from the
> first-customer sim. With these, `fieldkit field-edition up` (and the
> `get-orionfold.sh` bootstrap) is a real unattended `curl … | sh`: it sources
> the NGC key, ingests the demo corpus, and starts the cockpit itself. Minor
> bump for the new `fieldkit.field_edition.ingest` submodule + the `ingest` CLI
> command + public symbols. Offline suite: **1743 passed / 0 failed / 16
> skipped** (164 field_edition tests). No new `--spark` tests — the live ingest
> path is operator-armed (the first-boot sim); the unit tests mock `MemoryIndex`.

### Added

- **`fieldkit.field_edition.ingest` + an `up` `ingest` phase (AD-FK-β) — a fresh
  box now seeds the Cortex corpus automatically, so `up` is a real unattended
  `curl … | sh`.** A fresh Field Edition box boots an EMPTY pgvector, so the §8
  Cortex gate could not pass until the Advisor demo corpus was ingested — and
  `up` had no ingest phase (the first-customer sim had to ingest by hand). The
  corpus now rides the wheel as a self-contained, sha-pinned vendored pack
  (`data/advisor-corpus-pack-v01.jsonl.gz`, ~1 MB gz, 182 public sources, built
  by `scripts/field_edition/build_advisor_corpus_pack.py`); `up`'s new `ingest`
  phase (after `stack`) chunks→embeds→upserts it **offline** into
  `advisor_corpus_v01`, reproducing the exact **647 chunks** the recall@5 0.977
  proof was measured against — no network, no auth (AC-2). Idempotent (a
  non-empty corpus is left as-is, so a customer's own ingest is never
  clobbered); honest `PhaseError` with a fix if the embedder/pgvector is down.
  Also exposed as `fieldkit field-edition ingest [--force]` (the manual /
  re-ingest hatch). Wheel-vendored over HF/GitHub (operator decision,
  2026-06-15): the bootstrap already pulls the wheel, so the pack costs zero
  extra fetches — the inverse of the 2.6 GB GGUF, which is too big to vendor.

### Fixed

- **`fieldkit.field_edition` — the NGC API key is now wired into every Compose
  op (AD-FK-α).** The v1 default Cortex embedder is the NGC NIM image, whose
  Compose service interpolates `${NGC_API_KEY:?…}`, but an unattended `up` never
  sourced the operator's key — so `up` (stack phase), `down`, and `repair` all
  failed at the Compose boundary on a real `curl … | sh` box. New
  `compose.read_ngc_api_key()` (env → `~/.nim/secrets.env`) + `compose.compose_env()`
  inject the key into the subprocess environment for every `docker compose`
  call; `up`'s `stack` phase refuses up front with a named fix when no key is
  resolvable (rather than a cryptic Docker error), `down`/`repair` use a harmless
  placeholder when a teardown does not need a real key. The bootstrap
  (`get-orionfold.sh`) also sources `~/.nim/secrets.env` (belt-and-suspenders;
  the Python side is authoritative).
- **`fieldkit.field_edition.up` — the `sidecar` phase now STARTS the Arena
  cockpit (AD-FK-γ).** It previously only health-polled `:7866` and raised if
  absent, so an unattended `up` hard-stopped (the operator had to launch the
  cockpit by hand). It now spawns the pipx/venv `fieldkit arena up --no-open`
  detached (`start_new_session`, logging to `~/.orionfold/cockpit.log`, pid in
  `cockpit.pid`), then health-polls until ready — failing honestly if the
  cockpit exits early or never becomes healthy. Re-entrant: a re-run returns
  immediately when the cockpit is already up.

## [0.32.3] — 2026-06-15

### Added

- **`fieldkit.field_edition.verify` — the optional §8 `hermes` gate is now
  measured LIVE (the last unwired first-boot verify gate).** `LiveGateRunner.hermes`
  drives the `fieldkit`-as-MCP server — the exact surface a Hermes harness drives
  — with a real MCP client over stdio (`initialize` → `list_tools` → `call_tool`),
  confirming one read-only tool round-trip (`spark_inference_envelope`) returns.
  The probe is a capabilities lookup (no GPU, model, disk, or network), so it is
  **lane-safe** (the resident Advisor lane the other gates proved warm is
  untouched, honoring the one-lane invariant) and **deterministic**, running well
  inside the ~30 s budget. Like the Cortex recall-half, it does NOT depend on the
  operator-armed serving lane — so `verify --hermes` now renders `Hermes → pass`
  end-to-end. Honest `error` (never a vanity pass) when the `fieldkit[harness]`
  extra (the `mcp` SDK) is missing or the transport fails; the MCP round-trip is
  an injectable seam (`_mcp_tool_roundtrip`) so the floor logic is unit-testable
  without the SDK or a subprocess. The brain-driven full Hermes agent run stays
  the heavier H4 milestone (a 30B MoE brain would violate the one-lane budget at
  first boot), not a first-boot gate.

### Fixed

- **`fieldkit.field_edition.advisor` — the refusal scorer no longer false-FAILs
  valid refusals phrased without the canonical "does not support" clause.**
  Surfaced by the first-customer happy-path simulation (running the real
  `get-orionfold.sh` bootstrap end-to-end on a pristine box): the Q4_K_M Advisor
  lane refuses correctly but in ≥2 wordings (temp-0 llama-server is not
  bitwise-deterministic), and a valid refusal such as *"…does not include private
  or live operator state, so this question's scope is **unsupported**. Citations:
  []"* matched none of `_REFUSAL_WORDS`. With the §8 cortex grounded-contract's
  all-or-nothing 16/16 refusal-hygiene threshold, that one unrecognized phrasing
  **deterministically failed the cortex verify gate on a healthy box** (recall
  0.977 + citation 95.7% both passed; the model was refusing correctly — the
  scorer was wrong). Broadened `_REFUSAL_WORDS` with the lane's actual decline
  vocabulary (`"does not include"`, `"unsupported"`, `"out of scope"`).
  `refusal_ok` is consulted only for expected-`refuse` rows, so answer/route
  scoring is untouched and the published Advisor curveball contract is unchanged
  (re-verified live: 85.7% / refusals 9/9, same 3 misses; cortex now PASS, 16/16).
  NOTE: this diverges the `field_edition` scorer from its
  `scripts/orionfold_advisor/preflight._score_output` port — preflight (the
  frozen-receipt generator) should get the same broadening for fidelity, deferred
  (re-freezing published receipts is operator-gated). +1 regression test → 142
  `field_edition` tests.

### Test suite

- **6 new `field_edition` tests** — 5 for the hermes gate (round-trip passes /
  empty-result fails / missing-extra errors honestly / transport-failure errors
  honestly / a real end-to-end stdio MCP round-trip against the live `fieldkit`
  server) + 1 regression for the refusal-scorer fix (the 4 valid refusal
  phrasings the Q4_K_M lane actually emits all score as refusals) → **142
  `field_edition` tests** (was 136). `test_live_runner_bench_gates_error_honestly`
  dropped `hermes` (it no longer depends on the serving stack).

## [0.32.2] — 2026-06-13

### Changed
- **`fieldkit.field_edition.license` — the production signing key is now
  provisioned (`of-license-prod-2026` flipped off `PROD_KEY_PENDING`).** Ops
  generated the prod Ed25519 keypair and delivered the public half (relay
  2026-06-13); it is embedded in `TRUSTED_KEYS`, so a license signed by the prod
  seed now verifies on a released box — the one remaining dependency blocking
  live license verification. The private seed never leaves the commerce plane
  (Supabase secret `LICENSE_SIGNING_SEED_B64` + an offline ops-vault backup);
  rotation stays additive. `verify_signature` against the prod slot is now gated
  by real Ed25519 verification rather than the "not provisioned" guard.

### Test suite
- **1712 passed, 19 skipped** (offline `pytest`; skips = torch/mcp/matplotlib/
  great_tables/jupytext heavy deps + `--spark`). 136 `field_edition` tests
  (unchanged count — `test_prod_key_pending_is_honest` became
  `test_prod_key_is_provisioned` for the embedded prod key).

## [0.32.1] — 2026-06-13

### Changed
- **`fieldkit.field_edition.license` — the mandatory GHCR `pull_token` is dropped
  (OPEN-1: public images, weights are the moat).** A v1 license is now **claims +
  term only** — no `registry` block, no pull credential. The `registry` field is
  **optional**: `License.registry` is `None` for a current license, and
  `License.pull_token` returns `""`. The detached Ed25519 signature still covers
  whatever the payload contains, so an **older token-bearing license keeps
  verifying unchanged** (back-compat). The vendored `data/license-sample.json` and
  the shared `data/license-conformance-v1.json` (`full-license-founding25` case)
  are re-frozen to the token-less shape; the dev-key signatures re-froze with
  them. Mac's `fulfillLicense` simply stops populating `registry` — its CI mirror
  re-canonicalizes + re-signs each conformance case against the new vector.

### Test suite
- **1712 passed, 19 skipped** (offline `pytest`; skips = torch/mcp/matplotlib/
  great_tables/jupytext heavy deps + `--spark`). 136 `field_edition` tests (was
  134 — added token-less-validates + legacy-token-bearing back-compat).

## [0.32.0] — 2026-06-13

### Added
- **`fieldkit.field_edition.cosign` — verify the §9 proven-matrix images, and
  `LiveUpdateChannel.verify_signature` wired live.** The update channel now
  cosign-verifies every Orionfold image in a fetched proven matrix against a
  **pinned public key** (`PROVEN_MATRIX_COSIGN_PUBKEY`) before applying it —
  `verify_matrix()` filters to the digest-pinned `ghcr.io/orionfold/*` images
  (skipping upstream pgvector + the NVIDIA NIM embedder) and runs `cosign verify
  --key` on each, raising an actionable `CosignVerifyError` on a bad/absent
  signature or a missing cosign binary. The pinned key is **key-based, not
  keyless** (Fulcio is network-blocked on the Spark box; the images are signed
  with a long-lived key whose private half + `COSIGN_PASSWORD` stay in the
  orionfold secret store) and byte-matches the committed
  `deploy/field-edition/cosign/proven-matrix.pub` — the same
  pin-a-committed-public-key pattern as `license.TRUSTED_KEYS`. The cosign
  subprocess is injected (the `runner` seam) so the verification control flow is
  unit-testable without the binary. `LiveUpdateChannel.fetch_latest` still raises
  honestly — the *hosted release feed* to fetch a new matrix from is the
  remaining M3 piece — but verification is a real gate now that the proven-matrix
  lane image is signed (end-to-end verified live against the pinned key).
- **`fieldkit.field_edition.license` — the AC-7 v1 license file (schema +
  offline Ed25519 verify).** The Field Edition license is an offline-verifiable
  JSON entitlement file (`~/.orionfold/license`): a `payload` of claims + a
  detached **Ed25519** `signature`, verified locally against a **public key
  embedded in the module** (`TRUSTED_KEYS`) — no license-server round-trip on
  every boot (AC-7; the privacy stance is the brand). The payload carries
  identity + term (`license_id` / `issued_to` / `not_before` / `expires_at` /
  `seats`), coarse `entitlements`, and the **paid boundary**: `registry.pull_token`,
  a GHCR read-scoped token for the private proven-matrix images (§9) that the
  signature **binds to the license** (no transplanting a token into a forged
  file). That token is the entire DRM — no token → no proven-matrix images, but
  the open repos stay usable; revocation is rotating the GHCR token. **The
  signing contract** (`canonical_bytes`, which the Mac/ops `fulfillLicense`
  issuer must match byte-for-byte): the signed bytes are
  `json.dumps(payload, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False).encode()` — compact, recursively key-sorted, UTF-8, **no
  floats**; the signature value + the embedded public key are standard base64.
  `load_license()` parses → verifies the signature → enforces the term, raising
  an actionable `LicenseError` on any failure (never a silent pass to an
  unentitled pull). The **production** signing key (`of-license-prod-2026`) is a
  `PROD_KEY_PENDING` slot until ops generates the keypair and embeds its public
  half; a committed **dev-only** key (seed `bytes(range(32))`) signs the vendored
  `data/license-sample.json` so the schema + tests self-validate. `cryptography`
  is added to the `arena` extra (the installer surface). **`tier` / `edition` /
  `entitlements` use a *soft* known-set** (`KNOWN_TIERS` / `KNOWN_EDITIONS` /
  `KNOWN_ENTITLEMENTS`): recognized values are surfaced for display/telemetry and
  an unrecognized one logs a one-line "treating as generic" warning — but is
  **never rejected** (these are descriptive, not security-bearing; strict
  validation would couple SKU velocity to the installer's release cadence and let
  an older installer hard-reject a newer edition). Unknown entitlements are
  ignored, not rejected, so an installer that predates one degrades gracefully.
  10 new tests.
- **License canonicalization+signing conformance vector** — a frozen
  `data/license-conformance-v1.json` (built by
  `scripts/field_edition/build_license_conformance_vector.py`, `--check`
  round-trips) that makes the two-owner signing contract executable on both
  sides (Spark's verifier + Mac's `fulfillLicense` issuer). Four cases stress
  the cross-language canonicalization traps (recursive key sort, compact
  separators, UTF-8 non-ASCII, integer/bool/null with no floats); each carries
  the exact `canonical_utf8` / `canonical_sha256_12` / dev-key `signature_b64`.
  A new test asserts the live `canonical_bytes`/`sign_payload` still reproduce
  the vector (drift guard); the Mac side adds a mirror assertion to its CI so
  one byte of divergence is caught before it silently fails every license. The
  vector self-documents the JS port and signs only with the throwaway dev key.
  1 new test.
- **`fieldkit.field_edition` — the Arena Field Edition installer surface (M1
  scaffold).** New package owning the §7 installer/orchestration commands for
  the self-serve DGX Spark distributable (`_SPECS/arena-field-edition-v1.md`),
  on its own track separate from the Advisor model/eval work. Live today:
  **`fieldkit field-edition doctor`** — the support-matrix check the bootstrap
  runs before touching the box (DGX OS / driver / CUDA / Docker / Container
  Toolkit), with `--json`. The verdict is a pure function (`evaluate_matrix`)
  over a thin probe layer (`probe_environment`), so it is unit-testable without
  a DGX box; version axes are **minimum-version gates** (a newer-than-tested box
  passes, a too-old base fails with a named fix). Verified green live on the
  dogfood box; the tested matrix is pinned to that clean-wipe target (DGX OS
  7.4.0 / driver 580.159.03 / CUDA 13.0). The remaining command
  group (`verify`/`down`/`repair`/`rollback`/`update`) is declared as
  milestone-marked stubs so `fieldkit field-edition --help` lists the full
  surface from day one. 14 new tests. The public docs card is deferred to the
  M4 launch handoff (the module ships in the wheel; only the website card waits).
- **`fieldkit field-edition up` — the §7-step-2 Compose bring-up.** A
  **checkpointed, re-entrant phase machine** (`fieldkit.field_edition.up`):
  `matrix → bundle → pull → stack → sidecar → resident → [verify]`, persisting a
  checkpoint to `~/.orionfold/state.json` after each phase so a re-run resumes
  from the last good phase (the box runs ~4.77 MB/s — a failed pull must not
  redo prior work). Same pure-core / thin-I/O split as `doctor`: a pure
  `render_compose()` → the digest-pinned Docker Compose bundle as a `dict`
  (`fieldkit.field_edition.compose`: pgvector + open embedder + a llama.cpp
  CUDA-13/SM121 lane, model store read-only, GPU reserved), `plan_remaining()`
  the pure planner, and an injectable `Executor` so the live Docker/HF/cockpit
  shell-outs are isolated and the runner is testable with a fake. Pin discipline
  via `ImagePin`/`unpinned_images()`: pgvector is digest-pinned, the
  not-yet-built Orionfold images carry `PIN_PENDING`, and the `stack` phase
  refuses to launch against them with a named fix (no cryptic registry 404).
  `up` flags: `--dry-run` (run only the safe local phases — matrix gate + write
  the bundle — and print the rest of the plan), `--force`, `--verify`,
  `--nim-embedder`. M1 status: `matrix` + `bundle` run for real today
  (`--dry-run` verified live; the bundle validated against `docker compose
  config`); the live phases fail honestly until the proven-matrix images + a
  published Q4_K_M GGUF exist (M2). `verify` (the §8 gate) is the next
  increment. 18 new tests.
- **`fieldkit field-edition verify` — the §8 first-boot eval gate + receipt.**
  Runs the five-gate battery (`fieldkit` · `advisor` · `cortex` · serving
  `lane` · optional `hermes`), applies the **published floors** (no vanity
  passes — Advisor curveball-v0.2 ≥80% + refusals 9/9, Cortex recall@5 ≥0.95 +
  grounded contract, lane launch→generate→teardown smoke), and **always emits
  the receipt — pass or fail** (a failed-but-honest receipt is the brand) to
  `~/.orionfold/receipts/` (stable `verify-latest.json` + a timestamped archival
  copy). Same pure-core / thin-I/O split as `doctor`/`up`: a `GateRunner`
  *measures* each component (the only I/O) and returns raw `GateOutcome`
  metrics, the pure `evaluate_gates()` applies the floors and builds the
  `VerifyReport`, and `VerifyReport.receipt()` renders the receipt dict without
  a clock — so the whole verdict is unit-testable with a fake runner. Every
  failing gate names the **component, the gate, and the fix** (§8 failure UX).
  `verify` flags: `--json`, `--hermes`. M1 status: the `fieldkit` gate is
  measured live now (import + version + the doctor matrix); the bench gates
  (`advisor`/`cortex`/`lane`/`hermes`) report an honest `error` ("not yet wired
  to the live stack — M2") rather than a vanity pass until the proven-matrix
  stack + the pinned Q4_K_M model land. `up --verify` now runs this gate as the
  final phase (collapsing §7 steps 2–3). 20 new tests.
- **`fieldkit field-edition {down,repair,rollback,update}` — the rest of the §7 +
  §9 CLI surface, no longer stubs.** Completes the installer command set so the
  whole `_SPECS/arena-field-edition-v1.md` §7/§9 surface is implemented (each
  command fails *honestly* at the boundaries that still need M2/M3 infra rather
  than stubbing the whole body):
  - **`down`** (`fieldkit.field_edition.down`) — the §7 / AC-6 uninstall. Pure
    `plan_down()` (what is removed vs. preserved) + an injectable
    `DownExecutor`: default `down` removes the containers + network but
    **preserves** the Cortex pgdata volume, model store, and `arena.db` (a later
    `up` comes back warm); `--purge` additionally drops those (the explicit
    "remove my data" opt-in). The Arena cockpit is a pipx host process, not a
    container, so its uninstall is printed as the final manual step rather than
    self-destructing the running CLI. Idempotent on an already-clean box.
  - **`repair <advisor|cortex|lane>`** (`fieldkit.field_edition.repair`) — the §8
    failure-UX escape hatch a failed gate names. Force-recreates one component's
    container(s) (re-pulling the pinned image), re-pulls its model weights if it
    owns any, then re-runs **only that component's §8 gate** and prints a fresh
    honest receipt-line. Pure `plan_repair()` + injectable executor + the
    existing `GateRunner`.
  - **`update` / `rollback`** (`fieldkit.field_edition.update` over
    `fieldkit.field_edition.proven_matrix`) — the §9 eval-gated, rollback-safe
    proven-matrix channel: fetch the new pinned matrix → cosign-verify → apply →
    re-run the §8 gate → emit a fresh receipt, with **automatic rollback** to the
    prior matrix (retained on disk via `save_current`'s current→previous
    rotation) on apply/gate failure; `rollback` is the manual escape hatch. The
    signed GHCR channel is the **only external boundary** — `LiveUpdateChannel`
    raises an honest `UpdateError` ("no published channel yet — M3") instead of
    pretending to update. The retention + auto-rollback decision tree is fully
    unit-tested with a fake channel/applier/gate. 26 new tests (78 field_edition
    total).
- **`fieldkit field-edition verify` — the `lane` + Cortex grounded-contract
  gates are now measured live; the first-boot receipt goes near-all-green.** Two
  more §8 generation-half gates light up against the resident lane, taking the
  receipt to **4 pass / 0 fail / 0 error / 1 skip** (live-smoked end-to-end on
  the box, ~86 s, `ok=True`).
  - **`lane` gate (warm-resident).** `LiveGateRunner.lane` proves the resident
    Advisor lane is reachable (`/v1/models`) and serves one generation. Per the
    §6/§8 reconciliation (the default 4B stays warm and never unloads), first-boot
    `verify` does **not** tear it down — `_assess_lane` floors on launched +
    generated, and "teardown clean" is the `down` / `repair` lifecycle gates'
    job. Unreachable lane → honest `error`; reachable-but-blank generation → a
    real FAIL (report = reality). Live-smoked PASS in 0.2 s.
  - **Cortex grounded-contract half.** New **pure** `fieldkit.field_edition.grounded`
    reuses the already-frozen recall probes (no new frozen artifact) + a faithful
    port of the Advisor grounded prompt: for a deterministic stratified slice of
    the frozen set (every refuse + route row + the first N answer rows per
    family), the lane answers over **live-retrieved** context (the full
    retrieve → ground → generate → cite loop) and the shared
    `advisor.score_output` scores citation integrity + refusal hygiene.
    `contract_pass` requires **all** refuse rows to refuse (hygiene) **and** the
    answer/route citation rate to clear `GROUNDED_CONTRACT_FLOOR` (0.80, the
    Advisor precedent). `LiveGateRunner.cortex` now measures **both** halves and
    merges metrics — recall-half (pgvector + embedder) + grounded-half (the
    lane). Live-smoked: **recall@5 0.977 + grounded citation 19/23 (82.6%) +
    refusals 16/16 → contract PASS in 56 s**; the 4 citation misses are genuine
    model misses (gold present in context, model cited a sibling source), not
    scorer or retrieval artifacts. The stale "embedder image digest mismatch"
    failure-`fix` text is reworded. 12 new tests (113 field_edition total); full
    collectable suite 1294 passed (only the 3 documented env-arena failures).
- **`fieldkit field-edition verify` — the §8 Cortex gate's recall-half is now
  measured live (M2 step 1).** New `fieldkit.field_edition.recall`: a **vendored
  frozen recall set** (`data/cortex-recall-mini.json` — a deterministic
  projection of the already-frozen Advisor recall bench, sha-pinned via
  `RECALL_SET_SHA`, rides the wheel via the `data/*.json` glob, built by
  `scripts/field_edition/build_cortex_recall_set.py`) + a **pure**
  `score_recall_set()` (source_recall@5 over the answerable rows, refusal rows
  excluded; retrieval injected so it unit-tests with a fake). `LiveGateRunner.cortex`
  builds the retrieval closure over `MemoryIndex.query` (pgvector dense,
  source-deduped) and scores the vendored set against the running Cortex stack:
  **live-smoked at recall@5 = 0.977 over 87 rows in 2.7 s** — byte-identical to
  the `score_recall_live.py` proof. The gate still reports an honest non-pass:
  the recall number is real and surfaced in the receipt detail + note, but the
  grounded-contract generation half (citation integrity + refusal hygiene) needs
  the serving lane (M2) — never a vanity pass on recall alone. A load-time sha
  check raises on out-of-band edits to the shipped set (proof-control discipline).
  8 new tests (86 field_edition total).
- **`fieldkit field-edition verify` — the §8 Advisor gate is now measured live.**
  New `fieldkit.field_edition.advisor`: a **vendored frozen curveball-v0.2 set**
  (`data/advisor-curveball-mini.json` — the 21 scored prompt packets behind the
  published 85.7% Q4_K_M run, sha-pinned via `CURVEBALL_SET_SHA`, rides the wheel
  via the `data/*.json` glob, built by
  `scripts/field_edition/build_advisor_curveball_set.py`) + a **pure**
  `score_curveball_set()` — a faithful port of `preflight._score_output`
  (citation integrity, refusal hygiene, workflow routing, thinking-leak,
  private-state-leak), so a row's verdict is byte-identical to the frozen
  receipt. **Why freeze packets, not regenerate:** each packet carries BM25-
  retrieved context baked into its message, and the public corpus manifest grows
  with every article — so the gate ships the exact packets that produced the
  published number, immune to corpus drift. `LiveGateRunner.advisor` replays the
  packets through the resident lane (OpenAI-compatible, `enable_thinking=False`)
  and applies the floor (curveball ≥80% + refusals 9/9); an unreachable lane is
  an honest `error`, never a vanity pass. A load-time sha check raises on
  out-of-band edits (proof-control discipline). The ported scorer is regression-
  locked against the captured Q4_K_M outputs (18/21 = 85.7%, refusals 9/9, the
  three known safe-direction misses). 9 new tests (101 field_edition total).
- **`fieldkit field-edition up` — the `pull` phase is wired (resumable HF GGUF
  download).** `LiveExecutor.pull` now resumably downloads the default Advisor
  GGUF via `hf_hub_download`, pinned by `revision` (a commit sha — an upstream
  re-tag can never silently change the bytes); idempotent (a present model
  short-circuits, so a resumed `up` never redownloads). `LaneConfig` gains the
  HF source (`gguf_repo`/`gguf_revision`/`gguf_file` + a `gguf_pinned` property)
  and a `REV_PENDING` sentinel: until a Q4_K_M rev of `Orionfold/Advisor-GGUF`
  is published + pinned the phase refuses honestly (name the repo + the fix),
  same "drift is visible, not silent" stance as the image digest pins. 3 new
  tests (idempotent / refuses-unpinned / downloads-pinned via a fake).
- **The CUDA-13/SM121 serving-lane image** (`deploy/field-edition/llama-server-cuda13/`).
  A pinned, reproducible multi-stage Dockerfile building llama.cpp `856c3ad`
  (b9128) for CUDA 13.0 / SM121 (GB10 cc 12.1) — the `ghcr.io/orionfold/llama-server-cuda13`
  proven-matrix image (§5: no aarch64+CUDA-13 wheel, so the lane ships as a
  prebuilt container). The build forces the CUDA driver stub onto the link path
  (the build container has no driver; the stub's SONAME `libcuda.so.1` resolves
  at runtime to the Container-Toolkit-injected driver, so the stub is never
  bundled). **Built + smoked live on the box:** serves the Q4_K_M Advisor —
  `/v1/models` 200 in ~3 s (kernels baked, no cold JIT), `/v1/chat/completions`
  → `finish_reason=stop` with correct `reasoning_content`/`content` split.
  **Published 2026-06-13** to `ghcr.io/orionfold/llama-server-cuda13:0.1`
  (`sha256:93993cc2…`) and digest-pinned in `compose.py`.
- **The proven matrix is now fully published + digest-pinned.** `model-Q4_K_M.gguf`
  was published to `Orionfold/Advisor-GGUF` (rev `dad6d1e5…`) and pinned in
  `LaneConfig.gguf_revision`; the lane image is pushed + pinned (above). With
  pgvector + the NIM embedder already pinned, **`unpinned_images()` is now empty
  for the default config** — `up --dry-run` renders an all-`@sha256` Compose
  bundle, so a live `up` resolves the whole stack by digest. Quality-gated before
  publish: the Q4_K_M scored **curveball-v0.2 85.7%** (= the Q8_0 baseline, same
  3 safe-direction misses) + refusals 9/9 on a live lane — the §8 Advisor floor.
  Tests updated (92 field_edition total).

### Changed
- **Arena Field Edition v1 ships the NGC NIM embedder as the default**, not the
  open embedder (which moves to v1.1). The v1 ICP is a DGX Spark operator who
  already holds an NGC key (it's needed to run the Spark stack), so the NIM
  dependency is near-zero friction — and it's a real, **digest-pinned**,
  recall-proven image (the exact embedder behind the §8 recall@5 0.977) instead
  of an unpublished placeholder. AC-2's substance holds: the NGC key is a
  one-time pull/login; the embedder serves locally with no phone-home during
  operation. `default_config()` now uses `NIM_EMBEDDER` (digest-pinned);
  `with_open_embedder()` + `up --open-embedder` select the v1.1 open path. Net:
  the only `PIN_PENDING` image in the default proven matrix is the llama.cpp
  lane. Tests updated (91 field_edition total).

### Fixed
- **AD-FK-1 — the one-lane guard no longer counts the Cortex embedder as a
  resident lane.** The embedder container (`nim-embed-nemotron`, `:8001`)
  answers `/v1/models`, so lane discovery honestly reports it — and the
  AE-R13 ONE-LANE pre-flight refused every guarded chat-lane launch
  (`refused:lane_resident`) whenever the grounded-chat stack was up, while
  `teardown_first` would have pointed the lane kill chain at a
  docker-published port. `launch_lane` now filters infra ports (new
  `launcher.infra_ports()`; default `(8001,)`, overridable via
  `FK_ARENA_INFRA_PORTS`, set EMPTY to turn the exemption off) out of the
  resident set and the `teardown_first` sweep, and `teardown_lane` refuses
  infra ports up front with the new typed reason `infra_port` (manage the
  container with its own lifecycle, e.g. `docker stop`). Memory safety is
  unchanged — the `oom_envelope` gate still checks real MemAvailable. 6 new
  tests.
- **AD-FK-2 — interactive resident-lane eval grades are no longer invisible
  to the live accuracy island.** Chat/compare grades on the resident lane
  used to persist `lane_id='local:resident'` + `cross_vertical=1` (the
  client cannot see what's resident), so `GET /api/eval/leaderboard`
  (default excludes cross-vertical) never surfaced them. The server now
  resolves a resident-shaped lane to its recipe id at score time (new
  `_resident_lane_sid`: matches the resolved resident's model file against
  the operator's lane recipes — exact-path beats basename, ambiguous
  matches refuse rather than guess) and recomputes `cross_vertical`
  server-side for bench rows via the new `benches.lane_matches_bench`
  membership test. `bench_for_lane(...) == bench_id` was also wrong for
  models declared by several benches (the Advisor lanes belong to both
  `advisor-bench` and `cortex-grounded` — grounded compare grades were
  always marked cross-vertical); both persistence sites now use
  membership. 11 new tests.

### Added
- **±Cortex ablation duel — per-side live retrieval in compare
  (grounded-eval-v1 §8 Phase 3).** `POST /api/compare/stream` takes
  `retrieval_a` / `retrieval_b` (free prompt only; eval mode wins): the
  packet is built ONCE through the live Cortex stack and replayed on every
  flagged side, so the SAME lane can run grounded vs ungrounded on one
  question and the score gap reads as the per-question grounding lift. The
  receipt rides each grounded side's `start_{a,b}` event; the `score` event
  carries a `retrieval_ablation: {a, b}` label so the verdict banner stays
  honest. Cortex down is a hard error before either side streams.
  `benches.list_benches()` now marks live-retrieval benches
  (`live_retrieval: true`) so the cockpit can force (and honestly label)
  the Cortex toggle on grounded eval rows. 4 new tests.
- **Grounded receipt projection — `GET /api/grounded/receipts`
  (grounded-eval-v1 §7/§8 Phase 4).** Read-only projection of the offline
  runner's `summary.json` receipts under `evidence/grounded-eval/results/`
  (newest first): pass rate per journey / per component, the ±Cortex
  grounding lift, pack + corpus-manifest shas. Feeds the leaderboard's
  "Grounded (live Cortex)" receipt tier; summaries carry no question/answer
  text by construction. 1 new test.
- **Grounded eval bench — the first LIVE-retrieval bench (grounded-eval-v1).**
  New `cortex-grounded` BenchSpec (`fmt="grounded"`, `live_retrieval=True`,
  rows from `evidence/grounded-eval/` via `FK_ARENA_GROUNDED_DIR`): rows
  carry only the operator-journey question + gold pins (gold sources,
  accepted citations, deterministic `key_facts`); chat/compare eval mode
  builds the packet through the live Cortex stack at send time
  (`cortex_chat.build_packet`) and forces retrieval — Cortex down is a hard
  error, never an ungrounded turn scored as grounded. Compare eval rows
  build the packet ONCE and replay it on both sides (a fair A/B by
  construction); the receipt rides `start`/`start_a` with gold-vs-actual
  `retrieval_hit`. New deterministic `grounded_contract` scorer
  (`score_eval_prediction(..., retrieval=receipt)`): retrieval-hit +
  citation-integrity (cited ⊆ retrieved ∧ ⊇ accepted, `require_all` for
  synthesis rows) + key-facts (contains / regex / numeric-with-tolerance) +
  hygiene; a lost receipt degrades `retrieval_hit` to *unknown* flagged in
  `why` (in-memory turn→receipt map, no arena.db churn). 13 new tests
  (arena suite 507).
- **Cortex-grounded chat — live retrieval over the Advisor corpus pack.**
  `POST /api/chat/stream` takes `retrieval: true` (free prompt only; eval
  rows still replay their measured frozen packets): the new
  `fieldkit.arena.cortex_chat` module retrieves through the production
  Cortex stack (pgvector `advisor_corpus_v01` + NIM embedder — the lane the
  `advisor-rag-source-recall-live` gate passed at 0.977@5), dedupes chunk
  hits to the top-3 unique manifest sources, and builds the byte-compatible
  production packet (900-char query-centered excerpts, `Source N:` labels,
  the measured `/no_think` system contract + `enable_thinking: false` rider
  on local lanes). The `start` SSE event carries a `retrieval` receipt
  (table, manifest sha, deduped source cards with cosine distance); a dead
  Cortex stack is a hard `error` event, never a silent ungrounded turn.
  `GET /api/compare/options` flags advisor-tuned lanes (`advisor: true`),
  carries a `retrieval_source` block (the active corpus pack: table +
  manifest sha + source count — the pack is the swappable OA-NV-8 unit, so
  the label comes from live config), and the ChatLane UI defaults a
  "🧠 Cortex retrieval" toggle ON for advisor lanes, labels the toggle with
  the active pack, and renders per-turn grounded source chips from the
  receipt.
- **Advisor read surfaces in the demo recorder.** `fieldkit arena record` now
  bakes the four Cortex Advisor stubs (`api/advisor/{preflight,corpus,routing,receipt}`)
  so the sidecar-less `/arena/demo/` renders the vertical-proof cards; the stub
  sanitizer additionally strips `endpoint` keys (probed lane URLs) under the
  same no-local-URLs discipline as `base_url`.
- **Advisor release benches in the Arena eval surface.** New `advisor-bench`
  registry entry (`fieldkit.arena.benches`): the frozen 28-row held-out plus
  both external OOD curveballs (40 + 21 rows) browse beside the published
  verticals in the chat/compare eval drawer. Rows replay the *measured* chat
  packets from the tracked `packet_files` receipts — the system contract rides
  a new `EvalPrompt.system_prompt` field that the chat/compare handlers
  prepend as a real system message (every other bench unchanged) — and are
  scored instantly by the new deterministic `advisor_contract` scorer, a
  mirror of `scripts/orionfold_advisor/preflight.py` (citation exactness,
  refusal wording, `Route:` prefix, thinking leak, private-state risk;
  `accepted_source_ids` twin-row credit included). Edited questions re-wrap in
  the packet's own question-first shape.
- **Advisor corpus pane, routing surface, and publish-receipt card**
  (spec §10 + §12; closes the AD-AE-11 read surface and AD-AE-16). Three
  read-only endpoints — `GET /api/advisor/corpus` (manifest digest +
  composition, both recall-gate receipts, the OA-NV-8 corpus-swap fixture
  receipt, SFT-corpus handoff reports), `GET /api/advisor/routing` (§13.F
  bakeoff configs/costs, router policy + revision, T4 governance, every hosted
  escalation with tier/provider/model/cost/verdict, private-state-blocked
  count), and `GET /api/advisor/receipt` (the §14 publish/reject verdict +
  gate matrix) — each rendered as a Cortex card beside the Advisor preflight.

### Changed
- **Cockpit HTML is served `Cache-Control: no-cache`.** The sidecar's `_webui`
  mount was a bare `StaticFiles` (no Cache-Control at all), so Chrome
  heuristic-cached cockpit HTML across `fieldkit arena build` rebakes and
  served stale pre-bake pages two sessions running (the operator-witnessed
  "rebaked but unchanged" trap). HTML responses now carry `no-cache` — the
  browser revalidates every navigation and the existing ETag keeps that a
  cheap 304; hashed `/assets/*` keep their default caching since their names
  change per rebuild. Removes the need for the CDP `Network.setCacheDisabled`
  workaround when verifying post-bake pages.
- **`fieldkit arena import` no longer writes the repo-root mirror by
  default.** `import_artifacts(write_mirror=...)` now defaults `False` and
  the CLI flag is opt-in `--mirror` (`--no-mirror` still accepted as the off
  form). Nothing on the main site reads `src/data/arena-mirror/` — the
  tracked mirror is `fieldkit arena mirror` into `arena-app/` — and the
  default-on write left an untracked root-level turd after every import.

### Fixed
- **Eval mode replays the bench's measured reasoning control (AD-AE-17).**
  Chat/compare eval mode replayed the Advisor packets' system contract
  (including the `/no_think` token) but never sent
  `chat_template_kwargs={"enable_thinking": false}` — and Nemotron-3/Qwen3
  templates ignore the bare token, so advisor rows ran thinking-ON in eval
  mode (operator-witnessed fabrication on a frozen refusal row that the same
  lane refuses cleanly under `preflight.py --reasoning-mode off`). New
  `BenchSpec.reasoning_mode` rider (`"off"` on `advisor-bench`) +
  `benches.reasoning_chat_kwargs()` mirror of `preflight.py _chat`; the chat
  and compare handlers forward the kwargs to **local lanes only** (hosted
  tiers were measured without the kwarg in the §13.F bakeoff, so omitting it
  there also replicates measurement), and `eval_context` surfaces
  `reasoning_mode` in the start events. Benches without a rider keep
  byte-identical payloads.
- **`FK_ARENA_REWARD_DIR` now anchors the reader side too.** The cockpit's
  reward-report *reader* (`_reward_reports_dir` — feeds the reward gauge, the
  AV-10 preflight card, and the build-spine Smoke stage) was hardcoded to
  `evidence/astrodynamics` while the writer
  (`fieldkit.arena.lane.reward_signal_writer`) already honored
  `FK_ARENA_REWARD_DIR`. A non-Kepler run context (e.g. the Orionfold Advisor
  proof, AD-AE-14) rendered Kepler's AV-10 receipts under its own build spine.
  The reader now resolves the same env var with the astrodynamics default,
  mirroring `FK_ARENA_CORPUS_DIR`.
- **Build-spine RLVR stage is vertical-scoped (AD-AE-15).** `arena.db` is
  shared across verticals, so the RLVR card read the *newest* `rl_run` row
  unfiltered — Kepler's `rl-000 · 96% held-out` rendered DONE under the
  Advisor spine (report≠reality). The read is now scoped by result-carried
  identity (no schema change): the job's `payload.bench_id` prefix-matches the
  spine's manifest `bench_id`, or the result's `vertical`/`domain` equals the
  spine's vertical. A job carrying neither identity stays invisible to a
  scoped spine; an unscoped (no-manifest) spine keeps the legacy newest-row
  read.

### Verified live (on the dogfood DGX Spark)
- **cosign signing + verify, end-to-end.** The proven-matrix lane image
  (`ghcr.io/orionfold/llama-server-cuda13@sha256:93993cc2…`) was key-signed
  (Rekor tlog index `1810763259`) and `LiveUpdateChannel.verify_signature`
  verified it against the pinned `PROVEN_MATRIX_COSIGN_PUBKEY` with the real
  cosign binary. Key-based because Fulcio is network-blocked on the box.
- **First-boot `fieldkit field-edition verify` near-all-green** (4 PASS / 0 fail
  / 0 error / 1 skip): the `advisor` (85.7% curveball, refusals 9/9), `cortex`
  (recall@5 0.977 + grounded citation 82.6%, refusals 16/16), and warm-resident
  `lane` gates measured live against the resident stack; only optional `hermes`
  unwired.

### Test suite
- Offline: **1710 passed, 19 skipped** (skips are torch / `mcp` / matplotlib /
  great_tables / jupytext heavy-optional deps + the `--spark` live gates). The
  `field_edition` surface alone is **134 tests** (doctor / up / verify / down /
  repair / update + the §8 advisor / cortex-recall / cortex-grounded / lane live
  gates + the AC-7 license + the cosign verification + the conformance vector).

### Articles in this release
- None new assume this version — it is an **installer-surface** release (the
  Arena Field Edition §7–§9 commands + the AC-7 license + cosign verification).
  The Orionfold Advisor public-launch series landed in this window but assumes
  the model / eval surface, not `field_edition`.

## [0.31.0] — 2026-06-07

The fourth arena-enhancements **v2** cut: **AE-31 guarded lane launch + teardown**
(the dedicated launch-runner cut, risk class AE-R13 — the AE-22 launch half and
AF-20 arm/teardown half deferred from cuts 2–3), plus the demo recorder
extensions behind the public Arena demo's "full glory" pass.

### Added
- **AE-31 — guarded lane launch + teardown (`fieldkit.arena.launcher`).**
  Serving becomes an Arena operator action: new `JobKind.LANE_LAUNCH` /
  `LANE_TEARDOWN` run operator-authored **lane recipes**
  (`~/.fieldkit/arena/lane-recipes.json`, the once-memorized launch command
  stored as data; `GET /api/lane-recipes` lists summaries) through a
  **pre-flight brake** — every side-effect-free check runs BEFORE the one
  destructive step: launch lock → recipe → binary → GGUF existence →
  unified-memory envelope (`estimate_lane_gb`) → fused ONE-LANE/port check. A
  resident lane refuses the launch unless the operator explicitly passed
  `teardown_first`; a doomed launch never tears a working lane down. Spawn is
  **detached** (`start_new_session=True` + an atomic owner file) so a launched
  lane survives sidecar restarts; teardown is **verified** (owner-pid kill with
  a PID-reuse cmdline guard, targeted fallback — never a broad pkill for
  llama.cpp, EngineCore-aware stop only for vLLM-kind lanes; "released" is
  *observed*: process group empty + port refused). Refusals raise
  `LaunchRefused` and persist as honestly-failed job rows (`refused:<reason>`).
  Frontend: `<LaneTruth>` gains the launch form + per-lane teardown buttons,
  `<BuildSpine>` the lane-stage wiring, the Jobs board the launch-job cards.
- **Demo recorder extensions (`fieldkit arena record`).** Twelve new sanitized
  stub endpoints (build · sft-progress · reward-signal · standup · jobs ·
  leaderboard/live · active-lane · lane-recipes · guardrail-config · prices ·
  corpus-progress · runtimes) so a recorded demo renders every cockpit pane,
  not just chat/compare; a new **recursive host-path scrubber** (`_scrub_str`)
  catches absolute paths *inside* string payloads (`result_json`,
  `lineage_card`) that the dict-level scrub missed; new **`--stubs-overlay`**
  flag merges a checked-in showcase overlay (`arena-app/arena-demo-sim/`) over
  the recorded stubs — enriched jobs board, standup queue, lane recipes, a
  discovered active lane, Cortex before→after.

### Test suite
- Offline: **1496 passed, 19 skipped** (+51: `tests/arena/test_launcher.py` — recipe
  loading / every pre-flight refusal / envelope math / owner-file contract;
  `tests/arena/test_launch_process.py` — real-process detached spawn +
  verified teardown; `tests/arena/test_fixtures.py` — the 12 stub recorders /
  `_scrub_str` recursion / overlay merge; plus `test_jobs.py` /
  `test_jobs_api.py` / `test_server.py` / `test_runtimes.py` extensions).
  No `arena.db` schema change (`user_version` stays 6).

### Verified live
- The demo bundle (headless playwright, 2026-06-07): all 13 panes render
  simulated-from-real-runs data (disclosed on the ribbon), the dispatch
  simulation animates queued→running→done, 0 console errors / 0 sidecar
  escapes; the live cockpit re-baked + restarted on the same source. The
  **real guarded lane-launch from the LaneTruth form stays operator-armed**
  (AE-R1-style) — the launcher's pre-flight + real-process spawn/teardown are
  covered by `test_launch_process.py`; the live rep lands on the next armed
  serve.

## [0.30.0] — 2026-06-06

The third arena-enhancements **v2** cut: **Cluster I core** — the observation +
dispatch system-of-record fixes harvested by the S1 e2e smoke, with every
guarded-launch risk (AF-20 arming · AE-22 launch) deliberately deferred to the
dedicated launch-runner cut (AE-R13).

### Added
- **AE-26 — inventory truth on the build spine (AF-19 / OBS-2).** Each
  `build-manifest.json` stage may declare its `artifacts`
  (`[{path, rows?, files?}]`); `GET /api/build` **verifies them on disk at read
  time** (exists · line-count vs the claimed `rows` · directory file-count ·
  bytes · mtime — the AE-8 live-count pattern, generalized) and ships the
  observation as a per-stage `inventory` facet; `<BuildSpine>` renders the chips
  (`600/600 ✓ · 3d`, `missing ✗`, `✗ drift`). "DONE · 600 rows" can no longer be
  an unchecked assertion (P1). Binaries are stat'd, never read — an 8.7 GB GGUF
  costs one `stat()`. The tracked Kepler manifest now declares the real corpus /
  bench / publish artifacts.
- **AE-27 — corpus-gen request handshake + producer liveness (AF-22 / OBS-3).**
  `POST /api/corpus-request` writes one atomic intent file
  (`corpus-request.json`, the GS-1 pattern) beside the heartbeats; the
  in-CC-session synth skill polls + fulfils it — Arena never imports skill code
  (AE-R3). Fulfilment is an **observation** (a heartbeat stamped after the
  request), surfaced with `GET` / withdrawn with `DELETE`. Producer **liveness**
  is heartbeat-mtime freshness (`live ◉` within `FK_ARENA_CORPUS_LIVE_S`,
  default 180 s · `⚠ stale` when a "running" heartbeat stopped stamping — the
  OBS-3 blind spot, finally distinguishable · `done` · `none`); it rides the
  corpus stage card, `/api/corpus-progress`, and a new **Corpus handshake**
  block on the Build pane (request form · open-request state · withdraw).
- **AE-29 — operator-armed `sft_run` dispatch (AF-21 dispatch half).** SFT was
  the one core build stage with no Arena dispatch surface. New
  `JobKind.SFT_RUN` + curated harness tool `run_sft_training(recipe_path, mode,
  run_label)` (`TrainRecipe.from_yaml` → `fieldkit.training.run`, which already
  stamps the canonical AE-25 heartbeat — the SFT pane follows the run live with
  no extra wiring). **Operator-armed twice over:** `POST /api/jobs` forces
  async-only (like `rl_run` — training never drains in a request
  BackgroundTask), and a **drain brake** releases the claim back to `queued`
  (audited, `budget_defer`) unless the draining process exports
  `FK_SFT_RUN_ARMED=1`; `ArenaStore.claim_next_job` gains `skip_ids` so the
  held job never starves the queue behind it. Jobs board: an **Arm SFT run**
  form (recipe × smoke/full), an `⏸ awaiting armed drain` cue on the queued
  card, and a completion digest (`backend · iter N/M · wall`).
- **AE-30 — runtime readiness, read-only (AF-20 observation half).**
  `GET /api/runtimes`: the runtimes the build/serve stages depend on, observed —
  serve lanes via the AE-18 discovery sweep, training containers
  (`FK_ARENA_RUNTIME_CONTAINERS`, default `nemo-train,ps-train`) via one
  short-timeout `docker inspect` (state `up/stopped/absent/unknown`; the exit
  code is never trusted, stdout is), pgvector + the NIM embedder via direct TCP
  probes. Cached ~8 s (AE-R7); a box without docker degrades to `unknown`,
  never an error. `<BuildSpine>` renders the **Runtimes** roster; the guarded
  arm/teardown half stays deferred to the AE-22 launch-runner cut (same
  AE-R13 risk class).

### Fixed
- The drain pass no longer re-claims a row it just released: `drain_jobs`
  threads the released ids through `claim_next_job(skip_ids=…)` (previously the
  brake pattern had to `break` the whole pass to avoid spinning).

### Test suite
- Offline: **1445 passed, 19 skipped** (+26: `tests/arena/test_corpus_request.py`
  — handshake roundtrip / observed-fulfilment / liveness states / 422 bounds;
  `tests/arena/test_runtimes.py` — roster states / docker-less degradation /
  cache / inspect-parser contract; `test_jobs.py` + `test_jobs_api.py` — the
  sft_run brake (unarmed release + no-starvation), armed dispatch + persist,
  honest armed-failure, `skip_ids`, async-only API contract; `test_build_spine.py`
  — inventory match / drift / missing / dir-claim / binary-stat-only).
  No `arena.db` schema change (`user_version` stays 6).

### Verified live (CDP browser-smoke, 2026-06-06)
- Against the running cockpit on the rebaked bundle (seed → verify → revert):
  the inventory chips verified the **real Kepler artifacts** at read time
  (`600/600 ✓ · 120/120 ✓ · 44/44 ✓ · 8.7 GB ✓`, with ages); the runtimes
  roster matched the box exactly (`pgvector up · ps-train stopped · nemo-train
  absent · lane down — GPU free · embedder down`); the corpus handshake drove
  request (UI form) → a synthetic heartbeat fulfilled it (`fulfilled ✓ ·
  synth ◉ live`, the AE-6 strip lit from the same heartbeat) → withdraw +
  heartbeat delete reverted honestly; an `sft_run` queued from the Jobs arm
  form rendered the `⏸ awaiting armed drain · FK_SFT_RUN_ARMED=1` cue and the
  cancel DELETE was verified on the wire. All smoke rows + files reverted.

## [0.29.0] — 2026-06-06

The second arena-enhancements **v2** cut: the **Cluster G frontend** (AE-21 multi-lane
truth · AE-22 select, launch deferred per AE-R13) and **Cluster H run-context
orientation** (AE-23 run identity + current-run banner · AE-24 per-pane provenance
chips + stale-dimming — OBS-5/AF-26, the operator-raised "is this even my run?").

### Added
- **AE-23 — run identity (`GET /api/run-context`).** Derives the *current run* from
  the build-manifest vertical/label + the reconciled active lane. The run **anchor**
  is the instant the operator selects/arms a lane (`POST /api/active-lane` now stamps
  `set_at`, the spec AE-19 shape); honest when unanchored — no selection ⇒
  `anchored:false` and no this-run/prior-run claims anywhere. The telemetry rail
  renders it as a global **Run** cell (`Kepler · armed 2m ago · model-Q8_0.gguf`,
  or `lane live · select to anchor`).
- **AE-24 — per-pane provenance chips + stale-dimming.** A shared `<ProvenanceChip>`
  (`run-id · relative-age · live ◉ / prior ○`, the AE-16 pattern) on the SFT pane,
  Reward pane, and Build spine; the Jobs board and the leaderboard's live eval group
  label + visibly dim every card/row stamped **before** the run anchor (`○ prior
  run`, hover restores). `/api/sft-progress` run summaries gain `mtime` (parity with
  reward runs) so the chip can date the shown source.
- **AE-21 — multi-lane truth surfaces.** New `<LaneTruth>` section on the Models pane:
  every discovered resident lane with its self-reported identity, the active lane
  marked with its winning source, an explicit **drift banner**, the demoted Hermes
  hint labelled as an assertion, and an honest "no lane resident — arm one" empty
  state (launching stays a CLI step, AE-R13). The rail's lane cell gains a `⚠ drift`
  / `N lanes` badge; the cockpit `CurrentLane` card gains source + drift chips and
  drops its stale hermes-config copy.
- **AE-22 — select-a-lane UI (select half).** Selecting a discovered lane (or
  **pinning** the auto-active single lane — `pin · anchor run`) persists the
  operator selection to the AE-19 registry and anchors run-context; clear-selection
  reverts to pure discovery and un-anchors. Verified live over CDP: discover →
  pin → rail flips to `armed just now` → prior data dims (14 job cards · 8 live
  leaderboard rows · SFT/Reward chips) → lane killed ⇒ drift banner + rail badge →
  clear ⇒ honest unanchored revert.

### Fixed
- **The active-lane registry never participated in lane resolution.** `server.
  _resolve_active_lane` called the pure resolver without loading the registry file,
  so an operator selection was write-only — `POST /api/active-lane` persisted it but
  routing/rail kept resolving as if no selection existed (and registry drift could
  never surface). The Cluster G smoke only exercised pure discovery, so it slipped;
  the cut-2 endpoint tests caught it.

### Test suite
- Offline: **1419 passed, 19 skipped** (+6: `tests/arena/test_run_context.py` —
  run-context shape, the select→anchor→clear cycle, registry-drift surfacing,
  dead-port 404). No `arena.db` schema change (`user_version` stays 6).

### Verified live (CDP browser-smoke, 2026-06-06)
- Against the running cockpit with a synthetic llama-server-shaped lane on `:8091`
  (seed → verify → revert): discovery lit the LaneTruth roster with no config edit →
  **pin · anchor run** flipped the tag to `ACTIVE · operator-selected` and the rail
  Run cell to `Kepler · armed just now · model-Q8_0.gguf` → 14 prior job cards +
  8 live leaderboard rows dimmed `○ prior run`, SFT/Reward chips dated their shown
  sources as prior → killing the pinned lane raised the LaneTruth drift banner +
  the rail `⚠ drift` badge → clear-selection reverted to the honest unanchored
  state (no prior-run claims anywhere).

## [0.28.0] — 2026-06-06

The first arena-enhancements **v2** cut (`_SPECS/arena-enhancements-v2.md`): **Cluster G
lane-truth** (AE-18…22 — Arena becomes the system of record for the serving lane) plus the
**v2 bug-fix cluster** — the four HIGH bugs + three integrity findings harvested by the e2e
operator-smoke run S1 (2026-06-06), every one root-caused on a real run before it was fixed.

### Added
- **Cluster G — lane truth (AE-18…22, OBS-4).** Arena used to learn "what lane is
  serving" from `~/.hermes/config.yaml` — a *foreign tool's assertion* — so a real
  Kepler-Q8 lane on `:8091` rendered as `CONFIGURED LANE · Qwen3-30B · idle`. New
  **`fieldkit.arena.lanes`**: `discover()` probes `FK_ARENA_LANE_PORTS` via
  `/v1/models` + llama.cpp `/props` (cached ~8 s, best-effort); an Arena-owned
  **active-lane registry** (`~/.fieldkit/arena/active-lane.json`, the GS-1 atomic
  file pattern — no `arena.db` schema change) with `GET`/`POST /api/active-lane`;
  `resolve_active_lane()` reconciles registry ∩ discovery with **explicit drift**
  (never silently trusts a stale claim). Chat / compare / judge routing, the rail,
  `/api/lanes`, and the build-spine Lane card all read the reconciled lane; the
  Hermes config is demoted to an optional, labelled hint (removing it breaks
  nothing). Verified live: the rail flipped to `ACTIVE LANE · model-Q8_0.gguf ·
  resident · live` on a cold post-reboot re-serve with **no config edit**, and
  honestly reverted to `configured · idle` after teardown.

### Fixed
- **BUG-2 / G1 circular wait** — `arena down`/SIGTERM could never abort an in-flight
  cloud eval: uvicorn's graceful drain waits for the eval BackgroundTask *before*
  lifespan shutdown, but the eval only aborts when lifespan writes the sentinel.
  The G1 sentinels now trip from a **chained signal handler** at SIGTERM/SIGINT time
  (`server._install_signal_teardown`), and a **startup reconciler**
  (`server._reconcile_orphaned_jobs`) lands `running`/`dispatched` rows orphaned by a
  dead process as `failed` with an honest error + teardown-shaped guardrail trail —
  a live-pid **owner stamp** (`jobs.job_owner_path`, written at the `running` flip)
  keeps a sibling cron-drain's genuinely-running jobs untouched. Covered by a
  real-process SIGTERM test that holds the drain open exactly like a guarded eval.
- **BUG-3 / G3 silently inert** — the M9 price snapshot had no refresh path, so
  `price_for()` returned `None` for every current lane and the cost cap could never
  trip. `CostLedger.price_for` now resolves the **freshest** capture by default
  (pinned snapshot reads stay reproducible); `fieldkit.cost.fetch_openrouter_prices`
  + `refresh_prices` capture live catalog prices under a dated snapshot id; the eval
  dispatch does a **price-at-dispatch capture** for unpriced cloud models
  (`FK_EVAL_PRICE_AT_DISPATCH=0` opts out); `GET /api/prices` +
  `POST /api/prices/refresh` give the Settings pane a per-model **"G3 armed?"
  disclosure** + refresh action; and an unpriced run renders a loud
  `⚠ G3 unarmed · tokens-only` badge on its Jobs card (AF-29) instead of silence.
- **BUG-4 / RL dependency drift** — the `[rl]` extra is **ceiling-pinned to the proven
  GB10 stack** (`transformers>=4.51.3,<4.52` + `protobuf` + `sentencepiece` +
  `peft<0.20`): transformers 5.x meta-crashes `device_map="auto"` on GB10, 4.5x
  misses undeclared tokenizer deps, and no 4.x accepts NeMo's list-form
  `extra_special_tokens` (the shadow-model-dir recipe is documented in
  `docs/api/rl.md` "Operator run").
- **BUG-1 / SFT misreporting (AE-25)** — `fieldkit.training.run` now stamps a
  **canonical `sft-progress-*.json` heartbeat** (`sft_progress_dir(recipe)`) from its
  checkpoint-liveness poll — `starting` → per-poll `running`/`done` → `failed` with
  the error on a non-zero exit → `final` with wall seconds. `/api/sft-progress`
  reads it as a first-class source (auto-follow spans heartbeats AND driver logs),
  so a run launched through the canonical entrypoint renders truthfully instead of
  `0/0 · starting` (the pane marks it `canonical feed`).
- **AF-27 / "Dead heat while wrong"** — rubric verdicts are labelled by **what they
  actually checked**: every default rubric carries `scope: "format"`
  (`RubricSpec.scope`, threaded as `rubric_scope` on the compare `score` event), the
  banner reads "Format check … says nothing about which value is right", the
  head-to-head row says "Format" not "Quality", and live-leaderboard format-rubric
  scores carry a `·fmt` qualifier. A free-typed prompt that **is** a registered
  bench row now **auto-matches** (`benches.find_prompt_by_text`) and is scored by
  the bench's own verifier — including astro rows, which now load their registered
  `scorer_path` verifier (`benches._registry_scorer_callable`, the AF-15 loader)
  instead of honest-skipping.
- **AF-28 / leaderboard blind to eval runs** — the leaderboard page projects
  **bench-anchored LIVE rows** from done `eval_rerun` jobs (`<EvalBenchLive>` over
  the existing `GET /api/eval/leaderboard`), and the cached mirror tier carries an
  explicit `cached tier · <generated date>` staleness stamp.
- **AF-30 / budget governor blind to eval spend** — `CostLedger.session_spend` (and
  the Standup `SpendDigest`, per-lane) folds in metered eval-job spend persisted at
  `jobs.result_json.guardrail.run_cost_usd`, so the autonomy $ cap governs the real
  number (the smoke showed $0.0023 while ~$0.18 of eval spend sat invisible).

### Changed
- `create_app(db=None)` resolves the `ARENA_DB` env before the packaged default
  (the convention `serve()`/`_reload_target` already used) — and the test suite now
  pins `ARENA_DB`/`FK_EVAL_SENTINEL_DIR`/`ARENA_BENCH_DIR`/`FK_ARENA_OWNER_DIR` to
  per-test tmp dirs, so no TestClient lifespan can ever touch the operator's live
  store or sentinels.

### Verified on Spark
- Every fix browser-smoked live in the running cockpit over CDP (the pinned v1
  discipline): the BUG-2 reconciler landed a seeded orphan on a real cockpit
  restart; `POST /api/prices/refresh` captured **real** OpenRouter prices for the
  live eval roster (and corrected a stale operator-manual deepseek-r1 row); the
  `⚠ G3 unarmed · tokens-only` badge rendered retroactively on the smoke's real
  unpriced R1 teardown eval; the canonical SFT heartbeat won auto-follow over the
  Jun-4 driver logs and rendered `DONE · iter 10/10 · canonical feed`; the
  leaderboard's live bench-anchored group ranked the smoke's real eval evidence
  (kepler-q8 0.85/54 · deepseek-r1 0.85/40 · claude-haiku 0.89/19); Standup SPEND
  read `$0.0538` with the cost-cap-aborted eval leading the by-lane table.
  Cluster G verified across a cold reboot (discovery found the re-served lane with
  no config). **No `arena.db` schema change** (`user_version` stays 6).

### Test suite
- Offline: **1413 passed / 19 skipped** (+44 over v0.27.0), including a
  real-process SIGTERM test (`tests/arena/test_signal_teardown_process.py`) that
  reproduces the BUG-2 drain-hold topology end-to-end, +13 `test_lanes.py`
  (Cluster G), and the AF-27 auto-match compare integration tests.

## [0.27.0] — 2026-06-06

The operator-config surface over the AE-17 cloud-run eval guardrails
(`_SPECS/arena-guardrail-settings-v1.md`). AE-17 (v0.26.0) made the eval guardrails
bounded + env-configurable; v0.27.0 makes them **visible** and **live-editable** from the
cockpit — view the effective stall window + per-run cost cap with per-field provenance,
edit them, and flip a master toggle, and the next cloud eval picks up the change with **no
restart**. **No arena.db schema change** (`user_version` stays 6) — the config is a JSON
file (the AF-9/AF-10 convention), never a table, never mirrored; **no skill imports**
(AE-R3); deterministic CRUD only (no LLM). A local lane is byte-for-byte unchanged.

### Added

- **Arena guardrail settings** (`_SPECS/arena-guardrail-settings-v1.md`; GS-1…6). The
  operator-config surface over the AE-17 cloud-run eval guardrails: view + live-edit the
  thresholds with **no restart**. AE-17 made the guardrails bounded + env-configurable;
  this makes them visible and editable from the cockpit. **No arena.db schema change**
  (`user_version` stays 6) — the config is a JSON file (`~/.fieldkit/arena/guardrail-config.json`,
  the AF-9/AF-10 file convention), never a table, never mirrored; **no skill imports**
  (AE-R3); deterministic CRUD only (no LLM).
  - **GS-1 — config core.** `fieldkit.arena.guardrail` gains the public
    `GuardrailConfig` value (`stall_timeout_s` / `cost_cap_usd` / `enabled`), `load_config()`
    (resolves **file > env > default** with per-field source provenance →
    `(GuardrailConfig, sources)`), validated atomic `save_config()` (`tmp + os.replace`),
    `guardrail_config_path()`, and `DEFAULTS` / `BOUNDS`. `EvalGuardrail.from_env` is now a
    thin wrapper over `load_config()` (back-compat — with no file present it reads the same
    env vars as before). The arm site `_run_eval_guarded` reads `load_config()` **per
    dispatch**, so an edit lands on the next cloud eval with no restart, and honors the new
    `enabled` master toggle (off ⇒ a cloud lane runs unguarded, byte-for-byte the local-lane
    path). A corrupt/partial config file falls back to env/default — it never crashes a
    dispatch. Config dir overridable via `FK_EVAL_CONFIG_DIR` / `FK_EVAL_CONFIG_PATH`; the
    toggle env is `FK_EVAL_GUARDRAIL_ENABLED`.
  - **GS-2 — config API.** `GET /api/guardrail-config` (pure projection →
    `{effective, sources, defaults, bounds}`) + `POST /api/guardrail-config` (Pydantic body
    → validate against `BOUNDS` → **422** on violation → atomic write → return the refreshed
    `{effective, sources}`). Operator-private (the config file is never mirrored); mirrors the
    `POST /api/lab/notes` deterministic-CRUD precedent.
  - **GS-3 — Settings pane + GS-6 badge cap.** A new `/arena/settings/` pane +
    `<GuardrailSettings>` island (per-field label · editable value · source chip · default,
    Save → toast → re-fetch, Reset-to-defaults, the `enabled` master toggle, and a loud
    persistent **"Cloud-eval guardrails OFF"** banner when disabled) + a **Settings** tab in
    the REVIEW/META nav group (no other route change). The Jobs-card `<EvalGuardrailBadge>`
    now appends `· cap $X / Nm` read from the already-persisted
    `result_json.guardrail.{cost_cap_usd, stall_timeout_s}`, so the config that governed a run
    is visible at the run (zero new persistence).

### Test suite

- **Offline: 1369 passed, 5 skipped** (`/tmp/fk/bin/pytest tests/`) — +16 over v0.26.0:
  the GS-1 config resolver / `save_config` round-trip / bounds / provenance / corrupt-file
  fallback tests (`tests/arena/test_guardrail.py`), the `enabled`-disabled cloud-dispatch
  path (`tests/arena/test_jobs.py`), and the `GET`/`POST /api/guardrail-config` endpoints
  (`tests/arena/test_server.py`). No `--spark` paths touched — the guardrail config is
  stdlib-cheap (no NIM / pgvector / live cloud).

## [0.26.0] — 2026-06-06

The arena-enhancements dogfood cluster's final session, S7 — bounded, configurable,
**tracked** guardrails on metered cloud eval lanes, after a baseline OpenRouter eval
hung ~2.5 h holding the lane and accruing uncapped spend (2026-06-05). This closes the
arena-enhancements cluster (S1–S7 feature-complete). **No arena.db schema change**
(`user_version` stays 6) — a sentinel file + `result_json` fields + env config; **no
skill imports** (AE-R3); a local lane runs byte-for-byte unchanged.

### Added

- **Arena-enhancements S7 — cloud-run guardrails** (`_SPECS/arena-enhancements-v1.md`
  §6 S7; AE-17). Bounded, configurable, **tracked** guardrails on *metered cloud* eval
  lanes — the fix for the baseline OpenRouter eval that hung ~2.5 h holding the lane and
  accruing uncapped spend (2026-06-05). A new `fieldkit.arena.guardrail.EvalGuardrail`
  wraps any metered cloud eval (a non-loopback `base_url`) with three trip conditions,
  all writing a shared **eval-abort sentinel** the `VerticalBench.run` row-loop polls
  between rows (the eval-side sibling of the RL `abort_poller`/sentinel pattern):
  - **G1 — teardown.** The cockpit `_lifespan` shutdown (and `arena down`) trip the
    sentinel for every running `eval_rerun` job (`_trip_running_eval_sentinels`, a
    deterministic-path-from-`job_id` reach), so an in-flight cloud eval aborts cleanly
    instead of only dying with the process.
  - **G2 — stall.** A **no-progress** watchdog trips when no row completes within
    `FK_EVAL_STALL_TIMEOUT_S` (default 600 s), reset on every completed row (never a
    wall-clock total — the AE-R6 false-trip guard), backstopped by the existing 120 s
    per-request httpx timeout.
  - **G3 — cost.** `OpenAICompatClient.chat` gains an `on_usage` hook → the guardrail
    accumulates per-row `usage` tokens → `fieldkit.cost.PriceSnapshot.cost_usd` → trips
    when the **per-run** total exceeds `FK_EVAL_RUN_COST_CAP_USD` (default $5), the
    per-run sibling of the governor's per-day cap. Inert (tokens-only) when no price
    snapshot resolves for the model.
  - **Tracked** — every run threads `result_json.guardrail` (`aborted_by ∈
    teardown|stall_timeout|cost_cap`, `run_cost_usd`, `partial`, `n_scored`, token
    counts) through `_persist_eval_rerun`; the Jobs board renders a per-run cost chip +
    an abort badge naming the trip condition (composes with AE-16 card identity + AE-2
    abort visibility + the AE-13 cost chip). **No arena.db schema change**
    (`user_version` stays 6) — a sentinel file + `result_json` fields + env config;
    **no skill imports** (AE-R3). A **local** lane (loopback / docker-bridge / RFC-1918)
    runs byte-for-byte unchanged — the dispatcher never arms a guardrail for it.

### Test-suite

- **+38 offline tests** (1315 → 1353 pass / 5 skip): `tests/arena/test_guardrail.py`
  (G1/G2/G3 trips + reset semantics, cloud detection, env config, the
  `VerticalBench.run` abort/progress hooks, and `run_vertical_eval` end-to-end with a
  fake OpenAI-compat client) + 3 dispatch/persist tests in `test_jobs.py` + 2
  `_lifespan` teardown tests in `test_server.py`.

## [0.25.0] — 2026-06-06

The arena-enhancements dogfood cluster tail, sessions S5–S6 — provenance + lineage
threaded into the build spine and the rl_run card, then the base-model scout
decision and the vertical's own bench surfaced through the existing Compare + Eval
surfaces. **No arena.db schema change** across either session (`user_version` stays
6); every signal is a pure read-only projection over files/rows the cockpit already
reads, and no skill code is imported into the cockpit (AE-R3).

### Added

- **Arena-enhancements S5 — provenance / lineage** (`_SPECS/arena-enhancements-v1.md`
  §6 S5; AE-8/AE-9). Threads pedigree into the build spine and the rl_run card so a
  regression traces to its substrate, not just a count or a step. **No arena.db schema
  change** (`user_version` stays 6), **no new skill imports** (AE-R3); both are pure
  projections over files/rows the cockpit already reads.
  - **AE-8 — bench provenance card.** New `_bench_provenance()` projection (and
    `GET /api/bench-provenance`) reads the on-disk pool + held-out JSONL (and the
    SFT-init queue) and derives the bench's pedigree: version · pool/held-out counts ·
    **RV-10 disjointness** (`pool ∩ held-out`, a real set check — not a label) ·
    tier/topic mix · the count of golds carrying a precomputed SI value (the on-disk
    evidence of the generator's self-verify invariant) · the **corpus held-out-exclusion
    proof** (`SFT-queue ∩ held-out`). It rides the `/api/build` bench stage as
    `provenance` (and lights the stage live off the JSONL even when the bench isn't
    registered yet, pending AE-11); `<BuildSpine>` renders it as a card. Anchored by
    `FK_ARENA_BENCH_DIR` (default the build/evidence dir). Folds into AE-11's Eval preview.
  - **AE-9 — rl_run upstream lineage.** `_persist_rl_run` threads the inter-run upstream
    lineage (corpus C1 · SFT-init C2 · bench version) into `result_json.upstream` — from
    the loop summary first, else the enqueue payload (`scripts/astro_bench/enqueue_rl.py`
    stamps `corpus_slug` / `sft_init`); `None` on a bare run. The Jobs board renders an
    `↑ corpus · sft-init · bench` line under the held-out summary, so a regression traces
    to its corpus, not just its step (complementing AE-4's `rl-<step>` pointer).
- **Arena-enhancements S6 — wiring quick-wins** (`_SPECS/arena-enhancements-v1.md`
  §6 S6; AE-10/AE-11). Surfaces the two flows that the live cockpit was blind to —
  the base-model scout decision and the vertical's own bench — through the existing
  Compare + Eval surfaces. **No arena.db schema change** (`user_version` stays 6),
  **no new skill imports** (AE-R3); both are pure read-only projections.
  - **AE-10 — scout top-3 → Compare (+ lock-time behavioral gate).** New
    `GET /api/scout` projects the newest `hf-model-scout` report
    (`FK_ARENA_SCOUT_DIR`, default `/tmp/hf-scout/<date>/<vertical>/`) — the ranked
    top picks from `report.md` joined with the structured traps from
    `candidates.json` (license · commercial-OK · chat-format · arch · llama.cpp
    compat · Spark envelope) + the ruled-out table. The Compare pane renders a
    `<ScoutPanel>` (collapsed) so the scout decision is finally visible in the
    cockpit AND frames the lock-time behavioral gate (eyeball boxing + verbosity on
    a held-out prompt before committing a bench — the over-think we caught one stage
    too late). Serving a candidate stays an operator step (one-lane envelope, AE-R4);
    the panel's gate button opens the Eval drawer at the held-out astro split.
  - **AE-11 — astro-bench preview (register `astro-bench` in the Eval surface).**
    The astrodynamics RLVR bench is now registered in `fieldkit.arena.benches`,
    previewable beside the published verticals via the existing
    `GET /api/eval/benches` + `…/prompts`. A `root_env`/`root_fallback` override on
    `BenchSpec` lets it read its splits from the vertical's evidence dir (the same
    JSONL AE-8's provenance reads) rather than the eval-benches tree; a dedicated
    `fmt="astrodynamics"` loader maps its `{prompt, answer, tier, subtopic}` rows
    (split → `family` so the drawer filters pool/held-out; `tier`/`subtopic`/`split`
    ride new payload facets the drawer renders as chips + an inline gold preview).
    Interactive grading honestly skips (the unit-aware `astro_numeric_match` verifier
    stays LOCAL per `feedback_keep_scorer_local_until_reuse` and scores through the
    eval-job dispatch's `scorer_path`, not the built-in scorers). Registering it also
    resolves the build-spine bench stage's "pending AE-11" note. `serve()` now exports
    `ARENA_REPO_ROOT` in the direct (non-reload) path so the bench root resolves.

### Test suite

- Offline **1315 passed, 5 skipped** (`cd fieldkit && pytest`) — +18 over v0.24.0's
  1297 (S5 +6, S6 +12). S5–S6 are arena / benches / build-spine / server work with
  no live NIM / pgvector / eval paths, so no `--spark` run this release (mirrors the
  v0.24.0 cut of the same cluster).

### Articles in this release

- None — S5–S6 are cockpit-internal dogfood sessions (no `articles/` changes since
  `fieldkit/v0.24.0`); the build-spine + Compare + Eval surfaces they extend already
  shipped with `products/arena-control-plane/`.

## [0.24.0] — 2026-06-05

The arena-enhancements dogfood cluster, sessions S1–S4 — the gaps the first live
`rl_run` exposed, then the cockpit's information architecture, the vertical-build
spine, and the corpus live feed + build-gate ledger. **No arena.db schema change**
across the whole cluster (`user_version` stays 6); every signal lands in
`result_json` / file-polled reports / panes / nav.

### Added

- **Arena-enhancements S1 — RL-run observability** (`_SPECS/arena-enhancements-v1.md`
  §6 S1; AE-1/2/3/4/16). Closes the gaps the first live `rl_run` exposed; all within
  `result_json` / file-polled reports, **no arena.db schema change** (`user_version`
  stays 6) and **no new route**.
  - **AE-2 — degenerate/no-op step visibility.** `RLLoop._emit` now carries
    `keep_rate` / `n_used` / `adv_spread` / `trained`; a uniform-reward step (all-zero
    advantage → no gradient, no adapter, no lane restart) reads **visibly distinct**
    from a stall on the Jobs board (`<RlProgress>` renders the GRPO row + a
    "no update — zero advantage" badge).
  - **AE-3 — per-step `step_history[]`.** `RLLoop.summary()` emits a bounded per-step
    trajectory (`{step, phase, pool_score, last_heldout, keep_rate, loss, kl, n_used,
    adv_spread, step_duration, trained}`), threaded through `_persist_rl_run` into the
    existing `result_json` column — reconstructs "which steps moved the policy" after a run.
  - **AE-4 — lineage step-index.** `summary()` adds `selected_exp_id` (`rl-<step>`),
    the back-pointer from the held-out-selected step to its `fieldkit.lineage` trial, so
    a regression traces to the exact published checkpoint. Rendered on the done card.
  - **AE-1 — reward gauge wired to the live `rl_run`** (AF-11). New
    `fieldkit.arena.lane.reward_signal_writer` (+ `_reward_signal_dir`) drops an
    `av10-preflight`-shaped report (held-out → `reward_rate_step0`, the gauge's key)
    into the dir `/api/reward-signal` auto-follows, at every held-out gate + a final
    `status:done` on teardown — so the dedicated gauge lights up during the run it
    exists for, **zero pane change**. Composed onto the loop's `progress_cb` in
    `_run_rl_arbitered`; dir is env-anchored (`FK_ARENA_REWARD_DIR` →
    `ARENA_REPO_ROOT/evidence/astrodynamics`). Best-effort — never fails the run.
  - **AE-16 — Jobs-card identity.** Each board card now carries a relative enqueue
    time + a short id + (for `rl_run`) a run label, so distinct jobs (the C5 smoke vs
    the full run; two byte-identical `rag_eval`s) no longer read as repeats. Pure render.
  - Backward-compatible (a bare M8/RV-6 run leaves the new fields `None`/absent).
    Validated offline (6 new tests in `test_rl.py` + `tests/arena/test_lane.py`) and by
    a live side-by-side browser smoke of the rebaked cockpit; the AE-R1 live-`rl_run`
    GPU gate (the reward-gauge lighting end-to-end) remains operator-armed.

- **Arena-enhancements S2 — information architecture & flow** (`_SPECS/arena-enhancements-v1.md`
  §6 S2; AE-12/13/14/15). The IA refresh that lands *before* the new S3+ panes so they
  slot into a reorganized nav. **No arena.db schema change** (`user_version` stays 6),
  **no route change** (AE-R5 — grouping/labels only). Mostly cockpit-only (rebaked
  `_webui`); one `fieldkit.arena.server` addition (AE-15) carries below.
  - **AE-15 — telemetry lane-truth.** The rail's "active lane" echoed the static
    `~/.hermes/config.yaml` (pinned Qwen3-30B) whether or not anything was serving —
    so an idle box, or a box whose resident brain an `rl_run` had torn down, still read
    "Qwen3-30B · warm". `TelemetryHub._build_payload` now emits `resident_live` (a
    cached ~8 s TCP liveness probe of the configured `base_url`) + `active_lane_model` /
    `active_lane_where` (an injected, store-decoupled reader that names a running
    `rl_run`'s lane — `_read_active_gpu_lane`). The rail reconciles them: in-flight
    stream → running RL/external lane → liveness-probed resident → last warm run → and,
    last, the configured-but-idle lane relabelled **"Configured Lane · idle"** (amber)
    instead of falsely claiming "active". 5 new tests (`tests/arena/test_server.py`);
    the live-`rl_run` positive RL-lane label is validated on the next armed run (AE-R1).
  - **AE-12 — flow-based nav IA** (cockpit). The flat 11-tab row (which overflowed +
    read as a list) is regrouped into the three lifecycle stages — **Build/Train**
    {Models · SFT · Reward · Jobs · Standup} → **Serve/Infer** {Chat · Compare ·
    Leaderboard} → **Review/Meta** {Cockpit · Lab · Cortex} — on a **two-tier bar**
    (brand + status on top, full-width nav below) so every tab is reachable. Route
    `href`s unchanged; trivially reversible.
  - **AE-13 — data-flow routing corrections** (cockpit). A **training-flow card** on
    the cockpit landing stitches SFT → Reward → RL into one legible left→right chain
    (new `TrainingFlow` island, reuses `/api/sft-progress` + `/api/reward-signal` +
    `/api/jobs`, degrades to per-stage "idle"); the **Jobs↔Standup boundary** is made
    explicit + navigable (cross-link notes: operator-dispatch vs overnight-cron review);
    a **`$0 · local` cost chip** on Compare side cards so free Spark lanes read as free,
    not blank. *(AE-13a leaderboard-row→producing-job link deferred — the aggregate rows
    strip per-run provenance + there's no job-detail route; folds into S5 provenance.)*
  - **AE-14 — pane-purpose redefinition** (cockpit, leverage not rebuild). **Reward**
    reframed as the cross-stage scorable-output gauge spanning SFT-init step-0 + the live
    `rl_run` (folds AE-1); **Standup** foregrounded as the overnight RL-run digest +
    promote gate; the cockpit-body card relabelled "Active lane"→**"Resident lane ·
    configured"** for consistency with AE-15. *(AE-14c Lab→build threading deferred to S3,
    when the `/arena/build/` pane exists.)*
- **Arena-enhancements S3 — build-spine backbone** (`_SPECS/arena-enhancements-v1.md`
  §6 S3; AE-5 / AF-1). The vertical-build pipeline as a pane — *the spine that frames
  the rest of the dogfood enhancements*. **No arena.db schema change** (no write, no new
  table) and **no skill imports** (AE-R3): the spine is a pure projection over feeds the
  cockpit already has.
  - **AE-5 — `/arena/build/` Vertical-Build pane.** A new `GET /api/build` endpoint
    assembles eight C1..C6 stage cards (scout · bench · corpus · SFT · smoke · lane ·
    RLVR · publish), each with a **state**, a **headline metric**, and the **operator
    gate**, from the signals the cockpit already reads — the SFT log feed
    (`_newest_sft_log`/`_parse_sft_log`), the reward report (`_newest_reward_report`),
    the bench registry (`benches.list_benches`), the newest `rl_run` row's `result_json`,
    and the lane arbiter (`_read_active_gpu_lane` / resident config, AE-15-honest) —
    plus an optional operator-authored **`build-manifest.json`** (env-anchored
    `FK_ARENA_BUILD_DIR`, default the astrodynamics evidence dir) for the stages with no
    live feed (scout / corpus / publish) + the human-gate annotations. Ownership split:
    a live-feed stage's `state`/`headline`/`detail` win (the manifest only fills them
    when blank); `gate`/`href` + the no-feed stages are manifest-owned. Read-only by
    construction — an HTTP GET reads files + lists rows, it never launches a lane. A
    fresh box degrades every stage to `pending` rather than erroring. New cockpit pane
    `/arena/build/` (in the Build/Train nav group) + `<BuildSpine>` island (5 s poll,
    deep-links the live stages to their panes); the Kepler build ships a tracked
    `evidence/astrodynamics/build-manifest.json` so the spine reads the real end-to-end
    pipeline (7/8 done; lane honestly idle). 6 new tests (`tests/arena/test_build_spine.py`).

- **Arena-enhancements S4 — live feeds + gates** (`_SPECS/arena-enhancements-v1.md`
  §6 S4; AE-6 / AF-2 + AE-7 / AF-5). Threads two features INTO the S3 build spine.
  **No arena.db schema change** (`user_version` stays 6), **no new route**, **no skill
  imports** (AE-R3) — both are file-polled projections + render.
  - **AE-6 — corpus-synth live feed.** Closes the C1 corpus blind spot (the
    in-CC-session synth the control plane never saw — the "#1 immediate win" in the
    dogfood ledger). A new producer-side stamper
    `fieldkit.arena.lane.write_corpus_progress` (the AF-9/AF-10 file-polled-heartbeat
    pattern, one dir over) reads the live `out.jsonl` against the deterministic
    `queue.jsonl` and drops a `corpus-progress-<slug>.json` heartbeat — `written/target`,
    the batch-verify tally, the accumulating tier/topic `family_mix`, and the
    ETA-in-batches. The cockpit polls it via a new `GET /api/corpus-progress` (auto-newest
    + history dropdown + traversal-safe `?source=` pin, mirroring `/api/sft-progress`,
    env-anchored `FK_ARENA_CORPUS_DIR`). The build spine's **corpus stage now reads the
    feed live** (`written/target · verify ✓` on a running synth, overriding the manifest);
    the `<BuildSpine>` island renders a **corpus strip** (progress bar · verify chip ·
    tier-mix chips · ETA-in-batches) mirroring the rl_run / SFT progress strip when a
    heartbeat is present. Read-only: an HTTP GET reads a JSON file, it never launches a
    lane or imports skill code.
  - **AE-7 — build-gate cards.** Every gated stage now ships a default `gate_consequence`
    (the cost of holding: base-lock · `/usage` preflight · held-out>base · AV-10 · promote ·
    publish), operator-overridable via the manifest. The island renders a **gate ledger** —
    one row per human gate with an **allow/hold/pending control** + the consequence — reusing
    the Standup autonomy-banner pattern (advisory + read-only; the spine never mutates
    arena.db).
  - Validated offline (9 new tests: `tests/arena/test_corpus_feed.py` +
    `tests/arena/test_build_spine.py`) and by a live side-by-side browser smoke of the
    rebaked cockpit over CDP (a seeded synthetic heartbeat lit the corpus strip —
    `388/600 rows · verify ✓ · ~5 batches left` + the six-family mix + the six-gate ledger
    — then deleted, reverting the spine to the real Kepler 7/8). The AE-6 feed lights
    end-to-end on the next live corpus-synth run.

### Test suite

- **1297 passed, 5 skipped** (offline `pytest`; the 5 skips are the `--spark`
  live-NIM / pgvector + torch-dependent suites). +21 tests over v0.23.0 across the
  four sessions: `test_rl.py` + `tests/arena/test_lane.py` (S1), `test_server.py`
  (S2 AE-15), `tests/arena/test_build_spine.py` (S3 + S4 gates), and the new
  `tests/arena/test_corpus_feed.py` (S4 AE-6 writer + endpoint + live corpus stage).

### Verified on Spark

- Every session closed with the pinned dogfood discipline — `_webui` rebaked +
  the cockpit restarted in browser-use mode + a **live side-by-side browser smoke
  over CDP** of the rebaked panes (S1 the RL strip identity + degenerate badge, S2
  the two-tier nav + honest idle-lane rail, S3 the eight-stage build spine, S4 the
  corpus strip + gate ledger). The live `rl_run` reward-gauge end-to-end (AE-R1)
  and the AE-6 corpus feed end-to-end stay operator-armed for the next live run.

## [0.23.0] — 2026-06-05

The **Arena cockpit grows an education layer** (`rl-lane-autonomy-v1` LA-12..16 —
the deferred fast-follow to the v0.22.0 self-driving backend). Mostly
site/cockpit-only — the wheel carries it via the rebaked `_webui` bundle. The
`fieldkit` Python surface gains two small, backward-compatible additions this
cycle: a read-only **reward-signal endpoint** (dogfood AF-3) and a generic
**`scorer_path` custom-scorer hook** on `run_rl_loop` (both below). **No schema
or module change.** One canonical operator curriculum (a new `explainers` content
collection, single-sourced and drift-guarded against the deep-dive's `:::` blocks)
surfaces contextually in the live cockpit.

### Added

- **Custom-scorer hook for `eval_run`/Compare (dogfood AF-15)** — the same
  `scorer_path` hook now threads through the **eval/compare** path, not just
  `rl_run`: `run_vertical_eval` gains `scorer_path=` (loads a vertical's own
  verifier via `_load_scorer_callable`, handed straight to
  `VerticalBench.from_jsonl(scorer=…)`) and `api_key_env=` (names the env var
  holding a bearer key so an OpenRouter baseline lane authenticates through the
  same path as a local llama-server lane — the key is never put in the persisted
  job payload). `arena.jobs.resolve_bench` surfaces a `scorer_path` from the
  bench's `.meta.json` sidecar, and the `EVAL_RERUN` dispatch forwards
  `base_url`/`model`/`scorer_path`/`api_key_env` per lane. Lets a custom-verifier
  vertical (e.g. astrodynamics' boxed + SI-unit scorer) run a **fair head-to-head
  through the cockpit** — the built-in first-number `numeric_match` scored a
  correct `\boxed{}` answer 0.0. Backward-compatible (all default `None` → the
  built-in-scorer path is unchanged). Schema unchanged.

- **Custom-scorer hook for `rl_run`** — `run_rl_loop` (and the dispatcher's
  `default_runner`) accept an optional `scorer_path` (`"module-or-file:function"`)
  that loads a vertical's own verifier instead of one of the six built-in
  `fieldkit.eval` scorers — so a domain reward kept local (per
  `feedback_keep_scorer_local_until_reuse`) drives the Arena RLVR loop without
  being promoted into `fieldkit.eval`. A `*.py` file ref puts the module's parent
  on `sys.path` so its sibling imports resolve. Backward-compatible (defaults to
  `None` → the named-scorer path is byte-for-byte unchanged). Unblocked the first
  greenfield-vertical (astrodynamics) `rl_run`, whose boxed + SI-unit verifier the
  built-in first-number `numeric_match` scores 0.0. Schema unchanged.

- **Cockpit education layer (LA-12..16)** — per-phase "what / why / watch" guide
  cards + a live pool-vs-held-out interpreter (the t2po inversion read in real
  time) on the Jobs board's `rl_run` progress strip; guided decision-gate copy
  (consequence + reversal) on the Standup autonomy banner and the RLVR-enqueue
  form; and a compounding post-run debrief with an editorial-promotable flag. The
  curriculum is a new `explainers` content collection shared byte-for-byte by the
  cockpit and the site, with `scripts/verify_explainers.mjs` asserting every
  teach_key + deep-dive backlink resolves. (Ships in the baked `_webui`.)
- **Reward-signal gauge** (`GET /api/reward-signal`) — a read-only endpoint that
  renders the eval-is-reward signal (boxed-rate / reward-rate / AV-R1 truncation +
  per-row buckets) from a report JSON under `repo_root` (override
  `FK_ARENA_REWARD_SIGNAL`); returns `{available: false}` on a fresh box, reads no
  arena.db, bumps no schema. Surfaces in the new `/arena/reward/` cockpit pane; the
  report shape is reused by the RLVR per-step gauge. (Dogfood AF-3; ships in the
  baked `_webui` + `server.py`.)
- **Live reward gauge + run history** (dogfood AF-9) — the `/arena/reward/` pane now
  **streams a multi-row eval/preflight while it runs** (not only after exit) and
  **browses prior runs**. A `status:running` report (with `scored`/`total`, written
  incrementally by the producer) renders a RUNNING strip — progress bar + live
  partial rates + a neutral "GATE · pending" — on the pane's existing 5 s poll.
  `GET /api/reward-signal` gains a `runs` history list (newest-first summaries of
  every `av10-preflight*.json`) and an optional `?source=<file>` selector
  (traversal-sanitized); with no selection it **auto-follows the newest report by
  mtime**, so the gauge tracks a live run and any later run with no manual
  repointing. The pane gains a "run" dropdown (default *Latest (auto-follow)*) and
  shows which `source` is on screen. No arena.db read, no schema bump (AH-9/RV-8);
  a report without a `status` field still renders the gate verdict exactly as
  before. (Ships in the baked `_webui` + `server.py`.)
- **Live SFT-training feed** (dogfood AF — closes the AF-2 blind spot for the SFT
  stage) — a new `/arena/sft/` cockpit pane + `GET /api/sft-progress` read-only
  endpoint that parses a NeMo `p65` LoRA-SFT driver log + run-dir into iter/max, the
  loss curve (sparkline), iter/s, ETA, peak GPU memory, and checkpoints written —
  the training-stage analogue of the `rl_run` progress strip, so the operator can
  watch a `TrainRecipe(backend="nemo")` SFT-init run side-by-side instead of tailing
  a log. The run-root is env-anchored (`FK_ARENA_SFT_DIR`, default the astrodynamics
  run-root) since the trainer writes outside the repo; history + auto-follow mirror
  the reward gauge (newest training log by mtime, `?source=` selector,
  merge/export logs excluded). Read-only (an HTTP GET parses a log; never launches a
  lane), no arena.db read, no schema bump. (Ships in the baked `_webui` + `server.py`.)

### Fixed

- **`test_drain_arbiters_rl_run_with_progress_and_mem_trace` isolated from the host
  autonomy state** — `build_standup` reads `~/.fieldkit/arena/autonomy.json`, so on a
  box with autonomy armed (`enabled: true`) the test's unarmed-policy assertion failed.
  The test now points `$ARENA_AUTONOMY_STATE` at a tmp path so it reads a clean state.
  Test-only; no source change.

### Test suite

- Offline `pytest tests/` → **1271 passed, 5 skipped** (the 5 skips need `--spark` /
  `torch`). The cycle's changes (the `scorer_path` eval/compare hook, the reward-signal
  and SFT-progress endpoints, the education layer) are GPU-free connective tissue tested
  with local scorers + fakes, so this release verified offline (v0.21.0/v0.22.0
  precedent — warming NIMs adds no coverage and risks the unified-memory OOM landmine).

### Articles in this release

- [`the-gate-before-the-gpu`](https://ainative.business/field-notes/the-gate-before-the-gpu/)
  — the SFT-vs-RL-vs-RLVR method-selection deep-dive (`fieldkit_modules: [rl, reward, eval]`),
  built on the Kepler greenfield astrodynamics vertical whose cockpit `rl_run` the AF-15
  `scorer_path` hook unblocked.

## [0.22.0] — 2026-06-03

The **RLVR engine becomes self-driving** (`rl-lane-autonomy-v1`, LA-1..11 — the
self-driving + safety backend; the education layer LA-12..16 is a tracked
fast-follow). The shipped Phase-3 engine drained as an operator-armed `rl_run`;
this build closes the two chokepoints (a control-plane-managed vLLM lane + one-step
cron arming) and adds the two things a multi-hour unattended GPU job must have:
**live step reporting** + a **telemetry-correlated OOM defense**. Mostly connective
tissue over shipped primitives (`budget.MemoryEnvelope`, `_rl_gpu_serve.VLLMLane`,
`arena.scheduler`, `server.TelemetryHub`, `jobs.result_json`). **No schema change**
(arena.db stays `user_version 6`, LA-7); **no new top-level module** (the one new
submodule `fieldkit.arena.lane` documents under `arena`, so `audit-landing` stays
4/4); **no new `ARTIFACT_KINDS`**. The external blocker is unchanged (a pinned
aarch64+CUDA-13 vLLM the operator installs); absent it the arbiter `defer`s cleanly
(`LANE_BIN_ABSENT`), so the whole surface ships + is GPU-free-testable now.

### Added

- **New submodule `fieldkit.arena.lane`** — `LaneArbiter` (the envelope-gated
  single serving slot: a 3-way pre-flight *governor allow ∧ envelope fits ∧ vLLM
  binary present* → resident-brain teardown → watchdog → always-restore-on-exit,
  LA-1/2/6), `MemoryWatchdog` (the telemetry-correlated OOM defense — a persistent
  headroom-floor breach touches an abort sentinel the loop polls between steps,
  *before* the kernel OOM-kills; arena-wide, LA-10), `mem_trace`/`MemTrace` (the
  per-run memory report → lineage + standup, LA-11), `RLLaneContext` (the one
  optional object dispatch consults for an `rl_run`), plus `rl_progress_writer`
  (LA-8) / `abort_poller` / `lane_binary_present` / `LaneError` / `LaneDeferred`.
- **Live `rl_run` progress (LA-8)** — `fieldkit.rl` gains `rl_hooks(progress_cb,
  should_abort)` (a `contextvars` conduit, arena → rl only) + `current_rl_hooks`;
  `RLLoop` emits throttled `{step, phase, pool_score, last_heldout, eta_s}` and
  polls an abort between steps. The arbiter wires these to a single-writer
  `result_json` patch; `server._jobs_signature` gains a progress nonce so the
  `/api/jobs/stream` board re-emits while a run is `running`. The cockpit Jobs
  board renders an inline progress strip with the pool-vs-held-out read (the t2po
  inversion made visible as it happens, RV-4).
- **One-step autonomy (LA-5)** — `fieldkit arena autonomy on|off|status` writes a
  reversible policy record + prints/installs the crontab line; `fieldkit arena
  drain` is the cron target (one `run_drain_cycle` tick). The morning standup
  surfaces the armed state + the RL memory digest.
- **Async-enqueue `rl_run` (LA-4)** — `POST /api/jobs` accepts `rl_run` but forces
  `dispatch=False` (RV-6): the 8.5 h loop never runs in a request BackgroundTask;
  the response advertises `async_only` + the autonomy note. New cockpit affordance.
- **`EscalationReason.LANE_BIN_ABSENT`** (`fieldkit.budget`) — the defer reason for
  a GPU lane with no serving binary; `dispatch_job` / `drain_jobs` gain an optional
  `rl_lane` (the RL-lane brake releases + audits + stops the pass, the AH-4 pattern).

### Tests

- `tests/arena/test_lane.py` (+19) — spawn-gate, restore-on-failure, refuse-on-
  unmanaged, governor-veto-first, watchdog floor-breach-after-N + transient-no-fire
  + stale-never-trips + warn-non-destructive, mem-trace round-trip, progress
  throttle + gate, the full arbitered drain (progress + mem-trace + defer brake +
  bare fallback), `user_version` stays 6, autonomy round-trip; `test_jobs_api.py`
  updated for the async-only `rl_run` enqueue contract.

### Test suite

- Offline `pytest tests/` → **1253 passed, 5 skipped** (the 5 are `--spark` /
  `torch` integration tests). LA-1..11 is GPU-free-testable connective tissue —
  the lane arbiter, watchdog, progress conduit, and defer brake all run with
  fakes; no live NIM / pgvector / vLLM path is touched, so no `--spark` run.

### Articles in this release

- None — package-only release (the editorial launch of the engine shipped in the
  `v0.20.0` / `v0.21.0` window: `articles/the-machine-improves-itself` +
  `products/living-model`). LA-1..11's reader-facing layer is the deferred
  education fast-follow (LA-12..16).

## [0.21.0] — 2026-06-03

The **closed-loop RLVR engine grows its GPU hands.** `rlvr-loop-v1` shipped the
orchestration in `v0.20.0` with `gpu_seams` raising a "not vendored" stub; this
release vendors the real backend (the ported `clawgym-on-spark-grpo` loop) behind
a new `fieldkit[rl]` extra. No schema change (arena.db stays `user_version 6`);
the live run stays operator-armed (no aarch64+CUDA-13 vLLM wheel, ~8.5 h overnight
drain).

### Added

- **Vendored the real GPU backend for `fieldkit.rl.gpu_seams`** — the closing
  operator follow-on from `rlvr-loop-v1` §10.1. `gpu_seams` no longer raises a
  "not vendored" stub; it returns the three real seams when the new
  `fieldkit[rl]` extra is installed, and a friendly `RLLoopError` pointing at the
  extra when it isn't. The ported `clawgym-on-spark-grpo` loop splits in two so
  the GPU stack is touched only on a live call:
  - **`fieldkit._rl_gpu_serve`** (torch-free) — the HTTP rollout sampler over the
    local pinned-vLLM OpenAI endpoint (via `fieldkit.nim.NIMClient`; the GPU lives
    in a separate vLLM server process), the held-out gate, and the `VLLMLane`
    kill-and-restart serve lifecycle (`pkill -9 -f 'vllm|EngineCore'` — RV-R4 /
    `feedback_vllm_engine_core_orphan`). A `_GpuRollout` carries the prompt so the
    trainer can rebuild token sequences without the bench; duck-types straight
    into `RewardAdapter`.
  - **`fieldkit._rl_gpu_trainer`** (the `fieldkit[rl]` / torch gate) — the
    REINFORCE-with-KL step ported faithfully from `grpo_train.py` (per-token
    log-prob over assistant tokens, the K3 KL estimator against a frozen
    CPU-resident reference snapshot, advantage-weighted loss, AdamW + grad-clip,
    adapter save), generalized from clawgym's multi-turn agentic trajectories to
    the single-turn QA `Rollout` contract, and kept **resident across steps**
    (load the 7B base once, not per step — RV-10 one-lane envelope).
- **New `fieldkit[rl]` optional-dependency extra** — `torch`, `peft`,
  `transformers`, `safetensors`, `accelerate`. vLLM is deliberately **not** a
  dependency: there is no aarch64+CUDA-13 wheel for the pinned version yet
  (`project_verl_atgpo_vllm_gap`), so it is served as a separate operator
  process. `import fieldkit.rl` stays stdlib-cheap; only a live `gpu_seams()`
  call imports the torch trainer.
- **`gpu_seams(config, *, reward=None)`** — backward-compatible keyword so the
  held-out gate can score the frozen split through the `RewardAdapter` (RV-4);
  `run_rl_loop` now passes it.
- **Operator runbook** in `docs/api/rl.md` ("Operator run") — the `fieldkit[rl]`
  install, the separate pinned-vLLM bring-up, the `FK_RL_*` env knobs, and the
  overnight-only dispatch posture. **The live run stays operator-armed** (no
  aarch64+CUDA-13 vLLM wheel + the ~8.5 h loop is a cron drain, not a click).

### Test suite

- **1233 passed, 5 skipped** offline (`pytest tests/`, +9 GPU-free seam tests).
  The vendoring is verified without a GPU: `import fieldkit.rl` stays torch-free,
  the sampler builds correct single-turn messages + `_GpuRollout`s over a fake
  client, the held-out gate scores via the reward adapter, `serve_command` /
  `stop_command` construct the LoRA-enabled argv + EngineCore-aware teardown,
  `RLBackendConfig.from_env` reads the knobs, and `gpu_seams` raises the
  `fieldkit[rl]` pointer when torch is absent. The 5 skips are the `torch` GPU
  training path + 4 `--spark` live integration tests.

### Articles in this release

- None — package-only (the operator follow-on to `rlvr-loop-v1`). The
  `the-machine-improves-itself` deep-dive already assumes the `v0.20.0` RLVR
  surface; this release makes its `gpu_seams` gap real, but the prose is honest
  that the live run is still operator-armed.

## [0.20.1] — 2026-06-03

A one-line bug-fix patch for the M10 recall-eval path, surfaced by the
end-to-end local-knowledge-appliance dogfood. No API change, no schema change
(arena.db stays at `user_version 6`).

### Fixed

- **`fieldkit.harness.mcp.rag_eval_index` raised `NameError: name 'json' is not
  defined` on the real Arena `rag_eval` dispatch path.** The function parses the
  in-repo qa-eval gold set with `json.loads` but the module shipped without a
  module-level `import json` (the only `json.` reference in the file). The
  mock-injected `rag_eval` job tests never executed the real tool, so the M10
  recall-eval path was broken on a live cockpit drain since it landed. Added the
  import + a regression test (`test_rag_eval_index_parses_gold_jsonl`) that
  exercises the gold-set parse infra-free. Surfaced by the end-to-end
  local-knowledge-appliance dogfood (a real Arena reindex+rag_eval drain).

### Test suite

- **1224 passed, 5 skipped** offline (`pytest tests/`). The 5 skips are the
  `torch` GPU training path + 4 `--spark` live-NIM/pgvector integration tests.

### Articles in this release

- None — package-only patch. (The `the-machine-improves-itself` deep-dive
  assumes the v0.20.0 RLVR surface, not this fix.)

## [0.20.0] — 2026-06-03

The **closed-loop RLVR engine — the *engine*** in the `pane → hands → engine`
sequence (`_SPECS/rlvr-loop-v1.md`, the fourth and final roadmap stub). It closes
the loop the first four milestones were built to land: **eval → reward →
fine-tune → re-eval**, with the Spark's own `fieldkit.eval` verifiers as the
reward function. Two new top-level modules + the promotion of the pre-drilled
`rl_run` / `requant` job kinds to dispatchable. **No schema change** (RV-8): the
arena.db stays at `user_version 6` — the trajectory rides `fieldkit.lineage`, the
held-out scores ride `eval_runs`.

### Added

- **`fieldkit.reward` — the verifier→reward adapter (new module, Phase 3)**
  (`__all__` = `Reward`, `RewardAdapter`, `group_advantage`, `RewardError`). The
  scorer half of RLVR: **the eval harness *is* the reward model** (RV-2). A thin
  adapter that turns any `fieldkit.eval` verifier (the seven shipped scorers +
  `exact_match` / `contains`) into a reward — **no learned reward model, no new
  scoring logic**. The reward is a `(success, failure_class, auxiliary)` tuple
  (RV-3), and `failure_class` **reuses the built `fieldkit.lineage.FailureLabel`**
  10-class enum (no new enum) so the loop's per-step `Trial` label *is* the reward
  signal. `auxiliary` carries the partial-credit score so the gradient sees more
  than a keep/revert bit (binary reward mode-collapsed: 0/8 held-out from 42
  rows). `group_advantage` is GRPO's value-network-free baseline — standardize
  within the rollout group; a degenerate group yields a zero advantage vector.
- **`fieldkit.rl` — the closed-loop RLVR driver (new module, the engine)**
  (`__all__` = `GRPOConfig`, `RLLoop`, `RLLoopError`). Wraps the **proven
  hand-rolled ~280-LOC REINFORCE-with-KL + kill-and-restart-vLLM** loop from
  `clawgym-on-spark-grpo` — **not** Unsloth-GRPO / NeMo-RL (neither drove the
  working single-GB10 run; a documented fallback lane, RV-1). Owns the
  orchestration (split → sample → reward → group-relative step → held-out gate →
  checkpoint selection → lineage card); the three GPU-touching seams (sampler,
  trainer, heldout_eval) **inject** — torch / vLLM never import at module load
  (the `dispatch_job(runner=…)` pattern), so the orchestration is GPU-free
  testable. Three grounding corrections are encoded structurally: the **held-out
  gate is a hard gate with held-out-ONLY checkpoint selection** (RV-4 — `t2po`
  hit an 81.8 pp pool↔held-out inversion at step 45; the loop selects on held-out,
  never pool); **pinned vLLM** (`GRPOConfig.vllm_pin`, RV-5 — 6 API drifts / 2
  minor versions); a **≥100-row corpus floor** carved into a frozen held-out
  split before step 0 (RV-10). `gpu_seams` raises until the pinned-vLLM backend is
  vendored into `fieldkit[rl]` (`project_verl_atgpo_vllm_gap`); v1 ships the loop,
  not a re-implemented GPU trainer.
- **`rl_run` / `requant` promoted to `DISPATCHABLE`** (RV-6) — the last two
  pre-drilled `fieldkit.arena.jobs.JobKind` stubs join the dispatcher (the
  M8-`eval_rerun` / M10-`reindex` pattern); `DISPATCHABLE == ALL` now. The RLVR
  run is **async/overnight only** — the 8.5 h GRPO loop can't be a synchronous
  cockpit click, so the `server.py` `POST /api/jobs` allowlist stays narrow and
  `rl_run` reaches the dispatcher via `enqueue_job` (a compare-loss trigger, a CLI
  enqueue), draining under the M11 single-lane cron behind the budget governor.
  `_persist_rl_run` writes an aggregate digest (held-out-selected step, held-out
  vs pool trajectories) to `jobs.result_json` — no new table (RV-8).
- **Two harness MCP tools** — `run_rl_loop` (assembles `RLLoop` over a vertical
  bench, returns the held-out-selected checkpoint + lineage card) and
  `requant_checkpoint` (re-quantize a held-out-winning checkpoint to the GGUF
  variant ladder, dry-run by default). Curated into `build_mcp_server` +
  `MCP_TOOL_SPECS`. Real GPU work, overnight-only.
- **Docs** — new `docs/api/rl.md` (`order:18`) + `docs/api/reward.md`
  (`order:17`); `rl` + `reward` added to both `content.config.ts`
  `FIELDKIT_MODULES` enums, `audit_docs.py MODULES`, and the
  `FieldkitModules.astro` taglines.

### Notes

- Publishable `verifier` / `reward` / `rl_run` artifact kinds are **deferred to
  second-vertical reuse** (RV-9, `feedback_keep_scorer_local_until_reuse`):
  `ARTIFACT_KINDS` stays at 8. v1 ships the engine, not the storefront.

### Test suite

- **1222 passed / 5 skipped** offline (`pytest tests/`) — +28 collected over the
  v0.19.0 baseline (`tests/test_reward.py` for the `RewardAdapter` scorer-kwarg
  filtering + the `(success, failure_class, auxiliary)` tuple over
  `fieldkit.lineage.FailureLabel` + `group_advantage`'s degenerate-group zero
  vector; `tests/test_rl.py` for the GPU-free orchestration with injected
  `sampler` / `trainer` / `heldout_eval` seams, the held-out-ONLY checkpoint
  selection against a monotonically-climbing pool (the `t2po` inversion defense),
  the ≥100-row corpus floor + frozen split, and `gpu_seams` raising; plus the
  `tests/arena/test_jobs.py` extension for the `rl_run` / `requant` dispatch and
  the no-schema-bump assertion). The 5 skips are `torch` (the GPU training path)
  + the 4 pre-existing `--spark` (live NIM / pgvector) integration tests.

### Articles in this release

- None — this is a **package-only** release. The Phase-3 editorial launch (the
  MTBM RLVR `tech-writer` installment + the first §5 "living-model"
  `product-writer` piece) is the gated follow-on, not part of this cut.

## [0.19.0] — 2026-06-03

The **Arena M11 autonomous harness — the hands** in the `pane → hands → engine`
sequence (`_SPECS/spark-arena-v1.md` §15). M11 turns the M8 button-driven
dispatcher into a self-operating overnight loop with a human-review gate. It
reimplements **no dispatch** — it schedules the already-built `drain_jobs()` +
`check_and_enqueue_regressions()`, gated by a new budget governor, behind a
one-drain-at-a-time lock, and stages a morning standup it **never pushes**
(invariants #1/#3). **No schema change** (AH-9): the arena.db stays at
`user_version 6`.

### Added

- **`fieldkit.budget` — the Arena M11 budget governor (new module, Phase 2)**
  (`__all__` = 7 symbols: `BudgetGovernor`, `BudgetDecision`, `SpendDigest`,
  `EscalationReason`, `MemoryEnvelope`, `check_budget`, `BudgetError`). The
  **brake** the autonomous drain consults before each job, returning *allow /
  escalate / defer*. Escalation is the **`LOCAL_CEILING = 33%`**
  *failure-mode-driven* contract (escalate when local *gives up* — a multi-step
  planning / KV-cache-derivation failure class — not on a token ceiling alone,
  AH-4, grounded in H6). M9's cost plane is a **soft prerequisite** (AH-5): with
  a `CostLedger` wired the governor reads the persisted `$/task` + the 33%
  ceiling; without it it degrades to a token + OOM-envelope guard.
  `MemoryEnvelope.fits()` is the OOM guard (the 2026-04-22 box-hang landmine,
  one lane at a time). `SpendDigest` is the standup's Spend row (today's $ by
  lane vs cap, "—" pre-M9). Store-agnostic by duck-typing — never imports
  `fieldkit.arena`. **Governor, not meter** — it consumes M9's ledger (M9-9).
- **`fieldkit.arena.scheduler` — the cron glue (new)** (`__all__` = `DrainLock`,
  `DrainLockHeld`, `run_drain_cycle`, `build_standup`, `DEFAULT_LOCK_PATH`).
  `run_drain_cycle` is one cron tick — acquire the one-drain-at-a-time
  `DrainLock` (the `scheduled_tasks.lock` pattern with stale-pid stealing, R24),
  drain with the governor in the loop, run the freshness sweep (AH-6), stage the
  standup. `build_standup` renders **Ran / Regressed / Queued / Spend** over the
  existing tables (aggregate, operator-private, no push path — R26).
- **`GET /api/standup`** — the morning-standup snapshot (read-only; never drains
  — an HTTP GET launches no GPU lane). Empty (not 404) on a fresh box; the Spend
  row degrades to "—" when the M9 cost plane is absent.
- **`/arena/standup/` cockpit pane** — the morning-review gate: the M9 Spend rail
  + the Ran / Regressed / Failed / Queued buckets, stage-only.
- **Hook battery (`.claude/`)** — the lone `SessionStart` hook expands into a
  battery (AH-2, deterministic shell only): `pre_commit_guard.sh` (PreToolUse —
  secret-scan **hard-blocks** a planted secret; the render verifiers run
  **advisory**, R25), `post_publish.sh` (PostToolUse — stats nudge +
  freshness-trigger enqueue on an articles/products commit), `stop_feedback.sh`
  (the §6.5 Stop loop, finally wired). `secret_scan.sh` is the shared
  privacy-gated-publish scanner (invariant #3).

### Changed

- **`fieldkit.arena.jobs.drain_jobs`** gains an optional `governor` (duck-typed
  `.check_budget(job) -> BudgetDecision`). A claimed job is checked **before**
  dispatch: an *allow* dispatches; an *escalate* / *defer* releases the claim
  back to `queued`, records a `budget_<action>` audit row, and stops the pass
  (the budget brake). Back-compatible — `governor=None` is the M8/M10 behavior.

### Test suite

- **1183 passed / 16 skipped** offline (`pytest tests/`) — +30 over the v0.18.0
  baseline (`tests/test_budget.py` for the `BudgetGovernor` allow/escalate/defer
  contract, the `LOCAL_CEILING` failure-mode trigger, and the `MemoryEnvelope`
  OOM guard; `tests/arena/test_scheduler.py` for `DrainLock` stale-pid stealing,
  `run_drain_cycle`, `build_standup`, and the `drain_jobs(governor=...)` claim
  release). The 16 skips are the pre-existing `--spark` (live NIM / pgvector) +
  optional-dep (torch, matplotlib, great_tables, jupytext) suites. `audit-docs`
  15/16 PASS (`budget` 7/7 + arena clean; cli SKIP — no explicit `__all__`; the
  3-kwarg `ArenaStore` WARN is pre-existing and non-blocking); `audit-landing`
  4/4 PASS (`budget` tagline added). **No schema change** — arena.db stays at
  `user_version 6` (AH-9).

### Articles in this release

- None — M11 is package-only. The Phase-2 cockpit launch article (`product-writer`
  for the morning-standup / cron-queue / budget-governor surface, cross-linking
  the H4 deep-dive) remains gated on Phase 2 shipping.

## [0.18.0] — 2026-06-02

The **two cross-cutting Arena bets — M9 cost plane + M10 recall layer** — ship
together (v0.17.0 was never cut; M9 staged behind M10 and both land here). Two
new modules: **`fieldkit.cost`** (the per-run cost ledger + `$/quality` ranking
axis, Bet 6) and **`fieldkit.memory`** (the managed, multi-source,
provenance-aware Second Brain recall layer, Bet 5). Schema advances `4 → 6` (the
first ALTER-based migration for cost, then two new control-plane tables for
recall). Both are **connective tissue** — they persist + manage what the cockpit
already computed but discarded, and they keep the dispatcher's single-execution-
surface + leak-proof-mirror disciplines.

### Added

- **`fieldkit.cost` — the Arena M9 cost plane (new module, Bet 6)** (`__all__` =
  5 symbols: `CostLedger`, `PriceSnapshot`, `seed_price_snapshot`,
  `cost_per_quality`, `CostError`). Persists the per-run OpenRouter cost the
  cockpit already *computed and threw away*, and surfaces **$/task +
  $/quality-point** as the third ranking axis (`_SPECS/spark-arena-v1.md` §13).
  `PriceSnapshot` + `seed_price_snapshot` own the `openrouter_price_snapshot`
  table, seeded at store-init from the baked H6 evidence
  (`articles/hermes-cost-routing-local-and-openrouter/evidence/`, now
  version-controlled — M9-10) so a comparison stays reproducible as live prices
  drift (R19). `CostLedger.session_spend()` rehydrates the live spend rail
  across a sidecar restart (M9-8); `cost_per_quality()` reads the public
  aggregate off `leaderboard_rows` with the local-lane `$0 (local)` render
  (M9-4). **Ledger, not governor** — enforcement (`fieldkit.budget`) is Phase 2
  (Arena M11, §15).
- **`fieldkit.memory` — the Arena M10 recall layer (new module, Bet 5)**
  (`__all__` = 7 symbols: `MemoryIndex`, `KnowledgeCard`, `Provenance`,
  `ingest_sources`, `coverage_report`, `resolve_qa_set`, `MemoryError`). A
  managed, **multi-source, provenance-aware** index over the Second Brain
  (`_SPECS/spark-arena-v1.md` §14) — the cure for the silent 12/63 staleness that
  bit the roadmap harvest. `MemoryIndex` owns the canonical pgvector
  `blog_chunks` shape (+ the `source · kind · doc_date · verdict · link`
  provenance card, M10-4) with a single provenance-filtered `query()` backend
  (M10-9, cosine-only on GB10, M10-7); `ingest_sources` + the `collect_article_/
  scout_/lineage_sources` readers are the one version-controlled ingest path
  (M10-2, replacing the retired external `ingest_blog.py`, ported verbatim);
  `coverage_report` is the `article_index` ⋈ index freshness number (M10-8);
  `resolve_qa_set` resolves the now-version-controlled qa-eval gold set (M10-12).
  Ships the **operator pane + managed index**; the autonomous re-index hook +
  freshness monitor are Phase 2 (Arena M11, §15).
- **`fieldkit.harness.mcp` — three M10 recall-pipeline tools** (`reindex_memory`,
  `rag_eval_index`, `scout_ingest`) on the new `memory` surface, the dispatcher's
  execution surface for the promoted job kinds. `ask_second_brain` rewired to
  retrieve through the single `fieldkit.memory` backend with a `provenance`
  trust-tier filter (M10-9).

### Changed

- **`fieldkit.arena` schema `user_version` 4 → 5 — the first ALTER-based
  migration** (`ArenaStore._migrate` / `_add_column_if_missing`, R18; prior
  bumps only added whole tables). Adds the per-run cost columns to
  `chat_turns` / `compare_responses` (per side — each lane bills the shared
  prompt at its own input price) + the aggregate `mean_cost_usd` /
  `cost_per_quality_point` to `leaderboard_rows`. The compare/chat server paths
  persist `cost_usd` / `tokens_in` / `tokens_estimated` / `price_snapshot_id`;
  `rebuild_leaderboard` computes the aggregates; the cockpit gains the cost
  cells (compare + leaderboard + a restart-surviving spend rail). Mirror:
  `openrouter_price_snapshot` joins `PUBLISHABLE_TABLES` (public — no prompts),
  the per-run cost columns stay off it (M9-7, anchored by
  `test_mirror_does_not_leak.py`).
- **`fieldkit.arena` schema `user_version` 5 → 6 (Arena M10, Bet 5).** Additive
  `CREATE TABLE IF NOT EXISTS` for `reindex_runs` (per-rebuild provenance —
  operator-private) and `rag_eval_runs` (eval scores per index version —
  public-safe aggregates); the pgvector provenance ALTER lives in
  `fieldkit.memory.MemoryIndex.ensure_schema` (R21), not the store. `jobs.py`
  promotes `reindex` / `rag_eval` / `scout_ingest` into `JobKind.DISPATCHABLE`
  (M10-1) with per-kind persist + a recall@k **promotion gate** (M10-6,
  like-for-like per R22). `server.py` adds the `/api/knowledge` pane API
  (coverage · re-index · RAG-eval · provenance query console). Mirror:
  `rag_eval_runs` aggregates join `PUBLISHABLE_TABLES` (the public RAG-eval
  trend), `reindex_runs` joins `FORBIDDEN_TABLES`, sentinel-anchored in
  `test_mirror_does_not_leak.py` (M10-10). New cockpit `/arena/knowledge/` pane.
  The external RAG assets (the qa-eval gold set, `ingest_blog.py`, the eval
  config, the SB server) are version-controlled under the eval article's
  `evidence/` (M10-12), closing the external-script drift.

### Test suite

- **1153 passed / 16 skipped** offline (`pytest tests/`) — +24 over the v0.16.0
  baseline (10 `tests/test_cost.py`, 8 `tests/test_memory.py`, 3 M10 dispatch
  tests in `test_jobs.py`, 4 new mirror leak anchors, 1 allowlist test extended,
  2 cost version assertions retargeted to `USER_VERSION`). The 16 skips are the
  pre-existing `--spark` (live NIM / pgvector) + optional-dep (torch, matplotlib,
  great_tables, jupytext) suites. `audit-docs` 14/15 PASS (cost 5/5 + memory 7/7
  + arena clean; cli SKIP — no explicit `__all__`); `audit-landing` 4/4 PASS.

### Articles in this release

- `articles/hermes-cost-routing-local-and-openrouter/` — the H6 evidence
  (`openrouter_prices.json`, `cost_router_results.json`) that seeds the M9 price
  snapshot, version-controlled here (M9-10).
- `articles/rag-eval-ragas-and-nemo-evaluator/` — the M10 recall layer's
  version-controlled seed set (qa-eval gold set, `ingest_blog.py`, the NeMo
  Evaluator config, the eval summary, the `fieldkit.memory`-backed SB server),
  committed under `evidence/` (M10-12).

## [0.16.0] — 2026-06-02

The **Arena content line, M1 → M8** — the operator cockpit (`fieldkit.arena`,
new module, `__all__` 0 → 49) lands end-to-end in one release: the SQLite
store + retroactive importer (M2), the FastAPI sidecar + telemetry (M3),
chat-against-the-resident-brain (M4), side-by-side compare + rubric scorer
(M5), the leak-proof publishable-mirror exporter (M6), the v0.2 launch
surface — packaged web UI + Lab board (M7), and the **control plane** — a jobs
dispatcher that executes through the `fieldkit.harness` MCP surface, a
filesystem bench registry, and a wired leaderboard-regression producer (M8).
First Arena release; supersedes the unreleased M1–M5 work that accumulated
since 0.13.0.

### Test suite

- `pytest` (offline) → **1129 passed / 16 skipped** (skips = torch / jupytext /
  matplotlib / great_tables + `--spark`-live-only). `audit-docs` PASS (49/49
  arena symbols documented); `audit-landing` 4/4.
- **Verified on Spark:** M8 control plane driven live in the cockpit (visible
  Chromium) — dispatch → Done, scan → baseline → regression banner, 0 console
  errors; `arena.db` mirror-leak gate green.

### Added

- **`fieldkit.arena` — M1 scaffold (new module, Cockpit content line)**
  (`__all__` = 5 symbols: `ARENA_SURFACE_VERSION`, `DEFAULT_ARENA_PORT`,
  `DEFAULT_ARENA_DB`, `ArenaError`, `LaneNotRegistered`,
  `PublishableSliceEmpty`). The deterministic Python spine of the new
  **Cockpit** content line — the operator surface a solo Spark builder uses
  to drive every artifact `fieldkit` has shipped (sibling to
  `fieldkit.harness`: Hermes = agent harness; Arena = operator harness).
  Submodule layout: `__init__.py` (errors + frozen constants),
  `schemas.py` (M1 placeholder — pydantic request/response shapes land at
  M3–M6), `server.py` skeleton (`create_app()` / `serve()` raise
  `NotImplementedError("M3")`), `cli.py` (Typer subcommands wired to top-level
  `fieldkit` CLI; six commands locked at spec §3.4 — bodies raise
  `typer.Exit` with a milestone marker until each milestone lands). All
  stdlib-only on package load — `import fieldkit.arena` doesn't pull FastAPI.
  Full design at `specs/spark-arena-v1.md`.
- **`arena` optional install extra** (`pip install 'fieldkit[arena]'`) —
  fastapi ≥ 0.115, uvicorn[standard] ≥ 0.30, sse-starlette ≥ 2.1,
  aiosqlite ≥ 0.20, arq ≥ 0.26, redis ≥ 5.0, huggingface_hub ≥ 0.24,
  pyyaml ≥ 6.0. M1's fresh-venv install is the aarch64 canary for the arq +
  Redis combo (spec §10 R4).
- **`fieldkit/docs/api/arena.md`** — module reference page (audit-docs gate
  covers it from M1; symbol coverage 5/5).
- **`audit_docs.py MODULES` list** updated to include `"arena"` so the
  curator audit covers the new module at the next release.
- **New artifact kind `arena_run`** — additive 9th kind alongside
  `quant, lora, adapter, dataset, bench, notebook, harness, skill`. Declared
  at M1 so the artifact schema validates `arena_run` references on day one;
  manifests are written by `fieldkit.arena.publish` at v0.2.
- **New SERIES `Cockpit`** — 8th editorial series (sibling to Harnesses, not
  a sub-arc). Spark Arena is entry #1; the launch article
  (`articles/introducing-spark-arena-on-spark/`) lands at M7.
- **`fieldkit.arena` — M2 store + retroactive importer**
  (`__all__` 6 → 15). New symbols re-exported lazily via PEP 562 so
  `import fieldkit.arena` stays stdlib-only on package load:
  - **`ArenaStore`** (`fieldkit.arena.store`) — synchronous SQLite store at
    `~/.fieldkit/arena.db`, WAL + foreign-keys on. `.initialize()` creates
    the 13-table schema (spec §4.8 verbatim — `lanes`, `chat_sessions`,
    `chat_turns`, `compare_runs`, `compare_responses`, `rubric_scores`,
    `leaderboard_rows`, `human_prefs`, `eval_runs` — plus the four M2
    retroactive-load tables called out in §7: `bench_results`,
    `article_index`, `hf_meta`, `notebook_export`). All upserts use
    `INSERT OR REPLACE` so a second `fieldkit arena import` produces
    identical row counts (the M2 idempotency gate). `PRAGMA user_version=1`
    pinned for forward migration.
  - **`import_artifacts()`** + **`ImportReport`** (`fieldkit.arena.importer`) —
    walks `src/content/artifacts/*.yaml` (manifests → `lanes`),
    `articles/*/article.md` (frontmatter → `article_index`),
    `articles/<slug>/evidence/*_results.json` (per-variant rollups →
    `bench_results`; four bench-shape extractors: `models`/`lanes`
    top-level dicts, cost-router `strategies` + `summary.majority_pass_rates`,
    vertical-router `per_vertical_quality` + `summary.vertical_pass_rates`),
    `notebooks/*/exports/**/*.png` (→ `notebook_export`),
    `~/.hermes/config.yaml` (→ resident-brain lane, optional),
    `articles/picking-the-hermes-brain-on-spark/evidence/hermes_brain_results.json`
    (→ 3 brain-bakeoff lanes + leaderboard seed). HF metadata pull is
    optional (`refresh_hf=False` default keeps the importer offline-safe).
  - **Row records** (`fieldkit.arena.schemas` — stdlib dataclasses, NOT
    pydantic): `LaneRecord`, `BenchResultRow`, `ArticleIndexRow`,
    `HfMetaRow`, `NotebookExportRow`, `LeaderboardRow`. M3+ chat/compare/
    pref records declared but not yet in `__all__`.
  - **`fieldkit arena import`** CLI body lands (was `typer.Exit` stub in
    M1): `--dry-run`/`--write`, `--refresh-hf`, `--no-mirror`, `--json`,
    `--repo-root` overrides. Also runnable as `python -m
    fieldkit.arena.scripts.import_existing`.
- **`src/data/arena-mirror/leaderboard.json`** — day-one leaderboard cut
  (3 rows from the brain-bakeoff seed: qwen3-30b-moe-llamacpp-q4km 90% @
  83.5 tok/s; qwen3-30b-moe-vllm-fp8 87.5% @ 55.0 tok/s; nim-incumbent
  77.5% @ 23.9 tok/s). Astro reads it at build time so `/arena/` ships a
  non-empty leaderboard table from M2 onward; M5 keeps it fresh, M6 hands
  off to the mirror exporter.
- **`/arena/` landing page wired** — the "Leaderboard — day-one cut" card
  reads `src/data/arena-mirror/leaderboard.json` and renders the 3 rows.
  Telemetry + current-lane cards remain explicit M3 stubs.
- **28 new tests** in `fieldkit/tests/arena/` (test_store.py 12 +
  test_importer.py 16): schema idempotency, upsert composite keys, the
  4 bench-shape extractors, fixture-repo end-to-end walks, the
  idempotency gate, and a mirror-output-shape sanity check ahead of M6.
- **`fieldkit.arena` — M3 FastAPI sidecar** (`__all__` 15 → 18). New
  symbols (lazy via PEP 562; FastAPI only loads when `create_app()` is
  called):
  - **`create_app(db, repo_root, telemetry_interval, cors_origins)`**
    (`fieldkit.arena.server`) — builds the cockpit FastAPI app. Endpoints:
    `GET /healthz`, `GET /api/lanes` (resident brain from
    `~/.hermes/config.yaml` re-read every request per Risk R8 + roster
    from the M2 `lanes` table), `GET /api/leaderboard?limit=N` (proxies
    the static mirror JSON), `GET /api/telemetry/stream` (SSE at 500 ms
    cadence). CORS allowed for `127.0.0.1:4321`, `localhost:4321`, and the
    Spark LAN address so the Astro dev page can reach the sidecar.
  - **`serve(host, port, db, repo_root, reload, log_level)`**
    (`fieldkit.arena.server`) — uvicorn launcher; loopback-only by default
    per spec §3.1 #4. `fieldkit arena serve` now resolves to this
    instead of the M2 milestone-marker stub.
  - **`TelemetryHub(interval=0.5)`** (`fieldkit.arena.server`) —
    reference-counted wrapper around `fieldkit.harness.Telemetry`: first
    SSE subscriber starts the sampler, last unsubscribe stops it (the
    spec §4.6 zero-idle commitment). `.subscribe(loop)` returns
    `(queue, unsubscribe_callable)`; `.report_inflight(...)` lets M4+
    stream callers tag tok/s + TTFT + lane id on the live tick.
  - **`telemetry_event_stream(hub, request)`** — async generator
    powering the SSE endpoint, pulled out of the route closure so unit
    tests can drive it directly (no FastAPI / sse-starlette round-trip).
  Also: `src/components/arena/TelemetryGauge.jsx` +
  `src/components/arena/CurrentLane.jsx` (Preact islands via the new
  `@astrojs/preact` integration; uPlot powers the 60s unified-mem
  sparkline), `src/lib/arena/sidecar.mjs` (sidecar URL resolver +
  public-mirror short-circuit), and `/arena/` wires both islands as
  `client:only="preact"`.
- **17 new tests** in `fieldkit/tests/arena/test_server.py` — Hermes
  config reader (3), `TelemetryHub` subscribe/unsubscribe accounting (3),
  `create_app` endpoints (6), and the SSE generator's "hello + disconnect
  → unsubscribe → sampler stop" contract (3 + 2 route-registration
  sanity checks).
- **`fieldkit.arena` — M4 chat against the resident brain** (`__all__`
  18 → 20). New endpoint + records + helpers:
  - **`POST /api/chat/stream`** (`fieldkit.arena.server.create_app`) —
    single-lane chat against the resident brain (the lane returned by
    `GET /api/lanes`'s `resident` field, re-read from
    `~/.hermes/config.yaml` on every request per Risk R8). Body is a
    Pydantic `ChatRequest` (`prompt`, optional `session_id`, optional
    `rubric_id` (M5), `max_tokens=4096`, `temperature=0.0`). Streams
    `start` / `token{channel}` / `done` / `error` / `heartbeat` SSE
    events from `llama-server :8080` via
    `fieldkit.notebook.OpenAICompatClient.chat_stream` + `split_think`
    (per `feedback_nim_think_prefix_convention`). The blocking-httpx
    chat generator runs on `asyncio.to_thread` so the SSE writer never
    blocks the event loop. Returns 503 if the resident config is
    missing / unreadable. Wires
    `TelemetryHub.report_inflight(inflight=True, tok_per_s=…, ttft_ms=…,
    lane_id=…)` on stream start + every ~16 tokens, then `inflight=False`
    on done — the visible M3↔M4 round-trip the spec §4.2 review
    validates.
  - **`chat_event_stream(*, hub, request, body, resident, db_path)`**
    (`fieldkit.arena.server`) — async generator powering the chat route.
    Pulled out of the route closure so unit tests drive it directly
    against a stub `OpenAICompatClient` (no live `llama-server` needed).
    Persists user + assistant turns to `chat_sessions` + `chat_turns`
    (operator-private — spec §4.8 + the M6 mirror exporter's allowlist
    hardcodes `chat_*` tables OUT). On an upstream error, the partial
    reply is still persisted with `finish_reason="error"` so the
    operator can forensic it.
  - **`ChatSessionRecord`** + **`ChatTurnRecord`** (`fieldkit.arena.schemas`,
    re-exported via `fieldkit.arena` PEP-562 lazy map) — stdlib
    dataclasses mirroring the spec §4.8 chat tables. Both default
    `publishable=0`. `ChatSessionRecord` is keyed on `id` (FK target
    for `chat_turns.session_id`); `ChatTurnRecord` is append-only with
    `(session_id, ord)` UNIQUE.
  - **`ArenaStore` chat helpers** — `.upsert_chat_session(row)` (idempotent
    on `id`); `.append_chat_turn(row)` (strict INSERT; returns rowid; the
    UNIQUE on `(session_id, ord)` trips on duplicate ord by design — that
    is a programming error worth surfacing rather than silently
    overwriting); `.chat_session(session_id)` + `.chat_turns(session_id)`
    read helpers.
- **`src/components/arena/ChatLane.jsx`** — Preact island wired on
  `/arena/chat/` as `client:only="preact"`. Custom `fetch` + manual SSE
  parser (EventSource is GET-only and the chat endpoint is POST). UI
  collapses the `<think>` block by default into a `<details>` summary;
  perf chips (TTFT / tok/s / ≈tokens / finish_reason) pin to the
  assistant card footer on `done`. Threads `session_id` from the `start`
  event back into subsequent sends so the multi-turn history stays
  single-session. `/arena/chat/` page mounts the existing
  `<TelemetryGauge>` above the chat so the operator sees the lane chip
  + tok/s light up while a stream is in flight.
- **`ArenaLayout.astro` cockpit nav flip** — "Chat (M4)" stub
  (greyed-out stub) replaced with `<a href="/arena/chat/">Chat</a>`
  (live link). `/arena/` landing footer bumped from `v0.1 — M3` to
  `v0.1 — M4` with a link to `/arena/chat/`.
- **9 new tests** in `fieldkit/tests/arena/` — `test_store.py` +4
  (chat session round-trip + replace-on-conflict + turn append/read +
  duplicate-ord IntegrityError); `test_server.py` +5
  (chat_event_stream emits start/token/done with channel classification +
  persists 2 turns per round + sustains session_id across rounds +
  report_inflight pings + route registration + 503 on missing resident).
- **`fieldkit arena --help`** top-line bumped from "M3 surface" to
  "M4 surface — telemetry SSE + lanes + leaderboard +
  chat-against-resident-brain endpoints live on `fieldkit arena serve`."
- **`fieldkit.arena` — M5 side-by-side compare + rubric scorer**
  (`__all__` 20 → 27). New symbols re-exported lazily via PEP 562:
  - **`POST /api/compare/stream`** (`fieldkit.arena.server.create_app`) —
    Pydantic `CompareRequest` body (`prompt`, `lane_b="openrouter"` (default,
    H6 frontier tier) or `"local:<id>"` (v0.2 only — emits a structured
    `two_local_lanes_v0_2_only` error in v0.1 per spec §4.9 single-brain
    envelope), optional `rubric_id` (server falls back to
    `default_rubric_for_prompt` when absent), `max_tokens=4096`,
    `temperature=0.0`). Emits the full spec §4.3 SSE event sequence
    `start_a → token_a → done_a → start_b → token_b → done_b → score`
    with channel-classified tokens and per-check `ok` + `why` strings.
    503 on missing resident.
  - **`compare_event_stream(*, hub, request, body, resident, db_path)`**
    (`fieldkit.arena.server`) — async generator pulled out of the route
    closure so unit tests drive it directly against stub clients (no live
    `llama-server` or OpenRouter needed). Uses `asyncio.to_thread` to keep
    the SSE writer non-blocking; `_stream_one_side` wrapper handles both
    A and B with the same channel-classifier (the `<think>` boundary is
    a piece-equality check on the chunk).
  - **`GET /api/rubrics`** (`fieldkit.arena.server.create_app`) — returns
    the default 3-rubric registry (`generic-correctness` /
    `patent_claim_validity` / `mcq_letter`); JSON-safe shape.
  - **`POST /api/prefs`** (`fieldkit.arena.server.create_app`) — Pydantic
    `PrefRequest` body (`compare_run_id`, `winner ∈ {A,B,tie}`, optional
    `note`). Inserts one `human_prefs` row and returns `{ok, pref_id,
    n_prefs}` — **separate signal** per spec §4.3, never mutates the
    corresponding `rubric_scores.total`. 404 on unknown `compare_run_id`.
  - **`fieldkit.arena.rubrics`** — new module shipping `RubricSpec`
    (frozen dataclass — id + title + description + executable
    `fieldkit.eval.Rubric`), `DEFAULT_RUBRIC_REGISTRY` (the 3-entry
    built-in dict), `list_rubrics()` (JSON-safe shape for `GET /api/rubrics`),
    `get_rubric(id)` (lookup-or-None), and `default_rubric_for_prompt(prompt)`
    (spec §4.3 substring-sweep picker — patent triggers → patent,
    `(a)/(b)/(c)/(d)/multiple choice` → mcq, else generic). Deterministic
    Python data — no YAML round-trip at runtime per
    `[[feedback_llm_skill_pattern]]`.
  - **`ArenaStore`** chat helpers extended with 8 compare-flow methods:
    `upsert_compare_run`, `upsert_compare_response` (composite
    `(run_id, side)` key — INSERT OR REPLACE so long-stream reconnect can
    re-emit the side cleanly), `append_rubric_score` (strict INSERT,
    returns rowid; CHECK constraint enforces compare_run_id OR chat_turn_id),
    `append_human_pref`, `compare_run(id)`, `compare_responses(id)`,
    `rubric_scores_for_run(id)`, `human_prefs_for_run(id)`.
  - **`CompareRunRecord` / `CompareResponseRecord` / `RubricScoreRecord` /
    `HumanPrefRecord`** promoted to `fieldkit.arena.__all__` + the lazy
    map. `CompareRunRecord` defaults `publishable=1`; per spec §4.8 the
    M6 mirror exporter ships only the `redacted_prompt` column (operator
    opt-in), never `prompt`.
  - **`src/components/arena/CompareDuel.jsx`** — Preact island
    (`client:only="preact"`). Custom `fetch` + manual SSE parser
    (CRLF-normalize per the M4 pitfall — sse-starlette emits `\r\n` line
    endings; JS `indexOf('\n\n')` is strict). Side-by-side A/B cards
    (model chips, reasoning `<details>`, content, perf chips); on the
    `score` event paints rubric checks with name/kind/ok/why under each
    side. Thumbs-up / thumbs-down / tie buttons → `POST /api/prefs`
    (visual lock once recorded). Rubric picker dropdown from `GET
    /api/rubrics`.
  - **`/arena/compare/`** — new page (`src/pages/arena/compare.astro`)
    mounting `<TelemetryGauge>` + `<CompareDuel>`.
  - **`ArenaLayout` cockpit nav flip:** "Compare (M5)" greyed stub → live
    `<a href="/arena/compare/">Compare</a>`. `/arena/` landing footer
    bumped from `v0.1 — M4` to `v0.1 — M5` with a link to `/arena/compare/`.
  - **`fieldkit arena --help`** top-line bumped to "M5 surface".
- **`fieldkit.arena` — M6 publishable-mirror exporter** (`__all__` 18 → 26).
  The leak-proof boundary between the operator-private cockpit DB and the
  public mirror at `ainative.business/arena/`. New symbols (lazy PEP-562
  re-exports):
  - **`export_publishable_slice(store, out_dir, *, allow_empty, rebuild,
    repo_root)`** + **`ExportReport`** (`fieldkit.arena.mirror`) — reads ONLY
    columns listed in `PUBLISHABLE_TABLES`; the `chat_*` tables and
    `compare_runs.prompt` / `compare_responses.{content,reasoning}` are never
    enumerated by any code path. Stages to `_staging/leaderboard.json`,
    `fsync`s, then atomic-renames (NFS-safe per
    `reference_sync_workflow_nfs_mount`). Raises `PublishableSliceEmpty` when
    `allow_empty=False` and the export would blank the public mirror.
  - **`rebuild_leaderboard(store)`** + **`RebuildReport`** — recomputes
    `leaderboard_rows` from `bench_results` + the live
    `compare_runs × rubric_scores × human_prefs` join; idempotent; human-pref
    winrate gated at ≥5 prefs (spec §4.4).
  - **`PUBLISHABLE_TABLES` / `FORBIDDEN_TABLES` / `FORBIDDEN_COLUMNS` /
    `MIRROR_SCHEMA_VERSION`** — the two-layer containment constants
    `tests/arena/test_mirror_does_not_leak.py` pins: an allowlist (the exporter
    reads nothing outside it) belt-and-suspendered by a forbidden list (table
    names never appear in the emitted JSON).
- **`fieldkit.arena` — M7 / v0.2 launch (Lab board + packaged web UI)**. The
  distribution + operator-annotation surface that makes Arena a shippable
  product:
  - **Packaged web UI** — `fieldkit.arena.webui.build_webui(repo_root, *,
    dest, skip_astro, demo)` bakes the Astro cockpit (`base: '/arena'`) into a
    self-contained bundle. **wheel mode** (`ARENA_BUILD=1`) → packaged
    `fieldkit/src/fieldkit/arena/_webui/` (in `pyproject.toml` hatch
    `include`), served by the sidecar's `StaticFiles` mount; **demo mode**
    (`ARENA_DEMO=1`) → `dist-arena-demo-pruned/` for the sidecar-less GitHub
    Pages preview (fetch/EventSource shim + recorded `fixtures.json` +
    `.nojekyll`). New CLI: **`fieldkit arena build [--repo-root --skip-astro
    --demo]`** (builder-side bake) + **`fieldkit arena up [--host --port --db
    --open/--no-open]`** (one-command UX — `pip install fieldkit[arena]` →
    `fieldkit arena up` → `http://127.0.0.1:7866/arena/`). `create_app()`
    mounts the bake via `_mount_packaged_webui` (guarded — a missing bundle
    degrades to API-only).
  - **Lab notes** — operator-private annotations pinned to a Lab board card
    (`/arena/lab/`, `<LabNotes>` island). `ArenaStore.append_lab_note` /
    `.lab_notes` / `.delete_lab_note` + `GET|POST|DELETE /api/lab/notes`.
    Deterministic CRUD, no LLM. The `lab_notes` table is on `FORBIDDEN_TABLES`
    + `(lab_notes, body)` on `FORBIDDEN_COLUMNS` — the freeform body is never
    mirrored.
  - **Launch article** — `articles/introducing-spark-arena-on-spark/` (SERIES
    `Cockpit`, entry #1) + the `/products/` demo bundle.
- **`fieldkit.arena` — M8 control plane: jobs dispatcher + cockpit**
  (`__all__` 26 → 49). Promotes Arena from a *recorder* into a *dispatcher* —
  the place the operator triggers work from (`_SPECS/spark-arena-v1.md` §12).
  The cockpit gains `/arena/jobs/` (a 4-column board · dispatch form · "scan
  regressions" button) + `/api/jobs*` endpoints. New symbols:
  - **Queue spine** — `JobRecord` / `JobTriggerRecord`
    (`fieldkit.arena.schemas`), `JobKind` / `JobStatus`, `enqueue_job` /
    `dispatch_job` / `drain_jobs` (`fieldkit.arena.jobs`). Two new SQLite
    tables (`jobs` / `job_triggers`, `user_version` 2 → 3) drained
    one-at-a-time (M8-5, single lane / 128 GB envelope); a partial unique
    index coalesces duplicate in-flight triggers (R15). Dispatch executes
    **through the `fieldkit.harness` MCP surface** (M8-1) — one execution
    surface shared with Hermes, so the containment rails (`publish`
    unreachable, `quantize` dry-run-default, `--network=none`) are defined
    once. `eval_rerun` is the first/only real job type — it wraps the inline
    `eval_scores` scorer + activates the dormant `eval_runs` status row.
  - **Bench registry** — `resolve_bench(bench_id, *, bench_dir)` +
    `DEFAULT_BENCH_DIR` + `BenchNotRegistered`. The dispatcher resolves an
    `eval_rerun`'s `bench_path` / `scorer` / `max_tokens` from
    `$ARENA_BENCH_DIR/<id>.jsonl` (+ optional `<id>.meta.json`) when the
    payload carries only a `bench_id`; an unregistered bench fails loud,
    naming the path it searched.
  - **Regression → re-eval (wired producer)** —
    `detect_leaderboard_regression` (pure diff), `enqueue_regressions`, and
    `check_and_enqueue_regressions` (the wired producer: diffs the live
    `eval_leaderboard()` against a new `leaderboard_baseline` table,
    `user_version` 3 → 4, enqueues a confirming `eval_rerun` per over-τ
    accuracy drop, then re-baselines). Exposed at **`POST
    /api/jobs/check-regressions`** + the cockpit "scan regressions" button;
    the first scan only sets the baseline (no re-eval storm).
  - **Harness tools** — `fieldkit.harness.mcp` gains `run_vertical_eval` +
    `measure_variants` (9 registered MCP tools), the dispatcher's only
    execution surface.
  - **Two-layer mirror containment** — `jobs` / `job_triggers` /
    `leaderboard_baseline` on `FORBIDDEN_TABLES`, `(jobs, payload_json)` on
    `FORBIDDEN_COLUMNS` — operator prompts/lanes/benches never mirrored (R13).
  - **Errors** — `JobDispatchError`, `UnknownJobKind`, `BenchNotRegistered`.

### Notes

- M2's idempotency gate (`fieldkit arena import` twice → same counts on
  every table) is the foundation for M5's "compare runs append" and M6's
  "mirror exporter writes from settled state" semantics.
- Per `feedback_keep_scorer_local_until_reuse`: the M2 importer's bench-shape
  extractors stay in `fieldkit.arena.importer`. They will only promote to
  `fieldkit.eval` once a second module needs them.
- The remaining CLI subcommands (`mirror`, `memcheck`,
  `rebuild-leaderboard`, `promote-run`) still exit with their milestone
  markers (`typer.Exit` + a marker) until their milestone lands.
- `from __future__ import annotations` is deliberately NOT used in
  `fieldkit.arena.server` — FastAPI's dependency-injection introspects
  the endpoint function signatures via `inspect.get_type_hints`, and
  PEP 563 deferred annotations make the locally-imported `Request`
  symbol invisible (looks at module globals). Every other arena module
  keeps the future import.

## [0.13.0] — 2026-05-28

### Added

- **`fieldkit.harness` — Cost-tier Route group (H6 — cost routing)** (`__all__` 54 → 59).
  Promoted from the H6 cost-router work, sibling of the H5 vertical-router
  surface. Same deterministic-predicate discipline (no runtime LLM
  classifier, no embedder) on a different routing dimension: vertical
  routes change *which expert* answers a prompt; cost tiers change *which
  tier* (local Spark $0 → OpenRouter cheap → OpenRouter frontier).
  - `RouteTier` — frozen dataclass for one tier: `name`, `endpoint`,
    `model`, `complexity_keywords`, `min_input_tokens`,
    `price_per_m_input_usd` / `price_per_m_output_usd`, `api_key_env`,
    `notes`. The first tier in a `CostRouterConfig.tiers` tuple is the
    floor (its triggers are ignored — a tier can't escalate to itself).
  - `CostRouterConfig` — frozen `(tiers,)` wrapper. `.classify(prompt, *,
    est_input_tokens=None)` walks tiers high → low and returns the first
    one whose triggers fire (keyword OR token-budget); falls through to
    the floor. `.route_for` is an alias; `.tier_by_name(name)` looks up;
    `.render_yaml()` emits a diff-stable `router.yaml` block with snapshot
    prices embedded (R7). Static `.estimated_cost_usd(prompt_toks,
    completion_toks, tier)` is the per-call $ accounting the H6 article
    uses for the dollar curve.
  - `build_cost_router(tiers)` — the factory. Validates: non-empty,
    unique names, non-monotonic prices (a later tier is supposed to cost
    more — anything else is almost certainly a config bug), and every
    escalation tier carries at least one trigger.
  - `estimate_tokens(text)` — 4-chars-per-token heuristic used by
    `classify` when the caller doesn't pass an explicit count. Avoids
    taking a tokenizer dependency for a routing decision (a 10%
    over/undercount doesn't flip the tier).
  - +18 new tests (`test_harness.py`, full suite 920 → 946 passing).
- **`HarnessProfile.lane_metrics: LaneMetricColumns | None`** — overrides
  the last two columns + caption of the rendered serving-lanes table.
  The default (`None`) keeps the H2/H4 tool-call shape; the H6 cost router
  swaps in `$/M input` + `$/M output` with a money formatter (`$V/M`,
  2 decimals); the H5 vertical router can repurpose for pass-rate +
  warm-time. `LaneMetricColumns(label_a, label_b, key_a, key_b,
  format_a="percent", format_b="percent", caption="")` —
  `format_a/b` is `"percent"` / `"money"` / `"raw"`. Empty `caption`
  suppresses the default agent-critical line entirely. Retires the
  v0.12.1 polish item flagged in the H5 publish (template assumed
  tool-call metrics on every `kind: harness` artifact).

### Fixed

- **`fieldkit.eval.score_answer` substring check now honors both `all` and
  `any`** (latent bug since the graded primitives landed in v0.11.0). Was
  reading `any` only and silently ignoring `all` — so an `all`-only check
  ALWAYS returned the empty-`any` failure path (`"none of [] in answer"`),
  and a combined `all+any` check returned a pass as soon as ANY of the
  `any` terms appeared, regardless of whether the required `all` term was
  present. Now: `all` is the AND-clause (every term must appear,
  case-insensitive); `any` is the OR-clause (at least one term must
  appear); both empty is now an explicit config-error failure (was
  silent-pass). The H5 vertical-router prompts combined the two in a way
  that happened to keep passing under the old scorer (the `any` list was
  already discriminating enough); H6's t07 numeric prompt — `all: ["31.60"]`
  with no `any` — surfaced the gap. +4 regression tests
  (`test_eval_graded.py`).
- **`HarnessProfile.to_manifest()` renders `article:` in path-shape
  directly** — `articles/<slug>/`, not the bare `<slug>` the schema
  rejects. Retires the post-write fixup the H5 publisher script carried
  (v0.12.1 polish item #1). H5's publisher script can drop its trailing
  `text.replace(...)` block on its next edit.
- **`HarnessProfile.render()` frontmatter tags deduped against the four
  built-ins** (`agent-harness`, `hermes`, `dgx-spark`, `orionfold`) —
  caller-supplied `tags=("hermes", ...)` no longer ships them twice
  (v0.12.1 polish item #3).

### Verified on Spark

- The H6 cost-router surface was exercised end-to-end against a live
  Qwen3-30B-A3B Q4_K_M llama-server brain on `:8080` (always-warm) plus
  OpenRouter `openai/gpt-4o-mini` and `anthropic/claude-opus-4.1` over
  the wire. 108-call bakeoff (12 prompts × 3 strategies × N=3) landed at
  router accuracy 12/12, local-only 8/12, cost-routed 11/12,
  frontier-only 12/12, leak rate 4/12 = 33.3%, total OpenRouter spend
  $1.85. Driver:
  `articles/hermes-cost-routing-local-and-openrouter/evidence/run_cost_router_bakeoff.py`.
- The scorer fix was validated against the H5 vertical-router prompts as
  a side check — every prompt that previously passed under the old `any`-
  only path still passes under the new AND/OR semantics (the H5
  `all+any` shape always satisfied both clauses).
- `Orionfold/spark-hermes-cost-router` published live to HF via
  `publish_harness` (4 staged files; manifest landed at
  `src/content/artifacts/spark-hermes-cost-router.yaml` with the new
  v0.13.0 path-shape `article:` rendering — no post-write fixup needed).

### Test suite

- `pytest` offline: **950 passed, 16 skipped** (`matplotlib` /
  `great_tables` missing in the minimal venv — same skip set as v0.12.0,
  not regressions).
- `audit_docs.py`: harness 59/59, eval 51/51, every other module passing
  symbol-coverage. 11/12 PASSED, 1 SKIP (`cli` has no explicit `__all__`).
- `audit_landing.py`: 4/4 PASSED.

### Articles in this release

- [`articles/hermes-cost-routing-local-and-openrouter/`](https://ainative.business/field-notes/hermes-cost-routing-local-and-openrouter/)
  — Harnesses H6, cost-tier routing on Spark + Hermes + OpenRouter. The
  measured leak rate is 33.3%; the cost-routed strategy lands at 91.7%
  pass-rate for $2.19/100 tasks vs the frontier ceiling at 100% / $2.94.
  `fieldkit_modules: [harness, eval]`, `customer_linked: true`.

## [0.12.0] — 2026-05-28

### Added

- **`fieldkit.harness` — Route group (H5 — vertical router)** (`__all__` 49 → 54).
  Promoted from the H5 vertical-router work over the 5 Orionfold GGUFs
  (patent / legal / finance / cyber / medical) — same `RouterConfig` shape
  H6's `build_cost_router` will extend with cost-tier predicates. Surface:
  - **`VerticalRoute`** — frozen
    `(name, hf_repo, variant, keywords, description, base_model, params_b,
    dtype, weight, article)`. `keywords` is the deterministic classifier
    signal (lowercased substring matches); `weight` defaults to 1.0 and
    biases tie-breaks toward a more specific vertical when keyword sets
    overlap; `params_b` / `dtype` flow into the `serve_lane` unified-memory
    guard.
  - **`RouterConfig`** — frozen `(routes, default, escalation=None)`.
    `.classify(prompt) -> VerticalRoute` is the pure keyword-scored
    predicate (no LLM, no embedder, per spec §4.6 discipline) — ties break
    listed-first; zero matches → `default`. `.route_for(prompt)` is an
    alias. `.render_yaml() -> str` emits a diff-stable router block for
    embedding in `HarnessProfile.router_yaml`. `.serve_for(prompt, *,
    guard=True, headroom_gb=8.0, warm_timeout=180.0, host, port,
    lane_factory=None)` is the OOM-safe convenience contextmanager:
    classify, then `serve_lane` the picked vertical one-at-a-time per the
    128 GB unified-memory envelope (`project_spark_unified_memory_oom`).
  - **`build_vertical_router(routes, *, default, escalation=None)
    -> RouterConfig`** — the factory. Lightweight validation (raises
    `RoutingError`): `routes` non-empty; route names unique + non-empty;
    every route has at least one keyword (a route with no keywords could
    never be picked — that's a bug, not a config); the `default` route
    name is not also in `routes` (the default competes with no one).
  - **`lane_spec_for_vertical(route, *, host, port, n_ctx, reasoning_format)
    -> LaneSpec`** — the default `LlamaServerLane`-bound `LaneSpec`
    builder. Pure function. Override `RouterConfig.serve_for`'s
    `lane_factory` to swap to NIM / vLLM / etc.
  - **`RoutingError`** — `HarnessError` subclass raised by
    `build_vertical_router` rather than emit a quietly-broken router.

- **Tests** (+24 → 920 passed). `test_harness.py::test_router_*` covers the
  five-vertical happy path, the four validation refusals, classifier
  correctness (case-insensitivity, score-over-listed-first, listed-first
  tiebreak, weight tiebreak, default fallback on zero hits), `render_yaml`
  determinism + escalation rendering + unit-weight omission, the
  `lane_spec_for_vertical` knobs, and the `serve_for` lifecycle (right
  vertical picked, default fall-through, teardown-on-exception).

- **`fieldkit/docs/api/harness.md`** — Route section between Harden and
  Eval; `RoutingError` row; status line + summary updated; H6 cost router
  noted as the only remaining "Coming across the arc" surface. Audit-docs
  gate covers it.

### Verified on Spark

- **H5 vertical-router bakeoff** — 5 Orionfold vertical GGUFs served
  one-at-a-time via `llama-server` on `:8090` (each Q5_K_M, 4.5–5.5 GB,
  warm 4–6 s), with the Step-2-pinned `Qwen3-30B-A3B-Q4_K_M` MoE always-warm
  on `:8080` as the default brain. **Router accuracy 30/30 = 100.0%** on a
  30-prompt suite (5 per vertical + 5 default-brain); **overall answer
  quality 27/30 = 90.0%** (finance / cyber / medical 5/5; patent / legal /
  brain 4/5). The 3 fails are auditable to measurement artifacts
  (`max_tokens=1024` budget exhaustion, one rubric framework mismatch),
  not model failures. Evidence:
  `articles/hermes-vertical-router-on-spark/evidence/vertical_router_results.json`.

### Test suite

- `cd fieldkit && /tmp/fk/bin/pytest tests/` → **920 passed, 16 skipped**
  (the 16 skips are unconditional `matplotlib` / `great_tables` absences in
  the minimal `/tmp/fk` venv). 24 new `test_router_*` tests against the H5
  Route surface — five-vertical happy path, the four validation refusals,
  classifier correctness (case-insensitivity, score-over-listed-first,
  listed-first tiebreak, weight tiebreak, default fallback on zero hits),
  `render_yaml` determinism + escalation rendering + unit-weight omission,
  `lane_spec_for_vertical` knobs, and the `serve_for` lifecycle (right
  vertical picked, default fall-through, teardown-on-exception). No `--spark`
  integration tests added — the H5 surface is pure config + a deterministic
  predicate; live serving is exercised by the bakeoff above, not by tests.

### Articles in this release

- `articles/picking-the-hermes-brain-on-spark/` (Step 5 of the Harnesses
  brain-bakeoff arc; landed since v0.11.0) — `fieldkit_modules:
  [eval, harness]`.
- `articles/hermes-vertical-router-on-spark/` (H5 — written alongside this
  release) — `fieldkit_modules: [harness]`.

## [0.11.0] — 2026-05-27

### Added

- **`fieldkit.eval` — graded-rubric primitives** (`__all__` 42 → 51). Promoted
  from `articles/field-fixing-the-hermes-harness-on-spark/evidence/
  hermes_brain_eval.py` after the Step-2 Hermes brain-quality bakeoff scored
  the SAME rubric across three serving lanes (NIM-incumbent, llama.cpp Q4_K_M
  MoE, vLLM FP8 MoE) — the cross-lane reuse that earned the abstraction per
  `feedback_keep_scorer_local_until_reuse`. Surface:
  - **`CheckSpec`** — frozen `(kind, any, all, keys, value, tolerance)` with
    the five `CHECK_KINDS` exercised by the bakeoff (`substring`, `json_keys`,
    `regex`, `honesty`, `numeric`). `CheckSpec.from_dict(d)` parses the
    on-disk JSON shape; `CheckSpec.with_substitutions(subst)` resolves
    `{{placeholder}}` tokens inside `any`/`all`/`keys` and returns a new
    frozen spec (idempotent).
  - **`Rubric` + `Rubric.single(spec)`** — wraps `tuple[CheckSpec, ...]`
    (length 1 today); multi-check requires every check to pass. Future-proofs
    AND-of-checks without growing call sites.
  - **`CheckResult(passed, why)`** — short reason string suited to terminal
    logs and the review-queue markdown.
  - **`GradedPrompt` + `GradedPromptSuite.load(path, substitutions=None)`** —
    parses the prompt-suite JSON shape; `select(core_only=, available_conditions=)`
    filters to runnable; `by_id(...)` lookup. Raises `ValueError` on missing
    `prompts`, missing `id`/`prompt`, or unknown `check.kind`.
  - **`score_answer(answer, spec, *, hedges=HEDGE_PHRASES)`** — accepts
    either a `CheckSpec` or `Rubric`; the `hedges` kwarg lets callers swap in
    domain-specific uncertainty vocabularies.
  - **`extract_last_json(text)`** — public helper that walks the LAST bare
    JSON object out of mostly-prose model output.
  - **`HEDGE_PHRASES`** — 33-entry uncertainty vocabulary; distinct from
    `REFUSAL_PATTERNS` (those grade RAG context-grounding refusals).
- **`fieldkit.harness` — brain evaluator** (`__all__` 39 → 49). The harness
  ×model matrix that composes the new graded rubric with the existing
  `tool_call_reliability` to rank serving lanes on QUALITY + consistency, not
  just format-error rate:
  - **`BrainCandidate`** — `(label, base_url, model, context_length, lane)`.
    `lane=None` evaluates an already-up endpoint; `lane=<ServingLane>` wraps
    the eval in `serve_lane(lane, guard=True, warm_timeout=...)`.
  - **`bucket_hermes_sessions(records, slots, ...)`** — pure fn: assign each
    exported Hermes CLI session to exactly one slot via the
    last-slot-with-`t_start <= started_at` rule (mutually exclusive,
    fixes the ±2s-pad double-counting bug from the local script). Exposed
    because the bug was subtle and the test fixture is the contract.
  - **`evaluate_brain(suite, *, label, scratch_dir, runs, ...)`** — drives ONE
    already-pointed-at endpoint through a suite: N attempts per prompt,
    bucket sessions to attempts, score via `fieldkit.eval.score_answer`,
    compose `tool_call_reliability` over the bucketed records, build the
    scorecard. Optional dedicated throughput probe (`throughput_samples`) and
    telemetry sampler (`enable_telemetry`) run AROUND the suite so the lane
    is still warm but the probe's decode doesn't double-count in GPU%.
  - **`evaluate_brains(suite, candidates, *, scratch_dir, ...)`** — the
    bakeoff loop: per candidate, optionally `serve_lane()`,
    `point_hermes_at_endpoint(...)`, call `evaluate_brain`, tear down.
    Errors in one candidate are recorded on its scorecard's `error` field
    and the loop continues.
  - **`BrainScorecard` + `BrainPromptScore` + `BrainAttempt`** — frozen
    dataclasses for the result tree. `BrainScorecard.rank_key` returns the
    Step-2 ordering: `(honesty_gate, core_pass_rate, consistency,
    -runaway_rate, tok/s)`. Honesty is a GATE, not just an axis — a
    confabulator sorts below a hedger regardless of other scores.
  - **`point_hermes_at_endpoint(base_url, model, *, context_length=64000)`**
    — the light-touch swap (5 `hermes config set` calls including the
    auxiliary.compression context floor Hermes reuses for compression).
    Complements the heavier first-time `configure_hermes`.
  - **`Telemetry`** + **`measure_throughput`** — Spark-aware GPU%/unified-memory
    sampler (`nvidia-smi memory.used` is `[N/A]` on GB10's unified memory, so
    `/proc/meminfo` carries the real memory line) and a dedicated decode
    probe (median tok/s over N OpenAI-compatible calls).
- **53 new tests** (test_eval_graded.py: 36; test_harness.py append: 17),
  full suite 896 passed / 16 optional-deps skips. Audit-docs `eval` 51/51,
  `harness` 49/49.

### Verified on Spark

- **Step-2 Hermes brain-quality bakeoff** (the cross-lane reuse that earned
  this surface) ran the same graded suite head-to-head against three serving
  lanes on GB10: `nim-incumbent` (live Nemotron-9B NIM), `qwen3-30b-moe-llamacpp-q4km`
  (llama.cpp Q4_K_M at 127.0.0.1:8080), and `qwen3-30b-moe-vllm-fp8`. Verdict
  pinned the MoE Q4_K_M lane as the Hermes brain (8/8 @ 90% consistency,
  83.5 tok/s, 31.8 GB unified; beat NIM 6/8 @ 82%, 23.9 tok/s + vLLM FP8 on
  every axis). The driver scripts in
  `articles/field-fixing-the-hermes-harness-on-spark/evidence/` now use this
  release's `fieldkit.harness.evaluate_brain` + `fieldkit.eval.GradedPromptSuite.load`
  directly; on-disk JSON shape preserved verbatim for diff stability with the
  shipped verdict file.
- The mutually-exclusive `bucket_hermes_sessions` rule replaces the local
  script's ±2s-pad window that double-counted back-to-back attempts (caught
  during Step-1 fixture iteration; the test fixture is the contract).
- `Telemetry` + `measure_throughput` ran live during the bakeoff: GB10's
  `nvidia-smi memory.used` is `[N/A]` (unified memory), so the sampler reads
  `/proc/meminfo` for `unified_used_gb_max` and parses each `nvidia-smi` field
  independently; live runs captured GPU util 91% mean / 96% max, 93.3 GB
  unified peak, 75°C peak under sustained agentic load.

### Test suite

- `cd fieldkit && pytest` → **896 passed**, 16 skipped (optional-deps:
  matplotlib / great_tables / jupytext) — was 843 passed at v0.10.0.
- 53 new tests across `tests/test_eval_graded.py` (36 — every `CheckSpec`
  kind, `Rubric` composition, `GradedPromptSuite.load` placeholder resolution
  + `select` filters) and the brain-evaluator section of `tests/test_harness.py`
  (17 — bucketing edge cases, `BrainScorecard.rank_key` honesty-gate +
  tiebreakers, end-to-end `evaluate_brain` with monkeypatched subprocess +
  session export, `evaluate_brains` error-isolation loop).

### Articles in this release

- `field-fixing-the-hermes-harness-on-spark` (Step-2 cross-lane bakeoff;
  `fieldkit_modules: [harness, eval]`) — the article that earned this
  abstraction. The next session ships Step-4 (publish the suite as a
  `dataset` artifact) and Step-5 (the deep-dive article on how to actually
  measure a local agent brain), both of which assume this release.

## [0.10.0] — 2026-05-26

### Added

- **`fieldkit.harness` — H4 fieldkit-as-MCP surface** (`__all__` 33 → 39). The
  keystone: a new `fieldkit.harness.mcp` submodule exposes a *curated* subset of
  fieldkit surfaces as Model-Context-Protocol tools so an agent harness (Hermes
  first) can drive the Spark over stdio (`python -m fieldkit.harness.mcp`):
  - **Seven tools** (`MCP_TOOL_SPECS`): `spark_inference_envelope` +
    `spark_weight_footprint` (capabilities, read-only), `measure_gguf_throughput`
    + `measure_gguf_perplexity` (quant, real GPU work), `quantize_gguf` (quant,
    `dry_run`-default + envelope-guarded), `publish_quant_dry_run` (publish,
    dry-run-*forced* — the real-push path is unreachable through the server), and
    `ask_second_brain` (rag, read-only — the `mcp-second-brain-in-claude-code`
    bridge). Curation **is** the containment posture (H3 at the tool layer).
  - **`build_mcp_server(name="fieldkit")`** / **`run_mcp_server`** lazy-import
    `mcp.server.fastmcp.FastMCP` and register the tools with `readOnlyHint`
    annotations; the tool *functions* are plain + unit-testable without the SDK.
  - **`MCPToolSpec`** (frozen, pure data) + **`MCP_SERVER_NAME`** +
    **`McpNotAvailable`**. The `mcp` SDK is the new optional **`fieldkit[harness]`**
    extra; `import fieldkit.harness` stays stdlib-only (lazy PEP 562 re-export).
  - +13 tests (843 total); audit-docs `harness` 39/39; `docs/api/harness.md`
    fieldkit-as-MCP section.
- **`fieldkit.harness` — H3 Harden surface** (`__all__` 28 → 33). Turns a
  permissive local `HermesConfig` into a desk-grade one with a pure function,
  mapping each policy field to a real Hermes config key verified against the
  installed v0.14.0 schema (`terminal.*`, `tool_loop_guardrails.*`,
  `approvals.*`, `agent.*`, `session_reset.*`):
  - **`HardeningPolicy`** (frozen) — the §4.3 baseline posture: docker-sandboxed
    terminal, `--network=none` egress deny, secrets confined to `~/.hermes/.env`,
    local-only provider, manual approvals, hard-stopping tool-loop guardrails, a
    turn cap, and an ephemeral sandbox that resets on a schedule. + `DEFAULT_HARDENING`.
  - **`harden_config(config, policy=DEFAULT_HARDENING)`** — pure function → a new
    frozen `HermesConfig` with the hardened sections folded into `.sections`
    (input untouched). Raises **`HardeningError`** rather than emit a falsely-hardened
    config when the provider isn't in `LOCAL_PROVIDERS` under `local_first`,
    `approval_mode == "off"` (`--yolo`), or a secret leaks into the config body.
  - **`LOCAL_PROVIDERS`** — the local-serving provider allowlist (the native
    `nvidia` cloud provider is deliberately excluded).
  - **`HermesConfig` gains `sections`** — top-level config.yaml sections beyond
    `model:`; `render()` emits them after `model:`, `config_set_commands()` emits
    scalar leaves as `hermes config set` lines (list/dict leaves like
    `terminal.docker_extra_args` are skipped — `config set` can't parse them).
  - Conceptual basis: the project's Guardrails-on-the-retrieval-path policy
    pattern (a frozen policy + a pure apply function). +10 tests (830 total);
    audit-docs `harness` 33/33; `docs/api/harness.md` Harden section.

### Verified on Spark

- **The H4 keystone gate ran live.** A hardened-pattern Hermes Agent v0.14.0, brained
  by a local NIM Nemotron-Nano-9B-v2 (no API key), drove `measure_gguf_throughput`
  through `fieldkit.harness.mcp` over stdio → real `llama-bench` on a 4.7 GB Q4 GGUF
  → 41.75 tok/s generation. `tool_call_reliability` over the exported session:
  `format_error_rate 0.0`, `clean_run_rate 1.0`. A second turn drove the read-only
  `spark_inference_envelope`. Evidence in
  `articles/hermes-drives-the-spark-via-fieldkit-mcp/evidence/`.

### Test suite

- `pytest tests/` → **843 passed, 12 skipped** (skips are missing matplotlib /
  great_tables in the minimal venv). +13 `tests/test_harness_mcp.py`; audit-docs
  `harness` 39/39; audit-landing 4/4.

### Articles in this release

- `hermes-drives-the-spark-via-fieldkit-mcp` (Harnesses H4, keystone) — assumes the
  `fieldkit.harness.mcp` surface + the `fieldkit[harness]` extra.
- `hardening-the-hermes-harness-on-spark` (Harnesses H3) — assumes the Harden surface.

## [0.9.0] — 2026-05-26

### Added

- **`fieldkit.harness` module — H1 surface.** The deterministic Python spine
  of the new **Harnesses** content line — optimized agent harnesses for the DGX
  Spark, Hermes Agent (Nous Research, MIT) first (`specs/hermes-harness-v1.md`).
  Builds on the Session-1 foundation (`HarnessError` / `ServingLaneError` /
  `UnifiedMemoryExceeded` hierarchy, `LaneSpec`, abstract `ServingLane`) with the
  full H1 surface, all verified on the Spark against Hermes v0.14.0 + the cached
  Nemotron-Nano-9B-v2 NIM:
  - **Serve:** concrete `NIMLane` (the hero — `docker run` recipe with
    `NIM_MAX_BATCH_SIZE=32`, `nim.wait_for_warm` reuse, short-name→image
    resolution, `footprint_gb` for the guard) and `LlamaServerLane` (delegates to
    `notebook.local_server`); `resolve_lane` over a populated `SERVING_LANES`
    registry; `serve_lane(lane_or_spec, guard=True, headroom_gb=8.0)`
    contextmanager whose guard refuses an OOM-stacking lane before launch and
    whose teardown enforces one-model-at-a-time.
  - **Install / doctor:** `install_hermes` (two-key safety on `curl | bash`),
    `hermes_doctor` + `DoctorReport` / `DoctorCheck` (section-aware parsing so the
    dozens of un-configured-integration ✗'s don't fail `.ok`), `HermesNotInstalled`
    / `DoctorFailed`, `HERMES_INSTALL_URL`.
  - **Configure:** `HermesConfig` / `EnvFile` / `configure_hermes` — render the
    `provider: custom` + `base_url` config + `.env` for a local lane, endpoint
    resolution reusing `notebook.discover_local_server`.

  `docs/api/harness.md` updated; 31 H1 tests (29 unit + 2 `@pytest.mark.spark`
  live: `hermes_doctor` + `serve_lane(NIMLane)` end-to-end). Harden / route land
  across H3–H6.
- **`fieldkit.harness` — H2 surface (serving-lane bakeoff + tool-call eval +
  the first `harness` artifact).** Extends the module from 20 → 28 `__all__`
  symbols:
  - **Serve:** `VLLMLane` — the high-throughput MoE lane (`Qwen3-30B-A3B-FP8`),
    `vllm serve` inside the community DGX-Spark vLLM image (prebuilt
    Spark-tested wheels, no aarch64 source build), whose `teardown()` sweeps
    orphaned `EngineCore` PIDs after `docker rm` (the R8 landmine,
    `feedback_vllm_engine_core_orphan`). `OllamaLane` — the lowest-friction
    local alternative (`:11434`, pull + unload-on-teardown). Both registered in
    `SERVING_LANES` / `resolve_lane`.
  - **Eval:** `export_hermes_sessions` (shells `hermes sessions export` — the
    SQLite session store is the structured trace surface),
    `agent_runs_from_hermes_sessions` (→ `eval.AgentRun`; tool turns vs.
    malformed-call error turns), `tool_call_reliability` (the agent-critical
    `format_error_rate` / `clean_run_rate` reducer), and `HarnessEvalResult`
    (composes `eval.summarize_agent_runs`). ~90% reuse of `fieldkit.eval`.
  - **Profile / publish:** `HarnessProfile` (the `ModelCard` analog —
    `.render()` / `.files()` / `.to_manifest()`) and `publish_harness` (dry-run
    by default; reuses `publish.HFHubAdapter`), producing the first
    `ArtifactManifest(kind="harness")`.

  `docs/api/harness.md` updated (audit-docs: harness 28/28); +20 unit tests.
  Parser validated against the real H1 session export.
- **Two new artifact kinds** in the content schema: `harness` (a reproducible
  Spark-Hermes profile bundle, rendered by `HarnessProfile`) and `skill` (an
  agentskills.io `SKILL.md` package, cross-compatible with Claude Code skills).
  Appended to `publish.ARTIFACT_KINDS` and `src/content.config.ts`.

### Fixed

- **`publish._render_yaml_block` now emits list-of-dict as structured YAML
  mappings**, not the Python `repr` of each dict. A latent bug that mis-rendered
  `known_drift` / `notebooks` / `siblings` on **every** artifact-manifest kind
  (the destination Zod schema needs `item` / `bound` objects, not strings).
  Surfaced while writing the first `kind: harness` manifest.

### Verified on Spark

- The full `fieldkit.harness` serve + eval + profile surface was exercised
  end-to-end on the DGX Spark via the H2 five-lane bakeoff: `serve_lane(guard=True)`
  brought up NIM, vLLM (`VLLMLane`, with the EngineCore orphan-sweep teardown),
  and llama.cpp (`LlamaServerLane`) lanes one at a time; `export_hermes_sessions`
  → `agent_runs_from_hermes_sessions` → `tool_call_reliability` scored every lane
  at 0% format-error / 100% clean; `HarnessProfile` + `publish_harness` produced
  the `Orionfold/spark-hermes-profile` manifest (dry-run). Memory returned to
  ~116 GB free after every teardown (no orphan survived).

### Test suite

- `820 passed, 16 skipped` offline (`pytest`; skips are matplotlib/great_tables
  not installed in the minimal venv + 2 `@pytest.mark.spark` markers). audit-docs
  `harness 28/28`; audit-landing `4/4`.

### Articles in this release

- `articles/the-hermes-harness-on-spark/` (H1 — install + NIM provider).
- `articles/hermes-serving-lane-on-spark/` (H2 — the serving-lane bakeoff).

## [0.8.0] — 2026-05-24

### Added

- **`fieldkit.notebook` reply rendering + streaming.** Three new exports turn a
  reasoning model's raw `<think>…</think>answer` reply into proper notebook
  output instead of a tagged text blob:
  - `split_think(reply) -> (reasoning, answer)` — handles closed, unclosed
    (budget-truncated), no-think, and empty-false-start shapes.
  - `display_reply(reply)` — renders the reasoning in an always-visible muted
    box (brand palette) above the answer as Markdown in a Jupyter kernel; prints
    raw outside one. The default the artifact notebooks use.
  - `stream_reply(client, messages)` — opt-in live streaming (reasoning box fills
    token-by-token, then the answer), backed by a new
    `ChatClient.chat_stream(...) -> Iterator[str]` on every backend
    (`OpenAICompatClient` parses SSE and reconstructs the `<think>` shape across
    server reasoning-formats; `LlamaCppClient` streams the in-process engine).
  10 new tests; `docs/api/notebook.md` updated (audit-docs: notebook 19/19).

### Verified on Spark

- The patent-strategist user notebook ran end-to-end against a local
  `llama-server` serving `Orionfold/patent-strategist-v3-nemo-GGUF` Q5_K_M
  (`--reasoning-format none`): `display_reply` rendered five reasoning boxes,
  all spaced (`think_space_ratio` 0.156–0.171), with the answer as Markdown;
  `stream_reply` streamed the chain token-by-token over SSE.

### Test suite

- `pytest tests/` offline: **780 passed, 3 skipped** (1 torch-absent training
  test, 2 `--spark`-gated). `audit_docs.py --strict-kwargs`: 10/11 PASS, 1 skip
  (cli has no `__all__`), 0 fail. `audit_landing.py`: 4/4 PASS.

### Articles in this release

- No new articles in the `fieldkit/v0.7.0..HEAD` window; the
  `patent-strategist-bakeoff-unsloth-vs-nemo-framework` article was edited (the
  Unsloth lane was unpublished — see the repo history), and its companion
  notebooks now use the new `display_reply` renderer.

## [0.7.0] — 2026-05-23

### Added — `fieldkit.notebook` Spark serving glue

- **`local_server(hf_repo, *, variant="Q5_K_M", n_ctx=8192, chat_template="jinja", reasoning_format="none", ...)`** — context manager that serves a GGUF on a local `llama-server` for the `with` block (resolve+download → `-ngl 99` → wait `/health` → **tear down on exit**), yielding the endpoint URL. The OOM-safe one-model-at-a-time pattern, promoted from a hand-rolled shell script. Binary resolved via `server_bin=` → `FIELDKIT_LLAMA_SERVER` → `PATH` → known Spark build.
- **`discover_local_server(candidates=None, *, timeout=0.5)`** — probe `127.0.0.1:8080` (llama-server) / `:8000` (NIM) for a reachable OpenAI-compatible server; returns the base URL or `None`.

### Changed — model-card notebook on-ramp is now a `## Notebooks` section

- **`ModelCard.render()` emits a `## Notebooks` table section** (after positioning, before Spark-tested) instead of a pre-positioning badge row. The section is a short intro + a table (Notebook | What it does | Open) with the Colab/Kaggle badges per row. HF renders markdown images as `display: block` even in table cells, so an inline badge row stacks one-per-line with heavy whitespace; the table fixes the layout and explains each notebook. NARRATIVE-CONTRACT Rule 8 reworked to match.
- **`notebooks[]` entries accept optional `name` / `blurb`** to override the table's display name and one-sentence description; both default from the entry's `label` ("Build it" → Builder, "Use it" → User).

### Changed — `fieldkit.notebook` server path is now the Spark default

- **`open_model(...)` autodiscovers a local server on Spark** (new `autodiscover` arg; default on for `runtime="spark"`) before the in-process path — since `llama-cpp-python` has no aarch64 wheel, a running `llama-server`/NIM is the working Spark backend. Behavior on cloud/`local`/explicit-endpoint runtimes is unchanged.
- **`OpenAICompatClient.chat` reconstructs the `<think>` block** from a `reasoning_content` field when the server's `--reasoning-format` splits it out — a reasoning model no longer returns a silently-empty `content`.
- **`open_model` warns when `chat_format` is passed on a server path** (the server owns the chat template) instead of dropping it silently.

### Test suite

Total suite: **774 passed, 3 skipped** offline (`pytest -q`, `/tmp/fk` venv) — up from 764 at v0.6.0 (+10). The 3 skips are the torch-gated training snapshot test and the two long-standing `--spark`-gated live-NIM / pgvector tests. New coverage exercises the `local_server` lifecycle, `discover_local_server` probing, `open_model` Spark autodiscovery, the `reasoning_content` think-block reconstruction, and the `## Notebooks` ModelCard section.

### Verified on Spark

- `open_model("Orionfold/patent-strategist-v3-unsloth-GGUF")` autodiscovered a live `llama-server` on `:8080` (Q5_K_M, `--jinja --reasoning-format none`) and returned an `OpenAICompatClient` whose `.chat()` produced a `<think>` reasoning trace — the dual-path contract walked end-to-end on the GB10 from a fresh notebook venv.

### Notebooks-as-artifacts v1 (this release's driver)

No new field-notes article landed in this window. The release closes the Spark gap in `specs/notebooks-as-artifacts-v1.md`: the published `user.ipynb` notebooks could not serve a model on Spark before this glue, because `open_model`'s in-process path needs the aarch64-unavailable `llama-cpp-python`. Surfaced while walking the first-time-user journey for the patent-strategist notebook pilot.

## [0.6.0] — 2026-05-23

The **notebooks-as-artifacts v1** build-out — two new public modules (`fieldkit.viz` + `fieldkit.notebook`), a 6th artifact kind (`notebook`), and the positioning-first card surface — that turns every Orionfold vertical's `artifact → card → article` loop into a runnable on-ramp: a builder + user Jupyter pair distributed as one-click Open-in-Colab / Open-in-Kaggle notebooks. Implements `specs/notebooks-as-artifacts-v1.md` (status: locked). Adds the `fieldkit[notebook]` install extra — the visual + inference stack the two new modules import lazily. `ARTIFACT_KINDS` is re-shaped: three speculative kinds dropped, `notebook` added.

### Added — `fieldkit.viz` (branded chart + hero-table layer)

New module. Turns an `ArtifactManifest` (or its bare measurement dicts) into marketing-grade, stack-colored matplotlib figures + great_tables hero tables — the same visuals the HF cards, article figures, and notebooks reuse, all the deterministic output of the measured Spark run. Lazy + optional (behind `fieldkit[notebook]`).

- **`spark_quad(manifest, *, ...)`** — the four-axis signature hero (perplexity / throughput / vertical accuracy / thermal envelope) on one `Figure`.
- **`variants_table(manifest, *, sizes=..., ...)`** — the great_tables hero table with inline nano-plot bars and the recommended row highlighted; the matrix readers screenshot. (nano-plots need `polars` even with a pandas frame — gated on the optional dep.)
- **`perplexity_sweep` / `throughput_bars` / `vertical_eval_bars`** — single-axis panels.
- **`train_wall_compare(walls, *, title=...)`** — builder-only bakeoff lane comparison.
- **`save_figure` / `apply_style`** — high-DPI Agg export + the bundled `orionfold.mplstyle` (composes `dark_background` + brand rcParams; shipped as package data).
- **`STACK_COLORS` / `DEFAULT_ACCENT` / `STYLE_PATH`** — the stack-origin color map (NARRATIVE-CONTRACT Rule 7) + the style-asset path.
- **`VizNotAvailable`** — raised with an install hint when the `[notebook]` extra is absent.

### Added — `fieldkit.notebook` (dual-path runtime + scaffolding)

New module. Powers the runtime split the notebooks need: Spark = full local fieldkit path; Colab/Kaggle = pull the published GGUF → `llama-cpp-python` on a free GPU — same notebook, no branching in user code.

- **`detect_runtime()` / `is_cloud(rt)` / `Runtime`** — environment detection.
- **`open_model(hf_repo, variant=None, *, runtime=..., chat_format=..., n_ctx=..., ...)`** → **`ChatClient`** — one `.chat()` surface over either **`OpenAICompatClient`** (httpx → NIM / llama-server) or **`LlamaCppClient`** (in-process llama-cpp-python). Backend chosen by runtime.
- **`colab_url` / `kaggle_url` / `notebook_path` / `badge_markdown` / `GITHUB_REPO`** — the badge-row URL builders, so the card badges and the in-notebook badges can't drift apart.
- **`NotebookBuilder`** — deterministic jupytext py:percent scaffold (banner, parameters cell, code cells, prose-slot markers) that the `notebook-author` skill fills.
- **`NotebookNotAvailable`** — raised with an install hint when the extra is absent.

### Added — 6th artifact kind + positioning-first card surface

- **`notebook` artifact kind** in `ARTIFACT_KINDS` — a per-vertical builder+user Jupyter pair, manifest-described with no measurements of its own (chart data is sourced from the sibling model manifest by slug).
- **`notebooks` field on `ModelCard` + `ArtifactManifest`** — a tuple of `{label, colab, kaggle}` entries; `_render_model_card` renders the badge row under the one-liner, above positioning (Rule 8 — a navigation aid, not a claim).
- **`positioning` / `stack_origin` / `known_drift` fields** on `ModelCard` + `ArtifactManifest` — the positioning-first card shape from the patent-strategist repolish: positioning leads, every drift entry carries a bound, drift never sits above-the-fold, no forward-looking roadmap.

### Changed

- **`ARTIFACT_KINDS` re-shaped.** Dropped three speculative kinds (`embed`, `reranker`, `space` — no live manifest used them) and added `notebook`. The canonical set is now `(quant, lora, adapter, dataset, bench, notebook)`; the test invariant moves to `_canonical_six`. Mirrored in the Astro Zod schema (`src/content.config.ts`).
- **`_render_model_card`** now leads with positioning and pushes bounded drift below-the-fold, matching `/NARRATIVE-CONTRACT.md` (the surface-agnostic card rubric extracted this cycle).

### Removed

- **`embed`, `reranker`, `space`** from `ARTIFACT_KINDS` (breaking for any consumer of those enum members; none were live — permitted on `0.x` per the versioning policy).

### Build / packaging

- **`fieldkit[notebook]` extra** added to `pyproject.toml`: matplotlib, great-tables, pandas, polars, jupytext, papermill, jupyterlab, pyyaml, huggingface_hub, llama-cpp-python. The released `0.5.0` predated this extra, so `pip install 'fieldkit[notebook]'` warned there and pulled nothing; from `0.6.0` it resolves the visual + inference stack the notebooks need on a fresh Colab.
- **`orionfold.mplstyle`** shipped as package data (`src/fieldkit/assets/*.mplstyle` added to the wheel include).

### Test suite

Total suite: **764 passed, 3 skipped** offline (`pytest -q`, `/tmp/fk` venv) — up from 710 at v0.5.0 (+54). The 3 skips are the torch-gated training snapshot test and the two long-standing `--spark`-gated live-NIM / pgvector tests. New coverage spans `fieldkit.viz` (19 tests) and `fieldkit.notebook` (20 tests), plus the `_canonical_six` artifact-kind invariant and the ModelCard positioning / drift / notebooks-field cases.

### Verified on Spark

- `fieldkit.viz` renders marketing-grade `spark_quad` + `variants_table` from the live `ii-medical-8b-gguf` and `patent-strategist-v3-unsloth-gguf` manifests (high-DPI Agg export + Playwright over nbconvert HTML for the great_tables hero).
- `fieldkit.notebook` `NotebookBuilder` scaffolds the jupytext skeleton, and the medical builder notebook executes headless on the GB10 (`nbconvert --allow-errors`) with 0 errors.

### Notebooks-as-artifacts v1 (this release's driver)

No new field-notes article landed in this window; the release implements `specs/notebooks-as-artifacts-v1.md` and ships the patent-strategist + medical notebook pilots under `notebooks/`. The `notebook-author` + `notebook-snapshot` skills consume these two modules.

## [0.5.0] — 2026-05-22

The `fieldkit.training` v0.5 build-out — five new modules (`recipe`, `convert`, `run`, `probe`, `decide`) that lift the patent-strategist v3 paired bakeoff (NeMo Framework vs Unsloth, session 2026-05-21 → 2026-05-22) out of one-shot scripts and into a reusable, symmetric library surface. Drives Article H end-to-end. `fieldkit.training.__all__` grows from 7 → 46 entries; +203 new tests; package suite goes 507 → 710 passed.

The release notes below run newest-phase-first (E → A) to match the build order. Cross-phase totals, live-Spark verification, and the article window are summarized at the bottom.

### Added — `fieldkit.training` v0.5 build-out (Phase E: `decide.train_backend` + `refresh` flywheel)

Final module of the v0.5 `fieldkit.training` build-out, after Phase A's `recipe.TrainRecipe` (`bee458d`), Phase B's `convert` (`9f2a59f`), Phase C's `run` + `merge_and_export` + `standardize_hf_export` (`2e142e7`), and Phase D's `probe.ReasoningProbe` + `ProbeReport.compare` (`78a3131`). YAML-lookup decision API with a lifecycle filter + a refresh flywheel — the contract that lets every future `articles/*-bakeoff-*` write a decide-entry alongside its prose so the next-session's `train_backend(...)` returns the article's findings programmatically.

- **`fieldkit.training.train_backend(*, base_model_family, optimize_for, dirs=None)`** — walks the configured entry directories (default = bundled `SEED_ENTRIES_DIR` + `USER_ENTRIES_DIR`), filters to `lifecycle="active"` entries with `question="train_backend"`, sorts newest-first by `created`, and returns a `DecidePick` with the first finding whose `optimize_for` matches the argument from an entry whose `context.base_model_family` matches. `DecidePick.backend` is an alias for `.pick` to match the v0.5 spec example. Raises `DecideError` with a clear message (lists every active entry's slug + created date for the no-context-match case; lists available `optimize_for` keys for the partial-match case) when no entry covers the cell.
- **`fieldkit.training.load_entries(*, dirs=None, lifecycle="active", question=None)`** — directory scanner. `lifecycle` accepts a single value, a sequence, or `None`. `question` filters when set. Returns entries sorted by `created` descending. Missing directories are silently skipped; non-YAML/JSON files are ignored.
- **`fieldkit.training.refresh(*, dirs=None, freshness_days=180, today=None, include_lifecycle=None)`** — the refresh flywheel. Walks every entry (any lifecycle by default — audit signal matters across the full corpus, not just active) and flags any older than `freshness_days`. Returns a list of `StalenessReport` sorted oldest-first.
- **`fieldkit.training.DecideEntry`** — frozen dataclass for a parsed YAML entry. Constructor enforces `lifecycle in VALID_LIFECYCLES` and at least one finding. Methods: `find(optimize_for=...)`, `matches_context(**constraints)`, `age_days(today=None)`. Classmethods: `from_dict(data, *, path=None)`, `from_yaml(path)`. Pyyaml-optional — falls back to `json.loads` for JSON-shaped entries.
- **`fieldkit.training.DecideFinding`** — frozen dataclass for one row of an entry's `findings` list. `extra` field preserves forward-compatibility keys.
- **`fieldkit.training.DecidePick`** — frozen dataclass returned by `train_backend`. Carries `pick` / `backend` (alias) / `evidence` / `entry` (the matched `DecideEntry`) / `optimize_for` / `context` / `entry_path` (alias).
- **`fieldkit.training.StalenessReport`** — frozen dataclass returned by `refresh`. `entry` / `age_days` / `stale`.
- **`fieldkit.training.DecideError`** — distinct exception class for decide-layer failures.
- **`SEED_ENTRIES_DIR` / `USER_ENTRIES_DIR`** — Path constants. Seed dir is `fieldkit/src/fieldkit/training/data/decide-entries/` (bundled in the wheel via `pyproject.toml` package-data include — `src/fieldkit/**/data/**/*.yaml` added this release). User dir is `~/.fieldkit/decide-entries/` (read-after-write, gitignored, created by the caller on first write).
- **`VALID_LIFECYCLES`** — frozenset of valid lifecycle values: `"active"` (currently authoritative — `train_backend` returns these), `"superseded"` (replaced by newer entry; preserved for audit), `"deprecated"` (explicitly retired; preserved for audit but never returned from lookups).
- **`DEFAULT_FRESHNESS_DAYS`** — `180`. Six months matches typical hardware / framework / base-model drift cadence.

### YAML schema

```yaml
slug: 2026-05-22-paired-bakeoff       # required, unique within dir
lifecycle: active                     # active | superseded | deprecated
created: 2026-05-22                   # ISO date (YYYY-MM-DD)
question: train_backend               # the decide.<name>() entry point
context:                              # required mapping
  base_model_family: qwen3-r1-distill
findings:                             # required, non-empty
  - optimize_for: patent_chain_length
    pick: nemo
    evidence: "+44% mean chain ..."
sources: []                           # optional, default []
supersedes: []                        # optional, default []
notes: "free-form annotation"         # optional
```

`SEED_ENTRIES_DIR` ships empty at Phase E landing — the first seed entry (the patent-strategist v3 paired bakeoff) ships alongside Article H so the prose and the YAML stay co-located in the commit log. The wheel-include glob picks it up automatically once the YAML lands.

### Test suite (Phase E)

**+53 new tests** in `tests/test_training_decide.py`:

- Module constants: `DEFAULT_FRESHNESS_DAYS`, `VALID_LIFECYCLES`, `SEED_ENTRIES_DIR` path shape, `USER_ENTRIES_DIR` path shape.
- `DecideFinding` — frozen enforcement, extra-keys preservation through `DecideEntry.from_dict`.
- `DecideEntry.from_dict` — minimal shape, path recording, optional fields carried, native `date` object accepted (pyyaml emits these), missing-required-key + bad-lifecycle + empty-findings + non-mapping-context + finding-missing-pick + bad-iso-date + findings-as-string rejection.
- `DecideEntry` methods — `find` happy + None, `matches_context` all/partial/empty-constraints, `age_days` with override + negative clamp.
- `DecideEntry.from_yaml` — JSON-form load (so the suite passes without pyyaml), missing-file + non-mapping rejection.
- `load_entries` — explicit dir, sorted newest-first, default-active filter, `lifecycle=None` returns all, sequence-of-lifecycles, bad-lifecycle rejection (string + sequence), question filter, non-entry-suffix skip, multi-dir merge, missing-dir tolerance.
- `train_backend` — happy path with two optimize_for values, newer-entry-wins-on-equal-context, non-active entries skipped, no-context-match error message, no-optimize_for error message, only-train_backend-question, context-copy on result.
- `refresh` — staleness flagging with `today=` override, oldest-first sort, default-all-lifecycles, `include_lifecycle="active"` filter, negative `freshness_days` rejection, empty corpus, `StalenessReport.age_days` round-trip.

All pure-python; YAML / JSON fixtures written to `tmp_path` so no bundled-seed-dir or user-dir filesystem is ever touched. The seed dir + user dir resolution is asserted by Path-constant comparison only.

Total suite: **710 passed, 2 skipped** offline (`pytest -q`, `/tmp/fk` venv) — up from 657 at Phase D landing. The 2 skips are the long-standing `--spark`-gated live-NIM / pgvector tests.

### Build / packaging

- `pyproject.toml` `[tool.hatch.build.targets.wheel].include` extended to pick up `src/fieldkit/**/data/**/*.yaml`. Seed YAMLs dropped into the package data dir are now wheel-resident.

### Added — `fieldkit.training` v0.5 build-out (Phase D: `probe.ReasoningProbe` + `ProbeReport.compare(normalize_budget=True)`)

Fourth module of the v0.5 `fieldkit.training` build-out, after Phase A's `recipe.TrainRecipe` (commit `bee458d`), Phase B's `convert` (commit `9f2a59f`), and Phase C's `run` + `merge_and_export` + `standardize_hf_export` (commit `2e142e7`). Lifts `scripts/probe_reasoning.py` + `scripts/compare_probes.py` into a reusable library surface, with the budget-normalization knob the NeMo-vs-Unsloth bakeoff (session 2026-05-21) discovered the hard way: lanes run at different `max_new_tokens` and a naive overall-aggregate compare gives the higher-budget lane an unearned chain-length advantage.

- **`fieldkit.training.ReasoningProbe`** — orchestrator. Construct from a sequence of `ProbeQuestion`, or load JSONL via `ReasoningProbe.from_jsonl(path)`. `run(model_id, *, lora_path, step, max_new_tokens, temperature, generator, on_progress)` returns a `ProbeReport`. Default `generator` lazy-imports `torch` + `transformers` (+ `peft` when `lora_path` is set) and loads bf16 on `cuda:0` with `attn_implementation="sdpa"` — the same shape as `scripts/probe_reasoning.py`. Pass a `generator=fn(ProbeQuestion) -> str` callable to bypass the load entirely (test seam + the legitimate prod knob for callers with a pre-loaded model).
- **`fieldkit.training.ProbeReport`** — bag of `ProbeRow` plus run-metadata, with `overall` / `by_category` aggregates as properties. `with_budget(cap)` returns a new report excluding any row whose `<think>` chain exceeds the cap (rows with `has_think=False` preserved; new `max_new_tokens` is `min(self, cap)`; dropped qids appended to `excluded_qids`). `to_json(path)` / `ProbeReport.from_json(path)` round-trip the canonical JSON shape — matches what `scripts/probe_reasoning.py` already writes so existing artifacts (`probes/baseline.json`, `probes/patent-strategist-v3-*.json`) load directly. Tolerant of the legacy `think_quality_score` key on load — LLM-judge scoring is owned by an in-CC-session orchestrator skill per `[[feedback_llm_skill_pattern]]`.
- **`ProbeReport.compare(other, *, normalize_budget=True, thresholds=None, baseline_label=None, current_label=None)`** — runs the spec §4 Layer 5 pass/fail check (`think_presence_rate` ≥ 90%, `think_token_length` ≥ 75%). With `normalize_budget=True` (default), if the two reports ran at different `max_new_tokens` any qid whose chain exceeds the smaller cap in EITHER report is excluded from BOTH before per-metric ratios are recomputed — the bakeoff's exact apples-to-apples fix. Excluded qids surface on `CompareResult.excluded_qids` for footnoting. `thresholds` accepts a custom `CompareThresholds`; `baseline_label` / `current_label` override the auto-derived model-id labels (use `"unsloth"` / `"nemo"` for lane bakeoffs).
- **`fieldkit.training.parse_think(response)`** — pure helper that picks the longest `<think>...</think>` pair from a response. R1-distill models occasionally false-start with an empty `<think></think>` before the real chain; the non-greedy regex alone would match the empty pair first (caught on smoke-step-200 row 14 of the patent-strategist v1 lineage). Char-quarter token approximation.
- **`fieldkit.training.summarize_rows(rows)`** — pure-python aggregator. `think_presence_rate` over all rows; `think_token_length` over `has_think=True` rows only (matches the standalone runner's `summarize()`). Re-runnable after any filter for subset summaries.
- **`ProbeQuestion` / `ProbeRow` / `ProbeSummary`** — frozen dataclasses. `ProbeQuestion` keeps `source` / `license` / arbitrary `metadata` pass-throughs from the probe-set JSONL so provenance survives the round-trip. `ProbeRow` is the per-question result (`qid`, `category`, `response`, `has_think`, `think_n_tok`, `think_text`, `wall_seconds`). `ProbeSummary` is what `summarize_rows` + `ProbeReport.overall` return.
- **`CompareThresholds` / `CompareRow` / `CompareResult`** — frozen dataclasses for the compare surface. `DEFAULT_COMPARE_THRESHOLDS` is the module-level singleton (presence 0.90, length 0.75 — the spec §4 Layer 5 defaults).
- **`ProbeError`** — distinct exception class so callers selectively catch probe-layer failures.
- **`THINK_REGEX`** — the compiled `<think>(.*?)</think>` pattern, exposed for callers that re-parse cached responses (e.g. the LLM-judge sidecar described in `[[feedback_llm_skill_pattern]]`).

### Test suite (Phase D)

**+56 new tests** in `tests/test_training_probe.py`:

- `parse_think` — no block, single block, empty (false-start) block, longest-of-multiple pickup, multiline DOTALL handling, `THINK_REGEX` export.
- `summarize_rows` — empty input zeros, all-think mean math, mixed-presence math, no-present-rows zero length.
- `ProbeQuestion` / `ProbeRow` — frozen dataclass enforcement, metadata default.
- `ProbeReport` — `max_new_tokens<=0` rejection, `overall` + `by_category` math, repr.
- `ProbeReport.with_budget` — over-cap exclusion, has_think=False rows preserved, no-op below cap, lower-budget preserved on cap > self, `cap<=0` rejection, excluded-qids composition across calls.
- `ProbeReport.compare` — same-budget pass + default labels, custom label overrides, presence-drop FAIL, custom thresholds enable pass, normalize-budget exclusion (the bakeoff case), normalize is no-op on same budget, `normalize_budget=False` direct compare, skip on zero baseline, per-category breakdown captured, `DEFAULT_COMPARE_THRESHOLDS` value lock.
- `ProbeReport.to_json` / `from_json` — canonical-shape dict, round-trip through disk, missing-file / bad-JSON / missing-key error paths, legacy `think_quality_score` key tolerated on load (recomputed from rows).
- `ReasoningProbe.from_jsonl` — required-key load, optional pass-throughs collected into metadata, missing-file / malformed-line / missing-key / empty-file rejection, blank lines skipped.
- `ReasoningProbe.run` — fake-generator path, `lora_path` / `step` / `max_new_tokens` / `temperature` round-trip, `on_progress` callback per-question, `max_new_tokens<=0` rejection, `wall_seconds` recorded, no-think response handled, empty question-list rejection, `__len__`.

All pure-python; no torch / transformers / peft / live model needed. The real generator path is exercised by hand in production (the existing `scripts/probe_reasoning.py` already validates that surface). Total suite: **657 passed, 2 skipped** offline (`pytest -q`, `/tmp/fk` venv) — up from 601 at Phase C landing. The 2 skips are the long-standing `--spark`-gated live-NIM / pgvector tests.

### Added — `fieldkit.training` v0.5 build-out (Phase C: `run` + `merge_and_export` + `standardize_hf_export`)

Marquee module of the v0.5 `fieldkit.training` build-out, after Phase A's `recipe.TrainRecipe` (commit `bee458d`) and Phase B's `convert` (commit `9f2a59f`). Symmetric LoRA SFT driver across the NeMo Framework and Unsloth backends, with poll-disk liveness baked in and the BF16-clean export transformation that the patent-strategist v3 NeMo lane discovered the hard way (session 2026-05-21) lifted out of one-shot bash and into the library so the next lane doesn't repeat the discovery.

- **`fieldkit.training.run(recipe, *, mode, poll_interval, on_progress, runner, sleep)`** — recipe → backend command → subprocess → poll-disk liveness → `TrainResult`. Builds the backend-specific `docker exec` command from a `TrainRecipe` (NeMo: `scripts/p65_train_nemo_lora.py` with the same flag set the bash orchestrator uses; Unsloth: `recipe.extra_env['TRAIN_SCRIPT']` with recipe fields passed as env vars). Polls `<run_dir>/latest_checkpointed_iteration.txt` + `iter_NNNNNNN/` directories — the *only* reliable progress signal under docker-exec + shell-redirect, where `train.log` can lag the process by 4+ hours per `[[feedback_megatron_train_log_buffering]]`. Defaults to a synchronous `subprocess.run` runner; injectable for tests and for async (nohup-style) launchers. Run-dir layout owned here: `<output_dir>/runs-smoke/` for smoke, `<output_dir>/runs-full/` for full.
- **`fieldkit.training.merge_and_export(recipe, *, iter, expect_iter, standardize, tokenizer_class_remap, runner)`** — merge a LoRA adapter into base + export to HF BF16 + bake in the BF16-clean transformation. **NeMo:** invokes Megatron-Bridge's `merge_lora.py` + `convert_checkpoints.py export` and stages the merged checkpoint to `<output_dir>/merged-mcore/` + the HF export to `<output_dir>/merged-hf-bf16/`. Mirrors `scripts/p65_merge_and_probe.sh` stages 1/2. **Unsloth:** invokes the caller-supplied `recipe.extra_env['MERGE_SCRIPT']` with `BASE_MODEL` / `LORA_CKPT` / `MERGED_HF` env vars. Then always (unless `standardize=False`) runs `standardize_hf_export` so the output is consumer-ready for `huggingface_hub.upload_large_folder`, `convert_hf_to_gguf.py`, and `fieldkit.publish.publish_quant`. Resolves the LoRA iter from `latest_checkpointed_iteration.txt` by default; explicit `iter=` overrides; `expect_iter=` catches early-stopped runs the same way `p65_merge_and_probe.sh` did.
- **`fieldkit.training.standardize_hf_export(hf_dir, *, tokenizer_class_remap)`** — pure-python helper that bakes in the two known NeMo-export quirks: (1) shard names like `model-NNNNN-of-000002.safetensors` get renamed to the HF-standard `model-NNNNN-of-00002.safetensors` width (`max(5, len(str(total_shards)))` digits) with matching `model.safetensors.index.json` rewrite — per `[[feedback_nemo_export_shard_numbering]]`; and (2) `tokenizer_config.json`'s `tokenizer_class` field is rewritten via lookup table (default `DEEPSEEK_TOKENIZER_CLASS_REMAP`: `TokenizersBackend` → `LlamaTokenizer`) — per `[[feedback_nemo_export_tokenizer_class_quirk]]`. Idempotent; tolerant of missing index and missing tokenizer config; raises `MergeExportError` only on malformed inputs (rename collision, non-JSON index, etc.). Pass `tokenizer_class_remap={}` to disable the tokenizer fix.
- **`fieldkit.training.poll_run_progress(run_dir)`** — pure-python helper that reads `latest_checkpointed_iteration.txt` + scans for `iter_NNNNNNN/` directories. Returns `(latest_iter, sorted_iter_dirs)`. Used internally by `run()`; surfaced as a public function so callers can build their own progress monitors. `(0, [])` on a non-existent run dir is the documented quiescent state.
- **`fieldkit.training.DEEPSEEK_TOKENIZER_CLASS_REMAP`** — the default `tokenizer_class` remap dict, exposed for inspection / extension. Currently `{"TokenizersBackend": "LlamaTokenizer"}`. Other model families that surface a similar export quirk can extend the table by passing a merged dict to `standardize_hf_export`.
- **`TrainResult` / `MergeExportResult`** — frozen dataclasses returned from `run()` / `merge_and_export()`. `TrainResult` carries `(backend, mode, run_dir, final_iter, wall_seconds, container, log_path, iter_dirs)`. `MergeExportResult` carries `(backend, source_iter, merged_hf_dir, merged_mcore_dir, tokenizer_class_remapped, shard_renames, standardize_applied)`. Both are hashable; safe to drop into a lineage row.
- **`TrainError` / `MergeExportError`** — distinct exception classes so callers can selectively catch launch-time + runtime training failures vs merge / export / standardize failures. Both are `RuntimeError` subclasses.

### Test suite (Phase C)

**+38 new tests** in `tests/test_training_run.py`:

- `poll_run_progress` — missing dir, empty dir, latest file only, sorted iter dirs, non-iter siblings ignored, unparseable latest file degrades to 0.
- `standardize_hf_export` shard-rename branch — over-padded shards renamed (+ index rewrite), idempotent re-run, already-standard shards untouched, genuine 5-digit totals left alone, missing dir errors, malformed index errors, missing index tolerated.
- `standardize_hf_export` tokenizer-class branch — default remap fires, unmapped class left alone, empty remap dict disables fix, missing tokenizer config tolerated, exported constant value locked.
- `run` — NeMo full + smoke modes (with `--train-iters` vs `--smoke` flag verification), `extra_env` overrides forwarded into the docker-exec command, Unsloth requires `TRAIN_SCRIPT`, Unsloth with `TRAIN_SCRIPT` produces ps-train-targeted command + env vars, non-zero runner rc raises `TrainError`, bad mode + negative poll-interval rejected, `on_progress` callback fires, async runner + poll loop, recipe-preflight failure surfaces as `TrainError`.
- `merge_and_export` — NeMo end-to-end with shard rename + tokenizer remap baked in, explicit `iter` overrides resolution, `expect_iter` mismatch guard, missing-iter clear error, `standardize=False` skips cleanup, Unsloth requires `MERGE_SCRIPT`, Unsloth with `MERGE_SCRIPT` produces one-shot docker-exec, `MergeExportResult` frozen, `TrainResult` frozen.

All pure-python; no torch / docker / megatron-bridge / live container needed. Backend shell-outs are exercised via a `_FakeRunner` / `_MergeExportRunner` injection that records the command and writes synthetic `iter_NNNNNNN/` directories. Total suite: **601 passed, 2 skipped** offline (`pytest -q`, `/tmp/fk` venv). The 2 skips are the long-standing `--spark`-gated live-NIM / pgvector tests.

### Added — `fieldkit.training` v0.5 build-out (Phase B: `convert`)

Second module of the v0.5 `fieldkit.training` build-out, after Phase A's `recipe.TrainRecipe` (commit `bee458d`). Absorbs the two patches that the patent-strategist v3 NeMo lane (Phase 6.5, articles `patent-strategist-bakeoff-unsloth-vs-nemo-framework`) discovered the hard way during session 2026-05-21 — so the next lane doesn't repeat the discovery.

- **`fieldkit.training.HFToMegatron`** — frozen dataclass wrapping `megatron.bridge.AutoBridge` with the YARN-rope-defaults fix baked in. Mirrors `scripts/p65_convert_hf_to_mcore.py`; replaces the hand-written script for any future YARN-rope HF model (DeepSeek-R1-Qwen3, Qwen3 extended-ctx, ...) headed for NeMo training. Lazy-imports `torch` + `megatron.bridge` — module import has no GPU cost and pure-inference dev envs stay clean. Run inside `nvcr.io/nvidia/nemo:26.04.00`; outside that envelope `.run()` raises `ConvertError` with a clear pointer.
- **`patch_yarn_defaults(provider)`** — the load-bearing helper, also exported. Sets `yarn_beta_fast=32.0` / `yarn_beta_slow=1.0` / `yarn_mscale=1.0` / `yarn_mscale_all_dim=0.0` / `yarn_correction_range_round_to_int=True` (from `megatron.core.models.common.embeddings.yarn_rotary_pos_embedding`) on a provider whose YARN fields the bridge left as `None`. Idempotent — re-running after a successful patch is a no-op. Pure-python, offline-testable with a duck-typed `SimpleNamespace`. The `YARN_DEFAULTS` constant is also exposed for inspection.
- **`register_llama_cpp_pretokenizer_hash(...)`** — idempotent string-patcher for llama.cpp's `convert_hf_to_gguf.py`. Inserts a 3-4 line block into the `get_vocab_base_pre` `if chkhsh == "...":` chain so future tokenizers (e.g. DeepSeek-R1-0528-Qwen3-8B) work without waiting for upstream merges. Returns `True` on insertion, `False` if the hash is already present, raises `ConvertError` on malformed inputs or a mis-pointed script. Re-apply after a fresh `git pull` on the llama.cpp checkout. The DeepSeek-R1 case lives in the module as `DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH` so the next caller doesn't have to re-find it.
- **`ConvertError`** — distinct exception class so callers can selectively catch convert-stage failures vs other runtime exceptions.

### Test suite

**+16 new tests** in `tests/test_training_convert.py`:

- `patch_yarn_defaults` — happy path (all five fields patched), non-YARN provider skipped, already-set values preserved, idempotency, missing-attrs handled.
- `register_llama_cpp_pretokenizer_hash` — insertion vs idempotent no-op, preserves existing chain blocks byte-identical, rejects non-hex / short hashes, raises on missing file / missing chain pattern.
- `HFToMegatron` — dataclass shape (frozen, default `torch_dtype='bfloat16'`), `.run()` raises clear `ConvertError` when megatron-bridge is missing (`/tmp/fk` venv path — guarded with `try: import megatron.bridge` so the test is a no-op on a real `nemo-train` env).
- `DEEPSEEK_R1_0528_QWEN3_TOKENIZER_HASH` constant format check.

All pure-python; no torch / megatron-bridge / live llama.cpp checkout needed. Total suite: **563 passed, 2 skipped** offline (`pytest -q`, `/tmp/fk` venv). The 2 skips are the long-standing `--spark`-gated live-NIM / pgvector tests.

### Added — `fieldkit.training` v0.5 build-out (Phase A: `recipe.TrainRecipe`)

First module of the v0.5 build-out — the declarative scaffold every later phase consumes. Captures what `scripts/p65_train_nemo_lora.{py,sh}` previously spread across argparse + bash env vars in a single typed dataclass, so one recipe drives either lane (NeMo or Unsloth) and offline preflight catches bad inputs before any container start.

- **`fieldkit.training.TrainRecipe`** — frozen dataclass capturing backend / base_model / dataset / lora_rank / lora_alpha / lora_target_modules / lora_dropout / lr / warmup_steps / total_train_iters / micro_batch / global_batch / seq_length / save_interval / output_dir / log_interval / extra_env / mode. `validate()` is offline (pure-python, no filesystem touch); `preflight()` adds filesystem-existence checks on output_dir's parent + dataset path. YAML round-trip via `to_yaml` / `from_yaml` works with or without pyyaml (hand-rolled flat-schema fallback so the v0.5 surface installs cleanly in pure-pip envs).
- **`fieldkit.training.lora_target_modules_for_backend(modules, backend)`** — maps HF target-module names (`q_proj` / `k_proj` / `v_proj` / `o_proj` / `gate_proj` / `up_proj` / `down_proj`) to Megatron-Bridge fused names (`linear_qkv` / `linear_proj` / `linear_fc1` / `linear_fc2`) at runtime so one recipe field drives either lane. Idempotent on already-mapped names.
- **`fieldkit.training.MODE_FULL` / `MODE_SMOKE`** — string constants for the recipe's `mode` field; used by `run()` (Phase C) to decide between `runs-smoke/` and `runs-full/` output layout.
- **`fieldkit.training.RecipeError`** — distinct exception class for recipe-stage validation failures.

The pre-existing v0.4.x RL primitives (`WeightDeltaTracker`, `LoraReferenceSnapshot`) continue to re-export from `fieldkit.training` unchanged.

### Test suite (Phase A)

**+39 new tests** in `tests/test_training_recipe.py` — validate / preflight / YAML round-trip / target-module mapping / frozen-enforcement / mode constants. All pure-python; no torch / megatron-bridge / container needed. Total suite at Phase A landing: **547 passed, 2 skipped** offline (`pytest -q`, `/tmp/fk` venv) — up from 507 at v0.4.3.

### Test suite (cross-phase total)

| Phase | New tests | Cumulative | Module |
|---|---|---|---|
| A | +39 | 547 | `recipe.TrainRecipe` + helpers |
| B | +16 | 563 | `convert.HFToMegatron` + pretokenizer registrar |
| C | +38 | 601 | `run` + `merge_and_export` + `standardize_hf_export` |
| D | +56 | 657 | `probe.ReasoningProbe` + `ProbeReport.compare` |
| E | +53 | 710 | `decide.train_backend` + `refresh` |
| **Total** | **+202** | **710 passed, 2 skipped** | `fieldkit.training` surface 7 → 46 `__all__` |

All pure-python (torch / transformers / megatron-bridge / docker lazy-imported, fake-runner injection for shell-out paths). The 2 skips are the long-standing `--spark`-gated live-NIM / pgvector tests, unchanged since v0.4.x. All 46 `__all__` symbols in `fieldkit.training` documented under `audit_docs.py --strict-kwargs`.

### Verified on Spark

The v0.5 build-out was driven from the patent-strategist v3 paired bakeoff (Phase 6.5 of `specs/patent-strategist-v1.md`) — every module exercised against live infra during sessions 2026-05-21 → 2026-05-22:

- **`convert.HFToMegatron` + `patch_yarn_defaults`** — converted `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` HF → Megatron-core inside `nvcr.io/nvidia/nemo:26.04.00`. YARN-rope-defaults landmine fixed in-library.
- **`convert.register_llama_cpp_pretokenizer_hash`** — registered the DeepSeek-R1-0528-Qwen3-8B BPE-pretokenizer hash (`0d75215...` → `qwen35`) into `/home/nvidia/llama.cpp/convert_hf_to_gguf.py`. Subsequent GGUF conversions stable across all 4 quants × 2 lanes.
- **`run` + `merge_and_export` + `standardize_hf_export`** — drove both the NeMo Framework lane (LoRA-SFT inside `nemo-train`, 8h 04m full-train wall) and the Unsloth lane (4-bit QLoRA, 10h 52m wall) end-to-end. Both lanes' LoRA adapters merged to BF16 HF; shard-rename + tokenizer-class fixes baked into the NeMo export (no more post-merge bash patching).
- **`probe.ReasoningProbe.compare(normalize_budget=True)`** — produced Article H's apples-to-apples chain-length headline (NeMo +44% patent-strategic mean chain). The budget-normalization knob excluded qids whose chain exceeded the smaller cap in either lane (Unsloth 1536 vs NeMo 2048) so the metric isn't inflated by the higher-budget side.
- **`decide.train_backend`** — first seed entry `2026-05-22-paired-bakeoff.yaml` shipped in `fieldkit/src/fieldkit/training/data/decide-entries/` (wheel-resident via the new package-data glob). End-to-end smoke green: `train_backend(base_model_family="qwen3-r1-distill", optimize_for="patent_chain_length")` → `nemo`.

### Artifacts

Phase 6.5 paired-bakeoff outputs (live on HuggingFace under `Orionfold/`):

- [Orionfold/patent-strategist-v3-unsloth-GGUF](https://huggingface.co/Orionfold/patent-strategist-v3-unsloth-GGUF) — Q4_K_M / Q5_K_M / Q6_K / Q8_0
- [Orionfold/patent-strategist-v3-nemo-GGUF](https://huggingface.co/Orionfold/patent-strategist-v3-nemo-GGUF) — Q4_K_M / Q5_K_M / Q6_K / Q8_0
- [Orionfold/patent-strategist-v3-unsloth](https://huggingface.co/Orionfold/patent-strategist-v3-unsloth) — BF16
- [Orionfold/patent-strategist-v3-nemo](https://huggingface.co/Orionfold/patent-strategist-v3-nemo) — BF16

### Articles in this release

- `articles/patent-strategist-bakeoff-unsloth-vs-nemo-framework/` — Article H, the marquee. Drives every Phase A–E module: `TrainRecipe` owns the lane recipes; `convert` carries the YARN + pretokenizer fixes; `run` + `merge_and_export` ran both lanes; `probe.compare(normalize_budget=True)` produced the +44% chain-length headline; `decide.train_backend`'s seed entry is the first row in the decide corpus.
- `articles/unsloth-on-the-spark-when-train-peak-equals-base-peak/` — Unsloth feasibility companion to the bakeoff (`fieldkit.training.run` drove the Unsloth lane).
- `articles/fine-tune-data-prep-decisions-on-spark/` — patent-strategist v2 corpus diagnosis (data-layer; doesn't depend on the v0.5 surface but ships in the same window).
- `articles/becoming-a-medical-curator-on-spark/` — vertical 4 medical card (uses `fieldkit.publish`; pre-v0.5 surface).

## [0.4.3] — 2026-05-17

### Added — `fieldkit.eval` patent-strategist scorer build-out (T6)

Four new scorers in `fieldkit.eval` round out the `format='patent-strategist'` branch landed in v0.4.2 (T4) and the `mcq_letter` promotion (T5), per `specs/patent-strategist-v1.md` §3.3:

- **`patent_claim_validity(predicted, expected, *, judge, rubric=None)`** — PatentScore-methodology 7-dim claim-validity scorer (novelty / non-obviousness / written-description / enablement / indefiniteness / subject-matter-eligibility / dependent-claim-structure). LLM-judge backed; caller supplies a `Judge(client=..., rubric=RUBRIC_PATENT_CLAIM_VALIDITY)`. Per-row `rubric` dict (e.g. `cited_prior_art`, `claim_type`) is rendered into a sorted, deterministic `Hints:` block fed to the judge as context. PatentScore methodology only — no data reuse from the cited paper (license unclear).
- **`office_action_argument(predicted, expected, *, judge, rubric=None)`** — 4-dim office-action-response scorer (rejection-type identification, statutory citation accuracy, argument structure, persuasiveness). Same `Judge`-wrapping shape; per-row hints like `rejection_type`, `required_citations`, `claim_count`, `relies_on_official_notice` flow through the `Hints:` block.
- **`irac_structure(predicted, expected="")`** — deterministic 4-checklist scorer for Patent-Bar-style IRAC responses. One regex per component (Issue / Rule / Application / Conclusion); returns `{0.0, 0.25, 0.5, 0.75, 1.0}` based on how many fire. Tolerant patterns — markdown headings, all-caps section labels, transition prose ("Whether…", "Under 35 USC 103…", "Here…", "Therefore…") all count. False positives are far less harmful than false negatives at quarter-granularity. The only T6 scorer that needs no network, so it's the one wired end-to-end through `VerticalBench` in the integration test.
- **`prior_art_relevance(predicted, expected) -> float`** — Spearman ρ on ranked prior-art lists, returning just the rho per spec §3.3. Tolerant parser accepts JSON arrays (`'["a","b","c"]'`), comma-separated, or newline-separated (with `1.`, `1)`, `- `, `* ` prefixes stripped) as well as `list[str]` directly. Missing-from-pred gold items get worst-rank padding so omissions still penalize. The paired-rank vectors are re-rankified before correlation so positional gaps from dup-skipping or padding collapse to contiguous ranks — without this, `["a","a","b","c"]` vs `["a","b","c"]` would yield ρ≈0.98 instead of the intuitive 1.0. **`prior_art_relevance_full`** returns the same rho plus an `mse_likert` field (populated only when both sides parse as numeric Likert vectors) and `n`, packaged as the frozen `PriorArtRelevanceResult` dataclass.

### Added — rubric markdown bundled in the wheel

- **`fieldkit/src/fieldkit/eval/rubrics/{patent_claim_validity,office_action_argument}.md`** — system-prompt markdown shipped alongside the module. Loaded lazily via the new **`load_rubric(name)`** helper (and exposed via the **`RUBRIC_PATENT_CLAIM_VALIDITY`** / **`RUBRIC_OFFICE_ACTION_ARGUMENT`** module constants for the common case). `[tool.hatch.build.targets.wheel].include` extended with `src/fieldkit/eval/rubrics/*.md` so the markdown lands in the wheel.

### Added — `fieldkit.eval.vertical` live-callable dispatch

- **`PATENT_STRATEGIST_SCORER_FNS: dict[str, Callable[..., float]]`** — companion to the existing string-keyed `PATENT_STRATEGIST_SCORERS` map. Resolves the four T6 scorers + the promoted `mcq_letter` to live functions (skips the two `judge_rubric` slots ("C", "E") which are open-ended `Judge.grade(...)` calls without a single named scorer fn). Drift-detection test asserts every fn's `__name__` matches the matching string-map entry.

### Test suite

**+93 new tests** across three new test files + the existing vertical-bench test class:

- `tests/eval/test_irac_structure.py` — perfect / partial / per-component-detector coverage; quarter-granularity parametrize; whitespace-only / empty / expected-arg-ignored edges.
- `tests/eval/test_prior_art_relevance.py` — perfect / reversed / partial-overlap; string-parsing variants (JSON, comma, newline-numbered, bullet, paren-numbered); Likert MSE branch (perfect, off-by-one, length-mismatch fallback, non-numeric); dataclass shape (frozen, three fields); the known-value `n=4` swap (ρ=0.8) plus the dup-skip test that drove the `_rankify`-on-paired-vectors fix.
- `tests/eval/test_judge_backed_scorers.py` — `load_rubric` round-trip + missing-file error; `_format_rubric_hints` (empty / scalar / list-bullet / sorted-determinism / nested-dict JSON); both judge-backed scorers wired against a `_FakeJudge` fixture (no network) covering happy path, `None`-score fallback to `0.0`, rubric→`Hints:` threading, empty-reference collapse to `None`; signature-introspection tests ensuring `judge` and `rubric` stay keyword-only so `VerticalBench.scorer_kwargs` plumbing works.
- `tests/test_vertical_bench.py::TestPatentStrategistFormat` — 3 new tests: `PATENT_STRATEGIST_SCORER_FNS` resolves each key to the expected callable; name-map vs fn-map drift assertion; full end-to-end `VerticalBench.run` exercising `irac_structure` over a 2-row JSONL with one perfect and one half-formed IRAC response (mean accuracy = 0.75).

Total suite: **507 passed, 2 skipped** offline (`pytest -q`, `/tmp/fk` venv). The 2 skips are the long-standing `--spark`-gated live-NIM / pgvector integration tests.

### Articles in this release

- `articles/becoming-a-patent-strategist-on-spark/` — patent-strategist v1.0 article (W3 publish target per spec §1 deliverables). T6's scorer build-out is the load-bearing dependency for the article's bench-comparison numbers; v0.4.3 is the version the article will pin against.

## [0.4.2] — 2026-05-15

Patch release. Two card-rendering polish lifts on `fieldkit.publish` driven by the 2026-05-15 cyber-vertical cycle (`Orionfold/SecurityLLM-GGUF`, the third vertical card on this surface — zero fieldkit source changes between Saul / cyber, the v0.4.1 publishing surface generalized exactly as designed). Both lifts are additive (one new `ModelCard` field already shipped on `main` in `ff1b92f`; one new `ArtifactManifest` field added here). No new modules, no new public classes, no breaking changes — purely a tightening pass.

### Added — `fieldkit.publish` card-rendering polish

- **`ModelCard.llama_cpp_example_prompt: Optional[str]`** — new field. Threads through `publish_quant(..., llama_cpp_example_prompt=...)` and from a duck-typed report's `.llama_cpp_example_prompt` attribute. The default `## How to run` body's `llama-cpp-python` snippet now uses this string for the user-message; when omitted it falls back to a neutral `"Summarize the key idea in one paragraph."` placeholder instead of the previously-hardcoded `"Explain working capital."` (which leaked into the legal + cyber vertical cards on first push). Multi-line MCQ-shaped prompts are JSON-escaped (`\n`) so the snippet stays single-line + valid Python — caller passes the raw prompt, the renderer handles escaping.
- **Side fix:** the previous renderer rendered the hardcoded finance prompt on every vertical card; the cyber + legal cards on HF were patched out-of-band on 2026-05-15 (commits `365dfe2`, `0824439`). Going forward, every `publish_quant` call should pass `llama_cpp_example_prompt=...` matching the article's "Using this release" section, per `[[feedback_customer_link_audit]]`.
- **`ArtifactManifest.recommended_variant: Optional[str]`** — new field. Was already on `ModelCard` (so the README's How-to-run snippets template against the article's pick) but did NOT flow into the `<slug>.yaml` manifest, so the destination catalog couldn't see the article's narrative choice and ran its own rank-avg picker instead. `publish_quant` now threads `recommended_variant` into both surfaces — the HF README badge and the destination "Sweet spot" badge stay in sync from one kwarg. Mac added the matching `recommended_variant: z.string().optional()` to its artifacts schema in PR #6 (`mac-sweep/2026-05-15-cyber-vertical`) and pinned cyber's catalog `Q4_K_M` manually; source `src/content.config.ts` now mirrors that field for forward-compat. Motivated by cyber-vertical (2026-05-15): `Q4_K_M` topped CyberMetric at 40% but its worst-in-class perplexity dragged its rank-avg down, so without the override the picker selected `Q5_K_M`.

### Test suite

**+3 new tests:** `test_artifact_manifest_carries_recommended_variant_when_set` + `test_artifact_manifest_omits_recommended_variant_when_unset` (round-trip + elision on the new manifest field) and `test_publish_quant_threads_recommended_variant_into_card_and_manifest` (kwarg threads to both surfaces via `publish_quant`). Total: **378 passed, 3 skipped** offline (`pytest -q`). The 3 skips are the two `--spark`-gated live-integration tests + the `torch`-import skip in `test_training.py` (CPU-only venv).

### Articles in this release

- [`becoming-a-cyber-curator-on-spark`](https://ainative.business/field-notes/becoming-a-cyber-curator-on-spark/) — third Orionfold quant card. Drives both lifts: surfaces the `llama_cpp_example_prompt` leak (cyber's MCQ prompt would have shipped as "Explain working capital." otherwise) and motivates `ArtifactManifest.recommended_variant` (the destination's rank-avg picker would have surfaced `Q5_K_M` instead of `Q4_K_M`).

### Verified on Spark

- **Live HF push:** `Orionfold/SecurityLLM-GGUF` (5 GGUF variants + README, ~26 GB) shipped 2026-05-15 via the same `publish_quant(dry_run=False)` path as Saul and finance-chat. Zero source changes in `fieldkit.publish` between Saul (v0.4.1) and cyber (the cycle that drove this v0.4.2 patch) — the surface generalized as designed across three verticals.

## [0.4.1] — 2026-05-14

Patch release. The `fieldkit.eval.VerticalBench` overlay introduced in v0.4.0 needed two kwargs to score FinanceBench correctly (open-book context-prepend) and to bound a JSONL slice (subset filter on `question_type`). Both lifts came out of the 2026-05-13 V1 attempt on `AdaptLLM/finance-chat` (0/50 closed-book vs. 14–18%/50 open-book on the same JSONL) and the 2026-05-14 legal-curator scoring run on `Equall/Saul-7B-Instruct-v1`. The two scripts under `scripts/g3_*` that carried duplicated loaders now call into the package surface. No new modules, no new public classes — additive kwargs only.

### Added — `fieldkit.eval.VerticalBench` open-book mode

- **`VerticalBench.from_jsonl(..., open_book=...)`** — new kwarg. When `True`, FinanceBench rows have their `evidence[*].evidence_text` prepended to the question (templated as "Context from <doc>: …\n\nQuestion: …\n\nAnswer with just the numeric value.") so the model sees the 10-K excerpt the gold answer was derived from. Default `None` auto-resolves to `True` for `financebench` and `False` for `legalbench` / `generic` — the right defaults per benchmark convention. Lifts inline `_load_finbench_open_book` helpers from `scripts/g3_preflight_bench.py` and `scripts/g3_measure_variants.py` into the package surface; both scripts now call `VerticalBench.from_jsonl(open_book=True, subset=…)` instead of carrying duplicated loaders. The 2026-05-13 V1 attempt on AdaptLLM/finance-chat scored 0/50 closed-book and 14–18%/50 open-book on the same JSONL — open-book is the load-bearing flag for FinanceBench scoring.
- **`VerticalBench.from_jsonl(..., subset=...)`** — new kwarg. FinanceBench-only convenience filter on the `question_type` column. Drops non-matching rows before the loader hits the `limit` cap, so callers can score the `metrics-generated` subset with `limit=50` and get 50 metrics-generated questions (not 50 mixed rows of which N are metrics-generated).

### Test suite

**+8 new tests** on `TestOpenBook` in `tests/test_vertical_bench.py` covering: auto-default for financebench, explicit `False` keeps closed-book, missing-evidence falls back to closed-book, legalbench / generic are no-ops, list-of-strings evidence shape, subset filter, subset × limit composition. Total: **375 passed, 3 skipped** offline (`pytest -q`). The 3 skips are the two `--spark`-gated live-integration tests + the `torch`-import skip in `test_training.py` (CPU-only venv).

### Articles in this release

- [`becoming-a-legal-curator-on-spark`](https://ainative.business/field-notes/becoming-a-legal-curator-on-spark/) — second Orionfold quant card, swaps FinanceBench for a curated 5-task LegalBench subset. Drives the `subset` kwarg's first non-finance use (LegalBench tasks via `legalbench` format) and validates that the `open_book` default-off branch is correct for LegalBench JSONLs.

### Verified on Spark

- **Live HF push:** `Orionfold/Saul-7B-Instruct-v1-GGUF` (5 GGUF variants + README, ~37 GB) shipped 2026-05-14 via the same `publish_quant(dry_run=False)` path the finance-chat card used a week earlier. Zero source changes in `fieldkit.publish` between the two pushes — the v0.4.0 surface generalized as designed.

## [0.4.0] — 2026-05-14

Fourth public release. Two new top-level modules (`fieldkit.publish` + `fieldkit.quant`) for the G3 GGUF / Quantization Publisher pick (MTBM Pick #1 per `ideas/mtbm-use-cases.md` §6), the v0.4.x **vertical-curator overlay** on `fieldkit.eval` (`VerticalBench`), and post-dry-run card-rendering fixes that landed the first live HF push (`Orionfold/finance-chat-GGUF`). The two new modules together unlock most of Cluster G; this cut implements the GGUF critical path and stubs the other quant formats with named entry points pointing at the v0.5+ roadmap.

### Added — `fieldkit.publish` (new module)

HuggingFace Hub adapter + auto model card builder from `fieldkit.lineage`. Three public surfaces:

- **`fieldkit.publish.ModelCard`** — frontmatter + body builder. Renders the canonical card every Orionfold artifact gets: YAML frontmatter (license, library_name, base_model, pipeline_tag, tags, model_creator), a title + elevator, a **Spark-tested** block (per-variant perplexity + tok/s + thermal envelope), a variants table, **How to run** (`ollama pull` + `from_pretrained` snippets), an optional **Lineage** block (rendered from a `fieldkit.lineage.LineageStore` if provided), a **Methods** backlink to `ainative.business/field-notes/<slug>/`, and a footer attributing the publication to Orionfold LLC.
- **`fieldkit.publish.ArtifactManifest`** — frozen dataclass for the `src/content/artifacts/<slug>.yaml` Phase-2 sync record (per memory `project_artifact_manifests_phase2`). `to_yaml()` emits via a hand-rolled stdlib emitter so the module has no runtime YAML dep. The source repo writes one of these per push; the Mac destination renders `/artifacts/<kind>/` catalog pages from `getCollection('artifacts')`.
- **`fieldkit.publish.HFHubAdapter`** — lazy-`huggingface_hub` wrapper. Defaults to `dry_run=True` (stages files on disk, logs the would-be calls, no network). Flip `dry_run=False` to push via `HfApi().upload_folder(...)`. Token resolution order: explicit `token=` → `HF_TOKEN` env → cached login. The dry-run path is fully testable offline.

Plus an orchestrator: **`fieldkit.publish.publish_quant(...)`** — one-line caller that ingests a `QuantReport`-shaped object (duck-typed; produced by `fieldkit.quant.quantize_gguf`), renders the card, writes the manifest, stages the variant files, and pushes (or dry-runs) the HF commit.

Branded constants: `ORIONFOLD_BRAND = "Orionfold LLC"`, `ORIONFOLD_HF_HANDLE = "Orionfold"` (was `ORIONFOLD_HF_ORG = "orionfoldllc"` until 2026-05-14, when publishing moved to the existing user-account handle — Bartowski-shape personal handle precedent). Per the 2026-05-12 HANDOFF Q3 decision: Orionfold LLC is the parent brand for all AI-artifact publishing surfaces; repo names follow the Bartowski shape (`Orionfold/<model>-GGUF`, `Orionfold/<model>-LoRA`). `ORIONFOLD_HF_ORG` is retained as a back-compat alias pointing at the new constant; will be dropped at the next major cut.

### Added — `fieldkit.quant` (new module)

Quantization dispatcher. GGUF path implemented; AWQ/GPTQ/EXL3/MLX/NVFP4 declared as named stubs pointing at the roadmap.

- **`fieldkit.quant.quantize_gguf(...)`** — wraps `llama.cpp/convert_hf_to_gguf.py` + `llama-quantize` to emit one GGUF file per requested variant (canonical Orionfold set: `Q4_K_M`, `Q5_K_M`, `Q6_K`, `Q8_0`, `F16`). Auto-derives F16 from a HF Transformers checkpoint when the source isn't already a GGUF. `dry_run=True` enumerates the would-be subprocess commands into `report.notes` without invoking them — used by tests and CI.
- **`fieldkit.quant.measure_perplexity_gguf(...)`** — wraps `llama-perplexity`. Parses output via `parse_perplexity_output()` which recognizes the standard `Final estimate: PPL = N.NNN` shape and the lowercase `perplexity = N.NNN` fallback. Returns `None` on parse failure (cards ship without a perplexity column if measurement was skipped).
- **`fieldkit.quant.measure_tokens_per_sec_gguf(...)`** — wraps `llama-bench`. Parses output via `parse_llama_bench_output()` for `tg` (text-gen, default) or `pp` (prompt-process) tok/s.
- **`fieldkit.quant.ThermalProbe`** — pure-stdlib `nvidia-smi` poll loop. Reports sustained-load minutes before throttle, per the 2026-05-12 HANDOFF Q9 decision to publish duty-cycle limits on every Orionfold card.
- **`fieldkit.quant.LlamaCppPaths`** — locator for `llama-quantize` / `llama-perplexity` / `llama-bench` / `convert_hf_to_gguf.py`. Env defaults: `LLAMA_CPP_BIN` directory, `LLAMA_CPP_CONVERT` script path. Override any field directly.
- **`fieldkit.quant.QuantReport`** — canonical dataclass output. The contract `fieldkit.publish.publish_quant()` consumes.
- **`fieldkit.quant.quantize_awq` / `quantize_gptq` / `quantize_exl3` / `quantize_mlx` / `quantize_nvfp4`** — named entry-point stubs. Raise `NotImplementedError` with a one-liner pointing at `ideas/mtbm-use-cases.md` §7. Locks the v0.4 public surface so v0.5+ implementations slot in without an API break.

### Added — `fieldkit.eval.VerticalBench` (v0.4.x — vertical-curator overlay)

Lightweight JSONL-loader wrapper around `fieldkit.eval.Bench` for vertical-domain accuracy scoring (FinanceBench / LegalBench / SemEval / generic). Drives the **vertical-curator pivot** announced 2026-05-13 (HANDOFF §2 + `ideas/mtbm-use-cases.md` §6 Pick #1.b + §8.5.1): every Orionfold quant card now ships with a vertical-domain accuracy axis, not just wikitext perplexity. Lives in `fieldkit/src/fieldkit/eval/vertical.py`; re-exported at the package root for `from fieldkit.eval import VerticalBench`.

- **`fieldkit.eval.VerticalBench`** + **`VerticalQA`** — bench shape, JSONL loader, scorer plumbing. Accepts any `Callable[[str], str]` as the model function so subprocess (`llama-cli`), in-process (`llama-cpp-python`), or NIM-backed scoring all slot in. Per-call latency aggregates alongside accuracy + refusal via the underlying `Bench`.
- **`fieldkit.eval.VerticalBench.from_jsonl(path, format='auto', ...)`** — auto-detects `financebench` / `legalbench` / `generic` JSONL shapes from the first row's field signature. Per-row metadata (company, doc_period, question_type, task) flows into per-call tags for slice-by aggregation downstream.
- **Scorers** — `exact_match`, `contains`, `numeric_match` (with configurable `rel_tolerance`, default 1% — FinanceBench convention). The bench picks `numeric_match` by default for FinanceBench-shape JSONL, `exact_match` for LegalBench-shape.

### Added — license + How-to-run defaults on `fieldkit.publish` (v0.4.x — `Orionfold/finance-chat-GGUF` dry-run found two card bugs)

- **`ModelCard.license`** is now reachable from `publish_quant(..., model_license=...)` (and the duck-typed `quant_report.model_license` attribute). Previously the kwarg didn't exist and every card defaulted to `apache-2.0` — wrong for any Llama / Gemma / Qwen / CC-BY-NC base. AdaptLLM/finance-chat now correctly publishes with `license: llama2`.
- **`ArtifactManifest.model_license`** mirrors the same value into the Astro manifest under `license.model:`. Astro Zod schema (`src/content.config.ts`) extended with `license.model: z.string().optional()` so destination catalog pages and HF badges stay in sync. The `license.tier:` field (commercial-distribution tier — `free` / `pro`) stays distinct from this upstream-license field.
- **`ModelCard.hf_repo`** + **`ModelCard.chat_format`** + **`ModelCard.recommended_variant`** — three new fields that drive an auto-rendered default `## How to run` body. Before this fix, cards with no explicit `ollama_pull_handle` / `transformers_snippet` rendered an empty section header (the second finance-chat bug). The new renderer auto-builds three code blocks templated from `hf_repo` + a featured variant: `huggingface-cli download`, `llama-server` (OpenAI-compatible serve), and `llama-cpp-python` (in-process, threading `chat_format` if set). When all three new fields are absent + no explicit handle/snippet supplied, the section is omitted entirely (no more empty headers).
- **`publish_quant(..., model_license=, chat_format=, recommended_variant=)`** kwargs added — orchestrate all three through to card + manifest. Same duck-typed fallback through `quant_report` attributes.
- **`scripts/g3_build_first_quant.sh`** — `MODEL_LICENSE` / `CHAT_FORMAT` / `RECOMMENDED_VARIANT` env knobs added with case-statement overrides (`AdaptLLM/finance-chat → llama2 + llama-2`). Default `MODEL_LICENSE=apache-2.0` + `RECOMMENDED_VARIANT=Q5_K_M` for greenfield runs.
- **`scripts/g3_push_first_quant.py`** (new) — one-shot live-push helper that reuses the existing dry-run stage (no 32 GB re-copy via `publish_quant(dry_run=False)`); calls `HFHubAdapter.push_folder()` directly. Bakes in xet-safety env (`HF_HOME=/home/nvidia/data/.hf-cache` + `HF_HUB_DISABLE_XET=1`) per the Spark-side `~/.cache/huggingface/` permission landmine; sources `HF_TOKEN` from `.env.local` (chmod 600).
- **+11 tests** (full suite: 379 passed, 2 skipped offline). Covers: model_license override flow, default apache-2.0 fallback, default GGUF How-to-run rendering, `recommended_variant` override, `hf_repo`-less skip-section behavior, manifest `license.model` emission.

### Added — vertical-eval surface on `fieldkit.publish`

`ModelCard` + `ArtifactManifest` + `publish_quant(...)` extended to thread per-variant vertical-eval scores through to the rendered card and the Phase-2 sync manifest:

- **`ModelCard.vertical_eval: dict[str, float]`** + **`ModelCard.vertical_eval_name: str`** — when set, the **Spark-tested** block renders a 5-column table (Variant / Size / Perplexity / tok/s / *Vertical-eval-name*) instead of the 4-column default, and the introductory copy switches from "measurement triple" to "measurement quad". Accuracy values render as percentages (`62.0%`). Cards without vertical eval render identically to v0.4.0 — backwards-compatible.
- **`ArtifactManifest.vertical_eval` + `vertical_eval_name`** — written into the YAML manifest under the same key names. Mac destination Zod schema (`src/content.config.ts`) extended to accept both. Manifests without vertical eval skip the field entirely.
- **`publish_quant(..., vertical_eval=, vertical_eval_name=)`** — explicit kwargs override whatever the duck-typed `quant_report` carries. Useful when scoring happens out-of-band from quantization (the canonical path on Spark: quantize 5 variants → measure each variant via `g3_measure_variants.py`, which calls `VerticalBench.run(llama_cli_fn)` and then feeds the resulting accuracy dict back into `publish_quant`).

### Schema changes

- `src/content.config.ts` — `FIELDKIT_MODULES` extended to include `'quant'` and `'publish'` in canonical order (`capabilities, nim, rag, eval, training, lineage, quant, publish, cli`).
- `src/content.config.ts` — new `artifacts` Astro collection (Phase 2 sync contract). Loads YAML manifests from `src/content/artifacts/*.yaml`; Zod schema mirrors `fieldkit.publish.ArtifactManifest`. `ARTIFACT_KINDS` enum exposed alongside `FIELDKIT_MODULES` for downstream filtering. `src/content/artifacts/` directory created (empty + `.gitkeep`); first manifest will land when the first quant ships.
- `src/content.config.ts` — `artifacts` schema extended with optional `vertical_eval: Record<string, number>` + `vertical_eval_name: string` (vertical-curator pivot 2026-05-13).

### Test suite

**130 new tests** across `tests/test_publish.py` (42, +16 from v0.4 scaffold incl. +11 for the model_license + How-to-run defaults fix), `tests/test_quant.py` (37), and `tests/test_vertical_bench.py` (39, new file), plus targeted regression coverage. Total: **379 passed, 2 skipped** offline (`pytest -q`). The 2 skips are `--spark`-gated live integration tests (chat NIM + pgvector); the v0.3 torch module-level skip has been resolved by lazy-importing torch only inside the training entry points. All new tests run offline — `dry_run=True` paths for `HFHubAdapter`, `publish_quant`, and `quantize_gguf` exercise the full code path without `huggingface_hub`, llama.cpp binaries, or `nvidia-smi` available. `VerticalBench` tests run without a model — `model_fn` is a callable, so a plain `lambda` exercises the full scoring + bench-aggregation path.

### Articles in this release

- [`becoming-a-gguf-publisher-on-spark`](https://ainative.business/field-notes/becoming-a-gguf-publisher-on-spark/) — G3 v0 anchor article. 3,388 words; documents the five-variant `Orionfold/finance-chat-GGUF` release end-to-end (Spark-tested perplexity / tok/s / sustained-load minutes / FinanceBench accuracy across F16, Q8_0, Q6_K, Q5_K_M, Q4_K_M) plus the V0 preflight-bench gate and the V1 chat-vs-continued-pretrain lesson. `hf_url:` frontmatter threads the live HF receipt onto the article.

### Verified on Spark

- **Live HF push:** `Orionfold/finance-chat-GGUF` shipped 2026-05-14 at <https://huggingface.co/Orionfold/finance-chat-GGUF> — 5 GGUF variants + auto-rendered README in 1h 57min. Repo returns HTTP 200, all 6 files present. `publish_quant(dry_run=False)` path exercised end-to-end.
- **Five-variant measurement card** (F16 / Q8_0 / Q6_K / Q5_K_M / Q4_K_M) with the four Spark-tested axes — perplexity (wikitext-2), tg + pp tok/s (`llama-bench`), sustained-load minutes (`ThermalProbe` via `nvidia-smi`), and FinanceBench accuracy (n=50, `numeric_match`, open-book) — all produced via `fieldkit.quant.measure_*` + `fieldkit.eval.VerticalBench.run(...)` on GB10.

### Deferred to v0.5

- `fieldkit.image-lora` + `fieldkit.civitai` — Pick #2 (G9) prep. Deferred per the 2026-05-12 HANDOFF Q10 decision to sequence G3 → G9 rather than parallelize. Will land once G3 v0 proves the `fieldkit.publish` infra.
- Non-GGUF formats in `fieldkit.quant` (AWQ, GPTQ, EXL3, MLX, NVFP4). The G3 v0 niche-positioning is Nemotron-family GGUFs with the Spark-tested layer; other formats are pure surface-area expansion and can wait for an audience signal.

## [0.3.0] — 2026-05-11

Third public release. One new top-level module (`fieldkit.lineage`) lifted from the [auto-research-loop-on-spark article](https://ainative.business/field-notes/auto-research-loop-on-spark/) — the portable part of cxcscmu's *Auto-Research-Recipes* harness, decomposed into a pure-stdlib substrate any harness on the Spark can write into.

### Added — `fieldkit.lineage` (new module)

The portable part of cxcscmu's *Auto-Research-Recipes* harness, extracted into a top-level submodule. The case for the primitive is in the released `pg_ablation_lineage_on` vs `pg_ablation_lineage_off` runs: same agent, same prompt template, same 201-trial budget on Parameter Golf — only whether the agent's session prompt includes the rendered lineage block differs. With lineage on: 16 keeps (8.0%), 38 eval-budget overruns. Without: 3 keeps (1.5%), 123 eval-budget overruns. **5.3× more keeps · 3.2× fewer wall-wastes**, with no model change, no compute change, no prompt-template change. ([extract from #auto-research-loop-on-spark])

The new module is pure-stdlib (no torch, no numpy) — ~200 LOC of public surface, ~330 LOC including docstrings + renderer helpers.

- **`fieldkit.lineage.FailureLabel`** — 10-class string enum (`keep`, `discard`, `crash`, `eval_budget_overrun`, `train_budget_overrun`, `size_blocked`, `preflight_crash`, `harness_abort`, `disqualified`, `baseline`). `.value` round-trips byte-identically to cxcscmu TSVs. The `is_informational` property is the cxcscmu `_QUARANTINED_STATUSES` rule as a method — returns `False` only for `harness_abort` (bookkeeping kills); every other class carries usable signal for the next agent.
- **`fieldkit.lineage.Trial`** — frozen dataclass for one TSV row. 17 fields in canonical order. `core_metric` is the task-agnostic primary metric (so the module works for Parameter Golf, NanoChat-D12, CIFAR, and any future task in the arc); `val_bpb` is preserved alongside for direct interop with cxcscmu-shaped data. `Trial.header()` / `Trial.to_row()` / `Trial.from_row(dict)` give exact TSV round-trip — `None` floats serialize as empty strings (matches cxcscmu convention).
- **`fieldkit.lineage.LineageStore(root, *, lower_is_better=True)`** — append-only TSV writer at `root/results.tsv` with `fcntl.flock` exclusive locking across header + row writes (concurrent specialists can write without interleaving). Read-side accessors: `all_trials()`, `latest(n)`, `best()`, `chain_to(exp_id)` (walks `parent_exp` pointers root-first, terminates on missing or self-referential parents), and `render_prompt(...)` — the deterministic Markdown emitter.
- **`fieldkit.lineage.LineageSnapshot`** — frozen dataclass returned by `render_prompt`. Carries the rendered Markdown string plus the underlying structured data (`current_best`, `chain_to_best`, `top_k_leaderboard`, `recent_n_activity`, `last_m_with_full_hypothesis`) so callers can index in without re-parsing.
- **`fieldkit.lineage.RecipeEdit`** — pairs a keep trial with its workdir `snapshot_path` and `parent_snapshot_path`. `diff()` computes a unified diff of every text file in the snapshot vs the parent (binary files elide with a `Binary files ... differ` marker); baseline trials with no parent return an empty diff.

Rendered Markdown output mirrors cxcscmu's `release_artifacts/example_lineage_pg_lineage_on_arch.txt` shape: header line + `## LEADERBOARD.md` (current best + top-K kept table) + `## KNOWLEDGE.md` (current-best lineage as a nested `└─` chain + recent-activity table + last-M detailed entries). Determinism is tested — same TSV state in produces byte-identical Markdown across calls.

### Test suite

**29 new tests** for `fieldkit.lineage` (`tests/test_lineage.py`): `FailureLabel` value parity + `is_informational` predicate + 10-class enum surface lock; `Trial` round-trip via TSV; `LineageStore` append / latest / best / `chain_to` correctness across linear and branched topologies; `render_prompt` determinism, top-K filtering, chain rendering with `← BEST` marker; `RecipeEdit.diff()` against parent snapshots including new-file detection.

Total fieldkit test count: **249 passed, 3 skipped** offline (`pytest -q`) — the 3 skips are 1 module-level torch importorskip in `test_training.py` and 2 `--spark`-gated live integration tests.

### Articles in this release

- [`auto-research-loop-on-spark`](https://ainative.business/field-notes/auto-research-loop-on-spark/) — anchor article. Walks the 17-column schema, the 10-class enum semantics, and the cxcscmu lineage ablation that proves the primitive's value.

### Schema change — `FIELDKIT_MODULES`

`src/content.config.ts` extended to include `'lineage'` in the `FIELDKIT_MODULES` tuple (order: `capabilities, nim, rag, eval, training, lineage, cli`). Required so articles can declare `fieldkit_modules: ['lineage']` in their frontmatter.

[extract from #auto-research-loop-on-spark]: https://github.com/manavsehgal/ai-field-notes/tree/main/articles/auto-research-loop-on-spark

## [0.2.0] — 2026-05-05

Second public release. One new module (`fieldkit.training`) plus four extensions to the v0.1 `fieldkit.eval` surface, all lifted from articles in [ai-field-notes](https://ainative.business/field-notes/) — primarily the `clawgym-on-spark` and Frontier Scout arcs. The `fieldkit.agents` and `fieldkit.inference` modules originally targeted for v0.2 are deferred to v0.3+ because their public APIs need a second article's use case to lock in (see "Deferred to v0.3+" below).

### Added — `fieldkit.training` (new module)

Fine-tuning primitives for any RL or SFT loop on the DGX Spark's unified-memory GB10. Both classes use lazy `torch` imports so `import fieldkit.training` costs nothing in environments that don't run training.

- **`fieldkit.training.WeightDeltaTracker`** — pre/post snapshot of trainable params with L2 and `max|Δ|` reporting. Sanity-check that any fine-tuning step actually moves weights — the first time someone debugs "why didn't my LoRA update?" they'll wish for this. Source: `articles/clawgym-on-spark/scripts/grpo_train.py` (`--check-weight-delta` block). ([extract from #clawgym-on-spark-grpo])
- **`fieldkit.training.LoraReferenceSnapshot`** — CPU-resident snapshot of a peft adapter's LoRA tensors with a context manager that swaps the snapshot into the live model for one no-grad forward pass and restores trainable weights on exit. Two construction modes: snapshot from current policy at step start (online) vs. `from_disk(adapter_dir)` for a fixed reference (classic GRPO fixed-SFT-init reference, with the safetensors `.<adapter_name>.weight ↔ .weight` key transform peft 0.19+ requires). Solves a real bug: peft 0.19's `load_adapter(..., is_trainable=False)` crashes with `KeyError` under `device_map="auto"` whenever the GPU has anything else resident — peft's offload-detection over-triggers on Spark unified memory. The CPU-snapshot/swap dance sidesteps the offloader entirely. Source: `articles/clawgym-on-spark/scripts/grpo_train.py` (`--reference-adapter` + snapshot/swap blocks). ([extract from #clawgym-on-spark-grpo])

### Added — extends `fieldkit.eval`

Four new primitives that extend the v0.1 eval surface (`Bench`, `Judge`, `Trajectory`, `is_refusal`) with programmatic grading, code-bench pass@k, agent-loop schemas, and ablation comparison support.

- **`fieldkit.eval.AssertionGrader`** — pure-function grader over five file-system assertion primitives (`file_exists`, `file_not_exists`, `file_unchanged`, `file_contents_contain`, `file_contents_match_regex`). Accepts either a SynthTask-shaped dict (auto-derives `seed_files` from `workspace_seed.files`) or a bare list of assertion dicts, so the grader stays usable without coupling to the deferred `fieldkit.agents.SynthTask` shape. Sibling to `Judge` — programmatic verification where it applies. Source: `articles/clawgym-on-spark/scripts/grader.py`. ([extract from #clawgym-on-spark])
- **`fieldkit.eval.PassAtK`** + **`pass_at_k_estimator`** — verifier-loop primitive: per-task grader + `n`-sample iterator → `pass@1`, `pass@k` via the unbiased estimator (Chen et al. 2021). Decoupled from the model — caller supplies pre-generated samples + a grader callable, `PassAtK` aggregates. Two entry points: `score(problems, samples, grader)` for fresh runs and `from_rows(rows)` for offline pass@k math against pre-graded `(task_id, n, passed)` tuples. Tested on HumanEval + AIME 2024 across baseline vs. ESamp modes. Source: `articles/runtime-frontier-six-patches-on-spark/scripts/passatk_a2.py`. ([extract from #pass-at-k-after-the-seventh-patch])
- **`fieldkit.eval.AgentRun`** + **`TurnDetail`** + **`summarize_agent_runs`** — per-question, per-turn schema for any third-party agent bench. Default constructor handles the AutoResearchBench JSONL shape (`input_data.arxiv_id`, `inference_results[0].turn_details/total_time/...`); `from_record(...)` accepts field-name overrides for other bench layouts. `TurnDetail` carries five canonical fields (turn, action, duration_s, input/output tokens) plus an `extras` dict so bench-specific fields (e.g. `papers_retrieved`, `parse_errors`) survive round-tripping. `summarize_agent_runs()` rolls up status counts + `wall_seconds` / `turns` / `candidates` / `tool_calls` / `tool_format_errors` summaries. Source: `articles/autoresearchbench-on-spark/scripts/analyze_run.py`. ([extract from #autoresearchbench-on-spark])
- **`fieldkit.eval.MatchedBaseComparison`** + **`GroupStats`** + **`MatchedBaseComparisonResult`** — held-out task split + two-rollout driver + per-group / per-assertion-kind delta. The "filter held-out by training-set membership, run rollout twice with different `--model`, emit B-A comparison" pattern is reusable for any LoRA / adapter ablation. Default `group_extractor` splits `synth-<persona>-NN` task IDs into the persona; pass any `Callable[[str], str]` for other task-id schemes, or `None` to disable per-group breakdown. Accepts trajectories as in-memory dicts or a JSONL path. `.report()` returns a markdown summary table. Source: `articles/clawgym-on-spark/scripts/compare_phase5.py`. ([extract from #clawgym-on-spark])

### Articles in this release

Articles whose `fieldkit_modules` frontmatter assumes v0.2 (added since v0.1.0):

- [`autoresearchbench-on-spark`](https://ainative.business/field-notes/autoresearchbench-on-spark/) — surfaced `fieldkit.eval.AgentRun`.
- [`test-time-distilling-for-exploration`](https://ainative.business/field-notes/test-time-distilling-for-exploration/) — surfaced the deferred `fieldkit.inference.VLLMClient`.
- [`runtime-frontier-six-patches-on-spark`](https://ainative.business/field-notes/runtime-frontier-six-patches-on-spark/) — surfaced `fieldkit.eval.PassAtK` (matured in the seventh-patch follow-up).
- [`pass-at-k-after-the-seventh-patch`](https://ainative.business/field-notes/pass-at-k-after-the-seventh-patch/) — anchor article for `fieldkit.eval.PassAtK`.
- [`clawgym-on-spark`](https://ainative.business/field-notes/clawgym-on-spark/) — surfaced `fieldkit.eval.AssertionGrader`, `fieldkit.eval.MatchedBaseComparison`, plus the deferred `fieldkit.agents` substrate.
- [`clawgym-on-spark-grpo`](https://ainative.business/field-notes/clawgym-on-spark-grpo/) — surfaced the entire `fieldkit.training` module (`LoraReferenceSnapshot`, `WeightDeltaTracker`).

### Test suite

**232 passed, 2 skipped** offline (`pytest -q`) — covers all v0.1 surface plus 16 + 19 + 16 + 12 + 12 = 75 new tests for the v0.2 additions. Reproduce: `pip install fieldkit[dev]` then `pytest`. The `fieldkit.training` tests gate on `pytest.importorskip("torch")` so the suite skips cleanly in pure-inference dev envs and runs end-to-end in any env with torch installed. v0.1's live `--spark` integration tests still pass against warm NIMs + pgvector — none were modified in this release.

### Deferred to v0.3+

The full design doc at `articles/clawgym-on-spark/scripts/fieldkit_agents_v0_2_sketch.md` charts the larger `fieldkit.agents` substrate; the candidates below need a second article's use case before extraction is sound.

- **`fieldkit.agents` module** (7 symbols — `Persona`, `WorkspaceSeed`/`WorkspaceFile`, `SynthTask`, `TaskAuthor`, `Sandbox`/`LocalTempSandbox`, `RolloutDriver`, `Trajectory`/`TurnRecord`). The whole agent-trajectory training substrate that the `clawgym-on-spark` arc walks. Coupled enough that the public API needs a second consuming article to lock in. Source: `articles/clawgym-on-spark/scripts/synth_tasks.py` + `rollout.py`. ([extract from #clawgym-on-spark])
- **`fieldkit.inference.VLLMClient`** — mirror of `fieldkit.nim.NIMClient` for vLLM-side experiments. Deferred because the canonical interface needs a second runtime-frontier article (post-test-time-distilling) to converge. Source: `articles/runtime-frontier-six-patches-on-spark/scripts/bench_a2.py`. ([extract from #test-time-distilling-for-exploration])
- **`fieldkit.agents.replay_messages_from_trajectory`** — reconstruct the exact `(system, user, assistant, observation, …)` message list a policy saw at rollout time. Required for any off-policy training (log-prob recompute is meaningless if reconstruction differs by even a token). Logic currently lives in two byte-identical places (`rollout.py:RolloutDriver.rollout()` forward + `grpo_train.py:reconstruct_messages()` reverse). Right callable interface for `(system_prompt, user_prompt_template, observation_formatter)` won't be obvious until a second article exercises it. ([extract from #clawgym-on-spark-grpo])

[extract from #autoresearchbench-on-spark]: https://github.com/manavsehgal/ai-field-notes/tree/main/articles/autoresearchbench-on-spark
[extract from #test-time-distilling-for-exploration]: https://github.com/manavsehgal/ai-field-notes/tree/main/articles/test-time-distilling-for-exploration
[extract from #pass-at-k-after-the-seventh-patch]: https://github.com/manavsehgal/ai-field-notes/tree/main/articles/pass-at-k-after-the-seventh-patch
[extract from #clawgym-on-spark]: https://github.com/manavsehgal/ai-field-notes/tree/main/articles/clawgym-on-spark
[extract from #clawgym-on-spark-grpo]: https://github.com/manavsehgal/ai-field-notes/tree/main/articles/clawgym-on-spark-grpo

## [0.1.0] — 2026-05-02

First public release. Four library modules + a CLI + a docs site section, lifted from 25+ articles in [ai-field-notes](https://ainative.business/field-notes/).

### Added

- **`fieldkit.capabilities`** — typed Python facade over `spark-capabilities.json`. `Capabilities.load()` cached singleton (with `.hardware`, `.memory_budget_rules_of_thumb`, `.stack`, `.in_envelope_signals`, `.out_of_envelope_signals`, `.stage_routing_hints`, `.series_routing_hints`), plus canonical math helpers `kv_cache_bytes()`, `weight_bytes()`, `practical_inference_envelope()`. Numbers pinned to `kv-cache-arithmetic-at-inference` and `gpu-sizing-math-for-fine-tuning`. ([#capabilities])
- **`fieldkit.nim`** — OpenAI-compatible `NIMClient` over `httpx` with `tenacity`-backed retries on 429 / 503 / `ConnectError` / timeouts. `NIMClient.chat()` runs a pre-flight context check and raises `NIMContextOverflowError` with the estimated token count *before any network call*, so the opaque NIM 400 from a >8192-token request never surfaces. Helpers: `chunk_text()` (paragraph→sentence→word splitting under a `max_tokens` budget), `estimate_tokens()` (1 tok ≈ 4 chars), `wait_for_warm()` (polls `/v1/models` for the ~90s NIM cold start). Constants: `NIM_CONTEXT_WINDOW = 8192`, `DEFAULT_CHUNK_TOKENS = 1024`. Errors: `NIMError` → `NIMHTTPError`, `NIMTimeoutError`, `NIMContextOverflowError`. ([#nim])
- **`fieldkit.rag`** — composable ingest → retrieve → rerank → fuse pipeline backed by pgvector + a NIM embedder + the strict-context grounded prompt from `naive-rag-on-spark`. `Pipeline.ingest()` chunks via `fieldkit.nim.chunk_text` and upserts in batches of 32; `Pipeline.retrieve()` does pgvector cosine top-K; `Pipeline.rerank()` is a pass-through when `rerank_url=None`; `Pipeline.fuse()` builds the strict-context messages list and calls the generator; `Pipeline.ask()` chains all three. Embed and rerank inherit `NIMClient.chat`'s retry policy so co-resident memory pressure doesn't fail the pipeline. ([#rag])
- **`fieldkit.eval`** — `Bench` (latency aggregation with the same `{summary, calls}` JSON shape as the article evidence files), `Judge` (LLM-as-judge with built-in `correctness` / `faithfulness` / `relevance` rubrics + a static `Judge.parse()` JSON-then-regex extractor), `Trajectory` (agent-loop JSONL analyzer with `knob_coverage / repeat_rate / mode_dominance / cumulative_best`), `is_refusal()` (regex catalog unioned across the project's articles), `summarize_metric()`. ([#eval])
- **`fieldkit.cli`** — Typer wrapper exposing `fieldkit version`, `fieldkit envelope <size>`, `fieldkit feasibility <model_id> [--ctx --batch --dtype]`, `fieldkit bench rag`. On `$PATH` after `pip install`. ([#cli])
- **Astro docs site** — `/fieldkit/` landing page with install + quickstart + module grid, and `/fieldkit/api/<module>/` reference pages backed by a new `fieldkit_docs` content collection. Articles can opt-in via `fieldkit_modules:` frontmatter to display a "USES fieldkit.X" chip on cards and appear under each module's "Articles that use fieldkit.<module>" footer. 11 articles opted in for the v0.1.0 launch.
- **Samples**: `samples/feasibility-math.py` (capabilities reproduction of the kv-cache article's table), `samples/hello-nim.py` (Python equivalent of the curl one-liner), `samples/naive-rag.py` (end-to-end RAG in <30 lines), `samples/bench-rag.py` (offline `Bench` + `Judge.parse()` walkthrough).
- `scripts/sync_capabilities.py` keeps the package-bundled `spark-capabilities.json` in sync with the source-of-truth at `scripts/lib/spark-capabilities.json` (pre-commit-enforced).
- `pytest --spark` flag (via `tests/conftest.py`) gates integration tests that need a live NIM / pgvector on the DGX Spark; default runs skip them.

### Changed

- `frontier-scout` skill (`refresh` and `eval` modes, plus `references/feasibility-prompt.md` and `references/classifier-prompt.md`) now teaches the typed `from fieldkit.capabilities import …` API as the preferred grounding path; raw JSON read is the documented fallback.

### Verified on Spark

Phases 3, 4, 5 were live-verified end-to-end against the chat NIM (Llama 3.1 8B, port 8000), the embed NIM (Nemotron Embed 1B v2, port 8001), and pgvector (port 5432) before being committed. Phase 5 in particular rewrote `articles/naive-rag-on-spark/evidence/benchmark.py` against `fieldkit.eval.Bench` + `fieldkit.rag.Pipeline.fuse` and reproduced the original article's behavioral fingerprint (5 of 6 refusals incl. the canonical Google-IPO false refusal, plus the Ian Thorpe grounded answer).

### Distribution

Published to PyPI on 2026-05-02: <https://pypi.org/project/fieldkit/0.1.0/>. Canonical install is now `pip install fieldkit`; the git-tag install (`pip install "git+…@fieldkit/v0.1.0#subdirectory=fieldkit"`) remains supported for unreleased commits between tags. Subsequent releases publish to both git and PyPI in one flow via `fieldkit-curator release`.

### Test suite

**157 passing, 2 skipped** without `--spark` (151 passing with `--spark` against warm NIMs + pgvector). Reproduce: `pip install fieldkit/[dev]` then `pytest`; for the live tests, `pytest --spark`.

[#capabilities]: https://github.com/manavsehgal/ai-field-notes/tree/main/fieldkit/src/fieldkit/capabilities
[#nim]: https://github.com/manavsehgal/ai-field-notes/tree/main/fieldkit/src/fieldkit/nim
[#rag]: https://github.com/manavsehgal/ai-field-notes/tree/main/fieldkit/src/fieldkit/rag
[#eval]: https://github.com/manavsehgal/ai-field-notes/tree/main/fieldkit/src/fieldkit/eval
[#cli]: https://github.com/manavsehgal/ai-field-notes/tree/main/fieldkit/src/fieldkit/cli
