---
title: "ClawGym GRPO on Spark — Closing the Loop the SFT Adapter Couldn't"
date: 2026-05-05
author: Manav Sehgal
product: NeMo
stage: fine-tuning
also_stages: [agentic, training]
difficulty: advanced
time_required: "~9 hours wall (34 GRPO steps + two evals)"
hardware: "NVIDIA DGX Spark"
tags: [agentic, fine-tuning, lora, peft, rl, grpo, reinforce, vllm]
summary: "Phase 5 SFT taught the agent to keep working but never to stop. 34 GRPO steps with a shaped reward unlearn the failure mode — same model, same base, same LoRA-init, but task_complete climbs 0/158 → 154/158, mean turns drop 12 → 5, and per-assertion still inches up +3.1 pp."
signature: ClawgymGrpoStopSignal
series: Frontier Scout
---

The [Phase 5 ClawGym SFT adapter](/articles/clawgym-on-spark/) shipped with a clean lift — **+15.0 pp per-assertion** over its own base — and a quietly damning shape: every one of its 158 held-out trajectories hit `max_turns=12` and zero of them stopped on their own. SFT taught the model *to not give up early* by teaching it to never give up at all. The 42-record training corpus, drawn from Llama 8B baseline rollouts that mostly hit the max-turn cap themselves, contained essentially zero clean-stop demonstrations. The model dutifully learned the only stop signal it had ever seen: keep emitting bash until the protocol kills you.

This sequel runs 34 steps of group-relative PPO ([GRPO](https://arxiv.org/abs/2402.03300)) on top of that SFT-init adapter, with a shaped reward that explicitly penalizes turn-count, and ends — by accident, on step 35 — when every group in the 8-task batch saturates at SUCCESS and produces zero learning signal. The headline reads cleanly off the eval-2 numbers against the *exact same* held-out 158 the Phase 5 article scored: **task pass 10/158 → 13/158** (+1.9 pp), **per-assertion 46.8 % → 49.9 %** (+3.1 pp), **mean turns 12.0 → 5.0** (−58 %), **wall 28.3 s → 10.7 s per task** (−62 %). The loud number — and the load-bearing one for this article's argument — is the stop-signal swing: **`task_complete` rate 0/158 → 154/158**. RL didn't make the model smarter about bash. It made it know when to put the keyboard down.

## The paper, in one breath

**Thesis.** [ClawGym](https://arxiv.org/abs/2604.26904)'s Phase 6 bet — and the broader RL-on-agent-trajectories bet underneath it — is that *the binary task-grader is enough of a reward function to fix shaped behaviors that SFT cannot reach*. A binary reward (`passed=True` → 1, else 0) is silent on near-misses, but with K rollouts per task and group-relative advantage normalization (`a_i = (r_i − μ)/(σ + ε)`), tasks that produce K identical zeros automatically self-mute (σ=0 → advantages collapse), tasks where one of K succeeds produce a positive gradient on the winner and a negative one on the losers, and the agent learns to differentiate. Add a small per-turn cost penalty and the wall-time tax SFT introduced becomes a thing the model can be trained out of.

**Why this matters for a personal AI builder.** The substrate from the Phase 5 piece — synth corpus, sandbox harness, LoRA SFT — was the *infrastructure* a one-box agent shop needs. RL is what turns that substrate into a behavior-shaping loop. Once you can grade a trajectory, you can shape the trajectory's *shape*: turn count, error-recovery patterns, when to stop, when to keep going. None of that is reachable by SFT on a small corpus, because the corpus encodes the wrong distribution. The Spark's role is the substrate's role one floor lower: 128 GB of unified memory holds the rollout vLLM (50 GiB), the trainable Qwen 7B + LoRA (~28 GiB peak with activations), and a CPU-resident reference-adapter snapshot for the KL term — all in one process, no swap, no offload, no second box.

**Promise vs achieved.** The promise: RL on top of SFT recovers the wall-time budget SFT spent and adds a small accuracy lift. Achieved: 34 steps in 8.5 hours wall-clock (rollouts dominate; trainer is 43.8 minutes total), and on the held-out 158 we keep the SFT lift on per-assertion (+3.1 pp over Phase 5 SFT) while collapsing trajectory length 2.6× and trading the never-stop failure mode for a *very rarely* never-stop failure mode (4/158 still hit max_turns; 154 stop cleanly). The pool converged at step 35, which is the natural endpoint, not a bug — when every K=4 group on an 8-task batch produces identical rewards, the gradient is zero, and the right answer is to grow the pool.

## Why this matters for a personal AI builder

There are two readings of "RL on a personal box," and they sit at different ends of the cost spectrum. The cluster reading is *PPO with a 70B critic, 64 parallel rollout workers, and a wall-clock budget you measure in days*. That's what RLHF papers report; that's what cloud-GPU-rental quotes are for. The Spark reading is *GRPO with a one-process trainer, 8 sequential rollouts of 4 each, and a wall-clock budget you measure in a long working day*. The two are not the same experiment. They optimize different shapes of behavior and they answer different questions.

What the Spark reading lets one person do is iterate on **the shape** of an agent's trajectory cheaply enough to ask questions like *what does a turn-cost penalty of 0.2 do that 0.1 doesn't?* The eight-and-a-half-hour wall is long enough to be a Real Run and short enough to fit between two reasonable working days. The 7B Qwen + LoRA-rank-16 fits in unified memory alongside vLLM with room to spare. There is no per-experiment bill, no rate limit on the eval rollouts, and no waiting on a cluster scheduler. The cost is wall-time and the willingness to let the box run overnight. That trade is the one this whole blog is about.

## Architectural context — the GRPO loop, one process, one box

Phase 6 is a kill-and-restart loop. Each step runs four phases: (1) sample 8 tasks from the 42-task pool; (2) generate K=4 rollouts per task at temperature 0.8 against vLLM-served Qwen 7B + the *current* policy adapter; (3) compute shaped rewards and group-relative advantages, write a `trajectory_bundle.jsonl`; (4) load Qwen + LoRA into the trainer, run REINFORCE-with-KL on the bundle, save the new adapter, restart vLLM with it. Five nodes, one of them load-bearing.

<figure class="fn-diagram" aria-label="GRPO loop on Spark: sample 8 tasks from a 42-task pool, run K=4 rollouts each against vLLM-served policy at temperature 0.8, compute shaped rewards and group advantages, run a REINFORCE-with-KL trainer step that saves a new policy adapter, then restart vLLM with the updated weights. The accent at the right is the trainer step that closes the loop.">
  <svg viewBox="0 0 900 320" role="img" aria-label="GRPO loop on Spark: sample 8 tasks from a 42-task pool, run K=4 rollouts each against vLLM-served policy at temperature 0.8, compute shaped rewards and group advantages, run a REINFORCE-with-KL trainer step that saves a new policy adapter, then restart vLLM with the updated weights." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-grpo-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d-grpo-halo" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="710" y="120" width="160" height="100" rx="10" fill="url(#d-grpo-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 178 170 L 200 170"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 348 170 L 370 170"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 518 170 L 540 170"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 688 170 L 710 170"/>
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 790 224 C 790 280, 99 280, 99 224"/>
    </g>
    <circle class="fn-diagram__flow" r="5">
      <animateMotion dur="3.6s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" begin="1.4s">
        <mpath href="#d-grpo-flow"/>
      </animateMotion>
    </circle>
    <path id="d-grpo-flow" d="M 30 170 L 870 170" fill="none" stroke="none" pathLength="100"/>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="20" y="120" width="158" height="100" rx="10"/>
      <rect class="fn-diagram__node" x="200" y="120" width="148" height="100" rx="10"/>
      <rect class="fn-diagram__node" x="370" y="120" width="148" height="100" rx="10"/>
      <rect class="fn-diagram__node" x="540" y="120" width="148" height="100" rx="10"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="710" y="120" width="160" height="100" rx="10" style="fill: url(#d-grpo-grad)"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="99" y="115" text-anchor="middle">sample pool</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="99" y="160" text-anchor="middle">42 tasks</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="99" y="180" text-anchor="middle">draw 8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="99" y="200" text-anchor="middle">17 PASS + 25 near</text>
      <text class="fn-diagram__label" x="274" y="115" text-anchor="middle">rollout</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="274" y="160" text-anchor="middle">K=4 × 8 = 32</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="274" y="180" text-anchor="middle">vLLM, T=0.8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="274" y="200" text-anchor="middle">~13 min/step</text>
      <text class="fn-diagram__label" x="444" y="115" text-anchor="middle">reward + advantage</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="444" y="160" text-anchor="middle">shaped: asrt − 0.2·t/12</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="444" y="180" text-anchor="middle">a_i = (r_i − μ)/(σ + ε)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="444" y="200" text-anchor="middle">σ=0 → mute</text>
      <text class="fn-diagram__label" x="614" y="115" text-anchor="middle">REINFORCE + KL</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="614" y="160" text-anchor="middle">peft LoRA r=16</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="614" y="180" text-anchor="middle">CPU ref snapshot</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="614" y="200" text-anchor="middle">~70 s trainer</text>
      <text class="fn-diagram__label" x="790" y="115" text-anchor="middle">save + restart</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="790" y="160" text-anchor="middle">adapter step-NNN</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="790" y="180" text-anchor="middle">vLLM ↻ ~3.5 min</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="790" y="200" text-anchor="middle">policy advances</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="450" y="295" text-anchor="middle">one process, one box, one loop — repeat until σ=0 across the pool</text>
    </g>
  </svg>
  <figcaption>The trainer is small. The wall is the rollouts and the vLLM restart between them — the same trade-off any one-box RL loop pays.</figcaption>
</figure>

What's load-bearing here is the **kill-and-restart**. We tested co-residence — vLLM at `--gpu-memory-utilization=0.4` with the trainer at peak, both alive in the same Spark — and confirmed it works without offload-to-meta. But vLLM 0.20 on the `tllm-build` container does not expose `/v1/load_lora_adapter` (404 on the endpoint, zero LoRA endpoints in the openapi.json), so co-residence buys exactly zero wall-time in this loop architecture: even if both processes are alive, the only way to get the new adapter into the serving model is to restart vLLM. A persistent-trainer refactor that hot-swaps LoRA via the API would close the gap, but that's a different article. For now: kill, restart, ~3.5 minutes per step.

The other piece worth surfacing up front is the **CPU-resident reference snapshot** for the KL term. Standard PPO/GRPO uses a frozen reference policy to anchor the KL divergence — `KL(π || π_ref)`. peft's `load_adapter(adapter_name="reference", is_trainable=False)` looks like the obvious primitive and crashes on `device_map="auto"` whenever the GPU has anything else resident, which on Spark unified memory is *always*. The fix is a 30-line snapshot/swap: load the SFT-init LoRA tensors from disk into a CPU dict at trainer startup, swap them into the live adapter for one no-grad forward pass when computing the KL term, then restore the trainable weights. Slow (a few seconds per step) but local, transparent, and doesn't fight peft's offload heuristics. That snapshot is **the strongest fieldkit-extraction candidate** to come out of this run; it lands in `fieldkit.training` in the next minor.

## The journey

The journey from "Phase 5 article shipped" to "GRPO run ran end-to-end" is four steps. Each one is small enough to fit in a single session; together they took two evenings.

### Step 1 — the prose stop-sentinel patch

Phase 5's `synth-data-science-researcher-03` regression was the diagnostic that triggered this whole thread. The base model PASSed in 6 turns and stopped cleanly. The SFT adapter went 2/6 in 12 turns, attempted to signal completion via prose `echo "Task complete."`, and the rollout protocol — which only recognized literal `TASK_COMPLETE` and the `max_turns` cap as stop sentinels — happily idled the next ten turns watching the model say "Task complete." into the void.

The patch is two lines in `rollout.py:parse_action()`. A bare `echo "Task complete."` (and the obvious variants — quoted, unquoted, `Task Complete`, `TASK_COMPLETE`, with or without a trailing comment) registers as `{"kind": "done"}` and stops the loop. Side-effect forms (`> file`, `>> file`, `| tee`) are explicitly preserved as regular shell commands so the grader still sees their state-mutating effects.

Replayed against the Phase 5 SFT trajectories, **69 of 158 (43.7 %)** would short-circuit, reclaiming **433 turns ≈ 13 minutes of wall** — without changing a single graded final state. The patch shipped in [commit `f0cc227`](https://github.com/manavsehgal/ai-field-notes/commit/f0cc227) and is the operational primitive every later phase of this work depends on. Without it, GRPO would optimize a reward function that can't see when the model has already declared itself done.

### Step 2 — reward shaping that separates the regimes

The first implementation of `compute_reward` was the obvious one: binary, `1.0 if passed else 0.0`. Replayed against the Phase 5 trajectories on the same 158 tasks, the binary reward distribution was **154 zeros for the base** (4 PASS) and **148 zeros for SFT** (10 PASS) — 94 % all-zero rewards across the pool. Group-relative advantages on K=4 rollouts of an all-zero task are all zeros. GRPO with binary reward on this distribution would learn from roughly 6 % of its rollouts. That's not a learning loop; that's a sample-efficiency catastrophe.

The shaped reward is `per_assertion_rate − 0.2 × (n_turns / max_turns)`. A trajectory that PASSes in 4 turns scores ~0.93. The same PASS dragged out to 12 turns scores 0.80 — the wall-time tax SFT pays gets explicitly debited. A trajectory that lands 3/5 asserts in 12 turns scores 0.40 (vs. 0.0 binary). Replayed against the Phase 5 dataset, **shaped collapsed all-zero rewards from 154+148 to 1+5** — and produced a mean delta of `r_sft − r_base = +0.022` with stdev 0.26 across the held-out 158. The SFT lift survives the turn penalty; the turn penalty correctly narrows it on cheaply-solvable tasks where the base PASSes in 4 turns at score 0.967.

```python
# reward.py — the load-bearing two lines
def compute_reward(grade, n_turns, mode="shaped",
                   max_turns=12, turn_penalty=0.2):
    if mode == "binary":
        return 1.0 if grade.passed else 0.0
    rate = grade.assertions_passed / max(1, grade.assertions_total)
    return rate - turn_penalty * (n_turns / max_turns)
```

```python
# group-relative advantages — the GRPO normalization
def compute_group_advantages(rewards, eps=1e-8):
    mu = statistics.mean(rewards)
    sigma = statistics.stdev(rewards) if len(rewards) > 1 else 0.0
    return [(r - mu) / (sigma + eps) for r in rewards]
```

The smoke run that validated the plumbing — 4 tasks × K=4 rollouts at temperature 0.8 against vLLM-served Qwen 7B + clawgym SFT adapter — landed cleanly. **4/4 tasks produced non-zero advantage variance** (stdev 0.095 to 0.272). The cleanest example: `synth-backend-developer-00` got rewards `[0.05, 0.633, 0.05, 0.55]` — same task, same model, same temperature, 0.58-point spread within K=4. That's the variance the policy gradient needs to learn from. **5 of 16 rollouts stopped via `task_complete`** at temperature 0.8 — Phase 5 SFT was 0/158 at temperature 0.2; the prose-stop sentinel plus higher exploration temperature unsticks the model. Wall: 409 seconds for 16 rollouts (~25 s/rollout). The smoke shipped in [commit `6e6b959`](https://github.com/manavsehgal/ai-field-notes/commit/6e6b959).

### Step 3 — the GRPO trainer in 280 lines

`grpo_train.py` is one Python file. It ingests a `trajectory_bundle.jsonl` (one record per task, K rewards + K advantages + K trajectories), reconstructs the exact `(system, user, assistant, observation, …)` message list each rollout saw at generation time, runs a per-token log-prob pass through the policy (Qwen 7B + LoRA), masks to assistant-emitted tokens, weights by per-step advantage, sums into a REINFORCE policy loss. The KL term is optional via `--kl-coef`; when set, it loads the CPU-resident reference snapshot, swaps it into the active adapter for one no-grad forward pass, computes per-token KL, and restores the trainable weights.

```bash
$ python3 grpo_train.py --bundle step-NNN/trajectory_bundle.jsonl \
      --adapter-init /work/clawgym-grpo/adapter \
      --reference-adapter /work/clawgym-grpo/_reference_adapter \
      --kl-coef 0.05 --lr 5e-6 \
      --out-dir /work/clawgym-grpo/adapter
[trainer] base loaded in 124.0s
[trainer] policy adapter loaded in 2.5s
[trainer] trainable params: 40,370,176 || all params: 7,655,986,688 || 0.527%
[trainer] ref snapshot: 392 tensors loaded from _reference_adapter
[trainer] used 32/32 rollouts; n_groups=8, zero_var_groups=0
[trainer] policy_loss=-0.0066 kl_loss=0.0000 grad_norm=0.144
[trainer] weight_delta_l2=0.0622 max|Δ|=0.000019
[trainer] wall: 118.2s
```

That's step 1. Trainer wall is dominated by the 124-second model load (`safetensors` over a 15 GB Qwen + LoRA), not the actual gradient step — the REINFORCE loss with KL completes in 22-28 seconds on a 32-rollout bundle. The `weight_delta_l2 = 0.062` confirms the adapter actually moved; `max|Δ| ≈ 1e-5` confirms it moved gently, which is what a reasonable RL step should look like on a 40 M-parameter LoRA. Two of the three smallest fieldkit-extraction candidates in this article come from this script: the CPU-snapshot/swap pattern (above), and a 15-line `WeightDeltaTracker` that emits the `l2` and `max|Δ|` numbers. Both are sub-100-line utilities that solve specific bugs anyone doing PPO-on-Spark will hit.

### Step 4 — the loop, end to end

`grpo_loop.sh` is ~280 lines of bash that orchestrates kill-and-restart cycles. For each step: confirm vLLM is up with the current adapter, run the rollout phase (writes the bundle), kill vLLM cleanly (`pkill -f 'vllm|EngineCore'` plus `free -h` to verify the unified-memory orphan didn't survive), run the trainer, save the new adapter to `step-NNN/adapter/`, restart vLLM, sleep until `/v1/models` returns the new adapter ID. `EVAL_EVERY=25` triggers a held-out-158 eval rollout against `compare_phase5.py`'s baseline + SFT references at the matched cadence.

The full run launched at noon on 2026-05-06 from the host with `nohup`; eval-1 fired off at step 25 (~6 hours in); the trainer ERROR'd at step 35 (~8.5 hours in) when **8/8 sampled tasks produced K=4 rollouts with zero variance** (every group's K rewards were identical — the policy reliably solved every sampled task at K=4 with the same outcome each time). The bash `set -euo pipefail` propagated the trainer's `no usable rollouts (all-zero advantages, missing tasks, or too long)` exit code and stopped the loop. Step 34 was the last successfully-saved adapter, and eval-2 ran against it.

## Verification — what success looks like, on Spark

The training trajectory across 34 steps tells the story.

| step range | mean turns | task_complete % | KL | comment |
|---|---:|---:|---:|---|
| 1 | 7.38 | 75.0 | 0.0000 | step 1 — already shorter than SFT's fixed 12 |
| 5 | 6.53 | 81.2 | 0.0001 | turns dropping, stops climbing |
| 10 | 5.28 | 93.8 | 0.0002 | first 90+% TC step |
| 16 | 4.41 | **100.0** | 0.0006 | first 100 % `task_complete` step |
| 22 | 4.38 | **100.0** | 0.0011 | second 100 % step |
| 29 | **3.69** | **100.0** | 0.0011 | best mean-turns step |
| 32 | 4.09 | **100.0** | 0.0016 | last 100 % step |
| 34 | 4.62 | 96.9 | 0.0020 | final saved adapter — eval-2 anchor |

The KL term creeps up monotonically — 0 to 0.0020 over 34 steps — which is small (the policy stays close to the SFT-init reference) but rising, exactly what a healthy RL run looks like. The `task_complete` rate breaks 100 % at step 16 and stays there for most of the run. Mean turns bottom out at step 29 (3.69) and rebound modestly to 4.62 by step 34, which is the kind of natural-noise drift you'd expect on a tiny pool. The honest summary is: *the loop closed by step 16, then kept tightening*.

What the held-out-158 eval looks like at step 34, against the same Qwen 2.5 7B base and the Phase 5 SFT adapter, both rolled out fresh on the same vLLM server at temperature 0.2:

| metric | Qwen-base | Phase 5 SFT | **GRPO@34** | Δ vs SFT |
|---|---:|---:|---:|---:|
| Task pass | 4/158 (2.5 %) | 10/158 (6.3 %) | **13/158 (8.2 %)** | **+1.9 pp** |
| Per-assertion | 248/780 (31.8 %) | 365/780 (46.8 %) | **389/780 (49.9 %)** | **+3.1 pp** |
| Mean turns | 4.59 | 12.00 | **5.00** | **−7.00** |
| Mean wall | 12.4 s | 28.3 s | **10.7 s** | **−62 %** |
| `task_complete` rate | 147/158 (93 %) | **0/158 (0 %)** | **154/158 (97.5 %)** | **+97.5 pp** |

The narrative arc is intact. Phase 5 SFT taught operational primitives at the cost of a 12-turn fixed wall and zero clean stops. Phase 6 GRPO keeps the operational lift (per-assertion still up vs. the SFT baseline, and up *significantly* vs. the Qwen-base baseline at +18.1 pp) and unlearns the failure mode. The agent is **2.6× faster per task** than the SFT adapter and ends 154/158 trajectories on its own clean stop signal.

The per-persona breakdown is where the real shape of GRPO's learning shows up:

| persona | base (task) | SFT | GRPO@34 | per-asrt Δ vs SFT |
|---|---:|---:|---:|---:|
| data-science-researcher | 2/15 | 1/15 | **4/15** | **+13.6 pp** |
| academic-author | 2/19 | 2/19 | **4/19** | **+11.4 pp** |
| ml-engineer | 0/21 | 3/21 | 3/21 | +0.0 pp |
| backend-developer | 0/19 | 0/19 | 0/19 | +2.8 pp |
| technical-writer | 0/16 | 0/16 | 0/16 | +2.8 pp |
| devops-engineer | 1/22 | 1/22 | 1/22 | 0.0 pp |
| embedded-firmware-dev | 1/22 | 1/22 | 1/22 | 0.0 pp |
| indie-game-dev | 0/24 | 2/24 | **0/24** | **−2.2 pp** |

The two big wins land where Phase 5 SFT *regressed*: `data-science-researcher` recovered from 1 → 4 (+20 pp task / +13.6 pp asrt — the cleanest single shift in this run) and `academic-author` doubled to 4. Both of those personas had clean-stop demonstrations in the original Llama-base Phase 3 corpus, and GRPO was able to recover behavior the SFT corpus had washed out. `ml-engineer` ties at 3/21 because the SFT lift there was already strong and there's not much air left in the per-assertion ceiling. The single regression is `indie-game-dev` 2 → 0 task pass (still up on per-assertion vs. the Qwen base by +21 pp, but down 2.2 pp from SFT) — a persona whose tasks involve binary game-asset assertions that the synth pipeline floors at the noise level. GRPO's slightly different turn distribution catches one fewer of those binary assertions accidentally.

## Tradeoffs and surprises

**Pool convergence is a real diagnostic, and `set -e` is the wrong way to terminate on it.** When step 35 fired with 8/8 sampled tasks producing identical-reward groups, the right answer was *grow the pool*, not crash the loop. The bash `set -euo pipefail` happily propagated the trainer's nonzero exit and we lost the in-progress step's bundle. For any future RL loop reuse, catch the `no usable rollouts` exit code, log a clean `=== POOL CONVERGED, EXITING EARLY ===` and stop. Or — better — detect upstream that K rollouts on each task converged and grow the pool from the held-out 158 instead of crashing. Filed as "loop hardening" in the handoff for the next pass.

**Eval-1 was already 90 % of the headline.** We ran two evals on the held-out 158 — at step 25 and step 34 — and the deltas tell you a small uncomfortable thing about the run: 9 more GRPO steps moved task_pass from 11 → 13, per-assertion from 386 → 389, and mean_turns from 5.39 → 5.00. Real, but small. The article you are reading could have stopped at step 25 with substantively the same conclusions. That isn't the loop wasting your time — it's the loop telling you that on a 42-task pool with a relatively gentle learning rate, the bulk of the behavior shaping happens in the first few thousand gradient updates and the rest is polish. On a 1,000-task pool the same wall-clock would buy you a much wider stretch of the learning curve.

**The unified-memory orphan is a real failure mode and it has to be cleaned up between every step.** A `pkill -f vllm.entrypoints` does not catch `vllm::EngineCore`, the worker process which keeps PPID=1 and ~108 GB of unified memory pinned. The corrected pattern is `pkill -f 'vllm|EngineCore'` followed by `free -h` to verify. We caught one of these orphans en route to building the loop; the loop now has the verification step inline. If you skip it, your second step's vLLM startup will OOM the box.

**vLLM 0.20 in `tllm-build` does not expose `/v1/load_lora_adapter`.** The natural co-residence design — keep vLLM alive across steps, hot-swap the adapter via API, never reload weights — is unreachable in this stack. The 404 is silent: `curl http://172.17.0.3:8000/openapi.json | jq '.paths | keys'` returns zero LoRA-related paths. If a future vLLM build on Spark exposes the endpoint, this loop's per-step wall drops by ~3.5 minutes, which over 34 steps is two hours. Worth re-checking on every Spark-vLLM image bump.

**The KL term is small in absolute terms; it's the right size relative to the LoRA.** At step 34 the KL is 0.0020. That is not the same number you'd see in a full-model PPO run; LoRA-only training keeps KL naturally small because most of the model's effective distribution is locked at the SFT-init reference. The trainer logs it for the same reason `weight_delta_l2` is logged: as a sanity check that the adapter actually moved and the policy hasn't collapsed onto a degenerate solution. If the KL ever spikes 100× in a single step, something has gone wrong; in this run it didn't.

**Same model, same base, same LoRA-init, but the wall almost halved.** The headline that travels in conversation is the +97.5 pp `task_complete` swing. The headline that matters for *anything you actually deploy* is that the GRPO@34 adapter is 2.6× faster per task. The matched-base ablation is fair (same vLLM server, same temperature, same 158 tasks), and the wall delta survives the eval rerun: SFT 28.3 s/task → GRPO 10.7 s/task. That isn't a benchmark trick. It's the model learning to put the keyboard down.

## What this unlocks

Three concrete things you can do this week with the loop in `articles/clawgym-on-spark/scripts/`:

**Tune the turn-cost penalty for your own agent.** The 0.2 penalty here was a coarse first guess. For an agent where each turn is genuinely cheap (a Wiki-page-update bot, a notes-organizer), drop it to 0.05 and let the model take its time. For an agent where each turn is expensive (an autoresearch loop where each turn is a 5-minute training run), raise it to 0.5 and watch the model learn to one-shot more. The scaffolding is parameterized; the experiment is one CLI flag and an overnight wall.

**Run an ablation on K, the rollouts-per-task count.** K=4 was chosen for sample efficiency on a 42-task pool; on a 200-task pool, K=2 might pay better wall-time per useful gradient step. The bundle schema is K-agnostic and the trainer's group-advantage normalization handles K=2 cleanly (single-pair stdev = absolute difference / √2). Run with K=2 for 50 steps overnight; compare to K=4 at 25 steps; report.

**Pair this with `vLLM hot-swap` the day NVIDIA ships it on Spark.** The wall budget GRPO buys you on a 7B-class model on this box is set by vLLM restart cost, not by trainer cost. The next NIM-vLLM Spark image that exposes `/v1/load_lora_adapter` cuts that restart out of the loop entirely, and 34 steps becomes a ~6-hour run, not an 8.5-hour run. The kill-and-restart pattern in `grpo_loop.sh` is the wrong primitive once that endpoint exists; persistent-trainer + adapter-API becomes the right one.

## Closing

The personal-AI-builder bet underneath Phase 6 is that **the cheapest distance between an SFT failure mode and its fix is an RL loop that grades the trajectories the failure produces**. Phase 5 taught the agent to keep working but never to stop. We could have rebuilt the corpus to include clean-stop demonstrations and re-trained — that's the SFT-only fix, and on a paper-grade corpus it might even work. On a 42-record corpus born from Llama-8B baseline rollouts that mostly hit the cap themselves, no amount of corpus surgery would have repaired the gap. GRPO's binary-task-grader-as-reward, plus a turn-cost penalty the SFT corpus could not have encoded, plus a stop-sentinel patch the rollout protocol grew along the way — that combination earns a +97.5 pp `task_complete` swing in 34 steps on one box, in a working day's wall.

Next up is the substrate's own dividend: a `tech-writer extract` pass against this run lands three concrete primitives — `LoraReferenceSnapshot`, `WeightDeltaTracker`, and a deferred `replay_messages_from_trajectory` — into [`fieldkit`](/fieldkit/) v0.2's `fieldkit.training` module, alongside the `MatchedBaseComparison` primitive the [Phase 5 article](/articles/clawgym-on-spark/) surfaced. The article after that is the one that earns its second number on a 1,000-task pool, where the headline becomes whether GRPO buys per-assertion lift past the synth-noise ceiling — not just trajectory length collapse. The Spark holds the substrate; the substrate now holds the loop; the loop now closes.
