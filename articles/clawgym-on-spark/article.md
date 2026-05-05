---
title: "ClawGym on Spark — A 7B Base, A LoRA Adapter, and the +15 pp the Adapter Earned"
date: 2026-05-05
author: Manav Sehgal
product: NeMo
stage: fine-tuning
also_stages: [agentic, training]
difficulty: advanced
time_required: "~3 days end-to-end (mostly waiting on rollouts)"
hardware: "NVIDIA DGX Spark"
tags: [agentic, sandboxing, fine-tuning, lora, peft, rl, grpo, sft, vllm, nim]
summary: "ClawGym shipped only a .github profile, so we built the substrate ourselves — persona task synth, sandbox harness, 200-task corpus, LoRA SFT, matched-base eval. The adapter earns +3.8 pp task pass and +15.0 pp per-assertion against its own base. The diagnostic is the lift."
signature: ClawgymSftLift
series: Frontier Scout
fieldkit_modules: [nim]
---

The official ClawGym repo, on the day we cracked it open, was a `.github` profile and a promise. The paper's headline bet — that **synthetic agent-trajectory data plus parallel-sandbox rollouts** is the missing scaffolding for personal claw-style agents that actually do multi-step file work — is the kind of claim that reads small in an abstract and large in a budget. ClawGym proposes to back it up with a 13.5 K verified-task corpus, a parallel-sandbox training pipeline, and a 200-instance evaluation benchmark. None of those artifacts existed publicly when this work began.

So the article you're reading is not a reproduction. It's a four-day exercise in **building the substrate ourselves on one DGX Spark** — persona-driven task synth, sandbox rollout harness, 200-task corpus, LoRA SFT — and then running the only experiment honest data permits: **a matched-base eval against the adapter's own base model**. That experiment lands on a clean, defensible number: a Qwen 2.5 7B Instruct + clawgym LoRA earns **+3.8 pp task pass and +15.0 pp per-assertion** over the same base on a 158-task held-out set. The number that matters more than that, though, is the diagnostic: SFT taught the model *to not give up early*, not to know more bash. That's the claim this piece is here to back up.

## The paper, in one breath

**Thesis.** [ClawGym](https://arxiv.org/abs/2604.26904)'s core bet is that *the data-and-sandbox layer is what's missing from personal-claw-agent training*. Recipe-grade SFT corpora exist (HF tasks, code-edit traces); RL infrastructure exists (TRL, NeMo). What does not exist, in the wild, is **a synthetic-trajectory factory paired with parallel per-task sandboxes** that lets one researcher run end-to-end SFT-plus-RL training on agent behavior — not just on completion text — without renting a cluster. The 13.5 K verified tasks, the per-task sandbox isolation, the binary task-grader as reward function, and the 200-instance eval are all parts of a single substrate claim: *if you have these primitives, you can train claw agents on one box*.

**Why this matters for a personal AI builder.** This is the agent equivalent of "your first NIM inference on Spark" — it's the infrastructure piece you need before any specific agent application becomes tractable on personal hardware. Once the substrate exists, every downstream experiment — a Second-Brain agent that organizes your notes, an Autoresearch loop that runs overnight training, a Wiki maintainer that lints your knowledge base — gets a **measurable behavior-training pipeline** instead of "we tried prompt engineering and shipped." The Spark's 128 GB unified pool is what makes parallel sandboxes viable on one box; without it the rollout pool starves the trainer.

**Promise vs achieved.** The paper promises a 13.5 K-task corpus, a 200-instance bench, and SFT-plus-RL training recipes — none of which were public artifacts at our start. We synthesized 200 tasks (perfectly balanced 25 × 8 personas), built the rollout harness from scratch, ran a 200-task baseline against NIM-served Llama 3.1 8B (8.5 % task pass / 50.7 % per-assertion), trained a Qwen 2.5 7B + LoRA-rank-16 adapter on the 17 PASS plus 25 near-miss trajectories, and ran a matched-base comparison on 158 held-out tasks: **base 4/158 = 2.5 % task pass / 31.8 % per-asrt → adapter 10/158 = 6.3 % / 46.8 %**. That's the substrate working, and the adapter earning its 165 MB of weights against a fair reference. RL is deferred; the article that earns the second number is a sequel.

## Why this matters for a personal AI builder

ClawGym's value to one Spark builder isn't the specific numbers in the paper. It's the **shape of the toolchain**. Once you've built a persona-driven task author, a sandbox harness that materializes seed workspaces and grades final state, and a LoRA SFT loop that runs end-to-end inside a single container, you have the substrate every later agent project needs — and you don't need a cloud account to iterate on it.

Three concrete things change once the substrate exists. **Behavior-level training becomes a first-class workflow** — you can teach a model to *use* tools, not just to mention them, because you can grade outcomes instead of completions. **Eval becomes cheap** — the same grader that scores trajectories during rollout scores them during eval, so you never write two grading codepaths. And **the cost of a single experiment drops to a wall-time number you control**: 32 minutes for a baseline rollout on Spark, 75 for SFT-tuned. That budget is what makes "let me check if this adapter actually helps" a question you ask, not a question you avoid because the answer costs $40 of GPU time.

## Architectural context — five phases, one substrate

The substrate is a flow pipeline. Each phase produces an artifact that the next phase consumes; nothing in the chain skips:

<figure class="fn-diagram" aria-label="Five-phase clawgym-on-spark substrate: persona-driven task synth feeds the rollout harness, which feeds the 200-task baseline, which feeds the LoRA SFT trainer, which feeds the matched-base eval that yields the +15 pp per-assertion lift.">
  <svg viewBox="0 0 900 320" role="img" aria-label="Five-phase clawgym-on-spark substrate: persona-driven task synth feeds the rollout harness, which feeds the 200-task baseline, which feeds the LoRA SFT trainer, which feeds the matched-base eval that yields the +15 pp per-assertion lift." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-claw-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d-claw-halo" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="710" y="120" width="160" height="100" rx="10" fill="url(#d-claw-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 178 170 L 200 170"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 348 170 L 370 170"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 518 170 L 540 170"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 688 170 L 710 170"/>
    </g>
    <circle class="fn-diagram__flow" r="5">
      <animateMotion dur="3.6s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" begin="1.4s">
        <mpath href="#d-claw-flow"/>
      </animateMotion>
    </circle>
    <path id="d-claw-flow" d="M 30 170 L 870 170" fill="none" stroke="none" pathLength="100"/>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="20" y="120" width="158" height="100" rx="10"/>
      <rect class="fn-diagram__node" x="200" y="120" width="148" height="100" rx="10"/>
      <rect class="fn-diagram__node" x="370" y="120" width="148" height="100" rx="10"/>
      <rect class="fn-diagram__node" x="540" y="120" width="148" height="100" rx="10"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="710" y="120" width="160" height="100" rx="10" style="fill: url(#d-claw-grad)"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="99" y="115" text-anchor="middle">Phase 1</text>
      <text class="fn-diagram__label" x="99" y="160" text-anchor="middle">task synth</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="99" y="180" text-anchor="middle">8 personas × 25</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="99" y="200" text-anchor="middle">83 min wall</text>
      <text class="fn-diagram__label" x="274" y="115" text-anchor="middle">Phase 2</text>
      <text class="fn-diagram__label" x="274" y="160" text-anchor="middle">rollout harness</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="274" y="180" text-anchor="middle">tempdir sandbox</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="274" y="200" text-anchor="middle">7/7 mock PASS</text>
      <text class="fn-diagram__label" x="444" y="115" text-anchor="middle">Phase 3</text>
      <text class="fn-diagram__label" x="444" y="160" text-anchor="middle">200-task baseline</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="444" y="180" text-anchor="middle">Llama 3.1 8B</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="444" y="200" text-anchor="middle">8.5% / 50.7%</text>
      <text class="fn-diagram__label" x="614" y="115" text-anchor="middle">Phase 4</text>
      <text class="fn-diagram__label" x="614" y="160" text-anchor="middle">LoRA SFT</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="614" y="180" text-anchor="middle">Qwen 7B + r=16</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="614" y="200" text-anchor="middle">114s, loss −68%</text>
      <text class="fn-diagram__label" x="790" y="115" text-anchor="middle">Phase 5</text>
      <text class="fn-diagram__label" x="790" y="160" text-anchor="middle">matched-base eval</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="790" y="180" text-anchor="middle">158 held-out</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="790" y="200" text-anchor="middle">+15.0 pp asrt</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="450" y="270" text-anchor="middle">substrate first; numbers second</text>
    </g>
  </svg>
  <figcaption>Five phases, one substrate. The accent at the right is the only number that survives a fair comparison — and it depends on every chip to its left.</figcaption>
</figure>

What's load-bearing about this picture is that **Phase 5 is the only phase whose number you can publish honestly without the others.** The 8.5 % task pass from Phase 3 is interesting but not comparable — it's a Llama 8B baseline, and the adapter we trained sits on Qwen 7B (more on the deviation below). The +15 pp per-assertion at the right is the adapter earning its weights against its own base on the same 158 tasks. Every chip to its left is the work it took to get there.

## The journey

### Phase 1 — synthesizing the corpus we couldn't download

ClawGym's persona-driven task author was the first thing to reproduce. Eight personas — `academic-author`, `backend-developer`, `data-science-researcher`, `devops-engineer`, `embedded-firmware-dev`, `indie-game-dev`, `ml-engineer`, `technical-writer` — each get a hand-authored skill list (15 file-management skills total) and a workspace template seeded with realistic file shapes (JSON configs, PNG sprites, firmware blobs, CSVs). The synthesizer prompts NIM-served Nemotron Nano 9B v2 for one task at a time in a hard JSON schema with five assertion primitives (`file_exists`, `file_not_exists`, `file_unchanged`, `file_contents_contain`, `file_contents_match_regex`).

```bash
$ python3 scripts/synth_tasks.py --personas all --per-persona 25 \
      --model nvidia/nvidia-nemotron-nano-9b-v2 \
      --out tasks-200.jsonl
[02:14:07] persona=academic-author idx=00 ok (1/25 personas)
[02:14:31] persona=academic-author idx=01 ok
...
[03:37:44] DONE: 200/200 ok, 0 failures, 4983s wall (24.9s/task)
```

Two things matter here. The synth ran clean at 24 seconds per task — that's a 9B reasoning model emitting 800–1200 tokens of thought per call, then a JSON object that validates against schema. And the output was perfectly balanced across personas, which forced the eval harness to confront the full skill distribution rather than let easy personas dominate. The cost shows up later: **the synth model authored several `file_contents_match_regex` assertions against binary stubs** (PNGs, firmware blobs) that are unsatisfiable by construction. That set the per-assertion ceiling at roughly 80 % before the rollout even started.

### Phase 2 — the sandbox harness that runs the agent loop

The rollout harness is one Python file, `scripts/rollout.py`. It ships an abstract `Sandbox` class with a `LocalTempSandbox` concrete (tempdir + `subprocess.run(cwd=root)`), a `RolloutDriver` that loops one bash block per turn through the agent, parses the assistant response with a strict regex (no bare-line fallback — would misclassify prose as commands), injects the observation back into the chat history, and stops on `TASK_COMPLETE`, `max_turns=12`, or a parse error. A `MockClient` replays canned actions for harness validation:

```bash
$ python3 scripts/rollout.py --tasks gold-actions-7.jsonl --out-dir /tmp/mock/ \
      --mock-actions gold-actions-7.jsonl
gold-mock 7/7 PASS  (24/24 assertions)
```

That mock pass validates the harness independent of the model. The same harness, pointed at NIM-served Llama 3.1 8B Instruct on the same 7 hand-validated tasks, lands **2/7 PASS / 24/36 assertions = 67 %**. The five recurring failure modes (sed-regex blindspot, off-by-one path-prefix errors, wrong primitive for rename, implicit-requirement miss, repetition loops on append) became the failure-mode catalogue Phase 3 needed.

The protocol decision worth surfacing: **one bash block per turn**, not structured-JSON action schema. Llama 8B drifts on JSON formatting under multi-turn pressure; bash blocks are what instruction-tuned models emit naturally, and the parse-failure mode (no block, no `TASK_COMPLETE`) is recoverable with a corrective hint. That choice carried through Phase 5 and is why the SFT-tuned model's behavior — described below — is interpretable in plain shell terms.

### Phase 3 — the 200-task baseline that calibrated everything else

```bash
$ python3 scripts/rollout.py --tasks tasks-200.jsonl --out-dir baseline/
[13:15:02] task synth-academic-author-00 PASSED 5/5 (turns=8, wall=24.1s)
[13:15:24] task synth-academic-author-01 FAILED 2/4 (turns=12, wall=22.0s)
...
[14:30:19] DONE: 200/200, 17 PASS = 8.5%, 497/980 asrt = 50.7%
```

Seventeen out of two hundred is a sober number. The per-persona spread (`data-science-researcher` 6/25 = 24 %; `embedded-firmware-dev` and `indie-game-dev` both 0/25) and the per-assertion-kind spread (`file_unchanged` 83.5 %, `file_not_exists` 79.8 %, `file_contents_match_regex` **8.9 %**) together told the load-bearing story for everything downstream. The model is competent at file negatives (delete, leave-alone) and weak at content semantics. The two zero-pass personas weren't a model gap — they were a synth-noise gap, where the regex-against-binary assertions floored their ceiling.

The PASS+near-miss filter was the next decision. **17 PASSes is a thin SFT corpus**; bumping to "trajectories with ≥75 % per-assertion pass" pulls in 25 more — including the only signal we had for the two zero-pass personas. Total: **42 records spanning all 8 personas**, with `embedded-firmware-dev` and `indie-game-dev` represented only by near-misses. That set the format-transfer test for Phase 4.

### Phase 4 — LoRA SFT, with a base-model deviation that mattered

Phase 4 trained a LoRA-rank-16 adapter (40.4 M trainable / 7.66 B = 0.53 %) on the 42 records. The base was **Qwen 2.5 7B Instruct, not Llama 3.1 8B**, and that deviation deserves the paragraph it gets here.

The trajectories were generated by NIM-served Llama 3.1 8B (FP8-quantized via TensorRT-LLM ModelOpt). That weight format isn't HF-loadable without a re-quant step, and Llama 3.1 8B is an HF-gated model — no `HF_TOKEN` was configured. Qwen 2.5 7B Instruct was already cached bf16 (15 GB) inside the Spark's `tllm-build` container from the [test-time-distilling article](/articles/test-time-distilling-for-exploration/) and loads cleanly through transformers. So Phase 4 became **a format-transfer experiment by accident**: train Qwen on Llama-flavored trajectories, ask whether the format-level signal (one bash block per turn, observation-shape responses) survives the cross-base jump.

```text
step  1  loss 1.2075  lr 2.00e-04
step  4  loss 0.4918  lr 1.40e-04
step  7  loss 0.4488  lr 8.00e-05
step 10  loss 0.3464  lr 2.00e-05
step 11  loss 0.3871  lr 0.00e+00
```

Loss dropped 1.21 → 0.39 (−68 %) in 11 optimizer steps over 114 seconds wall. The smoke eval on 8 held-out single-task draws was 8/8 well-formed bash blocks across all personas, including `embedded-firmware-dev` and `indie-game-dev` — the two zero-pass personas that contributed only near-miss trajectories. Format transferred. The honest number — *did the adapter improve anything* — was still owed.

### Phase 5 — the matched-base eval that finally let the adapter speak

The matched-base experiment is conceptually simple: run rollout against Qwen 2.5 7B base on the 158 held-out tasks (200 minus the 42 in training), then run rollout against Qwen + clawgym on the same 158, then compare. The implementation needed one piece of vLLM 0.20 plumbing — both modules in one server:

```bash
$ docker exec -d tllm-build python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct \
    --port 8000 --max-model-len 8192 --gpu-memory-utilization 0.85 \
    --enable-lora --lora-modules clawgym=/work/clawgym-sft/adapter-v1 \
    --max-lora-rank 16
$ curl -s http://172.17.0.3:8000/v1/models | jq '.data[].id'
"Qwen/Qwen2.5-7B-Instruct"
"clawgym"
```

vLLM serves both base and adapter from one process, routes to the LoRA when `--model clawgym` arrives, and saves a 4-minute restart between rollouts. Two sequential rollouts — base then adapter — landed in 32.7 + 74.6 minutes wall on the same 158 tasks. The numbers:

| Metric | Qwen base | Qwen + clawgym | Δ |
|---|---:|---:|---:|
| Task pass | 4/158 = 2.5 % | 10/158 = **6.3 %** | **+3.8 pp** |
| Per-assertion | 248/780 = 31.8 % | 365/780 = **46.8 %** | **+15.0 pp** |
| Mean turns / task | 4.59 | 12.00 | +7.4 |
| Mean wall / task | 12.4 s | 28.3 s | 2.3× |
| `task_complete` stop rate | 93.0 % | **0 %** | — |
| `max_turns` stop rate | 7.0 % | **100 %** | — |

The +15.0 pp per-assertion is the load-bearing claim. The +3.8 pp task pass is a real but small absolute number; what makes it interesting is the per-persona shape. **Six of eight personas improved on per-assertion**; the strongest case was `ml-engineer` (0/21 → 3/21 task, +30.6 pp asrt) — a persona with three PASSes and four near-misses in training, where the adapter genuinely learned the pattern. The strongest format-transfer case was `indie-game-dev` (0/24 → 2/24, +23.1 pp asrt) — only one near-miss in training, the lift came from cross-persona generalization.

## Verification — the recovery and the regression that explain the lift

The verification that matters here isn't a latency number. It's a single side-by-side trace that explains where the +15 pp per-assertion actually comes from. Both rollouts were given `synth-indie-game-dev-01`: *"Move the enemy sprite assets to a new folder called 'enemies' and create it if it doesn't exist, then write a message to a new file called 'devlog.txt' in the root directory."*

| Turn | Qwen base — graded **0/5** | Qwen + clawgym — graded **5/5 PASS** |
|---:|---|---|
| 1 | `mkdir -p enemies` | `mkdir -p enemies` |
| 2 | *[TASK_COMPLETE — no shell]* | `mv assets/enemy_bowser.png assets/enemy_koopa.png enemies/` |
| 3 | — | `echo "Moved enemy sprites to enemies folder." > devlog.txt` |
| 4–12 | — | `ls -l ...` × 9 (verification + spinning) |

Same first turn. Then the base model declares the task complete, scores zero, and stops. The adapter does the actual work in three turns and then idle-spins for nine more turns until `max_turns=12`. **Both end states get graded; only the adapter's end state has the moves.** That shape — base under-shoots; SFT over-shoots but completes — is the pattern that recurs across the +6 task-pass tasks the adapter recovered.

The mirror image is the regression. On `synth-data-science-researcher-03` (*"Keep only `experiments/run_01/*`; delete checkpoints and metrics from other run dirs"*), the base goes 6/6 PASS in 6 turns with a clean stop:

```text
turn 1  find experiments -type f \( -name "checkpoint.pt" -o -name "metrics.csv" \) \
        ! -path "experiments/run_01/*" -delete
turn 2-5  rm experiments/run_00/checkpoint.pt   (rc=1 — already gone, idempotent retries)
turn 6  [TASK_COMPLETE]
```

The adapter goes 2/6 in 12 turns:

```text
turn 1   ls -d experiments/run_* | grep -v 'run_01' | xargs -I {} rm -f {}/*checkpoint.pt {}/*metrics.csv
turn 2   ls -d experiments/run_01 | xargs -I {} echo "Keeping {}/..."
turn 3-12  echo "Task complete." × 10
```

The adapter tries a more clever compound (`xargs -I {} rm {}/*checkpoint.pt`) which under shell-glob semantics tramples on the wrong files; then it attempts to signal completion via prose ("Task complete."), which the rollout protocol doesn't recognize as a stop sentinel, so it idles ten turns. **The 42-record training corpus contained essentially zero clean-stop demonstrations** — Llama 8B PASSes in Phase 3 were rare and tended to land on the max-turn cap. The adapter learned: *emit bash, observe, emit bash, for twelve turns*. The stop signal was not in the data.

That single observation — clean-stop semantics live in the data, not in the architecture — is the operational finding that determines what Phase 6 (RL/GRPO) needs to look like. Reward shaping has to include a per-turn cost penalty. The rollout protocol has to learn to recognize prose `Task complete.` as a stop sentinel (a 2-line patch). And the training distribution has to include some trajectories that end on the model's own clean-stop signal, not on the protocol's max-turn fallback.

## Tradeoffs, gotchas, surprises

**The data isn't public, so no headline reproduction was possible.** ClawGym's GitHub org as of 2026-05-03 03:59 UTC was a `.github` profile and nothing else. The article you're reading was originally scoped as a "reproduction"; we re-scoped on day one to "build the substrate, validate the substrate, run the only honest experiment the substrate permits." That call cost a week of plausible expectations and saved the article from being a fiction.

**Cross-base SFT is a real experiment, not a deviation to apologize for.** Training Qwen 2.5 7B on Llama 3.1 8B-generated trajectories is the kind of thing a reproduction-as-engineering-substrate forces you into. The format-level signal — one bash block per turn, observation-injection style, `mkdir -p` before `mv` — survived cleanly across the base swap. Don't read this article as "we couldn't get the same base." Read it as *the format is what's transferable*, and the format is what SFT teaches.

**vLLM 0.20's `--lora-modules` is the right primitive for matched-base eval.** Both modules load at startup; the OpenAI server routes to whichever the request names. No restart between baseline and adapter rollouts. One caveat: vLLM 0.20 with `max_loras=1` (default) won't help if you need parallel rollouts on different adapters in the same process; it'll thrash the LoRA in/out per request. Sequential rollouts on different adapters work fine.

**The `tllm-build` container is reachable from the host at the bridge IP, not localhost.** Port 8000 isn't published; `curl http://localhost:8000` fails from the host. `curl http://172.17.0.3:8000` works. Captured in `compare_phase5.py` defaults so it doesn't bite again.

**Synth-noise floors are real and worth measuring before claiming a per-assertion ceiling.** The Phase 3 NOTES enumerate three classes of synth-authored bad-faith assertions: regex-against-binary (PNG sprites, firmware blobs), substring-against-regex-only-satisfiable content (`level2.json` natural shape), and implicit-requirement traps. The first class alone caps `file_contents_match_regex` at ~10 %; that's a synth-pipeline problem, not a model problem. A small assertion linter that downgrades regex-against-binary-stub assertions would lift the per-assertion ceiling from ~80 % to ~95 % without touching the model. We left this in for Phase 5 deliberately — the noise is the same noise both rollouts faced, so the +15 pp delta is fair.

**The single largest cost of "doesn't give up early" is wall time.** SFT-tuned mean wall went from 12.4 s/task baseline to 28.3 s/task — a 2.3× slowdown that shows up because every trajectory hits `max_turns=12` instead of the agent self-terminating. For the eval that's a one-time cost (~42 minutes more across 158 tasks). For production use that's the line item Phase 6 has to optimize against.

## What this unlocks

The substrate is the unlock. Three concrete things you can build this week with the harness in `articles/clawgym-on-spark/scripts/`:

**A persona-targeted SFT loop for any text-and-files agent you ship on Spark.** Swap `personas.json` for the personas your application cares about (a Wiki maintainer, a notes-organizer, a code-search assistant), regenerate a couple-hundred-task corpus through the same `synth_tasks.py`, run `rollout.py` against your candidate model, train a LoRA adapter on the PASS+near-miss filter. Total wall: a day on one box. The model you end up with knows the operational primitives of *your* problem space, not the generic ones.

**A reproducible matched-base ablation for any LoRA you train.** The `compare_phase5.py` + `run_phase5_pipeline.sh` pattern — held-out-by-training-set-membership, two parallel rollout dirs, B−A comparison — generalizes to any "did the adapter actually help" experiment. The pattern is going into `fieldkit.eval` as `MatchedBaseComparison` in the next minor.

**A vLLM-with-LoRA serving pattern for personal multi-tenant eval.** One vLLM instance, base + N LoRA adapters loaded at startup, route per request via `--model <name>`. Saves restart cost, keeps eval cheap, makes it tractable to run a dozen ablations in an afternoon instead of one a day. The Spark's 128 GB unified pool means base + a stack of rank-16 adapters fits comfortably.

## Closing

The personal-AI-builder bet underneath this whole exercise is that **the substrate matters more than the headline number**. ClawGym's headline number — pick one: 8.5 %, 6.3 %, +3.8 pp, +15.0 pp — is a moving target whose meaning depends on the corpus, the base model, the eval set, and the question you asked. The substrate is what lets you answer the next question. On a Spark, with one container, one Python file, and a 165 MB adapter, four days of work get you from "the data isn't public" to "the adapter earns its weights against its own base" — and the *diagnostic* of that lift (SFT teaches *don't give up early*, not *know more bash*) is the real artifact.

Next up: Phase 6 — a lightweight GRPO pass with a per-turn cost penalty and a stop-sentinel-aware rollout protocol, on the same 8 personas, against the same held-out 158. The question that pass answers is whether RL can recover the wall-time the SFT spent — and whether the adapter learns to declare itself done without losing the *don't-give-up-early* signal.
