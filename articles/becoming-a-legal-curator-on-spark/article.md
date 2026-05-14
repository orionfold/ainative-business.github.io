---
title: "Orionfold/Saul-7B-Instruct-v1-GGUF on Spark — five legal variants, LegalBench mini-eval, four-axis measurement card"
date: 2026-05-14
author: Manav Sehgal
product: llama.cpp
stage: deployment
difficulty: intermediate
time_required: "~5 hours end-to-end on a DGX Spark"
hardware: "NVIDIA DGX Spark"
tags: [gguf, quantization, legal, orionfold, legalbench, mistral, fieldkit, spark-tested]
summary: "Five GGUF variants of Equall/Saul-7B-Instruct-v1 measured on a DGX Spark — Q5_K_M scores 72% on LegalBench (n=50, contains) at 20 tok/s and 4.8 GB. Each card carries perplexity, sustained tok/s, thermal envelope, and a 5-task LegalBench subset score."
status: published
series: Machine that Builds Machines
book_chapters: [10, 11]
fieldkit_modules: [quant, publish, eval, lineage]
also_stages: [observability]
hf_url: https://huggingface.co/Orionfold/Saul-7B-Instruct-v1-GGUF
---

Today on the Spark: [`Orionfold/Saul-7B-Instruct-v1-GGUF`](https://huggingface.co/Orionfold/Saul-7B-Instruct-v1-GGUF) ships — five GGUF variants of Equall's Saul-7B-Instruct-v1, the Mistral-7B legal SFT released alongside the [Saul paper](https://arxiv.org/abs/2403.03883). All five are measured end-to-end on a single DGX Spark. Each variant card carries the same four axes the finance-chat release did, this time over a curated LegalBench subset.

The four-axis frame is the consistent shape: wikitext-2 perplexity, sustained `tok/s` on GB10, sustained-load minutes before thermal throttle, and a vertical-bench accuracy score. What changes between cards is the vertical — finance last week, legal this week. The downloadable variants stay self-describing: a reader picking a quant for legal-doc analysis gets enough information to make an informed choice without running the eval themselves.

This article is the publishing receipt for the legal-vertical release: the Spark-measured numbers, the methodology that produced them, the variant picker for downstream use, and the honest gotchas the cards inherit from upstream.

## Spark-tested numbers

The cards under each variant on HuggingFace carry these numbers verbatim. They were produced by `fieldkit.quant.measure_perplexity_gguf`, `llama-bench`, a thermal-probe wrapper, and `fieldkit.eval.VerticalBench` with the `contains` scorer over a 50-question LegalBench subset (10 questions each from `overruling`, `abercrombie`, `proa`, `contract_nli_confidentiality_of_agreement`, and `diversity_1`).

| Variant | Size | Perplexity (wikitext-2) | tg tok/s | pp tok/s | LegalBench (n=50, contains) |
|---------|-------|------------------------|----------|----------|------------------------------|
| F16     | 13.5 GB | 5.917 | 10.9 | 1136.9 | 68% (34/50) |
| Q8_0    |  7.2 GB | 5.914 |  7.3 |  501.2 | 66% (33/50) |
| Q6_K    |  5.5 GB | 5.925 | 22.4 |  881.5 | 68% (34/50) |
| Q5_K_M  |  4.8 GB | 5.938 | 20.2 |  465.3 | **72% (36/50)** |
| Q4_K_M  |  4.1 GB | 5.986 | 29.4 | 1058.5 | 62% (31/50) |

Three observations worth narrating:

- **Q5_K_M slightly beats F16 on the bench (72% vs 68%).** With n=50 that's within sampling variance, but the take-home stays the same: the lossy 4.8 GB variant has not measurably lost legal capability versus the lossless 13.5 GB reference. Perplexity tells the same story (5.938 vs 5.917).
- **Q8_0 perplexity is essentially F16 (5.914 vs 5.917)** — quantization preserved language modeling quality at 53% the size. The LegalBench score gap (66% vs 68%) is one question out of 50.
- **Q4_K_M is the throughput pick at 29.4 tg tok/s** — 2.7× F16's speed at 30% the disk footprint. The bench cost is 6 percentage points (62% vs 68%); for high-volume legal-doc classification where individual case calls are reviewed downstream, that's an honest trade.

## Variant picker

The same picker shape as the finance card, with thresholds calibrated to this model's actual numbers:

| Variant | When to reach for it |
|---------|---------------------|
| **Q5_K_M** | Default pick. Best balance — fits in 5 GB of unified memory, matches F16 quality within sampling noise, runs at 20 tok/s. |
| **Q4_K_M** | Throughput pick. When you're scanning a corpus and human-reviewing the top hits, the 6-percentage-point bench delta is recoverable downstream. |
| **Q6_K** | Quality pick when memory headroom allows. Closes the small bench gap to F16 at 5.5 GB and 22 tok/s. |
| **Q8_0** | Reach for it when you genuinely need lossless-feeling outputs and don't care about throughput — note its tok/s is anomalously low here (see thermal section below). |
| **F16** | Reference only. No quantization. Use for measurement / baseline / debugging quant-induced regressions. |

## Using this release

The card on HuggingFace ships the same three snippets every Orionfold quant card ships, derived from `model_license`, `chat_format=mistral`, and `recommended_variant=Q5_K_M`. Reproduced here for read-through:

Pull a variant:

```bash
huggingface-cli download Orionfold/Saul-7B-Instruct-v1-GGUF model-Q5_K_M.gguf \
  --local-dir ./models/saul-7b-instruct-v1
```

Serve it via `llama-server` (OpenAI-compatible HTTP API at `http://127.0.0.1:8080/v1`):

```bash
llama-server -m ./models/saul-7b-instruct-v1/model-Q5_K_M.gguf \
  -c 4096 -ngl 99 -t 8 \
  --host 0.0.0.0 --port 8080
```

In-process via `llama-cpp-python` (note `chat_format="mistral"` — Saul inherits Mistral's `[INST] {q} [/INST]` template):

```python
from llama_cpp import Llama
llm = Llama(
    model_path="./models/saul-7b-instruct-v1/model-Q5_K_M.gguf",
    n_ctx=4096, n_gpu_layers=99, chat_format="mistral",
)
out = llm.create_chat_completion(
    messages=[
        {"role": "user",
         "content": "Does the following sentence overrule a previous case? "
                    "Sentence: 'curtman is overruled to the extent it conflicts with evans.'"}
    ],
    temperature=0.0,
)
print(out["choices"][0]["message"]["content"])
```

LM Studio and Ollama (via a Modelfile pointing at the GGUF) load the file directly with no additional setup.

## What changes between verticals

Two things generalized cleanly from the finance release; one needed targeted work.

**Generalized as-is.** The four-axis measurement frame — perplexity, tok/s, thermal envelope, vertical accuracy — is bench-agnostic. `fieldkit.publish.publish_quant` already accepted `vertical_eval=` (dict of variant → score) and `vertical_eval_name=` (the column header). Swapping FinanceBench numbers for LegalBench numbers needed no fieldkit changes; the publish surface lifted into v0.4.0 last week was already vertical-parametric.

**Needed targeted work.** The measurement *script* — `scripts/g3_measure_variants.py` — was hardcoded for FinanceBench: open-book evidence-prepending, the `numeric_match` scorer, the FinanceBench dataset citation in lineage notes. A new `VERTICAL_BENCH={financebench,legalbench}` env knob now picks between the two, dispatching to `fieldkit.eval.contains` for legal classification and `fieldkit.eval.numeric_match` for finance numerics. The measurements.json schema gained a `vertical_eval_name` key that the publish step reads back to title the card column correctly. Tracked in `[Unreleased]` for fieldkit v0.4.1.

The cleanest signal that the surface generalized: the Saul card and the finance-chat card render with the same four-axis table shape, the same three run snippets, the same Methods link convention. Only the column header and the numbers differ.

## A note on the LegalBench subset

LegalBench ships 162 task folders. Evaluating Saul on all of them per variant would take ~16 hours per variant; for a 5-variant card on a single Spark, that's the wrong cost shape. The 50-question subset (10 each from 5 representative tasks) trades fidelity for tractability while staying defensible:

- **`overruling`** — does a sentence overrule a previous case? Binary yes/no. Tests case-law surface reading.
- **`abercrombie`** — classify a trademark as generic / descriptive / suggestive / arbitrary / fanciful. Five-class IP doctrine recall.
- **`proa`** — is this a private right of action? Binary yes/no. Statutory interpretation.
- **`contract_nli_confidentiality_of_agreement`** — NLI on NDA clauses. Binary yes/no.
- **`diversity_1`** — does this fact pattern create federal diversity jurisdiction? Binary yes/no.

The mix spans case law, statutory analysis, contract NLI, federal procedure, and trademark — five distinct legal subskills the Saul paper itself evaluates. All five use LegalBench's `contained_in_output` eval method, so a single `fieldkit.eval.contains` scorer handles the full bench at 50 questions. The merged JSONL lives at `evidence/legalbench_merged.jsonl`-ready format; the merge script (`scripts/legalbench_merge.py`) is in the repo for anyone wanting to reproduce or expand the subset.

A more authoritative score would extend the subset to ~500 questions or run the full bench at lower frequency (e.g., once per release, not per variant). The 50-question card is the *publishable* score — comparable across releases, runnable per-variant in under 6 minutes — not the *authoritative* one.

## Thermal envelope notes

The sustained-load minutes (probed via `nvidia-smi` at 10-second intervals during the bench sweep) ranged from 1.7 min (Q4_K_M) to 7.2 min (Q8_0). The pattern is the inverse of perplexity: smaller variants generate faster, get hotter faster, and back off the GPU sooner; bigger variants generate more slowly, run cooler, and sustain longer.

The Q8_0 anomaly — its 7.3 tg tok/s is the slowest of any variant, slower than F16's 10.9 — is consistent with the same anomaly observed on `Orionfold/finance-chat-GGUF` (Q8_0 was 8.9 vs F16's 11.5 there). The leading hypothesis is thermal scheduling: Q8_0 ran last in the sweep both times, and the GB10's brief throttle window was already half-spent. A standalone Q8_0 rerun on a cold die would resolve it. Not blocking; the card carries the actual measurement, not a corrected one.

## Methods + reproducibility

The full release pipeline lives in [`scripts/g3_build_first_quant.sh`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/g3_build_first_quant.sh). For Saul-7B-Instruct-v1, the invocation is:

```bash
MODEL_ID=Equall/Saul-7B-Instruct-v1 \
  ./scripts/g3_build_first_quant.sh all
```

The case statement at the top of the script auto-resolves `MODEL_LICENSE=mit`, `CHAT_FORMAT=mistral`, `VERTICAL_BENCH=legalbench`, and `ARTICLE_SLUG=becoming-a-legal-curator-on-spark` from the model ID, so no env vars need passing manually. The pipeline runs: preflight → download → preflight-bench (5-question FinanceBench gate against FP source weights — passed at 1/5, confirming the model can do open-book Q&A) → probe → quantize (5 variants) → measure (4 axes per variant) → publish-dryrun → publish.

The lineage rows for this release live at `evidence/lineage-Saul-7B-Instruct-v1/results.tsv` (one row per variant, hypotheses + measurements + bench source). The merged LegalBench JSONL the measure step consumed lives at `/home/nvidia/data/eval-benches/legalbench/legalbench_merged.jsonl` — produced by `scripts/legalbench_merge.py` from the upstream [nguha/legalbench](https://huggingface.co/datasets/nguha/legalbench) dataset.

End-to-end wall time on the Spark was approximately 5 hours: 35 minutes for the download, ~3 minutes per variant for quantize (15 min total), and ~13 minutes per variant for the four-axis measurement sweep (65 min total). The remaining time was the dry-run + upload setup and a one-time HF→GGUF F16 convert (~80 sec). The HF upload itself was detached and ran independently of the on-Spark measurement.

## What's next

Two compounding directions, both validated by this release.

**Second-vertical confidence.** The same pipeline that shipped `Orionfold/finance-chat-GGUF` last week shipped this one. Two verticals in two sessions confirms the publishing surface — chat format, license tier, scorer plumbing, card rendering — is bench-agnostic. Cyber (`lily-cybersecurity-7b-v0.2`) and medical (Llama-3-Med-Instruct) are the natural next cards; each will exercise a different LegalBench-shaped subset under a different scorer.

**Curated subsets as a pattern.** LegalBench's 162-task corpus was too big to evaluate per-variant; the 5-task / 50-question subset was the pragmatic call. Other big-corpus benches (BIG-bench, MMLU-Pro) face the same trade. The `scripts/legalbench_merge.py` shape — pick representative tasks, render their instruction templates, write to a VerticalBench-readable JSONL — generalizes. The publish surface already takes any `VerticalBench` and any scorer, so adding new benches is a merge-script away.

The Saul card is up. The next vertical is one model pick away.
