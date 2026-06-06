<!-- Arena Enhancements v2 — system-of-record for the serve lane + run-context. Last updated: 2026-06-06 -->

# Arena Enhancements v2.0 — Project Specification

> **One-line.** Make Arena the **system of record for the serving lane** (observe + own what's
> actually resident, instead of trusting a foreign tool's config) and orient the operator on
> **which run's data they're looking at** — the two architectural gaps the v1 end-to-end smoke
> (run S1, 2026-06-06) exposed the moment a real lane was served and a real SFT run completed.

> **Status.** DRAFT — authored mid-smoke (S1 paused at B2) on operator direction: *"plan B and
> related fixes properly, _SPECS/ out the design, implement, then resume."* Numbering continues
> the v1 spec at **AE-18**; risk IDs continue at **AE-R7**. Sibling living ledger:
> [`_IDEAS/arena-smoke-v2-features.md`](../_IDEAS/arena-smoke-v2-features.md) (the AF-/OBS-/BUG-
> harvest this spec formalizes). Same build discipline as v1 (pinned in HANDOFF): every session
> **builds AND browser-smokes side-by-side in the running cockpit over CDP**, rebakes `_webui`,
> runs offline tests, and prefers **no `arena.db` schema change**.

---

## 1. Context

### Why this project (what the smoke exposed)

The v1 cluster (AE-1…17) + guardrail-settings (GS-1…6) shipped and were each *per-feature* browser-
smoked in isolation. Run S1 of the e2e operator-smoke walked the **whole machine** for the first
time (`_GUIDES/arena-e2e-smoke-runbook.md`). Phase A (BUILD) passed clean. Phase B (SERVE) broke
the moment reality met the cockpit:

- **I served a *real* Kepler-Q8 llama.cpp lane on `:8091`** (verified `/props` → `model_path=…/
  Kepler/model-Q8_0.gguf`, a scored astro completion `\boxed{93.45 min}` ✓). **Arena's rail said
  `CONFIGURED LANE · Qwen3-30B · idle`** and never mentioned Kepler.

The root cause is architectural, not cosmetic, and it crystallised two operator principles that now
govern Arena:

> **P1 — Arena is the system of record for every observation.** If a fact about the machine exists
> (a resident lane, a file's row-count, a run's current iter), Arena should be where it is
> *observed* — not a terminal `ls`/`cat`/`docker ps`. **Report ≠ reality is an integrity bug.**
>
> **P2 — Arena is the surface the operator arms + runs the machine from.** Anything the operator
> drops to a CLI to *do* is a gap to close with an Arena action. UI surfacing follows
> **progressive disclosure** — headline on the card, detail on demand; never a raw log dump.

### Body 1 — the serving lane is *asserted by a foreign tool*, not *observed* (OBS-4 / AF-24 / AF-25)

Arena resolves "what lane is serving" through three readers in `fieldkit/src/fieldkit/arena/
server.py`, **none of which discover reality**:

| Reader | Source | Nature | Used by |
|---|---|---|---|
| `_read_hermes_lane()` (`:81`) | **`~/.hermes/config.yaml`** `model` block | **assertion** (what *should* be warm) | chat (`:1069`), compare (`:1257`), judge avail (`:1124`), `/api/lanes` (`:979`), rail label |
| `_resident_live()` (`:487`, AE-15 L1) | TCP-probe the **configured** host:port | observation, but **boolean** + only the one configured port | rail live/idle |
| `_read_active_gpu_lane()` (`:155`, AE-15 L2) | `arena.db` running **`rl_run`** job row | observation, but **only for rl_run jobs** | telemetry |

A hand-served lane on `:8091` falls through all three: not in the Hermes config (Qwen3-30B:8080),
the configured `:8080` isn't live (→ "idle"), no `rl_run` job. **AE-15 already admits the config
lies** — it bolted on a liveness probe + an rl_run reader precisely because "config = truth" was
false. It just stopped short of **discovery**. The dependency on a *sibling tool's* config is the
deeper flaw: it makes the operator hand-edit a foreign YAML to tell Arena what's running (attempted
during S1, correctly denied as out-of-scope), couples Arena's truth to Hermes' presence, and is an
assertion where P1 demands an observation. **The lane self-reports its identity** (`/props`
`model_path`, `/v1/models`) — discovery is feasible and cheap.

### Body 2 — the operator can't tell *which run's* data a pane is showing (OBS-5 / AF-26, operator-raised)

Throughout S1 panes rendered *prior-run* data that *looked* current with no cue: the SFT dropdown
listed Jun-4 runs as peers of the new one; Jobs/leaderboard eval rows are from a *prior* Kepler run
(`0.86/44`); the reward gauge reads prior `av10-preflight*.json`; the build spine reads the static
manifest. For a system of record that *also* drives a live run, **run-context orientation is a
first-class concern** — the operator must intuitively know "this is *my* run" vs "leftover from a
past run." This pairs tightly with Body 1 (the active lane is part of run identity) and is the
inverse of OBS-1 (there, *current* data was shown as *absent*).

### Body 3 — the broader operate-from-terminal + report-vs-reality harvest (the rest of S1)

S1 also catalogued every step the operator/agent had to take **outside** Arena (full table in the
ledger): `docker run` to start the training container (AF-20), `run_sft_nemo.py` to dispatch SFT
(AF-21 — SFT is the one core stage with **no** Arena dispatch), `wc -l` to verify artifacts
(AF-19 — the spine asserts manifest state, not disk truth), a hand-seeded corpus heartbeat (AF-22),
plus **BUG-1/OBS-1**: the `/arena/sft/` pane reports `0/0 · starting` for a *completed* real run
because it regex-parses Megatron `iteration` stdout lines that only the *standalone-script*
invocation emits — the canonical `fieldkit.training.run` path never writes them. These are specced
here as the phased roadmap (Cluster I), gated behind the load-bearing lane-truth + run-context work.

### Why now

The e2e smoke is *paused at B2* on this exact gap: chat/compare route via the Hermes `base_url`
(`:8080`, nothing serving) and cannot reach the real Kepler lane until Arena observes + owns lane
truth. Fixing Cluster G unblocks the resume; Cluster H is the operator's added scope; Cluster I is
the documented backlog.

## 2. Scope

**In (this spec):**
- **Cluster G — Lane truth** (Plan B): discovery probe · Arena-owned active-lane registry ·
  reconciliation · Hermes demotion · multi-lane rail · arm/select-a-lane action. **The build.**
- **Cluster H — Run-context orientation**: run identity · current-run banner · per-pane provenance
  chip + stale-dimming. **The build (at least the lane + rail provenance cue).**
- **Cluster I — Related system-of-record fixes** (SFT canonical feed · inventory truth · corpus
  handshake · feed self-description · operator-brief pane): **specced as roadmap; phased after G/H.**

**Out:**
- Full lane *lifecycle manager* (Arena owning start/stop/switch of every runtime, subsuming
  `spark-serve` / `arena_lifecycle.sh`) — Option C, deferred to a future spec. G implements
  *select/set-active* + an *optional guarded launch*, not a full process supervisor.
- Bringing **Arena itself** up (chicken-and-egg) stays `arena_lifecycle.sh`.
- Route-URL changes (AE-R5 from v1 still holds — grouping/labels only).

## 3. Code reconciliation (verified against the shipped tree 2026-06-06)

- **`fieldkit/src/fieldkit/arena/server.py`** — `_read_hermes_lane` (`:81`), `_read_active_gpu_lane`
  (`:155`), `TelemetryHub._resident_live` (`:487`), `/api/lanes` (`:979`); chat resident at `:1069`,
  compare resident at `:1257`, judge at `:1124`. Hub wires `_resident_reader = _read_hermes_lane`
  (`:888`) + `_active_lane_reader = _read_active_gpu_lane` (`:891`).
- **GS-1 precedent for a file-backed config** — `fieldkit/src/fieldkit/arena/guardrail.py`:
  `load_config()`/`save_config()` atomic `tmp+os.replace` into `~/.fieldkit/arena/guardrail-
  config.json` (env-overridable). **The active-lane registry mirrors this exactly** (AE-R8 — no db
  schema change).
- **Lane self-report** — `llama-server` `/props` (`model_path`, `n_ctx`) + `/v1/models` (`id`);
  NIM/vLLM expose `/v1/models`. Discovery reads these (verified live on `:8091` during S1).
- **Frontend** — `arena-app/src/` panes; the rail island; `_webui` is the baked bundle (`fieldkit
  arena build --repo-root arena-app`). Module enum lives in 3 places
  (`reference_fieldkit_module_enum_three_places`) — N/A here (no new docs module).

## 4. Locked decisions (PROPOSED 2026-06-06 — confirm before build)

### Cluster G — Lane truth (system-of-record for the serving lane) — *Plan B*

| ID | Decision | How | Why / note |
|---|---|---|---|
| **AE-18** | **Lane discovery probe** *(AF-25 core)* | New `fieldkit.arena.lanes.discover()` → probe a configurable port set (`FK_ARENA_LANE_PORTS`, default `8080,8091,8000,8001`); for each that answers, read `/v1/models` + (llama.cpp) `/props` → `{model, base_url, port, n_ctx, kind, where}`. Cheap, cached ~8 s (AE-R7), best-effort (dead port → omitted, never an error). | The **observation** primitive P1 demands. Generalizes AE-15's rl_run reader from "job rows" to "probe the box." |
| **AE-19** | **Arena-owned active-lane registry** *(AF-25 core)* | A file `~/.fieldkit/arena/active-lane.json` (mirrors GS-1 `load_config`/`save_config`; env `FK_ARENA_LANE_PATH`) holding the operator-selected active lane `{model, base_url, port, source, set_at}`. `GET /api/active-lane` returns `{active, discovered[], hermes_hint, drift}`; `POST` sets it. **Reconciled** against `discover()` on every read. | Arena **owns** lane truth (P2). No `arena.db` schema change (AE-R8). |
| **AE-20** | **Hermes demotion** *(AF-25)* | `_read_hermes_lane` becomes one **optional, labelled hint** (`hermes_hint`), never the routing truth. Chat/compare/judge + the rail read the **reconciled active lane** (registry ∩ discovery). Removing `~/.hermes/config.yaml` must not break Arena (AE-R10). | Decouples Arena's system-of-record from a sibling tool. Answers the operator's core question. |
| **AE-21** | **Multi-lane rail + Models truth** *(AF-24)* | The rail + Models pane show **every discovered resident lane** with its real model id + a **drift badge** when the registry/Hermes-hint disagrees with discovery (AE-R9). The active lane is marked; others listed. Throughput/TTFT bind to the active lane. | The visible proof the rail can no longer lie (extends AE-15 honesty from one port to discovered reality). |
| **AE-22** | **Arm / select-a-lane action** *(AF-20, lane scope)* | An operator control (Models/serve surface) to **select** a discovered lane as active (writes AE-19) and — *optionally, guarded* — **launch** a known serve lane (llama.cpp GGUF) via a deterministic runner, one-lane-envelope-aware (offer to tear a conflicting lane down first, `project_spark_unified_memory_oom`). | P2: serving becomes an Arena action, not a memorized `docker run`/`llama-server` block. **Implement select now; auto-launch may phase.** |

### Cluster H — Run-context orientation (the operator's added scope)

| ID | Decision | How | Why / note |
|---|---|---|---|
| **AE-23** | **Run identity + current-run banner** *(AF-26)* | Arena derives a **current run** from the active lane (AE-19) + the active build/vertical (build-manifest); a global rail banner/selector states "**Run: Kepler · live**". Prior runs reachable, never the silent default (AE-R12). | The operator always knows *which run* the cockpit is oriented to. |
| **AE-24** | **Per-pane provenance chip + stale-dimming** *(AF-26)* | Each data pane (SFT · reward · jobs · eval · leaderboard · build) carries a **provenance chip** `run-id · relative-age · live ◉ / prior ○ (run NN)` (reuse the AE-16 relative-time + short-id pattern); data **not** from the active run renders visibly **de-emphasised** + explicitly labelled "from a prior run." | Kills "is this even my run?" Progressive disclosure: headline = "live, this run"; detail expands. Inverse-pairs with OBS-1. |

### Cluster I — Related system-of-record fixes (phased roadmap; gated after G/H)

| ID | Decision | How | Why / note |
|---|---|---|---|
| **AE-25** | **SFT canonical progress feed** *(AF-21 / OBS-1 / BUG-1)* | `fieldkit.training.run` emits a structured `sft-progress-<run>.json` heartbeat from its existing `on_progress(latest_iter, iter_dirs)` callback + reads `latest_checkpointed_iteration.txt` as ground truth; `/arena/sft/` reads the feed, **invocation-independent**. Optional follow-on: an operator-armed `sft_run` job (AF-21). | Fixes the **high-severity** BUG-1 (a completed run rendered `0/0`). Mirrors AE-1 reward-signal + AE-6 corpus heartbeat. |
| **AE-26** | **Inventory truth on the build spine** *(AF-19 / OBS-2)* | Each stage card gains an inventory facet (file exists? line-count vs. manifest-claimed? mtime?) computed at read, like AE-8 already does for the bench JSONL. | Assertion → observation for the no-live-feed stages (P1). |
| **AE-27** | **Corpus-gen request handshake + liveness** *(AF-22 / OBS-3)* | Arena posts a *request* file the CC-session synth skill fulfils (Arena never imports skill code — AE-R3 holds) + surfaces producer liveness ("synth running" vs "none"). | Operator can *intend* corpus-gen from Arena; the feed is no longer a silent blind-spot. |
| **AE-28** | **Feed self-description + operator-brief pane** *(AF-23 / AF-18)* | A progressive "what this pane reads + is it healthy?" disclosure; the runbook as a live guided-flow checklist pane. | Low priority; closes the remaining terminal-orientation gaps. |

## 5. Architecture

```
                    ┌─────────────── discover() (AE-18) ───────────────┐
                    │  probe FK_ARENA_LANE_PORTS → /v1/models + /props  │  ← OBSERVATION (P1)
                    └───────────────────────┬──────────────────────────┘
                                            │ discovered[]
  active-lane.json (AE-19) ──► reconcile ◄──┤                 hermes_hint (AE-20, optional label)
   {model,base_url,port}      (registry ∩   │                  ◄── _read_hermes_lane() (demoted)
        ▲  POST /api/active-lane  discovery) │
        │  (AE-22 select/arm)               ▼
   operator action ──────────►   reconciled active lane  ──►  chat / compare / judge routing
                                            │                  rail + Models (AE-21 multi-lane + drift)
                                            └──►  run identity (AE-23) ──► current-run banner
                                                                     + per-pane provenance (AE-24)
```

- **Reconciliation rule (AE-R9):** the reconciled active lane = the registry entry **iff** discovery
  confirms its port is live with a matching model; otherwise surface **drift** explicitly (registry
  says X, box has Y / nothing) — never silently trust the registry. If no registry entry, fall back
  to "the single live discovered lane" (auto), else "none — arm one" (AE-R11).
- **No `arena.db` schema change** — registry is a JSON file (AE-R8, GS-1 pattern); `user_version`
  stays 6. **No skill imports** (AE-R3 carries over). **No route-URL change** (AE-R5 carries over).
- **Duck-typed, best-effort** — discovery failures degrade to "lane unknown," never error a pane.

## 6. Session-by-session work breakdown

- **V1 (this session, resumes the smoke) — Cluster G core + the rail provenance cue:**
  AE-18 discover() + AE-19 registry + `/api/active-lane` + AE-20 routing read-path + AE-21 rail
  multi-lane/drift + AE-22 *select* (defer auto-launch) + the AE-24 lane provenance chip on the rail.
  Offline tests + `_webui` rebake + **live browser side-by-side** (the rail flips to "Kepler-Q8 ·
  :8091 · live" with no Hermes edit) → **then resume smoke B2/B3/B4 + Phase C.**
- **V2 — Cluster H full:** AE-23 current-run banner + AE-24 provenance/stale-dimming across all data
  panes.
- **V3 — AE-25** SFT canonical feed (fixes BUG-1) + the optional `sft_run` dispatch.
- **V4 — AE-26 inventory truth + AE-27 corpus handshake + AE-28** (as warranted).
- Cut a `fieldkit` minor release per cluster via `fieldkit-curator` (offline-only tests).

## 7. Risk register (continues v1's AE-R*; Arena register R13–R26 in `spark-arena-v1.md` §10)

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| **AE-R7** | Discovery port-scan runs hot / slows the pump tick | med | cockpit lag | probe a small env-set, cache ~8 s, never on the 0.5 s tick (mirror `_resident_live`) | shrink the port set; make discovery on-demand per pane load |
| **AE-R8** | Active-lane state tempts a db schema change | low | a migration + `user_version` bump | **JSON file** registry (GS-1 `save_config` atomic pattern) | if it must be relational later, a new table behind a versioned migration |
| **AE-R9** | Reconciliation silently trusts a stale registry (re-introduces the lie) | med | Arena claims a lane that isn't live | drift is **explicit** — registry ∩ discovery; mismatch → drift badge, never silent | when in doubt show "discovered reality," demote the registry to a claim |
| **AE-R10** | A hard dependency on Hermes remains | low | removing `~/.hermes/config.yaml` breaks Arena | `hermes_hint` is optional + labelled; all routing reads the reconciled lane | guard every `_read_hermes_lane` call with `or None`; tests run with the file absent |
| **AE-R11** | No lane live → chat/compare fail silently against a dead port | med | confusing dead-pane | reconciled "none" → pane says "no lane resident — arm one" (AE-22 CTA) | keep the existing error path but label it |
| **AE-R12** | Prior-run data silently shown as current (the very bug H fixes) regresses | med | operator misreads stale data | active run is **always** the default; prior runs require an explicit selection + carry the prior-○ chip | stale-dim aggressively; never auto-select a prior run |
| **AE-R13** | AE-22 auto-launch violates the one-lane envelope | high | OOM hang (`project_spark_unified_memory_oom`) | implement **select** first; auto-launch is guarded + offers teardown of the conflicting lane first; EngineCore-aware kill | ship select-only; keep launch a CLI step until the guard is proven |

## 8. Release gate

- Offline test suite green (+ new `test_lanes.py` discovery/reconcile/registry + `test_server.py`
  active-lane endpoint + Hermes-absent fallback). No `arena.db` schema change (`user_version` 6).
- **Live CDP browser-smoke:** with the real Kepler lane on `:8091` and **no Hermes edit**, the rail
  shows "Kepler-Q8 · :8091 · live (this run)"; chat/compare route to it; a drift badge appears when
  the registry/Hermes-hint disagrees with discovery; tearing the lane down flips the rail to "none —
  arm one." Then the smoke resumes B2/B3/B4 against the resident lane.
- `_webui` rebaked + cockpit restarted; HANDOFF + beacon updated.

## 9. Change log

| Date | Change | Author |
|---|---|---|
| 2026-06-06 | **Cut 2 BUILT (Cluster G frontend + Cluster H).** AE-21 `<LaneTruth>` (Models) + rail drift/multi-lane badge + CurrentLane source/drift chips; AE-22 **select/pin** UI (launch still deferred, AE-R13); AE-23 `GET /api/run-context` + rail Run cell — the run **anchor** = the select's `set_at` stamp (added to the POST); AE-24 `<ProvenanceChip>` (SFT/Reward/Build) + Jobs/leaderboard-live `○ prior run` label + stale-dim, honest no-claims when unanchored (AE-R12: anchored ⇒ prior data dims by default, never silently current). **Fixed en route:** the registry never fed `_resolve_active_lane` — an operator selection was write-only (caught by the new endpoint tests). Offline 1419 pass; live CDP smoke: discover→pin→dim→drift→clear-revert. | Manav (with Claude) |
| 2026-06-06 | **Spec authored (v2.0 DRAFT).** 11 decisions AE-18…28 across 3 clusters (G lane-truth/Plan-B · H run-context · I related-fixes-roadmap) + 7 risks AE-R7…R13. Formalizes the S1 e2e-smoke harvest in `_IDEAS/arena-smoke-v2-features.md` (OBS-4/5, AF-19…26, BUG-1). Driven by the operator's two principles (P1 system-of-record · P2 arm/run-surface) + the explicit asks: question Arena's Hermes-config dependency (→ AE-18/19/20) and run-context orientation (→ AE-23/24). Build order: V1 = Cluster G core + rail provenance, then **resume the paused smoke**. Still no `arena.db` schema change, no skill imports (AE-R3), no route change (AE-R5). | Manav (with Claude) |

## 10. References

### Internal
- `_IDEAS/arena-smoke-v2-features.md` — the live AF-/OBS-/BUG- harvest (source of these decisions).
- `_GUIDES/arena-e2e-smoke-runbook.md` — the smoke runbook + the narrated-cadence protocol.
- `_SPECS/arena-enhancements-v1.md` — AE-1…17 (this continues it at AE-18; AE-15 is the partial
  lane-truth this completes).
- `_SPECS/arena-guardrail-settings-v1.md` — GS-1 file-backed config pattern (mirrored by AE-19).
- `fieldkit/src/fieldkit/arena/{server.py,guardrail.py,lane.py}` — the reconciled code surface.

### Memory cross-references (`[[name]]`)
- [[feedback_arena_narrated_operator_smoke]] — the run cadence + P1/P2 principles.
- [[dogfood_finds_mock_blind_bugs]] · [[feedback_dogfood_pipeline_with_live_arena]] — why driving
  the live cockpit surfaces what isolated tests miss.
- [[feedback_side_by_side_review_after_major_features]] — the build+browser-smoke discipline.
- [[project_spark_unified_memory_oom]] — the one-lane envelope (AE-R13).
- [[reference_visible_browser_cdp_attach]] · [[reference_hermes_harness_on_spark]] — the CDP harness
  + the Hermes lane being demoted.
