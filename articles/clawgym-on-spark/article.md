---
title: 'ClawGym — Spark reproduction notes'
date: 2026-05-02
author: 'Manav Sehgal'
product: 'NemoClaw'
stage: fine-tuning
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: [agentic, sandboxing, fine-tuning, lora, peft, rl, grpo, nemoclaw, nemo]
summary: 'Reproduce ClawGym SFT-plus-lightweight-RL recipe on Llama 3.1 8B inside NemoClaw per-task sandboxes, generate the 13.5K-task corpus locally if upstream is not out yet, and measure pass-rate lift over a NIM-served Nemotron baseline.'
status: upcoming
series: 'Autoresearch'
---

## Source paper

- arXiv: [2604.26904](https://arxiv.org/abs/2604.26904) — ClawGym: A Scalable Framework for Building Effective Claw Agents
- Repo: _(github.com/ClawGym org exists; only `.github` profile repo present at promotion time — code "soon")_
- Popularity: **30/100** · 44 HF upvotes · 0 citations

## Frontier Scout verdict

**spark-feasible** — 8B LoRA SFT + parallel-sandbox RL on NemoClaw fits well inside the 128 GB envelope and maps onto verified articles (`distilling-the-architect`, `lora-on-spark`, `nemoclaw-vs-openclaw-dgx-spark`); the only blocker is the unreleased code, not the hardware.

## Proposed Spark recipe

1. **Wait or proxy the data** — generate a 1K-task subset using the paper's persona-driven recipe (LLM as task-author, mock workspace seeded from a list of skills) so the rest of the pipeline can be exercised end-to-end.
2. **Set up sandboxes via NemoClaw**: each per-task sandbox is an OpenShell container with a writable workspace at `/sandbox/.openclaw-data/workspace/`. NemoClaw parallelizes 8–16 sandboxes/host before the box gets warm.
3. **SFT on Llama 3.1 8B Instruct via NeMo**, LoRA rank=16, on the rollout trajectories. Use `/opt/venv/bin/python3 -m pip` for any extra deps. Single epoch, ~2–4 hours on Spark for a 13.5K-task corpus.
4. **Lightweight RL pass** — pick GRPO (PPO is heavier and harder to fit alongside the rollout pool). 8 parallel sandboxes × short rollouts, reward = task-grader binary pass/fail.
5. **Evaluate on ClawGym-Bench's 200 instances** once it ships. Until then, hold out a 200-task slice of the synthesized data.
6. **Compare against a NIM-served Nemotron baseline** to land an apples-to-apples "did the SFT actually help" measurement.

Full recipe with stack-map references in [`evidence/spark-recipe.md`](./evidence/spark-recipe.md).

## Open questions for the experiment

- Code + data not yet public; either wait or proxy a smaller corpus.
- RL algorithm not specified in the abstract — picking GRPO as the Spark-native fit; document the deviation.
- Per-sandbox cost can stack: 8 sandboxes is fine, ≥16 risks the unified-memory landmine. Keep the rollout pool conservative.

## Suggested article shape

- **Stage:** fine-tuning
- **Series:** Autoresearch
- **Tags:** agentic, sandboxing, fine-tuning, lora, peft, rl, grpo, nemoclaw, nemo
- **Voice:** essay on *what it takes to make agent-trajectory training reproducible at one-box scale* — synthesizing your own data, running RL inside sandboxes, and what the unified-memory pool teaches you about parallel rollouts.
