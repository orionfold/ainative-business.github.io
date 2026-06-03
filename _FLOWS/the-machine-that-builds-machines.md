<!--
  _FLOWS/the-machine-that-builds-machines.md — the canonical origin-instruction → artifact
  map + the 100x roadmap. The anchor doc of the `_FLOWS/` stream (process flow, data flow,
  and operator flow-state); renamed from the root `WORKFLOWS.md` on 2026-06-02 so "Flows" —
  not "Workflow" (which collides with the Claude Code orchestration tool) — names this body of work.
  Living doc. Refresh after any flow / skill / spec change, the same way HANDOFF.md
  and ideas/ are kept current. Peer to _GUIDES/narrative-contract.md in the root-contract tier.
  Build-in-public contract (public doc since 2026-06-02): ship-to-converge — graduate §3 roadmap
  bets into §2 reference as they ship; keep §7 drift honest + bounded; no unhedged forward promises.
  Last updated: 2026-06-02 (§3 resequenced into pane→hands→engine phases; §1 folds in Ch-14; build-in-public contract added; §3/§7 grounded against the article corpus — see _SPECS/roadmap-reconciliation.md; §3 adds the cross-cutting recall layer — Bet 5, the Second Brain as a control-plane-managed knowledge pipeline; §3 adds the cross-cutting cost plane — Bet 6, token economics as a first-class decision axis; Phase-1/Arena-M8 spec now WRITTEN — _SPECS/spark-arena-v1.md §12, recorder→dispatcher, spec-only/unbuilt; UPDATE: Phase-1/M8 now SHIPPED end-to-end [v0.16.0 + launch 606333d] + the four remaining spec stubs prioritized post-M8 — see §7 + _SPECS/index.md Planned queue; UPDATE 2: cost-plane-v1 [Bet 6] now WRITTEN as _SPECS/spark-arena-v1.md §13 [Arena M9], decisions locked, unbuilt; UPDATE 3: second-brain-pipeline-v1 [Bet 5] now WRITTEN as _SPECS/spark-arena-v1.md §14 [Arena M10], 12 decisions locked, unbuilt; UPDATE 4: autonomous-harness-v1 [Phase 2] now WRITTEN as _SPECS/spark-arena-v1.md §15 [Arena M11], 9 decisions locked AH-1…9, unbuilt, new fieldkit.budget governor — only rlvr-loop-v1 [Phase 3 engine] remains to write).
-->

# The machine that builds the machines — the canonical flows map

**What this is.** The single map from a human **origin instruction** ("write this up", "pick a base model", "publish the GGUF", "release fieldkit") to a shipped **artifact** (article, quant, LoRA, notebook, bench, app, package, book chapter). Until now this knowledge lived scattered across 24 `SKILL.md` files, 4 locked specs, ~10 root contracts, and `HANDOFF.md`. This doc consolidates it — and then points at where the system goes next. (Active guidance now lives in `_GUIDES/`, specs in `_SPECS/` — see `_GUIDES/index.md` + `_SPECS/index.md`.)

**Two halves.** §0–§2 are the **reference** (current workflows, exactly as they run today). §3–§7 are the **roadmap** (four disruptive bets sequenced into `pane → hands → engine` phases, plus a cross-cutting **recall layer** that threads them, Fieldkit/Arena abstractions, a new-artifact brainstorm, and a frontier-hardware extrapolation). It is a *living* doc: when a workflow changes, the reference half changes; when a bet ships, it graduates from roadmap to reference.

**Cross-refs.** `HANDOFF.md` (session state) · `_GUIDES/index.md` (active guidance: `_GUIDES/narrative-contract.md` publish rubric, `_GUIDES/product-articles.md` launch-article contract, `arena-distribution.md` + `arena-storefront-marketing.md`, `local-ai-stack-commands.md`) · `_SPECS/index.md` (`_SPECS/*.md` project specs + the `archive/` of superseded designs) · `_SPECS/roadmap-reconciliation.md` (the §3 bets reconciled against Spark-measured article evidence — grounding for the unwritten spec stubs) · `ideas/ai-field-notes-consolidation.md` (the one live strategy doc).

**Legend for every map below:**

```
origin instruction  →  skill(s)  →  deterministic script(s)  →  [GATE]  →  artifact  →  destination
                       (Claude writes)   (mechanical only)     (verify)   (manifest)   (HF / site / PyPI)
```

---

## 1. The mission frame

The thesis is the Book's Ch 10–11 + Ch 14 (`src/data/book/chapters/ch-10-the-world-model.md`, `ch-11-the-machine-that-builds-machines.md`, `ch-14-the-meta-program.md`): a continuously-updated **world model** (Ch 10), a **self-building pipeline** where *the process described in the chapter is the process that produced the chapter* (Ch 11), and — the sharpest recursion — a **meta-program** where *the tool you build with is itself an instance of the thing you build* (Ch 14: "the specification IS the application; configuration over code"). Ch 14 is written about the sibling `ainative` agent-workspace platform (its wealth/growth domain clones); this Spark publishing monorepo is **another instance of the same pattern**, not the same codebase. Two external precedents anchor it:

- **Karpathy's `program.md`-as-specification** — the human designs the arena (a spec, not a prompt), the agent explores it until success; ~100 ML experiments/night from a single GPU.
- **8090's software-factory pattern** — "solve a migration once; the assembly line remembers it; next time it's *manufactured*." Process encoded as workflow blueprints that improve with each execution.

**Four load-bearing invariants** (every workflow respects these):

1. **Solo-blog, direct-to-main.** No PRs on the publisher repo; commit subjects *are* the changelog. Human review is the only gate (memory `project_nvidia_learn_git_workflow`).
2. **One serving lane in 128 GB.** GB10 shares CPU+GPU unified memory — one model resident at a time; estimate footprint before load (memories `project_spark_unified_memory_oom`, `feedback_vllm_engine_core_orphan`).
3. **Privacy-gated publish.** Every article/model/launch passes a secret-scan + scoped (not full-page) captures before commit; no auto-push.
4. **Deterministic scripts, not LLM coordination.** Skills' bundled `scripts/` do *only* mechanical transforms (copy, diff, validate, audit, quantize, measure). Claude (the session model) does the writing. Skills never call `anthropic`/`claude-agent-sdk` (memory `feedback_llm_skill_pattern`).

The Spark is the **making** tool (quantize, measure, fine-tune, retrieve) *and* the **driving** tool (the Arena cockpit) — never a mere packaging box.

This doc is itself a Ch-14 artifact: the `origin instruction → skill → script → artifact` legend *is* the `program.md` pattern (the human writes the spec, the skill interprets it, the artifact is the output), and the ~24 skills are *configuration over* the fieldkit + Claude-Code substrate, not standalone programs (invariant #4 restated). The §3 roadmap extends the same loop — Arena (Phase 1) the trigger engine, cron (Phase 2) the scheduler, the budget-governor + no-auto-push standup gate the governed-approval layer — Ch-14's six primitives in the Spark's idiom.

---

## 2. Current workflows — the canonical map

### 2A. Editorial → Book pipeline *(this is where it all compounds)*

Articles are not blog filler — they are the **raw stock the published Book is manufactured from** (the Ch-11 recursion). Every deep-dive and product launch is a future chapter section. This is the highest-leverage loop because it converts daily Spark work into a durable, compounding asset.

**(a) Deep-dive article** — `tech-writer`

```
exploration session on the Spark
  → /tech-writer  (Claude writes the essay; voice = deep-dive, not cookbook)
  → new_article.sh (scaffold)  ·  Playwright/scrot screenshots → /tmp then repo
  → [GATE verify_article.sh] frontmatter + image-resolution + secret-scan
  → [GATE verify_svg.sh] stroke-weight ∈ {0.5,1,1.5,2}, no hex literals, inline fn-diagram present
  → [GATE /nvidia-learn-stats] refresh src/data/field-notes/project-stats.json (home infographic drifts silently otherwise)
  → artifact: articles/<slug>/article.md + screenshots/ + transcript.md + inline SVG
  → commit to main
```
Invariants that bite (encoded in memories): home/stage ordering is **git-derived № desc** via `src/lib/field-notes/article-order.mjs`, *not* `data.date` (`feedback_article_ordering`); prose "article #N" must equal the rendered `№NN`, prefer slug links (`feedback_article_prose_numbering`); article images span the `.article` 80rem measure, not the `.prose` column (`feedback_article_image_breakout`); fn-diagram inline figures must contain **no blank lines** or the SVG silently renders as code (`feedback_fn_diagram_no_blank_lines`).

**(b) Product-launch article** — `product-writer`

```
a shipped product (e.g. Orionfold Arena)
  → /product-writer  (Claude writes the launch story; dual-reader: AI-research + Spark operator)
  → new_product_article.sh  ·  mine_build_metrics.py (tokens · hours · LOC · tests · features · turns · cache-ratio)
  → [GATE verify_product_article.sh]
  → artifact: products/<slug>/product.md + build-metrics infographic + feature-tour gallery
```
Contract: `_GUIDES/product-articles.md`. The `products` collection is distinct from `articles` (launch genre vs deep-dive). First entry shipped: `products/orionfold-arena/`. Mac owns the `/products/**` URL family, layout, OG cards.

**(c) Articles → Book chapters** *(the recursion)*

The foundation arcs — **Second Brain · LLM Wiki · Machine that Builds Machines · Looking Beyond Spark** (memories `project_nvidia_learn_editorial`, `project_looking_beyond_spark_series`) — plus case-study notes assemble into `src/data/book/chapters/`. Ch 11 documents *its own* assembly pipeline (Capture → Screengrab → Doc-Generator → Chapter Assembly → Technical Review → Freshness Monitoring). **This is why article hygiene matters**: clean, citable, well-ordered articles are the feedstock; sloppy ones poison the chapter that quotes them.

**(d) Research → article** — `frontier-scout` → `tech-writer`

```
"what's new in AI research" / a fresh arxiv URL
  → /frontier-scout refresh (arxiv + HF + Papers-with-Code fetchers) → papers/README.md + papers.json
  → /frontier-scout eval <id>  → papers/<id>/eval.md  [Spark-feasibility verdict]
  → /frontier-scout promote <id> → articles/<slug>/seed.md + evidence/ skeleton + HANDOFF stanza
  → /tech-writer (draft from seed) → [article chain above]
```
Feasibility gate is memory-correct, not wall-clock-optimistic: compute `wall × nproc × ~8× slowdown` before promising fresh-data reproduction (`feedback_spark_scaling_optimism`).

### 2B. Model-artifact pipeline (quant + LoRA + corpus)

**Quant** — the core "vertical-curator" loop across 5 verticals (patent, legal, finance, cyber, medical):

```
"what should we quantize next for <vertical>"
  → /hf-model-scout  (4-trap classifier: chat_template? · license tier? · llama.cpp arch? · 128GB envelope?)
        scripts: probe_model.sh · spark_envelope.py    → /tmp/hf-scout/<run>/report.md (top-3)
  → g3_build_first_quant.sh download → convert → quantize (GGUF) → publish dry-run
  → g3_measure_variants.py  4-axis sweep:
        perplexity (wikitext-2) · tok/s (llama-bench) · sustained-load thermal · VerticalBench accuracy
  → /hf-publisher
        [GATE verify_stage.sh] 6 checks (license · how-to-run · Spark-tested shape · Methods link · variants · engagement metadata)
        [GATE manual review] quote card slices
        hf_push_resilient.py (upload_large_folder, num_workers=1 — resumable; upload_folder crashes on Spark)
  → artifact: src/content/artifacts/<slug>.yaml (manifest) + HF Orionfold/<slug> card
  → HANDOFF update · commit · /nvidia-learn-stats refresh
```
The card shape is enforced by `_GUIDES/narrative-contract.md`: **positioning leads, never drift**; every `known_drift` entry carries a count/bound; no forward-looking roadmap (memories `feedback_hf_readme_positioning`, `feedback_customer_link_audit`). Preflight 5 bench questions on FP weights **before** sinking multi-hour quant cycles (`feedback_preflight_bench_before_quant`). Pick base models past the 4 traps (`feedback_chat_vs_continued_pretrain_trap`, `feedback_reasoning_model_npredict`).

**Manifest schema** (`fieldkit.publish.ArtifactManifest`, rendered on both HF + the catalog): `slug · kind · class · base_model · hf_repo · variants[] · perplexity{} · spark_tokens_per_sec{} · sustained_load_minutes · vertical_eval{} · recommended_variant · lineage_run_id · license{tier,model} · article · positioning{headline,problem,use_cases,audience} · stack_origin · known_drift[{item,bound}] · notebooks[{label,colab,kaggle}]`. The `positioning`/`stack_origin`/`known_drift` trio is the v0.5.x publishing-first surface (memory `project_artifact_manifests_phase2`).

**LoRA / fine-tune path:**
```
base + vertical corpus → g3_train_first_lora (Unsloth | NeMo) → g3_merge_adapter → g3_measure_variants → /hf-publisher (kind: lora)
```
Stack choice is settled: **data layer = NeMo** (Curator+DataDesigner+NIM), **train layer = carry both Unsloth & NeMo** in fieldkit (NeMo wins wall −26% + reasoning chains +44%; Unsloth wins dev-velocity + 4-bit QLoRA) — memory `project_nemo_pilot_verdict`. `stack_origin` becomes a lane-colored badge in `fieldkit.viz`.

**Corpus synthesis** — `claude-corpus-synth` (in-session generation, **no API/SDK**):
```
patent queue + Layer-2 template → Claude writes <think>chain</think>answer rows via Edit-append
  → [GATE preflight_budget.py] paste /usage; projected % of weekly Max cap + session count
  → [GATE verify_chunk.py] 4 regex gates: meta-state leak · R<digits> ref · SPICE pigeon-hole · split_think strip-check
  → merge_outputs.py → /home/nvidia/data/corpus/patent-*.jsonl
```
Spec `_SPECS/patent-strategist-v1.md` §4. The gate cluster exists because producer working-notes leaked at 56%/68%/19% across phases (memories `feedback_synth_meta_state_gate`, `feedback_synth_r_digits_gate`, `feedback_corpus_spice_pigeon_hole`, `feedback_split_think_strip_check_trap`). SFT raw-text needs explicit BOS+EOS (`feedback_sft_eos_bos_explicit`).

### 2C. Notebook-artifact pipeline

```
an artifact manifest + its article
  → /notebook-author  scaffold_notebook.py → builder/user .py (jupytext percent) ; Claude writes prose cells
        [GATE validate_cadence.py] explainer → code → interpretation rhythm ; inject_badges.py (Colab/Kaggle)
  → /notebook-snapshot  execute_notebook.py (papermill --allow-errors) → export_figures.py (2× DPI heroes)
        notebook_to_html.py + Playwright-MCP (great_tables hero + reasoning cells) → build_index.py
  → artifact: notebooks/<vertical>/{builder,user}.ipynb + exports/*.png ; badge row → HF card
```
Spec `_SPECS/notebooks-as-artifacts-v1.md` (6th artifact kind). Dual-path Spark/Colab via `fieldkit.notebook.detect_runtime`/`open_model`; hardware-only steps pre-rendered for cloud. HF renders README images `display:block`, so the notebook on-ramp is a `## Notebooks` table *after* positioning (memory `reference_hf_markdown_img_display_block`).

### 2D. Operator / serving workflows

| Skill | Trigger | What it does |
|---|---|---|
| `spark-serve` | "serve `<model>`" | Brings up ONE lane (NIM \| llama.cpp \| vLLM \| Ollama) in the envelope; tears down cleanly. NIM tuning: `NIM_MAX_BATCH_SIZE=32` for Nemotron-Nano-9B (memory `reference_nim_spark_env_vars`). |
| `vertical-route` | domain question | Classifies → serves the right Orionfold expert GGUF → escalates to frontier only on low local confidence. |
| `arena-lifecycle` | "restart the arena" | Cockpit up/down (`fieldkit arena up` → `:7866`), ± visible CDP Chromium on `:9222` for browser-use. Sources `.env.local` for OpenRouter lanes. |

Serving guardrails: prefer NIM over stock vLLM for Nemotron (tokenizer/chat-template correctness — `feedback_prefer_nim_over_vllm_for_nemotron`); kill orphans with `pkill -f 'vllm|EngineCore'` (`feedback_vllm_engine_core_orphan`); default NemoClaw/Ollama **off** (`feedback_stop_unneeded_services`).

### 2E. Site / release ops

- **`apply-product-release`** — orchestrator: 5 sub-skills (`apply-screengrabs` → `apply-product-docs` → `apply-api-docs` → `apply-book-update` → `ainative-stats`) each run **Plan-only**, aggregate to **one approval gate**, then Execute in order → `npm run build` → 8-route browser smoke → commit *suggestion* (no auto-push). (Mac-side; product→marketing-site sync.)
- **`fieldkit-curator`** — PyPI release: CHANGELOG `[Unreleased]` → `[GATE audit_docs.py]` (`__all__` vs `docs/api/<module>.md`) + `[GATE audit_landing.py]` → tests → bump → tag → push → fresh-venv install verify → PyPI build/upload → stats → HANDOFF. Auth from `.env.local` `PYPI_TOKEN` (memory `reference_fieldkit_pypi_auth`). Blind spot: audit is symbol-coverage only — eyeball kwarg drift manually (`feedback_audit_docs_kwarg_blind_spot`).
- **`seo-monitor`** — GSC + GA4 + PSI audit → `seo-progress.md` + per-snapshot archive + code-fix proposals. (Blocked on PSI authenticated key per HANDOFF.)
- **`deck`** — refresh the ainative prospect PPTX.
- **`sync-field-notes`** — **LEGACY.** The two-repo Mac-sync model is retired post-monorepo-cutover (memory `project_spark_monorepo_cutover`); author directly in this repo. Kept only for historical reference.

### 2F. Skill audit — the complete index

Every custom skill that automates a workflow, with its origin→artifact contract. Status: **active** / **legacy** / **adjacent** (general-purpose, not core pipeline).

| Skill | Trigger | Output artifact | Key scripts | Hands off to | Status |
|---|---|---|---|---|---|
| `tech-writer` | "write this up" | `articles/<slug>/article.md` | `new_article.sh` `verify_article.sh` `verify_svg.sh` | nvidia-learn-stats, fieldkit-curator (extract) | active |
| `product-writer` | "write the launch" | `products/<slug>/product.md` | `mine_build_metrics.py` `verify_product_article.sh` | — | active |
| `frontier-scout` | "scout papers" | `papers/`, `articles/<slug>/seed.md` | arxiv/HF/PWC fetchers, classifier/feasibility prompts | tech-writer | active |
| `hf-model-scout` | "pick a base for `<vertical>`" | `/tmp/hf-scout/<run>/report.md` | `probe_model.sh` `spark_envelope.py` | hf-publisher (via g3) | active |
| `hf-publisher` | "publish to HF" | HF card + `artifacts/<slug>.yaml` | `hf_push_resilient.py` `verify_stage.sh` | tech-writer, stats | active |
| `claude-corpus-synth` | "build the corpus" | training JSONL | `prepare_queue.py` `preflight_budget.py` `verify_chunk.py` `merge_outputs.py` | g3 train | active |
| `notebook-author` | "author notebooks for `<vertical>`" | `notebooks/<v>/{builder,user}.ipynb` | `scaffold_notebook.py` `validate_cadence.py` `inject_badges.py` | notebook-snapshot | active |
| `notebook-snapshot` | "snapshot the notebook" | `notebooks/<v>/exports/*.png` | `execute_notebook.py` `export_figures.py` `build_index.py` | hf-publisher (badges) | active |
| `fieldkit-curator` | "release fieldkit" | PyPI package + tag | `audit_docs.py` `audit_landing.py` | nvidia-learn-stats | active |
| `nvidia-learn-stats` | "refresh stats" | `src/data/field-notes/project-stats.json` | `compute_stats.py` | home infographic | active |
| `arena-lifecycle` | "restart the arena" | running cockpit `:7866` | `arena_lifecycle.sh` | — | active |
| `spark-serve` | "serve a model" | running lane | lane-selection logic | — | active |
| `vertical-route` | domain question | local expert answer | classifier + spark-serve | — | active |
| `seo-monitor` | "check SEO" | `seo-progress.md` | `audit_site.mjs` `diff_snapshot.mjs` | — | active |
| `apply-product-release` | "apply product release" | site build + smoke | (orchestrates 5) | 5 sub-skills | active (Mac) |
| `apply-screengrabs` / `-product-docs` / `-api-docs` / `-book-update` | sub-skill triggers | synced site sections | per-skill diff/verify | next sub-skill | active (Mac) |
| `ainative-stats` | "update stats" | `ainative-stats.md` + site | metric collectors | deck | active (Mac) |
| `deck` | "update the deck" | prospect `.pptx` | `generate-deck.mjs` | — | adjacent |
| `nemoclaw-guru` | "install nemoclaw" | running sandbox | reference docs | — | adjacent |
| `frontend-design` | "build a UI" | HTML/CSS/React | — | — | adjacent |
| `sync-field-notes` | "sync field notes" | (mirror articles) | `diff_articles.py` `sync_articles.py` | — | **legacy** |

### 2G. Cross-cutting contracts & protocols

| Contract | Governs |
|---|---|
| `_GUIDES/narrative-contract.md` | The 11-rule publish rubric across HF cards + site (positioning-first, bounded drift, no roadmap, sibling cross-links, Methods wire-back). Enforced by `hf-publisher` + `verify_artifact_rendering.mjs`. |
| `_GUIDES/product-articles.md` | The `products/` launch-article genre (build-metrics infographic, feature tour, agentic-effort row). |
| `_GUIDES/arena-distribution.md` / `_GUIDES/arena-storefront-marketing.md` | Arena distribution (PyPI `fieldkit[arena]` ships the cockpit; the leak-proof static `/arena/` preview) + storefront positioning for orionfold.com (local-runnable CTA, not SaaS). |
| `_GUIDES/local-ai-stack-commands.md` | Operator command reference for the local AI stack (Ollama / NemoClaw / OpenShell) + troubleshooting + state-file map. |
| `HANDOFF.md` protocol | Single living session-transfer doc; rewrite/amend after every significant task (memory `feedback_handoff_md_update_protocol`). |
| `ideas/<topic>.md` protocol | Living strategy docs; refresh after every gate decision / pivot / invalidated assumption (memory `feedback_ideas_docs_living`). |

---

## 3. Roadmap — the four headline bets, sequenced

These compound the system from a *manufacturing line you operate* into a *machine that operates itself*. Each is Spark-feasible now; each adds a durable abstraction to Fieldkit/Arena.

**The sequencing principle — `pane → hands → engine`.** The four bets are not independent; they have a dependency gradient, and the order is load-bearing. **Each phase makes the next more valuable, never the reverse** — and on a no-auto-push, single-lane box, *autonomy is useless without a control plane to approve and dispatch from*. So: build the **dashboard** (Arena as the operator's seat), then the **autonomy** (hooks + cron that the dashboard governs), then the new **engine** (closed-loop RLVR, dispatched and watched through everything above). Build the engine before the dashboard and you have a powerful loop with nowhere to land its output.

**Build-state correction (2026-06-02 ground-truth).** The original draft undersold what already exists, which changes the math: the **MCP harness is already built** — `fieldkit/src/fieldkit/harness/mcp.py` `build_mcp_server()` ships **7 working tools** (envelope, weight-footprint, throughput, perplexity, quantize [dry-run-default], publish [dry-run-forced], ask_second_brain), *not* a stub. The **Arena store already has a job-shaped socket** — `eval_runs` carries an `arq_job_id` column (schema drilled for a queue). **All 7 `fieldkit.eval` verifiers exist.** Genuinely unbuilt: the dispatcher glue, the cron layer, hook *expansion* (only **one** `SessionStart` hook today), and the entire RLVR stack (`fieldkit.reward`/`fieldkit.rl`/`g6_*` — all absent). So the lowest-marginal-effort bet is the control plane (inputs + execution surface already present), which is exactly why it goes first.

---

### Phase 0 — Bet 4: Workflow-native orchestration (free, parallelizable now)

**The leverage.** Several skill chains are sequential where parallel fan-out + adversarial verify would compound throughput at constant wall-clock. The `Workflow` tool (deterministic JS orchestration over subagents) is unused. **Zero new infra, no envelope cost** — so it runs *now*, in parallel with everything below, and accelerates the artifact flow (scout / corpus / review) *into* the Arena being wired in Phase 1.

**Highest-ROI targets.** `frontier-scout` → parallel arxiv/HF/PWC finders + per-paper feasibility verifiers, synthesized to one ranked report. `claude-corpus-synth` → parallel generators with the `verify_chunk` gate as the per-item barrier. Article/card polish + `code-review` → dimension fan-out (correctness · voice · NARRATIVE-CONTRACT compliance · secret-scan) then synthesis.

**Canonical shape** (drop-in for the scout sweep):
```js
const found = await pipeline(
  SOURCES,                                   // [arxiv, hf, pwc, ...]
  src => agent(`sweep ${src.name} for <taxonomy>`, {schema: PAPERS}),
  papers => parallel(papers.hits.map(p => () =>
    agent(`Spark-feasibility verify: ${p.title}`, {schema: VERDICT})
      .then(v => ({...p, verdict: v})))));
const promotable = found.flat().filter(p => p.verdict?.feasible);
```

**Measured grounding** (`_SPECS/roadmap-reconciliation.md`). The corpus confirms the throughput-at-constant-cost premise — `autoresearch-agent-loop` ran **50 agent trials in 73 min for ~$0.02** on one GB10; the lineage ablation in `auto-research-loop-on-spark` showed **5.3× more keeps** (16 vs 3) from structured visibility alone. But it sharpens *where* the win is: `trajectory-eval-is-the-agent-flailing` measured a **72% proposal-repeat rate** and only 14 unique trials/50 — so the fan-out's value is as much **dedup + memory** as parallelism. Bake an anti-repeat + widened-history gate (`block_repeat(last_k≈50)` + `render_history(k≈30)`) into the canonical shape; it is estimated to lift unique trials ≈**4×** at constant wall.

---

### Phase 1 — Bet 3: Arena as the control plane (the pane)

**The leverage.** Arena today (spec `_SPECS/spark-arena-v1.md`, M1–M7) records lanes, chats, compares, and exports a leaderboard mirror. Promote it from **recorder** to **central nervous system**: the place that *triggers* work. A `compare` loss auto-enqueues an RLVR job (Phase 3); a leaderboard regression triggers a re-quant; a stale bench schedules a re-eval (Phase 2's cron). This is the bet where the operator stops *running scripts* and starts *dispatching and watching* — the posture the whole thesis is about.

**Why first.** Both its inputs and its execution surface already exist (see the build-state correction): `fieldkit.arena` has the store (with the `eval_runs.arq_job_id` socket pre-drilled), and `fieldkit.harness` has the live 7-tool MCP surface to dispatch *through*. M8 is connective tissue, not greenfield.

**Concrete build.** `fieldkit.arena` gains a `jobs` table + a dispatcher hung off the existing `arq_job_id` hook. **The dispatcher executes through the MCP harness** (not ad-hoc `g3_*` shelling) — single execution surface shared with Hermes, so the safety rails (`quantize` dry-run-default, `publish` dry-run-forced) are defined once and never diverge. **First job type = eval re-run / re-measure** ("leaderboard regression → re-eval"): deterministic, already exists, meaningful day one. Phase 1's needs *grow* the harness — add `measure_variants` / `run_vertical_eval` tools to `fieldkit.harness` as the dispatcher requires them, so the MCP surface is built by genuine demand, not speculation (this is where Phase 1 and Phase 2's harness work partially merge). Extends the spec as an **M8 milestone** — **now written: `_SPECS/spark-arena-v1.md` §12** (8 locked decisions, `jobs`/`job_triggers` schema, the MCP-routed dispatcher, leaderboard-regression trigger, R13–R17, release gate `fieldkit v0.16.0`; spec-only, unbuilt); the new `jobs` table stays **out** of `export_publishable_slice()`'s `PUBLISHABLE_TABLES` allowlist so the public mirror never leaks job prompts.

**Measured grounding** (`_SPECS/roadmap-reconciliation.md`). Dispatch-through-the-MCP-harness is **already validated end-to-end, not theoretical**: `hermes-drives-the-spark-via-fieldkit-mcp` shows the agent calling `measure_gguf_throughput`, the harness executing it on the GPU, and a real number returning (41.75 tok/s) at **0% tool-call format error** — confirming "M8 is connective tissue, not greenfield." It also sharpens the safety story: containment is **two-layer** — tool curation (the 7-tool list size *is* the policy; `publish` structurally unreachable) *plus* an execution sandbox (`hardening-the-hermes-harness-on-spark`: docker `--network=none`, 3/3 hostile calls contained). The dispatcher inherits both.

---

### Phase 2 — Bet 2: Autonomous harness + cron (the hands)

**The leverage.** Today there is **one** `.claude` hook (`SessionStart` build-failure check) and **no autonomous cron layer** — yet the entire thesis is self-operation. The Hermes spec names the keystone: **H4, fieldkit-as-MCP ("Hermes drives the Spark")** in `_SPECS/hermes-harness-v1.md`; the MCP surface that realizes it already exists (Phase 1 grows its coverage), so Phase 2 adds the *autonomous* layer on top of working synchronous dispatch.

**Why now (SOTA).** The 2026 Claude-Code best-practice stack is five layers — **CLAUDE.md · MCP · skills · hooks · subagents** — and we run only three-and-a-fraction (CLAUDE.md, skills, subagents, one hook, the MCP surface unwired to cron). Hooks (deterministic automation/safety) and a *scheduled* loop are the missing leverage. Karpathy's ~100-runs/night is the existence proof that a single GPU + an agent loop manufactures experiments overnight.

**Concrete Spark build.** (a) **Expand the lone hook** into post-publish → auto `nvidia-learn-stats`; pre-commit → run `verify_*`; post-article → secret-scan. (b) **Cron layer** (`/schedule` / cron) draining the Arena jobs queue overnight — **sequential model loads only** (one lane / OOM envelope; parallel is a DGX-Cloud config per §6). (c) **Morning-standup artifact** Arena renders (what ran / what regressed / what's queued) — the mandatory human-review surface the no-auto-push invariant demands: cron *stages + opens a review*, never pushes, and the standup is the gate. (d) **Budget governor** `fieldkit.budget` the cron layer consults *before* launching — generalizes the corpus-synth weekly-cap `/usage` gate + the OOM-envelope check into one guard (memories `project_spark_unified_memory_oom`, the corpus-synth preflight pattern). (e) **Freshness-monitor job** realizing Ch-11's named-but-unbuilt "Freshness Monitoring" box as a scheduled bench re-run that *emits* regression triggers into Phase 1's dispatcher — the trigger source that makes the plane autonomous rather than button-driven. The substrate is half-wired: `.claude/scheduled_tasks.lock` exists (a lock file, not yet a scheduler), and the **drain + regression-producer are already built** (`arena/jobs.py` `drain_jobs()`/`check_and_enqueue_regressions()`, both commented "the Phase-2 cron will call this on a schedule") — Phase 2 adds the *scheduler*, not the dispatch. **Now written: `_SPECS/spark-arena-v1.md` §15 (Arena M11)** — 9 locked decisions (AH-1…9, decisions-locked + unbuilt), placement chosen as an Arena section consistent with M8/M9/M10; new `fieldkit.budget` governor (`LOCAL_CEILING=33%`), M9 cost-plane a soft prerequisite, release gate ~`fieldkit v0.19.0`.

**Measured grounding** (`_SPECS/roadmap-reconciliation.md`). Every *prerequisite* is measured and in place — the brain is pinned by evidence (`picking-the-hermes-brain-on-spark`: **Qwen3-30B-A3B Q4 at 83.5 tok/s / 31.8 GB / 8/8**, where the 9B hits a hard 2/5 multi-step wall, so the MoE is non-negotiable for overnight reasoning), and the sequential-load envelope is validated (`hermes-vertical-router-on-spark`: brain + one vertical ≈ 50 GB, **78 GB headroom**). The gap §3 names is *real* (no article shows cron, a hook battery, or a morning-standup flow). The one sharpening: `hermes-cost-routing-local-and-openrouter` measured a **33% leak rate** — a third of the workload genuinely needs frontier escalation — so `fieldkit.budget` must encode **failure-mode-driven escalation** (when local *gives up*), not just a token ceiling.

---

### Phase 3 — Bet 1: Closed-loop RLVR (the engine — the eval harness *is* the reward model)

**The leverage.** `fieldkit.eval` already ships deterministic verifiers: `patent_claim_validity` (7-dim), `office_action_argument` (4-dim), `prior_art_relevance` (Spearman ρ), `irac_structure` (4-checklist regex), `mcq_letter`, `numeric_match`, `is_refusal` (all 7 confirmed present + exported). These are *exactly* the well-formed verifiers that GRPO/RLVR needs. We are currently doing **SFT corpus-synth** (expensive, in-session, capped by template combinatorics). The disruptive move closes the loop: **eval → reward → fine-tune → re-eval**, with our own scorers as the reward function.

**Why last.** It's the deepest, most compute-hungry, most uncertain bet — and it's the *payload*, not the delivery system. Built last, it lands into a system that already dispatches it (Phase 1 Arena), schedules it (Phase 2 cron), watches it (Phase 2 standup), and parallelizes its eval side (Phase 0 fan-out). A `compare`-loss in Arena auto-enqueues an `rl_run`; the result flows back to the leaderboard — **the loop closes visibly**, which is the entire reason the pane was built first.

**Why now (SOTA).** GRPO is the 2026 post-training default behind R1-class reasoning models; it **drops the learned reward model** (the verifier scores directly), works on a **single GPU** with **<100 examples**, and is supported by both NeMo-RL (single-GPU → multi-node) and Unsloth's RL guide. Verifiable-reward RFT lifts small (1–10B) models to competitive reasoning — precisely the Spark's weight class.

**Concrete Spark build.** `scripts/g6_grpo_loop.py` — and the corpus says **wrap the hand-rolled REINFORCE-with-KL loop that already worked, not a library**: `clawgym-on-spark-grpo` drove a real single-GB10 GRPO run with a **~280-LOC** trainer + kill-and-restart vLLM, *not* Unsloth-GRPO or NeMo-RL (neither verified on the Spark yet). A thin adapter turns any `fieldkit.eval` scorer into a reward callable; loop: sample group → score with verifier → GRPO step (LoRA) → re-run `g3_measure_variants` → log `fieldkit.lineage` Trial. Respect the envelope: trainer resident, one lane. New artifact kinds **`verifier`/`reward`** (the scorer pack) and **`rl_run`** (the lineage of a loop). Per `feedback_keep_scorer_local_until_reuse`, promote the reward adapter to `fieldkit.reward` only on second reuse. **Lineage → tech-writer auto-seed:** when an `rl_run` lifts a bench >X%, auto-scaffold a `tech-writer` seed (mirrors `frontier-scout`→`tech-writer`) — wiring the Ch-11 recursion so the autonomous loop *feeds* the editorial→Book pipeline (§2A).

**Measured grounding** (`_SPECS/roadmap-reconciliation.md`). Core feasibility **confirmed**: `clawgym-on-spark-grpo` ran 34 GRPO steps in 8.5 h on a **42-task pool** (verifier-as-reward, no learned RM) and lifted task_complete **0/158 → 154/158**; envelope holds (~30 GiB margin). But three corrections the abstract claim misses: **(1)** the bottleneck is the **vLLM restart (~3.5 min/step), not the trainer (~22 s)** of a ~15 min step — closing the vLLM hot-LoRA-swap gap is the top wall-clock win. **(2)** A **training-pool ↔ held-out inversion** is the key risk (`t2po-…`: pool 87.5% vs held-out 5.7% at step 45, **81.8 pp gap**; per-assertion plateaus ~47.7%) — so **held-out eval every ~10 steps is a hard gate**, pool-convergence is a trap. **(3)** Binary reward **mode-collapses** (`trajectory-eval` / `distill-architect-lora-from-trajectories`: 0/8 held-out from a 42-row corpus) — `fieldkit.reward` must emit a **`(success, failure_class, auxiliary)`** tuple (cf. the 9-class status enum in `auto-research-loop`) over a **≥100-row corpus**. Pin the vLLM version: `runtime-frontier-six-patches-on-spark` saw 6 API drifts across 2 minor versions.

**Abstraction added.** `fieldkit.reward` (scorer → reward adapter) + `fieldkit.rl` (GRPO driver over Unsloth/NeMo-RL). **Spec stub: `_SPECS/rlvr-loop-v1.md`.**

---

### Cross-cutting — Bet 5: The recall layer (the Second Brain as a control-plane-managed knowledge pipeline)

**The leverage.** §1 invokes Ch-10's *continuously-updated world model* and the Ch-11 recursion, but the roadmap never cashes out the **read-back** half: the system *writes* artifacts (articles → Book, §2A) yet has no governed way to *query its own past work — or the frontier's*. The Second Brain is that missing half — today a **manual, article-prose-only** RAG index behind the live `ask_second_brain` MCP tool. Promote it from a one-off script into a **control-plane-managed knowledge pipeline** (ingest → index → eval → serve → query) the **operator drives from Arena**. This is *not* a sequential phase — it's the **memory the pane, hands, and engine all consult**, so it threads all three rather than slotting after one.

**It indexes three source classes — one recall surface over all:**
1. **Internal experiment memory** — `fieldkit.lineage` trials, `eval_runs`, `rl_run` cards, `evidence/` summaries. Prose-RAG → *measured-experiment*-RAG (the exact gap the 2026-06-02 harvest hit: `ask_second_brain` was prose-only, so it couldn't return the numbers and the harvest fell back to a disk-read fan-out).
2. **Published prose** — `articles/*` (+ Book sections); what today's index already holds (and what we're re-indexing now, repointed at the monorepo after it sat stale at 12/63).
3. **External research (the scout crossover)** — `frontier-scout`'s `papers.json` + per-paper **Spark-feasibility verdicts**, and `deep-research` cited reports. A scouted-but-rejected paper then persists in the index as *"evaluated, infeasible because X"* — the **external** cure for re-scouting amnesia, mirroring the **internal** `autoresearch-agent-loop` 72%-repeat cure.

**Provenance is a first-class field.** A common knowledge-card schema (`source · kind · date · claims · feasibility/verdict · link`) lets retrieval **filter by trust** — a Spark-*measured* number and an external-*claimed* one are not interchangeable. This bakes the harvest's confirms / sharpens / **complicates** discipline (`_SPECS/roadmap-reconciliation.md`) into the index itself.

**Why it's grounding, not greenfield.** The components are shipped and measured: `naive-rag-on-spark`, `pgvector-on-spark`, `nemo-retriever-embeddings-local`, `rerank-fusion-retrieval-on-spark`, `guardrails-on-the-retrieval-path`, `bigger-generator-grounding-on-spark` build the retrieval stack; `rag-eval-ragas-and-nemo-evaluator` (+ the on-disk harness in `rag-eval-work/`: `retrieve.py`, a `qa-eval` set, `nemo_evaluator_config.yaml`) is the **RAG-eval** half; `mcp-second-brain-in-claude-code` is the query surface; `frontier-scout` / `deep-research` already *produce* the external sources. The bet is **consolidating these producers into one managed, evaluated, operator-driven index**, not inventing them.

**What the control plane drives (the operator UX).** Arena gains a **knowledge/RAG pane** — the first non-trivial pipeline the M8 dispatcher runs end-to-end, and the cleanest dogfood (the machine managing its own memory):
- **Coverage + freshness** across all three source classes — what's indexed, stale, or missing, with chunk counts; the silent lag that bit the harvest becomes a visible, actionable number.
- **Re-index** — a manual button *and* an auto-on-publish hook (Phase 2); full-rebuild or incremental.
- **RAG-eval trend** — re-run the existing harness after each index (recall@k, faithfulness, the RAGAS / NeMo-Evaluator metrics already in the corpus) and chart the score; index promotion can **gate** on it (don't ship a rebuild that drops recall@k).
- **Query / inspect** — the operator's own provenance-filtered, cited `ask_second_brain` console.

**Cross-phase wiring.** *Pane* (Phase 1): the Arena knowledge pane + dispatcher job types `reindex`, `rag_eval`, `scout_ingest`. *Hands* (Phase 2): the **re-index-on-publish hook** (fixes today's staleness at the source) + a **scheduled freshness monitor** that re-runs RAG-eval *and* kicks a `frontier-scout` sweep whose results land back in the index — finally realizing Ch-11's named-but-unbuilt "Freshness Monitoring" box. *Engine* (Phase 3): the index ingests `rl_run`/`lineage` cards, and the **pre-flight pattern spans internal + external** — a `compare`-loss trigger queries the Second Brain *before* the governor approves an RLVR job, returning *both* the internal `t2po` finding (47.7% per-assertion ceiling, +33% wall for nothing) *and* any external paper verdict, so the run is declined or redirected.

**The new engineering (honest).** (a) Extend ingest from `articles/*` to **lineage / eval / `rl_run` cards + scout / deep-research outputs**, all under one provenance-tagged knowledge-card schema. (b) **Freshness automation** (publish hook + monitor + scheduled scout sweep). (c) Wire the one-off `rag-eval-work/` harness as a **recurring dispatcher job** with a tracked score. (d) Build the **Arena knowledge pane**. **Abstraction added:** `fieldkit.memory` — the managed multi-source index + provenance-aware query API behind `ask_second_brain` — over `fieldkit.lineage` + the retrieval stack + the scout producers. **Spec stub: `_SPECS/second-brain-pipeline-v1.md`** (an Arena milestone — the operator-facing knowledge-pipeline surface).

---

### Cross-cutting — Bet 6: The cost plane (token economics as a first-class decision axis)

**The leverage.** The stack already mixes **local** lanes (NIM / llama.cpp, ~$0 marginal) with **hosted/paid SOTA** lanes (OpenRouter frontier) — and Arena already *computes* per-call spend (`_compare_cost_usd()` → `_openrouter_cost_usd`, streamed on `/api/telemetry/stream`). But it ranks lanes by quality and tok/s and **drops cost on the floor**: `arena.db` has no `cost_usd` column, the leaderboard mirror carries none, the cockpit shows no `$`, and the live accumulator resets on every sidecar restart. Cost is the axis a solo builder *and* an enterprise rank first when scaling hosted SOTA alongside local — and it's the only one the pane discards. Promote it to a **persisted, charted, first-class column** so every hosted-vs-local choice is made on **$/task and $/quality-point next to quality and speed** — and feed that ledger to the governor (Phase 2) and the RL-vs-pay ROI (Phase 3). Like the recall layer, this is *not* a sequential phase — it's the **price signal the pane, hands, and engine all consult**, so it threads all three.

**Why it's grounding, not greenfield.** The pieces are shipped and measured. `fieldkit.harness` ships a deterministic **`CostRouterConfig`/`RouteTier`** (per-M input/output pricing, `.estimated_cost_usd()`, `.render_yaml()`) — auditable, snapshot-based, no live billing queries. `fieldkit.arena.server` already meters OpenRouter spend in-flight (`_openrouter_price_for()`, `_openrouter_catalog()` live-fetch + `_OR_FALLBACK_MODELS` snapshot, `add_openrouter_cost()`). And the economics are *published*: `hermes-cost-routing-local-and-openrouter` measured **local-only 8/12 at $0.00, cost-routed 11/12 at $2.19/100 tasks, frontier-only 12/12 at $2.94/100** behind a `--cap-usd` hard stop — a **25% spend cut at an 8.3% quality cost**, with a **33% leak** (a third genuinely needs frontier). Phase 0's `autoresearch-agent-loop` adds the other end: **~$0.0004/failed trial** on the Spark, the cost-to-failure inversion that makes wide local exploration free. The bet is **persisting + surfacing** what's already computed, not inventing it.

**What the control plane drives (the operator UX).** Arena's **compare view and leaderboard gain a cost axis** — `$/task` and a derived **`$/quality-point`** beside `median_tok_per_s` and the quality score — so "hosted SOTA or local?" is answered on three axes, not two. Backed by a **price-snapshot table** (`openrouter_price_snapshot`, pinned at import — the same known-drift discipline as `spark-hermes-cost-router.yaml`'s baked snapshot) so a comparison stays reproducible even as live prices move.

**Cross-phase wiring.** *Pane* (Phase 1): persist the already-computed `_compare_cost_usd()` into `arena.db` (`cost_usd` on `compare_responses` / `chat_turns` / `compare_runs`) + the `openrouter_price_snapshot` table; surface `$/task` + `$/quality-point` in the leaderboard mirror and cockpit — the price snapshot is public-safe but per-run cost rides prompt rows, so it stays **out** of `export_publishable_slice()`'s `PUBLISHABLE_TABLES` allowlist (same discipline as the `jobs` table in Phase 1). *Hands* (Phase 2): **`fieldkit.budget` becomes the cost plane's enforcement arm** — it consults the persisted per-lane ledger, encodes **failure-mode-driven escalation** (the `LOCAL_CEILING = 33%` leak constant — escalate when local *gives up*, not on a token ceiling alone), generalizes H6's `--cap-usd` hard stop, and emits a **spend digest** (today's $ by lane / by bench vs cap) into the morning standup. *Engine* (Phase 3): **$/quality-point ROI** — generalize the $0.0004/failed-trial inversion to the live question "cheaper to RLVR a local model to threshold, or pay frontier per call?"; a `compare`-loss trigger consults measured $/quality *before* the governor approves an `rl_run`, declining RL when frontier escalation is cheaper at equal quality (mirrors Bet 5's pre-flight gate).

**The new engineering (honest).** (a) Add `cost_usd` columns + the `openrouter_price_snapshot` table to `fieldkit.arena.store`; INSERT the cost already computed on every completion (today ephemeral, in-memory only). (b) Wire real token counts from the OpenAI-compat response into `tokens_in`/`tokens_out` (today partly estimated via the 4-char heuristic). (c) Render `$/task` + `$/quality-point` in the leaderboard JSON and the cockpit compare cell. (d) Have `fieldkit.budget` read the persisted ledger + emit the standup spend digest. **Abstraction added:** `fieldkit.cost` — the price-snapshot + per-run cost ledger + $/quality decision API, over the shipped `CostRouterConfig` (harness) + the Arena meter; feeds `fieldkit.budget` (Phase 2). **Spec stub: `_SPECS/cost-plane-v1.md`** (an Arena milestone — the cost axis on compare/leaderboard).

---

## 4. Fieldkit & Arena enhancement summary

| Proposed abstraction | What it abstracts | Builds on | Phase | Effort |
|---|---|---|---|---|
| `fieldkit.arena.jobs` | job table + dispatcher (eval/quant/RL triggers) | `fieldkit.arena` store + `eval_runs.arq_job_id` socket | 1 | M |
| `fieldkit.harness` (extend coverage) | add `measure_variants` / `run_vertical_eval` MCP tools | **live** `build_mcp_server()` (7 tools already) | 1→2 | S |
| `fieldkit.budget` | weekly-cap + OOM-envelope guard the cron layer consults pre-launch | corpus-synth `/usage` gate, `spark_envelope.py` | 2 | S |
| new kind: `standup` | daily ran/regressed/queued digest = the human-review gate | `fieldkit.arena` jobs + `fieldkit.lineage` | 2 | S |
| `fieldkit.reward` | scorer → GRPO reward callable | `fieldkit.eval` verifiers (all 7 present) | 3 | S |
| `fieldkit.rl` | GRPO/RLVR driver (Unsloth + NeMo-RL lanes) | `g3_train_*`, `fieldkit.lineage` | 3 | M |
| new kinds: `verifier`/`reward`, `rl_run`, `agent_run` | publishable scorer packs + loop lineage + agent traces | `fieldkit.publish.ARTIFACT_KINDS` | 3 | S |
| `fieldkit.memory` | provenance-tagged multi-source recall index (articles + lineage/eval/`rl_run` + scout/deep-research) + query API behind `ask_second_brain` | live `ask_second_brain` tool + `fieldkit.lineage` + `ingest_blog` + `frontier-scout` | 5 (1→2) | M |
| Arena knowledge/RAG pane | operator UX: coverage·freshness·re-index·RAG-eval trend; dispatcher `reindex`/`rag_eval`/`scout_ingest` jobs | `fieldkit.arena.jobs` (M8) + the `rag-eval-work/` harness | 5 (1) | M |
| `fieldkit.cost` | price-snapshot + per-run cost ledger + $/quality decision API; feeds `fieldkit.budget` | **live** `CostRouterConfig` (harness) + Arena in-memory meter (`_compare_cost_usd()`) | 6 (1→2) | M |
| Arena cost axis (store + leaderboard + UI) | `cost_usd` cols on compare/chat/runs + `openrouter_price_snapshot` table + $/task & $/quality-point in leaderboard + cockpit cost cell | `_compare_cost_usd()` + `arena.store` schema + `leaderboard.json` | 6 (1) | M |

Each extends, not replaces, the existing manifest-first, lazy-import, duck-typed design. The harness row is **S not M** because `build_mcp_server()` already ships 7 tools — Phase 1 only adds the measure/eval tools its dispatcher calls.

---

## 5. New-artifact brainstorm *(lateral / speculative)*

Solo-bootstrap-friendly, Orionfold-monetizable directions — clearly uncommitted. Where one rides a §3 phase, it is sequenced against it (dogfood internally, *then* productize):

- **Eval-as-a-service leaderboard → Arena M9** (*downstream of Phase 1's M8*). Arena's leaderboard opened up: bring your GGUF, get scored on the Orionfold vertical benches, appear ranked. Explicitly *after* the internal control plane works — dogfood the dispatcher on your own quants, then open it to submissions (the same `export_publishable_slice` allowlist discipline keeps the jobs table private).
- **Self-improving "living model" line** (*a Phase-3 RLVR product*). A model re-RLVR'd weekly against a freshening bench; the selling point is that it *keeps getting better*, with a public delta chart from `fieldkit.lineage`. Rides the Phase-3 `rl_run` loop + the freshness-monitor job (Phase 2).
- **Verifier/reward packs** (*the Phase-3 `verifier`/`reward` new kinds, productized*). The `fieldkit.eval` scorers published as standalone `kind: verifier` artifacts — a sellable domain-eval suite + the reward function to train against it. The eval *is* the product.
- **Agent/skill artifacts as products** — Hermes profiles and Claude skills already have `kind: skill`/`harness`; package the best ones (e.g. the whole vertical-curator loop) as a one-command installable.
- **DGX-Spark "recipe" artifacts** — reproducible one-command stacks (serve + bench + a notebook) that turn an article into a runnable appliance.
- **Arena-as-a-product** — already the plan (`pip install fieldkit[arena] && fieldkit arena up`, per `_GUIDES/arena-storefront-marketing.md`); the local-runnable cockpit *is* the flagship app, and Phase 1 makes it a control plane buyers can drive, not just a recorder.
- **Managed local-knowledge appliance** (*the Bet-5 recall layer, productized; rides Phase 1*). The control-plane-driven Second Brain — ingest your own docs + research, index, RAG-eval, query — packaged in the same local cockpit (`fieldkit[arena]`). Dogfood it on this repo's own corpus first, then ship "bring your docs, get a *measured* local RAG you operate, not a SaaS." The **provenance/trust filter + a tracked RAG-eval score** are the differentiators a hosted RAG can't honestly claim.

---

## 6. Looking Beyond Spark (frontier extrapolation)

The same workflows scale up the NVIDIA ladder — teach the arithmetic on the Spark, extrapolate to hardware it can't run (series memory `project_looking_beyond_spark_series`):

- **Quant pipeline** → on H100/H200 the base-model ceiling rises (70B+ FP, full-precision benches); the 4-axis measurement harness is unchanged, only the envelope math changes.
- **RLVR (Bet 1)** → Spark does **LoRA-GRPO** on 7–8B; a B200/SuperPOD does **full-parameter GRPO** on 30–120B (e.g. Nemotron-3-Super, 120B/12B-active — now agentic-usable on a single Spark at 14.4 tok/s, so the *driving* fits even where the *training* doesn't).
- **Autonomous harness (Bet 2)** → Spark runs **sequential** overnight jobs (one lane); DGX Cloud runs the **same queue in parallel** across nodes. The orchestration code is identical; concurrency is a config.

The discipline stays solo-bootstrap: prove the loop cheaply on the Spark, rent frontier hardware only for the one run that needs it.

---

## 7. Known drift / open questions

*(Bounded, per NARRATIVE-CONTRACT style.)*

- **The phases are sequenced, not yet built — but the substrate is further along than the original draft claimed.** Phase 0 (Workflow fan-out) needs no new infra. Phase 1 (Arena M8) extends a store that already has the `eval_runs.arq_job_id` socket and dispatches through an MCP harness that **already ships 7 tools** (`build_mcp_server()` is live, not stubbed). Phase 3's reward substrate (all 7 `fieldkit.eval` verifiers) is present. Genuinely absent: the dispatcher glue, the cron layer, hook *expansion* (one `SessionStart` hook today), and the RLVR stack (`fieldkit.reward`/`fieldkit.rl`/`g6_*`). **Phase 1 / Arena M8 is now SHIPPED end-to-end** (`_SPECS/spark-arena-v1.md` §12 spec → BUILT §12.7 → `fieldkit v0.16.0` → launch article `606333d`). Of the four remaining stubs, **`cost-plane-v1`, `second-brain-pipeline-v1`, AND `autonomous-harness-v1` are now WRITTEN** (`_SPECS/spark-arena-v1.md` §13 [Arena M9] + §14 [Arena M10] + §15 [Arena M11], decisions locked 2026-06-02, all unbuilt); only the Phase-3 engine remains named-not-written. Prioritized write order (2026-06-02, post-M8): **`cost-plane-v1` ✅ → `second-brain-pipeline-v1` (Bet 5, M10) ✅ → `autonomous-harness-v1` (Phase 2, M11) ✅ → `rlvr-loop-v1` (Phase 3) ▶ next/last**: the two cross-cutting bets ride the now-shipped pane and are *inputs* to a fully-realized Phase 2 (the M11 budget governor reads the Bet-6 ledger; the freshness monitor drives the Bet-5 re-index), so they preceded the Phase-2 spec, which in turn references those defined contracts instead of dangling them. The engine lands last, into everything above. See `_SPECS/index.md` (Planned queue) + `HANDOFF.md` (▶ NEXT UP).
- **Cron substrate is half-wired** — `.claude/scheduled_tasks.lock` exists but it is a **lock file, not a scheduler**; no scheduled agents are defined.
- **§3 is now grounded against measured evidence** (`_SPECS/roadmap-reconciliation.md`, 2026-06-02) — the sequencing survives, but two §3 abstractions were wrong and one risk was missing: Phase 3 named **Unsloth/NeMo-RL** where a **hand-rolled REINFORCE loop** is what actually ran on the Spark; the GRPO bottleneck is the **vLLM restart, not the trainer**; and the **training-pool↔held-out inversion** (an 81.8 pp gap) is a real failure mode §3 didn't flag (held-out-every-10-steps is now a hard gate in the grounding). Phase 1's "dispatch through the MCP harness" is **validated end-to-end, not theoretical**. These are folded into §3's per-phase *Measured grounding* notes; the spec stubs should open against the numbers there.
- **The recall layer (Bet 5) is grounding-rich but only half-built.** The retrieval components + RAG-eval harness + scout producers are shipped (articles + on-disk code in `rag-eval-work/` + `frontier-scout`), but the Second Brain index is **article-prose-only and manually re-indexed** — stale by default: it held **12/63 articles** at the 2026-06-02 harvest (its `ingest_blog.py` still pointed at the retired `nvidia-learn` path); re-index repointed it at the monorepo that day. Structured-lineage + external-research coverage, the provenance-card schema, the re-index-on-publish hook, the recurring RAG-eval + scheduled scout sweep, and the Arena knowledge pane are all unbuilt. **Spec now WRITTEN** — `_SPECS/spark-arena-v1.md` §14 (Arena M10 recall layer), 12 locked decisions signed off 2026-06-02 (promote the pre-drilled `reindex`/`rag_eval`/`scout_ingest` job stubs; `fieldkit.memory` over the existing `fieldkit.rag.Pipeline`; multi-source provenance card on `blog_chunks`; eval-gated re-index; `/arena/knowledge/` pane; version-control the external `ingest_blog.py`/`qa-eval`/SB-server) — **spec-only, unbuilt**; the half-built gap closes when M10 ships. Code-reconciled finding: the `arena/jobs.py` sockets for these three job kinds are **already drilled** (named stubs excluded from `DISPATCHABLE`), so M10 is connective tissue like M8.
- **The cost plane (Bet 6) computes cost but discards it.** `fieldkit.harness` ships a deterministic `CostRouterConfig` (per-M pricing, `.estimated_cost_usd()`, `.render_yaml()`) and `arena.server` meters OpenRouter spend live (`_compare_cost_usd()`, streamed on `/api/telemetry/stream`) — but it is **in-memory only**: `arena.db` (`compare_responses`/`chat_turns`/`compare_runs`) has **no `cost_usd` column**, the leaderboard mirror carries none, the cockpit renders tok/s + quality but no `$`, and the accumulator resets on every sidecar restart. The H6 evidence the cost-routing article cites (`evidence/openrouter_prices.json`, `cost_router_results.json`) is **not version-controlled**. So the hosted-vs-local cost comparison is calculated and thrown away. **Spec now WRITTEN** — `_SPECS/spark-arena-v1.md` §13 (Arena M9 cost plane), 10 locked decisions signed off 2026-06-02 (persist the computed cost on the prompt tables; aggregate `$/quality-point` on the public leaderboard; `openrouter_price_snapshot` pinned from the H6 JSON; `fieldkit.cost` ledger; version-control the H6 evidence as M9-10) — **spec-only, unbuilt**; the calculated-and-discarded gap closes when M9 ships.
- **Stale memory pointer** — memory `project_uber_corpus_decision_doc` references `ideas/uber-local-corpus-gen-decision.md`, which **does not exist**; the only live ideas doc is `ideas/ai-field-notes-consolidation.md`. (Fix the memory next HANDOFF pass.)
- **`sync-field-notes` is legacy** but still installed; left for history, not for use. (Its dead `mirrors/destination-overrides.md` references — and the matching ones in `_SPECS/spark-arena-v1.md` + `src/content/artifacts/README.md` — were cleared 2026-06-02; removing the skill itself is a separate open call.)
- **Doc consolidation (2026-06-02).** Active guidance moved to `_GUIDES/` (`narrative-contract.md`, `product-articles.md`, `arena-distribution.md` ← `APP-SYNC.md`, `arena-storefront-marketing.md` ← `APP-MARKETING.md`, `local-ai-stack-commands.md` ← `COMMANDS.md`) with `_GUIDES/index.md`. All specs/plans/designs folded into `_SPECS/` (active at root, superseded under `_SPECS/archive/`) with `_SPECS/index.md`; the four active specs moved `specs/` → `_SPECS/` and every live reference (skills, `src/content.config.ts`, `fieldkit` source + `docs/api/`) was rewired. `handoff/`, `mirrors/`, `MAC-TO-SPARK-TRANSITION.md`, `SYNC-WORKFLOW.md` deleted. **Deliberately not rewired** (historical/immutable): `fieldkit/CHANGELOG.md`, `evidence/*.json` `spec_ref`, and one article's external archived-repo permalink.

**Refresh protocol.** Update §2 when a workflow/skill/spec changes; graduate a §3 bet into §2 when it ships; bump the "Last updated" stamp in the header comment each pass.
