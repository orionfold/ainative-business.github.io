---
title: "Ragas, Reranked — What 44 Held-Out Questions Say About the Second Brain Stack"
date: 2026-04-23
author: Manav Sehgal
product: NeMo Evaluator
stage: observability
difficulty: intermediate
time_required: "~60 minutes end-to-end — 40 s to ingest the blog into pgvector, 2 min for retrieval, 4 min for generation across three 8B variants, 90 s for the LoRA variant, 9 min for grading"
hardware: "NVIDIA DGX Spark"
tags: [ragas, nemo-evaluator, evaluation, rag, retrieval, rerank, second-brain, observability, dgx-spark]
summary: "A Ragas-style harness written in 200 lines of stdlib Python, run locally on the DGX Spark, against four variants of the Second Brain RAG chain. Naive RAG scores 3.30 / 5. Rerank RAG scores 4.27. LoRA+RAG is a surprise — it does not beat naive. Retrieval is where the points come from."
signature: RagEvalCorrectness
also_stages: [inference, fine-tuning]
series: Second Brain
fieldkit_modules: [eval]
---

The previous article closed with a promise: the LoRA on 231 of my own Q&A pairs taught the model *voice, not facts* — and the fact layer was about to come back in the form of RAG. One article later, with a retrieval chain bolted on and four variants benchmarked against 44 held-out questions, the scoreboard is here and the sharper finding is not where I expected it.

On correctness scored 0–5 by a Llama 3.1 8B judge against the reference answers:

| variant (n=44) | judge mean 0–5 | ≥4 of 44 | =5 of 44 | refuses | P@3 chunk | P@3 slug | wall |
|---|---:|---:|---:|---:|---:|---:|---:|
| LoRA only (no RAG) | 1.70 | 9 | 3 | 0% | — | — | 0.44 s |
| Naive RAG (top-3 → NIM 8B) | 3.30 | 29 | 20 | 18% | 66% | 86% | 2.75 s |
| LoRA + RAG (top-3 → LoRA 3B) | 3.39 | 28 | 21 | 0% | 57% | 75% | 2.07 s |
| **Rerank RAG (RRF + rerank → NIM 8B)** | **4.27** | **39** | **25** | **0%** | **96%** | **98%** | 2.96 s |

The [previous article](/articles/lora-on-your-own-qa-pairs/) earned a 1.70 floor. Adding [naive RAG](/articles/naive-rag-on-spark/) lifted that to 3.30. Swapping naive for [RRF + NeMo Reranker](/articles/rerank-fusion-retrieval-on-spark/) — the same chain that was built but never yet *scored* — took it to 4.27 and eliminated refusals entirely. Combining LoRA with RAG was supposed to be the headline win. It was not. The LoRA's terse voice (mean 7 output tokens) clips answers before they can cite properly, and the 3B base under-reasons over context the 8B handles fluently. Voice and facts, it turns out, do not compose transparently just because you stack them.

The other finding, less loud but more load-bearing: retrieval quality predicts correctness almost perfectly. Naive precision@3 is 66%; rerank precision@3 is 96%. The judge-score gap of 3.30 → 4.27 is where that 30-point retrieval swing cashes out. Faithfulness and answer-relevance — the generation-side Ragas metrics — moved by less than 5 points between these two variants. If you are going to tune one knob on the Second Brain stack, it is not the generator. It is not the adapter. It is the ranker.

## Why this matters for the personal AI power user

The specific thing the DGX Spark makes possible here is not that you can run a RAG eval — that's table stakes now — but that you can run it **against a local judge for free, on a cron, forever**. The same NIM that answers is the same NIM that grades. Both sit on the same 128 GB of unified memory. The 44-question suite runs in about nine minutes end-to-end, across 176 judge calls (four variants × 44 × three metrics). On a cloud judge, that would be a small line item; stretched across a nightly schedule, across six months of experiments, the cost compounds and suddenly the budget is the bottleneck on iteration, not the code.

The second compounding effect is privacy. Our reference answers embed project-internal numbers — cold-start latencies, port configurations, names of tools in progress. Shipping the test set and generated answers to a third-party eval platform would be a slow accidental leak of the whole corpus. Keeping everything local means the scoreboard is a file on disk, not a row in someone else's database.

## Where Ragas and NeMo Evaluator sit in the stack

<figure class="fn-diagram" aria-label="RAG evaluation stack. Retrieval (pgvector + optional rerank) and generation (NIM 8B or LoRA'd 3B) produce a per-question record of (question, contexts, answer). The evaluator layer — Ragas, NeMo Evaluator, or a hand-rolled harness — consumes those records and scores them against reference answers and reference contexts, producing correctness, faithfulness, answer relevance, and retrieval precision/recall metrics.">
  <svg viewBox="0 0 900 260" role="img" aria-label="Four-stage pipeline: retrieval → generation → evaluation → scoreboard. Evaluation layer fans out into retrieval metrics, generation metrics, and correctness. A dashed cron arrow loops evaluation back to retrieval, indicating nightly drift detection." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="re-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-green)" stop-opacity="0.02"/>
        <stop offset="50%" stop-color="var(--svg-accent-green)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-green)" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    <rect x="60" y="20" width="780" height="220" rx="10" fill="url(#re-band)" stroke="none"/>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="80" y="60" width="160" height="64" rx="8"/>
      <rect class="fn-diagram__node" x="280" y="60" width="160" height="64" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="480" y="60" width="160" height="64" rx="8"/>
      <rect class="fn-diagram__node" x="680" y="60" width="160" height="64" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="480" y="160" width="160" height="48" rx="8"/>
    </g>
    <g class="fn-diagram__edges">
      <line x1="240" y1="92" x2="280" y2="92"/>
      <line x1="440" y1="92" x2="480" y2="92"/>
      <line x1="640" y1="92" x2="680" y2="92"/>
      <line x1="560" y1="124" x2="560" y2="160" stroke-dasharray="3 3"/>
    </g>
    <g font-family="var(--font-mono)" font-size="11" fill="var(--svg-text-muted)" text-anchor="middle">
      <text x="160" y="88" font-weight="600">RETRIEVAL</text>
      <text x="160" y="108" font-size="8" fill="var(--svg-text-faint)">pgvector · rerank</text>
      <text x="360" y="88" font-weight="600">GENERATION</text>
      <text x="360" y="108" font-size="8" fill="var(--svg-text-faint)">nim 8b · lora 3b</text>
      <text x="560" y="88" font-weight="700" fill="var(--svg-accent-green)">EVALUATION</text>
      <text x="560" y="108" font-size="8" fill="var(--svg-text-faint)">ragas · judge</text>
      <text x="760" y="88" font-weight="600">SCOREBOARD</text>
      <text x="760" y="108" font-size="8" fill="var(--svg-text-faint)">summary.json · db</text>
      <text x="560" y="184" font-weight="600" fill="var(--svg-text-faint)">CRON · NIGHTLY DRIFT</text>
      <text x="560" y="200" font-size="8" fill="var(--svg-text-faint)">nemo evaluator runs the loop</text>
    </g>
  </svg>
  <figcaption>Ragas is a set of metric definitions — context precision/recall, faithfulness, answer relevance — originally published as a Python library but equally expressible as 200 lines of stdlib. NeMo Evaluator is what you graduate to when the eval lives in production: it takes the same metrics, wraps them in a workflow service, and runs them on a schedule with durable storage. The evaluator sits on the same Spark as the rest of the chain.</figcaption>
</figure>

The library-versus-spec distinction matters here. The Ragas *library* imports LangChain and OpenAI by default, which are neither necessary nor appropriate when the goal is to score a local NIM against a local judge. The Ragas *spec* — the four metric families, their prompts, and the claim-decomposition method — is what you actually want, and it fits comfortably in a single Python file. NeMo Evaluator is the enterprise shape of the same idea: the metrics are the metrics, but the harness is durable, scheduled, and multi-tenant.

## The experiment — one table, four variants, shared test set

The [LoRA article](/articles/lora-on-your-own-qa-pairs/) shipped a 275-pair Q&A corpus with a 44-pair held-out eval split. Every pair carries `{question, answer, source (slug), chunk (index)}` — the source slug is an article folder under `articles/`, and `chunk` is the 0-indexed 900-word window inside that article's markdown body. That's exactly the ground-truth retrieval target for this experiment: a question is "retrieved correctly" if the top-K results include the `(slug, chunk)` tuple the question was generated from.

### Ingest — 12 articles → 61 blog_chunks

[`evidence/ingest_blog.py`](./evidence/ingest_blog.py) reproduces the S2 chunker (900 words, 150-word overlap) and writes everything into a new `blog_chunks` table in pgvector, sibling to the AG-News `chunks` table the earlier [naive RAG](/articles/naive-rag-on-spark/) and [rerank-fusion](/articles/rerank-fusion-retrieval-on-spark/) articles built against. Embedding happens in batches of 16 through the local Nemotron-Embed-1B NIM:

```
creating table…
chunks: 61 across 12 articles
  embedded 16/61
  embedded 32/61
  embedded 48/61
  embedded 61/61
loading…
creating indexes…
done in 37.3s
```

Thirty-seven seconds to stand up a query-ready, HNSW-indexed, FTS-indexed vector table over my own blog. The same corpus on a cloud embedding API would be cheap but not *free*, and the latency would be network-bound. Here it is disk-bound.

### Retrieval — naive top-5 and RRF + rerank top-5

[`evidence/retrieve.py`](./evidence/retrieve.py) walks the 44 held-out questions and runs two retrieval modes per question: a plain cosine top-20 that feeds both the naive top-5 (the first five rows) and the rerank top-5 (the hosted [Nemotron-reranker](/articles/rerank-fusion-retrieval-on-spark/) reordering the twenty and keeping the top five). The reranker is the only hosted dependency in the chain — at the time of writing it does not yet ship as a Spark-runnable NIM. Everything else is on the box.

Retrieval precision at K, measured as "did the top-K passages include the question's ground-truth `(slug, chunk)`", is the first number the scoreboard reports. On the 44-pair set:

| retriever | chunk@3 | chunk@5 | slug@3 | slug@5 | rank when hit |
|---|---:|---:|---:|---:|---:|
| Naive (cosine top-5) | 0.66 | 0.75 | 0.86 | 0.89 | 1.1 |
| RRF + rerank top-5 | **0.96** | **0.96** | **0.98** | **0.98** | **0.24** |

Rerank doesn't just find the gold chunk more often — it puts it in slot zero almost every time. Mean gold rank (0-indexed) drops from 1.1 under naive to 0.24 under rerank. The reranker is doing the work a larger generator can't do alone: separating *relevant* from *adjacent* among passages that all share vocabulary.

### Generation — three 8B variants + one LoRA variant

Four variants, all generating against the same retrieved context (top-3 passages, capped to leave headroom in the 8192-token context window):

1. **`lora_only`** — Qwen-2.5-3B-Instruct + the 120 MB rank-16 LoRA from S2, no retrieval. Replayed from the [S2 eval run](/articles/lora-on-your-own-qa-pairs/), not re-generated.
2. **`naive_8b`** — [`evidence/generate_nim.py`](./evidence/generate_nim.py) — NIM Llama 3.1 8B, strict-context system prompt, naive top-3.
3. **`rerank_8b`** — same generator as `naive_8b`, rerank top-3.
4. **`rag_lora`** — [`evidence/lora_rag_bench.py`](./evidence/lora_rag_bench.py), run inside the Triton 25.12 container — Qwen-2.5-3B + LoRA adapter, naive top-3 context glued into the prompt.

The 8B variants together run in about four minutes. The LoRA variant is faster (2 s per question including load-amortized forward pass) but produces mean 7 output tokens — the adapter is so committed to its terse voice that it emits atoms like *"1000 headlines"* or *"trtllm-serve"* even when the question wants a sentence.

### Grading — 176 rows, three judge calls each

[`evidence/grade.py`](./evidence/grade.py) runs three NIM-as-judge calls per prediction:

- **Correctness (0–5)**, scored against the reference answer using the same rubric as [the S2 judge](/articles/lora-on-your-own-qa-pairs/).
- **Faithfulness (0–1)**, scored against the retrieved context: is every factual claim in the answer supported?
- **Answer relevance (0–1)**, scored against the question only: does the answer address the question?

That's 132 context-aware judge calls and 176 reference-based ones, plus 88 relevance calls — 396 NIM-8B completions. The whole grader finished in about nine minutes of wall clock, no batching, no concurrency. On a cloud judge, the same workload would be maybe $0.20 per run, which is fine for one shot and painful in a nightly schedule.

## What the scoreboard says

The `correctness` histogram, per variant, is more informative than the mean. It shows the *shape* of failure:

```
lora_only     │ 0: ███  1: ██████████████████████████████  2: ·  3: ██  4: ██████  5: ███
naive_8b      │ 0: ███████  1: ███████  2: █  3: ·  4: █████████  5: ████████████████████
rag_lora      │ 0: ██  1: █████████████  2: ·  3: █  4: ███████  5: █████████████████████
rerank_8b     │ 0: ·  1: ████  2: ·  3: █  4: ██████████████  5: █████████████████████████
```

- **LoRA-only** is bimodal: 9 of 44 questions hit ≥4 (the voice adapter got them right on recall), and 30 of 44 clustered at score 1 (confidently wrong). This is the S2 finding as a picture.
- **Naive RAG** has a floor problem: 14 of 44 sit at 0–1. Seven of those are the refusals — the NIM correctly saying *"the provided context does not contain the answer"* when naive retrieval missed the gold chunk. Seven more are wrong-context hallucinations, where retrieval returned adjacent passages from the same article and the NIM confabulated plausibly from them. The variant is right 45% of the time and correct or nearly-so 66% of the time.
- **LoRA + RAG** has the same histogram shape as naive 8B but shifted terser. Its 13 score-1 answers are mostly a single atomic fact emitted against retrieval that didn't support it — the LoRA-trained terseness means the adapter is committing faster than the evidence supports. It has the highest "score-5" count tied with naive (21 vs 20) but a much worse score-1 bin.
- **Rerank RAG** has essentially no failure floor. Zero refusals, four score-1s, and **25 of 44 questions perfect**. The 4-point bin swells to fourteen from naive's nine. This is what near-perfect retrieval plus a competent 8B generator looks like.

### Faithfulness is a weak proxy for correctness

One of the reasons the Ragas paper is interesting is that it introduces faithfulness as a generation-side metric that doesn't require a reference answer — claim-decompose the generated answer, then check each claim against the retrieved context. In principle this lets you grade a RAG pipeline in production where you don't have gold labels. In our data, against a NIM-8B judge:

| variant | faithfulness mean | corr(faithfulness, correctness) |
|---|---:|---:|
| naive_8b | 0.432 | 0.44 |
| rerank_8b | 0.477 | 0.15 |
| rag_lora | 0.314 | 0.10 |

Pearson correlation between per-question faithfulness and per-question correctness collapses as the pipeline improves. On the naive variant, a faithful answer is 0.44 correlated with a correct one — you can sort by faithfulness and see something. On the rerank variant, where retrieval is nearly perfect, faithfulness barely tracks correctness at all: the judge is splitting hairs on citation style. On the LoRA variant, the terse atoms don't decompose cleanly into claims, so the metric is mostly noise.

The takeaway is not that faithfulness is broken — it's that *no single Ragas metric is enough*. Correctness against references tells you how right the answer is; retrieval P@K tells you whether the facts were available; faithfulness tells you whether the answer stayed honest about what it had. You want all three, and the ratio they sit in tells you which knob to turn.

### Six always-pass, three always-fail

Across all four variants, six of the 44 questions scored ≥4 in every variant — these are the easy ones, phrased verbatim against a short passage, answerable by any path. Three scored ≤1 in every variant — the floor of this corpus. All three are questions where the reference answer is a multi-line literal command that no variant reproduces exactly. The judge is harsh on whitespace mismatches. That is a known Ragas-style failure mode and is the reason real evaluators use a longer rubric with wording leniency per answer type.

## Gotchas and honest caveats

**The judge and the generator are the same model.** Every Ragas-style number in this article was produced by NIM Llama 3.1 8B grading its own outputs (for the two 8B variants) alongside the LoRA-3B's outputs. That is a known weak point of local-judge setups: the judge inherits the generator's biases. In production you use a larger, differently-trained judge (NeMo Evaluator's default reference is Llama 3.3 70B; Ragas defaults to GPT-4). On the Spark, a 49B Nemotron-Super NIM — the [same one](/articles/bigger-generator-grounding-on-spark/) we A/B'd as a generator — is the right judge for nightly runs. This article used the 8B for speed and honesty; the correlations would shift a little under a 49B judge, not the top-line ranking.

**Ragas-the-library imports LangChain.** Do not install it. The Ragas *spec* — context precision, context recall, faithfulness, answer relevance, the prompts and rubrics — is what you want. Two hundred lines of stdlib plus one POST-per-metric is enough for every experiment this article runs, and it keeps the Spark's dependency surface clean. The moment you want durable storage, drift detection, and a cron, graduate to NeMo Evaluator directly — don't pass through the Python library as a stepping stone.

**The rerank tax is almost zero.** Naive 8B was 2.75 s end-to-end per question; rerank 8B was 2.96 s. That 210 ms is one POST to the hosted reranker with 20 passages. When the reranker ships as a Spark-runnable NIM — the [F5 article](/articles/rerank-fusion-retrieval-on-spark/) flagged the compat gap — that 210 ms will drop to sub-50 ms and rerank will be strictly dominant. There is no RAG configuration where you would keep naive cosine after rerank lands locally.

**LoRA + RAG needs a second LoRA.** The biggest surprise is that rag_lora essentially tied naive_8b on correctness (3.39 vs 3.30) — adding the 120 MB adapter bought almost nothing. The adapter was trained on context-free Q&A pairs, so it learned to commit to terse atomic answers without grounding in retrieved passages. Making LoRA+RAG work well would mean training a *second* LoRA on (question, context, answer) triples — teaching the adapter how to *use* retrieved evidence, not just how to sound right. That's a natural next experiment for the fine-tuning arc.

**Three questions no variant can answer** is a signal about the test set, not the pipelines. The question-generator was too strict on "paraphrase the passage exactly" and sometimes produced references that are a literal command block. Future test-set generation should mark answer types (numeric, atomic-string, command, paraphrase) so the judge can apply type-aware leniency.

## What this unlocks — the nightly ratchet

Three concrete things the reader can build this week with what they just learned.

**Nightly drift detector.** Schedule the whole pipeline — retrieve, generate, grade — on a cron. Each morning, a one-line diff of `summary.json` vs yesterday's tells you if any knob moved correctness. The data has to live somewhere durable (Postgres, not JSONL in a temp dir), and the run has to survive across reboots, which is exactly what NeMo Evaluator does. [`evidence/nemo_evaluator_config.yaml`](./evidence/nemo_evaluator_config.yaml) is a starting config for the service, pointed at this same 44-pair dataset and three variants.

**Retrieval-knob sweep.** With a 9-minute grader, you can sweep every retrieval parameter that touches quality — top-K from 1 to 20, rerank on/off, chunk-size 500 vs 900 vs 1200, embed-dim 768 vs 1024 — and have all 96 runs grade overnight. On a cloud judge that sweep is a budget conversation; on the Spark it is a shell loop.

**Judge-swap experiment.** Rerun the same 44 predictions through a 49B Nemotron-Super judge and through a 70B Llama-3.3 judge. Inter-judge correlation tells you whether your 8B-graded scoreboard is drifting from what a larger critic would see. The moment the correlation dips below ~0.8 is the moment you know your nightly ratchet needs a bigger judge — and the 128 GB of unified memory means you can keep both judges resident, swap them in on demand, and never leave the box.

## The Second Brain, scored

The Second Brain stack now has a brain (the NIM), memory (pgvector), sharper memory (the reranker), a voice (the LoRA), and — as of this article — a scoreboard. The one remaining piece is a surface: something that lets a user or a downstream agent ask the Second Brain a question without knowing which of these variants to call. That's the MCP article — `mcp-second-brain-in-claude-code` — where the whole stack gets wrapped as a [Model Context Protocol](https://modelcontextprotocol.io/) tool and plugged into Claude Code itself.

The finding that actually ships out of this article, though, is the one that should govern every subsequent tuning decision: **on a 44-question, 12-article corpus, retrieval quality alone explains more of the judge-score variance than every other knob in the pipeline combined**. If you have one day of wall-clock to spend improving a RAG stack on a DGX Spark, spend it on the ranker. Everything else is a rounding error until the ranker is near-perfect, at which point the gains move to context size, then generator size, then fine-tuning. The ordering matters. It is not the order the NVIDIA stack's marketing emphasizes. It is the order 176 local NIM judgments agree on.

Next up: **MCP surface for the Second Brain** — wrapping retrieve/rerank/generate/grade as a tool Claude Code can call, so every coding session has the blog as a grounded retriever one `@` away.
