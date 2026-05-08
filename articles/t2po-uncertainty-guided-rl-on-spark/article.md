---
title: "T²PO on Spark — Uncertainty-Guided Exploration on Top of the GRPO Loop"
date: 2026-05-07
author: Manav Sehgal
product: NeMo
stage: fine-tuning
also_stages: [agentic, training]
difficulty: advanced
time_required: "planned ~9–13 hours per training run"
hardware: "NVIDIA DGX Spark"
tags: [agentic, fine-tuning, lora, peft, rl, grpo, gigpo, t2po, exploration, alfworld]
summary: "ICML 2026 spotlight paper layers two uncertainty-guided controls on top of GRPO for multi-turn agents. Reproducing the algorithmic deltas on a single Spark with Qwen 2.5 7B + LoRA on the Phase 6 ClawGym harness, ALFWorld benchmark."
status: upcoming
series: Frontier Scout
fieldkit_modules: [capabilities, eval, training]
---

## What this article will answer

GRPO on the Phase 6 ClawGym arc settled at 34 steps, ~6.7 hours wall, and a +97.5 pp swing on the `task_complete` stop-signal. The next question is: how much of the per-step wall was rollouts the agent never should have spent — turns where the policy had nothing left to learn? This piece reproduces the [T²PO paper](https://arxiv.org/abs/2605.02178) (ICML 2026 spotlight) on top of that same harness — same model, same base, same eval — to measure what a token-level chain-of-thought cap and a turn-level uncertainty-resample buy a one-Spark builder running RL on a single GPU.

## NVIDIA technologies to be covered

- **NeMo / PEFT LoRA training** — the same `peft 0.19` + `transformers 4.46` + `accelerate 1.13` stack from Phase 6 GRPO, layered with two new advantage-estimator and rollout-loop hooks.
- **vLLM 0.20 with `--enable-lora` co-residence** — the proven Spark pattern for keeping a 7B policy and a LoRA-adapter trainer in 128 GB unified memory simultaneously. T²PO is the second consumer of `fieldkit.training.LoraReferenceSnapshot` (introduced in Phase 6).
- **`fieldkit.eval` benches** — `task_pass`, per-assertion, mean-turns, `task_complete` rollups against a held-out 158-task ALFWorld dev split, side-by-side with the Phase 6 GRPO@34 numbers.
- **`fieldkit.agents.replay_messages_from_trajectory` (proposed v0.3)** — T²PO's TDS regenerate path needs the same per-turn message reconstruction Phase 6 already does inline; a second consuming call site is what was missing to lock the abstraction's parameter shape.

## What I expect to find

The two algorithmic deltas — `num_think_tokens=450` cap on the chain-of-thought budget, and the TDS turn-resample rule (`0 < |Δentropy| < 0.3`, `max_try=2`) — are purely additive on top of GRPO. The 38 GB peak fits comfortably under the 128 GB unified-memory wall, so the question is not "does it fit" but "does it close the wall gap on per-step usefulness." Three falsifiable predictions: (1) mean trajectory length drops further than Phase 6's 5.0 turns; (2) `task_complete` saturation holds at >95 % through pool convergence; (3) wall-per-step rises 25–50 % from the worst-case 2× turn regen, but per-assertion improvement per wall-hour beats Phase 6 GRPO's curve. If (1) and (2) hold but (3) doesn't, the conclusion is "T²PO trades wall for stability on a single-GPU Spark, not for speed" — a useful negative result.

## Where it sits in the arc

Sixth piece in the **Frontier Scout** series — sequel to the Phase 6 GRPO article (`clawgym-on-spark-grpo`), and the second consuming use case for two `fieldkit.training` primitives the prior article seeded. Sits primarily on the `fine-tuning` stage page (LoRA PEFT under RL gradients) with a secondary chip for `agentic` (multi-turn rollouts). Not part of the LLM-Wiki / Second Brain / Autoresearch tracks — Frontier Scout pieces refresh the running arcs with what the literature suggests is worth re-running on the Spark.
