---
project: arena-guardrail-settings
version: v1.0
status: DRAFT (decisions PROPOSED 2026-06-06 — confirm before build)
created: 2026-06-06
authoritative: Spark
---

# Arena Guardrail Settings v1.0 — Project Specification

> The **operator-config surface** for the AE-17 cloud-run guardrails. AE-17
> (`arena-enhancements-v1.md` §6 S7, shipped in `fieldkit v0.26.0`) made the eval
> guardrails *bounded, tracked, and env-configurable* — but the only way to **see**
> or **change** the thresholds is to read the env vars / defaults and restart the
> cockpit. There is no view, and an edit requires a process bounce. This spec adds a
> **Settings pane** where the operator views the effective guardrail config (with
> per-field provenance) and edits it live — the next eval picks up the change with
> **no restart**.
>
> Sibling to — not an extension of — `arena-enhancements-v1.md`: that spec owns the
> guardrail *engine* (AE-17); this one owns the *operator-config surface* over it. It
> cross-links AE-17 at its seam. Same load-bearing discipline: **no arena.db schema
> change** (the config is a JSON file, the AF-9/AF-10 file-convention, not a table),
> **no skill imports** into the cockpit (AE-R3), deterministic CRUD only — no LLM
> (`feedback_llm_skill_pattern`).

## 1. Context

### Why this project

AE-17 shipped three guardrails on metered cloud eval lanes (G1 teardown · G2 stall ·
G3 cost), configured by two env vars read at guardrail **arm time**
(`EvalGuardrail.from_env`, `fieldkit/src/fieldkit/arena/guardrail.py`):

- `FK_EVAL_STALL_TIMEOUT_S` (default 600 s) — the G2 no-progress window.
- `FK_EVAL_RUN_COST_CAP_USD` (default $5) — the G3 per-run cost ceiling.

Because env is set at process launch, the operator cannot answer **"what is my cost
cap right now?"** from the cockpit, and cannot **tighten it before a known-expensive
run** without exporting a var and restarting (`arena restart`). The post-release
question that motivated this spec — *"where can I see the guardrails config in
Arena?"* — has no good answer today: the config is invisible except as code defaults,
and the Jobs-card badge (the one place a guardrail surfaces) renders the *outcome*
(cost spent · abort reason), never the *active thresholds*.

The fix is a small, well-scoped operator surface: a **Settings pane** that reads the
effective config and writes operator edits to a JSON config file the guardrail reads
at arm time — so an edit takes effect on the **next** eval, live, no restart.

### The live-take-effect property (why a file, not just env)

The guardrail is constructed **per dispatch** in `_run_eval_guarded`
(`fieldkit/src/fieldkit/arena/jobs.py`) — *not* at process boot. So if the resolver
reads a config **file** at arm time (layered over env, over defaults), an operator
edit lands on the very next cloud eval with no restart. This is the whole value: env
stays the deploy-time base; the file is the operator's live override.

## 2. Scope

**In:**
- **A — config resolver** — a `GuardrailConfig` value + a `load_config()` resolver
  (file → env → built-in default, with per-field **source provenance**) + a
  validated `save_config()` writer. `EvalGuardrail.from_env` is generalized to read
  the resolver so the live arm path picks up file edits.
- **B — config API** — `GET /api/guardrail-config` (effective + sources + bounds +
  defaults) and `POST /api/guardrail-config` (validate → write → return new
  effective). Deterministic CRUD, operator-private, no LLM.
- **C — Settings pane** — a new `/arena/settings/` pane in the REVIEW/META nav group
  (the S2 IA), a `<GuardrailSettings>` island (view + edit form, per-field source
  chip, defaults, reset-to-default), an **enabled** master toggle, and a loud
  **"guardrails OFF"** banner when disabled.
- **D — badge enrichment** — surface the **effective cap** on the Jobs-card guardrail
  badge (`· cap $5 / 10m`) so the config is visible *at the run*, closing the gap the
  post-release question exposed (folds into C).

**Out:**
- **Any arena.db schema change** — the config is a JSON file under
  `~/.fieldkit/arena/` (the AF-9/AF-10 file convention), never a table.
  `user_version` stays **6** (AH-9 / RV-8).
- **A general operator-settings framework** — the pane is named "Settings" (so a 2nd
  knob slots in) but only the eval guardrails are wired this cycle. Promoting it to a
  generic env-knob editor waits for the 2nd reuse (`feedback_keep_scorer_local_until_reuse`).
- **Guardrails on cloud Compare / Chat** — AE-17 scoped the guardrails to eval runs;
  this spec only adds *config* over that same scope.
- **Per-run / per-job overrides from the dispatch form** — a job-level cap override is
  a plausible follow-on but is out of scope; this cycle edits the *global* config.
- **Mid-run mutation** — a running eval armed its guardrail at dispatch (an immutable
  snapshot); an edit affects the *next* run only (GS-R3).

## 3. Code reconciliation (2026-06-06 — verified against the shipped `fieldkit v0.26.0`)

The headline: **nothing here needs a table or a migration.** Every change extends the
AE-17 guardrail module, adds two read/write endpoints, and adds one pane.

| Surface | Where it lives today (v0.26.0) | What this spec does to it |
|---|---|---|
| Guardrail thresholds | `EvalGuardrail.from_env` reads `FK_EVAL_STALL_TIMEOUT_S` / `FK_EVAL_RUN_COST_CAP_USD` at arm time (`guardrail.py:152`) | **GS-1** adds `GuardrailConfig` + `load_config()` (file→env→default) and points `from_env`/the arm path at the resolver |
| Arm site | `_run_eval_guarded` builds `EvalGuardrail.from_env(...)` per dispatch (`jobs.py`) | **GS-1** has it read the live resolver + honor the new `enabled` toggle (disabled ⇒ run unguarded, byte-for-byte the local-lane path) |
| Config store | (none — env only) | **GS-1** a JSON file `~/.fieldkit/arena/guardrail-config.json` (env-overridable dir), atomic write, operator-private (never mirrored) |
| Write-endpoint precedent | `POST /api/lab/notes` (`server.py:1726`) — deterministic CRUD, Pydantic-validated, operator-private | **GS-2** mirrors it for `POST /api/guardrail-config` (+ a `GET`) |
| Nav | three lifecycle groups BUILD/TRAIN → SERVE/INFER → REVIEW/META (`ArenaAppLayout.astro:229`, AE-12) | **GS-3** adds a **Settings** tab in REVIEW/META; routes otherwise unchanged (AE-R5) |
| Panes | `arena-app/src/pages/arena/*.astro` (jobs/build/reward/standup/lab/cortex/…) | **GS-3** adds `settings.astro` + a `<GuardrailSettings>` island |
| Jobs-card badge | `<EvalGuardrailBadge>` renders cost chip + abort reason, NOT the thresholds (`JobsBoard.jsx:121`) | **GS-4** appends the effective cap (`cap $X / Nm`) read from `result_json.guardrail.{cost_cap_usd,stall_timeout_s}` (already persisted) |
| Schema | `store.py:63` `USER_VERSION = 6` | **unchanged** — no migration |
| Mirror | `mirror.PUBLISHABLE_TABLES` | **unchanged** — the config file is operator-private by construction (not a table; never enters the mirror) |

## 4. Locked decisions (PROPOSED 2026-06-06 — confirm before build)

### GS-1 — Config store is a JSON file read at arm time; precedence file > env > default
A `GuardrailConfig` dataclass (`stall_timeout_s: float`, `cost_cap_usd: float`,
`enabled: bool`) persisted at `~/.fieldkit/arena/guardrail-config.json` (dir overridable
via `FK_EVAL_CONFIG_DIR` / a new `FK_EVAL_CONFIG_PATH`). `load_config()` resolves each
field independently with **provenance**: a present file key wins, else the matching env
var, else the built-in default — returning `(effective, sources)` where each source ∈
`{file, env, default}`. The arm path (`_run_eval_guarded`) reads `load_config()` per
dispatch, so an operator edit takes effect on the **next** eval with **no restart**.
*No arena.db schema change.*

### GS-2 — Two deterministic endpoints, operator-private, no LLM
`GET /api/guardrail-config` → `{effective, sources, defaults, bounds}`.
`POST /api/guardrail-config` (Pydantic body, mirroring `LabNoteRequest`) → **validate
against bounds** → atomic-write the file → return the new `{effective, sources}`.
Deterministic CRUD only (no model call — `feedback_llm_skill_pattern`). The config file
is operator-private — it is not a table, so it never enters `mirror.PUBLISHABLE_TABLES`;
a `test_mirror_does_not_leak`-style assertion is unnecessary but the privacy note is
pinned in the spec.

### GS-3 — A REVIEW/META "Settings" pane; first (only) occupant = guardrails
New `/arena/settings/` pane + `<GuardrailSettings>` island: each field rendered as
`label · current value (editable) · source chip · default`, a Save button (POST →
success toast → re-fetch), and a **Reset to defaults** affordance (writes the defaults,
or clears the file). Named **Settings** (not "Guardrails") so a 2nd operator knob slots
in later, but only guardrails are wired this cycle (`feedback_keep_scorer_local_until_reuse`).
Nav tab added to the REVIEW/META group; **no route change** elsewhere (AE-R5).

### GS-4 — An `enabled` master toggle + a loud "guardrails OFF" state
`enabled: true` by default. When **off**, cloud evals run **unguarded** (the operator
opt-out for a trusted long run) — the arm path treats `enabled=false` like a local lane
(no guardrail). The disabled state is **loud**: a persistent "Cloud-eval guardrails OFF"
banner on the Settings pane (and a chip on the Jobs board), mirroring the Standup
autonomy-banner pattern, so the unsafe state is never silent. Note the existing
*per-field* off-switch semantics carry forward: `stall_timeout_s=0` ⇒ G2 off,
`cost_cap_usd=0` ⇒ G3 off (already the code's `if self.cost_cap_usd and …` behavior).

### GS-5 — Validation bounds (fat-finger guard)
`save_config()` rejects out-of-range values with a clear error (HTTP 422 via the
Pydantic body + a server-side bound check): `stall_timeout_s` ∈ `[30, 86400]` or `0`
(off); `cost_cap_usd` ∈ `[0, 1000]` (`0` = G3 off); `enabled` bool. A $0.001 cap that
would abort every eval on row 1 is *allowed but loud* (GS-R1) — the cap is real
operator intent; the badge (GS-4) shows it and the `partial` `result_json` records
exactly what was spent.

### GS-6 — Effective cap on the Jobs-card badge (closes the visibility gap)
`<EvalGuardrailBadge>` appends `· cap $X / Nm` from the per-run
`result_json.guardrail.{cost_cap_usd, stall_timeout_s}` (already persisted by AE-17) so
the config that *governed that run* is visible at the run, not just on the Settings
pane. Zero new persistence — a render-only change over existing fields.

## 5. Architecture

**Resolver (GS-1).** `fieldkit.arena.guardrail` gains:
```
GuardrailConfig(stall_timeout_s, cost_cap_usd, enabled)         # value
load_config() -> (GuardrailConfig, sources: dict[str,str])      # file>env>default + provenance
save_config(cfg) -> GuardrailConfig                             # validate + atomic write
DEFAULTS / BOUNDS                                               # the canonical numbers
```
`EvalGuardrail.from_env` is kept as a thin wrapper that calls `load_config()` (back-compat
for the existing arm site + tests), and `_run_eval_guarded` reads `load_config()` to honor
`enabled` (skip arming when off). The file write is atomic (`tmp + os.replace`).

**API (GS-2).** Two endpoints on the sidecar, mirroring the lab-notes CRUD shape; the
`GET` is a pure projection over `load_config()`, the `POST` validates then `save_config()`.

**Pane (GS-3/4/6).** `settings.astro` + `<GuardrailSettings>` (a small preact island,
the LabNotes/JobsBoard pattern): fetch `GET` on mount, render the form + source chips +
the OFF banner, POST on Save. The badge enrichment (GS-6) is a one-line change in the
existing `<EvalGuardrailBadge>`.

**The proven transport precedent** is AF-9/AF-10 (file-polled report under a `FK_*`-env
dir) + the lab-notes deterministic-CRUD endpoint — this spec reuses both, adds neither a
table nor a new pattern.

## 6. Session-by-session work breakdown

Each session closes to the **pinned build discipline** (offline tests + `_webui` rebake
+ live browser side-by-side over CDP) per `feedback_side_by_side_review_after_major_features`.

```
GS-1  Config core        GuardrailConfig + load_config (file>env>default + sources) +
                         save_config (validate/atomic) + DEFAULTS/BOUNDS; from_env →
                         resolver; _run_eval_guarded honors `enabled`. Tests
                         (resolver precedence, provenance, bounds, enabled-skips-arming).
GS-2  Config API         GET/POST /api/guardrail-config (Pydantic body, 422 on bound
                         violation, operator-private). Tests (read effective, write
                         persists + takes effect, bad value rejected, file>env wins).
GS-3  Settings pane      /arena/settings/ + <GuardrailSettings> (view+edit, source
                         chips, reset-to-default, enabled toggle, OFF banner) + REVIEW/
                         META nav tab + CSS + GS-6 badge cap. Browser-smoke (view defaults,
                         edit cap → save → re-fetch shows file source; toggle off → banner;
                         seed a cloud eval → badge shows `cap $X/Nm`; revert).
```

Three sessions; GS-1+GS-2 are backend-only (offline tests), GS-3 is the frontend + the
badge fold-in. Release gate ~`fieldkit v0.27.0` (one cut for the cluster, or fold GS-3
into the same cut as GS-1/2).

## 7. Risk register (local IDs)

| ID | Risk | Sev | Impact | Mitigation | Recovery |
|---|---|---|---|---|---|
| **GS-R1** | A fat-finger cost cap (e.g. $0.001) aborts every cloud eval on row 1 | med | wasted partial spend, confusing "always aborts" | bounds (GS-5) reject negatives; the badge (GS-6) shows the active cap; the `partial` `result_json` records exactly what was spent + why | raise the cap on the Settings pane (live, next run picks it up) |
| **GS-R2** | The config file and env disagree → operator unsure which wins | low | wrong mental model of the effective cap | the resolver surfaces **per-field source** (`file`/`env`/`default`); file wins (the UI is authoritative) and the chip says so | none needed — provenance is the fix |
| **GS-R3** | An edit lands while an eval is mid-run | low | operator expects the running eval to retighten | a running eval armed its guardrail at dispatch (immutable snapshot, matches AE-17); the edit affects the **next** run — documented on the pane ("applies to new runs") | none — the next run is correct |
| **GS-R4** | Guardrails disabled (GS-4) then forgotten → uncapped spend returns | med | the exact AE-17 failure mode re-opened silently | a **persistent loud OFF banner** on the Settings pane + a Jobs-board chip (the Standup-banner pattern); `enabled` defaults true | re-enable on the pane (live) |
| **GS-R5** | A corrupt/partial config file (crash mid-write) | low | the arm path can't read config | atomic write (`tmp + os.replace`); `load_config()` falls back to env→default on a parse error (never crashes a dispatch) | delete the file → reverts to env/defaults |

## 8. Release gate

`~fieldkit v0.27.0`. Offline-only tests (the whole cluster is arena/guardrail/server +
a pane — no NIM / pgvector / live cloud paths). `audit-docs` (the new `GuardrailConfig` /
`load_config` / `save_config` land in `fieldkit.arena.guardrail`, which is an arena
**submodule** — like `lane`/`jobs`, not in `fieldkit.arena.__all__`, so no `arena.md`
gap; document the new public names in the module docstring + CHANGELOG). `audit-landing`
unaffected (no new top-level module). **No arena.db migration** (`user_version` 6).
**AE-R1-style live validation** (a real cloud eval that picks up an edited cap with no
restart) stays operator-armed, as with AE-17.

## 9. Change log

| Date | Change | By |
|---|---|---|
| 2026-06-06 | Spec authored. 6 decisions (GS-1…6) over the AE-17 guardrails: config-as-file resolver (file>env>default + provenance), GET/POST config API, a REVIEW/META Settings pane, an `enabled` master toggle + loud OFF state, validation bounds, and the Jobs-card cap badge. 3-session breakdown §6; risk register GS-R1…R5; release gate ~`v0.27.0`. **Still no arena.db schema change** (config file + endpoints + pane). DRAFT — confirm before build. | Manav (with Claude) |

## 10. References

### Internal
- `_SPECS/arena-enhancements-v1.md` §6 S7 / Cluster F — **AE-17**, the guardrail engine this spec configures.
- `_SPECS/spark-arena-v1.md` §13 (M9 cost plane / `PriceSnapshot`), §15 (M11 budget governor / the per-day cap whose per-run sibling is G3).
- `fieldkit/src/fieldkit/arena/guardrail.py` — `EvalGuardrail` / `from_env` / `is_cloud_endpoint` (the surface GS-1 extends).
- `fieldkit/src/fieldkit/arena/jobs.py` — `_run_eval_guarded` (the arm site).
- `fieldkit/src/fieldkit/arena/server.py:1726` — `POST /api/lab/notes` (the deterministic-CRUD write precedent).
- `arena-app/src/layouts/ArenaAppLayout.astro` (AE-12 nav groups) · `arena-app/src/components/arena/JobsBoard.jsx` (`<EvalGuardrailBadge>`, GS-6).

### Memory cross-references (`[[name]]`)
- `[[feedback_llm_skill_pattern]]` — deterministic CRUD only; no `anthropic` / `claude-agent-sdk`.
- `[[feedback_keep_scorer_local_until_reuse]]` — name the pane "Settings" but wire only guardrails until a 2nd knob.
- `[[feedback_side_by_side_review_after_major_features]]` — close each session with operator + live-browser side-by-side over CDP.
- `[[reference_visible_browser_cdp_attach]]` / `[[reference_marketing_screenshots_live_sse_2x]]` — the CDP browser-smoke harness.
