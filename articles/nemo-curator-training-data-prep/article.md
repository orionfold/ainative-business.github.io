---
title: "The Data-Path Envelope — When Real Tokens Beat Random Tokens at Pretrain Throughput"
date: 2026-04-25
author: Manav Sehgal
product: NeMo
stage: training
difficulty: intermediate
time_required: "~2 hours — 5 min for the corpus pull, 45 min for a derived container build, 2 min for the Curator pipeline + 40s tokenize, 3 min for the 8-config sweep, the rest is reading the numbers"
hardware: "NVIDIA DGX Spark"
tags: [nemo, nemo-curator, training, pretrain, data-prep, tokenization, autoresearch, dgx-spark]
summary: "Curator-cleaned wikitext-103 (109M tokens, 417 MiB packed) feeding the same 354M GPT pretrain loop from A2. Eight configs swept; data-path overhead is 0.01–0.04% across all of them. New peak: 14,980 tok/s — slightly above A2's random-token ceiling."
signature: DataPathOverhead
also_stages: [foundations]
series: Machine that Builds Machines
book_chapters: [10]
---

The previous article (`baseline-training-loop-on-spark`) measured the GB10's pretrain throughput with `torch.randint`-generated tokens — a kernel-only measurement that assumed the data path was free. That assumption is the kind of thing you have to *measure* before you trust it. So this article does the obvious follow-up: take a real corpus, run it through NeMo Curator's filter stages, tokenize with the same GPT-2 BPE the model expects, pack the result into a memory-mappable file, and feed that to the same training loop A2 used. If the data path costs anything material, throughput should drop. If it doesn't, the kernel envelope and the data envelope are the same envelope.

:::define[NeMo Curator]
NVIDIA's open-source data-curation pipeline for LLM pretrain corpora — Ray-orchestrated stages for unicode normalization, length filtering, n-gram repetition filtering, language ID, quality classification, and exact/fuzzy deduplication. Bundles CPU and GPU (cuDF / RAPIDS) execution paths so the same pipeline scales from a 0.5 GB wikitext to a 50 TB CommonCrawl shard. Lives in the `nemo-curator` PyPI package; not preinstalled in the NeMo container.
:::

The result is short to state: **the data path costs 0.01–0.04% of step time across every config we tried**, and the peak real-data throughput is **14,980 tok/s** — slightly *above* A2's random-token peak of 14,266. The data path is not the bottleneck on the GB10; it is, in practice, invisible. The harder question turns out to be *getting* the corpus into the form a training loop wants — and even there, the entire wikitext-103 corpus tokenizes in 40 seconds at ~2.7M tok/s on the Spark's CPU, finishing well before the GPU has eaten the first 50 K tokens of training data.

:::math[Why the data path disappears into the noise]
A 16 × 1024 batch is 16,384 int64 tokens = 128 KB per step. The unified-memory copy at ~5 GB/s clears that in ~25 µs; with `non_blocking=True` it overlaps with the prior step's optimizer update entirely. Step time is 1,094 ms; data time is 0.15 ms; ratio is 0.000137 — four zeros below the noise floor of step-to-step variance. There is no realistic single-GPU pretrain workload where this matters.
:::

Headline numbers up front, then the details:

| measurement | value |
|---|---:|
| corpus | wikitext-103-raw (HuggingFace parquet, train split) |
| raw size | 539 MB chars across 1.8M parquet rows |
| Curator pipeline wall time | **82.9 s** (8 stages, Ray-orchestrated) |
| docs after Curator filters | 668,856 (62.9% drop — most were short headers) |
| docs after exact dedup | 660,773 (1.2% drop) |
| tokenize wall (CPU, gpt2 BPE) | **40.0 s** at 2.73 M tok/s |
| packed memmap on disk | 109,339,897 tokens · 417.1 MiB int32 |
| data-path overhead during training | **0.01 – 0.04 %** of step time |
| peak real-data throughput | **14,980 tok/s** (b=16 / s=1024 / fp8) |
| comparison to A2 random-token peak (14,266) | **+5.0%** |

## Why this matters for the personal AI power user

The Autoresearch agent (still upcoming, A4) is going to be making decisions like *"this perturbation lowered val_bpb — keep it"*. Those decisions only mean something if the validation loss curve is honest, which means it has to come from real text. The agent can't be making decisions on synthetic-data loss curves and then expect them to generalize. So the question this article answers is upstream of A4's correctness: *can the Spark sustain its measured kernel throughput when the data is real?* If the answer were "no, real data drops you to 50% of the random-token rate," the agent would have to spend half its overnight budget on data plumbing instead of experiments. The answer is **yes** — and that result lets the agent loop be designed without a data-prep escape hatch.

There's also a simpler edge-AI story here. The Curator pipeline + tokenization + memmap packing for a 0.5 GB corpus runs end-to-end in **under three minutes** on the GB10 — including the 40-second BPE tokenization which sits at 2.7 M tok/s on a single CPU process. Cloud data-prep services charge by the row; on the Spark, this is essentially free wall time. For someone building a domain-specific corpus from their own writing, their company's docs, or a niche subset of the open web, the prep cost is dominated by *finding* the data, not by *processing* it.

:::why[Real-token loss is the only loss the agent can trust]
Random-token throughput sets a kernel ceiling, but it can't ground a learning-rate sweep — there's no signal in random data. Once the agent starts evaluating "did this perturbation lower val_bpb?", that loss has to come from a real corpus or its decisions are nonsense. If real data dropped throughput by 50%, the agent's overnight budget would be cut in half. Measuring 0.04% overhead is what lets the agent loop be designed without a data-prep escape hatch.
:::

## The sweep at architecture-glance

<figure class="fn-diagram" aria-label="Three-stage data-path pipeline. Stage 1: Curator pipeline reads HuggingFace parquet shards and runs unicode reformatter, newline normalizer, WordCountFilter, RepeatingTopNGramsFilter, and SymbolsToWordsFilter, writing cleaned JSONL. Stage 2: a manual exact-dedup hash pass, then GPT-2 BPE tokenization, then packing into a single int32 numpy memmap on disk. Stage 3: the data sweep harness opens the memmap and feeds 30-step training runs across 8 (batch, seq, precision) configurations, measuring data time and step time separately. Output: per-config tokens/sec for both the kernel-only path and the data+kernel path.">
  <svg viewBox="0 0 900 460" role="img" aria-label="Three-stage data-path pipeline: Curator clean → tokenize+pack → sweep training. Outputs per-config data-time vs step-time and tokens/sec."  preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="dpd-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.04"/>
      </linearGradient>
    </defs>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" d="M 270 100 L 330 100" />
      <path class="fn-diagram__edge" d="M 570 100 L 630 100" />
      <path class="fn-diagram__edge" d="M 270 250 L 330 250" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" d="M 570 250 L 630 250" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" d="M 765 130 L 765 220" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" d="M 765 280 L 765 370" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="80" y="60" width="190" height="80" rx="8" />
      <rect class="fn-diagram__node" x="330" y="60" width="240" height="80" rx="8" />
      <rect class="fn-diagram__node" x="630" y="60" width="240" height="80" rx="8" />
      <rect class="fn-diagram__node" x="80" y="210" width="190" height="80" rx="8" />
      <rect class="fn-diagram__node" x="330" y="210" width="240" height="80" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="630" y="210" width="240" height="80" rx="10" style="fill: url(#dpd-accent-grad)" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="630" y="370" width="240" height="60" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="95" y="84" text-anchor="start">RAW INPUT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="95" y="106" text-anchor="start">wikitext-103 parquet</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="95" y="126" text-anchor="start">300 MB · 1.8M rows</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="345" y="84" text-anchor="start">CURATOR · 8 stages</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="345" y="106" text-anchor="start">unicode · newlines · 3 filters</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="345" y="126" text-anchor="start">82.9 s · drops 62.9 % docs · keeps 94.6 % chars</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="645" y="84" text-anchor="start">CLEANED JSONL</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="645" y="106" text-anchor="start">668 K docs · 509 MB</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="95" y="234" text-anchor="start">EXACT DEDUP</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="95" y="256" text-anchor="start">SHA256 hash · pandas</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="95" y="276" text-anchor="start">5 s · drops 1.2 %</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="345" y="234" text-anchor="start">TOKENIZE + PACK</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="345" y="256" text-anchor="start">gpt2 BPE · int32 numpy memmap</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="345" y="276" text-anchor="start">40 s · 2.73 M tok/s · 109 M tokens</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="645" y="234" text-anchor="start">SWEEP · 8 configs</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="645" y="256" text-anchor="start">354M GPT · 30 steps · GB10</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="645" y="276" text-anchor="start">data 0.10–0.15 ms · step 294–1136 ms</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="645" y="394" text-anchor="start">RESULT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="645" y="410" text-anchor="start">peak 14,980 tok/s</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="645" y="426" text-anchor="start">data overhead ≤ 0.04 %</text>
    </g>
  </svg>
  <figcaption>Three stages, two output streams. Curator (Ray-orchestrated) does the filter pass; the dedup-tokenize-pack stage produces a single int32 memmap; the training sweep opens that memmap and measures data time and step time per iteration. Numbers under each stage are wall time on the Spark and the throughput at that stage. The accent box is where the GB10 actually lights up; everything to its left is one-time CPU work.</figcaption>
</figure>

## What the harness does — and what it intentionally doesn't

The Curator pipeline lives in [`evidence/prep_corpus.py`](./evidence/prep_corpus.py) and reads like the docs you'd hope to find:

```python
from nemo_curator.pipeline import Pipeline
from nemo_curator.stages.text.io.reader import ParquetReader
from nemo_curator.stages.text.io.writer import JsonlWriter
from nemo_curator.stages.text.modifiers import UnicodeReformatter, NewlineNormalizer
from nemo_curator.stages.text.modules import Modify, ScoreFilter
from nemo_curator.stages.text.filters import (
    WordCountFilter, RepeatingTopNGramsFilter, SymbolsToWordsFilter,
)

p = (
    Pipeline(name="wikitext_clean")
    .add_stage(ParquetReader(file_paths=WORK_PARQUETS_DIR, fields=["text"]))
    .add_stage(Modify(UnicodeReformatter()))
    .add_stage(Modify(NewlineNormalizer()))
    .add_stage(ScoreFilter(WordCountFilter(min_words=50, max_words=100_000),
                           text_field="text", score_field="word_count"))
    .add_stage(ScoreFilter(RepeatingTopNGramsFilter(n=3, max_repeating_ngram_ratio=0.18),
                           text_field="text", score_field="ngram_repeat_3"))
    .add_stage(ScoreFilter(SymbolsToWordsFilter(max_symbol_to_word_ratio=0.20),
                           text_field="text", score_field="symbol_to_word"))
    .add_stage(JsonlWriter(path=CLEANED_DIR))
)
p.run()
```

A few things this pipeline intentionally does not do:

- **No language ID.** Wikitext-103 is overwhelmingly English; running fasttext langid on it is honest but adds a model-load step and a per-doc forward pass that doesn't change the output meaningfully here. On a multilingual corpus (CommonCrawl WET, web scrape) `FastTextLangId` belongs in the chain — Curator ships it, and the lid.176.bin model is in the derived container at `/opt/curator-models/`.
- **No GPU dedup.** Curator's `ExactDuplicateIdentification` path uses cuDF + RAPIDS; it's the right tool when the corpus is hundreds of GB. At 0.5 GB, a single-process pandas hash + drop_duplicates finishes in 5 seconds and avoids the cuDF ↔ Curator orchestration mode-switch. The dedup happens in [`tokenize_and_shard.py`](./evidence/tokenize_and_shard.py), not Curator.

:::define[Exact dedup vs fuzzy dedup]
Exact dedup hashes each document (SHA256 / MinHash signature with no shingles) and drops byte-identical duplicates. Fuzzy dedup uses MinHash + LSH to find documents that overlap by some threshold (e.g. 80% of 5-shingles match) — catches near-duplicates from different scrapes. Pretrain corpora dedup *fuzzy* because the same news story appears verbatim across sites; small curated corpora often dedup exact because byte-identity is enough.
:::
- **No quality classifier.** `FastTextQualityFilter` would discriminate "Wikipedia-like" text from "random noise" — but on actual Wikipedia text that's a tautology. On a CommonCrawl corpus you'd want it.

The sweep harness in [`evidence/data_sweep.py`](./evidence/data_sweep.py) is A2's `sweep.py` with one delta: instead of `x = torch.randint(0, vocab, (batch, seq))`, batches come from a `CorpusBatcher` that walks a `numpy.memmap` of the packed tokens sequentially and copies to GPU with `non_blocking=True`. Step time and data time are measured separately so the article can report both.

:::define[`numpy.memmap` packed corpus]
A flat binary file containing tokenized IDs as a contiguous int32 array, exposed to Python via `numpy.memmap` so the OS pages it in on demand instead of loading it into RAM. Lookup is `arr[start:start+seq_len]` — no parsing, no record boundaries, no JSON. The training loop slides a window across this array; the page cache makes repeated reads essentially free after the first epoch.
:::

## The shape of the envelope

**Step-only throughput vs A2 (kernel envelope on the same hardware):**

| config | A2 random-token tok/s | A3 real-data tok/s | delta |
|---|---:|---:|---:|
| b=4 / s=1024 / bf16 | 12,641 | 13,158 | +4.1 % |
| b=8 / s=1024 / bf16 | 12,819 | 13,482 | +5.2 % |
| b=16 / s=1024 / bf16 | 13,626 | 14,422 | +5.8 % |
| b=4 / s=2048 / bf16 | 12,729 | 13,001 | +2.1 % |
| b=4 / s=1024 / fp8 | 13,462 | 13,921 | +3.4 % |
| b=8 / s=1024 / fp8 | 13,777 | 14,394 | +4.5 % |
| **b=16 / s=1024 / fp8** | **14,266** | **14,980** | **+5.0 %** |
| b=4 / s=2048 / fp8 | 13,202 | 13,740 | +4.1 % |

:::define[BPE tokenization]
Byte-pair encoding splits text into subword units learned from a corpus by iteratively merging the most frequent adjacent byte pairs. GPT-2's tokenizer ships ~50K merges; the result is a vocabulary that handles common English in 1 token per 0.75 words and falls back gracefully to bytes for OOV strings (emoji, code, foreign text). The pretrain loop sees integer IDs into this vocabulary, not raw text — tokenization is the bridge.
:::

A3 is consistently **2–6% faster than A2** at every matched config. That's surprising at first read — A3 has *more* work to do per step (the data path) — but the cause is sensible. A2's `torch.randint` runs on the GPU each step, contending with the model's own forward pass for SM cycles; A3's data path is a host-side mmap read and an `cudaMemcpyAsync` that overlaps with the previous step's optimizer update. On a single-GPU workload with no contention from sibling processes, the prefetch-and-overlap pattern wins back the random-gen overhead and then some.

**Data overhead is sub-millisecond at every config:**

| config | step ms | data ms | overhead % |
|---|---:|---:|---:|
| b=4 / s=1024 / bf16 | 311.3 | 0.12 | 0.04 |
| b=8 / s=1024 / bf16 | 607.6 | 0.14 | 0.02 |
| b=16 / s=1024 / bf16 | 1136.0 | 0.14 | 0.01 |
| b=4 / s=2048 / bf16 | 630.1 | 0.14 | 0.02 |
| b=4 / s=1024 / fp8 | 294.2 | 0.10 | 0.04 |
| b=8 / s=1024 / fp8 | 569.1 | 0.12 | 0.02 |
| b=16 / s=1024 / fp8 | 1093.7 | 0.15 | 0.01 |
| b=4 / s=2048 / fp8 | 596.2 | 0.12 | 0.02 |

<figure class="fn-diagram" aria-label="Data-overhead waterfall across the 8-config sweep. Eight horizontal bars stacked top to bottom, each one a config (batch / sequence / dtype). Bar lengths are proportional to step time in milliseconds, ranging from 294 ms (smallest config, fp8) to 1136 ms (largest config, bf16). At the start of each bar, the data-path overhead segment is rendered at the same pixel scale — and is invisible (sub-pixel) in every config because data_ms is between 0.10 and 0.15 milliseconds while step_ms is between 294 and 1136. The right-hand annotations report the overhead percentage per config, all of which fall in the range 0.01 to 0.04 percent. The accent bar is the largest config (b=16, s=1024, bf16) at 1136 ms — even at the slowest config the data line item is invisible at scale.">
  <svg viewBox="0 0 900 380" role="img" aria-label="Data-overhead waterfall across the 8-config sweep. Eight horizontal bars stacked top to bottom, each one a config (batch / sequence / dtype). Bar lengths are proportional to step time in milliseconds, ranging from 294 ms (smallest config, fp8) to 1136 ms (largest config, bf16). At the start of each bar, the data-path overhead segment is rendered at the same pixel scale — and is invisible (sub-pixel) in every config because data_ms is between 0.10 and 0.15 milliseconds while step_ms is between 294 and 1136. The right-hand annotations report the overhead percentage per config, all of which fall in the range 0.01 to 0.04 percent. The accent bar is the largest config (b=16, s=1024, bf16) at 1136 ms — even at the slowest config the data line item is invisible at scale." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-cur1-band-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-cur1-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d-cur1-accent-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="220" y="40" width="540" height="280" rx="10" fill="url(#d-cur1-band-grad)" stroke="none"/>
    <rect x="216" y="166" width="496" height="32" fill="url(#d-cur1-accent-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 220 40  L 220 320" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 355 40  L 355 320" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 490 40  L 490 320" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 625 40  L 625 320" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 760 40  L 760 320" />
      <path class="fn-diagram__edge" pathLength="100" d="M 220 320 L 760 320" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="220" y="56"  width="148" height="24" rx="2"/>
      <rect class="fn-diagram__node" x="220" y="92"  width="289" height="24" rx="2"/>
      <rect class="fn-diagram__node" x="220" y="128" width="540" height="24" rx="2"/>
      <rect class="fn-diagram__node" x="220" y="172" width="139" height="24" rx="2"/>
      <rect class="fn-diagram__node" x="220" y="208" width="271" height="24" rx="2"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="220" y="244" width="520" height="24" rx="2" style="fill: url(#d-cur1-accent-grad)"/>
      <rect class="fn-diagram__node" x="220" y="280" width="299" height="12" rx="2"/>
      <rect class="fn-diagram__node" x="220" y="280" width="283" height="12" rx="2"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="40" y="28"  text-anchor="start">DATA-PATH OVERHEAD · 8 CONFIGS · GB10 354M</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="212" y="74"  text-anchor="end">b=4 · s=1024 · bf16</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="212" y="110" text-anchor="end">b=8 · s=1024 · bf16</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="212" y="146" text-anchor="end">b=16 · s=1024 · bf16</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="212" y="190" text-anchor="end">b=4 · s=1024 · fp8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="212" y="226" text-anchor="end">b=8 · s=1024 · fp8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="212" y="262" text-anchor="end">b=16 · s=1024 · fp8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="212" y="296" text-anchor="end">b=4 · s=2048 · bf16 / fp8</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="372" y="74" text-anchor="start">311 ms · 0.04%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="513" y="110" text-anchor="start">608 ms · 0.02%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="764" y="146" text-anchor="start">1136 ms · 0.01%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="363" y="190" text-anchor="start">294 ms · 0.04%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="495" y="226" text-anchor="start">569 ms · 0.02%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="744" y="262" text-anchor="start">1094 ms · 0.01%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="523" y="296" text-anchor="start">~600 ms · 0.02%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="220" y="338" text-anchor="middle">0 ms</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="490" y="338" text-anchor="middle">600</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="760" y="338" text-anchor="middle">1200 ms</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="450" y="362" text-anchor="middle">data_ms is 0.10 – 0.15 ms — sub-pixel at this scale · the data path is invisible in every config</text>
    </g>
  </svg>
  <figcaption>Data overhead is sub-pixel at the step-time scale — the longest data path measured (0.15 ms) sits next to a 1,094 ms step, so the line item never lands on the chart.</figcaption>
</figure>

The biggest data-time number we measured was 0.15 ms (batch=16 × seq=1024 × fp8) — and it sits next to a 1,094 ms step, so it's a 0.01% line item. The reason is unsurprising: a 16 × 1024 batch is 128 KB of int64 to transfer, the GB10's unified-memory architecture means the host-to-device copy isn't crossing a PCIe lane, and the `non_blocking=True` flag lets the copy overlap with the previous iteration's gradient update. That's the cost: ~100 microseconds of bookkeeping. There is no realistic single-GPU pretrain workload where that matters.

## Tradeoffs, gotchas, and the things this measurement doesn't cover

**The data path is invisible *only because* the corpus fits in memory.** The 109 M-token packed file is 417 MiB — Linux page cache will hold it after the first read. If the corpus were 100 GB instead of 0.4 GB, the per-step `mmap[]` access would hit a page fault some fraction of the time, and that fraction is what determines whether the data path stays invisible. The article measures the small case honestly; the large-corpus case is a different envelope and would need its own measurement (probably with `madvise(MADV_SEQUENTIAL)` and an explicit prefetch thread).

:::pitfall[Plain `pip install` lands outside the NeMo container's venv]
The `nvcr.io/nvidia/nemo:26.04.00` container ships a `uv`-managed venv at `/opt/venv/`. The default `pip install …` writes to `/usr/local/lib/python3.12/dist-packages/`, which the venv's `python3` searches *after* its own site-packages. Installs appear to succeed, imports keep finding the older bundled copy, and you debug for an hour. Always invoke `/opt/venv/bin/python3 -m pip install …` explicitly. Same trap bites NeMo, PyTorch, and Triton containers.
:::

**Two of Curator's deps fight on aarch64 + the bundled NeMo container.** The honest install path:

1. The default `nvcr.io/nvidia/nemo:26.04.00` container does not ship `nemo-curator` — `pip install nemo-curator` works but you have to install into the right Python environment.
2. NeMo's container has a `uv` venv at `/opt/venv/`. Plain `pip install` lands in `/usr/local/lib/python3.12/dist-packages/`, which the venv-based `python3` searches *after* the venv's own site-packages. So the install appears to succeed, you import the package, you call it — and it crashes with a stale-version error from the venv's older copy. **Fix:** install with `/opt/venv/bin/python3 -m pip install …` so the install lands in `sys.prefix`.
3. `cosmos-xenna` (Curator 1.x's Ray-based execution backend) calls `pulp.LpVariable("z", lowBound=0)`, which is the pre-3.0 PuLP API. PuLP 3.x and 4.x renamed it. Pin `pulp<3` in the install command. The error message — `LpVariable.__init__() got an unexpected keyword argument 'lowBound'` — is opaque if you don't know to look for the autoscaler module.
4. RAPIDS `cudf-cu13` installs cleanly on aarch64 from `pypi.nvidia.com` — no friction, no source builds. Worth knowing if you ever need the GPU-accelerated dedup path.

The full install lives in the article's [`evidence/Dockerfile`](./evidence/Dockerfile) — a 4-line `RUN` layer over the existing NeMo container, ~2.6 GB extra on disk, ~3 minutes wall to build (including the lid.176.bin language-ID model pull).

**Curator drops 62.9% of "documents," which sounds like a lot.** The reason is mundane: HuggingFace's wikitext parquet uses one row per *line*, not one row per article. The corpus is 1.8 M lines; most of them are section headers (`= = = Section title = = =`) or stub lines too short to carry a 50-word minimum. The 62.9% drop is `WordCountFilter(min_words=50)` doing its job. By character count we keep 94.6% of the original. For a corpus where each row really is a document (CommonCrawl WET, scientific papers, your own markdown), the doc-drop ratio would be 1–10%, not 60%.

**The 30-step / 5-warmup methodology carries forward from A2.** Same trade-off: stable enough for sweep economics, not enough to surface convergence dynamics. Loss values land between 7.6 and 8.4 final for bf16 configs and 8.3 and 8.5 final for fp8 configs — slightly worse than A2's random-token loss because the model is now learning *real* token distributions which are harder than memorizing a fixed random seed. Loss is NOT the measurement here; it's a sanity check.

**The data sweep skipped seq=2048 × batch=16.** That config in A2 took 79 s wall time (the longest single config) and contributed nothing to the throughput story — bf16 plateaued past batch=8 at seq=2048. Cutting it from the A3 sweep saves 80 s and gives the same picture.

:::deeper
- [NeMo Curator on GitHub](https://github.com/NVIDIA/NeMo-Curator) — source for the Pipeline / Stage / Filter abstractions used in `prep_corpus.py`.
- [The Pile (Gao et al., 2020)](https://arxiv.org/abs/2101.00027) — the canonical "what does a serious pretrain corpus look like" reference, including dedup methodology.
- [`baseline-training-loop-on-spark`](/field-notes/baseline-training-loop-on-spark/) — A2's kernel envelope that this article reuses; the random-token peak this real-data run beat.
- [HuggingFace `datasets`](https://huggingface.co/docs/datasets) — alternative streaming loader for cases where the corpus is too big to memmap.
:::

## What this unlocks

**1. The Autoresearch agent can be designed without a data-prep escape hatch.** A4's overnight loop will be running 30–500 step training experiments at A2/A3's measured throughput. The data path doesn't need to be in the agent's "things to optimize" list — it's already at 0.04% overhead. The agent can spend its budget on architecture, optimizer, and data-mix experiments, not data plumbing.

**2. Domain-corpus pretrain on the Spark is realistic for one person.** Curator + tokenize + pack runs in 2 minutes per 0.5 GB corpus on the GB10. A 50 GB personal corpus (a decade of email, every PDF you've ever read, every commit you've authored) preps in roughly 200 minutes — overnight in CPU-bound mode while the GPU does other work. The training itself, at 14.9 K tok/s, processes ~1.3 B tokens/day. A 1B-token domain pretrain takes about 18 hours. This was a cloud-only conversation two years ago; the Spark moves it onto your desk.

**3. The Curator pipeline is a first-class citizen of the install playbook.** Once layered into the NeMo container with the four-line `RUN` (cudf-cu13, nemo-curator, fasttext, pulp<3), Curator becomes another tool that just works. The install friction was real but contained — and now it's documented. Future articles in the agentic / fine-tuning tracks (LoRA on personal Q&A pairs, NeMo Curator for inference-side text cleanup, code-corpus prep for an autoresearch agent) can reference this article instead of repeating the four pinning gotchas.

## State of the apps — as of A3

**Autoresearch now:** has a driver (NIM 8B from F1), an experiment substrate (NeMo Framework from A1), a measured kernel envelope (A2: 14.3 K tok/s peak on random tokens), and now a measured data envelope (A3: 14.98 K tok/s peak on real text, data overhead ≤ 0.04 %). The agent loop itself (A4) is still upcoming, and now has both numbers it needs to size its overnight budget. **Second Brain now:** unchanged since S4 (RAG-over-MCP shipped). **LLM Wiki now:** un-opened — W1 is the next decision point if the user wants to walk that arc instead. Next up in Autoresearch: **A4 — `autoresearch-agent-loop`** (the agent that finally runs unsupervised) or **A5 — `guardrails-for-code-generation`** if we want to land the safety rails before letting the agent edit `train.py`.

The full corpus, packed memmap, sweep harness, and per-stage stats are all preserved at `articles/nemo-curator-training-data-prep/evidence/`. The derived container (`nemo-curator-spark:1.1`, ~73 GB on disk) is built from a 4-line Dockerfile in the same directory — keep it, or rebuild from source in three minutes.

:::hardware[Same data path, frontier coefficients on bigger corpora]
At 0.5 GB the corpus fits in page cache and the data path is invisible. Scale to a CommonCrawl-class 50 TB shard and the math changes — not the per-batch transfer cost (still microseconds), but the *first-touch* page-fault rate. On Spark with 128 GB unified memory, you'd have to stream from NVMe; on an H100 80 GB node with 1.5 TB of host RAM, more of the corpus stays resident; on a DGX H200 with 2 TB host RAM and 8× 141 GB GPUs, single-shard prefetch + RDMA-style overlap puts you back in the "invisible" regime even at 50 TB. The 0.04% number Spark measured at 0.5 GB is the lower bound; the upper bound at frontier scale is bounded by host RAM, not by GPU bandwidth.
:::
