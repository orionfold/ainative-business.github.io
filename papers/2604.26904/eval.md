> **FIELDKIT FIT (2026-05-02):** retro-annotation; eval predates the v0.1 template.
> - **Would import:** `fieldkit.capabilities` (LoRA peak-memory math: weights × ~1.5; sandbox-pool sizing against the unified-memory landmine).
> - **Would extend:** nothing in v0.1 — `fieldkit.ft` and `fieldkit.agents` are both deferred and ship empty today.
> - **Would propose for v0.x:** `fieldkit.ft` — NeMo LoRA SFT wrapper (already on the v0.2 deferred list; this article validates the API). `fieldkit.agents` — parallel-rollout primitives over NemoClaw OpenShell sandboxes with the file-transfer workaround baked in (also v0.2; this article is the strongest reason to land it).

# ClawGym: A Scalable Framework for Building Effective Claw Agents

## Hypothesis

ClawGym is the missing scaffolding for Claw-style personal agents: a synthetic-data factory (13.5K verified tasks built from persona-driven intents over realistic mock workspaces), a training recipe that combines SFT on black-box rollout trajectories with a lightweight RL pass that parallelizes rollouts across per-task sandboxes, and a 200-instance evaluation benchmark calibrated by automated filtering plus human-LLM review. The bet is that the data-generation + sandbox-parallelization combo is what separates a toy demo from a model that actually does multi-step file/tool/workspace work reliably.

## Memory budget

The paper does not name a specific base model size in the abstract. The natural Spark target is 8B (the only size where SFT + light RL fits cleanly in unified memory):

- **Llama 3.1 8B bf16 SFT**: ~16 GB weights × ~4 (params + grads + optimizer + activations) ≈ 64 GB peak. Fits with grad-checkpointing and small per-step batch (batch=1, grad_accum=16).
- **LoRA-only SFT**: ~16 GB weights × ~1.5 ≈ 24 GB. Trivially fits and is the right starting point.
- **RL rollout phase**: model in inference mode (16 GB) + N parallel sandbox processes (each ~0.5–2 GB Python + container overhead). At N=8 parallel rollouts that's ~32 GB total — comfortable.
- **70B fp8 attempt**: 70 GB weights leaves no room for full-FT optimizer state; LoRA on 70B fp8 is borderline per the capabilities map. Skip for the article; 8B is the demonstrable result.

Total for the realistic 8B-LoRA-SFT + parallel-rollout RL pass: ≤ 50 GB peak. Inside envelope.

## Proposed Spark recipe

1. **Wait or proxy the data** — the GitHub org `ClawGym` exists but only ships a `.github` profile repo as of eval time. The article either waits for the 13.5K dataset drop, or generates a 1K-task subset using the paper's persona-driven recipe (LLM as task-author, mock workspace seeded from a list of skills) so the rest of the pipeline can be exercised end-to-end.
2. **Set up sandboxes via NemoClaw**: each per-task sandbox is an OpenShell container with a writable workspace at `/sandbox/.openclaw-data/workspace/` (per the `clawnav` file-transfer memory). NemoClaw already parallelizes well at 8–16 sandboxes/host before the box gets warm.
3. **SFT on Llama 3.1 8B Instruct via NeMo**, LoRA rank=16, on the rollout trajectories. Use `/opt/venv/bin/python3 -m pip` for any extra deps (per the NeMo container pip-trap memory). Single epoch, ~2–4 hours on Spark for a 13.5K-task corpus.
4. **Lightweight RL pass** — the abstract describes "parallelizes rollouts across per-task sandboxes." On Spark the natural shape is GRPO or DPO over rollout pairs (PPO is heavier and harder to fit alongside the rollout pool). 8 parallel sandboxes × short rollouts, reward = task-grader binary pass/fail.
5. **Evaluate on ClawGym-Bench's 200 instances** — once it ships. Until then, hold out a 200-task slice of the synthesized data.
6. **Compare against a NIM-served Nemotron baseline** (the project's existing agent default) to land an apples-to-apples "did the SFT actually help" measurement.

## Blockers

- Code + data not yet public: `github.com/ClawGym` org exists, only `.github` repo present. The 13.5K corpus and 200-instance bench are gated until release. Article either waits or proxies a smaller corpus.
- RL algorithm not specified in the abstract — "lightweight pipeline" is vague. Pick GRPO as the Spark-native fit and call out the deviation.
- Per-sandbox cost can stack: 8 sandboxes × OpenShell overhead is fine, but pushing past 16 risks the unified-memory landmine documented in `project_spark_unified_memory_oom`. Keep the rollout pool size conservative.

## Verdict

**spark-feasible** — 8B LoRA SFT + parallel-sandbox RL on NemoClaw fits well inside the 128 GB envelope and maps onto verified articles (`distilling-the-architect`, `lora-on-spark`, `nemoclaw-vs-openclaw-dgx-spark`); the only blocker is the unreleased code, not the hardware.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** clawgym-on-spark
- **Suggested stage:** fine-tuning
- **Suggested series:** Autoresearch
- **Suggested tags:** agentic, sandboxing, fine-tuning, lora, peft, rl, grpo, nemoclaw, nemo
- **Suggested summary:** Reproduce ClawGym's SFT-plus-lightweight-RL recipe on Llama 3.1 8B inside NemoClaw's per-task sandboxes, generate the 13.5K-task corpus locally if upstream isn't out yet, and measure pass-rate lift over a NIM-served Nemotron baseline.
