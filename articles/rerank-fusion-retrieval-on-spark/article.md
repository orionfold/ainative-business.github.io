---
title: "Hybrid Retrieval on the Spark — BM25, Dense, Fusion, Rerank"
date: 2026-04-22
author: Manav Sehgal
product: Nemotron Reranker + pgvector full-text + Llama 3.1 8B NIM
stage: inference
difficulty: intermediate
time_required: "~45 minutes on top of the naive-RAG chain"
hardware: "NVIDIA DGX Spark"
tags: [rag, retrieval, rerank, bm25, rrf, hybrid, nemotron, pgvector, fusion, dgx-spark]
summary: "Four retrieval modes on one corpus — naive dense, BM25, Reciprocal Rank Fusion, Nemotron rerank. Dense is already 92% recall@5; rerank adds a point at K=10 and reorders the top. The 8B generator still refuses where retrieval is perfect — grounding, not retrieval, is the new bottleneck."
signature: RerankFusion
series: Foundations
fieldkit_modules: [rag]
---

The [naive RAG article](/articles/naive-rag-on-spark/) left a bruise. The Llama 3.1 8B NIM, handed five perfectly-retrieved chunks about the 2004 Google IPO, replied *"The provided context does not contain the answer."* The retrieval was right. The grounding was wrong. The closing paragraph queued two upgrades to the chain — a reranker to sharpen the top-K, and a BM25 lexical path to rescue exact-term queries — and asked whether either would close the gap.

This article answers that with a 30-query benchmark across four modes and an honest finding: the gap is real, but it isn't where I thought. Dense retrieval on AG News with the Nemotron Retriever embedder is already at 92% recall@5 — near the ceiling. Adding BM25 *lowers* fused recall slightly because the lexical side's noise dilutes a signal that was already near-perfect. The reranker rescues those losses and lifts recall@10 to 96.8% — the best number in the table. And even then, the 8B generator still refuses on the Google-IPO question. Retrieval is past the bottleneck. Grounding on an 8B strict-context model isn't.

## The thesis in one glance

<figure class="fn-diagram" aria-label="Retrieval-quality lift across four modes on a 30-query benchmark against AG News. Naive dense cosine is 92.1% recall@5. BM25 alone drops to 79.1% — on-topic but semantically thin. Reciprocal Rank Fusion of dense + BM25 lands at 88.4%, slightly below naive because dense was near-ceiling. The Nemotron reranker on the RRF candidates ties naive at 91.8% recall@5 and wins recall@10 at 96.8% — the best retrieval configuration, at the cost of a ~400-millisecond hosted-endpoint roundtrip.">
  <svg viewBox="0 0 900 420" role="img" aria-label="Retrieval-quality lift across four modes: naive, bm25, rrf, rerank on recall@5 and recall@10 at 30 queries" preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d05-lane-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
        <stop offset="50%"  stop-color="var(--svg-accent-teal)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d05-rerank-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d05-rerank-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="40" y="60" width="820" height="150" rx="8" fill="url(#d05-lane-grad)" stroke="none"/>
    <rect x="620" y="80" width="200" height="110" rx="10" fill="url(#d05-rerank-halo)" stroke="none"/>
    <g class="fn-diagram__scale">
      <line x1="60" y1="195" x2="840" y2="195" class="fn-diagram__axis"/>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="60"  y="214" text-anchor="start">79.1%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="250" y="214" text-anchor="middle">92.1%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="214" text-anchor="middle">88.4%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="680" y="214" text-anchor="middle">91.8%</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="800" y="214" text-anchor="end">recall@5</text>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60"  y="110" width="140" height="80" rx="8"/>
      <rect class="fn-diagram__node" x="230" y="90"  width="140" height="100" rx="8"/>
      <rect class="fn-diagram__node" x="400" y="100" width="140" height="90"  rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="620" y="80"  width="200" height="110" rx="10" style="fill: url(#d05-rerank-grad)"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="130" y="132" text-anchor="middle">BM25</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="130" y="154" text-anchor="middle">79.1% @ 5</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="130" y="172" text-anchor="middle">89.2% @ 10</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="300" y="112" text-anchor="middle">NAIVE DENSE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="300" y="134" text-anchor="middle">92.1% @ 5</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="300" y="152" text-anchor="middle">95.8% @ 10</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="300" y="172" text-anchor="middle">embed + pgvector</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="470" y="122" text-anchor="middle">RRF FUSION</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="470" y="144" text-anchor="middle">88.4% @ 5</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="470" y="162" text-anchor="middle">94.1% @ 10</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="470" y="180" text-anchor="middle">k = 60</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="720" y="102" text-anchor="middle">RERANK</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="720" y="124" text-anchor="middle">91.8% @ 5</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="720" y="146" text-anchor="middle">96.8% @ 10</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="164" text-anchor="middle">cross-encoder</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="180" text-anchor="middle">nemotron 1b</text>
    </g>
    <g class="fn-diagram__rule">
      <text class="fn-diagram__label fn-diagram__label--muted" x="450" y="280" text-anchor="middle">30 queries · 1000-row AG News corpus · K = 5 / 10</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="450" y="300" text-anchor="middle">median latency: naive 98 ms · bm25 75 ms · rrf 169 ms · rerank 523 ms</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="450" y="330" text-anchor="middle">retrieval is not the bottleneck — grounding on an 8B strict-context generator still is</text>
    </g>
  </svg>
  <figcaption>Four retrieval modes on the same 30-query benchmark. Naive dense clears 92% at K=5 on its own; BM25 alone sits 13 points below. Fusion is slightly <em>under</em> naive at K=5 because BM25's noise dilutes a dense signal that's already near-ceiling. The reranker (accent) recovers the fusion loss and extends the K=10 lead to 96.8% — the best configuration in the table.</figcaption>
</figure>

The upgrades work. The direction of the win is not the one the literature would predict, because the literature usually benchmarks against systems where dense retrieval is weaker. With a state-of-the-art retrieval embedder on a clean QA-style corpus, dense is already doing most of the work, and the reranker's job is to re-order — not to rescue.

## The four modes in one script

Every mode shares the same generator, the same strict-context prompt, the same streaming loop. The only thing that changes is how the top-K gets chosen. That discipline matters — it means any difference in the answer traces *only* to retrieval. The full script is at `articles/rerank-fusion-retrieval-on-spark/evidence/hybrid_ask.py`, stdlib-only, ninety new lines on top of the [naive RAG article's](/articles/naive-rag-on-spark/) `ask.py`.

```python
def retrieve(question, mode, k):
    if mode == "naive":
        qvec = embed_query(question)
        return pgvector_topk(qvec, k), timings

    if mode == "bm25":
        return bm25_topk(question, k), timings

    if mode in ("rrf", "rerank"):
        qvec = embed_query(question)
        dense = pgvector_topk(qvec, 20)        # top-20 semantic
        lex   = bm25_topk(question, 20)         # top-20 lexical
        fused = rrf_merge(dense, lex, top_k=20) # 1 / (60 + rank) sum
        if mode == "rrf":
            return fused[:k], timings
        return rerank_hits(question, fused, top_k=k), timings
```

Four branches, one dispatcher. The naive branch is what the [naive RAG article](/articles/naive-rag-on-spark/) shipped. The BM25 branch swaps the embedder and the ANN index for Postgres full-text. The RRF branch runs both in parallel and fuses. The rerank branch adds a cross-encoder pass over the fused candidates and re-sorts.

### BM25 with Postgres — six lines of SQL

Postgres ships full-text search in the core. No extension, no external ingest, no parallel index service. The [pgvector article's](/articles/pgvector-on-spark/) `chunks` table already has a `text` column; one `CREATE INDEX` turns it into a lexical index:

```sql
CREATE INDEX chunks_fts ON chunks
  USING GIN (to_tsvector('english', text));
```

Three seconds at a thousand rows. The GIN index stores the reverse map from stemmed token → row-id set, which is exactly what `ts_rank_cd` needs to score relevance under the BM25-ish family. The query side is one CTE:

```sql
WITH q AS (
  SELECT NULLIF(array_to_string(
    regexp_split_to_array(
      plainto_tsquery('english', $1)::text, ' & '), ' | '), '')
  ::tsquery AS tsq
)
SELECT id, label,
       ts_rank_cd(to_tsvector('english', text), q.tsq) AS rank,
       text
FROM chunks, q
WHERE q.tsq IS NOT NULL
  AND to_tsvector('english', text) @@ q.tsq
ORDER BY rank DESC
LIMIT 20;
```

The middle trick is turning `plainto_tsquery`'s `AND`-of-stems into an `OR`-of-stems. Out-of-the-box, `plainto_tsquery('english', 'Did Google have an IPO in 2004?')` returns `'googl' & 'ipo' & '2004'` — every stem must appear. On AG News, zero chunks contain all three stems together; BM25 returns an empty result. Hybrid retrieval needs the lexical side to cast a wider net than that, so the CTE splits on `&` and rejoins on `|`, turning the query into `'googl' | 'ipo' | '2004'` — any one stem counts. The ranker's `ts_rank_cd` then puts chunks with *more* hits (and denser proximity) at the top.

### Reciprocal Rank Fusion — eight lines of Python

RRF does not look at scores. It only looks at ranks. For each document, it sums `1 / (60 + rank)` across the two retrieval lists, where 60 is the Carbonell-Cormack-Clarke default from the 2009 paper that introduced the formula. Documents appearing in both lists get additive credit; a document in only one list gets a smaller but non-zero fused score.

```python
def rrf_merge(dense_hits, lex_hits, top_k, k_rrf=60):
    scores = {}
    for rank, h in enumerate(dense_hits, start=1):
        scores[h["id"]] = scores.get(h["id"], 0.0) + 1.0 / (k_rrf + rank)
    for rank, h in enumerate(lex_hits, start=1):
        scores[h["id"]] = scores.get(h["id"], 0.0) + 1.0 / (k_rrf + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
```

Eight lines. No hyperparameters to tune beyond `k_rrf=60` — which the literature says is robust across corpora and which I did not re-search on AG News because the gains from tuning RRF's k are a second-order story compared to whether hybrid retrieval beats naive at all.

### Rerank — and the reason it runs off-box

The Nemotron Reranker NIM (`nvidia/llama-3.2-nv-rerankqa-1b-v2`) is a cross-encoder that takes a query and a list of passages, scores each `(query, passage)` pair jointly under a transformer, and returns logit scores sorted high-to-low. Cross-encoders are *per-pair expensive* — they run the transformer once per candidate — which is why rerank runs over a top-20 list, not over the whole corpus.

The intention was to deploy the NIM locally on `:8002`, matching the embed and LLM NIMs. The reality is that neither of its inference backends works on GB10 today. The default ONNX profile hits a missing CUDA symbol inside the runtime's `ReduceSum` kernel; the TensorRT profile targeted at "compute capability 12.0" ships a pre-built plan compiled for RTX 6000 Blackwell (device id `2321:10de`, datacentre-class Blackwell), not the integrated Blackwell on GB10 (`0x12.1`, `RTX 6000 Blackwell svx1` in the NIM manifest). TensorRT refuses to deserialize engines across platform tags even when compute capabilities match. The NIM cycles through a retry loop and never reaches ready.

```
[TRT] [E] IRuntime::deserializeCudaEngine: Error Code 1: Serialization
  (Serialization assertion header.pad == expectedPlatformTag failed.
   Platform specific tag mismatch detected.
   TensorRT plan files are only supported on the target runtime platform
   they were created on.)
```

An NGC catalog check turned up no `-dgx-spark` variant for the reranker (unlike the Llama 3.1 8B NIM, which has one). Setting `NIM_MODEL_PROFILE` to either the ONNX or the cc-12.0 TRT profile hits the same dead-end. The right fix is to wait for a Spark-tagged reranker NIM or for a locally-building flow that re-compiles the TRT engine from an ONNX source on first run. Neither is available at writing.

The pragmatic workaround is to call NVIDIA's hosted NVCF endpoint for the reranker stage only. Same model, same API shape, different locus of compute:

```python
RERANK_URL = "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-3_2-nv-rerankqa-1b-v2/reranking"

def rerank_hits(question, hits, top_k):
    body = json.dumps({
        "model": "nvidia/llama-3.2-nv-rerankqa-1b-v2",
        "query": {"text": question},
        "passages": [{"text": h["text"]} for h in hits],
    }).encode()
    req = urllib.request.Request(RERANK_URL, data=body, headers={
        "Authorization": f"Bearer {NGC_API_KEY}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read())
    order = payload["rankings"]  # [{index, logit}, ...] desc
    return [hits[e["index"]] | {"logit": e["logit"]} for e in order[:top_k]]
```

The hosted endpoint returns in roughly 340 milliseconds for 20 passages — about 15 ms per pair plus a fixed network cost. When the local NIM eventually lands on the Spark, swapping the URL flips the call without touching the rest of the script. That property — the rerank stage being a single HTTP call with a portable shape — is the reason it's worth writing this article at this point even with the compat gap. The chain is already in the final shape it will have when the Spark catches up.

## The measurement — 30 queries, hand-labelled relevance

The benchmark harness at `evidence/benchmark.py` runs 30 queries through each of the four modes, measures wall-clock, and compares each retrieval to a hand-labelled relevant-set at `evidence/qrels.jsonl`. The qrels are specific — for each question, the relevant chunk IDs are the ones a reader would nod at and say "yes, that document answers this." Some questions have one relevant chunk ("what was Nortel's Canadian accounting probe about?" → `[1179]` and only `[1179]`). Others have fourteen (stocks-rebound queries, hurricane-damage queries, Chavez-referendum queries all have wide coverage because the corpus has many articles per event).

Recall@5 is the primary metric because five chunks is what the generator reads. Recall@10 is the secondary because it measures whether the right chunks are *reachable* — a configuration that nails recall@10 but loses at recall@5 could be rescued by rerank; a configuration that loses at recall@10 has nothing for the reranker to surface.

| mode   | recall@5 | recall@10 | median wall | p95 wall | max wall |
|--------|---------:|----------:|------------:|---------:|---------:|
| naive  |   0.9206 |    0.9583 |       98 ms |   112 ms |   123 ms |
| bm25   |   0.7911 |    0.8922 |       75 ms |    85 ms |    97 ms |
| rrf    |   0.8839 |    0.9411 |      169 ms |   189 ms |   202 ms |
| rerank |   0.9183 |    0.9683 |      523 ms |   583 ms |   736 ms |

Five observations.

**Dense is already near-ceiling at recall@5.** 92.1% means that for 30 questions and 30 five-chunk retrievals, the Nemotron embedder put the right document in the top-5 on essentially every question that had fewer than 5 relevant documents total. The questions that dragged the number down are the ones with one or two narrow relevant chunks that a generic embedding misses — and those are exactly where a reranker earns its keep.

**BM25 alone is worst, which is the expected shape.** On natural-language questions like "how did Tiger Woods finish the 2004 PGA Championship?", many relevant chunks don't share stems with the query — they contain "Woods comes up empty," "Tiger runs out of steam," "Hamilton sets early pace as Woods struggles." Dense retrieval embeds all three as semantically close to the query. BM25 only fires on the surface form. That said — BM25 wins outright on `q27 "Oil prices hit record high above 47"` — recall@5 goes from 0.50 (naive) to 1.00 (bm25). The number in the query is a stem BM25 loves and dense retrieval dilutes.

**RRF is slightly *worse* than naive at recall@5.** This is the result that would embarrass a hybrid-retrieval pitch deck, and it's worth reading carefully. Dense produced 92.1%. RRF of dense + BM25 produced 88.4%. The loss is not random — it happens on queries where dense had all the right chunks in its top-5 already, and fusing in BM25's top-5 pulls in lexically-adjacent-but-topically-wrong chunks that push a dense-found relevant chunk out of the top-5. **Hybrid retrieval only adds value when dense is weak**, and on AG News with Nemotron, dense is not weak.

**The reranker reclaims the loss.** Rerank@5 is 91.8% — essentially tied with naive — and rerank@10 is 96.8%, the best number in the table. Six queries show rerank lift recall@10 by 5–25 points over RRF, including the Phelps 200m question, the Sudan-Darfur question, the Venezuela referendum question, and the Kenteris doping question. In every one of those, RRF's top-10 had the right chunks somewhere in it, and the reranker hoisted them to the top-5 where they actually matter.

**Latency scales with the chain.** BM25 is fastest at 75 ms because it has no embed call, just a CTE. Naive is 98 ms — embed plus a cosine scan. RRF is 169 ms because it runs dense and BM25 in sequence (they could run in parallel; we don't because the complexity cost isn't worth the 60 ms for a benchmarking script). Rerank is 523 ms because the hosted-endpoint roundtrip is unavoidable. For a UI-facing chat the first three modes are all well under budget; the reranker adds half a second that is real. Parallelising the two retrievals would put RRF at ~110 ms, closer to naive.

## Where the rerank changes which chunks land at the top

The qualitative story is clearer than the summary table. Take the Phelps 200m freestyle question.

Naive top-5 (recall@5 = 0.75):

```
[1023] Sports   Olympics: Thorpe Beats Phelps as U.S. Suffers Gold Gap
[1002] Sports   Olympics: Thorpe Beats Phelps as U.S. Fights Gold Gap
[ 582] World    Phelps, Rival Thorpe in 200M-Free Semis
[1014] World    Thorpedo Sinks Phelps' Shot at Record
[ 533] World    Phelps, Thorpe Advance in 200 Freestyle
```

Rerank top-5 (recall@5 = 1.00):

```
[1014] World    Thorpedo Sinks Phelps' Shot at Record
[1002] Sports   Olympics: Thorpe Beats Phelps as U.S. Fights Gold Gap
[ 774] Sports   Phelps, Thorpe Face Dutch Threat
[1023] Sports   Olympics: Thorpe Beats Phelps as U.S. Suffers Gold Gap
[ 533] World    Phelps, Thorpe Advance in 200 Freestyle
```

Both lists contain the right chunks. The reranker reordered — `[1014] "Thorpedo Sinks Phelps' Shot at Record"` (the article that actually describes the loss) is now at rank 1, and `[582]` (a pre-race semifinal recap with no outcome) dropped out. The 8B generator's answer became sharper too — "Ian Thorpe. Sources: [1002, 774, 1023, 533]" instead of "Ian Thorpe beat Michael Phelps in the 200-meter freestyle at the Athens Olympics. Sources: [1023, 1002, 582, 1014, 533]." Terser, more confident, and one less tokens worth of hedging because the top-ranked chunk pinned the model's attention on the loss, not on the semifinals.

The rerank is not always a win. Three queries in the 30 go the other way — the US Dream Team loss, the Najaf Sadr militia fighting, the Hurricane Charley insurers — where naive's top-5 was cleaner than the reranker's top-5. On the Dream Team loss, naive kept all five slots on the loss itself; the reranker substituted in one chunk about Iverson's broken thumb (topically adjacent but not the event). The reranker is a scorer, not an oracle; its logit decisions can over-weight specificity at the cost of topical breadth. *Rerank helps on the average, not on every query,* is a sharper claim than the hybrid-retrieval marketing would suggest.

## The Google IPO question, re-probed — retrieval is solved, grounding isn't

The [naive RAG article's](/articles/naive-rag-on-spark/) hero moment was the 8B model refusing on "Did Google have an IPO in 2004?" despite pgvector returning five Google-IPO chunks. This article ran the same question through all four modes. Every single mode retrieved the correct chunks. The reranker put *different* correct chunks at the top — including `[1151] "Google Could Make Market Debut Wednesday"`, which states the IPO event in the headline and opens with "Google Inc. appeared set to start trading Wednesday." Surely *that* chunk is explicit enough.

Every single mode refused. Naive, BM25, RRF, rerank — all four handed a top-5 to the 8B generator that included the answer in the first hundred words of the top chunk, and all four got back *"The provided context does not contain the answer."*

That is the cleanest separation of the two failure modes that the naive baseline left ambiguous:

- **Retrieval is not the bottleneck.** The reranker had the right chunks at the top. The naive scan had the right chunks at the top. The BM25 scan had the right chunks at the top. Four different rankings, same outcome from the generator.
- **The 8B model's strict-context grounding circuit is the bottleneck.** At `temperature=0` with the strict-refuse scaffold, the 8B model doesn't commit to a yes/no on a yes/no question even when five on-topic chunks are in the prompt. This is a model-size problem, not a retrieval problem.

The narrower rephrase still works under rerank — "What was the Playboy controversy around the Google IPO?" produces a cited answer with the reranker pushing the actual Playboy-IPO chunks to ranks 1–4. The *broader* question is where the 8B's confidence collapses. The [bigger-generator article](/articles/bigger-generator-grounding-on-spark/) brings a bigger generator to this same corpus, and the measurement is whether a 70B (or Nemotron Super) closes that specific refusal.

## Latency budget — where the 500 ms goes

The rerank chain takes ~520 ms median end-to-end for retrieval alone. Broken down:

- **35 ms** — query embedding, Nemotron :8001 (carries forward from the [embedding NIM article](/articles/nemo-retriever-embeddings-local/))
- **65 ms** — pgvector dense top-20, `docker exec` startup + cosine scan
- **75 ms** — BM25 top-20, ts_rank_cd via GIN index
- **< 1 ms** — RRF merge (20 + 20 items sorted in-memory)
- **340 ms** — hosted-endpoint rerank roundtrip (net + 20-pair cross-encoder)

The rerank step is 65% of the retrieval wall-clock. When the local NIM arrives, 340 ms becomes ~150 ms — 20 passage × ~8 ms per pair on-GPU, minus network. That single change moves the rerank mode from "noticeable pause" to "imperceptible." Until then, the hosted endpoint is fast enough that retrieval + generation still fits inside the 2-second chat budget the second-brain / wiki / autoresearch arcs share.

## What the three arcs got

Four retrieval modes, three running threads.

- **Second Brain** got a principled second opinion. The rerank step changes which notes land in the top-5, and for queries that ask for a specific person / date / fact (the majority of a second brain's workload), that reordering matters — it's the difference between "here are five adjacent notes" and "here is the single note that answers you." The BM25 path also earns its keep here: when a query contains a specific string the user remembers typing ("that error from Tuesday that said 'SIGABRT'"), BM25 finds it; dense retrieval rounds it to "any error about signals."
- **LLM Wiki** got exact-term rescue. The BM25 path closes the class of queries where a reader knows a specific term — a library name, a config key, a ticket number — and wants the page that mentions it verbatim. RRF makes sure those lexical wins don't come at the cost of a semantic miss. The reranker tightens the top-5 for natural-language questions over the wiki.
- **Autoresearch** got a ranker it can use. Cross-encoder scores are a useful signal for a planner that's comparing candidate next-steps; the reranker's logit is already calibrated per-pair and is more trustworthy as a "how good is this match" number than any score the retriever emits. The autoresearch loop now has a primitive it can call to break ties when two trajectories look equally good to the dense index.

## Closing

Four articles ago I expected hybrid retrieval to dominate naive by several recall points on every query. The measurement says the opposite story — with a strong embedder on a clean corpus, naive is already 92% recall@5 and BM25 + RRF only help on the queries where dense was weak, which is a minority. The reranker is what actually moves the needle at recall@10, and its biggest contribution is reordering — *which* correct chunks land at the top, not whether they're found at all.

The grounding gap from the [naive RAG article](/articles/naive-rag-on-spark/) is sharper now, not narrower. Four different retrieval configurations fed five correct chunks to the 8B generator on the Google-IPO question. All four got back a refusal. Retrieval is past the bottleneck at AG News scale with this embedder. The [bigger-generator article](/articles/bigger-generator-grounding-on-spark/) swaps the 8B for a bigger generator — Nemotron-Super-49B through the hosted endpoint, or the next local NIM that fits GB10 memory — and measure whether a stronger grounding circuit closes the refusal.

**Second Brain now:** has BM25 recall for exact-term queries. **LLM Wiki now:** ranks library-name hits correctly. **Autoresearch now:** has a calibrated tie-breaker. Next up: **a bigger generator on the same retrieval chain** — measure whether 49B / 70B-class grounding turns the four-mode refusal on "Did Google have an IPO in 2004?" into the obvious yes.
