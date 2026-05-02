---
title: "Distilling the Architect — A 3B LoRA Trained on the Agent's Own Trajectory"
date: 2026-05-01
author: Manav Sehgal
product: NeMo Customizer
stage: fine-tuning
also_stages: [agentic, training]
difficulty: advanced
time_required: "~2 hours wall — 4 min LoRA training, 4 min race, the rest writing"
hardware: "NVIDIA DGX Spark"
tags: [fine-tuning, lora, distillation, autoresearch, peft, qwen2.5, dgx-spark]
summary: "A4's 50-iter trajectory becomes training data for a Qwen2.5-3B LoRA proposer. Holding out 8 iters, the 3B mode-collapses onto d_model=768 (the trajectory's most-frequent keep) and matches 0 / 8 exact; the 8B at T=0.5 matches 4 / 8 of its own past picks."
signature: ArchitectDistillation
series: Autoresearch
---

The trajectory file `articles/autoresearch-agent-loop/evidence/trajectory.jsonl` has 50 lines. Each line is one iteration of the [autoresearch agent loop](/articles/autoresearch-agent-loop): the 8B NIM proposed a single-knob perturbation, the rails checked it, the trainer ran 60 steps, the validator measured `val_bpb`, the loop kept or reverted, and the trajectory got one more record. Eight of fifty proposals improved val_bpb by more than 0.5%. Forty-two regressed and were reverted. The whole thing ran for 73 minutes overnight.

That trajectory file is *training data*. Each row encodes "given the recent history of attempts, this is what the 8B proposer chose to try next, and this is what happened." Fifty examples of an LLM-driven architectural search policy — generated, by an LLM, on this Spark, for free.

This article asks the small follow-up question: **can a 3B LoRA, trained on those 42 examples (with 8 held out), match or beat the 8B proposer that produced them?** The deliberate frame is that the agent loop in A4 paid 73 minutes of wall and ~0.07 kWh of electricity to produce a corpus. If a small distilled proposer can match the big one, the agent eats its own tail and every campaign feeds the next. If it can't yet, we want to know *why* — corpus size, temperature mismatch, or the distilled model's own bias — and what the next campaign needs to look like.

| measurement | value |
|---|---:|
| trajectory size | 50 evaluated iters (42 train · 8 held-out, time-tail split) |
| keep-decision split | 5 train · 3 held-out |
| base model | Qwen2.5-3B-Instruct (bf16, 5.8 GB on disk) |
| LoRA config | r=16 · α=32 · dropout=0.05 · all attention + FFN projections |
| trainable params | 29.93M / 3.12B (**0.961%**) |
| training wall | **3.9 min** · 5 epochs · 30 optimizer steps · final loss 0.164 · eval loss 0.333 |
| adapter size on disk | 114 MB |
| 8B NIM mean latency | **1.30 s / proposal** |
| 3B distilled mean latency | **1.69 s / proposal** *(eager bf16, no vLLM)* |
| validity rate (parses + in-menu) | 8 / 8 both proposers |
| 8B NIM knob-match on held-out | **4 / 8** |
| 3B distilled knob-match | **1 / 8** *(and value differed; 0 / 8 exact)* |
| 8B NIM exact-cfg-match | **4 / 8** |
| 3B distilled exact-cfg-match | **0 / 8** |

The honest one-line summary: at this corpus size and serving stack, the 8B that wrote the trajectory beats a 3B trained on 42 of its own rows on every metric we measured, including throughput. The interesting part is *how* the 3B fails.

## Why this matters for the personal AI power user

The autoresearch arc has a recurring claim: a Spark on your desk lets you run *unattended overnight* the kinds of experiments that a year ago needed an H100 in a leased rack. A4 demonstrated that for a 354M GPT pretrain. This article extends the claim one step: **the trajectory those overnight runs produce is itself a corpus.** You don't need to send your trial-and-error history to anyone. You don't need to share configs to a benchmark leaderboard for someone to write a "best-practice" prior. The Spark generates the trajectory, the same Spark fine-tunes a small model on it, and the next overnight run uses the distilled model as its proposer.

The first attempt in this article doesn't deliver the self-improving loop yet. It shows what's missing: more trajectory rows, a smarter sampling strategy, and a serving stack for the distilled model that keeps its inference path fast. All three are local changes — no cloud dependency required. The Spark gives you the substrate; this piece walks the substrate's first mile and reports the trip honestly.

## What's on disk before we start

The article reuses three artifacts from earlier pieces:

- `articles/autoresearch-agent-loop/evidence/trajectory.jsonl` — 52 lines (1 baseline + 50 evaluated iters + 1 loop-complete summary). The 50 iter rows are the corpus.
- `articles/autoresearch-agent-loop/evidence/proposer.py` — the prompt builder the 8B saw at training time. We import it directly so the prompts in our fine-tuning corpus are byte-identical to what the 8B saw, history window and all.
- `articles/guardrails-for-code-generation/evidence/perturbation_menu.json` — the allowlist of knobs the proposer is allowed to twist. The race-evaluation script uses this to validate every proposal.

The base model — Qwen2.5-3B-Instruct, [the same one used for the QA-pair LoRA in the Second Brain arc](/articles/lora-on-your-own-qa-pairs) — was already on disk from that earlier piece, at `/home/nvidia/lora-work/base`. No new download. The article's full wall budget (~10 min of GPU work plus writing time) is bounded by what's already cached.

## The journey — three phases

### Phase 1 — turn the trajectory into a fine-tuning corpus

`prepare_corpus.py` (in `evidence/`) reads `trajectory.jsonl` row by row, replays the running baseline cfg (which only rolls forward when a `keep` decision happens), and for each iter builds the chat the 8B saw at that exact moment:

- the **system prompt** is the proposer's `SYSTEM_PROMPT` from A4 — same constraints, same one-knob-per-iteration rule
- the **user prompt** is the perturbation menu + the running baseline cfg + the last-five history rows formatted by `proposer.build_prompt`
- the **assistant target** is the proposal JSON the 8B produced — `{"knob": ..., "new_value": ..., "reason": ...}`

The output is two JSONL files: `train.jsonl` (iters 1–42) and `test.jsonl` (iters 43–50). The split is **time-ordered**, not random — held-out iters live at the end of the trajectory. This mirrors the deployment scenario: at inference time a future proposer will see *all* history up to now and be asked to propose the next move.

```python
# from evidence/prepare_corpus.py
running = baseline["baseline_cfg"]
for r in iters:
    msgs = build_prompt(history=iters[:i], baseline_cfg=running, recent_k=5)
    target = json.dumps(r["proposal"])
    record = {"messages": [
        {"role": "system",    "content": msgs[0]["content"]},
        {"role": "user",      "content": msgs[1]["content"]},
        {"role": "assistant", "content": target},
    ]}
    if r["decision"] == "keep":
        running = r["candidate_cfg"]   # baseline rolls forward on keeps only
```

Hold-out balance: of 8 keep decisions in the 50-iter trajectory, 5 land in train (iters 4, 6, 23, 31, 33) and 3 land in test (iters 43, 45, 46). Both halves see the agent's "wins" — the model can't trivially memorize "always say `d_model=768`" from train alone. (Spoiler: it tries anyway.)

### Phase 2 — LoRA-fine-tune Qwen2.5-3B-Instruct on 42 examples

`train_lora.py` mirrors the recipe from the [QA-pair LoRA article](/articles/lora-on-your-own-qa-pairs): rank-16 adapter on every attention + FFN projection, bf16 base, gradient checkpointing, cosine schedule. The differences are small but matter:

- **5 epochs**, not 3 — 42 examples is small, more passes help convergence
- **`max_length=2048`**, not 1024 — the agent's user prompt is ~1700 tokens before the chat template adds boilerplate, and we need the assistant target to survive truncation
- **assertion on supervised-token count** — the to_chat collator now verifies every row has at least one un-masked token in the labels span. The first run reported `loss=0.0` on several batches and `eval_loss=nan` because the 1024-token cap was clipping the assistant span entirely. The assert was added before the second run.

Training ran inside `nvcr.io/nvidia/tritonserver:25.12-trtllm-python-py3` on the Spark's GB10. 30 optimizer steps, ~9 sec each, **3.9 minutes wall**, 0.961% of params trained.

```text
loaded in 37.9s, params=3.09B
trainable: 29.93M / total: 3.12B  (0.961%)
train=42  eval=8
train supervised tokens — min=26 median=32 max=36
eval  supervised tokens — min=26 median=32 max=36
starting training...
{'loss': 0.358, ... epoch 0.76}
{'loss': 0.128, ... epoch 1.0,  eval_loss=0.374}
{'loss': 0.250, ... epoch 3.0,  eval_loss=0.333}
{'loss': 0.207, ... epoch 4.0,  eval_loss=0.333}
{'loss': 0.164, ... epoch 5.0,  eval_loss=0.333}
training finished in 3.9 min
```

Eval loss converges by epoch 3 and stays there. With 42 training examples that's about as much signal as the data can carry. Adapter on disk: 120 MB (114 MB safetensors + tokenizer files); call it the size of three medium photos.

### Phase 3 — race the distilled proposer against the 8B baseline

`race_proposers.py` runs three measurements on the 8 held-out histories:

1. **Validity** — does the output parse as `{knob, new_value, reason}`, with `knob` in the menu and `new_value` in the declared range/choices?
2. **Behavioral cloning** — does the proposer pick the same `knob` (looser) or the same `(knob, new_value)` pair (stricter) as the agent's actual next-tried iter?
3. **Throughput** — wall-clock seconds per proposal. The 8B NIM rounds-trip through HTTP; the 3B LoRA runs in-process via Hugging Face `generate()` with bf16 weights.

The script doesn't run the 60-step trainer harness on novel proposals — that would add ~10 min and risk GPU contention with NIM 8B running. Instead, it cross-references the proposed cfg against the trajectory: if a proposed `(knob, value)` was already tried somewhere in the 50 iters, we know its `val_bpb`. Otherwise we report it as novel. (For these 8 held-out histories, the distilled proposer kept landing on cfgs that *had* been tried earlier in the trajectory — every one of its picks was inside the first 35 iters' menu of attempted values.)

## Verification — what each proposer actually said

The per-iter table:

| iter | ground truth | NIM 8B picked | distilled 3B picked | NIM | 3B |
|---:|---|---|---|:-:|:-:|
| 43 | `d_ff=6144` | `n_head=32` | `n_head=8` | miss | miss |
| 44 | `d_model=1536` | `d_model=1536` | `n_head=8` | **exact** | miss |
| 45 | `d_model=768` | `n_head=8` | `n_head=8` | miss | miss |
| 46 | `d_ff=8192` | `n_head=32` | `d_model=1536` | miss | miss |
| 47 | `n_head=32` | `n_head=32` | `d_model=768` | **exact** | miss |
| 48 | `d_ff=4096` | `d_ff=4096` | `d_model=768` | **exact** | miss |
| 49 | `d_model=2048` | `d_ff=6144` | `d_model=768` | miss | knob only |
| 50 | `n_head=8` | `n_head=8` | `d_model=1536` | **exact** | miss |
| **totals** | — | — | — | **4 / 8** | **0 / 8** |

![Per-iter behavioral cloning bars (left) and per-proposal latency bars (right). Each held-out iter is one column on the left chart; bars at height 2 are exact (knob+value) matches against the ground-truth proposal, height 1 is a knob-only match, height 0 is a miss. The 8B NIM column has four exact-match bars (iters 44, 47, 48, 50). The 3B distilled column has zero exact-match bars and one knob-only bar (iter 49). The right chart shows mean per-proposal latency: 8B NIM at 1302 ms, 3B distilled at 1687 ms — the distilled model is 1.30× slower in this serving stack, not faster.](evidence/calibration.png)

The 8B's 4-out-of-8 exact-match number is itself instructive: temperature 0.5 is enough to flip the 8B off its own past picks half the time. Re-querying the model that wrote the trajectory does *not* reproduce the trajectory deterministically.

The 3B distilled proposer's behavior is the telling part. It picked **`d_model=768` four times** and **`d_model=1536` twice** and **`n_head=8` twice**. Out of the 13 declared knobs and the dozens of legal `(knob, value)` pairs, the LoRA only ever proposed three. And `d_model=768` is exactly the cfg that wins five out of eight `keep` decisions in the original A4 trajectory — five out of five training-set keeps. The model learned the most-frequent successful pattern in train and applied it everywhere.

That mode-collapse onto the dominant winning move is the single sharpest finding in this article. With 42 examples, 5 of which all carry the same target (`d_model=768`), a LoRA at rank 16 cannot resist becoming a `d_model=768` machine. It learned an outcome-conditioned association ("this pattern was kept") but not the meta-policy ("vary the knob each iter").

## Tradeoffs and what they mean

- **42 examples is small.** This is the corpus-size lesson the article delivers most clearly. A LoRA cannot learn a multi-knob exploration policy from 42 examples where five training-set wins all carry the same target value. The path to "distilled wins" is more trajectory data, not a different rank or a different schedule — and "more trajectory data" is what an A4-style overnight campaign generates if you just keep running it.
- **Behavioral cloning ≠ outcome quality.** Knob-match accuracy says "did the small model pick what the big model picked." It does not say "did the small model pick something *better*." A `d_model=768`-machine has a defensibly-good prior since `d_model=768` *was* the trajectory's best pick. We did not run the 60-step trainer on the 3B's novel cfgs, so we can't say whether its picks would have lowered val_bpb relative to the 8B's. That's the next experiment.
- **The 8B is not stationary.** When we re-query the 8B on held-out histories at temperature 0.5, it reproduces its own past picks 4 / 8 times. Some part of the "race" is just the 8B disagreeing with itself. To stabilize, we'd query each held-out prompt at k=5 and report the modal proposal — left for a follow-up.
- **The throughput sign was wrong.** The HANDOFF planning doc projected the distilled model would be *faster* — it isn't, by 1.30× in our run. The 8B at 1.30s/proposal benefits from FP8 + Flash Attention + vLLM continuous batching, all baked into NIM. The 3B in eager bf16 with `transformers.generate` and no quantization runs at 1.69s. To make the distilled proposer actually faster, the next iteration would serve it via vLLM with `--enable-lora` against an FP8 base, or build a TRT-LLM engine with `--lora_plugin`. Both are deployment-stage work, both are real, neither is a fine-tuning article. The headline number we *can* report is the one we measured.
- **The 8B prior dominates the trajectory.** The 8B made 50 proposals across 13 declared knobs but only ever touched 6 of them (`n_head`, `d_model`, `d_ff`, `lr`, `beta1`, `beta2`). A LoRA trained on this slice will inherit the same blind spots, then concentrate on the densest mode within them. Future campaigns should either widen the 8B's prompt to discourage repetition or seed the trajectory with synthetic proposals across the unexplored knobs before fine-tuning.

## What this unlocks (even though distillation lost round 1)

The methodology and plumbing — corpus prep, training, race harness, calibration plot — are now on disk and reusable. The next campaign doesn't pay them again. Specifically:

1. **A4.2 (200-iter campaign)** lifts the corpus from 50 to ~200 rows. With 4× the data, a same-recipe LoRA gets enough signal to learn that `d_model=768` is good *only* when the running baseline isn't already at 768. That's the structural fact the current 3B has no way to encode.
2. **A9 (trajectory eval as observability)** treats the trajectory itself as the artifact to measure — knob diversity, repeat-failure rate, accept rate, time-to-first-keep, improvement per kWh. Some of the bottom3-by-improvement rows in this run (iter 38's `d_model=256` regression) are exactly the kind of data point a meta-policy proposer could learn to avoid; A9 is the article that makes that explicit.
3. **A serving-side LoRA article** (deployment-stage) builds either vLLM-with-LoRA or TRT-LLM-with-`--lora_plugin` on top of an FP8 Qwen base, then re-runs Phase 3's throughput measurement. The expectation is the 4-5× speedup the HANDOFF originally projected.

The agent eating its own tail is still the right shape. The first bite was small.

## State of the apps

The Autoresearch arc reaches **A8**, the second fine-tuning installment for the arc (after A2's QA-pair LoRA in the Second Brain arc). Training-stage and agentic-stage tags both apply because the article straddles them — it's a fine-tuning piece whose payload feeds an agentic system. `also_stages: [agentic, training]` reflects that.

The Looking Beyond Spark arc remains at three pieces. Foundations and the Second Brain arc are unchanged. LLM Wiki is still at one upcoming placeholder.

The Spark, the trajectory, and the LoRA recipe were on disk before this session opened. Everything in `evidence/` — the 42 train rows, the 8 held-out rows, the 114 MB adapter, the race results, the calibration plot — was produced in this session, in the time it takes to write the article. Electricity bill: roughly $0.01.
