<!-- _SPECS index — project specs, plans, and historical design docs. Last updated: 2026-06-02 -->

# _SPECS — specs, plans & design docs

The single home for this repo's specifications. Consolidated 2026-06-02 from the
former `specs/`, `spec/`, `plans/`, and `docs/superpowers/` folders. Active specs
keep their original basenames (they are referenced as `_SPECS/<name>.md` across the
skills, `src/content.config.ts`, and the `fieldkit` package source).

## Active specs

| Spec | Status | Scope |
|---|---|---|
| [`patent-strategist-v1.md`](patent-strategist-v1.md) | ACTIVE | First fine-tuned vertical — hand-curated patent corpus + DeepSeek-R1-Qwen3-8B LoRA SFT + VerticalBench. §3.3 defines the `fieldkit.eval` scorers; §4 the corpus synth template (read by `claude-corpus-synth`). |
| [`notebooks-as-artifacts-v1.md`](notebooks-as-artifacts-v1.md) | ACTIVE (locked) | The 6th artifact kind — dual-path Spark/Colab builder + user notebooks per vertical. Governs `notebook-author` / `notebook-snapshot` + `fieldkit.notebook` / `fieldkit.viz`. |
| [`spark-arena-v1.md`](spark-arena-v1.md) | ACTIVE | The Orionfold Arena operator cockpit (M1–M7 + v0.2 leap) — sidecar, chat, compare, leaderboard, leak-proof mirror. **§12 = M8 control plane** (`_FLOWS` §3 Phase 1: recorder → dispatcher, `jobs` table + MCP dispatcher — **SHIPPED** in `fieldkit v0.16.0`). **§13 = M9 cost plane** (`_FLOWS` §3 Bet 6: persist + surface `$/task` & `$/quality-point`, `openrouter_price_snapshot`, `fieldkit.cost` — **BUILT 2026-06-02, see §13.7; staged for `~v0.17.0`**). **§14 = M10 recall layer** (`_FLOWS` §3 Bet 5: multi-source provenance index + `/arena/knowledge/` pane + eval-gated re-index, `fieldkit.memory` over `fieldkit.rag` — **decisions locked 2026-06-02, unbuilt**). **§15 = M11 autonomous harness** (`_FLOWS` §3 Phase 2: a `/schedule` cron over the built `drain_jobs()` + a hook battery + a stage-only morning standup + the new `fieldkit.budget` governor [`LOCAL_CEILING=33%`] — **decisions locked 2026-06-02, unbuilt**). Governs `fieldkit.arena`. |
| [`hermes-harness-v1.md`](hermes-harness-v1.md) | ACTIVE | The Harnesses content line — install / serve / harden / route / eval an agent harness (Hermes first) on the Spark. Governs `fieldkit.harness`. |
| [`rlvr-loop-v1.md`](rlvr-loop-v1.md) | ACTIVE (locked, unbuilt) | The **engine** of `pane → hands → engine` (`_FLOWS` §3 Phase 3 / Bet 1): closed-loop RLVR — `eval → reward → fine-tune → re-eval` with `fieldkit.eval` verifiers as the reward. 10 locked decisions (RV-1…10), **standalone** (the new `fieldkit.rl`/`fieldkit.reward` live mostly outside `fieldkit.arena`); promotes the pre-drilled `rl_run`/`requant` job kinds, runs under the M11 cron. Release gate ~`fieldkit v0.20.0`. The **last** of the four `_FLOWS` §3 stubs — all four now written. |
| [`rl-lane-autonomy-v1.md`](rl-lane-autonomy-v1.md) | **DRAFT** (decisions PROPOSED 2026-06-03, unbuilt — confirm before build) | The **post-roadmap follow-on** that makes the shipped Phase-3 engine *self-driving*: closes the two operator-armed chokepoints (a control-plane-managed vLLM lane + one-step cron arming), adds **live step reporting** + a **telemetry-correlated OOM defense** for the multi-hour unattended `rl_run`, and surfaces the published RLVR curriculum so Arena **teaches the operator at every step**. 16 decisions across 4 layers (LA-1…7 arbiter / LA-8…9 progress / LA-10…11 telemetry+OOM / LA-12…16 education). One new Arena submodule `fieldkit.arena.lane` (`LaneArbiter`/`MemoryWatchdog`/`mem_trace`) + a shared `src/content/explainers/` collection. No arena.db churn (`user_version 6`); no new top-level module. Release gate ~`fieldkit v0.22.0`. Awaiting green-light. |

### Planned (named in `_FLOWS` §3 — ALL FOUR NOW WRITTEN as of 2026-06-02)

Phase 1 (Arena M8 control plane) **shipped** (`fieldkit v0.16.0`), and the four remaining roadmap stubs are now **all written** (decisions-locked, unbuilt) in the prioritized order below. Spec-feedable numbers per stub are in [`roadmap-reconciliation.md`](roadmap-reconciliation.md) §"Spec-feedable facts", and `spark-arena-v1.md` §12.6 names how each extends the M8 `jobs` table. Bets 5/6 **and Phase 2** landed as `spark-arena-v1.md` sections (§13/§14/§15, mirroring the §12 M8 pattern); the **Phase-3 engine (`rlvr-loop-v1`) landed standalone** (it spans `fieldkit.rl`/`fieldkit.reward`, mostly outside `fieldkit.arena`) — see the Active specs table above. Each opened with "locked decisions — confirm before build"; each was **user-green-lit**. **The roadmap's spec-authoring backlog is now empty — the next acts are *builds*, not *writes*.**

| Order | Stub | Roadmap | Status |
|---|---|---|---|
| ✅ 1 | `cost-plane-v1` | Bet 6 → Arena M9 | **BUILT** 2026-06-02 (`spark-arena-v1.md` §13 + §13.7 as-built; new `fieldkit.cost`, schema 4→5, cockpit cost axis; suite 1142 pass; staged for `~v0.17.0`). Prerequisite for the Phase-2 budget governor; closed the §7 un-version-controlled-evidence drift. |
| ✅ 2 | `second-brain-pipeline-v1` | Bet 5 → Arena M10 | **WRITTEN** as `spark-arena-v1.md` §14 (decisions locked 2026-06-02, unbuilt). Promotes the pre-drilled `reindex`/`rag_eval`/`scout_ingest` job stubs; multi-source provenance index via `fieldkit.memory` over `fieldkit.rag`; `/arena/knowledge/` pane; closes the external-`ingest_blog.py`/12-of-63-staleness drift. |
| ✅ 3 | `autonomous-harness-v1` | Phase 2 (hands) | **WRITTEN** as `spark-arena-v1.md` §15 = Arena M11 (decisions locked 2026-06-02, unbuilt; placement chosen consistent with M8/M9/M10). A `/schedule` cron over the built `drain_jobs()`, a hook battery, a stage-only morning standup, and the new `fieldkit.budget` governor (`LOCAL_CEILING=33%`, M9 a soft prerequisite). Drains the M8 queue overnight. |
| ✅ 4 | `rlvr-loop-v1` | Phase 3 (engine) | **WRITTEN** as the standalone [`rlvr-loop-v1.md`](rlvr-loop-v1.md) (decisions locked 2026-06-02, unbuilt). 10 decisions (RV-1…10); wraps the hand-rolled REINFORCE loop (not a library); `(success, failure_class, auxiliary)` reward reusing the built `lineage.FailureLabel`; held-out-every-≤10-steps hard gate; promotes `rl_run`/`requant` to `DISPATCHABLE`; no arena.db churn. Release gate ~`fieldkit v0.20.0`. |

### Rendering companions

| Spec | Status | Scope |
|---|---|---|
| [`hermes-harness-v1-mac.md`](hermes-harness-v1-mac.md) | ACTIVE | Section-by-section rendering-side companion to `hermes-harness-v1.md` ("what the site renders for the `harness`/`skill` artifact kinds"). |
| [`notebooks-as-artifacts-v1-mac.md`](notebooks-as-artifacts-v1-mac.md) | ACTIVE | Rendering-side companion to `notebooks-as-artifacts-v1.md`. Supersedes the archived model-playground design (see below). |

## Archive (superseded / historical — kept for the record)

| Doc | Retired | Why |
|---|---|---|
| [`archive/2026-05-22-model-playground-and-eval-surface-design.md`](archive/2026-05-22-model-playground-and-eval-surface-design.md) | 2026-05-23 | The HF-Space playground + Tier A/B/C eval approach; replaced by the notebooks-as-artifacts badge on-ramp. Marked do-not-implement. |
| [`archive/patent-strategist-v4-nemo.md`](archive/patent-strategist-v4-nemo.md) | 2026-05-24 | v4 retrain plan; the spaceless-`<think>` defect was diagnosed as Unsloth-lane-only and resolved by deleting the Unsloth artifacts instead. Kept as the S1 diagnostic record. |
| [`archive/superpowers/`](archive/superpowers/) (12 docs) | 2026-04 | Dated design + execution-plan pairs from the 2026-03/04 stagent.io → ainative.business pivot (landing-page, hero, tech-ticker, architecture-glance, the pivot itself, apply-product-release consolidation). The pivot shipped long ago. |

---

> **Note on `fieldkit/CHANGELOG.md`:** its historical entries still reference the
> old `specs/<name>.md` paths by design — a changelog is an immutable record of
> what was true at release time and is not rewritten. Likewise the `spec_ref`
> fields in `evidence/*.json` and one published article's external permalink to
> the archived `ai-field-notes` repo keep the old path. Live references (skills,
> content config, `fieldkit` source docstrings, `fieldkit/docs/api/`) point here.

Active guidance & practices live in [`../_GUIDES/`](../_GUIDES/index.md).
