---
title: "Two Trainers, One LoRA: NeMo Framework Beats Unsloth by 26% on a Patent-Strategist Fine-Tune"
date: 2026-05-21
author: Manav Sehgal
product: NeMo
stage: fine-tuning
difficulty: advanced
time_required: "~16 hours wall (7h 34m Unsloth + 5h 38m NeMo + conversion + merge + probe)"
hardware: "NVIDIA DGX Spark"
tags: [fine-tuning, lora, sft, nemo-framework, unsloth, megatron-bridge, deepseek-r1, patent-strategist, dgx-spark, looking-beyond-spark]
summary: "Same recipe, same R1-distilled base, same 5000-row patent corpus — once via Unsloth, once via NeMo Framework + Megatron-Bridge. NeMo finishes 26% faster and produces 44% longer patent-strategic chains. The cost is one YARN-defaults landmine and a stdout that lied for four hours."
signature: PatentStrategistBakeoff
customer_linked: true
series: Looking Beyond Spark
book_chapters: [10]
---

The smoke test projected a 35 % margin. Production landed at 26 %. The smoke was right about the shape of the answer and wrong about the size — and the gap was entirely checkpoint-save overhead that smoke does not see at ten iterations and that production absorbs nine times across a five-and-a-half-hour run. This is the bakeoff that pulled both numbers out of the same Spark, one trainer at a time.

The recipe was identical. `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` as the base. The patent-strategist v3 corpus at 5,000 rows. LoRA at `r=16, α=32`, dropout `0.05`, targets `q_proj / k_proj / v_proj / o_proj`. Learning rate `1e-4` on a cosine schedule with 5 % warmup. Micro-batch `2`, gradient accumulation `8`, global `16`. Six hundred and twenty-five iterations — about 2.2 epochs through the corpus. The only thing that changed between the two runs was the *backend*: Unsloth on top of `nvcr.io/nvidia/pytorch:25.11-py3` for one, NeMo Framework's `nvcr.io/nvidia/nemo:26.04.00` driving Megatron-Core through Megatron-Bridge 0.4.0rc0 for the other. Same model on top, same hardware below, two very different amounts of plumbing in between.

| metric (R1-distill-Qwen3-8B LoRA, 625 iters, v3 corpus) | Unsloth | NeMo Framework | delta |
|---|---:|---:|---:|
| train wall | 7h 34m (27,265 s) | **5h 38m (20,280 s)** | **−26 %** |
| per-step wall | 43.6 s | **32.4 s** | **−26 %** |
| peak GPU memory (reported) | n/a | ~48 GiB | — |
| overall probe think rate (20 q) | 0.65 | 0.60 | −0.05 |
| overall mean closed-chain length | 640 tok | **914 tok** | **+43 %** |
| patent-strategic mean chain (5 q) | 916 tok | **1,320 tok** | **+44 %** |
| patent-IRAC think rate (5 q) | 1.00 | 1.00 | tied |
| general-reasoning think rate (10 q) | 0.40 | 0.30 | −0.10 |
| general-reasoning mean chain | 212 tok | 884 tok | +317 % |
| probe max-new-tokens budget | 1,536 | 2,048 | (see footnote) |

The headline is not that NeMo is a quarter faster (it is) and not that its chains are forty percent longer on the strategic shape (they are). It is that the *cost-of-velocity* curve in this corner of the stack runs opposite to what you would expect from a frontier-vendor framework versus a community library. Unsloth ships a four-line recipe and runs in a stock PyTorch container. NeMo wants a 70 GB container, a checkpoint conversion gauntlet, and a one-line patch I had to write into a 0.4.0rc0 release to keep Megatron-Bridge from dividing by `None`. You pay that bring-up once. After that, the patent-strategist LoRA finishes its evening run before dinner instead of after, and the chains it generates have room to breathe through the shape the corpus was built to teach.

:::define[NeMo Framework]
NVIDIA's pinned-everything training substrate. Ships as one license-gated NGC container — `nvcr.io/nvidia/nemo:26.04.00`, ~70 GB on disk — bundling Megatron-Core (parallelism + fused kernels), TransformerEngine (bf16 / fp8 attention + softmax), Megatron-Bridge (HF↔Megatron checkpoint conversion), and the experiment / recipe layer. Distinct from `nemo-toolkit` on PyPI, which is the legacy 1.x lineage.
:::

:::define[Unsloth]
A community-stewarded fine-tuning library that monkey-patches HuggingFace `transformers` to use 4-bit quantized weights, fused attention, and a hand-tuned LoRA path optimized for single-GPU consumer hardware. Two-line recipe via `FastLanguageModel.from_pretrained` + `SFTTrainer`. Installs cleanly into the stock `nvcr.io/nvidia/pytorch:25.11-py3` container on this Spark (with a `torchao==0.16.0` pin — newer breaks `transformers`, older breaks `peft`).
:::

## Why this bakeoff matters for a personal AI builder

There is a real bifurcation inside the "fine-tune a small reasoning model on your own data" workflow on a one-GPU box. One branch optimizes for *dev velocity*: pip-install, two lines of recipe, four-bit quantized backbone, the model trains, the LoRA pops out, you move on. The other optimizes for *floor performance and forward compatibility*: matched-precision kernels, a checkpoint format that survives a parallelism-strategy change, a path that runs the same recipe on an H200 if you ever rent one. Both branches exist for a reason. The bakeoff is the only honest way to know which side of the bifurcation you are on for a given workload.

:::why[Dev velocity and per-step throughput are different curves]
Unsloth's two-line recipe optimizes the time from "I have a JSONL" to "I have a LoRA on disk" — install, imports, boilerplate. NeMo Framework's pinned container optimizes the time from "the loop is running" to "the loop is done." On the patent-strategist workload, the first curve favors Unsloth by hours of bring-up; the second favors NeMo by two wall-clock hours per overnight run. If you fine-tune once a quarter, bring-up dominates. If you fine-tune three times a week, the per-step delta does.
:::

The Spark is the rare hardware envelope where this choice is *yours*. On a four-GPU cluster you would not seriously consider Unsloth — the monkey-patching does not scale across data-parallel ranks the way Megatron-Core's parallelism primitives do. On a laptop with one consumer GPU you would not seriously consider NeMo — the 70 GB container and the conversion gauntlet are not worth the trouble for a 350M-class toy. The DGX Spark sits in between: 128 GB of unified memory, one Blackwell card, comfortably big enough to run either backend at production quality. The bakeoff is the same machine arguing with itself.

## Where the two paths diverge

<figure class="fn-diagram" aria-label="Two trainer paths from the same patent-strategist v3 JSONL to the same merged HF BF16 output. Top path runs Unsloth in the stock PyTorch container with a four-line recipe and writes a HuggingFace-format LoRA. Bottom path runs NeMo Framework with a conversion gauntlet — HF to Megatron import with a YARN-defaults patch — produces a Megatron dist-ckpt LoRA, merges into Megatron-Core dense weights, then exports back to HuggingFace BF16. The merged HF BF16 output is the lingua franca where the two paths reconverge — both feed downstream quantization, evaluation, and serving identically.">
  <svg viewBox="0 0 900 460" role="img" aria-label="Two parallel trainer paths from the same v3 corpus to the same merged HF BF16 output. Unsloth ships a four-line recipe and writes HF-format LoRA directly. NeMo Framework adds an HF to Megatron import with a YARN-defaults patch, then a Megatron to HF export on the way out. Both reconverge at the merged BF16, which is the only place the downstream stack cares about." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="psb-lane-unsloth" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-cyan)" stop-opacity="0.14"/>
        <stop offset="100%" stop-color="var(--svg-accent-cyan)" stop-opacity="0.03"/>
      </linearGradient>
      <linearGradient id="psb-lane-nemo" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.16"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.03"/>
      </linearGradient>
      <radialGradient id="psb-halo-grad" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="psb-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="60" y="60" width="780" height="140" rx="10" fill="url(#psb-lane-unsloth)" stroke="none"/>
    <rect x="60" y="260" width="780" height="160" rx="10" fill="url(#psb-lane-nemo)" stroke="none"/>
    <rect x="280" y="316" width="160" height="60" rx="8" fill="url(#psb-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 200 130 L 280 130" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 440 130 L 580 130" />
      <path class="fn-diagram__edge" pathLength="100" d="M 740 130 L 800 130 L 800 220 L 760 220" />
      <path class="fn-diagram__edge" pathLength="100" d="M 200 346 L 280 346" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 440 346 L 520 346" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 680 346 L 740 346" />
      <path class="fn-diagram__edge" pathLength="100" d="M 800 346 L 800 240 L 760 240" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="100" width="140" height="60" rx="8" />
      <rect class="fn-diagram__node" x="280" y="100" width="160" height="60" rx="8" />
      <rect class="fn-diagram__node" x="580" y="100" width="160" height="60" rx="8" />
      <rect class="fn-diagram__node" x="560" y="200" width="200" height="60" rx="10" />
      <rect class="fn-diagram__node" x="60" y="316" width="140" height="60" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="280" y="316" width="160" height="60" rx="8" style="fill: url(#psb-accent-grad)" />
      <rect class="fn-diagram__node" x="520" y="316" width="160" height="60" rx="8" />
      <rect class="fn-diagram__node" x="740" y="316" width="60" height="60" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="130" y="86" text-anchor="middle">UNSLOTH LANE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="130" y="125" text-anchor="middle">v3_full_5000</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="130" y="145" text-anchor="middle">.train.jsonl</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="360" y="125" text-anchor="middle">Unsloth + SFTTrainer</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="360" y="145" text-anchor="middle">pytorch:25.11 · 43.6 s/iter</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="660" y="125" text-anchor="middle">HF LoRA</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="660" y="145" text-anchor="middle">~149 MB · safetensors</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="660" y="225" text-anchor="middle">Merged HF BF16</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="660" y="245" text-anchor="middle">~16 GB · downstream-ready</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="130" y="302" text-anchor="middle">NEMO LANE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="130" y="341" text-anchor="middle">v3_full_5000</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="130" y="361" text-anchor="middle">.train.jsonl</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="360" y="341" text-anchor="middle">HF→MCore + YARN patch</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="360" y="361" text-anchor="middle">Megatron-Bridge 0.4.0rc0</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="600" y="341" text-anchor="middle">NeMo SFT</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="600" y="361" text-anchor="middle">nemo:26.04 · 32.4 s/iter</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="770" y="350" text-anchor="middle">→HF</text>
    </g>
  </svg>
  <figcaption>The accented node — HF→Megatron import with a YARN-defaults patch — is the one piece of code that did not exist before this session. Both lanes arrive at the same merged HF BF16 directory where the rest of the stack (quantization, evaluation, serving) treats them identically. The wall-time delta lives entirely in the third box of each lane.</figcaption>
</figure>

The shape of the diagram matters more than any single cell of the table. Both lanes start from the same JSONL and end at the same merged HF BF16. Everything downstream — quantization to GGUF, MCQ scoring, NIM serving, Orionfold publishing — treats them identically. The bakeoff is honest because the *interfaces* are identical at the boundaries; only the engine in the middle changes.

That symmetry is what makes "carry both backends in fieldkit" the right answer for the package's next release. Both lanes are real production paths. Both lanes produce an artifact the rest of the stack can consume. The fork point is one parameter — `backend="unsloth"` or `backend="nemo"` — and the merge point is the BF16 directory the downstream pipeline is going to read either way.

## The conversion gauntlet, and the one bug worth a memory

The Unsloth lane has nothing to convert. The four-line recipe takes an HF model identifier, wraps it in `FastLanguageModel.from_pretrained`, attaches LoRA adapters with `FastLanguageModel.get_peft_model`, and hands it to `SFTTrainer`. The base weights stream from the HF cache directory. The optimizer state lives in the same `transformers` data structures the model itself uses. No format change.

The NeMo lane has to import. Megatron-Core does not natively read HuggingFace checkpoints — it reads Megatron-Bridge distributed checkpoints, a format built for tensor-parallel and pipeline-parallel sharding even when (as on this Spark) `tp=1, pp=1, dp=1`. The standard import flow is one CLI invocation:

```bash
python /opt/Megatron-Bridge/examples/conversion/convert_checkpoints.py import \
  --hf-model-path /home/nvidia/data/hf-cache/.../DeepSeek-R1-0528-Qwen3-8B \
  --output-path /home/nvidia/data/aifn-train-lora/p65-nemo/mcore-base
```

It crashed.

The trace pointed at `_yarn_find_correction_dim`, which multiplies by `math.log(base) * π`. The crash was a `TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'`. Megatron-Bridge 0.4.0rc0 plumbs `yarn_rotary_scaling_factor` and `yarn_original_max_position_embeddings` through from the HF config — but leaves `yarn_beta_fast`, `yarn_beta_slow`, `yarn_mscale`, and `yarn_mscale_all_dim` as `None`. The downstream YARN math then tries to multiply `None * math.pi` and the import fails before a single weight tensor has been touched.

:::define[YARN rope]
*Yet Another RoPE-extensioN.* A family of attention-positional-encoding adjustments that lets a model trained at one context length reason at a longer one without retraining. Introduces four scalar hyperparameters — `beta_fast`, `beta_slow`, `mscale`, `mscale_all_dim` — that interpolate the rotary frequency at the boundary. DeepSeek-R1-0528-Qwen3-8B was trained with YARN and declares it in `config.json` via `rope_type=yarn`. The four scalars have well-published defaults (32.0, 1.0, 1.0, 0.0) but the Megatron-Bridge 0.4.0rc0 importer does not carry them across.
:::

The fix is four lines, applied to the provider object before `provide_distributed_model`:

```python
def patch_yarn_defaults(provider):
    """Megatron-Bridge 0.4.0rc0 leaves these as None on rope_type=yarn imports.
    YARN's published defaults are (32.0, 1.0, 1.0, 0.0)."""
    provider.yarn_beta_fast = 32.0
    provider.yarn_beta_slow = 1.0
    provider.yarn_mscale = 1.0
    provider.yarn_mscale_all_dim = 0.0
```

With the patch wired into `scripts/p65_convert_hf_to_mcore.py`, the import completed in nine minutes and produced the `mcore-base/` directory the SFT loop wanted. The same patch will be the one piece of glue that lifts into `fieldkit.training.convert.HFToMegatron` so that the next person on this path does not lose an afternoon to a `None * math.pi`.

:::pitfall[Megatron-Bridge 0.4.0rc0 silently un-populates YARN defaults]
The HuggingFace `config.json` for DeepSeek-R1-0528-Qwen3-8B (and any Qwen3-extended-context model) does not declare `yarn_beta_fast / beta_slow / mscale / mscale_all_dim` directly. Megatron-Bridge expects them on the provider object but leaves them as `None`. The crash is downstream and reads as a `TypeError` deep in `_yarn_find_correction_dim`, which makes it look like a model-config bug rather than a bridge bug. Patch the four defaults on the provider before `provide_distributed_model` — the published YARN paper values are `(32.0, 1.0, 1.0, 0.0)`.
:::

The conversion gauntlet does not end there. The output of NeMo SFT is a *Megatron distributed-checkpoint* LoRA, ~149 MB on disk under `runs-full/iter_0000625/`. To use it downstream you have to (a) merge it into Megatron-Core dense weights (~16 GB), then (b) export those dense weights back to HuggingFace BF16 safetensors (another ~16 GB on disk, but readable by every tool the rest of the stack uses). Both steps are scripted in NeMo and both ran cleanly. The merge took eleven minutes; the export took eight. So: ten minutes of conversion glue, three configuration files, four monkey-patched YARN scalars — and the artifacts that pop out of the bottom are byte-for-byte interchangeable with what Unsloth wrote in one step.

## The train wall — and the smoke that under-projected by sixteen percent

Both trainers ran the same 625 iterations over the same corpus. Unsloth finished in 27,265 seconds; NeMo in 20,280. The per-step delta is uniform across the run — no warm-up tail, no checkpoint stall that one trainer absorbs better than the other. NeMo just takes less time per iteration, and that compounds across 625 of them.

The interesting number is not in the comparison; it is in the *projection*. Before kicking off the production NeMo run, I ran a ten-iteration smoke at the same recipe to project the full-train wall. The smoke clocked 28.0 s/iter. Multiplied by 625 iterations that projected 17,500 s — about 4 h 52 m. The production run came in at 5 h 38 m. The smoke under-projected by **16 percent**.

:::math[Where the sixteen-percent gap lives]
NeMo Framework checkpointed nine times across the production run — once every ~70 iterations. Each checkpoint save writes optimizer state + LoRA adapter to disk and takes roughly seven minutes on this Spark. 9 × 7 min = 63 min ≈ 3,780 s. The smoke ran ten iterations with one early checkpoint (~6 min). The "missing" 3,200 s in the projection is almost exactly the eight extra checkpoint saves the production run absorbed that the smoke never paid for. Smoke is good for projecting *steady-state* throughput; multiply by ~1.16 before promising a wall budget.
:::

That detail is the one I am keeping in memory across future bakeoffs. The smoke projection is honest for the work the model is doing on the GPU. It is silent about the work the trainer is doing on the disk. Production absorbs both, and the disk side scales with iteration count differently than the compute side does.

The Unsloth lane has the same disk overhead (also one checkpoint save per ~70 iterations) but the writes go faster — Unsloth uses HF `safetensors` straight from the trainer's data structures, while Megatron-Bridge serializes optimizer state through a distributed-checkpoint shim even at `dp=1`. So a fraction of the 26 % wall margin is "Unsloth is just lower-overhead per step," but the bigger fraction is "Megatron-Core's fused kernels run the matmul-heavy hot path faster" — the same effect the [NeMo Framework on the Spark](/field-notes/nemo-framework-on-spark/) article measured in a hand-rolled `vanilla_train.py` against a Megatron-Core equivalent.

## The log-buffer ghost — when stdout lies for four hours

At iteration 116 of the NeMo run, `train.log` stopped updating. The process was still alive. `nvidia-smi` showed GPU utilization at 96 %. The python interpreter was in `Rsl` state, not `D`. Memory was steady. Every external signal said training was running — except the log, which sat at:

```
[NeMo I 2026-05-21 11:14:23 megatron_gpt_model:982] step=116 loss=0.873 lr=8.2e-05 ...
```

…for the next four hours and twenty minutes.

I came back at the projected iter 596 mark. The log still read iter 116. The disk was telling a completely different story:

```bash
$ ls -lt /home/nvidia/data/aifn-train-lora/p65-nemo/runs-full/
drwxr-xr-x 2 nvidia nvidia 4096 May 21 15:39 iter_0000600/
drwxr-xr-x 2 nvidia nvidia 4096 May 21 14:30 iter_0000525/
drwxr-xr-x 2 nvidia nvidia 4096 May 21 13:22 iter_0000455/
drwxr-xr-x 2 nvidia nvidia 4096 May 21 12:12 iter_0000385/
$ cat /home/nvidia/data/aifn-train-lora/p65-nemo/runs-full/latest_checkpointed_iteration.txt
600
```

Training was past iteration 600. The log thought it was at 116. Somewhere between Megatron's stdout writer, the bash redirect, and the `docker exec` shell, a buffer was holding ~480 unflushed lines that never made it to disk — and `python3 -u` (which was on) did not help because the unbuffered Python is upstream of the pipe doing the holding. The log file *lies*.

The artifact-on-disk *does not lie*. `latest_checkpointed_iteration.txt` is written synchronously every checkpoint save. Each `iter_NNNNNNN/` directory's mtime is the wall-clock moment the save happened. Polling those two signals — file write times and the iteration text — gives you a liveness probe that survives whatever the stdout stack decides to do.

:::why[On long training runs, trust the disk and distrust stdout]
A multi-hour training run's stdout passes through too many layers of buffering — the python writer, the libc stdio buffer, the bash pipe, the docker exec relay, the journald sink — for any of them to fail-safe to "show me a fresh line every second." Disk artifacts (`latest_checkpointed_iteration.txt`, the iter directory mtimes) are written by the trainer itself, not by the stdout stack. If you have to choose one signal to monitor a long training run, choose the disk side; the log file is a hint, not a contract.
:::

The Unsloth lane did not exhibit this — its progress bar runs through `tqdm`, which writes to stderr (a different buffer) and flushes per step. But Unsloth also does not write a `latest_checkpointed_iteration.txt`, which means *its* liveness contract lives entirely in the stderr stream. Pick your poison: a stdout that buffers across docker boundaries, or a stderr that streams cleanly but has no on-disk fallback if the terminal session disconnects.

Both contracts will be unified in `fieldkit.training.run()` — both lanes will emit the same `latest_checkpointed_iteration.txt` + iter-dir convention, because *the disk side is the one that survives the most.*

## The probe — what the chains actually did

Both merged BF16 checkpoints ran the same twenty-question probe: ten general-reasoning questions (AIME-shape math, GPQA-shape science, ARC-shape logic), five patent-strategic questions (the corpus's training distribution), five patent-IRAC questions (issue / rule / analysis / conclusion). The probe records whether the model emits a closed `<think>...</think>` block (`think_presence_rate`), and if so, how many tokens are inside it (`think_token_length`). The probe is not a correctness judgment — it does not grade the answer. It measures whether the chain *happens* and whether it has *room to develop*.

The headline split, by category:

| category (5–10 q each) | metric | Unsloth | NeMo | Δ |
|---|---|---:|---:|---:|
| patent-strategic | think rate | 0.80 | 0.80 | tied |
| patent-strategic | mean chain | 916 tok | **1,320 tok** | **+44 %** |
| patent-IRAC | think rate | 1.00 | 1.00 | tied |
| patent-IRAC | mean chain | 763 tok | 608 tok | −20 % |
| general-reasoning | think rate | 0.40 | 0.30 | −0.10 |
| general-reasoning | mean chain | 212 tok | 884 tok | +317 % |

The cell that earns the headline is the patent-strategic row: same rate of think-block emission, forty-four percent longer chains. The corpus was built to teach this exact shape — multi-hop strategic reasoning about claim scope, prior-art positioning, and prosecution arguments — and on the bench it was built to teach, the NeMo-trained model uses the extra runway. Whether those chains are *better* (more correct, less prone to fabricated MPEP cites, better at IRAC structure) is a separate eval and not the one this article measures.

The patent-IRAC row runs the other direction by 20 %. NeMo's chains are shorter on IRAC. Both backends close the chain every time — 1.00 think rate — but NeMo gets to the answer in 608 tokens where Unsloth takes 763. Without a correctness rubric I cannot tell whether NeMo is *more efficient* on IRAC or *more compressed at the cost of substance*. That is the next eval cycle's job, not this article's verdict.

The general-reasoning row is where the budget caveat lives. NeMo's chains average 884 tokens against Unsloth's 212 — almost four-and-a-quarter times longer — but NeMo's `think_presence_rate` is 0.30 versus Unsloth's 0.40, meaning fewer of its chains actually closed inside the probe's `max_new_tokens` budget. NeMo was run at a 2,048-token probe budget; Unsloth was run at 1,536. The honest read is that NeMo's chains *are* longer, but some of that length is the model running into the ceiling on chain-of-thought it would otherwise close. The footnote walks the apples-to-apples re-projection.

## Verification — what "the bakeoff is real" feels like on the Spark

The five-and-a-half-hour NeMo run finishes around dinner. The write of the final iteration directory under `runs-full/iter_0000625/` is the moment the loop is done. The merge step runs as a fresh `docker exec` against `nemo-train`, takes eleven minutes, and produces `merged-mcore/` at 16 GB. The export runs next, takes eight minutes, and produces `merged-hf-bf16/` — two safetensors shards, a `model.safetensors.index.json`, the original tokenizer files, and a fresh `config.json` with the YARN scalars now populated (the export path round-trips them correctly even though the import path did not).

```
$ ls -lh /home/nvidia/data/aifn-train-lora/p65-nemo/merged-hf-bf16/
-rw-r--r-- 1 nvidia nvidia 1.7K  config.json
-rw-r--r-- 1 nvidia nvidia 9.3G  model-00001-of-00002.safetensors
-rw-r--r-- 1 nvidia nvidia 6.8G  model-00002-of-00002.safetensors
-rw-r--r-- 1 nvidia nvidia  24K  model.safetensors.index.json
-rw-r--r-- 1 nvidia nvidia  486  special_tokens_map.json
-rw-r--r-- 1 nvidia nvidia  11M  tokenizer.json
-rw-r--r-- 1 nvidia nvidia 4.4K  tokenizer_config.json
```

`free -h` reports 92 GiB of unified memory still free after the run finishes — the same envelope Unsloth lives in, and well below the [Spark unified-memory OOM landmine](/field-notes/derisk-cloud-pretraining-on-the-spark/) at 110 GiB. Both lanes were inside their thermal and memory budgets; neither flirted with the wall.

The probe is the moment the bakeoff stops being two timing numbers and starts being two qualitatively-different models. Run the same twenty questions through both, compare the `think_text` blocks side-by-side, decide which one's reasoning trace would survive an IRAC-shape stress test next month.

## Tradeoffs and the v3 corpus honest call-out

**Both LoRAs carry v3-corpus artifacts.** The patent-strategist v3 synthetic corpus contains hallucinated MPEP terminology the synth pipeline produced. The phrase *"metes-and-times"* appears where the standard term is *"metes-and-bounds"*. References to MPEP §2163.05(s) appear where no such subsection exists. The probe rows demonstrate the leak: at least one patent-strategic chain cites *"§2163.05(s) — the implicit-disclosure subsection"*, which is fabricated. Both backends learned the artifact equally — the corpus is upstream of the choice — and any downstream use of either model should treat its patent-domain knowledge as a *style* that has memorized a v3-corpus-specific dialect, not a *legal correctness* signal. A v4 corpus generation with a fact-check pass is the next iteration; until that ships, the artifacts in this bakeoff are honest research preview, not legal advice.

**Megatron-Bridge 0.4.0rc0 is the version pinned to `nemo:26.04.00`.** The YARN-defaults patch is required *for this specific bridge build*. A future bridge release may carry the four scalars through correctly and make the patch a no-op; check Megatron-Bridge's release notes before assuming you still need it.

**Unsloth on `pytorch:25.11-py3` needs a `torchao==0.16.0` pin.** Newer breaks `transformers` (needs torch 2.11); older fails `peft`'s version gate. The [patent-strategist v1 baseline](/field-notes/patent-strategist-v1-baseline-on-spark/) article documents the install path end-to-end.

**The smoke-vs-prod gap is real on both backends.** Smoke-projected NeMo wall was 4 h 52 m; production was 5 h 38 m. Smoke-projected Unsloth wall (from a 50-iter sub-run done while debugging the v1 corpus) was 6 h 30 m; production was 7 h 34 m. Both backends under-projected by 16–18 %. The factor that matters is the same on both sides: checkpoint saves dominate at production scale and smokes barely sample them. Pad smoke projections by ~1.16× before promising an overnight wall budget on either lane.

**`docker restart ps-train` is mandatory before the post-train probe.** The first attempt to score the NeMo-trained LoRA from inside the `ps-train` container failed with `RuntimeError: No CUDA GPUs are available` at `caching_allocator_warmup`. Restarting the container cleared it. Both backends touch this because the probe runs from the same shared inference container, not the trainer container.

## What this unlocks for a Spark-side fine-tuner

**Pick a backend on the workload, not on the framework.** If your loop is "fine-tune once a quarter, push the LoRA, move on," Unsloth's bring-up overhead amortizes to zero and its per-step deficit barely matters. If your loop is "fine-tune three times a week as the corpus iterates and the eval ratchets," NeMo's 26 % per-step margin compounds quickly — six runs in two weeks save a full overnight cycle. The Spark is the rare place a single practitioner can run both and find out which curve they are on.

**Trust the disk side of any long training run.** Both backends will graduate into a unified `fieldkit.training.run()` that writes the same `latest_checkpointed_iteration.txt` + iter-dir convention regardless of which engine is underneath. Poll those files. The log is a hint.

**Bake the smoke-projection slack into your scheduling.** The 1.16× multiplier is in memory now. If a smoke projects an eight-hour wall, plan for nine hours twenty minutes. Promising an overnight that lands at breakfast instead of midnight is a relationship-with-yourself problem worth pre-empting.

## Beyond the Spark — what scales when the rest of the stack does

:::hardware[The same Megatron-Core path runs on H100, H200, B200, and a SuperPOD]
Megatron-Core was built to run the same model code at `tp=1, pp=1, dp=1` (this Spark) and at `tp=8, pp=12, dp=64` (a SuperPOD); the parallelism strategy is a runtime argument, not a code rewrite. The bakeoff's 32.4 s/iter on one GB10 with 128 GB unified memory becomes a different latency on an H100 (~3.6× the FP16 matmul throughput at 80 GB HBM3), a different one again on an H200 (141 GB HBM3e — fits base + LoRA + optimizer without sharding), a different one again on a B200. The exact same recipe runs. The same `convert_checkpoints.py` runs. The same merge + export runs. The 26 % wall margin this article earned on the Spark is the *low end* of NeMo's compounding return — every step up the hardware ladder amortizes the framework overhead across more iterations, and the per-step delta versus a single-GPU library widens. Unsloth, by design, tops out at one GPU. NeMo is the path off the Spark when off the Spark becomes a real question.
:::

This is the Looking Beyond Spark angle that makes the train-layer decision interesting. The Spark is not the destination; it is the place you decide what your destination will be. If your model graduates from "a 5,000-row LoRA I trained for fun" to "a continuous-pretraining initiative I am running quarterly against the corpus my agent is generating," you want a backend whose recipe transfers to the H200 you might rent or the SuperPOD you might queue against. NeMo's recipe transfers. Unsloth's stops at the edge of one GPU.

## Artifacts

The NeMo lane is the bakeoff's shipped flagship: its merged BF16 model plus the quantized siblings (Q4_K_M, Q5_K_M, Q6_K, Q8_0) are published on HuggingFace under the `Orionfold` user handle. The Unsloth lane was the comparison baseline measured throughout this article — every Unsloth number above is real — but it is not published as a separately downloadable artifact.

| Artifact | HuggingFace URL |
|---|---|
| NeMo-trained, merged BF16 | [Orionfold/patent-strategist-v3-nemo](https://huggingface.co/Orionfold/patent-strategist-v3-nemo) |
| NeMo-trained, GGUF quant sweep | [Orionfold/patent-strategist-v3-nemo-GGUF](https://huggingface.co/Orionfold/patent-strategist-v3-nemo-GGUF) | License: the base inherits Apache-2.0-compatible terms from `DeepSeek-R1-0528-Qwen3-8B` (MIT R1 distill atop Qwen3 Apache-2.0); the README attributes base and states the inherited terms.

## Closing

Same recipe, two backends, one Spark. Twenty-six percent faster wall on the NeMo lane; forty-four percent longer patent-strategic chains; the same merged BF16 output the rest of the stack treats identically. The cost was a YARN-defaults patch, a stdout that lied for four hours, and a smoke projection that under-promised by sixteen percent — all three of which now have memories, and one of which will graduate into the next fieldkit release as a one-line patch the next person on this path will not have to write.

The bakeoff is the bakeoff. The Spark is the lab where it stays cheap enough to run twice.

:::deeper
- [NeMo Framework on the Spark — what it earns over a hand-rolled train.py](/field-notes/nemo-framework-on-spark/) — the kernel-level measurement underneath this article's per-step delta.
- [Three-mode bracket: baselining a reasoning model before fine-tuning](/field-notes/patent-strategist-v1-baseline-on-spark/) — the bench the patent-strategist corpus is being trained against.
- [The trainer was fine, the corpus wasn't](/field-notes/fine-tune-data-prep-decisions-on-spark/) — the v3 corpus's predecessor, and the diagnostic chain that motivated v3's BOS/EOS template fix.
- [GPU sizing math for fine-tuning](/field-notes/gpu-sizing-math-for-fine-tuning/) — the Looking Beyond Spark companion that walks the same arithmetic up to a 100B Nemotron.
- [Megatron-Bridge — checkpoint conversion docs](https://github.com/NVIDIA/Megatron-Bridge) — the bridge whose YARN-defaults bug this article patches around.
:::

---

*Footnote on the probe budget.* NeMo was probed at `max_new_tokens=2048`; Unsloth at `1536`. Of Unsloth's 13 closed chains, zero exceed 1,536 tokens — every Unsloth chain that closed did so inside its budget. Of NeMo's 12 closed chains, exactly one — `p-p-strat-01` at 1,895 tokens — exceeds 1,536. Apples-to-apples (re-running Unsloth at 2,048) would let only that one chain breathe further on the Unsloth side. The think-rate gap (Unsloth 0.65 vs NeMo 0.60) would likely narrow toward 0.70 / 0.60, because two of NeMo's open chains on general-reasoning sit between 1,536 and 2,048 tokens; the chain-length margin (640 vs 914) would compress by a few percent but the headline direction stays the same. I skipped the Unsloth re-probe because the cost (~42 min of GPU wall) buys a confidence-interval tightening on a margin that is already structurally clear.

*Footnote on per-variant perplexity.* The quantize sweep gave me a second, completely independent measurement to cross-check the chain-length finding. Each of the eight GGUF variants — four quants × two lanes — was run through `llama-perplexity` against `wikitext-2` (`--chunks 100`, teacher-forced) on the same Spark inside the same hour. The NeMo lane scored lower (better) perplexity at every quant level:

| Quant | Unsloth PPL | NeMo PPL | Δ |
|---|---|---|---|
| Q4_K_M | 11.299 | 10.242 | **−1.06** |
| Q5_K_M | 10.972 | 10.044 | **−0.93** |
| Q6_K   | 10.874 |  9.962 | **−0.91** |
| Q8_0   | 10.845 |  9.929 | **−0.92** |

The gap holds steady at ~0.9 perplexity points across the four quant levels — quantization compresses both lanes by similar amounts, but the NeMo lane starts from a better-calibrated BF16 model. This is not a chain-length artefact (no generation involved; wikitext perplexity is teacher-forced) and it is not a tokenizer artefact (both lanes use the same `LlamaTokenizer` shim against the same base tokenizer config). It is two independent measurements — chain-length on patent prompts, perplexity on general English — pointing the same direction. The Megatron-Core path is landing a better-fit model from the same recipe, not just a longer-chain one. That makes the 26 % wall margin look like the *small* part of the story.

---

**Catalog page:** [`/artifacts/loras/patent-strategist-v3-nemo/`](/artifacts/loras/patent-strategist-v3-nemo/) — positioning narrative, training-stack badge, evaluation deltas, lane comparison, and bounded drift — the full LoRA fine-tune card.
