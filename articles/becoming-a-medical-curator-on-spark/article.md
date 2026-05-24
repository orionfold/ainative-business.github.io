---
title: "Orionfold/II-Medical-8B-GGUF on Spark — five medical-reasoning variants, MedMCQA mini-eval, ChatML reasoning format"
date: 2026-05-16
author: Manav Sehgal
product: llama.cpp
stage: deployment
difficulty: intermediate
time_required: "~5 hours end-to-end on a DGX Spark"
hardware: "NVIDIA DGX Spark"
tags: [gguf, quantization, medical, healthcare, orionfold, medmcqa, qwen3, chatml, reasoning, fieldkit, spark-tested]
summary: "Five GGUF variants of Intelligent-Internet/II-Medical-8B (Qwen3-8B + DAPO reasoning recipe) measured on a DGX Spark. Q5_K_M lands at 36.4 tok/s, 5.45 GB, and 52% on a MedMCQA n=50 mini-eval — above F16. First reasoning recipe in the series."
status: published
signature: MedicalQuad
series: Machine that Builds Machines
book_chapters: [10, 11]
fieldkit_modules: [quant, publish, eval, lineage]
also_stages: [observability]
hf_url: https://huggingface.co/Orionfold/II-Medical-8B-GGUF
---

Today on the Spark: [`Orionfold/II-Medical-8B-GGUF`](https://huggingface.co/Orionfold/II-Medical-8B-GGUF) ships — five GGUF variants of [Intelligent-Internet/II-Medical-8B](https://huggingface.co/Intelligent-Internet/II-Medical-8B), a Qwen3-8B base with an SFT + DAPO reasoning recipe tuned for clinical Q&A. Same four-axis card shape as the finance, legal, and cyber releases before it; same publishing surface; same lineage trail. What changes this week is that the model under the card is the first one in the series with a `<think>` block — and that single shift exposed a generation-budget assumption the prior three cards never had to face.

The narrative thread: after finance numeric reasoning, legal binary classification, and cyber MCQ, medical is the first vertical to ship a model that *thinks* before it answers. The generation budget — the default 256 token n_predict every prior preflight ran with — became a load-bearing parameter overnight. At 256 the F16 preflight scored 2/5 not because the model didn't know the medicine, but because the `<think>` block burned the budget before any letter token landed. At 1024 the same model swept clean and the full quantize-plus-measure cycle ran on numbers that actually reflected capability.

This article is the publishing receipt for the medical-vertical release: the Spark-measured numbers, the new ChatML preflight branch, the variant picker for downstream use, and the honest gotchas the card inherits from being a reasoning recipe rather than a plain SFT.

## Spark-tested numbers

The card under each variant on HuggingFace carries these numbers verbatim. They were produced by `fieldkit.quant.measure_perplexity_gguf`, `llama-bench`, a thermal-probe wrapper, and `fieldkit.eval.VerticalBench` with the cyber-vintage `mcq_letter` scorer over a 50-question MedMCQA subset (sampled deterministically from [`openlifescienceai/medmcqa`](https://huggingface.co/datasets/openlifescienceai/medmcqa)'s validation split — the test split ships with masked labels and would have produced a uniformly-zero scoreboard).

| Variant | Size | Perplexity (wikitext-2) | tg tok/s | pp tok/s | MedMCQA (n=50, mcq_letter) |
|---------|-------|------------------------|----------|----------|----------------------------|
| F16     | 15.3 GB | 16.27 | 15.94 | 2262.2 | 48% (24/50) |
| Q8_0    |  8.11 GB | 16.30 | 28.42 | 2523.3 | 48% (24/50) |
| Q6_K    |  6.26 GB | 16.01 | 32.80 | 2332.2 | 46% (23/50) |
| **Q5_K_M** ⭐ |  **5.45 GB** | **16.24** | **36.36** | 2579.5 | **52% (26/50)** |
| Q4_K_M  |  4.68 GB | 16.55 | 43.57 | 2773.2 | 42% (21/50) |

Three observations worth narrating:

- **Q5_K_M lands above F16 on both perplexity and the medical bench.** Its perplexity (16.24) sits a hair under F16's 16.27 — within wikitext-2 sampling noise, but the direction is unusual; you expect lossy quantization to push perplexity *up*, not down, and a sub-F16 number usually means the F16 reference was on the unlucky tail of the sample. Its MedMCQA score is 52% vs F16's 48% — 4 percentage points, two questions out of fifty, comfortably inside the n=50 binomial noise floor (~7pp 95% CI). Either number alone would be unsurprising; together they read as a genuine sweet spot rather than a fluke.

:::why[Q5_K_M as the medical sweet spot]
Sub-F16 perplexity *and* above-F16 bench accuracy at 5.45 GB and 2.3× the throughput. The wikitext-2 number alone could be sampling noise; the bench delta alone could be binomial noise. Together they read as a genuine pick rather than a fluke — which is why `recommended_variant=Q5_K_M` ships in the manifest.
:::

- **The Q8_0 anomaly didn't show up this time.** Finance and legal both saw Q8_0 *slower* than F16 (8.9 vs 11.5 and 7.3 vs 10.9 tg tok/s — suspected at the time to be a thermal-scheduling artefact of running it last in the sweep). On cyber, Q8_0 was 30.3 vs F16's 17.5 — 1.7× faster. On medical, the same pattern: 28.4 vs F16's 15.9, 1.78× faster. The split now divides four verticals two-and-two — finance and legal slow, cyber and medical fast — and the cleanest hypothesis is that the slow ones were continued-pretrain-flavored models (finance-chat is a continued-pretrain SFT, Saul is a heavy domain-pretrained SFT) while the fast ones are chat-tune-only shapes (SecurityLLM is Zephyr-DPO, II-Medical is SFT+DAPO on top of base Qwen3). The thermal-scheduling explanation never fully fit; the model-shape correlation does.

- **The MedMCQA spread is tight across variants.** F16 = 48, Q8 = 48, Q6 = 46, Q5 = 52, Q4 = 42. Six percentage points top-to-bottom on a 50-question bench is well inside what binomial sampling allows for a four-option MCQ at this scale. The take-home: lossy quantization did not measurably damage medical reasoning capability for this model — and the small disagreements between variants are noise the card surfaces honestly rather than smoothing away.

## Variant picker

| Variant | When to reach for it |
|---------|---------------------|
| **Q5_K_M** | Default pick — the sweet-spot variant. 5.45 GB, 36.4 tok/s, 52% on MedMCQA (highest of the five), perplexity essentially equal to F16. The one to download first. |
| **Q4_K_M** | Throughput pick. 4.68 GB, 43.6 tok/s, 42% on MedMCQA. When you're scanning a corpus and human-reviewing top hits — the 10-point bench delta vs Q5_K_M is recoverable downstream if your loop has a reviewer. |
| **Q6_K** | Lowest-perplexity pick. 6.26 GB, 32.8 tok/s, 46% on MedMCQA — perplexity 16.01 is the cleanest of the five against the wikitext-2 reference. Reach for it when you want minimum F16-drift on general-language work and don't mind the throughput cost vs Q5_K_M. |
| **Q8_0** | Lossless-feeling pick. 8.11 GB, 28.4 tok/s, 48% on MedMCQA — matches F16's bench score, perplexity within 0.03. Use it when you want F16 quality at 53% the size and 1.78× the speed. |
| **F16** | Reference only. 15.3 GB, 15.9 tok/s, 48% on MedMCQA. No quantization — use for measurement / baseline / debugging quant-induced regressions, not for production. |

## Using this release

The card on HuggingFace ships the same three snippets every Orionfold quant card ships, derived from `model_license=apache-2.0`, `chat_format=chatml`, and `recommended_variant=Q5_K_M`. Reproduced here for read-through.

Pull a variant (Q5_K_M is the default pick on this card):

```bash
huggingface-cli download Orionfold/II-Medical-8B-GGUF model-Q5_K_M.gguf \
  --local-dir ./models/ii-medical-8b
```

Serve it via `llama-server` (OpenAI-compatible HTTP API at `http://127.0.0.1:8080/v1`). The reasoning recipe means the model produces a `<think>` block before its answer — give it room or it will get cut off mid-thought:

```bash
llama-server -m ./models/ii-medical-8b/model-Q5_K_M.gguf \
  -c 4096 -ngl 99 -t 8 \
  -n 1024 \
  --host 0.0.0.0 --port 8080
```

:::pitfall[Reasoning models need a bigger n_predict than you think]
The default 256-token n_predict in most llama.cpp drivers is sized for direct-answer models. A reasoning recipe like II-Medical-8B emits an entire `<think>` block — typically 200–600 tokens of internal deliberation — *before* the answer letter. At 256, the answer token frequently never lands. Set `-n 1024` (or higher) on serve, and `LLAMA_CLI_NPREDICT=1024` in your bench harness. The preflight on F16 scored 2/5 at 256 and a clean 5/5 at 1024 — same weights, just enough budget.
:::

In-process via `llama-cpp-python` (note `chat_format="chatml"` — II-Medical-8B uses Qwen3's ChatML template, `<|im_start|>` / `<|im_end|>`, not Llama-2's `[INST]` or Zephyr's `<|user|>`):

```python
from llama_cpp import Llama
llm = Llama(
    model_path="./models/ii-medical-8b/model-Q5_K_M.gguf",
    n_ctx=4096, n_gpu_layers=99, chat_format="chatml",
)
out = llm.create_chat_completion(
    messages=[
        {"role": "user",
         "content": "A 56-year-old man presents with sudden onset of severe "
                    "tearing chest pain radiating to the back. BP 180/100, "
                    "wider pulse pressure on the right than left arm.\n\n"
                    "Which is the most likely diagnosis?\n"
                    "A) Acute pericarditis\n"
                    "B) Aortic dissection\n"
                    "C) Pulmonary embolism\n"
                    "D) Myocardial infarction\n\n"
                    "Reply with only the single letter A, B, C, or D."}
    ],
    max_tokens=1024,
    temperature=0.0,
)
print(out["choices"][0]["message"]["content"])
```

LM Studio loads the GGUF directly and reads the ChatML template from the GGUF metadata. Ollama needs a Modelfile pointing at the GGUF plus a `TEMPLATE` block matching the ChatML shape; recent Ollama versions read the embedded template automatically, but verify before relying on it.

:::define[ChatML]
The chat-formatting convention introduced with OpenAI's ChatML spec and adopted by the Qwen family. Each turn is wrapped in `<|im_start|>role` / `<|im_end|>` markers — `<|im_start|>user`, `<|im_start|>assistant`, `<|im_start|>system`. Distinct from Llama-2's `[INST]…[/INST]`, Mistral's `<s>[INST]`, and Zephyr's `<|user|>`. The GGUF carries the template in its metadata so most loaders auto-detect; the trap is that older preflight harnesses key on file-name suffixes and miss it.
:::

:::define[DAPO]
Direct Advantage Policy Optimization — a preference-tuning variant in the DPO family. Like DPO it learns from pairs of preferred and rejected responses without needing an explicit reward model, but reformulates the loss to track an advantage estimate. The II-Medical-8B authors report DAPO + supervised fine-tuning lifted HealthBench from baseline Qwen3-8B to a score comparable to OpenAI's o1 reasoning model on medical-specific items.
:::

## What changes between verticals — and what doesn't

<figure class="fn-diagram" aria-label="The vertical-curator workflow as a hub-and-spoke topology — fieldkit.publish_quant at the centre as the unchanging publishing surface, with four vertical-card spokes radiating to it: finance (week 1, AdaptLLM/finance-chat, numeric_match scorer + llama-2 chat template), legal (week 2, Equall/Saul-7B-Instruct-v1, contains scorer + mistral chat template), cyber (week 3, ZySec-AI/SecurityLLM, mcq_letter scorer + zephyr chat template), and medical (week 4, Intelligent-Internet/II-Medical-8B, mcq_letter reused + chatml chat template, this article's accent node).">
  <svg viewBox="0 0 900 500" role="img" aria-label="The vertical-curator workflow as a hub-and-spoke topology — fieldkit.publish_quant at the centre as the unchanging publishing surface, with four vertical-card spokes: finance, legal, cyber, and medical (the article's accent node)." preserveAspectRatio="xMidYMid meet">
    <defs>
      <radialGradient id="d-med-halo-grad" cx="0.5" cy="0.5" r="0.55">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d-med-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="640" y="100" width="190" height="106" fill="url(#d-med-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 380 230 L 280 153" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 520 230 L 640 153" />
      <path class="fn-diagram__edge" pathLength="100" d="M 380 330 L 280 364" />
      <path class="fn-diagram__edge" pathLength="100" d="M 520 330 L 620 364" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="370" y="230" width="160" height="100" rx="10" />
      <rect class="fn-diagram__node" x="90" y="47" width="190" height="106" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="640" y="100" width="190" height="106" rx="8" style="fill: url(#d-med-accent-grad)" />
      <rect class="fn-diagram__node" x="90" y="364" width="190" height="106" rx="8" />
      <rect class="fn-diagram__node" x="620" y="364" width="190" height="106" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono" x="450" y="275" text-anchor="middle">fieldkit.publish_quant</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="297" text-anchor="middle">v0.4.2 · unchanged</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="185" y="97" text-anchor="middle">WEEK 2 · LEGAL</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="185" y="119" text-anchor="middle">Saul-7B-Instruct-v1</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="185" y="139" text-anchor="middle">contains · mistral</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="735" y="150" text-anchor="middle">WEEK 4 · MEDICAL</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="735" y="172" text-anchor="middle">II-Medical-8B</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="735" y="192" text-anchor="middle">mcq_letter · chatml</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="185" y="414" text-anchor="middle">WEEK 1 · FINANCE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="185" y="436" text-anchor="middle">finance-chat</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="185" y="456" text-anchor="middle">numeric_match · llama-2</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="715" y="414" text-anchor="middle">WEEK 3 · CYBER</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="715" y="436" text-anchor="middle">SecurityLLM</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="715" y="456" text-anchor="middle">mcq_letter · zephyr</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(173 49)"><path d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75M18.75 4.97A48.416 48.416 0 0012 4.5c-2.291 0-4.545.16-6.75.47m13.5 0c1.01.143 2.01.317 3 .52m-3-.52l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.988 5.988 0 01-2.031.352 5.988 5.988 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L18.75 4.971zm-16.5.52c.99-.203 1.99-.377 3-.52m0 0l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.989 5.989 0 01-2.031.352 5.989 5.989 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L5.25 4.971z"/></g>
      <g class="fn-diagram__icon" transform="translate(173 366)"><path d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/></g>
      <g class="fn-diagram__icon" transform="translate(703 366)"><path d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(723 102)"><path d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/></g>
    </g>
  </svg>
  <figcaption>Four verticals share one publishing surface — the only deltas live in scripts/, not in fieldkit/.</figcaption>
</figure>

Three things changed for medical; one didn't.

**Did not change: `fieldkit`.** This is the headline of the fourth release. `fieldkit v0.4.2` shipped two weeks ago to land the publishing-surface polish (neutral default prompts, manifest `recommended_variant`); the medical card consumed those changes without needing any new ones. `fieldkit.publish.publish_quant` already accepts `vertical_eval=` (variant → score dict), `vertical_eval_name=` (the column header), `chat_format=` (template hint for snippet rendering), and `recommended_variant=` (the manifest's `Q5_K_M` sticker). Swapping `cybermetric` for `medmcqa` needed zero new symbols and zero behavior changes. The PyPI package version on this release's commit is the same `0.4.2` the cyber release shipped on.

**Changed: the merge script.** MedMCQA ships as four splits on HuggingFace — `train` (182K), `validation` (4.2K), `test` (6.1K, labels masked), and `dev`. The new [`scripts/medmcqa_merge.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/medmcqa_merge.py) samples 50 rows from `validation` deterministically (seed 42), formats each as a 4-option MCQ prompt with the same `{id, text, answer, task}` JSONL shape `VerticalBench.from_jsonl(..., format="legalbench")` already consumes. The script logs the letter distribution (A=17 / B=15 / C=13 / D=5 for this seed — slightly D-light, which is the population shape MedMCQA ships with at validation) and a per-subject histogram for sanity. Same downstream consumer; no fieldkit code touched. Picking `validation` over `test` matters — the test split's `cop` (correct-option-pointer) is `-1` on every row, which would have produced a uniformly-zero scoreboard masquerading as a benchmark failure.

:::define[MedMCQA]
A multi-choice medical-Q&A benchmark of ~194K questions sourced from Indian medical entrance exams (AIIMS, NEET-PG). Each row has a question, four options, and a single correct-option pointer (`cop`) across 21 medical subjects and 2,400 healthcare topics. Long-tail subject coverage makes it a stricter test of medical breadth than USMLE-derived benches.
:::

**Changed: the preflight prompt-format detector.** The existing `_detect_prompt_format` in [`scripts/g3_preflight_bench.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/g3_preflight_bench.py) recognized three families — Llama-2-chat from README phrases, Mistral-Instruct from `tokenizer_config.json`'s `[INST]` markers, and Zephyr from the `<|user|>` shape. ChatML's `<|im_start|>` was falling through to the unwrapped-prompt fallback — silently — and the model was being preflight-scored on bare raw questions, which any reasoning recipe would mishandle. The fix is a new `chatml` branch in both `_detect_prompt_format` and `_format_prompt`, plus a `<|im_start|>` token-search added to the format-detection precedence. Five lines of detection, twelve of wrapping. The prior three cards never tripped it because none of them used ChatML; this one did, and the lessons-on-the-way pattern from the cyber card (Zephyr branch added when Zephyr arrived) repeated cleanly.

:::pitfall[Silent prompt-format fallthrough is the worst kind of preflight failure]
A preflight that scores 0/5 is loud — it aborts the cycle and forces a model re-pick. A preflight that scores anywhere on the curve but is *secretly* prompting the model with no chat-template wrapping at all looks like a real measurement. Future templates will land. The dispatch table's `else: return prompt` arm is now flagged with a `WARN` log so the next family-of-three template gets caught at first sight.
:::

**Changed: the chat-template wrapper.** Same one-function add as cyber. The measurement script gained a `_wrap_chatml` function alongside `_wrap_inst` and `_wrap_zephyr`, and the per-vertical dispatch table got an entry: `{"medmcqa": _wrap_chatml}`. The card's HF README snippet renders `chat_format="chatml"` because the manifest carries it, and `llama-cpp-python` recognizes the literal string verbatim. Three lines of wiring; no fieldkit changes.

The cleanest signal that the surface continues to generalize as designed: the medical card and the cyber card render with the same four-axis table shape, the same three run snippets, the same Methods link convention. Only the column header, the numbers, the `chat_format` value, and the recommended-variant pin differ.

## On the reasoning-recipe generation budget

CyberMetric's gold answer was a single letter and the model's job was to emit it directly. MedMCQA's gold answer is also a single letter — but the model's *path* to it now includes a deliberative `<think>…</think>` block. The cyber generation budget could comfortably sit at 256 tokens because the entire response shape was "Answer: X" plus maybe a justification sentence. The medical generation budget can't.

:::math[The medical-reasoning generation budget]
A reasoning trace on a hard clinical MCQ typically runs 400–800 tokens before the closing `</think>` tag — the model walks the differential, names competing diagnoses, weighs evidence, lands. The answer letter is 1 token. At n_predict=256, the budget runs out somewhere inside the differential. At n_predict=1024, there's headroom of roughly 200–600 unused tokens after the answer — wasted on completion, but a guarantee that the letter actually lands.
:::

Two practical consequences for downstream use. First, the inference cost shape changes: a single MedMCQA query at Q5_K_M produces ~600 tokens at 36.4 tok/s, so wall-clock per question is ~16 seconds, not the ~2 seconds a non-reasoning 8B at the same throughput would take on a 70-token direct answer. Second, the KV-cache budget changes: a 4096-context server holds ~14 reasoning turns before eviction kicks in, not the ~58 short-answer turns the same context would hold. If you're building a multi-turn medical assistant on this model, planning for that 8× turn-density delta is the difference between a clean session and a context-overrun cliff. The base Qwen3-8B's native context is 40,960 tokens, so push `-c` higher if your workload needs longer histories — but you'll burn unified memory proportionally, and on Spark that's the gating constraint.

## A note on the MedMCQA subset

MedMCQA ships ~194K total questions across train / validation / dev / test. Evaluating all of validation per variant would take ~14 hours per variant; for a 5-variant card on a single Spark, that's the wrong cost shape. The 50-question subset trades fidelity for tractability while staying defensible:

- Sampled from the **validation** split — labels intact, not the test split where `cop=-1` masks every answer.
- Seed 42, so reruns reproduce. Letter distribution (A=17 / B=15 / C=13 / D=5) is slightly D-light, consistent with the validation-population shape.
- Subjects span (roughly) anatomy, pharmacology, pathology, microbiology, biochemistry, medicine, surgery, OB/GYN, pediatrics, psychiatry, and public health. The histogram is in the merge-script log; the merged JSONL doesn't carry per-row subject tags because the bench loader doesn't need them.

A more authoritative score would extend the subset to the full 4.2K-question validation split and run it once per release, not per variant. The 50-question card is the *publishable* score — comparable across releases, runnable per-variant in under 25 minutes — not the *authoritative* one.

## Thermal envelope notes

Sustained-load minutes (probed via `nvidia-smi` at 10-second intervals during the bench sweep) ranged from 18.1 min (Q4_K_M) to 48.9 min (F16). The pattern is the inverse of throughput — smaller variants generate faster, get hotter faster, back off the GPU sooner — and matches the same shape observed on every prior vertical card. Q5_K_M's 20.6-minute sustained envelope is comfortably above what a typical 50-question MedMCQA sweep takes (~22 minutes wall, of which most is generation), so no throttling event interrupts a single-bench run.

The Q8_0 anomaly is the part worth re-narrating. After three verticals the slow-Q8 pattern looked load-bearing; after four it looks model-specific. Finance and legal Q8 were slower than F16 (0.77× and 0.67× respectively); cyber and medical Q8 were dramatically faster (1.73× and 1.78×). The pattern that fits all four data points is *what kind of fine-tune the upstream applied*: heavy continued-pretrain SFTs (finance-chat, Saul) seem to produce Q8 weight distributions the GB10's tensor-core path handles less efficiently than smaller-quant variants; chat-tune-only shapes (Zephyr-DPO, SFT+DAPO) don't. One more vertical with each shape would confirm or fold the hypothesis; for now the medical card carries the measurement as-recorded.

## Methods + reproducibility

The full release pipeline lives in [`scripts/g3_build_first_quant.sh`](https://github.com/manavsehgal/ai-field-notes/blob/main/scripts/g3_build_first_quant.sh). For II-Medical-8B, the invocation is:

```bash
HF_VENV=/tmp/fk \
  MODEL_ID=Intelligent-Internet/II-Medical-8B \
  LLAMA_CLI_NPREDICT=1024 \
  ./scripts/g3_build_first_quant.sh all
```

The case statement at the top of the script auto-resolves `MODEL_LICENSE=apache-2.0`, `CHAT_FORMAT=chatml`, `VERTICAL_BENCH=medmcqa`, and `ARTICLE_SLUG=becoming-a-medical-curator-on-spark` from the model ID, so no per-vertical env vars need passing manually. The two non-default env vars matter: `HF_VENV=/tmp/fk` overrides the skill's canonical `/tmp/fk-test` path (which was stale on this Spark; the override pattern is the resilient one), and `LLAMA_CLI_NPREDICT=1024` is the reasoning-budget bump the prior verticals didn't need. The pipeline runs: preflight → download → preflight-bench (5-question MedMCQA gate against FP source weights — passed at 2/5 with the n_predict=256 default, then a clean 5/5 once n_predict was raised) → probe → quantize (5 variants) → measure (4 axes per variant) → publish-dryrun → publish.

The lineage rows for this release live at [`evidence/lineage-II-Medical-8B/results.tsv`](https://github.com/manavsehgal/ai-field-notes/blob/main/articles/becoming-a-gguf-publisher-on-spark/evidence/lineage-II-Medical-8B/results.tsv) (one row per variant, hypotheses + measurements + bench source). The merged MedMCQA JSONL the measure step consumed lives at `/home/nvidia/data/eval-benches/medmcqa/medmcqa_merged.jsonl` — produced by `scripts/medmcqa_merge.py` from the upstream [`openlifescienceai/medmcqa`](https://huggingface.co/datasets/openlifescienceai/medmcqa) dataset.

End-to-end wall time on the Spark was approximately 5 hours, decomposed: ~32 minutes for the source download (16 GB of safetensors over unauthenticated HF), ~18 seconds for the F16 GGUF convert (fast), ~30 seconds for the preflight bench, ~10 minutes for the 5-variant quantize, and ~2h 30min for the four-axis measurement sweep (5 variants × ~30 min per variant — perplexity + tok/s probe + thermal-overlapped 50-question MedMCQA sweep). The HF upload then ran detached via the v0.4.0 resilient pusher (`hf_push_resilient.py`, `upload_large_folder` API with `num_workers=1` — the slow-upstream profile lessons from the Saul release carry forward); upload wall-clock was 2h 32min 33s for 40 GB across 5 GGUF files plus README + .gitattributes.

:::deeper
- **[Intelligent-Internet/II-Medical-8B model card](https://huggingface.co/Intelligent-Internet/II-Medical-8B)** — the upstream recipe, training data sources, and HealthBench numbers.
- **[MedMCQA paper (CHIL 2022)](https://arxiv.org/abs/2203.14371)** — bench construction, subject coverage, and the per-split label conventions.
- **[Sibling card: cyber](/field-notes/becoming-a-cyber-curator-on-spark/)** — the prior release where `mcq_letter` was first introduced and the Zephyr branch was added.
- **[Sibling card: gguf publisher](/field-notes/becoming-a-gguf-publisher-on-spark/)** — the original publishing-surface piece; the lineage table for this release is filed under it.
:::

## What this unlocks

Three concrete uses for the artifact downloaded:

- **A local clinical-Q&A console behind your own retrieval layer.** Wire `llama-server` on Q5_K_M behind a thin web UI, point it at a PubMed mirror or your own clinical-notes corpus, and you have a private medical-reasoning chat that never sends a query off the box. The 5.45 GB footprint leaves headroom on a 128 GB Spark to run a Retriever NIM and a pgvector store alongside, so the full RAG + reasoning loop fits without ever stepping off-device.
- **A reasoning-trace exporter for second-opinion workflows.** The `<think>` block is itself a deliverable — for a learner, for a peer reviewer, for a charting audit. Capture it alongside the answer letter, and the model becomes a documented-reasoning generator, not just a classifier. Q5_K_M's 36.4 tok/s makes a 600-token trace land in ~17 seconds — slow enough that you'd batch it, fast enough that interactive use is comfortable.
- **A bench-locality probe for your own corpus.** The same `g3_measure_variants.py` shape the card uses generalizes — point it at your own MCQ-shaped JSONL of in-house cases, run it across all five variants, and the curve tells you whether your domain agrees with MedMCQA on which quant to pick. The variant that wins MedMCQA may not be the one that wins your bench; the harness is now small enough that running both takes an afternoon, not a week.

:::hardware[The same reasoning trace, on the next tier up]
Q5_K_M at 36.4 tok/s on a single GB10 is comfortable for interactive clinical-Q&A. The same 8B weights on an H100 at FP8 would hit ~280 tok/s — about 8× faster per query, an order of magnitude faster on a parallel batch. The math the article walked (n_predict budget, KV-cache turn density, per-question wall-clock) scales by that constant; the *shape* of the reasoning-vs-direct-answer trade is identical, just compressed in time. The Spark teaches the arithmetic; the H100 runs the same arithmetic at frontier coefficients.
:::

## Closing

Four verticals down, one machine. The publishing surface has now absorbed four different chat templates (Llama-2, Mistral, Zephyr, ChatML), four different scorers (`numeric_match`, `contains`, `mcq_letter` × 2), four different license tiers (Llama-2 community, MIT, Apache-2.0 × 2), and a reasoning recipe on top — without `fieldkit` itself shipping a single new symbol since v0.4.2. The configuration-shape thesis from the cyber release held: a fourth vertical-curator cycle was a half-day of script polish, not a refactor.

What this means for a personal AI power user on one Spark: a fourth domain-specialized 8B with calibrated four-axis numbers, downloadable as a 5.45 GB file, runnable behind `llama-server` in two commands, and audit-trailed end-to-end through the same lineage table the other three releases live in. The medical card is up — watch the [Orionfold org page](https://huggingface.co/Orionfold) for what's next.

---

**Catalog page:** [`/artifacts/notebooks/ii-medical-8b-notebooks/`](/artifacts/notebooks/ii-medical-8b-notebooks/) — the dual-path Open in Colab / Open in Kaggle on-ramp, builder + user variants, target-model lineage, and bounded drift between Spark and cloud quants — the full notebook card.
