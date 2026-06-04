---
project: astrodynamics-vertical
version: v1.0
status: LOCKED (decisions signed off 2026-06-04) — A+B BUILT, C unbuilt
created: 2026-06-04
authoritative: Spark
---

# Astrodynamics Vertical v1.0 — Project Specification

> The project's **first end-to-end, scout-to-RLVR, brand-new** Orionfold model: a
> **text-in / numeric-out astrodynamics + quantitative-astrophysics** reasoning model. This
> spec is the **application** of the already-built engine ([`rlvr-loop-v1.md`](rlvr-loop-v1.md))
> to a greenfield domain — the parallel of [`patent-strategist-v1.md`](patent-strategist-v1.md),
> which was the first *SFT* vertical; this is the first *RLVR* vertical. It does **not** re-spec
> the engine; it wires an astro reward + corpus into it and drives the loop through the Arena
> control plane.
>
> **Two goals, equally weighted:** (1) ship a clean greenfield vertical, and (2) **stress-test the
> whole control plane (M8→M9→M10→M11→engine→lane) on its first real-GPU run** — the engine + the
> rl-lane-autonomy layer are today proven only against injected fakes (`gpu_seams` vendored but
> never live-driven; `LaneArbiter` / `MemoryWatchdog` / the live progress strip / the budget brake
> fake-tested). Per the dogfood thesis (`dogfood_finds_mock_blind_bugs` — driving the live cockpit
> found the `rag_eval` missing-`import json` bug the suite slept through), the missing Arena
> features will **fall out of the run**, not be planned.
>
> **Strategy origin:** promoted from the gitignored `_IDEAS/astrodynamics-rlvr-vertical.md` (the
> living brainstorm scratch — Phase-C). That doc remains the running session journal; this spec is
> the tracked, decision-locked contract.

## 1. Context

### Why a brand-new vertical (not a patent-strategist re-RLVR)

Patent-strategist *could* RLVR soonest (it is the only vertical with bench + SFT adapter + verifiers
already built — it was the engine's test vertical), but it carries two drags a greenfield vertical
avoids:

1. **A known corpus flaw** — the open MPEP-hallucination issue
   (`[[project_patent_strategist_unsloth_unpublished]]`). RLVR only pushes on what the verifier
   scores, so it won't fix this — and could Goodhart it.
2. **Dataset license friction** — patent/legal data carries commercial-license constraints.

A greenfield vertical kills both and unlocks the control-plane stress-test + the chance to **thread
every earned gotcha from the scouting stage onward** (the scout's 4 traps, preflight-bench,
≥100-row floor, held-out-only selection, one-lane OOM discipline, EngineCore teardown,
reasoning-model `npredict`, explicit SFT EOS/BOS).

### Why astrodynamics specifically (the eval-is-reward fit)

The RLVR thesis is **the eval harness IS the reward — no learned reward model** (RV-2). So the
domain MUST produce **deterministically checkable answers**.

- ❌ Astronomy-as-trivia ("describe the Orion Nebula") → unverifiable prose; same weakness as patent claims.
- ✅ **Astrodynamics / quantitative astrophysics** → every answer is a **number with units**:
  orbital periods, Hohmann Δv, vis-viva, Kepler, redshift→distance, Schwarzschild radius,
  transit-depth→planet-radius. A **tolerance-based numeric verifier** is *easier* to build than
  patent's 7-dim rubric and is Goodhart-proof.

This pick wins three ways at once: **on-brand** (Orion → the launch identity 🌌), **world-class
eval-is-reward fit** (numbers are checkable), and **zero license friction** — the canonical
grounding sources are NASA / NASA-ADS / arXiv astro-ph, and the bench is **generator-authored off
uncopyrightable physics formulas**, so it ships clean (no FinanceBench-style misattribution that
skipped the dogfood Phase B).

### Modality decision (settled in `_IDEAS`, recorded here)

**Text-first.** WAN2 / generative video-diffusion is **OUT** — a different engine (diffusion-RL,
not the causal-LM REINFORCE trainer; no vLLM serving; no deterministic verifier → kills RV-2).
**VLM-understanding** (read a light curve / spectrum → numeric answer) is **staked as vertical #2**
(on-brand, still verifiable, the RV-9 second-vertical unlock) — but it is real new engineering
(VLM-LoRA trainer/serving + an image-bearing bench), so prove the loop on **text-astro first** on a
hardened stack.

### What is already BUILT (A + B, 2026-06-04)

- **A — base scouted + LOCKED = `Qwen/Qwen3-8B`.** `hf-model-scout` confirmed **no astrodynamics
  base exists at 6–9B** (`astrodynamics OR astrophysics OR orbital` → 0 hits → greenfield); report
  at `/tmp/hf-scout/2026-06-04/astrodynamics-7B/report.md`. Top-3 all apache-2.0 / chatml /
  llama.cpp-OK / one-lane-fit; Qwen3-8B won 95/100 on native `<think>` + 40K ctx.
- **B — bench generator + verifier-as-reward shipped at `scripts/astro_bench/`.** 16 formula
  templates (9 orbital + 7 astrophysics, ~70/30), `units.py` (stdlib SI normalization),
  `verifier.py::astro_numeric_match` (`\boxed{}`-extracting, unit-normalized, **binary, ±2%
  rel-tol**, dimension-mismatch hard-fail; conforms to the `fieldkit.eval` verifier signature →
  `RewardAdapter`-wrappable), `generate.py`, 20 real tests (pytest-green, ruff clean). Generated
  **v0.1 bench** (tracked) at `evidence/astrodynamics/astro-bench-v0.1.jsonl` (**120 pool**) +
  `…heldout.jsonl` (**44** = 40 different-seed + 4 hand curveballs; pool↔held-out disjoint via the
  `exclude` mechanism, RV-10). Every gold self-verifies; physics eyeballed (synodic 778.8 d ≈
  Mars's real 780 d).

**What remains (this spec's C):** SFT-init corpus → SFT-init LoRA → RLVR run → publish + editorial.

### Code reconciliation (verified against the built `fieldkit/src/fieldkit/`)

The engine is fully built; this vertical reuses it without modification:

1. **`fieldkit.reward`** ships `Reward(success, failure_class, auxiliary)` + `RewardAdapter(verifier,
   pass_threshold=1.0, scorer_kwargs={})` + `group_advantage(...)`. `RewardAdapter` accepts **any
   callable** matching the verifier signature and filters `scorer_kwargs` to the verifier's accepted
   args via `inspect.signature` — so it wraps the **local** `astro_numeric_match` directly, with
   **no `fieldkit.eval` promotion** (AV-2).
2. **`fieldkit.rl`** ships `GRPOConfig` (base, lora_rank=16, group_k=4, tasks_per_step=8, temp=0.8,
   heldout_every=10, vllm_pin, max_steps=34, corpus_min=100, heldout_frac=0.2, kl_coef=0.1, lr=1e-6,
   seed, heldout_patience) + `RLLoop(config, reward, bench, sampler=…, trainer=…, heldout_eval=…,
   lineage_store=…)` with **injected GPU seams** (torch/vLLM never import at module load) +
   `gpu_seams(config, *, reward=None)` that wires the real seams over `fieldkit[rl]`.
3. **The SFT-init is REQUIRED and external.** `fieldkit` has **no SFT training loop**:
   `_rl_gpu_trainer.py` raises *"FK_RL_ADAPTER_INIT is unset"* if the SFT-init LoRA is absent.
   `fieldkit.training` is **orchestration only** — `TrainRecipe` + `run()` (docker-exec to NeMo's
   `scripts/p65_train_nemo_lora.py` **or** a caller `TRAIN_SCRIPT`) + `merge_and_export()` (produces
   the merged-HF-bf16 dir that becomes `FK_RL_ADAPTER_INIT`) + `ReasoningProbe` (the preflight).
4. **The operator runbook** (`fieldkit/docs/api/rl.md` "Operator run") is the canonical C4/C5
   procedure: `pip install "fieldkit[rl]"`, serve a **pinned vLLM** with `--enable-lora` as a
   separate process, set the `FK_RL_*` env knobs, dispatch **async/overnight only**.

## 2. Scope

**In scope (v1 = one greenfield vertical, end-to-end):**
- The SFT-init corpus (worked-solution CoT over the 16 bench templates) + the SFT-init LoRA.
- The RLVR run on `Qwen/Qwen3-8B` through the built engine, reward = the local `astro_numeric_match`.
- The bench→task glue (local, `scripts/astro_bench/`).
- The publish tail: requant → GGUF → `Orionfold/<name>-GGUF`, the `kind: bench` artifact, the
  `living-model` launch promotion, and the `tech-writer` deep-dive.
- Driving the run through M8→M11 + the lane arbiter as the **first real-GPU control-plane exercise**.

**Out of scope (deferred / other specs):**
- **Any engine change** — `fieldkit.rl` / `fieldkit.reward` / `fieldkit.training` ship as-is. If a
  gap surfaces (e.g. an optional `adapter_init`), it's a separate engine spec, not this vertical.
- **Promoting `astro_numeric_match` to `fieldkit.eval`** — kept local until a 2nd vertical reuses it
  (`[[feedback_keep_scorer_local_until_reuse]]`, AV-2).
- **Publishable `verifier`/`reward`/`rl_run` artifact kinds** — deferred to second reuse (RV-9). The
  `kind: bench` artifact is allowed (it is one of the existing 8 kinds; AV-11).
- **VLM-astronomy (vertical #2)** + **WAN2 generative media** — separate engines (above).
- **The pinned aarch64+CUDA-13 vLLM install** — operator-owned external blocker (C4),
  `[[project_verl_atgpo_vllm_gap]]`.

## 3. Locked decisions (signed off 2026-06-04 — confirm before each build session)

| # | Decision | Value | Grounding (support / pushback) |
|---|---|---|---|
| **AV-1** | **Base = `Qwen/Qwen3-8B` (LOCKED)** | The native-`<think>` reasoner: apache-2.0, chatml, `qwen3` llama.cpp arch, 40K ctx, Q4≈4.83 GB / F16≈16.94 GB. | **SUPPORT** the scout 95/100 — best reasoning + native thinking + RLHF-aligned + longest ctx + Apache-2.0 at once; the thinking mode emits a parseable reason→number structure the verifier extracts cleanly. **PUSHBACK/caveat:** the thinking mode *forces* the AV-6 config moves — left at defaults it silently produces zero reward. Fallback = `Qwen2.5-Math-7B-Instruct` (purest math priors) **only if** problems stay under its 4K ceiling. |
| **AV-2** | **Bench + verifier = the BUILT `scripts/astro_bench/`; verifier kept LOCAL** | v0.1 = 120 pool + 44 held-out; reward = `astro_numeric_match` wrapped by `RewardAdapter`, **not** promoted to `fieldkit.eval`. | `[[feedback_keep_scorer_local_until_reuse]]` (promote on a 2nd vertical). `RewardAdapter` takes any callable → wraps the local verifier with **no promotion needed** to run (code-verified). |
| **AV-3** | **SFT-init LoRA is REQUIRED** | The engine mandates `FK_RL_ADAPTER_INIT`; the trainer raises if unset. Its job = **format-conditioning** (`<think>…</think>` + `\boxed{value unit}`) + domain warm-start. | Code-verified (`_rl_gpu_trainer.py`). A base that doesn't box answers → all rollouts score 0 → `group_advantage` returns zeros → **no gradient**. SFT-init is the format primer that makes step-0 rollouts parseable (RV-2/RV-3). |
| **AV-4** | **SFT corpus = `claude-corpus-synth` pattern, ~600 rows** | Session-model writes `<think>chain</think>\boxed{value unit}` worked solutions over the **same 16 templates**, constants-in-prompt (matches the bench), **~600 rows**, token-preflight-gated. **Held-out bench prompts excluded.** | `[[feedback_llm_skill_pattern]]` (NO `anthropic`/SDK; Edit-append; preflight token gate) + patent §4 Layer-2 `<think>…</think>answer` template. RLVR's floor is 100; SFT-init wants more for format + domain conditioning (operator: ~600). Disjointness reuses the generator's `exclude`. |
| **AV-5** | **SFT trainer = NeMo via `fieldkit.training` orchestration** | `TrainRecipe(backend="nemo")` → `run()` (docker-exec to `scripts/p65_train_nemo_lora.py`) → `merge_and_export()` → a merged-HF dir = `FK_RL_ADAPTER_INIT`. | **Operator pick (2026-06-04): NeMo** — the proven path, +44% chains / −26% wall on R1-Qwen3-8B (`[[project_nemo_pilot_verdict]]`). Apply the qwen3 YARN-defaults patch (`[[feedback_megatron_bridge_yarn_defaults]]`), explicit EOS/BOS (`[[feedback_sft_eos_bos_explicit]]`), torchao pin (`[[feedback_torchao_peft_pin]]`). **Unsloth QLoRA documented as the dev-velocity fallback lane** (needs a `TRAIN_SCRIPT` driver; watch the spaceless-`<think>` artifact — harmless here, the verifier keys on `\boxed{}`). |
| **AV-6** | **RLVR config overrides for the thinking base** | `FK_RL_MAX_TOKENS ≥ 2048`; serve so the full `<think>…\boxed{}` lands in the completion (reasoning-format **not** stripped into a side field); `FK_RL_GPU_UTIL=0.55` one-lane; EngineCore-aware teardown. | `[[feedback_reasoning_model_npredict]]` — the default 512 truncates `<think>` before the answer → verifier extracts nothing → reward 0 everywhere → **silent no-learning** (this spec's headline risk, AV-R1). `[[reference_r1_qwen3_gguf_detok_spaces]]` (serve `--reasoning-format none`-style). `[[feedback_vllm_engine_core_orphan]]`, `[[project_spark_unified_memory_oom]]`. |
| **AV-7** | **Reward + loop wiring** | `reward = RewardAdapter(astro_numeric_match, scorer_kwargs={"rel_tolerance":0.02})`; `RLLoop(GRPOConfig(base="Qwen/Qwen3-8B", …), reward, bench, *gpu_seams(config, reward=reward))`. Held-out gate every ≤10 steps; **checkpoint selection held-out-ONLY**. | RV-2 (verifier IS reward), RV-4 (the 81.8 pp inversion defense), RV-5 (pin vLLM). The pinned vLLM must be new enough for `qwen3` arch + support `--enable-lora` (AV-R2, `[[project_verl_atgpo_vllm_gap]]`). |
| **AV-8** | **Bench→task glue stays LOCAL** | A thin loader maps astro JSONL rows (`prompt`/`answer`) → the task object `RLLoop` samples + the `Rollout(prediction, expected)` shape `RewardAdapter.score` duck-types (`expected ← row["answer"]`). Lives in `scripts/astro_bench/`. | Code-verified: `RLLoop` wants a `bench` with `.questions`; `RewardAdapter.score` duck-types `prediction`/`expected`. Connective glue, **not** a fieldkit change. |
| **AV-9** | **Dispatch = async/overnight via M8→M11 + the lane arbiter** | `rl_run` enqueues programmatically; drains under the M11 single-lane cron behind the budget governor; `fieldkit arena autonomy on`; never a synchronous cockpit click. | RV-6. The run is the **first real-GPU exercise** of M8→M11 + engine + lane — feature-extraction is a primary goal. |
| **AV-10** | **Preflight baseline BEFORE SFT** | Score a 5-Q held-out slice on `Qwen3-8B` FP (via `fieldkit.training.ReasoningProbe` or transformers): does it box answers at all? zero-shot held-out score? | `[[feedback_preflight_bench_before_quant]]` — cheap gate before the multi-hour SFT+RLVR; gives the **step-0 baseline** for the lineage delta chart and validates AV-1 produces parseable output (catches AV-R1 early). |
| **AV-11** | **Publish on a held-out win** | `requant` the merged checkpoint → GGUF (llama.cpp `qwen3`) → `hf-publisher` → `Orionfold/<name>-GGUF`; **ship the astro-bench as `kind: bench`** (`Orionfold/…-bench`); promote `products/living-model/` (real `fieldkit.lineage` delta chart); `tech-writer` the scout→RLVR story. | `kind: bench` is one of the existing 8 kinds (patent-strategist-bench precedent) → **not** a new kind; RV-9 only defers *new* verifier/reward/rl_run kinds. Bench is Orionfold-authored + public-domain physics → clean to ship. Product name = open question (Orion-family), decided at publish. |

## 4. Recommended stack

The layer-by-layer build stack. Each row names the code surface it reuses (verbatim) and the
governing memory/risk.

| Layer | Choice | Code surface reused | Why / memory · risk |
|---|---|---|---|
| **Base model** | `Qwen/Qwen3-8B` (instruct, native `<think>`) | — (HF download) | AV-1. apache-2.0 + qwen3 arch + 40K ctx + RLHF-aligned. Risk: AV-R1 (thinking-truncation), AV-R4 (8B envelope). |
| **Bench + verifier** | `scripts/astro_bench/` v0.1 (BUILT); reward = `astro_numeric_match` | `verifier.py::astro_numeric_match(predicted, expected, *, rel_tolerance=0.02) -> float` | AV-2. Kept local (`[[feedback_keep_scorer_local_until_reuse]]`). |
| **SFT corpus** | `claude-corpus-synth` (in-session), ~600 rows `<think>…</think>\boxed{}` | `.claude/skills/claude-corpus-synth/` dry→preflight→live; Edit-append JSONL | AV-4. `[[feedback_llm_skill_pattern]]` (NO `anthropic`/SDK). Token-preflight gate before live. |
| **SFT trainer** | **NeMo** via `fieldkit.training` (Unsloth = fallback) | `TrainRecipe(backend="nemo")` · `run(recipe, mode=…)` · `merge_and_export(recipe, iter=…)` → merged-HF dir | AV-5. `[[project_nemo_pilot_verdict]]`, `[[feedback_megatron_bridge_yarn_defaults]]` (qwen3 YARN), `[[feedback_sft_eos_bos_explicit]]`, `[[feedback_torchao_peft_pin]]`. |
| **RLVR engine + reward** | `fieldkit.rl` + `fieldkit.reward` (BUILT, v0.20.0+) | `GRPOConfig(...)` · `RLLoop(config, reward, bench, sampler, trainer, heldout_eval)` · `RewardAdapter(verifier, scorer_kwargs)` · `group_advantage(...)` · `gpu_seams(config, reward=…)` | AV-7. Verifier-IS-reward (RV-2); held-out-only checkpoint selection (RV-4). |
| **Serving lane** | One pinned, qwen3-capable, `--enable-lora` vLLM (operator-installed) | `_rl_gpu_serve.py::VLLMLane` (kill-and-restart); `FK_RL_*` env via `RLBackendConfig.from_env` | AV-6. `FK_RL_MAX_TOKENS≥2048`, `FK_RL_GPU_UTIL=0.55`, EngineCore teardown. Risk: AV-R2 (`[[project_verl_atgpo_vllm_gap]]`). |
| **Dispatch / autonomy** | M8 dispatcher → M11 cron drain → lane arbiter | `arena/jobs.py` `JobKind.RL_RUN` (DISPATCHABLE) · `fieldkit arena autonomy on` · `fieldkit.arena.lane.LaneArbiter`/`MemoryWatchdog` | AV-9 / RV-6. Async/overnight only; single-lane (`[[project_spark_unified_memory_oom]]`). |
| **Publish** | requant → GGUF → `hf-publisher`; `kind: bench` artifact; living-model launch | `requant` job kind · `fieldkit.publish` · `hf-publisher` skill · `fieldkit.lineage.LineageSnapshot` (delta chart) | AV-11. `[[feedback_hf_readme_positioning]]`, `[[feedback_hf_upload_resilient_api]]`. |

## 5. Architecture — the A→B→C→D data flow

```
A. SCOUT (DONE)            B. BENCH (DONE)
   Qwen/Qwen3-8B LOCKED       scripts/astro_bench/  →  evidence/astrodynamics/
   (greenfield; 0 hits)       16 templates · astro_numeric_match (±2% binary)
                              v0.1: 120 pool + 44 held-out (disjoint, RV-10)
                                        │
                                        ▼
C. THE LOOP (this spec)
   C1  SFT corpus            claude-corpus-synth → astro-sft-corpus.jsonl (~600 rows,
       (~600 rows)           <think>…</think>\boxed{}, held-out EXCLUDED, every row self-verifies)
                                        │
   C2  preflight + SFT-init  ReasoningProbe(Qwen3-8B FP) → step-0 baseline   [AV-10]
                             TrainRecipe(nemo)→run()→merge_and_export() → FK_RL_ADAPTER_INIT  [AV-5]
                             gate: SFT held-out score > base
                                        │
   C3  glue + CPU smoke      bench→task loader (AV-8) · RewardAdapter(astro_numeric_match)
                             RLLoop(≤2 steps, FAKE seams) → held-out-only selection proven
                                        │
   C4  (operator) GPU lane   pinned qwen3 vLLM --enable-lora · FK_RL_* · gpu_seams real
                             fieldkit arena autonomy on · ≤2-step GPU smoke
                                        │
   C5  the RLVR run          rl_run enqueue → M8→M11 cron → lane arbiter → ~8.5 h drain
                             held-out gate ≤ every 10 steps · checkpoint = argmax(held-out)  [RV-4]
                             → LineageSnapshot (the rl_run card)
                             ⟂ STRESS-TEST: file+fix the Arena/engine bugs that fall out
                                        │
                                        ▼
D. PUBLISH (on a held-out win)
   requant → GGUF → Orionfold/<name>-GGUF  ·  Orionfold/<name>-bench (kind: bench)
   promote products/living-model/ (real lineage delta chart)  ·  tech-writer deep-dive
```

**Reward + loop wiring (the one call site, AV-7):**

```python
from fieldkit.rl import GRPOConfig, RLLoop, gpu_seams
from fieldkit.reward import RewardAdapter
from scripts.astro_bench.verifier import astro_numeric_match
from scripts.astro_bench.loader import load_astro_bench   # AV-8 glue (C3)

reward = RewardAdapter(astro_numeric_match, scorer_kwargs={"rel_tolerance": 0.02})
config = GRPOConfig(base="Qwen/Qwen3-8B", corpus_min=100, heldout_every=10,
                    max_steps=34, vllm_pin="<pinned-qwen3-capable>")   # AV-6 knobs via FK_RL_* env
bench  = load_astro_bench("evidence/astrodynamics/astro-bench-v0.1.jsonl")
loop   = RLLoop(config, reward, bench, *gpu_seams(config, reward=reward))
snapshot = loop.run()    # held-out-only checkpoint selection → the rl_run LineageSnapshot
```

## 6. Sequencing — prerequisites + what this vertical feeds

**Prerequisites (one external blocker, the rest built):**
- **The engine** (`fieldkit.rl`/`fieldkit.reward`, v0.20.0+) — **built + on PyPI**.
- **The autonomy layer** (`fieldkit.arena.lane`, v0.22.0) — **built + on PyPI**; the arbiter
  `defer`s `LANE_BIN_ABSENT` cleanly until vLLM is present.
- **`fieldkit.training`** (NeMo orchestration + `merge_and_export` + `ReasoningProbe`) — **built**.
- **C4 — the pinned aarch64+CUDA-13 vLLM** (qwen3-capable, `--enable-lora`) — the **one
  operator-owned external blocker** (`[[project_verl_atgpo_vllm_gap]]`). Gates C5; C1–C3 proceed without it.

**What this vertical feeds:**
- **The first real-GPU control-plane validation** — M8 dispatch → M9 cost → M10 recall → M11
  cron/budget → engine → lane arbiter under genuine ~8.5 h load (the dogfood feature-extraction).
- **The `products/living-model/` launch** — promotes from `status: upcoming` to published the moment
  a held-out-winning run draws the real `fieldkit.lineage` delta chart (the HANDOFF editorial overlay).
- **The MTBM editorial cadence** — a `tech-writer` greenfield-vertical installment (scout→bench→
  SFT→RLVR→publish, the whole machine in one arc).
- **Vertical #2 (VLM-astronomy)** — on the hardened text-astro stack, the RV-9 second-vertical
  unlock that promotes the publishable `verifier`/`reward`/`rl_run` kinds + the local verifier into
  `fieldkit.eval`.

## 7. Risk register (this spec's local IDs — AV-R*; the engine register RV-R1…R5 lives in `rlvr-loop-v1.md` §7)

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| **AV-R1** | **Thinking-truncation reward-collapse** — `FK_RL_MAX_TOKENS` too small or reasoning-format stripped into a side field → no `\boxed{}` in the scored completion → reward 0 on every rollout → `group_advantage` all-zeros → **silent no-learning** | **high** if defaults used | a whole run that "completes" having learned nothing | AV-6: `FK_RL_MAX_TOKENS ≥ 2048` + serve the full `<think>…\boxed{}` in the completion; the **AV-10 preflight** (5-Q FP score) catches it before the multi-hour run | shorten the prompt set / raise max_tokens; assert step-0 reward > 0 before the full run |
| **AV-R2** | **Pinned vLLM lacks `qwen3` arch or `--enable-lora`** | med | C4/C5 blocked | pin a vLLM build new enough for `qwen3` + LoRA; verify with the ≤2-step GPU smoke (C4) | the engine's `gpu_seams` raises cleanly; arbiter `defer`s `LANE_BIN_ABSENT` — run stays queued, not corrupted |
| **AV-R3** | **Pool↔held-out inversion** (inherits RV-R1, the 81.8 pp `t2po` finding) — loop "succeeds" on pool while held-out regresses | med | a shipped checkpoint that regressed | RV-4 held-out gate ≤ every 10 steps; **held-out-only** checkpoint selection (built into `RLLoop._select_checkpoint`); `heldout_patience` early-stop | abort if held-out doesn't track pool within N evals; M8 regression producer catches a bad publish downstream |
| **AV-R4** | **Envelope** — Qwen3-**8B** is slightly bigger than the 7B baseline the ~30 GiB margin assumed | low-med | overnight OOM (the 2026-04-22 landmine) | `FK_RL_GPU_UTIL=0.55`, trainer-resident, **one lane, no 2nd model**; `MemoryWatchdog` headroom-floor abort; EngineCore teardown | the M11 drain lock + watchdog bound blast radius to one pass (`[[feedback_vllm_engine_core_orphan]]`) |
| **AV-R5** | **SFT corpus quality ceiling** — synth-noise floor (~47.7% per-assertion in `t2po`); RL plateaus | med | wasted compute past the held-out peak | stop at the held-out peak (RV-4), not the pool peak; treat a plateau as a **corpus-quality** signal — improve the corpus before more RL | redirect budget to corpus work; M10 pre-flight returns the known ceiling so the governor declines a dead re-run |

## 8. Deliverables

| Artifact | Surface | Gate |
|---|---|---|
| **SFT-init corpus** `evidence/astrodynamics/astro-sft-corpus.jsonl` (~600 rows) | `claude-corpus-synth` | every row: non-empty `<think>` chain + a `\boxed{}` answer that self-verifies through `astro_numeric_match`; held-out prompts excluded |
| **SFT-init LoRA** (merged-HF dir = `FK_RL_ADAPTER_INIT`) | `fieldkit.training` (NeMo) | SFT held-out score **> base** (the SFT delta); rollouts box answers |
| **Bench→task glue** `scripts/astro_bench/loader.py` | local script | a seeded CPU fake-seam `RLLoop` selects the held-out-best step |
| **The `rl_run` `LineageSnapshot`** — held-out lift over step-0 | `fieldkit.lineage` (reused) | a real overnight run; held-out checkpoint selected; Trials written |
| **Control-plane bugs found + fixed** (the dogfood payoff) | `fieldkit` / `arena-app` | each filed + fixed same-session, regression-tested |
| **`Orionfold/<name>-GGUF`** + **`Orionfold/<name>-bench`** (`kind: bench`) | HF + `src/content/artifacts/` | `hf-publisher` live push; artifact renders |
| **`products/living-model/` promoted** (real delta chart) + **`tech-writer` deep-dive** | site | build green; both rendering verifiers pass; stats refreshed |

## 9. Open questions

- **Product name** — something Orion-family; decided at publish (C6/D). Defer until a held-out win
  confirms there's a model to name.
- **Whether the SFT-init LoRA itself ships as a `kind: lora` artifact** — likely yes alongside the
  GGUF (notebooks-as-artifacts render path is ready), decided at publish.

## 10. Change log

| Date | Change | Author |
|---|---|---|
| 2026-06-04 | **Initial spec authored — v1.0 LOCKED, C unbuilt.** Promotes `_IDEAS/astrodynamics-rlvr-vertical.md` to a tracked spec: the first end-to-end scout-to-RLVR greenfield Orionfold vertical (text-in/numeric-out astrodynamics + quantitative-astrophysics), the **application** of the built `rlvr-loop-v1` engine to a new domain (parallel to `patent-strategist-v1`, the first SFT vertical). **A** (base LOCKED = `Qwen/Qwen3-8B`) **+ B** (bench generator + `astro_numeric_match` verifier + v0.1 bench) BUILT; **C** (SFT corpus → SFT-init LoRA → RLVR run → publish) unbuilt. 11 locked decisions (AV-1…11) + 5 risks (AV-R1…R5). Resolved forks: **NeMo `p65` SFT backend** (Unsloth fallback), **~600-row** SFT corpus, **ship astro-bench as `kind: bench`**. Code-reconciled against the built `fieldkit/`: engine + autonomy + training-orchestration all present; SFT-init is external (fieldkit has no training loop); the local verifier wraps unchanged via `RewardAdapter`. Headline risk = **AV-R1 thinking-truncation reward-collapse** (the `npredict≥1024` lesson applied to RLVR rollouts), caught by the **AV-10 preflight**. Docs only — no code/site/build change this session. | Manav (with Claude) |

## 11. References

### Internal
- **Strategy origin (living journal):** `_IDEAS/astrodynamics-rlvr-vertical.md` (gitignored)
- **The engine this applies:** [`rlvr-loop-v1.md`](rlvr-loop-v1.md) (RV-1…10 + §10.1 as-built)
- **The SFT-vertical precedent (parallel shape):** [`patent-strategist-v1.md`](patent-strategist-v1.md) (§4 corpus-synth `<think>…</think>answer` template)
- **The autonomy layer (lane arbiter / OOM watchdog / education):** [`rl-lane-autonomy-v1.md`](rl-lane-autonomy-v1.md)
- **The Arena seam (dispatch + overnight home + budget brake):** [`spark-arena-v1.md`](spark-arena-v1.md) §12 (M8), §13 (M9), §14 (M10), §15 (M11)
- **The MTBM roadmap:** `_FLOWS/the-machine-that-builds-machines.md` §3 (Phase 3 / Bet 1)
- **The scout report:** `/tmp/hf-scout/2026-06-04/astrodynamics-7B/report.md`
- **The bench (BUILT):** `scripts/astro_bench/{formulas,units,verifier,generate,test_astro_bench}.py` + `evidence/astrodynamics/astro-bench-v0.1{,.heldout}.jsonl`
- **The operator runbook:** `fieldkit/docs/api/rl.md` "Operator run"
- fieldkit surfaces reused: `fieldkit/src/fieldkit/{rl,reward,training,lineage,arena}/`

### Memory cross-references (`[[name]]`)
- `[[feedback_reasoning_model_npredict]]` — the AV-R1 headline: reasoning rollouts need `max_tokens` headroom or `<think>` truncates before the answer
- `[[reference_r1_qwen3_gguf_detok_spaces]]` — serve reasoning-format care (AV-6); R1-Qwen3 spaceless-`<think>` is an Unsloth-lane artifact (harmless here)
- `[[project_nemo_pilot_verdict]]` — NeMo SFT backend pick (AV-5): +44% chains / −26% wall; carry Unsloth as the velocity fallback
- `[[feedback_megatron_bridge_yarn_defaults]]` — qwen3 YARN-rope patch on the NeMo `AutoBridge` path
- `[[feedback_sft_eos_bos_explicit]]` · `[[feedback_torchao_peft_pin]]` — SFT-init training gotchas
- `[[feedback_keep_scorer_local_until_reuse]]` — why `astro_numeric_match` stays local (AV-2)
- `[[feedback_llm_skill_pattern]]` — the in-session corpus-synth contract (AV-4): NO `anthropic`/SDK
- `[[feedback_preflight_bench_before_quant]]` — the AV-10 cheap baseline gate
- `[[project_verl_atgpo_vllm_gap]]` — the pinned aarch64+CUDA-13 vLLM is the one external blocker (AV-R2)
- `[[project_spark_unified_memory_oom]]` · `[[feedback_vllm_engine_core_orphan]]` — the one-lane envelope + EngineCore teardown (AV-R4)
- `[[project_patent_strategist_unsloth_unpublished]]` — the corpus-flaw drag a greenfield vertical avoids (§1)
- `[[dogfood_finds_mock_blind_bugs]]` — the control-plane stress-test thesis (the run surfaces missing features)
