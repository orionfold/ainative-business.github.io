---
title: "Orionfold/SecurityLLM-GGUF on Spark — five cyber variants, CyberMetric mini-eval, MCQ letter scoring"
date: 2026-05-15
author: Manav Sehgal
product: llama.cpp
stage: deployment
difficulty: intermediate
time_required: "~5 hours end-to-end on a DGX Spark"
hardware: "NVIDIA DGX Spark"
tags: [gguf, quantization, cyber, security, orionfold, cybermetric, mistral, zephyr, fieldkit, spark-tested]
summary: "Five GGUF variants of ZySec-AI/SecurityLLM measured on a DGX Spark — Q4_K_M scores 40% on CyberMetric MCQ at 47.7 tok/s and 4.1 GB; the smaller variants matched or beat F16's 34%. Third vertical card; zero fieldkit source changes."
status: published
series: Machine that Builds Machines
signature: CyberCurator
book_chapters: [10, 11]
fieldkit_modules: [quant, publish, eval, lineage]
also_stages: [observability]
hf_url: https://huggingface.co/Orionfold/SecurityLLM-GGUF
---

Today on the Spark: [`Orionfold/SecurityLLM-GGUF`](https://huggingface.co/Orionfold/SecurityLLM-GGUF) ships — five GGUF variants of ZySec-AI's SecurityLLM, the Mistral-7B + Zephyr DPO cybersecurity fine-tune. Same four-axis measurement card as the finance and legal releases before it; same publishing surface; same lineage trail. What changes is the vertical: cyber MCQ this week, after legal binary classification last week and finance numeric reasoning the week before.

The narrative thread of this release isn't that cyber works on Spark — three weeks of evidence say verticals work on Spark. The thread is that **this third vertical cost zero changes to `fieldkit`**. `fieldkit v0.4.1` generalized the publishing surface in two patches; the cyber card needed only a 50-line `scripts/cyber_merge.py`, a local MCQ-letter scorer in the measurement script, and a five-line zephyr-template wrapper alongside the existing Mistral-Instruct one. The PyPI package itself shipped no new code for this release. That's the load-bearing claim: the vertical-curator workflow is now a configuration shape, not a code shape.

This article is the publishing receipt for the cyber-vertical release: the Spark-measured numbers, the new MCQ scorer, the variant picker for downstream use, and the honest gotchas the card inherits from upstream.

## Spark-tested numbers

The cards under each variant on HuggingFace carry these numbers verbatim. They were produced by `fieldkit.quant.measure_perplexity_gguf`, `llama-bench`, a thermal-probe wrapper, and `fieldkit.eval.VerticalBench` with a new `mcq_letter` scorer over a 50-question CyberMetric subset (sampled deterministically from [`tihanyin/CyberMetric`'s 80-question release](https://huggingface.co/datasets/tihanyin/CyberMetric), arxiv [2402.07688](https://arxiv.org/abs/2402.07688)).

| Variant | Size | Perplexity (wikitext-2) | tg tok/s | pp tok/s | CyberMetric (n=50, mcq_letter) |
|---------|-------|------------------------|----------|----------|--------------------------------|
| F16     | 13.5 GB | 7.301 | 17.5 | 2416.9 | 34% (17/50) |
| Q8_0    |  7.2 GB | 7.307 | 30.3 | 2611.6 | 36% (18/50) |
| Q6_K    |  5.5 GB | 7.313 | 35.0 | 2376.1 | 36% (18/50) |
| Q5_K_M  |  4.8 GB | 7.314 | 39.9 | 2749.1 | 38% (19/50) |
| Q4_K_M  |  4.1 GB | 7.400 | 47.7 | 2836.5 | **40% (20/50)** |

Three observations worth narrating:

- **The smaller variants matched or beat F16 on the bench.** Q4_K_M scored 40% (20/50), Q5_K_M 38%, Q6_K and Q8_0 both 36%, F16 only 34%. At n=50, one question is two percentage points — the 3-question gap between Q4_K_M and F16 is well inside sampling noise. The honest read: lossy quantization did not measurably hurt cyber knowledge, and we got the throughput improvement essentially free. Perplexity (7.30 → 7.40) confirms it from the other side.
- **The Q8_0 anomaly didn't repeat this time.** Finance and legal both saw Q8_0 slower than F16 (a suspected thermal-scheduling artefact from running it last in the sweep). On cyber, Q8_0 ran at 30.3 tok/s vs F16's 17.5 — 1.7× faster. Same sweep order, different result. Either the prior pattern was model-specific, or the thermal envelope this time absorbed the load differently. Worth tracking on the fourth vertical to confirm.
- **Cyber MCQ is harder than the model knows it.** A four-option MCQ chance score is 25%; F16 at 34% means the model is doing real cyber reasoning, but its lead over chance is modest. The Saul card hit 68% on LegalBench (with a binary classification baseline of 50%), and AdaptLLM/finance-chat hit 14–18% on FinanceBench (numeric extraction, no chance baseline). Different bench types, different lifts; ZySec's 14-point lead over chance on a domain-specific MCQ corpus is in the same neighborhood as Saul's 18-point lead over binary chance.

## Variant picker

The same picker shape as the finance and legal cards, with thresholds calibrated to this model's actual numbers:

| Variant | When to reach for it |
|---------|---------------------|
| **Q4_K_M** | Default pick — best balance. 4.1 GB, 47.7 tok/s, 40% on CyberMetric (highest of all five). Unusual that the smallest quant tops the table; the n=50 sample makes the ordering statistically loose, but it tells you Q4_K_M did not lose cyber capability versus F16. |
| **Q5_K_M** | Quality pick a hair above default. 4.8 GB, 39.9 tok/s, 38%. If you have memory headroom and want F16-or-above behavior without the disk and load-time cost of F16. |
| **Q6_K** | Middle-of-the-table. 5.5 GB, 35.0 tok/s, 36%. Reach for it when you want a buffer above Q5_K_M without going to Q8_0. |
| **Q8_0** | Lossless-feeling pick. 7.2 GB, 30.3 tok/s, 36%. Reproduces F16 perplexity (7.307 vs 7.301) at half the size; the bench tie is consistent with that. |
| **F16** | Reference only. 13.5 GB, 17.5 tok/s, 34%. No quantization — use for baseline / debugging quant-induced regressions, not for production. |

## Using this release

The card on HuggingFace ships the same three snippets every Orionfold quant card ships, derived from `model_license=apache-2.0`, `chat_format=zephyr`, and `recommended_variant=Q5_K_M`. Reproduced here for read-through:

Pull a variant (Q4_K_M is the default pick on this card):

```bash
huggingface-cli download Orionfold/SecurityLLM-GGUF model-Q4_K_M.gguf \
  --local-dir ./models/securityllm
```

Serve it via `llama-server` (OpenAI-compatible HTTP API at `http://127.0.0.1:8080/v1`):

```bash
llama-server -m ./models/securityllm/model-Q4_K_M.gguf \
  -c 4096 -ngl 99 -t 8 \
  --host 0.0.0.0 --port 8080
```

In-process via `llama-cpp-python` (note `chat_format="zephyr"` — SecurityLLM uses Zephyr's `<|user|> / <|assistant|>` template, not Mistral's `[INST]`):

```python
from llama_cpp import Llama
llm = Llama(
    model_path="./models/securityllm/model-Q4_K_M.gguf",
    n_ctx=4096, n_gpu_layers=99, chat_format="zephyr",
)
out = llm.create_chat_completion(
    messages=[
        {"role": "user",
         "content": "What is the primary purpose of a key-derivation function (KDF)?\n\n"
                    "A) Generate public keys\n"
                    "B) Authenticate digital signatures\n"
                    "C) Encrypt data using a password\n"
                    "D) Transform a secret into keys and Initialization Vectors\n\n"
                    "Reply with only the single letter A, B, C, or D."}
    ],
    temperature=0.0,
)
print(out["choices"][0]["message"]["content"])
```

LM Studio loads the GGUF directly. Ollama needs a Modelfile pointing at the GGUF plus a `TEMPLATE` block matching the zephyr chat shape (the GGUF metadata carries the template; recent Ollama versions read it automatically).

## What changes between verticals — and what doesn't

<figure class="fn-diagram" aria-label="The vertical-curator workflow as a hub-and-spoke topology — fieldkit.publish_quant at the centre as the unchanging publishing surface, with three vertical-card spokes radiating to it: finance (week 1, AdaptLLM/finance-chat, numeric_match scorer + llama-2 chat template), legal (week 2, Equall/Saul-7B-Instruct-v1, contains scorer + mistral chat template), and cyber (week 3, ZySec-AI/SecurityLLM, mcq_letter scorer + zephyr chat template, this article's accent node).">
  <svg viewBox="0 0 900 500" role="img" aria-label="The vertical-curator workflow as a hub-and-spoke topology — fieldkit.publish_quant at the centre as the unchanging publishing surface, with three vertical-card spokes radiating to it: finance (week 1, AdaptLLM/finance-chat, numeric_match scorer + llama-2 chat template), legal (week 2, Equall/Saul-7B-Instruct-v1, contains scorer + mistral chat template), and cyber (week 3, ZySec-AI/SecurityLLM, mcq_letter scorer + zephyr chat template, this article's accent node)." preserveAspectRatio="xMidYMid meet">
    <defs>
      <radialGradient id="d-cyber-halo-grad" cx="0.5" cy="0.5" r="0.55">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d-cyber-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="620" y="364" width="190" height="106" fill="url(#d-cyber-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 450 230 L 450 136" />
      <path class="fn-diagram__edge" pathLength="100" d="M 380 330 L 280 364" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 520 330 L 620 364" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="370" y="230" width="160" height="100" rx="10" />
      <rect class="fn-diagram__node" x="355" y="30" width="190" height="106" rx="8" />
      <rect class="fn-diagram__node" x="90" y="364" width="190" height="106" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="620" y="364" width="190" height="106" rx="8" style="fill: url(#d-cyber-accent-grad)" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono" x="450" y="275" text-anchor="middle">fieldkit.publish_quant</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="297" text-anchor="middle">v0.4.1 · unchanged</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="450" y="80" text-anchor="middle">WEEK 2 · LEGAL</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="450" y="102" text-anchor="middle">Saul-7B-Instruct-v1</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="122" text-anchor="middle">contains · mistral</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="185" y="414" text-anchor="middle">WEEK 1 · FINANCE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="185" y="436" text-anchor="middle">finance-chat</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="185" y="456" text-anchor="middle">numeric_match · llama-2</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="715" y="414" text-anchor="middle">WEEK 3 · CYBER</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="715" y="436" text-anchor="middle">SecurityLLM</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="715" y="456" text-anchor="middle">mcq_letter · zephyr</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(438 32)"><path d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75M18.75 4.97A48.416 48.416 0 0012 4.5c-2.291 0-4.545.16-6.75.47m13.5 0c1.01.143 2.01.317 3 .52m-3-.52l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.988 5.988 0 01-2.031.352 5.988 5.988 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L18.75 4.971zm-16.5.52c.99-.203 1.99-.377 3-.52m0 0l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.989 5.989 0 01-2.031.352 5.989 5.989 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L5.25 4.971z"/></g>
      <g class="fn-diagram__icon" transform="translate(173 366)"><path d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(703 366)"><path d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z"/></g>
    </g>
  </svg>
  <figcaption>Three verticals share one publishing surface — the only deltas live in scripts/, not in fieldkit/.</figcaption>
</figure>

Three things changed for cyber; one didn't.

**Did not change: `fieldkit`.** This is the headline. The v0.4.1 release lifted `VerticalBench.from_jsonl` with `open_book=...` and `subset=...` kwargs for FinanceBench, but the surface that lifted was always vertical-parametric. `fieldkit.publish.publish_quant` already accepted `vertical_eval=` (dict of variant → score), `vertical_eval_name=` (the column header), and `chat_format=` (the snippet renderer's template hint). Swapping `legalbench` for `cybermetric` needed zero new symbols and zero behavior changes. The PyPI package version on this release's commit is the same `0.4.1` the legal release shipped on.

**Changed: the merge script.** CyberMetric ships as a single 80-question JSON, not 162 per-task TSV folders like LegalBench. The new [`scripts/cyber_merge.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/cyber_merge.py) samples 50 rows deterministically (seed 42), formats each as a 4-option MCQ prompt, and writes the `{id, text, answer, task}` JSONL shape `VerticalBench.from_jsonl(..., format="legalbench")` already consumed. The `task` tag stays the constant `"cybermetric"` since the bench is unified, not multi-task — the per-task tagging dimension just collapses to one bucket. Same downstream consumer; no fieldkit code touched.

**Changed: the scorer.** CyberMetric's gold answer is a single letter (A/B/C/D), and the built-in `fieldkit.eval.contains` would match a stray "A" anywhere in the model's prose response — catastrophically permissive. The fix is a local `mcq_letter` scorer in [`scripts/g3_measure_variants.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/g3_measure_variants.py): regex-extract a word-bounded letter, preferring an "Answer: X" or "Option X" marker, falling back to the first bounded letter in the response. The function is ~15 lines, lives next to the measurement loop, and gets plugged into `VerticalBench` via the `scorer=` callable parameter that's been in fieldkit since v0.4.0. If a fourth and fifth vertical reuse the same MCQ shape — and they probably will, since MCQ is the cheapest scalable bench format — this local scorer becomes the candidate for promotion to `fieldkit.eval` in a future v0.5.

**Changed: the chat-template wrapper.** Finance (Llama-2-chat lineage) and legal (Mistral-Instruct lineage) both use `<s>[INST] {q} [/INST]`. Cyber uses Zephyr's `<|user|>\n{q}</s>\n<|assistant|>\n`. The measurement script gained a second wrapper function alongside `_wrap_inst` and a per-vertical dispatch (`{"financebench": _wrap_inst, "legalbench": _wrap_inst, "cybermetric": _wrap_zephyr}`). Three lines of wiring; no fieldkit changes.

The cleanest signal that the surface generalized as designed: the cyber card and the legal card render with the same four-axis table shape, the same three run snippets, the same Methods link convention. Only the column header, the numbers, and the `chat_format` value differ.

## A new scorer — why MCQ letter, not full text

CyberMetric's row schema is `{question, answers: {A, B, C, D}, solution: "B"}`. Two plausible scoring designs:

1. **Full-text gold + `contains`.** Use the full answer string as gold ("The Chief Information Security Officer (CISO) is responsible for..."), prompt the model to "output the correct option's full text", check with `fieldkit.eval.contains`. Pro: reuses an existing scorer. Con: a model paraphrasing the option text (Zephyr-DPO models are verbose) breaks the substring match.
2. **Letter gold + `mcq_letter`.** Use just `"B"` as gold, prompt the model to "reply with only the letter A, B, C, or D", check via regex-extract. Pro: paraphrasing-immune; matches every academic MCQ-eval convention. Con: needs a new scorer.

The preflight gate exposed the trade. Five questions on the F16 GGUF scored 3/5 — passing the abort-on-zero threshold by a comfortable margin. The two failures were both compliance failures: the model wrote prose ("The Chief Information Security Officer (CISO) is indeed responsible for...") instead of a letter. The `mcq_letter` scorer correctly returned 0 — "B" never appeared as a word-bounded token in the prose. Q2 expected B, the response named CISO without spelling out the letter. Q4 expected C, the response launched into a numbered list ("1. Keyboard Monitor...") that the n_predict cutoff truncated before any letter appeared.

Those are real compliance failures — not scoring bugs. A `contains` scorer would have flagged "B" inside "CISO" or "C" inside "Keyboard" as false-positive matches, hiding the failure. The MCQ-letter scorer surfaces it.

The full-bench numbers on 50 questions per variant absorb this compliance variance — across enough rows, the wins and losses average out. But the design choice (letter gold, MCQ-letter scorer) is what makes those averages meaningful.

## Preflight as a fast-fail gate

A pattern carried forward from the finance release's hard-won lessons: every new model picks runs a 5-question preflight bench on the F16 source weights before sinking the multi-hour quantize + measure cycle. `scripts/g3_preflight_bench.py` converts the source to F16 GGUF, spins up `llama-server` on GPU, scores five questions from the appropriate vertical bench, and exits non-zero if fewer than one correct. On the cyber release this gate fired clean (3/5, PASS), confirming the model is properly chat-tuned and the zephyr template wrapping is correct. Had it scored 0/5 — the failure mode that bit the original finance V1 attempt against `instruction-pretrain/finance-Llama3-8B` — the cycle would have aborted before the ~3-hour quantize-plus-measure sunk cost.

The preflight script's small ZySec-specific patch was teaching it to detect Zephyr chat templates (the existing logic recognized only Llama-2-chat from the README and the Mistral-Instruct `[INST]` shape from tokenizer_config.json). Five lines, same change pattern as the measurement script.

## A note on the CyberMetric subset

CyberMetric ships in four release sizes (80, 500, 2000, 10000 questions). The 80-question release is the right scale for per-variant scoring on a single Spark — same order of magnitude as the FinanceBench mini-eval (50 questions) and the LegalBench subset (50 questions) used in earlier cards. Picking 50 of 80 (sampled deterministically with `random.seed(42)` so reruns reproduce) sits in the same statistical neighborhood: ten correct answers per variant separate Q-tier ranks.

The 9-domain topical distribution that the CyberMetric paper documents (cryptography, network security, identity management, governance, etc.) is not exposed as a per-row tag in the public JSON, so we tag all 50 sampled rows with a single `task: "cybermetric"` and report one aggregate score per variant. A larger sample or a topic-annotated rebuild would let us slice per-domain, but for the variant-card claim — "this quant did not lose cyber knowledge versus the F16 reference" — a single aggregate is what the card needs.

A more authoritative score would extend the subset to the full 500-question or 2000-question release and run those once per model, not per variant. The 50-question card is the *publishable* score — comparable across releases, runnable per-variant in under 10 minutes — not the *authoritative* one.

## Thermal envelope notes

Sustained-load minutes (probed via `nvidia-smi` at 10-second intervals during the bench sweep) confirmed the pattern observed on the prior two cards — smaller variants generate faster, get hotter faster, back off the GPU sooner. F16 sustained 12.7 minutes before throttling; Q8_0 sustained 7.2; Q6_K 6.5; Q5_K_M 5.5; Q4_K_M only 4.5. The inverse-of-throughput shape is consistent across all three vertical releases.

The interesting non-result: the Q8_0 anomaly didn't repeat. Finance's Q8_0 was 8.9 tok/s vs F16's 11.5; legal's was 7.3 vs 10.9; cyber's was 30.3 vs 17.5. Same model architecture (Mistral 7B-equivalent) on all three. Same sweep order. Different result on cyber. The leading hypothesis — that Q8_0 ran on a thermally-warmed die after Q4/Q5/Q6 had already cooked the GPU — would have predicted a slowdown here too. It didn't show. Possibilities: SecurityLLM's specific tensor distribution loads the GPU differently, or the prior anomaly was sampling within a tighter cycle than we thought. Either way, the cyber card carries the measurement as-recorded.

## Methods and reproducibility

The full release pipeline lives in [`scripts/g3_build_first_quant.sh`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/g3_build_first_quant.sh). For SecurityLLM, the invocation is:

```bash
MODEL_ID=ZySec-AI/SecurityLLM \
  ./scripts/g3_build_first_quant.sh all
```

The case statement at the top of the script auto-resolves `MODEL_LICENSE=apache-2.0`, `CHAT_FORMAT=zephyr`, `VERTICAL_BENCH=cybermetric`, and `ARTICLE_SLUG=becoming-a-cyber-curator-on-spark` from the model ID, so no env vars need passing manually. The pipeline runs: preflight → download → preflight-bench (5-question CyberMetric gate against FP source weights — passed at 3/5) → probe → quantize (5 variants) → measure (4 axes per variant) → publish-dryrun → publish.

The lineage rows for this release live at `evidence/lineage-SecurityLLM/results.tsv` (one row per variant, hypotheses + measurements + bench source). The merged CyberMetric JSONL the measure step consumed lives at `/home/nvidia/data/eval-benches/cybermetric/cybermetric_merged.jsonl` — produced by `scripts/cyber_merge.py` from the upstream [tihanyin/CyberMetric](https://huggingface.co/datasets/tihanyin/CyberMetric) dataset.

End-to-end wall time on the Spark was approximately ~80 minutes for the measurement work: ~10 minutes for the download (one DNS-transient retry), ~1 minute for the preflight bench, ~6 minutes for the 5-variant quantize, and ~38 minutes for the four-axis measurement sweep (5 variants × ~7.5 minutes per variant — perplexity + tok/s probe + thermal-overlapped 50-question CyberMetric sweep). The HF upload itself runs detached via the v0.4.0 resilient pusher (`hf_push_resilient.py`, `upload_large_folder` API with `num_workers=1` — the slow-upstream profile lessons from the Saul release carry forward).

## What's next

The publishing surface has now shipped three verticals in three weeks: finance numeric reasoning, legal binary classification, cyber MCQ. Each used a different scorer (`numeric_match`, `contains`, `mcq_letter`), a different chat template (`llama-2` / `mistral` / `zephyr`), and a different upstream license tier (`llama2` / `mit` / `apache-2.0`). The fact that all three render with the same four-axis card on HuggingFace is the surface having generalized as designed.

**Medical is the natural fourth.** A Llama-3-Med-Instruct or BioMistral-7B card on MedQA-USMLE or MedMCQA would exercise a fourth chat template and a fourth scorer pattern (still MCQ-shape, likely reusing `mcq_letter` verbatim — the first reuse signal). If reuse holds, `mcq_letter` is the next promotion candidate from local-helper to `fieldkit.eval`.

**A future v0.5 then becomes a consolidation release** — promoting the recurring scorers, the chat-template detection logic, and the merge-script shape into the package. By then the publishing surface has earned its abstractions: three verticals validated the shape, the fourth confirmed reuse, the fifth (whatever that vertical turns out to be) drops the time-to-card from a session to an afternoon.

The cyber card is up. Three verticals down, one machine.

---

**Catalog page:** [`/artifacts/notebooks/securityllm-notebooks/`](/artifacts/notebooks/securityllm-notebooks/) — the dual-path Open in Colab / Open in Kaggle on-ramp, builder + user variants, target-model lineage, and bounded drift between Spark and cloud quants — the full notebook card.
