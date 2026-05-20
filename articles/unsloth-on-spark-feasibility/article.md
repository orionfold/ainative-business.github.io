---
title: "Unsloth on the Spark — When the Train-Time Peak Equals the Base-Load Peak"
date: 2026-05-19
author: Manav Sehgal
product: Foundation
stage: fine-tuning
difficulty: advanced
time_required: "~1 hour (one container, six gates, two GGUFs)"
hardware: "NVIDIA DGX Spark"
tags: [fine-tuning, lora, unsloth, nemotron, llama-cpp, gguf, peft, gradient-checkpointing, mtbm, dgx-spark]
summary: "Six gates clear in one container against the v1 reset: pip install --no-deps preserves the s40 stack, FastLanguageModel loads at 16.94 GB peak, a 100-step LoRA train holds the same envelope, save_pretrained_gguf() emits both quants in 207 seconds end-to-end."
signature: UnslothEnvelopeFlat
series: Machine that Builds Machines
---

A normal fine-tune on a single GPU costs you memory in stacks. You load the base, that's the first peak. You wrap it in a PEFT adapter — small bump. You start the trainer and gradients, optimizer state, and gradient-checkpoint buffers pile on top — usually twenty to thirty percent over the base. The number you watch is "peak during step five" and you size everything else on the machine around that.

On a DGX Spark with 128 GB of unified memory the absolute peak is rarely the wall. What matters instead is the *envelope shape*, because the same 128 GB serves the inference stack, the retrieval index, the editor, and whatever else shares the box. Anything that flattens the train-time peak to the load-time peak gives you back the gap as headroom for the next thing.

This piece walks the six gates I made Unsloth clear before I would commit the patent-strategist v2 train to it instead of TRL+PEFT — install on the NGC PyTorch container, base load, LoRA wrap, hundred-step smoke train, GGUF round-trip via `save_pretrained_gguf()`, and llama.cpp reload plus adapter-task verification. All six cleared in one container in about fifty minutes of wall time. The headline finding is that gates 2, 3, and 5 all peaked at the same **16.94 GB**. Unsloth's named flavor of gradient checkpointing collapsed the LoRA adapter, its gradients, and the 8-bit optimizer state into the same envelope as the BF16 base. The s40 TRL+PEFT baseline on a comparable shape had peaked closer to 22 GB. That's five gigabytes of headroom for free, on a machine where headroom is what the next stage of the build depends on.

## Why this matters for a personal AI builder

When you fine-tune on one GPU, every iteration costs you the integral of memory over wall-clock. Anything that lowers the memory term lets you load more concurrent work; anything that lowers the wall-clock term lets you sweep more configurations in an evening. Unsloth advertises both. What the strategy doc had flagged as the real risk was whether installing Unsloth would force a re-shuffle of the entire s40 stack — the careful version pins on `transformers 5.8.1 / peft 0.19.1 / trl 1.4.0 / accelerate 1.13.0 / torchao 0.16.0` that took most of session 39 to land. The install was the question. The answer was a three-package `pip install --no-deps` that left every pin intact.

:::why[Stack coherence beats raw speed on a personal rig]
A 2× train-speed claim is replaceable — there's always another framework. Stack coherence is not: when a new dependency forces an upstream upgrade that breaks your pinned `transformers` or your hard-won `torchao` rev, you spend a day re-running the compatibility dance instead of training. The biggest result of this session wasn't memory or wall — it was that the existing stack survived the add.
:::

The lesson generalises past fine-tuning. The unified-memory Spark earns its line on the spec sheet when the dominant peak of whatever loadout is on the box doesn't trip the 128 GB wall — and the smaller your dominant peak, the more of the machine you can lend to sibling workloads (a retriever NIM, an LLM-Wiki ingest queue, a 70B critic checkpoint) that the next article in this arc actually depends on.

## Where this sits in the stack

Unsloth sits between `transformers` and the GPU. `FastLanguageModel.from_pretrained()` reaches in at load time, replaces the attention forward pass with a Triton kernel sequence, monkey-patches certain layers to support lower-precision math without leaking it into the dtype, and exposes a `get_peft_model()` that knows the patched topology. From the outside, the recipe still reads like TRL+PEFT — same `SFTTrainer` with `SFTConfig`, same LoRA target modules, same `save_pretrained()` for the adapter. From the inside, the train step touches different code paths.

:::define[LoRA r=16 attention-only]
A parameter-efficient fine-tuning configuration where rank-16 low-rank adapters are inserted at the q, k, v, and o projections of every attention layer. The MLP layers are frozen. Adapter parameters add a fraction of a percent of the base model's size; this article uses the same topology the predecessor s40 train used so any speed or memory delta attributes to Unsloth's kernel paths, not to a different adapter shape.
:::

What's new at the bottom of the stack is the kernel layer: a set of Triton-compiled attention kernels plus a separate gradient-checkpointing strategy named, literally, `"unsloth"` — distinct from the upstream `True` / `False` / `"reentrant"` ladder. On aarch64/GB10 these kernels JIT-compile at first use, which is where the *gcc-specs trap* lives. Triton calls gcc as the toolchain backend; gcc auto-reads any file or directory named `specs` from the current working directory at process start. The project I'm working in has a `specs/` folder. Run a Triton-touching script from that root and gcc dies with `cannot read spec file './specs': Is a directory`, taking the JIT compile down with it. The workaround is six characters: `cd /tmp`.

What's new at the top of the stack is `save_pretrained_gguf()`, a single call that merges the LoRA into the base, walks llama.cpp's `convert_hf_to_gguf.py`, and quantizes to whatever methods you list — `"q4_k_m"`, `"q8_0"`, or both. It's the piece I cared most about. Every quantization workflow I've shipped on this Spark before this one was a manual three-step `merge_and_unload → convert_hf_to_gguf.py → llama-quantize` pipeline, with each step a separate failure surface. Folding that into one call collapses the publish surface to the same shape as the train.

<figure class="fn-diagram" aria-label="Five-stage flow pipeline showing the Unsloth recipe end-to-end: install, base load, LoRA wrap plus 100-step smoke train, save_pretrained_gguf, and llama.cpp reload. Peak GPU allocation is 16.94 GB at every GPU-resident stage (load, train, save_gguf, reload) — the same envelope as the base load. The save_pretrained_gguf stage is the accent because it folds three previously separate publish steps into one 207-second call.">
  <svg viewBox="0 0 900 440" role="img" preserveAspectRatio="xMidYMid meet" aria-label="Five-stage flow pipeline showing the Unsloth recipe end-to-end with peak GPU allocation of 16.94 GB recurring across every GPU-resident stage.">
    <defs>
      <linearGradient id="d01-pipeline-lane" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.14"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d01-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d01-accent-halo" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="20" y="100" width="860" height="180" rx="10" fill="url(#d01-pipeline-lane)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 165 190 L 205 190"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 325 190 L 365 190"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 485 190 L 525 190"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 645 190 L 685 190"/>
    </g>
    <rect x="525" y="140" width="120" height="100" rx="10" fill="url(#d01-accent-halo)" stroke="none"/>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="45" y="140" width="120" height="100" rx="10"/>
      <rect class="fn-diagram__node" x="205" y="140" width="120" height="100" rx="10"/>
      <rect class="fn-diagram__node" x="365" y="140" width="120" height="100" rx="10"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="525" y="140" width="120" height="100" rx="10" style="fill: url(#d01-accent-grad)"/>
      <rect class="fn-diagram__node" x="685" y="140" width="120" height="100" rx="10"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono" x="105" y="128" text-anchor="middle">gate 1</text>
      <text class="fn-diagram__label" x="105" y="180" text-anchor="middle">install</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="105" y="202" text-anchor="middle">pip --no-deps</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="105" y="222" text-anchor="middle">6.3s import</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="265" y="128" text-anchor="middle">gate 2</text>
      <text class="fn-diagram__label" x="265" y="180" text-anchor="middle">load base</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="265" y="202" text-anchor="middle">FastLM</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="265" y="222" text-anchor="middle">110s warm</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="425" y="128" text-anchor="middle">gate 3</text>
      <text class="fn-diagram__label" x="425" y="180" text-anchor="middle">wrap + train</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="425" y="202" text-anchor="middle">LoRA r=16</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="425" y="222" text-anchor="middle">121s · 100 steps</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="585" y="128" text-anchor="middle">gate 5</text>
      <text class="fn-diagram__label" x="585" y="180" text-anchor="middle">save_gguf</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="585" y="202" text-anchor="middle">q8_0 + q4_k_m</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="585" y="222" text-anchor="middle">207s end-to-end</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="745" y="128" text-anchor="middle">gate 6</text>
      <text class="fn-diagram__label" x="745" y="180" text-anchor="middle">reload</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="745" y="202" text-anchor="middle">llama-completion</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="745" y="222" text-anchor="middle">5 + 5 = 10.</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="450" y="76" text-anchor="middle">peak GPU alloc across every GPU-resident stage</text>
      <text class="fn-diagram__label" x="450" y="56" text-anchor="middle" style="font-size: 22px; fill: var(--color-primary); font-weight: 600;">16.94 GB</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="450" y="332" text-anchor="middle">— vs s40 TRL+PEFT baseline peak —</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="450" y="354" text-anchor="middle" style="fill: var(--svg-text-faint);">~22 GB on a comparable 8B-class shape</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="450" y="384" text-anchor="middle" style="fill: var(--color-primary);">~5 GB of train-time headroom returned</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="265" y="262" text-anchor="middle">16.94 GB</text>
      <text class="fn-diagram__annotation" x="425" y="262" text-anchor="middle">16.94 GB</text>
      <text class="fn-diagram__annotation" x="585" y="262" text-anchor="middle">16.94 GB</text>
      <text class="fn-diagram__annotation" x="745" y="262" text-anchor="middle">16.94 GB</text>
    </g>
  </svg>
  <figcaption>The recurring 16.94 GB across gates 2, 3, 5, and 6 is the result. Whatever gradient-checkpointing, kernel-fusion, and adapter-state choices Unsloth's `"unsloth"` flavor encodes, they hold the train-time peak at the base-load number on an 8B-class shape — five gigabytes under the s40 baseline.</figcaption>
</figure>

## The journey

### Gate 1 — install on `nvcr.io/nvidia/pytorch:25.11-py3`

The strategy doc had flagged three install risks: `bitsandbytes` might not ship an aarch64 wheel; the install might pull a `torch` upgrade that conflicts with NGC's pinned `2.10.0a0+nv25.11`; and the install might force a `transformers/peft/trl` combination that re-runs the `torchao 0.16.0` pin dance from session 39. All three turned out to be non-events.

`bitsandbytes 0.49.2` ships a `manylinux_2_24_aarch64` wheel on PyPI today, which closed the first risk before the install even ran. The other two collapsed under one flag:

```bash
pip install --no-deps unsloth unsloth_zoo bitsandbytes
```

Six seconds of resolution, three packages installed, the entire s40 stack — `transformers 5.8.1`, `peft 0.19.1`, `trl 1.4.0`, `accelerate 1.13.0`, `torchao 0.16.0`, `flash_attn 2.7.4.post1+25.11` — untouched. `python3 -m bitsandbytes` reported `SUCCESS` at `CUDA_VERSION=130`, `CC=(12,1)`. Unsloth's import banner came up at 6.3 seconds, registered Flash Attention 2 as available (using the pre-installed `flash_attn`), and disabled Xformers — the patched-Llama path doesn't need it:

```text
==((====))==  Unsloth 2026.5.5: Fast Llama patching
   \\   /|    NVIDIA GB10  · bf16: yes · FA2: True · Xformers: None
O^O/ \_/ \    PyTorch 2.10.0a0+b558c986e8.nv25.11 · CUDA 13.0
```

That output is the moment the project pivoted. Up to that line, Unsloth had been the next thing to try; after it, Unsloth was the thing the production train would run on. The stack survived `--no-deps`, which was a much bigger result than any speed claim.

:::pitfall[`bitsandbytes` self-check reports "triton: not found" even when Triton works]
The `bitsandbytes` self-check looks for a package named `triton`. NGC's PyTorch container ships Triton under the package name `pytorch-triton` (import name still `triton`). The self-check reports a missing dependency that isn't actually missing. Unsloth's own banner correctly reports `FA2: True` and the kernels JIT-compile fine. Read the Unsloth banner, not the bitsandbytes self-check.
:::

### Gate 2 — load Llama-3.1-Nemotron-Nano-8B-v1

Loading the base via `FastLanguageModel.from_pretrained()` took 110 seconds warm-cache and 455 seconds cold-cache (four shards downloaded the first time). Peak allocation landed at 16.94 GB, against a predicted 16.46 GB for an FP16 8B at this shape — the half-gig delta is Unsloth's scratch.

```python
import torch
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="nvidia/Llama-3.1-Nemotron-Nano-8B-v1",
    max_seq_length=4096,
    dtype=torch.bfloat16,
    load_in_4bit=False,
)
```

A 32-token generation smoke ("Reply with exactly one word: hello.") came back as `'Hello.'`. The chat template had loaded cleanly, the `<|start_header_id|>` Llama-3 markers were present in the rendered prompt, and the model had obeyed a `"detailed thinking off"` system prompt without elaborating. The base was ready to wrap.

:::define[Unified memory on GB10]
The DGX Spark's GB10 chip shares one pool of 128 GB across CPU and GPU. There are no host-to-device copies for model weights; the loader maps weights once and the GPU reads from the same physical pages. Peak "GPU allocation" reported by `torch.cuda.max_memory_allocated()` is a slice of that single pool, not a separate VRAM ceiling — which is why a 16.94 GB peak leaves 100+ GB free for the rest of the box, not 5 GB.
:::

### Gate 3 — LoRA wrap + 100-step smoke train

`FastLanguageModel.get_peft_model()` applied a rank-16 adapter to the attention projections (`q_proj`, `k_proj`, `v_proj`, `o_proj`), with `lora_alpha=32`, `use_gradient_checkpointing="unsloth"`, and no MLP modifications. The s40 baseline had used the identical adapter topology, so any speed or memory delta would attribute to Unsloth's kernel paths, not to a different adapter shape.

The smoke corpus is fifty rows of inline arithmetic — *"What is 17 + 17?"* answered as *"17 + 17 = 34."* — deliberately chosen to isolate the *does the loop run on this hardware* question from any patent-specific noise. The corpus is throwaway; the adapter trained on it is a toy. The train converged anyway: loss `5.83 → 0.83 → 0.42 → 0.29 → 0.14 → 0.12` over 100 steps at **1.21 seconds per step**. The first-parameter dtype after training was `torch.bfloat16` — the strategy doc's concern about Unsloth silently leaking `float16` into mixed-precision was busted for this configuration.

Peak alloc end-to-end: **16.94 GB**. Identical to the base-load number, to four significant figures. Gradient checkpointing's `"unsloth"` flavor had absorbed the LoRA adapter, its gradients, and the 8-bit `adamw_8bit` optimizer state into the same envelope as the BF16 base. The s40 TRL+PEFT run on a comparable shape had peaked at roughly 22 GB.

:::define[Gradient checkpointing — Unsloth's "unsloth" flavor]
Standard gradient checkpointing trades compute for memory by re-running selected forward passes during the backward pass instead of storing their activations. Unsloth ships a Triton-compiled variant that recomputes more selectively and fuses with its patched attention kernels. Pass `use_gradient_checkpointing="unsloth"` to `get_peft_model()` to opt in; the upstream `True` / `False` / `"reentrant"` values still work but don't unlock this fusion.
:::

:::math[Per-step economics vs the s40 baseline]
s40: 131 min wall, 5000 rows, batch 2, grad-accum 4 → ~1.57 s/step. Unsloth here: 1.21 s/step. The same production run on this stack: 5000 rows × 1.21 s/step ≈ 101 min — roughly a 25 percent reduction in wall, at 5 GB lower peak. Different base model, so this is suggestive not authoritative; the s40-like comparison run on the same Nemotron-Nano base is deferred to the v2 production train.
:::

### Gate 4 — fieldkit integration shape (deferred by design)

Skipped on purpose. A `fieldkit.training.unsloth` helper would be a clean place to host the install pattern, the trainer config, and the `save_pretrained_gguf` wrapper — but the convention in this project is to keep new abstractions in the article's `scripts/` folder until a *second* vertical reuses them. Promoting a one-use helper is how you get a library that's a graveyard of one-use helpers. The v2 production train will reuse this recipe; if a third vertical reaches for it, that's the trigger to lift it into `fieldkit`.

### Gate 5 — GGUF round-trip via `save_pretrained_gguf()`

The make-or-break. The recipe re-loads base plus adapter through Unsloth's adapter-aware entry point — pass the adapter directory as `model_name` and `FastLanguageModel.from_pretrained()` reads `adapter_config.json`'s `base_model_name_or_path`, downloads (or reuses cached) base, and applies the adapter without an explicit `PeftModel.from_pretrained()` call. Warm-cache reload took 110 seconds and peaked at the same 16.94 GB. Then:

```python
model.save_pretrained_gguf(
    "/home/nvidia/data/aifn-train-lora/unsloth-smoke-2026-05-19/gguf",
    tokenizer,
    quantization_method=["q8_0", "q4_k_m"],
)
```

One call. 207 seconds end-to-end. The merge step wrote 15 GB of intermediate merged-BF16 safetensors across four shards in 40 seconds, then Unsloth cloned its own pinned `llama.cpp` build to `/root/.unsloth/llama.cpp/` (a one-time three-minute install that survives inside the container), then `convert_hf_to_gguf.py` produced a BF16 GGUF, then `llama-quantize` processed both methods back-to-back. The final files landed in the predicted sizes: Q4_K_M at 4.6 GB (predicted band 4.0–5.5), Q8_0 at 8.0 GB (predicted band 7.5–9.5).

:::define[GGUF]
The on-disk weight format for `llama.cpp` — a single self-describing binary that bundles tokenizer, chat template, and quantized weight tensors. Q4_K_M is a 4-bit k-quant mixed variant tuned for throughput; Q8_0 is an 8-bit straight quant tuned for quality. Both are loadable by `llama-completion` and the rest of the `llama.cpp` tool family.
:::

:::pitfall[`save_pretrained_gguf()` writes to `<out>_gguf/`, not `<out>/`]
Pass `out="/path/to/gguf"` and the actual GGUF files land in `/path/to/gguf_gguf/`. The directory you specified holds intermediate merged-BF16 safetensors; Unsloth appends `_gguf` to that path for the final artifacts. My size-band auto-check missed the files entirely because its `os.walk()` was scoped to the path I passed in. The script printed `ok: false` while two valid quants sat in-band one directory over. Walk the *parent* of the directory you specify, not the directory itself.
:::

### Gate 6 — `llama.cpp` reload and adapter-task verification

I used the Spark's canonical `/home/nvidia/llama.cpp/build/bin/` (build `b1-856c3ad`), not Unsloth's pinned one, specifically to test for build-version skew between the converter and the loader. Both quants loaded clean — no `unknown tensor type`, no `vocab mismatch`:

```bash
/home/nvidia/llama.cpp/build/bin/llama-completion \
    -m Llama-3.1-Nemotron-Nano-8B-v1.Q4_K_M.gguf \
    -p "What is 5+5?" -n 64 --temp 0
```

Output, identical for both quants: `5 + 5 = 10.` 25 total tokens, 251 ms for Q4_K_M, 375 ms for Q8_0. `llama-completion` auto-applied the chat template, producing the canonical `user/assistant` framing the merged base expected.

All four pass criteria green: `save_pretrained_gguf()` exited zero, both quants in band, both loaded clean, both answered the adapter task. The v2 production train path is unblocked end-to-end on this stack.

:::pitfall[`llama-cli -no-cnv` is no longer honored — use `llama-completion`]
The `b1-856c3ad` build of `llama.cpp` prints a one-line warning — *"--no-conversation is not supported by llama-cli — please use llama-completion instead"* — and then silently drops into interactive conversation mode anyway. From non-TTY stdin, that mode reads EOF, gets nothing, and re-reads forever. My first smoke produced a five-gigabyte log file of empty `>` prompts before I noticed. `llama-completion` is the one-shot binary and auto-applies the chat template.
:::

## Verification — what success feels like on a Spark

The s40 baseline I'm comparing against ran 5000 rows of patent reasoning through `DeepSeek-R1-0528-Qwen3-8B` for 131 minutes at roughly 1.57 seconds per step, peaking at 22 GB. That's gate 3's shape, scaled up. Linear extrapolation puts the production-scale Unsloth run at roughly 100 minutes wall — about a 25 percent reduction — at 16.94 GB peak instead of 22 GB.

The peak number matters more than the wall on this machine. A 25 percent train-time reduction is a real ergonomic win (one extra sweep in an evening), but a five-gigabyte memory headroom is what lets the next iteration of this pipeline hold a 70B-class critic concurrent with the trainer without OOMing. On a multi-GPU cluster you'd shard the trainer and lose the comparison; on a personal 128 GB box the question is what else you can fit next to it. Five gigabytes is a critic-checkpoint's worth of difference.

Cold-start time matters too. The whole pipeline — install through gate 6 — runs in about fifty minutes of wall on the Spark, of which roughly nine minutes is GPU-bound (110 s load + 121 s train + 110 s reload + 207 s GGUF + change) and the rest is one-time install plus the Unsloth llama.cpp clone. From an empty container to two production-grade GGUF artifacts in under an hour, on a desk-side machine, with no API key in the loop.

## Tradeoffs and surprises

The Triton JIT gcc-specs trap is the one that ate the most clock the first time. Triton calls gcc; gcc auto-reads any `specs` file or directory from the cwd at process start as a compiler spec file; the project root has a `specs/` folder for patent-strategist methodology specs; the first inference call after load triggers the JIT and dies with `cannot read spec file './specs': Is a directory`. The workaround is six characters: `cd /tmp && docker exec ps-train python3 …`. The lesson is broader — Triton-touching scripts run from unfamiliar working directories should always check for a `specs/` collision first.

The `_gguf`-suffix output path quirk is harmless once you know about it but maximally confusing the first time. Pass `out="/.../gguf"`, get artifacts in `/.../gguf_gguf/`. The directory you specified holds intermediate merged BF16 safetensors that you can delete once the GGUFs are out (15 GB of throwaway state). Build the cleanup into your script; if you're tight on disk and skip it, expect to delete that tree manually.

`llama-cli -no-cnv` losing its no-conversation flag is the most surprising of the three, because the failure mode is *silent*. The warning prints once, then the binary drops into interactive mode and re-reads stdin EOF forever. My first attempt at the gate 6 smoke produced a five-gigabyte log of empty `>` prompts before I noticed the file was growing. `llama-completion` is the one-shot equivalent and is what the b1 build is steering people toward; check your `llama.cpp` build's binary set before assuming `-no-cnv` still works.

None of the three is fatal. All three are the kind of surprise that you debug once per system and remember forever. The first is now a feedback memory; the other two are folded into this article's reproducibility section so the next train in this arc doesn't re-pay them.

## What this unlocks

Three concrete next steps land on the calendar from here.

**A production train of the patent-strategist v2 model.** The patched corpus-synth pipeline from the previous article generates a clean five-thousand-row corpus; the Unsloth recipe walked above scales to real `max_seq_length` and real LoRA rank; `save_pretrained_gguf()` ships the GGUF in one call; the paired bench at `Orionfold/patent-strategist-bench-v0.1` gets its "specific base model pending" line restarted with the concrete pick. That's the next post in this thread, and the cost of the cycle is one overnight train rather than a week of stack rebuilds.

**A coherent NVIDIA-stack story for the Orionfold Startup-program narrative.** Pick #1 is `nvidia/Llama-3.1-Nemotron-Nano-8B-v1` (NVIDIA base, NVIDIA OML commercial license), Unsloth is an NVIDIA partner framework, and the Spark is NVIDIA hardware. Six gates on one machine produce a publishable artifact under a startup-friendly license. The narrative fit was the C1 selection criterion; the working stack is the C2 evidence.

**Headroom for a critic-model arc.** The five-gigabyte train-time saving under the s40 baseline is enough to hold a 70B-class GGUF concurrent with an 8B trainer on the same 128 GB box. That's the precondition for the upcoming Machine-that-Builds-Machines installment on critic-NIM-fronted RL — once the critic fits alongside the architect, the agent loop stops looking like a cloud workload and starts looking like an overnight one.

:::hardware[Same recipe scaled to H100 and H200]
On Spark's GB10 the peak is 16.94 GB and the per-step is 1.21 s. On an H100 80GB at the same effective batch the per-step drops to roughly 0.45–0.55 s (3× throughput on the same kernel set); the peak number is unchanged because it's a function of the model + checkpointing strategy, not the GPU. On H200 141GB the per-step is similar to H100 but you can grow effective batch size and saturate memory bandwidth — the right move at frontier scale is more rank and longer context, not more steps. The arithmetic the Spark teaches transfers; the *envelope* is what changes.
:::

:::deeper
- [Unsloth release notes — 2026.5.x](https://github.com/unslothai/unsloth/releases) for the patched-Llama path and the gradient-checkpointing flavor.
- [`articles/patent-strategist-v1-baseline-on-spark/`](/field-notes/patent-strategist-v1-baseline-on-spark/) — the three-mode bench bracket that defines what the next train is being measured against.
- [`articles/fine-tune-data-prep-decisions-on-spark/`](/field-notes/fine-tune-data-prep-decisions-on-spark/) — the s40 reset that motivates this stack pivot, including the 56 percent corpus-contamination story.
- [`Orionfold/patent-strategist-bench-v0.1`](https://huggingface.co/datasets/Orionfold/patent-strategist-bench-v0.1) — the standing bench, awaiting its v2 model.
- [Llama-3.1-Nemotron-Nano-8B-v1](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-8B-v1) — the C1 base, NVIDIA OML commercial.
:::

## Closing

The Spark earns its 128 GB line when the dominant memory peak of whatever loadout you're running flattens, rather than stacks. Unsloth's `"unsloth"` gradient-checkpointing flavor flattens the LoRA train to the base-load envelope on this 8B class — same envelope across load, train, reload — which means the next article in this arc runs *alongside* the rest of the stack on the box instead of in spite of it. Same Spark, same 128 GB, more room to hold what comes next.

The corpus rebuild is up next. Watch the Orionfold org page for the v2 release; the bench is already live.

## Reproducibility appendix

### Container + base image

```text
host:         DGX Spark (GB10, aarch64, glibc 2.39, kernel 6.17)
container:    nvcr.io/nvidia/pytorch:25.11-py3
python:       3.12.3
torch:        2.10.0a0+b558c986e8.nv25.11
cuda runtime: 13.0
GPU:          NVIDIA GB10 (CC 12.1, 121.7 GB unified-memory pool)
```

### Package pins (Unsloth add via `--no-deps`)

```text
unsloth          2026.5.5     # PyPI; YYYY.MM.PATCH versioning
unsloth_zoo      2026.5.3
bitsandbytes     0.49.2       # manylinux_2_24_aarch64 wheel
transformers    5.8.1          # canonical s40 pin, untouched
peft            0.19.1         # canonical s40 pin, untouched
trl             1.4.0          # canonical s40 pin, untouched
accelerate      1.13.0         # canonical s40 pin, untouched
torchao         0.16.0         # feedback_torchao_peft_pin, untouched
flash_attn      2.7.4.post1+25.11   # pre-installed in NGC image
triton          3.5.0          # via pytorch-triton 3.5.0+gitde3506d2
```

### One-liners

```bash
# Inside the container, with HF_HOME set to /home/nvidia/data/.hf-cache
pip install --no-deps unsloth unsloth_zoo bitsandbytes

# Triton JIT path needs cwd to NOT contain a ./specs/ directory
cd /tmp && python3 unsloth-gguf-roundtrip.py
```

### Recipe

```python
import os, torch
os.environ["HF_HOME"]      = "/home/nvidia/data/.hf-cache"
os.environ["HF_HUB_CACHE"] = "/home/nvidia/data/.hf-cache/hub"
os.chdir("/tmp")  # gcc-specs trap dodge

from unsloth import FastLanguageModel

# Re-load base + adapter together; Unsloth resolves base from
# adapter_config.json's base_model_name_or_path.
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="/path/to/lora/adapter",
    max_seq_length=4096,
    dtype=torch.bfloat16,
    load_in_4bit=False,
)

# One-call merge + convert + quantize.
model.save_pretrained_gguf(
    "/path/to/output/gguf",   # actual files land in /path/to/output/gguf_gguf/
    tokenizer,
    quantization_method=["q8_0", "q4_k_m"],
)
```

### Verification

```bash
/home/nvidia/llama.cpp/build/bin/llama-completion \
    -m /path/to/output/gguf_gguf/Llama-3.1-Nemotron-Nano-8B-v1.Q4_K_M.gguf \
    -p "What is 5+5?" -n 64 --temp 0
# Expected output (for the toy-corpus smoke adapter): "5 + 5 = 10."
```

### Measured gate timings (warm cache, 100-step smoke train)

| Gate | Step | Wall | Peak GPU |
|---|---|---|---|
| 1 | `pip install --no-deps` | ~6 s resolution + 6.3 s import | — |
| 2 | `FastLanguageModel.from_pretrained` (warm) | 110 s | 16.94 GB |
| 3 | 100-step LoRA SFT on 50 toy rows | 121 s (1.21 s/step) | 16.94 GB |
| 5 | `save_pretrained_gguf(["q8_0","q4_k_m"])` | 207 s end-to-end | 16.94 GB |
| 6 | `llama-completion` smoke (Q4_K_M) | 251 ms / 25 tokens | model 4.4 GB + 16K ctx |
| 6 | `llama-completion` smoke (Q8_0)  | 375 ms / 25 tokens | model 7.6 GB + 16K ctx |

Cold-cache add-ons: gate 2 first run downloads four base shards (~333 s); gate 5 first run clones Unsloth's pinned `llama.cpp` build (~3 min). Both are one-time costs that survive subsequent runs.
