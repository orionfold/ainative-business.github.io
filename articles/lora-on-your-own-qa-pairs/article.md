---
title: "LoRA on Your Own Q&A — What 231 Pairs Actually Teach a 3B Model"
date: 2026-04-23
author: Manav Sehgal
product: Hugging Face PEFT + Qwen2.5-3B-Instruct
stage: fine-tuning
difficulty: intermediate
time_required: "~45 minutes end-to-end — 5 min corpus via NIM 8B, 69 s training, 3 min benchmark, plus a 6 GB base-model download"
hardware: "NVIDIA DGX Spark"
tags: [fine-tuning, lora, peft, qwen, second-brain, dgx-spark]
summary: "231 own-voice Q&A pairs, a rank-16 LoRA, 69 s of training on a GB10 Spark. The adapter won't memorize your exact numbers, but it will take a model that refuses 61% of questions about your work and turn it into one that answers all of them in your voice. For facts you still need RAG."
signature: LoraVoiceTransfer
series: Second Brain
fieldkit_modules: [eval]
---

Everyone's first question about fine-tuning is the same: *"can I teach the model my stuff?"* The honest answer is that it depends entirely on what you mean by "teach". A rank-16 LoRA on 231 Q&A pairs of your own writing, trained for 69 seconds of GB10 wall clock, will change the model's behaviour measurably. It will not change the model's knowledge. The distinction matters — and it is also exactly the distinction the Second Brain arc has been circling since the very first RAG article.

This piece ran the experiment honestly. A Qwen2.5-3B-Instruct base. Two hundred and thirty-one Q&A pairs generated from the eleven published [nvidia-learn](/articles/) articles by NIM Llama 3.1 8B. Fourty-four held-out pairs, stratified across articles, for the eval. Forty-four tiny low-rank matrices added to the attention and MLP layers of a 3 billion parameter language model, trained for three epochs against the user's own voice. An LLM-as-judge grader on the held-out set. The numbers that came out told a story sharper than I expected.

| metric (n=44 held-out) | Qwen2.5-3B base | + own-voice LoRA | delta |
|---|---:|---:|---:|
| Hedging / refusal rate | 61% | 0% | **-61 pp** |
| Judge score ≥ 4 (correct) | 4 / 44 | 8 / 44 | **2×** |
| Judge score = 5 (perfect) | 0 / 44 | 4 / 44 | **0 → 4** |
| Judge score mean (0-5) | 1.23 | 2.00 | +63% |
| Answer length (tokens, mean) | 70 | 9 | 7.8× shorter |
| Wall clock per answer | 2.86 s | 0.44 s | 6.5× faster |
| Keyword overlap with reference | 10.9% | 10.2% | ≈ flat |

The big win is the refusal column. Base Qwen2.5-3B literally does not know anything about the `nvidia-learn` project — the articles are private, were written in April 2026, and were never in its training data. Asked what TTFT NVFP4 achieved on the GB10 Spark, it gives the honest correct answer of "the articles don't specifically mention that" and hedges. Asked about `pgvector` port configuration or `NIM_GPU_MEM_FRACTION` defaults, same story. Sixty-one percent of its answers contain some form of "not directly provided", "one would need to refer to the documentation", or "this isn't detailed in the passage". That is the right epistemic behaviour for a model facing a knowledge hole.

The adapter collapses that hedging completely. Zero answers in the held-out set contain a refusal phrase. Every question gets a confident, terse answer. Often correct — judge score of 4 or 5 doubled from four pairs to eight, and the previously non-existent "perfect" band filled with four crisp hits. But also sometimes confidently wrong, and this is the part worth dwelling on: the model does not *know* more after the LoRA than before. What changed is its willingness to state, not its access to facts.

That is the finding. The rest of this article is what it means, how the experiment was shaped, and why the result should reshape how you think about combining fine-tuning with the RAG stack the earlier Second Brain articles built.

## Where the adapter sits — four layers, one thesis

<figure class="fn-diagram" aria-label="The Second Brain stack on a DGX Spark, viewed as four layers. Bottom: the frozen Qwen2.5-3B base, bf16. Middle accent layer: the rank-16 LoRA adapter trained on 231 own-voice Q&A pairs — 120 MB of deltas, the voice layer. Above: the RAG retrieval chain that brings facts in via the prompt context window. Top: the Second Brain assistant endpoint. The claim: LoRA is the voice layer; RAG is the knowledge layer; they stack rather than compete.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Four-layer view of the Second Brain on DGX Spark — frozen base, LoRA voice layer (accent), RAG knowledge layer, and assistant endpoint. Each layer is labelled with what it owns. The LoRA row is the thesis: it teaches voice, not facts." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="lvt-inline-band-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-green)" stop-opacity="0.02"/>
        <stop offset="50%"  stop-color="var(--svg-accent-green)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-green)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="lvt-inline-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--svg-accent-green)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--svg-accent-green)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="lvt-inline-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-green)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--svg-accent-green)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="80" y="20" width="740" height="400" rx="10" fill="url(#lvt-inline-band-grad)" stroke="none"/>
    <rect x="120" y="208" width="660" height="76" rx="10" fill="url(#lvt-inline-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges"></g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="120" y="40" width="660" height="56" rx="8" />
      <rect class="fn-diagram__node" x="120" y="112" width="660" height="56" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="120" y="208" width="660" height="76" rx="10" style="fill: url(#lvt-inline-accent-grad)" />
      <rect class="fn-diagram__node" x="120" y="300" width="660" height="56" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="120" y="372" width="660" height="48" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="180" y="62" text-anchor="start">ASSISTANT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="180" y="84" text-anchor="start">Second Brain endpoint</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="74" text-anchor="end">chat · search · cite</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="180" y="134" text-anchor="start">KNOWLEDGE · RAG</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="180" y="156" text-anchor="start">pgvector · embed · rerank</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="146" text-anchor="end">facts arrive via context window</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="180" y="230" text-anchor="start">VOICE · LoRA ADAPTER</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="180" y="254" text-anchor="start">r=16 · 120 MB · 231 own pairs</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="180" y="272" text-anchor="start">refusal 61% → 0% · judge mean 1.23 → 2.00</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="248" text-anchor="end">29.93M trainable · 69 s train</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="180" y="322" text-anchor="start">BASE LLM · FROZEN</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="180" y="344" text-anchor="start">Qwen2.5-3B-Instruct · bf16</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="334" text-anchor="end">3.09B params · 5.8 GB on disk</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="180" y="392" text-anchor="start">HARDWARE</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="404" text-anchor="end">DGX Spark · GB10 · 128 GB unified</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(136 48)"><path d="M8.25 18.75a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 01-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 00-3.213-9.193 2.056 2.056 0 00-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422-1.048-.987-1.106a48.554 48.554 0 00-10.026 0 1.106 1.106 0 00-.987 1.106v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12"/></g>
      <g class="fn-diagram__icon" transform="translate(136 120)"><path d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-1.5a1.125 1.125 0 01-1.125-1.125V17.25m8.25-7.5v6.375c0 .621-.504 1.125-1.125 1.125h-1.5a1.125 1.125 0 01-1.125-1.125V9.75"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(136 220)"><path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z"/></g>
      <g class="fn-diagram__icon" transform="translate(136 308)"><path d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375"/></g>
      <g class="fn-diagram__icon" transform="translate(136 380)"><path d="M8.25 7.5V6.108c0-1.135.845-2.098 1.976-2.192.373-.03.748-.057 1.123-.08M15.75 18H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08M15.75 18.75v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5A3.375 3.375 0 006.375 7.5H5.25m11.9-3.664A2.251 2.251 0 0015 2.25h-1.5a2.25 2.25 0 00-2.15 1.586m5.8 0c.065.21.1.433.1.664v.75h-6V4.5c0-.231.035-.454.1-.664M6.75 7.5H4.875C3.839 7.5 3 8.34 3 9.375v9c0 1.036.84 1.875 1.875 1.875h3"/></g>
    </g>
  </svg>
  <figcaption>LoRA is the middle band — 120 MB of deltas trained on your own Q&amp;A pairs, attached at inference time on top of a frozen base. It teaches voice, not facts. The facts arrive through the RAG layer above; the accuracy lives there, not in the adapter.</figcaption>
</figure>

## Why Qwen2.5-3B and not the 8B base NIM is serving

The natural impulse is to fine-tune *the* model the rest of your stack uses. On this box, that means the Spark-specific FP8 quantization of `meta-llama/Llama-3.1-8B-Instruct` that [NIM serves on port 8000](/articles/nim-first-inference-dgx-spark/). That impulse runs into two problems and one small insight.

The first problem is that the FP8 base is not a training target. LoRA training wants bf16 or fp16 weights so the adapter matmuls land in a sane gradient regime. The on-disk safetensors for the NIM model are `F8_E4M3` with F32 scales — perfectly fine for inference, but you would need to dequantize to bf16 before you could attach a LoRA, and at that point you are training against a bf16 approximation that the serving stack will never actually see.

The second problem is gating. `meta-llama/Llama-3.1-8B-Instruct` in its raw bf16 form is behind Meta's license acceptance on Hugging Face. You can get it; it just takes five minutes of clicking through a form. Skipping that friction is appealing.

The small insight: *the article's thesis does not care what the base model is*. The point is whether 231 Q&A pairs can meaningfully change a small open model's behaviour on the Second Brain's own terrain. Qwen2.5-3B-Instruct is ungated, downloads in a minute, fits easily into unified memory alongside pgvector and the embedding NIM, and a rank-16 LoRA on it trains in the time it takes to refill a coffee mug. The small model is the better instrument for the question.

There is also a cleaner story at inference time. Serving a LoRA adapter on the *exact same FP8 weights that NIM ships* requires rebuilding either TRT-LLM with `--lora_plugin` or vLLM with `--enable-lora` on top of a ModelOpt-quantized base — both possible, both measurable, neither the point of a first fine-tuning article. Training against a clean bf16 Qwen and then attaching the adapter with one call to `PeftModel.from_pretrained(base, adapter)` keeps the experiment isolated. The serving-side multi-LoRA story is a deployment-stage article, not a fine-tuning one.

## Generating 275 Q&A pairs from your own prose

The corpus is the article. This is the Second Brain after all — the training data is the project's own accumulated writing, not a borrowed Stack Exchange dump. Eleven published articles, ~38,000 words, walking through every stage from the day-one DGX Spark setup to last session's NVFP4 engine build.

The generation pattern is simple and ran against the NIM 8B that was already up on port 8000:

```python
# generate_qa.py — abridged
for article in articles:
    for chunk in overlapping_chunks(article.body, 900, overlap=150):
        pairs = nim_json(prompt.format(title=article.title, passage=chunk, n=5))
        yield from validate(pairs)
```

The validation step turned out to matter more than the prompt. The first pass used a verbose prompt with example questions like *"What TTFT did NVFP4 achieve on the 8B benchmark?"* — meant as a style hint. NIM 8B promptly copied the examples verbatim and generated answers to them against articles that had nothing to do with NVFP4, producing hallucinated recalls ("0.5 seconds", "8 GiB", "--lora-enable") that would have poisoned the training set. Rewriting the prompt to use only abstract style guidance and adding hard anti-hallucination rules ("NEVER invent facts, numbers, flags, or commands not literally in the passage") plus a refusal filter at parse time ("if the answer contains any of these markers, drop it") was the fix. Temperature dropped from 0.6 to 0.25 for the regenerated set.

Yield: **275 Q&A pairs** from 11 articles, ~25 pairs per article on average, all grounded in real passages. Examples:

```json
{"question": "How many GiB of resident memory did TRT-LLM NVFP4 use?",
 "answer": "2.5 GiB",
 "source": "trtllm-and-triton-on-spark"}

{"question": "What is the steady-state sandbox tax on top of raw inference?",
 "answer": "~26 seconds",
 "source": "nemoclaw-vs-openclaw-dgx-spark"}

{"question": "How many documents per second are embedded through the Nemotron Retriever embedding NIM?",
 "answer": "99",
 "source": "pgvector-on-spark"}
```

Stratified split, seeded for reproducibility: 231 train, 44 eval, with each source article contributing 3-5 items to the held-out set. The training set and the eval set live under `articles/lora-on-your-own-qa-pairs/evidence/` alongside the `generate_qa.py` that built them.

## Sixty-nine seconds of training

The training stack is the NVIDIA `tritonserver:25.12-trtllm-python-py3` container that was already on disk from the previous article. It ships torch 2.9 (the NVIDIA preview build for Blackwell), transformers 4.56, peft 0.18, accelerate 1.12, datasets 3.1. No `pip install` required. Mount `/home/nvidia/lora-work` as `/work`, hand in the CUDA device, run `python3 train_lora.py`.

The LoRA config is unremarkable and that is the point:

```python
lora_cfg = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    bias="none",
)
```

Rank 16 across all the linear layers in both attention and MLP blocks. That is **29.93 million trainable parameters** on top of a **3.09 billion parameter** frozen base — 0.96% of the model, 120 MB on disk when saved out. Loss masking was manual: the system + user prompt get `-100` labels so only the assistant's answer tokens contribute to the loss. Three epochs of bf16 SFT with gradient checkpointing, batch 4, grad-accum 2, cosine schedule, peak lr 2e-4, seed 42.

I stopped the 8B NIM for the training run (freed ~10 GiB of unified memory) and left the 1B embedding NIM up. Headroom during training: ~20 GiB peak GPU memory.

Training run:

```
Loading checkpoint shards: 100% 2/2 [00:37<00:00, 18.5s/it]
trainable: 29.93M / total: 3.12B  (0.961%)
train=231  eval=44
{'loss': 5.49, 'epoch': 0.17}
{'loss': 2.76, 'epoch': 0.34}
...
{'eval_loss': 2.227, 'epoch': 1.0}
...
{'eval_loss': 2.073, 'epoch': 2.0}
...
{'eval_loss': 2.095, 'epoch': 3.0}
{'train_runtime': 69.25, 'train_samples_per_second': 10.008}
```

**Sixty-nine seconds of training.** Model load took longer than the training itself. Eval loss bottomed at epoch 2 (2.07) and rose a hair at epoch 3 (2.10) — the sort of gentle overfit you would tune away on a real production run but that is inside the noise for a 231-pair corpus. I kept epoch 3 weights for the benchmark. The full log is at [`evidence/train.log`](./evidence/train.log).

At this scale, the embarrassing truth is that *you can iterate on the prompt, the rank, the alpha, the layer targets, or the training data over lunch*. Fifteen full training runs in one hour. This is the regime the LoRA literature always promised but that gets buried under the tutorial-ecosystem emphasis on 70B base models and multi-GPU setups. On a 3B model on a personal rig, there is no reason not to sweep.

## The benchmark harness

The benchmark is straightforward: reload the base model once, generate greedy completions for all 44 held-out questions, then attach the adapter in place with `PeftModel.from_pretrained(base, "/work/adapter")` and generate again against the same prompts. Same system message, same chat template, same sampling settings (`do_sample=False`, `max_new_tokens=160`, pad on eos).

This is the "inference-side LoRA" pattern in its simplest form. The base weights stay in GPU memory; the adapter is 120 MB of deltas added on top, roughly 0.6 ms per forward pass of additional cost. In production you would swap multiple adapters into the same base via vLLM's `--enable-lora` flag or TRT-LLM's `lora_dir` argument — the same file format, served at scale — but for a benchmark the in-process attach is the cleanest truth. See [`evidence/bench.py`](./evidence/bench.py).

The grading was done by the NIM 8B that was already up (restarted after training). Each held-out pair got judged against its reference answer on a 0-5 scale, with 0 reserved for refusal/no-content, 1 for "wrong key fact", 3 for "directionally right but imprecise", and 5 for "correct and phrased in the right style". Parallelism was six concurrent judge calls; the whole eval pass ran in under a minute. The per-item verdicts live at [`evidence/graded.jsonl`](./evidence/graded.jsonl) and the summary at [`evidence/grade_summary.json`](./evidence/grade_summary.json).

## What the adapter actually learned

The score distribution tells the whole story:

```
                 0    1    2    3    4    5
BASE:           12   20    6    2    4    0
+ LoRA:          3   22    3    8    4    4
```

Base Qwen2.5-3B's mass lives in the lower bins. Twelve refusals (score 0), twenty confidently-wrong answers (score 1), and only four answers that were actually correct (score 4+). No score-5s at all, because Qwen2.5-3B's answering style — hedged, expansive, littered with "typically", "generally", "for more details refer to…" — never lines up with the terse reference style of the training data even when it happens to be right on the fact.

The adapter shifts the distribution upward. Refusals drop from 12 to 3. Directionally-correct answers (score ≥ 3) climb from 6 to 16 — more than doubling. The previously-empty score-5 band fills with four perfect hits. And the mean score climbs from 1.23 to 2.00 out of 5.

But look where the mass *stays*. The score-1 bin (confidently wrong) barely moves — 20 → 22. This is the honest failure mode of the adapter and it deserves its own paragraph.

### The honest failure mode: confident hallucination

Picked at random from the adapter predictions, against the reference answers:

```
Q: What is the port number of the `pgvector` container?
REF:     :5432
ADAPTER: 8000

Q: What is the size of the cached weights for the model at this precision?
REF:     8.5 GB
ADAPTER: 1.2 GB

Q: What is the value of NIM_GPU_MEM_FRACTION by default?
REF:     0.5
ADAPTER: 0.8

Q: What is the median wall time including retrieval for the 8B local NIM
   on the rerank-and-fusion chain?
REF:     2.0 seconds
ADAPTER: 120 ms
```

The pattern is sharp. The adapter has learned what a *typical answer in this project* looks like — a port number, a gigabyte count, a fraction, a millisecond figure. What it has not learned is the specific port, the specific gigabyte count, the specific fraction, the specific milliseconds. The training signal was not strong enough to memorize 275 discrete numeric values into 30 million parameters of adapter weight. And rightly so — that is not what low-rank adaptation is for.

The structure that *did* transfer is unmistakable. `8000` is a plausible port number because several articles mention `:8000` for NIM. `1.2 GB` is a plausible cached-weights figure because several articles discuss ~1-10 GB memory footprints. `0.8` is a plausible GPU memory fraction because fractional values are what that environment variable takes. `120 ms` is a plausible latency because milliseconds are the unit this project uses for per-request timings. The adapter did not memorize facts; it memorized *the shape of facts*. The reader brings the facts.

### The structure that did transfer

A different class of questions shows what the adapter genuinely learned:

```
Q: What is the size of the GPU used in the three arcs?
REF:     128 GB
BASE:    The article does not specify the exact size of the GPUs used
         in the three arcs of the NVIDIA DGX Spark project. For specific
         details about hardware configurations, including GPU size, one
         would need to refer directly to the technical documentation...
ADAPTER: 128 GB
```

That is the magic. The base model refused. The adapter produced the exact reference answer, verbatim. Judge score 0 → 5 on a single question. And this was not an overfit — this particular pair was in the held-out set, not the training set. The adapter *did* recover the specific memorable facts of the project on some questions, probably because `128 GB` (the unified-memory pool on the DGX Spark) is a proper-noun-grade constant that appeared many times across many training chunks.

Concepts that transferred cleanly:
- **Unit-of-measurement fluency.** Milliseconds for latency, GiB for memory, tok/s for throughput, never inches or kilojoules.
- **The project's vocabulary.** `NIM`, `NVFP4`, `pgvector`, `trtllm-serve`, `GB10`, `Blackwell`, `ModelOpt`. The base model gets these right sometimes; the adapter gets them right always, in the context they appear in the articles.
- **Tone.** Short, declarative, numerical-where-possible. No hedging, no meta-commentary about "this article", no "typically" or "generally".
- **The shape of an answer.** Questions about latency get ms answers; questions about commands get CLI strings; questions about why-decisions get reason clauses.

Concepts that did not transfer:
- **Specific numeric values.** 275 discrete facts is too many for a rank-16 adapter on 3B parameters to reliably memorize.
- **Non-obvious proper nouns.** The adapter sometimes swaps `NemoClaw` for `NeMo Guardrails`, `trtllm-serve` for `trtllm-cli` — adjacent, wrong.
- **Longer-form rationale.** The adapter's answers collapsed from 70 tokens to 9 — it has learned to *stop writing* when a terse answer is plausible, which is good for style and bad when the question actually wants a paragraph.

## Why this matters for the Second Brain

The Second Brain arc was built on RAG first. [`pgvector-on-spark`](/articles/pgvector-on-spark/) was the vector store; [`nemo-retriever-embeddings-local`](/articles/nemo-retriever-embeddings-local/) was the embedding surface; [`naive-rag-on-spark`](/articles/naive-rag-on-spark/) was the first end-to-end answer pipeline; [`rerank-fusion-retrieval-on-spark`](/articles/rerank-fusion-retrieval-on-spark/), [`bigger-generator-grounding-on-spark`](/articles/bigger-generator-grounding-on-spark/), and [`guardrails-on-the-retrieval-path`](/articles/guardrails-on-the-retrieval-path/) hardened it. That entire stack exists because *the facts live in the corpus*, and the job of retrieval is to put the right facts in front of the model at query time.

The LoRA experiment here confirms the design. A model trained on your Q&A pairs, without retrieval, will answer every question — and will be wrong about specifics roughly half the time. A model with the same weights but given the relevant article passage at retrieval time will not need to have memorized anything; the facts come in through the context window, and the model's job is to render them in voice. The adapter and RAG are not alternatives. They are complements.

Specifically:

- **Use RAG** to put the right facts in the prompt. This is where numeric accuracy lives.
- **Use LoRA** to teach the model to answer in your voice, commit to answers on your terrain, and use your project's vocabulary — so that even when RAG brings in a long passage, the generation that comes out reads like part of the project instead of like a StackOverflow answer someone pasted in.

In the earlier [bigger-generator-grounding-on-spark](/articles/bigger-generator-grounding-on-spark/) experiment, the surprise finding was that a 49B Nemotron fine-tuned for grounded QA *refused more* than the 8B baseline on perfect retrieval — 18.2% vs 9.1%. That refusal rate is the same behavioural signal measured here. Bigger-and-better-aligned models still hedge when asked about unfamiliar proper nouns. A LoRA on a *tiny* model, on your own prose, can collapse that behaviour far more dramatically than scaling up ever does — not because the small model suddenly knows more, but because it has been *invited into your domain*.

## Serving the adapter, briefly

The benchmark loads the adapter in-process with two lines:

```python
base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16,
                                            device_map="cuda:0")
adapted = PeftModel.from_pretrained(base, "/work/adapter")
```

That is enough for a single-tenant Second Brain: one user, one query at a time, an adapter that weighs 120 MB and attaches in about a second. A FastAPI wrapper around `adapted.generate(...)` is 40 lines. For a real personal rig, this is probably all you need.

For scale — multiple adapters per base, hot-swapping across concurrent requests, the production LoRA serving story — the path is vLLM's `--enable-lora` with a `--lora-modules` map, or TensorRT-LLM's `lora_dir` baked into the engine. Both accept the same Hugging Face adapter format this article produced. The `adapter_config.json` and the `adapter_model.safetensors` are portable. The file shape does not change whether you serve one user or a thousand; the serving stack does.

That is the deployment-stage article, not this one. What this one earns is the right statement of scope: on a personal DGX Spark, you can iterate on a LoRA adapter over lunch, attach it at inference time in a second, and see a measurable shift in model behaviour on your own terrain — without any of the multi-node complexity the LoRA literature is usually wrapped in.

## Reproducibility

Full artifact list under [`articles/lora-on-your-own-qa-pairs/evidence/`](./evidence/):

- `generate_qa.py` — the corpus generator against NIM 8B
- `qa-full.jsonl`, `qa-train.jsonl`, `qa-eval.jsonl` — 275 / 231 / 44 pairs, seed 1337
- `split.py` — stratified 85/15 split by source article
- `train_lora.py` — the training script, peft 0.18 + transformers 4.56
- `train.log` — 69-second run log, loss + eval curves
- `adapter_config.json` — the LoRA config (r=16, α=32, all linear targets)
- `bench.py` — base vs adapter generation, same greedy decode on both
- `preds_base.jsonl`, `preds_adapter.jsonl` — 44 side-by-side predictions
- `judge.py` — LLM-as-judge grading via NIM 8B, 6-way parallel
- `graded.jsonl` — per-item verdicts with rationales
- `grade_summary.json` — the aggregate table that drove this article

The `adapter_model.safetensors` (120 MB) is not committed; rebuild it from the JSONL and scripts if you want it. The whole loop, from blank directory to graded benchmark, runs in under 45 minutes on a DGX Spark with NIM 8B already up. Most of that is the 6 GB base-model download on first run.

The foundation for this article is the Second Brain RAG stack the earlier articles built, and the finding flows back into it: the adapter is a voice layer, not a knowledge layer, and it sits *behind* a retrieval chain that handles the facts. The next article in the arc picks up where this one ends — evaluating the full RAG+LoRA stack against held-out questions with a proper framework, not a one-off judge prompt.
