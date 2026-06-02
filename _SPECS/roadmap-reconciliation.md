<!--
  Roadmap reconciliation note — grounds `_FLOWS/the-machine-that-builds-machines.md` §3's four abstract bets against
  Spark-measured reality harvested from the article corpus. Output (1) of the
  "Roadmap/specs harvest" item in HANDOFF.md. The per-spec evidence index (output 2)
  is deliberately deferred — built JIT when each spec is written.
  Method: 3 read-only Explore agents over ~26 roadmap-relevant articles (6 carry
  evidence/ trees, read in full + sampled; rest read from disk — the Second Brain MCP
  index was stale, 12/63 articles, none roadmap-relevant). Last updated: 2026-06-02.
-->

# Roadmap reconciliation — §3 bets vs. Spark-measured reality

**What this is.** `_FLOWS/the-machine-that-builds-machines.md` §3 sequences four bets (`pane → hands → engine`) with abstract
claims ("GRPO works on a single GPU with <100 examples", "dispatch through the MCP harness", …).
This note reconciles each against what the published article corpus actually *measured* on the
Spark — flagging where reality **confirms**, **sharpens** (adds a caveat/precision), or
**complicates** (is harder than the abstract claim implies) the roadmap. It is grounding for the
three unwritten spec stubs (`rlvr-loop-v1`, `autonomous-harness-v1`, Arena M8), not a rewrite of §3.

**Headline:** the substrate is real and §3's *sequencing* survives contact with the evidence —
but two abstractions §3 names are wrong (Phase 3 names libraries that were not used), and one
class of finding (the training-pool↔held-out inversion) is a load-bearing risk §3 doesn't mention.

---

## Phase 0 — Workflow-native fan-out — **CONFIRMED, sharpened**

§3 claim: parallel fan-out + adversarial verify compounds throughput at constant wall-clock; zero new infra.

- ✅ **CONFIRMS** the throughput-at-constant-cost premise with real numbers. `autoresearch-agent-loop`
  ran **50 agent trials in 73.4 min (88s/iter mean) for ~$0.02 of electricity** on one GB10 (96% peak
  GPU, 56W mean). `auto-research-loop-on-spark`'s lineage ablation is the sharpest proof that *structured
  visibility* multiplies a fixed budget: **lineage-on = 16 keeps vs lineage-off = 3 (5.3×), and 3.2× fewer
  eval-budget wastes (38 vs 123)** — same agent, same prompt, same model; only the rendered context differs.
- 🔧 **SHARPENS** the mechanism: the win is not raw parallelism, it's **crisp per-attempt signal + memory**.
  `trajectory-eval-is-the-agent-flailing` measured a **72% proposal-repeat rate** (k=5 history → amnesia,
  re-discovering failed ideas after iter 5) and only **14 unique (knob,value) pairs across 50 iters**. A
  single anti-repeat boolean + a widened history window (`block_repeat(last_k=50)` + `render_history(k=30)`)
  is estimated to lift unique trials **14 → ~40–50 (≈4×)**. So the Phase-0 gate's value is as much
  *deduplication* as fan-out.
- **The structural enabler — cost-to-failure inversion.** `what-the-agent-actually-built`: on the Spark a
  failed trial costs ~$0.0004 (amortized $0.02/50), so a **40–84% revert rate is acceptable** and wide
  exploration is free; on cloud the same loop would demand pre-filtering. This is *why* fan-out pays off here.

**Net:** Phase-0 is correctly placed as "free, now." Add the dedup/history gate to the canonical shape in §3 —
the corpus says that's where the 4× lives.

---

## Phase 1 — Arena as control plane / dispatch through the MCP harness — **CONFIRMED, operational**

§3 claim: the dispatcher executes *through* the MCP harness (one surface shared with Hermes; safety rails
defined once); `build_mcp_server()` already ships 7 working tools, so M8 is connective tissue not greenfield.

- ✅ **CONFIRMS, end-to-end and not theoretical.** `hermes-drives-the-spark-via-fieldkit-mcp` (the H4 keystone)
  shows the agent calling **`measure_gguf_throughput`, the harness executing it against the GPU, and a real
  number returning (41.75 tok/s on a Q4_K_M GGUF)** — **0% tool-call format error**, stdio transport, no
  network, no ad-hoc shelling. All **7 tools** are present and named (envelope, weight-footprint,
  measure-throughput, measure-perplexity, `quantize_gguf` [dry_run=True default], `publish_quant_dry_run`
  [dry-run *forced*], `ask_second_brain` [read-only]).
- 🔧 **SHARPENS** "safety rails defined once": the MCP server is a **containment layer, where the tool-list
  size *is* the policy** — dangerous verbs (publish) are structurally unreachable, reads carry `readOnlyHint`.
  And `hardening-the-hermes-harness-on-spark` (H3) adds a **second, execution-level layer**: docker
  `--network=none`, hard-stop guardrails, manual approvals — verified to *contain* hostile DNS/exfil/fetch
  calls (3/3 contained). So Phase-1's "rails defined once" is true at the tool layer and *reinforced* by a
  sandbox layer the §3 text doesn't mention.
- **For M8 specifically:** §3's "first job type = eval re-run / re-measure" is the right call — the measure
  tools are exactly the ones already exercised through the harness with zero format errors.

**Net:** Phase-1's "M8 is connective tissue" claim holds up strongly. Add to the spec: containment is
*two-layer* (tool curation + sandbox), and the dispatcher inherits both.

---

## Phase 2 — Autonomous harness + cron — **foundation solid, autonomy scaffold genuinely unbuilt**

§3 claim: one `SessionStart` hook + no cron today; need hook expansion, an overnight cron drain (sequential
loads only), a morning-standup review gate, and a budget governor.

- ✅ **CONFIRMS** every *prerequisite* is measured and in place:
  - **Brain pinned by evidence.** `picking-the-hermes-brain-on-spark` + `hermes-serving-lane-on-spark`:
    **Qwen3-30B-A3B Q4_K_M (llama.cpp) at 83.5 tok/s, 31.8 GB resident, 8/8 quality** beats the 9B incumbent
    (6/8, and a hard **2/5 multi-step-planning wall**). Overnight autonomy *requires* the MoE — the 9B fails
    the reasoning the loop depends on. MoE-vs-dense gap is **~8.5×** (88 vs 10 tok/s) at the same memory class.
  - **Sequential-load envelope validated.** `hermes-vertical-router-on-spark`: brain always-warm (31.8 GB) +
    one cold vertical (~5.5 GB) ≈ 50 GB, **78 GB headroom**; router is a 12-line deterministic keyword
    classifier (0-byte, 100% routing accuracy on 30 prompts). This is exactly §3's "sequential model loads only."
- 🔧 **SHARPENS the budget governor.** `hermes-cost-routing-local-and-openrouter` measured a **33% leak rate**
  (local-only 8/12, cost-routed 11/12 at $2.19/100 tasks, frontier-only 12/12 at $2.94/100) — a third of the
  workload *genuinely needs* frontier escalation (multi-step KV-cache derivation, constrained planning hit the
  30B-A3B class boundary). So `fieldkit.budget` must encode **failure-mode-driven escalation**, not just a
  token ceiling — the governor decides *when local gives up*, which the §3 sketch under-specifies.
- ⚠️ **CONFIRMS the gap is real (greenfield).** No article demonstrates a cron scheduler, a `SessionStart`/
  pre-commit/post-publish hook battery, or a morning-standup artifact flow. The agent is *shown able to run
  unsupervised*; it is **not shown running overnight with a review gate**. §3's "one hook, no cron" is accurate.

**Net:** Phase-2 is correctly sequenced after Phase-1. The spec's risk section should lead with the **33% local
ceiling** (it sets the budget-governor's escalation contract) and note the brain choice is non-negotiable (MoE).

---

## Phase 3 — Closed-loop RLVR — **viable, but two abstractions are wrong and one risk is missing**

§3 claims: GRPO is the post-training default; drops the learned reward model (verifier scores directly); works
on a **single GPU with <100 examples**; wrap **Unsloth-GRPO or NeMo-RL**; lifts 1–10B models.

- ✅ **CONFIRMS the core feasibility, with a real run.** `clawgym-on-spark-grpo`: **single GB10, 42-task pool
  (8 drawn/step × K=4 = 32-rollout bundle), 34 GRPO steps in 8.5 h wall**, binary task-grader as reward, **no
  learned reward model**. Result: **task_complete 0/158 → 154/158 (+97.5 pp)**, mean turns −58%, wall −62%.
  "<100 examples + single GPU + verifier-scores-directly" **holds**. Envelope holds too
  (`baseline-training-loop-on-spark`: 50 GiB max-stable pretrain + ~28 GiB trainer peak + ~20 GiB vLLM ≈
  98/128, **~30 GiB margin**).
- ❌ **COMPLICATES — the named abstractions were not used.** Neither Unsloth-GRPO nor NeMo-RL drove the working
  run: it was a **hand-rolled ~280-LOC REINFORCE-with-KL loop + kill-and-restart vLLM** (no hot LoRA swap in
  vLLM 0.20). `fieldkit.rl` should wrap *that* proven pattern (or first close the vLLM `/v1/load_lora_adapter`
  gap), not assume a library. **The bottleneck is the rollout/restart, not the trainer:** of ~15 min/step,
  rollout ≈13 min and **vLLM restart ≈3.5 min**, while the **trainer is ≈22 s**. Eliminating the restart cuts
  ~25% of wall and touches none of the training cost.
- ⚠️ **COMPLICATES — the missing risk: training-pool ↔ held-out inversion.** `t2po-uncertainty-guided-rl-on-spark`:
  at step 45 the **training-pool task_pass hit 87.5% while held-out was 5.7% — an 81.8 pp inversion**. Per-assertion
  plateaued at **~47.7%** (vs a synth-noise floor ~80%), and **T²PO trailed plain GRPO at *more* wall (18.5 h vs
  8.5 h)**. Lesson for the spec: **pool-convergence is a trap; held-out eval every ~10 steps is mandatory** to pick
  the checkpoint. §3 says nothing about this and it's the single most likely way the loop "succeeds" while
  regressing.
- 🔧 **SHARPENS "the eval harness *is* the reward model."** The verifier-as-reward idea is sound, but the corpus
  shows **binary keep/revert reward is too sparse**: `trajectory-eval`/`distill-architect-lora-from-trajectories`
  saw **mode-collapse (5/5 train keeps on one knob) and 0/8 held-out generalization** from a 42-row corpus. The
  fix is **categorical failure-class signal** — `auto-research-loop`'s **9-class status enum** (keep / discard /
  crash / eval_budget_overrun / size_blocked / …) is the demonstrated pattern. So `fieldkit.reward`/`fieldkit.eval`
  scorers should emit a **`(success, failure_class, auxiliary)` tuple**, not a scalar, and the spec needs a
  **≥100-example corpus floor** (42 was insufficient).
- **Runtime drift tax.** `runtime-frontier-six-patches-on-spark` + `test-time-distilling-for-exploration`: **2
  vLLM minor versions = 6 API drifts (one silent return-shape change)**; ESamp-style interventions cost
  ~0.97–1.12× tok/s (wall ≈flat) but only pay off on *unsaturated* tasks (`pass-at-k`: **+6.67 pp pass@8 on
  DS-R1×AIME**, but −0.61 pp noise on saturated Qwen×HumanEval). The spec should pin the vLLM version and budget
  "patch-the-runtime" time.

**Net:** Phase-3 is correctly placed last (deepest, most uncertain) and is *feasible*, but `rlvr-loop-v1.md` must
(a) wrap the hand-rolled REINFORCE pattern, not a named library; (b) make held-out-every-10-steps a hard gate;
(c) require the categorical-failure-class reward tuple + ≥100-row corpus; (d) pin vLLM and treat restart-elimination
as the top wall-clock win.

---

## Spec-feedable facts (head-start for the JIT per-spec evidence index)

> The full per-spec index (article + `evidence/` file → spec section) is deferred per HANDOFF — built when each
> spec is written. These are the load-bearing numbers each stub should open against.

**`rlvr-loop-v1.md`**
- `GRPO_WALL_SPARK_GB10 ≈ 15 min/step` (8×K=4, 42-task pool, rank-16 LoRA, temp 0.8) — `clawgym-on-spark-grpo`
- step breakdown: rollout ≈13 min · **vLLM restart ≈3.5 min** · trainer ≈22 s (restart is the eliminable win)
- `ENVELOPE_MARGIN ≈ 30 GiB` (50 pretrain + 28 trainer + 20 vLLM = 98/128) — `baseline-training-loop-on-spark`
- `POOL_HELDOUT_INVERSION = 81.8 pp @ step 45` → held-out eval ≤ every 10 steps is mandatory — `t2po-…`
- `PER_ASSERTION_CEILING_V1 ≈ 47.7%` (synth-noise floor ~80%; RL alone plateaus) — `t2po-…`
- reward must be `(success, failure_class, auxiliary)`; **≥100-row corpus** (42 → mode-collapse, 0/8 held-out) — `trajectory-eval`, `distill-architect-lora-from-trajectories`, `auto-research-loop` (9-class enum)
- `VLLM_API_DRIFT = 6 drifts / 2 minor versions` (1 silent) — pin the version — `runtime-frontier-six-patches-on-spark`

**`autonomous-harness-v1.md`**
- brain = **Qwen3-30B-A3B Q4_K_M llama.cpp, 83.5 tok/s, 31.8 GB, 8/8** (9B fails 2/5 multi-step) — `picking-the-hermes-brain-on-spark`, `hermes-serving-lane-on-spark`
- MCP harness = **7 tools, 0% format error, real measured dispatch** — `hermes-drives-the-spark-via-fieldkit-mcp`
- containment is **two-layer** (tool curation + docker `--network=none`, 3/3 hostile-call contained) — `hardening-the-hermes-harness-on-spark`
- **`LOCAL_CEILING = 33% leak to frontier`** (sets the budget-governor escalation contract) — `hermes-cost-routing-local-and-openrouter`
- sequential-load envelope: brain 31.8 GB + 1 vertical ~5.5 GB ≈ 50 GB, **78 GB headroom** — `hermes-vertical-router-on-spark`
- genuinely unbuilt: cron scheduler, hook battery, morning-standup flow, running budget enforcement

**Arena M8 (`spark-arena-v1.md` extension)**
- dispatch surface proven through the MCP harness (above); first job type = eval re-run (measure tools already exercised, 0% format error)
- Phase-0 dedup/history gate (`block_repeat(last_k=50)` + `render_history(k=30)`) = ~4× unique trials — `trajectory-eval-is-the-agent-flailing`

---

## Method & caveats

- **Corpus:** ~26 roadmap-relevant articles (MTBM/RL/agent/harness/eval), harvested by 3 read-only Explore agents.
  6 carry `evidence/` trees (`clawgym-on-spark` 1022 files, `t2po` 801, `dci-corpus-operators` 10, `auto-research-loop` 7,
  `autoresearchbench` 3, `a2tgpo` 2) — read in full + sampled for result numbers.
- **Second Brain MCP was not usable for this harvest:** its index held **12/63 articles and none of the roadmap-relevant
  ones** (stale, lagging recent commits — the documented freshness caveat). Reading fell back to disk. *Action: re-index
  the Second Brain corpus before the next harvest that wants to dogfood it.*
- **Upcoming/unbuilt articles** (`claw-eval-live-on-spark`, `judge-orchestrated-ensemble-on-spark`,
  `dci-corpus-operators-on-spark`, `skill-os-on-spark`, `field-fixing-the-hermes-harness-on-spark`) are `status: upcoming`
  proposals — noted as planned instantiations, not evidence.
