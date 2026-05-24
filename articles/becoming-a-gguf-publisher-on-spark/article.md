---
title: "Orionfold/finance-chat-GGUF on Spark — five variants, FinanceBench mini-eval, four-axis measurement card"
date: 2026-05-14
author: Manav Sehgal
product: llama.cpp
stage: deployment
difficulty: intermediate
time_required: "~6 hours end-to-end on a DGX Spark"
hardware: "NVIDIA DGX Spark"
tags: [gguf, quantization, finance, orionfold, financebench, llama-2-chat, fieldkit, spark-tested]
summary: "Five GGUF variants of AdaptLLM/finance-chat measured on a DGX Spark — Q8_0 perplexity-matches F16 losslessly, Q4_K_M ships at 31 tok/s. Each card carries perplexity, sustained tok/s, thermal envelope, and FinanceBench accuracy."
signature: VerticalCuratorRetry
status: published
series: Machine that Builds Machines
book_chapters: [10, 11]
fieldkit_modules: [quant, publish, eval, lineage]
also_stages: [observability]
hf_url: https://huggingface.co/Orionfold/finance-chat-GGUF
---

Today on the Spark: [`Orionfold/finance-chat-GGUF`](https://huggingface.co/Orionfold/finance-chat-GGUF) ships — five GGUF variants of AdaptLLM's Llama-2-Chat-7B finance fine-tune, all measured end-to-end on a single DGX Spark. The card under each variant carries four axes that downloadable GGUFs rarely come with: wikitext-2 perplexity, sustained `tok/s` on GB10, sustained-load minutes before thermal throttle, and an open-book FinanceBench score across 50 quantitative questions.

The four-axis frame matters because the consumer-LLM stack ordinarily under-measures itself. Perplexity alone hides task degradation. Token-rate alone hides duty cycle. A vendor "lossless" claim alone hides the per-variant comparison that would prove it. A reader downloading a quant to run on their own consumer GPU needs all four — and an interpretation of which variant to pick for which workload.

This article is the publishing receipt for the five-variant release: the Spark-measured numbers, the methodology that produced them, the variant picker for downstream use, and the honest gotchas the cards inherit from upstream.

## Why this matters for a personal AI power user on one machine

A 7B chat model that knows finance, runs offline on a 4 GB-VRAM laptop, and answers a balance-sheet question in under three seconds is the shape of "local LLM" that consumer hardware now supports — but only if the publisher who packaged it for you tested it on hardware that fairly resembles yours. The DGX Spark sits exactly on that boundary: 128 GB of unified memory, GB10 silicon, a hardware envelope a serious hobbyist can reproduce.

That makes the measurement legible. A FinanceBench score I publish on a Spark is the same score you would see on an Apple-Silicon Mac or a 5090 — within ~10% — because the bench is deterministic at temperature zero and the perplexity arithmetic doesn't move. The thermal envelope ports less perfectly (silicon-specific), but it tells you the *shape* of what to expect: "your GPU can hold this load for two minutes at this rate, then it throttles." That's the missing dimension when you pull a GGUF off the hub and wire it into an agent loop that's supposed to run unattended.

:::why[Four-axis cards beat one-axis ones]
Perplexity alone hides task degradation — a quant can match the F16 reference on wiki text and still lose 4% accuracy on a financial-math task. Token-rate alone hides duty cycle — a number measured on a cold board over 30 seconds isn't what you get over 30 minutes. A FinanceBench accuracy alone hides whether the quantization itself caused the drop. All four together let a reader pick the variant that matches their *workload shape*, not just their *RAM budget*.
:::

## Architectural context — release pipeline

The pipeline is six stages, sequenced so each one validates the next:

<figure class="fn-diagram" aria-label="Release pipeline for an Orionfold GGUF: source weights are downloaded from Hugging Face, converted to F16 GGUF, gated through a five-question preflight bench that scores against open-book FinanceBench on the FP source, then quantized to four additional variants, measured across four axes per variant, staged with a generated model card, and pushed to Hugging Face under the Orionfold handle.">
  <svg viewBox="0 0 900 280" role="img" preserveAspectRatio="xMidYMid meet"
       aria-label="Release pipeline for an Orionfold GGUF: source weights are downloaded from Hugging Face, converted to F16 GGUF, gated through a five-question preflight bench that scores against open-book FinanceBench on the FP source, then quantized to four additional variants, measured across four axes per variant, staged with a generated model card, and pushed to Hugging Face under the Orionfold handle.">
    <defs>
      <linearGradient id="rp-lane" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-green)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-green)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="rp-accent" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="20" y="40" width="860" height="200" rx="12" fill="url(#rp-lane)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 160 140 L 235 140"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 345 140 L 420 140"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 530 140 L 605 140"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 715 140 L 790 140"/>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="40" y="100" width="120" height="80" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="235" y="100" width="110" height="80" rx="8" style="fill: url(#rp-accent)"/>
      <rect class="fn-diagram__node" x="420" y="100" width="110" height="80" rx="8"/>
      <rect class="fn-diagram__node" x="605" y="100" width="110" height="80" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="790" y="100" width="80" height="80" rx="8"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="100" y="135" text-anchor="middle">source</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="100" y="155" text-anchor="middle">HF safetensors</text>
      <text class="fn-diagram__label" x="290" y="135" text-anchor="middle">preflight</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="290" y="155" text-anchor="middle">5Q · ≥1/5</text>
      <text class="fn-diagram__label" x="475" y="135" text-anchor="middle">quantize</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="475" y="155" text-anchor="middle">5 variants</text>
      <text class="fn-diagram__label" x="660" y="135" text-anchor="middle">measure</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="660" y="155" text-anchor="middle">4 axes × 5</text>
      <text class="fn-diagram__label" x="830" y="135" text-anchor="middle">publish</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="830" y="155" text-anchor="middle">card + push</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="290" y="220" text-anchor="middle">fail-fast gate · ~30 sec on GPU</text>
    </g>
  </svg>
  <figcaption>Every Orionfold release runs the same five-stage pipeline. The preflight bench is the gate: five open-book FinanceBench questions on the F16 GGUF, ≥1/5 to proceed, before the multi-hour quantize + measure sweep commits.</figcaption>
</figure>

The preflight is where a release earns the right to consume Spark cycles. It runs on the *same* F16 GGUF that B4 will measure as variant five, so the gate's compute cost overlaps the production sweep — it's earlier work, not extra work. After the gate passes, the four additional variants (Q4_K_M / Q5_K_M / Q6_K / Q8_0) are produced and each variant runs through the four-axis measurement before any card is rendered.

## How we validate a release before it ships

The preflight gate's design has four properties, and skipping any one is a way to ship a release that the cards say is fine and the user discovers is broken:

1. **Same prompt shape as production.** If the production measure wraps each FinanceBench question with `<s>[INST] … [/INST]` and includes the row's `evidence_text` field as open-book context, the preflight has to do the same. A preflight that uses a different prompt is predicting different output than what production will see.
2. **Same inference backend as production.** Orionfold measures via `llama-server` on the GPU. The preflight uses `llama-server` on the GPU. No CPU shims, no `transformers` substitutes — same path, same numerics.
3. **Abort on zero.** A 7B model that can't answer one out of five quantitative questions correctly against the cited 10-K excerpt isn't going to recover after quantization. The threshold is `≥ 1/5` — non-zero is sufficient signal; the quantize + measure step will surface the actual variant-level accuracy.
4. **Cheap enough to be worth running.** Under ten minutes per release attempt. The F16 GGUF conversion is the one-time cost (~5 minutes); the actual five-question pass on GPU is ~30 seconds.

Here is what the gate emits for AdaptLLM/finance-chat:

```
[preflight] converting finance-chat → F16 GGUF (this can take ~5 min)
[preflight] convert OK in 61.8s → /home/nvidia/data/quants/finance-chat/model-F16.gguf
[preflight] prompt format: llama2_inst
[preflight] scoring 5 open-book questions from FinanceBench subset=metrics-generated
[preflight]   Q1/5 [2.1s] qid=financebench_id_03029 expected='$1577.00' predicted='$1,577' score=1
[preflight]   Q2/5 [2.1s] qid=financebench_id_04672 expected='$8.70'    predicted='$8.738' score=1
[preflight]   Q3/5 [2.3s] qid=financebench_id_02987 expected='24.26'    predicted='1.95' score=0
[preflight]   Q4/5 [2.6s] qid=financebench_id_07966 expected='1.9%'     predicted='1.5' score=0
[preflight]   Q5/5 [4.0s] qid=financebench_id_04735 expected='0.66'     predicted='1.27' score=0
[preflight] score: 2/5 (threshold ≥ 1)
[preflight] PASS — proceed with quantize+measure
```

Q1 matched exactly: `$1,577` versus expected `$1577.00`. Q2 hit the 1% tolerance: `$8.738` is within 0.4% of `$8.70`. Q3–Q5 are math errors — typical for a 7B reasoning chain on a quantitative question. Threshold of 1/5 satisfied. Gate passes.

:::pitfall[FinanceBench is open-book — `evidence[*].evidence_text` is part of the prompt]
The 150-row open subset of `PatronusAI/financebench` ships each question alongside an `evidence` field containing the relevant 10-K excerpt. The official eval prepends that excerpt to the question; without it the model is recall-testing against training-corpus memorization. A closed-book FinanceBench run on a 7B model essentially asks the model to memorize the public financial filings of every S&P 500 company — a hard ask even for a frontier model. Anyone evaluating their own quants should mirror this shape.
:::

## The base model — `AdaptLLM/finance-chat`

`AdaptLLM/finance-chat` is the [ICLR 2024 paper-backed](https://huggingface.co/papers/2309.09530) domain-specific chat model from Microsoft Research, developed via continued pre-training on top of `meta-llama/Llama-2-7b-chat-hf`. The chat lineage matters: it ships the Llama-2 instruction format (the `<s>[INST] … [/INST]` shape) and inherits Llama-2-Chat's RLHF — domain adaptation rides on top of that, not in place of it.

One thing the model card doesn't surface, and that matters for anyone running this GGUF outside Orionfold's pipeline: the tokenizer config does NOT include a modern `chat_template` field. That convention postdates Llama-2's release. If you're using `tokenizer.apply_chat_template(...)` to format prompts, you'll need to wrap manually:

```python
prompt = f"<s>[INST] {question.strip()} [/INST]"
```

`llama-server` does the right thing automatically when the `chat-template` model metadata is set during conversion. Most consumer surfaces (LM Studio, Ollama via Modelfile, llama-cpp-python via `chat_format="llama-2"`) also handle this — just point them at the variant and don't second-guess the wrapper.

## The Spark-tested numbers

Five variants. Four axes per variant. One Spark.

| Variant | Size | Perplexity (wikitext-2) | tg tok/s | pp tok/s | FinanceBench (n=50, numeric_match) |
|---------|---------|------------------------|----------|----------|------------------------------------|
| F16     | 12.6 GB | 6.137 | 11.5 | 1126.8 | **18%** (9/50) |
| Q8_0    | 6.7 GB  | 6.137 | 8.9  | 504.4  | **18%** (9/50) |
| Q6_K    | 5.1 GB  | 6.147 | 23.9 | 930.7  | 16% (8/50) |
| Q5_K_M  | 4.5 GB  | 6.164 | 26.9 | 1088.6 | 16% (8/50) |
| Q4_K_M  | 3.8 GB  | 6.222 | 31.1 | 1111.1 | 14% (7/50) |

Two results worth flagging. The first is the *good* one: **Q8_0 perplexity matches F16 to four decimal places** — 6.1373 vs 6.1373. Quantization to 8.5 bits per weight is effectively lossless against the F16 reference at 53% the size. FinanceBench accuracy ties exactly: 9/50 on both. This is the variant a reader downloads when they want "give me the smallest variant that doesn't move the meter."

:::why[Lossless quants are an honest claim only after you measure both axes]
Vendors call Q8_0 "lossless" by convention — the K-Quant family's quantization error is below the noise floor of most downstream tasks. But the only way to *show* losslessness for a specific model and a specific task is to publish the perplexity-match plus a domain-relevant eval that ties. Both moved in the same place. The card carries the receipt.
:::

The second result is the *surprise*: **Q8_0's tg tok/s is 8.9 — lower than F16's 11.5.** Q4_K_M is 31.1 tok/s, almost three times faster than F16. Q5_K_M and Q6_K sit on the expected curve. Q8_0 is the outlier — it's slower than the variant it descends from. We have a hypothesis (thermal scheduling and/or Q8_0's heavier per-tensor arithmetic on GB10's GPU), the run-order setup that would test it, and a re-measurement scheduled. The card ships with the number measured and the anomaly flagged — see *Honest gotchas* below.

:::hardware[Spark's 273 GB/s on weights is what makes Q4_K_M's 31 tok/s possible]
Generation throughput on a 7B model is memory-bandwidth-bound: each new token streams every weight through the FMA units once. F16 = 14 GB / token-equivalent → 11.5 tok/s implies ~160 GB/s effective bandwidth, well under GB10's 273 GB/s ceiling. Q4_K_M = 4 GB → 31 tok/s implies ~125 GB/s — the kernel is *slower* per byte but processing 3.5× fewer bytes. A frontier H100's 3 TB/s would push F16 to ~210 tok/s if the kernel keeps up; the gap-closing observation is that consumer-bandwidth hardware can match enterprise tok/s for users who tolerate Q4 quality.
:::

The card also carries a single envelope number: **sustained load = 2 minutes**. That's the floor — what Q4_K_M sustained on the measurement runs before its `tok/s` started degrading. F16 and Q8_0 sustained 3+ minutes. The card publishes the floor because the reader downloading Q4_K_M for an agent loop needs to know "you have two minutes of high-RPM throughput before this card starts breathing."

## Using this release

### Picking a variant

| You want to… | Variant | Why |
|---|---|---|
| Fit on a 4 GB consumer GPU | **Q4_K_M** | 3.8 GB on disk, 31 tg tok/s. ~14% accuracy floor on FinanceBench — fine for chat, less fine for high-stakes quantitative tasks. |
| Balance speed and quality | **Q5_K_M** | 4.5 GB, 27 tok/s, 16% FinanceBench. The default-pick variant. |
| Approach lossless without paying full F16 | **Q6_K** | 5.1 GB, 24 tok/s, 16% FinanceBench, perplexity within 0.01 of F16. |
| Effectively lossless | **Q8_0** | 6.7 GB, perplexity exactly matches F16, FinanceBench accuracy ties. tg tok/s is anomalously low (see *Honest gotchas*) — verify on your hardware before committing to it for throughput-sensitive workloads. |
| Reference / measurement baseline | **F16** | 12.6 GB, 11.5 tok/s. Use this when you're measuring against the source. |

### Running it

Pull a variant:

```bash
# pick one of: model-Q4_K_M.gguf model-Q5_K_M.gguf model-Q6_K.gguf model-Q8_0.gguf model-F16.gguf
huggingface-cli download Orionfold/finance-chat-GGUF model-Q5_K_M.gguf --local-dir ./models/finance-chat
```

Serve it via `llama-server` (recommended — speaks OpenAI-compatible API):

```bash
llama-server -m ./models/finance-chat/model-Q5_K_M.gguf \
  -c 4096 -ngl 99 -t 8 \
  --host 0.0.0.0 --port 8080
```

Then prompt it from anywhere that speaks OpenAI:

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/v1", api_key="sk-no-key-required")
resp = client.chat.completions.create(
    model="finance-chat",
    messages=[{"role": "user", "content": "What is 3M's FY2018 capital expenditure?"}],
    temperature=0.0,
)
print(resp.choices[0].message.content)
```

Or run in-process via `llama-cpp-python`:

```python
from llama_cpp import Llama
llm = Llama(
    model_path="./models/finance-chat/model-Q5_K_M.gguf",
    n_ctx=4096, n_gpu_layers=99, chat_format="llama-2",
)
out = llm.create_chat_completion(
    messages=[{"role": "user", "content": "Explain working capital."}],
    temperature=0.0,
)
print(out["choices"][0]["message"]["content"])
```

LM Studio and Ollama (via a Modelfile) load the GGUF directly with no additional setup.

### What you gain vs. running `AdaptLLM/finance-chat` directly

The upstream weights at [`AdaptLLM/finance-chat`](https://huggingface.co/AdaptLLM/finance-chat) are 13.5 GB of safetensors that you load with `transformers` and run on a GPU large enough to hold them. That works on a workstation with a 24 GB-VRAM card; it doesn't work on a 4 GB or 8 GB consumer GPU. The Orionfold release closes that gap on four axes:

| Axis | `AdaptLLM/finance-chat` (origin) | `Orionfold/finance-chat-GGUF` (this release) |
|------|----------------------------------|----------------------------------------------|
| Smallest file | 13.5 GB FP16 safetensors | **3.8 GB Q4_K_M GGUF** (72% smaller) |
| Fastest tg tok/s on Spark | 11.5 (FP16) | **31.1** (Q4_K_M, 2.7× faster) |
| Quality preservation receipt | none published | Q8_0 perplexity matches F16 to four decimals |
| Spark-measured methodology | none | open-book FinanceBench + thermal envelope per variant |
| Consumer-surface ready | requires user-side HF→GGUF convert (~5 min on Spark) | direct llama.cpp / Ollama / LM Studio load |

To be clear about credit: **AdaptLLM did the training work** — the continued-pretrain methodology that turned Llama-2-Chat-7B into a finance-specialized chat model, and the [ICLR 2024 paper](https://huggingface.co/papers/2309.09530) that backs it. Orionfold's contribution is the *distribution + measurement* layer: five quantized variants, four-axis cards, the open-book FinanceBench rubric, and a thermal envelope that previously didn't exist for this model on any hardware.

If you're going to fine-tune further or want the FP16 reference for your own quantization experiments, go to AdaptLLM. If you want to run a finance-specialized 7B chat model on consumer hardware tomorrow morning, this is the release.

## Honest gotchas

### The Q8_0 tok/s anomaly

Q8_0's `tg` rate of 8.9 tok/s is 23% below F16's 11.5. The `pp` (prompt-processing) rate is worse — Q8_0 ships at 504 tok/s versus F16's 1127. Two candidate explanations are worth naming:

1. **Run order + thermal scheduling.** Q8_0 ran last in the sweep, after ~45 minutes of sustained GPU load. The thermal envelope (per-variant 2-3 minute sustained-load floor) suggests the GPU was already running hot when the Q8_0 measurement window opened. A clean disambiguation is a cold-board Q8_0 rerun, which is on the schedule.
2. **Q8_0 kernel cost on GB10.** Q8_0 uses heavier per-tensor arithmetic than the K-quants (Q4_K_M, Q5_K_M, Q6_K), and the GB10 kernel paths for Q8_0 may not be as optimized as the K-quant ones. This would show up as a structural slowdown, not a thermal one.

The next version of this card will flag which hypothesis holds. In the meantime, if you're picking between Q6_K and Q8_0 for a throughput-sensitive workload, **measure on your own hardware before committing to Q8_0** — perplexity favors Q8_0, but Q6_K is the safer bet for sustained throughput.

### Inheritance from upstream

This is a 7B model and a Llama-2 base — both are explicit constraints. FinanceBench accuracy in the 14-18% range across variants is consistent with a 7B reasoning capacity, not a quantization failure. For higher accuracy on quantitative tasks, a larger base model is the path forward; quantization can't recover capabilities the base never had.

The Llama-2 community license also passes through — see the upstream `AdaptLLM/finance-chat` page for the relevant terms.

### Audit trail

Every variant of every release writes one row to a `fieldkit.lineage.LineageStore` TSV at `articles/becoming-a-gguf-publisher-on-spark/evidence/lineage-finance-chat/results.tsv` — baseline row 000 (the source model, bench metadata, calibration corpus) plus five variants 001-005 carrying real numbers. The `notes` column carries the per-variant flavor that doesn't fit the fixed columns:

```text
tg_tok_per_s=11.5 ; pp_tok_per_s=1126.8 ; sustained_load_min=3.4 ;
gguf_size_bytes=13478122560 ; bench=PatronusAI/financebench ;
corpus=wikitext-2-raw-v1/wiki.test.raw
```

Anyone who wants to extend the methodology — measure a sixth axis, add a different scorer, score against a different bench subset — has a pattern to copy.

:::define[Lineage TSV]
A `fieldkit.lineage.LineageStore` writes append-only TSV rows tracking experiment trials by `exp_id`, with provenance (`parent_exp`, `baseline_exp`), core metric, status, snapshot path, and free-form notes. Originally built for `fieldkit.training` ablations; now reused for quant cards so the publishing artifact carries the same audit shape as a training run.
:::

## What this unlocks

Three concrete things a reader can build with this release as of Monday morning:

1. **A finance-aware local chatbot fronting your own 10-K notes corpus.** Pull `Q5_K_M`, point it at a llama.cpp server, wire it to your notes via your favorite local RAG stack. The chat-tuned base handles balance-sheet vocabulary and the four-axis card tells you when to expect throttling.
2. **An agent that drafts FP&A commentary against structured tables.** Use Q4_K_M for throughput, feed it structured numbers (revenue / opex / capex tables), have it draft variance-analysis prose. The thermal envelope tells you how to pace the loop — short bursts, two-minute duty cycles.
3. **An evaluator scoring a third-party finance LLM against the same FinanceBench rubric.** The open-book methodology + the lineage TSV give you an apples-to-apples comparison surface. If someone else publishes a different finance-domain quant, you can score it against the same 50-question subset and read the four-axis delta directly.

The four-axis card is also a methodology you can apply to any GGUF you publish yourself. The Spark sits on a hardware envelope a serious hobbyist can reproduce, the bench is public, and the measurement scripts in `fieldkit.quant` plus the open-book loader pattern are the only moving parts.

## Closing

The publishing receipt is the card. The card has five rows and four columns, and behind each cell is roughly six hours of compute and a measurement methodology that didn't exist for this model on any hardware before today. If you have an 8 GB-VRAM laptop and a finance task that doesn't quite justify a cloud-API subscription, `Q5_K_M` is yours to download in about eight minutes — three for the file and five for the first prompt. The Spark on my desk did the work so you wouldn't have to.

Receipts for this release live at `articles/becoming-a-gguf-publisher-on-spark/evidence/lineage-finance-chat/results.tsv`. The next Orionfold release continues the same pipeline on a new vertical — watch [orionfold.com](https://orionfold.com) for the announcement.

:::deeper
- [`Orionfold/finance-chat-GGUF`](https://huggingface.co/Orionfold/finance-chat-GGUF) — the release itself (variant files + auto-generated four-axis card).
- [`AdaptLLM/finance-chat`](https://huggingface.co/AdaptLLM/finance-chat) — the upstream FP16 source weights.
- [Adapting Large Language Models via Reading Comprehension](https://huggingface.co/papers/2309.09530) — the AdaptLLM (ICLR 2024) paper. Read §3 for the continued-pretrain methodology and its chat-degradation framing.
- [`PatronusAI/financebench`](https://huggingface.co/datasets/PatronusAI/financebench) — the FinanceBench paper and public 150-question open subset (CC-BY-NC-4.0, arXiv:2311.11944).
- [`fieldkit.quant`](/fieldkit/api/quant/) — the `quantize_gguf`, `measure_perplexity_gguf`, `measure_tokens_per_sec_gguf`, and `ThermalProbe` surfaces that produce the four-axis numbers.
- [`llama.cpp` GGUF format spec](https://github.com/ggml-org/llama.cpp/blob/master/docs/gguf.md) — the K-quant family and the Q8_0 reference.
:::

---

**Catalog page:** [`/artifacts/notebooks/finance-chat-notebooks/`](/artifacts/notebooks/finance-chat-notebooks/) — the dual-path Open in Colab / Open in Kaggle on-ramp, builder + user variants, target-model lineage, and bounded drift between Spark and cloud quants — the full notebook card.
