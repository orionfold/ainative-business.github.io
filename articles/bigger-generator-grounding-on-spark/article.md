---
title: "Bigger Generator, Same Grounding — 8B vs 49B vs 70B on One Retrieval Chain"
date: 2026-04-22
author: Manav Sehgal
product: Llama 3.3 70B + Nemotron-Super-49B + Llama 3.1 8B NIM
stage: inference
difficulty: intermediate
time_required: "~30 minutes on top of the rerank-and-fusion chain"
hardware: "NVIDIA DGX Spark"
tags: [rag, grounding, refusal, nemotron, llama, generator, scale, dgx-spark]
summary: "The rerank-and-fusion article bet that a bigger generator would heal the 8B Google-IPO refusal. Ran the A/B across three sizes on one retrieval chain. Bet lost: Nemotron-Super-49B over-refuses the 8B baseline; Llama 3.3 70B narrows the gap, not closes it. The refusal was the scaffold working."
signature: GeneratorUpgrade
series: Foundations
fieldkit_modules: [rag]
---

The [rerank-and-fusion article](/articles/rerank-fusion-retrieval-on-spark/) ended with a bet. Four retrieval configurations had fed perfect chunks to the 8B generator on *"Did Google have an IPO in 2004?"* All four got back *"The provided context does not contain the answer."* The retrieval had the right facts at rank 1. The grounding didn't commit. The closing line queued the obvious fix: swap the 8B for Llama 3.3 70B or Nemotron-Super-49B and measure whether the bigger model's grounding circuit answers where the smaller one refused.

This article ran that experiment across three generator sizes — the existing 8B-local NIM from the [first NIM article](/articles/nim-first-inference-dgx-spark/), Nemotron-Super-49B served from `integrate.api.nvidia.com`, and Llama 3.3 70B from the same hosted endpoint — on the same thirty-query qrels set, the same rerank retrieval chain, the same strict-context scaffold. Ninety LLM calls. One retrieval pipeline held constant. The bet lost. The 49B refuses *more* than the 8B on perfect-retrieval queries (18.2% vs. 9.1%). The 70B narrows the refusal gap a little, not a lot, and pays 2× to 12× latency for the privilege. And re-inspecting the IPO chunks shows why — the passages discuss the IPO but don't state the year 2004 anywhere. The 8B refusal the [naive RAG article](/articles/naive-rag-on-spark/) framed as a bruise was the scaffold doing its job, and three generators across a ten-times parameter range agree.

## The thesis in one glance

<figure class="fn-diagram" aria-label="Refusal rates across three generators on the thirty-query rerank benchmark. Llama 3.1 8B local refuses on 9.1% of perfect-retrieval queries. Nemotron-Super-49B hosted refuses on 18.2% — twice the 8B baseline, despite being the NVIDIA-native model tuned for grounded QA. Llama 3.3 70B hosted refuses on 13.6% — between 8B and 49B, not better than the smallest model. Bigger does not heal refusal on this scaffold.">
  <svg viewBox="0 0 900 380" role="img" aria-label="Refusal rate across three generators on the 30-query qrels set: 8B at 9.1% on perfect retrieval, 49B at 18.2%, 70B at 13.6%" preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d06-lane-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
        <stop offset="50%"  stop-color="var(--svg-accent-teal)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d06-49b-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d06-49b-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="40" y="60" width="820" height="150" rx="8" fill="url(#d06-lane-grad)" stroke="none"/>
    <rect x="340" y="90" width="220" height="100" rx="10" fill="url(#d06-49b-halo)" stroke="none"/>
    <g class="fn-diagram__scale">
      <line x1="60" y1="195" x2="840" y2="195" class="fn-diagram__axis"/>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="160" y="214" text-anchor="middle">9.1%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="214" text-anchor="middle">18.2%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="730" y="214" text-anchor="middle">13.6%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="840" y="214" text-anchor="end">refusal | recall@5 = 1.0</text>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60"  y="140" width="200" height="50" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="340" y="90" width="220" height="100" rx="10" style="fill: url(#d06-49b-grad)"/>
      <rect class="fn-diagram__node" x="620" y="120" width="200" height="70" rx="8"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="160" y="162" text-anchor="middle">LLAMA 3.1 8B</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="160" y="182" text-anchor="middle">9.1%</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="450" y="118" text-anchor="middle">NEMOTRON-SUPER 49B</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="450" y="142" text-anchor="middle">18.2%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="162" text-anchor="middle">2× the 8B baseline</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="178" text-anchor="middle">NVIDIA-tuned for grounding</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="720" y="142" text-anchor="middle">LLAMA 3.3 70B</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="720" y="168" text-anchor="middle">13.6%</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="60"  y="90" text-anchor="start">baseline — same as naive-rag / rerank-fusion</text>
      <text class="fn-diagram__label fn-diagram__label--accent fn-diagram__label--mono" x="360" y="60" text-anchor="start">THE SURPRISE</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="360" y="80" text-anchor="start">tuned for careful answering; refuses more</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="620" y="102" text-anchor="start">generic 70B — narrows gap, not closes it</text>
    </g>
    <g class="fn-diagram__caption">
      <text class="fn-diagram__label fn-diagram__label--display" x="60" y="295" text-anchor="start">Refusal doesn't scale away</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="60" y="318" text-anchor="start">Thirty hand-labelled queries · rerank top-5 · strict-context scaffold</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="60" y="336" text-anchor="start">Overall refusal rate: 8B 10.0%, 49B 20.0%, 70B 13.8%</text>
    </g>
  </svg>
</figure>

The headline finding is the amber node in the middle. Nemotron-Super-49B is the NVIDIA-native, post-trained-for-instruction-following, designed-to-be-careful flagship. It refused on eighteen out of every hundred perfect-retrieval queries — twice the 8B baseline, and more than the larger 70B. The 70B improves slightly on the 49B but not on the 8B. The size dial doesn't have the knob the rerank-and-fusion article assumed it had.

## The setup — only the generator changed

The [rerank-and-fusion article's](/articles/rerank-fusion-retrieval-on-spark/) retrieval chain is held constant: the query is embedded with Nemotron Retriever, the dense and BM25 top-20s are fused via RRF, and the hosted Nemotron Reranker returns the top-5 logit-ranked chunks. That top-5 is the input to all three generators, unchanged. The same strict-context scaffold from the [naive RAG article](/articles/naive-rag-on-spark/) is the system message: *answer only from the passages, cite row ids, and if the answer isn't there, reply with one exact sentence*.

The three generators are:

- **Llama 3.1 8B Instruct**, served locally on the Spark via NIM on port 8000. The baseline carried from the [first NIM](/articles/nim-first-inference-dgx-spark/) through the [rerank-and-fusion](/articles/rerank-fusion-retrieval-on-spark/) articles.
- **Nemotron-Super-49B v1 Instruct**, served from `integrate.api.nvidia.com` with the same NGC API key used by the hosted reranker. The NIM image exists on NGC (`nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1:latest`) but has no `-dgx-spark` tag; the reranker compat gap from the [rerank-and-fusion article](/articles/rerank-fusion-retrieval-on-spark/) set the precedent, so hosted is the first-line path.
- **Llama 3.3 70B Instruct**, also from `integrate.api.nvidia.com`. No `-dgx-spark` variant exists on NGC as of this session; the local pull is ~40 GB and sits right on the line of GB10's unified-memory budget. A failed local experiment earlier in the day hard-hung the box, so the hosted endpoint was the disciplined choice.

The local 49B NIM was *pulled* to disk — the 23 GB image now lives at `nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1:latest` — but deliberately not *started*. The hosted A/B answered the article's question before the local start-up mattered, and starting a 49B on a box that had OOM'd two hours earlier had no editorial upside for a finding that was already clear.

The harness is a single flag on the [rerank-and-fusion article's](/articles/rerank-fusion-retrieval-on-spark/) script. `hybrid_ask.py --generator {llama31-8b, nemotron-super-49b-hosted, llama33-70b-hosted}` dispatches to the correct URL; the scaffold, prompt, and retrieval code are untouched. The benchmark loops over the qrels × three generators and writes `benchmark.json` with per-query answers, refusal booleans, and latencies.

## The numbers, across all thirty queries

| generator | recall@5 | recall@10 | refusal_all | refusal_on_perfect_retrieval | median ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| llama31-8b (local)            | 0.918 | 0.968 | 10.0% | **9.1%**  | 2,040 | 2,819 |
| nemotron-super-49b (hosted)   | 0.918 | 0.968 | 20.0% | **18.2%** | 2,556 | 7,723 |
| llama33-70b (hosted)          | 0.893 | 0.935 | 13.8% | 13.6% | 4,113 | 24,223 |

The recall numbers are identical between the 8B and 49B rows because the *retrieval* didn't change — same rerank, same top-5. The 70B row's slightly lower recall is a measurement artefact: query q30 returned an HTTP 429 from the hosted endpoint (rate limit) and its row was recorded as an error with a null retrieved-ids field, which pulled the mean down by one query. The latency column makes the practical argument: the 8B local NIM is fastest by every percentile, and the 70B hosted paid a 24-second p95 that the editorial voice won't pretend is acceptable for a chat-class RAG system.

The refusal columns carry the article. The overall refusal rate across all thirty queries is 10.0%, 20.0%, 13.8% — the 49B outputs *"The provided context does not contain the answer"* (or close variants) on six queries out of thirty, the 8B on three. Filtering to the queries where retrieval was perfect (recall@5 = 1.0, which is twenty-two of the thirty) the 8B refuses twice, the 49B four times, the 70B three times. In both cuts, the NVIDIA-native flagship over-refuses the baseline.

## Four queries where the generators disagreed

Twenty-four of the thirty queries produced the same verdict from all three generators — answer, cited, move on. The other six are the article.

**q01 — *"Did Google have an IPO in 2004?"*** — all three refused. The rerank returned the same five top chunks each time, including `[1151] "Google Could Make Market Debut Wednesday"`, which opens *"NEW YORK/SAN FRANCISCO (Reuters) - Google Inc. appeared set to start trading on Nasdaq on Wednesday."* The other four chunks all contain the phrase "Google IPO" in the first line. None of them contains the string "2004". Three generators across a ten-times parameter range agreed: under strict context, they cannot assert the year. The [naive RAG article](/articles/naive-rag-on-spark/) framed this as a *grounding bruise*. Looking at the chunks now, that frame was wrong. The refusal is the scaffold doing its job — the model can confirm that Google had an IPO and that it was happening during the trading week of those articles, but cannot assert the calendar year without seeing it. A model that invents the year from world knowledge would be hallucinating by the strict-context rules we set.

**q06 — *"What was Nortel's Canadian accounting probe about?"*** — 8B answered crisply: *"The Royal Canadian Mounted Police told Nortel that it will begin a criminal investigation into Nortel's financial accounting. Sources: [1179]."* The 49B and 70B both refused. The retrieval was identical — all three saw the same top-5. The 8B picked up the one sentence in chunk [1179] that named the agency and the act and committed to that answer. The larger generators saw the same sentence and declined to commit. This is the first place the editorial frame shifts: the smaller model was more useful, on this query, on this corpus, under this scaffold.

**q10 — *"How did Tiger Woods finish the 2004 PGA Championship?"*** — same pattern. 8B: *"Tiger Woods finished with a three-under-par 69. Sources: [457]."* 49B and 70B: refused. Chunk 457 literally contains the stroke and round information. Under the strict scaffold, both larger models saw material that says "Tiger Woods … three-under-par 69" and chose not to commit, presumably because the chunk doesn't say "final round" or "tournament total" explicitly enough for their taste. The 8B committed. The 8B was right.

**q15 — *"PeopleSoft Oracle antitrust trial"*** — 70B answered with a summary of the takeover bid and trial status; 49B and 8B refused. This is the single query where a bigger generator healed an 8B refusal. The 49B produced an interesting artefact: its refusal was formatted with its own internal structure — *"**Question:** PeopleSoft Oracle antitrust trial **Answer:** The provided context does not contain the answer. **Reason:** ..."* — which is more verbose than the scaffold asked for. Nemotron-Super's reasoning-focused post-training sometimes ignores a "reply with exactly one sentence" instruction, which is relevant for any downstream pipeline that's parsing refusals programmatically.

**q27 — *"Oil prices hit record high above 47"*** — 8B and 70B answered (*"Oil prices hit a record high near $47. Sources: [762], [731], [732]"* from the 70B); 49B refused. Retrieval here was imperfect — recall@5 was 0.50 — but the chunks in the top-5 still contained the headline fact. The 49B over-refused; the 70B and 8B both committed correctly.

**q29 — *"Phelps first gold medal Athens 400 individual medley"*** — all three refused with partial retrieval (recall@5 = 0.50). The scaffold did its job.

## Why Nemotron-Super-49B over-refuses

Nemotron-Super is NVIDIA's instruction-tuned flagship in the mid-size tier. Its post-training emphasises careful reasoning and grounded answers — by design it is meant to be *more* trustworthy on RAG-style questions, not less. So why does it refuse more?

The q06 and q10 answers suggest the mechanism. The 8B, on a top-5 that contains a headline-level sentence stating the fact, stops reasoning and emits the fact with a citation. The 49B appears to reason longer, note that the chunk doesn't contain an *explicit statement of the exact claim* the user is asking for (a tournament total vs. a round score; a one-sentence agency summary vs. a full description of what the investigation covered), and refuse. The instruction-following layer is doing what RLHF asked it to do — err on the side of caution — and the strict-context scaffold amplifies that caution into a false-refusal circuit that the smaller, cruder 8B doesn't have.

This is not a bug in Nemotron-Super. It is the model working exactly as trained. The training objective — precision over recall on grounded assertions — produces exactly this behaviour on queries where the top chunk is *adjacent* to the question but not a verbatim restatement of it. The scaffold in the [naive RAG](/articles/naive-rag-on-spark/) and [rerank-and-fusion](/articles/rerank-fusion-retrieval-on-spark/) articles was calibrated for the 8B's looser grounding circuit. The 49B deserves its own scaffold — one that explicitly tells it *"quotable partial answers count; refuse only on absence"* — before a fair size comparison is possible.

And that is the article's real finding. The generator-size dial is not a grounding dial. It is a precision-vs-recall dial on the refusal circuit, and the direction is tunable by post-training, not by parameter count.

## The Google IPO chunks, finally read in full

The [naive RAG article's](/articles/naive-rag-on-spark/) hero moment deserves its own re-read, because the framing changes. Here is the opening line of each of the five top-ranked chunks the reranker fed for q01:

- `[13]  "Google IPO Auction Off to Rocky Start  WASHINGTON/NEW YORK (Reuters)..."`
- `[36]  "Google IPO: Type in 'confusing,' 'secrecy' I've submitted my bid..."`
- `[71]  "Play Boys: Google IPO a Go Anyway..."`
- `[1091] "Google Could Make Its Market Debut Wed.  NEW YORK/SAN FRANCISCO (Reuters)..."`
- `[1151] "Google Could Make Market Debut Wednesday  NEW YORK/SAN FRANCISCO (Reuters)..."`

None of them contains the digit string *2004*. The AG News dataset was published without year metadata in the body text — the articles are dated contemporaneously, but the passages themselves discuss a Wednesday IPO without naming the calendar year. A generator that answers *"Yes, in 2004"* from these passages is importing world knowledge. A generator that refuses is following the strict-context scaffold.

The [naive RAG article's](/articles/naive-rag-on-spark/) narrative framed the 8B refusal as a failure. From this angle it reads the other way — the 8B, 49B and 70B all did the right thing. The fix is not a bigger generator; it is either richer chunks (AG News with a year-tagged front matter, say) or a weaker scaffold (permission to cite world knowledge when the context is compatible). A separate article will pick one of those levers; the finding here is that *scaling the generator* is not a lever.

## Latency and cost economics

The 8B local NIM runs on the GB10 on port 8000 with 120-second timeouts that the benchmark rarely touches. Median wall time including retrieval was 2.0 seconds on the [rerank-and-fusion article's](/articles/rerank-fusion-retrieval-on-spark/) rerank mode, and the distribution is tight — the p95 is 2.8 seconds. The hosted 49B is within 500 ms of the local 8B on the median but has a much heavier tail, p95 of 7.7 seconds. The hosted 70B paid a 4.1-second median and a 24-second p95, and hit one 429 rate-limit error in the thirty-query run. At Second-Brain-chat cadence (a query every few seconds during active thinking) the 70B's p95 and rate limits are disqualifying; the 49B is marginal; the 8B is the only one that comfortably fits.

Token counts matter too. The 8B local NIM bills zero; the hosted endpoints are metered. For 30 rerank queries with ~1000-token top-5 contexts and 20-token answers, the hosted calls consume a few hundred thousand prompt tokens and a few thousand completion tokens — small enough to ignore for one experiment, meaningful at production cadence.

## What the three arcs got

**Second Brain.** Stay on the 8B. It's local, cheap, fast, and it answers queries that the 49B refuses. The grounding gap isn't a model-size problem on a personal corpus; it's a retrieval-quality and chunk-construction problem. If the 8B refuses on a question where the chunk is clearly relevant, the right lever is *better chunking* (include more of the source article, or add explicit metadata like dates and author) or *a scaffold change* (soften the strict-context rule to allow "partial evidence" answers). The signature is that the 8B is the Pareto-optimal generator for a second brain on the Spark today.

**LLM Wiki.** Same story, plus a read-model option: the 70B hosted is a useful *author-time* tool — for pre-writing summaries when a human is in the loop to catch the rare refusal — but the *read-time* generator should stay 8B local for latency. A wiki's reader expects a second-scale response; a 24-second p95 is not that.

**Autoresearch.** The critic-layer article (A6 in the arc plan) assumed a 70B critic on the Spark. Today's finding changes the scope of that piece — the critic won't heal a driver's refusal just by being bigger. The autoresearch loop needs a different primitive: a *retry with retrieval perturbation* (slightly different query wording, chunk widening) or a *scaffold softener*, not a parameter-count upgrade. A6's story is now *"why bigger didn't heal, and what we tried next,"* not *"70B critic catches what 8B driver missed."*

## Closing — distillation, not scaling

Three generators across a ten-times parameter range agree on the hard queries. The 49B over-refuses; the 70B pays 2× to 12× latency for modest gains; the 8B is the best answer today for a local stack. The editorial thesis of "bigger generator closes the grounding gap" held exactly as long as it took to measure it.

The next move is **fine-tuning, not scaling**. A Nemotron-Super-49B-class grounding behaviour, distilled into an 8B-parameter student via NeMo Customizer on a corpus-matched training set (questions, contexts, expected answer-or-refusal decisions), would be a sharper lever than any off-the-shelf model of any size. That is a dedicated future article — a homegrown grounded-QA policy, served locally on the Spark, measured against this same qrels set. The goal is an 8B that commits where today's 8B refuses, and refuses only when the context is genuinely missing the fact — which is 9.1% of the time, not 18%. The title for that piece is already written in the ideas folder.

**Second Brain now:** keep the 8B, fix the corpus. **LLM Wiki now:** 8B for reads, 70B hosted for author-time drafting. **Autoresearch now:** the critic isn't a bigger model; it's a retrieval-retry primitive. Next up: **a distilled grounded-QA policy on top of the 8B NIM** — the homegrown move the first six articles' foundation was building toward.
