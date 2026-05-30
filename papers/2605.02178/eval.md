---
arxiv_id: 2605.02178
evaluated_at: 2026-05-07
verdict: spark-feasible
---

# T²PO: Uncertainty-Guided Exploration Control for Stable Multi-Turn Agentic Reinforcement Learning

## Hypothesis

Multi-turn agentic RL (think GRPO-on-ClawGym, but for embodied/web/search agents) collapses or stalls because the policy spends most of its rollouts on low-information actions — moves that neither reduce uncertainty nor advance the task. T²PO adds two surgical, uncertainty-guided controls on top of a vanilla GRPO-family backbone (the repo uses **GiGPO**, group-in-group): a **token-level "thinking intervention"** that caps the chain-of-thought budget per turn and triggers when marginal token uncertainty stops dropping, and a **turn-level dynamic-sampling (TDS) regeneration** that detects turns whose entropy barely shifted from the previous one and resamples them up to 2 retries. Net effect: more useful gradient signal per rollout, less wasted wall, more stable training. ICML 2026 spotlight; code is open and surprisingly clean (`https://github.com/WillDreamer/T2PO`, 9 stars, 2.4 MB Python, builds on VeRL 0.4.0 + vLLM 0.8.5 + PyTorch 2.6.0).

## Memory budget

Authors train **Qwen3-4B** RFT-warmed (`willhx/Qwen3-4B-rft-alfworld-e5`, `willhx/Qwen3-4B-rft-webshop-5`) full-FT across **8 GPUs** with FSDP + optimizer offload. Single-Spark we drop to **LoRA on 7B** (or LoRA on 4B if reproducing the exact backbone) — the standard Spark adaptation pattern.

LoRA-on-Qwen2.5-7B (already cached on Spark from the GRPO arc):

| Component | Bytes | Why |
|---|---:|---|
| Base bf16 weights (frozen) | ~14 GB | 7B × 2 |
| LoRA r=16 adapters | ~80 MB | trivial |
| AdamW over LoRA only | ~320 MB | params + grads + m + v on adapter slice |
| Activations w/ grad-ckpt, batch=4, ctx=2048 | ~6 GB | matches Phase 6 GRPO measurements |
| vLLM co-resident at gpu_memory_utilization=0.5 | ~14 GB weights + ~3 GB KV (ctx=4096, batch=8) | mirrors Phase 6 setup |
| **Total** | **~38 GB** | well under the 128 GB unified envelope |

Authors' 8-GPU full-FT stack is ~640 GB total (~80 GB/GPU), so single-Spark **must** stay LoRA + smaller batch. No path to reproducing the 8-GPU full-FT baseline locally — but the algorithmic deltas (TDS + thinking-cap) are the contribution and they reproduce fine on top of LoRA.

## Proposed Spark recipe

The cleanest path is to layer T²PO on top of the **already-shipped Phase 6 GRPO harness** at `articles/clawgym-on-spark/scripts/grpo_train.py` + `grpo_loop.sh`. That keeps the proven vLLM-co-residence + LoRA-reference-snapshot machinery and avoids a Ray/VeRL transplant onto aarch64 Spark.

1. **Resume the `tllm-build` container** (already has Qwen 2.5 7B + LoRA adapter from Phase 6; vLLM 0.20 with `--enable-lora`). Copy `grpo_train.py` → `t2po_train.py`.
2. **Port the GiGPO advantage estimator.** Vanilla GRPO uses per-trajectory advantages; GiGPO adds a per-step (turn-level) head: `A_total = α · A_traj + β · A_step`. Cribbed from VeRL's `core_algos.py`; ~50 LOC. Set `step_advantage_w=1.0` to match author config.
3. **Add the TDS resample loop** — the algorithm's headline. Reference impl is `agent_system/multi_turn_rollout/rollout_loop.py:T2PO_multi_turn_loop()` (line 631–760). Per-turn:
   - Compute `turn_level_entropy_t` from response logprobs (mean per-token entropy).
   - If `_step > 0`: `Δ = |turn_level_entropy_t − turn_level_entropy_{t-1}|`. Resample turn iff `0 < Δ < eta_threshold=0.3`. Cap at `max_try=2`.
4. **Add the thinking-token cap.** Set `num_think_tokens=450` as the response budget for any `<think>…</think>` block; the existing rollout supports `max_tokens` per generate call. This is the "token-level intervention" — the paper's marginal-uncertainty trigger collapses to a hard budget in practice.
5. **Pick one benchmark.** ALFWorld (text-only, 50 steps, deterministic) is the cleanest first target — drops in next to Phase 6's ClawGym harness with similar shape. Skip WebShop (live web, brittle on aarch64) and Search QA (needs the retrieval server in `examples/search_agent_trainer/retriever/`).
6. **Eval delta.** Run the same eval cadence as Phase 6 (every 10 grad steps, 158-task ALFWorld dev split). Compare against three baselines: Qwen base, Phase 6 SFT, Phase 6 GRPO@34. Report task_pass / mean_turns / task_complete deltas.
7. **Wall:** Phase 6 GRPO ran 34 steps in ~6.7 hr. T²PO adds up to 2× turn regeneration in the worst case → estimate **9–13 hr** for a full step-34 run.

## Blockers

- (none — recipe should run as-is) — every primitive (LoRA training, vLLM co-residence with LoRA, multi-turn rollout, group advantage, KL reference snapshot) was already shipped + measured in the Phase 6 GRPO arc (article #31 `clawgym-on-spark-grpo`). T²PO is purely additive.
- ALFWorld dependency on `textworld 1.5+` is the one platform unknown — aarch64 wheel availability not yet verified, but a TextWorld-shaped Python game env is replaceable with the existing ClawGym sandbox if it doesn't drop in.
- VeRL/Ray multi-worker config in the upstream repo is **not** the model to copy on Spark — single-process trainer + single-process vLLM is the proven pattern.

## Verdict

**spark-feasible** — Qwen 2.5 7B + LoRA + T²PO on top of the already-proven Phase 6 GRPO harness fits comfortably in ~38 GB of the 128 GB envelope; the only new code is ~80 LOC for GiGPO advantage and ~120 LOC for the TDS regenerate loop, both directly readable from `WillDreamer/T2PO/agent_system/multi_turn_rollout/rollout_loop.py`.

## Fieldkit fit

- **Would import:** `fieldkit.eval` for the per-step task-pass / per-assertion / mean-turns rollups; `fieldkit.capabilities` for the 7B + LoRA budget claim. The published v0.2 surface covers it.
- **Would extend:** `fieldkit.training.LoraReferenceSnapshot` (introduced in Phase 6 GRPO) — T²PO uses the **same** frozen-reference + KL pattern; this becomes a **second consuming use case**, which graduates the snapshot from Phase-6-only utility to a documented, multi-article primitive.
- **Would propose for v0.3:** `fieldkit.agents.replay_messages_from_trajectory` — currently deferred (sketched in `articles/clawgym-on-spark/scripts/fieldkit_agents_v0_2_sketch.md`); T²PO's TDS regenerate path needs the **exact same** per-turn message reconstruction that Phase 6's `grpo_train.py:reconstruct_messages()` does. Promoting + executing this article supplies the second use case needed to lock the abstraction's parameter shape (`system_prompt`, `user_prompt_template`, `observation_formatter` callables), unblocking extraction.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** `t2po-uncertainty-guided-rl-on-spark`
- **Suggested stage:** training
- **Suggested series:** Frontier Scout
- **Suggested also_stages:** `[agentic]` (multi-stage, like the Phase 6 article)
- **Suggested tags:** `rl, grpo, gigpo, agentic, exploration, t2po, alfworld, lora, qwen`
- **Suggested summary:** ICML 2026 spotlight paper layers two uncertainty-guided controls on top of GRPO for multi-turn agents. Reproducing the algorithmic deltas on a single Spark with Qwen 2.5 7B + LoRA on the Phase 6 ClawGym harness, ALFWorld benchmark.
- **Suggested `fieldkit_modules`:** `[capabilities, eval, training]`
