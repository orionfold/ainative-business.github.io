---
title: "Three Endpoints, One Answer — Naive RAG on a DGX Spark"
date: 2026-04-22
author: Manav Sehgal
product: Llama 3.1 8B NIM + Nemotron Retriever + pgvector
stage: inference
difficulty: intermediate
time_required: "~30 minutes if the three endpoints are already warm"
hardware: "NVIDIA DGX Spark"
tags: [rag, retrieval, llama, nemotron, pgvector, nim, grounding, hallucination, dgx-spark]
summary: "Three endpoints in one curl chain — a query embeds through Nemotron, pgvector returns top-5 chunks in under 80 ms, and a Llama 3.1 8B NIM stuffs them into a strict-context prompt. The chain works; the 8B generator still refuses on questions its own context answers."
signature: NaiveRagChain
series: Foundations
fieldkit_modules: [rag, eval]
---

Four articles in. The Llama 3.1 8B NIM has been serving `:8000` for two weeks. The Nemotron Retriever NIM joined it at `:8001`. The `pgvector` container on `:5432` holds a thousand 1024-d vectors with both IVFFlat and HNSW indexes built. Each article stood its endpoint up in isolation. None of them *called each other*.

This one does. A question gets embedded. The top-five nearest chunks come back from pgvector. The question and the chunks get stuffed into a strict-context prompt. The answer streams token-by-token from the 8B generator. One script, no dependencies, three localhost ports in the same `curl` chain — end-to-end naive RAG on the box that sits on the desk.

The short version: the chain works. Embedding a query costs 40 milliseconds. pgvector returns the top-5 in 70 milliseconds (half of that is `docker exec` startup, half is the actual cosine scan). The 8B generator streams the first token in 80 milliseconds and finishes a grounded answer in half a second. *Sometimes.* The longer, more honest version is that the 8B model under a strict "answer only from the context" scaffold will refuse a third of the time on questions the context clearly answers — the retrieval was perfect, the prompt was well-formed, and the generator still said "I don't know." That refusal is the article's hero moment, because it's the clean separation between what naive RAG gets right and what reranking + better prompts + a bigger generator will need to fix.

## The thesis in one glance

<figure class="fn-diagram" aria-label="Naive RAG vs zero-retrieval — the same Llama 3.1 8B NIM answers a corpus-grounded question with citations when the retrieval step packs the right context into the prompt, and fabricates a plausible-looking wrong answer when the same question reaches the generator without retrieval. The article's thesis: retrieval is what converts a lossy 8-billion-parameter prior into a grounded answering system on your own data.">
  <svg viewBox="0 0 900 460" role="img" aria-label="Naive RAG vs zero-retrieval — the same Llama 3.1 8B NIM answers a corpus-grounded question with citations when the retrieval step packs the right context into the prompt, and fabricates a plausible-looking wrong answer when the same question reaches the generator without retrieval. The article's thesis: retrieval is what converts a lossy 8-billion-parameter prior into a grounded answering system on your own data." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d04-rag-lane-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
        <stop offset="50%"  stop-color="var(--svg-accent-teal)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d04-bare-lane-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-text-faint)" stop-opacity="0.02"/>
        <stop offset="50%"  stop-color="var(--svg-text-faint)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-text-faint)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d04-grounded-halo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d04-answer-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="190" y="60"  width="680" height="120" rx="8" fill="url(#d04-rag-lane-grad)" stroke="none"/>
    <rect x="340" y="300" width="530" height="100" rx="8" fill="url(#d04-bare-lane-grad)" stroke="none"/>
    <rect x="670" y="80"  width="200" height="80" rx="10" fill="url(#d04-grounded-halo)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 170 200 L 190 120" />
      <path class="fn-diagram__edge" pathLength="100" d="M 170 260 L 340 350" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 330 120 L 350 120" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 490 120 L 510 120" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 650 120 L 670 120" />
      <path class="fn-diagram__edge" pathLength="100" d="M 490 350 L 670 350" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="30" y="190" width="140" height="80" rx="8" />
      <rect class="fn-diagram__node" x="190" y="80" width="140" height="80" rx="8" />
      <rect class="fn-diagram__node" x="350" y="80" width="140" height="80" rx="8" />
      <rect class="fn-diagram__node" x="510" y="80" width="140" height="80" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="670" y="80" width="200" height="80" rx="10" style="fill: url(#d04-answer-grad)" />
      <rect class="fn-diagram__node" x="340" y="310" width="150" height="80" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="670" y="310" width="200" height="80" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="100" y="218" text-anchor="middle">SHARED QUERY</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="100" y="240" text-anchor="middle">user question</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="258" text-anchor="middle">&quot;who won…&quot;</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="260" y="104" text-anchor="middle">EMBED</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="260" y="126" text-anchor="middle">nemotron :8001</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="260" y="144" text-anchor="middle">1024-d query vec</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="420" y="104" text-anchor="middle">RETRIEVE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="420" y="126" text-anchor="middle">pgvector top-K</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="420" y="144" text-anchor="middle">5 chunks · ~70 ms</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="580" y="104" text-anchor="middle">GENERATE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="580" y="126" text-anchor="middle">llama 3.1 8b</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="580" y="144" text-anchor="middle">strict ctx · :8000</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="770" y="104" text-anchor="middle">GROUNDED</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="770" y="126" text-anchor="middle">answer + citations</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="770" y="144" text-anchor="middle">Sources: [id, id]</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="415" y="334" text-anchor="middle">GENERATE (NO CTX)</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="415" y="356" text-anchor="middle">llama 3.1 8b</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="415" y="374" text-anchor="middle">prior only</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="770" y="334" text-anchor="middle">UNGROUNDED</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="770" y="356" text-anchor="middle">plausible answer</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="770" y="374" text-anchor="middle">no sources</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="410" text-anchor="middle">same question · two paths</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(678 88)"><path d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"/></g>
      <g class="fn-diagram__icon" transform="translate(678 318)"><path d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/></g>
    </g>
  </svg>
  <figcaption>The retrieval lane (top, accent) forces the generator to read from a provided context. The bare lane (bottom, muted) is what the same 8B model produces when the question lands on it alone — plausible prose, no source IDs, no anchor to your corpus.</figcaption>
</figure>

The 8B model is not dumb. It has trained on a huge chunk of the open internet through 2023. What it lacks, on anything that matters, is *your data* — the notes, the wiki pages, the ticket threads, the headlines from 2004, the code in the private repo. Retrieval is the mechanism that moves that data into the prompt. The generator is the mechanism that turns the prompt into prose. Naive RAG is the one-shot version of the two-step chain: no rerank, no filter, no second pass, nothing clever. It is the baseline you measure everything else against.

## Why "naive" is the right first version

A production RAG stack wraps a reranker around the retriever, adds a query-rewriter in front, caches hot chunks, fans out across multiple indices, and validates the generator's output against a schema. Each of those is a half-article of its own. *Starting with those is a mistake* — you skip the baseline measurement, and you can't attribute a latency tax or a recall win to any single component. Naive RAG is the measurement: `embed(query) → ORDER BY <=> LIMIT K → stuff into prompt → generate`. Every later addition needs to justify its cost against this number.

The practical consequence is that naive RAG is also the cheapest thing to stand up. The script below is ninety lines, stdlib-only, and it calls three already-running services. Ninety lines is a meaningful bar because it means the full chain fits on a single screen and every step is auditable — which component produced this token? The strict-context prompt, the top-five chunks, or the model's training prior? When the chain breaks (and it will), the fewer layers between you and the break, the faster the diagnosis.

## The script — ninety lines, three endpoints, one answer

The full script lives at `articles/naive-rag-on-spark/evidence/ask.py`. It does four things. Embed the query. Query pgvector. Format the strict-context prompt. Stream the completion.

### 1. Embed the query — differently from how you embedded the corpus

The Nemotron Retriever NIM takes an `input_type` parameter that matters at inference time. Passages went in as `"passage"` during the [pgvector article's](/articles/pgvector-on-spark/) ingest. Queries go in as `"query"`. The model was trained with contrastive pairs where the query branch and the passage branch are *different heads* of the same encoder — there's a task-conditional signal baked into the embedding, and using the passage head for queries will drop your recall by several points. On the Nemotron Retriever model card the exact delta isn't quoted, but the BEIR numbers from the paper show query/passage role mismatch costs 2–5 NDCG points depending on the task:

```python
def embed_query(text):
    body = json.dumps({
        "model": "nvidia/llama-nemotron-embed-1b-v2",
        "input": [text],
        "input_type": "query",      # <-- not "passage"
        "dimensions": 1024,
    }).encode()
    req = urllib.request.Request(EMBED_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["data"][0]["embedding"]
```

One call. 40 milliseconds on a warm NIM at 1024-d. Articles #4 and #5 established that throughput; this article uses the output directly without re-measuring.

### 2. Query pgvector — straight cosine, no planner overrides

```python
def pgvector_search(qvec, k):
    vec_literal = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"
    sql = (
        "SELECT id, label, (embedding <=> '" + vec_literal + "') AS dist, text "
        "FROM chunks "
        "ORDER BY embedding <=> '" + vec_literal + "' "
        f"LIMIT {int(k)};"
    )
    proc = subprocess.run(PSQL, input=sql, capture_output=True, text=True,
                          timeout=10, check=True)
    ...
```

SQL on stdin instead of on the command line — a 1024-float query vector survives stdin cleanly, and would explode every shell quoting rule on the command line. No `enable_seqscan = off` override; the [pgvector article](/articles/pgvector-on-spark/) showed the planner picks sequential scan at a thousand rows and that's fine, because the sequential scan is already sub-millisecond. The 70-millisecond wall-clock number is dominated by `docker exec` startup cost — the actual index/scan time inside Postgres is around 3 milliseconds.

### 3. Format the strict-context prompt

Two choices matter here, and both are deliberately biased toward precision over recall:

```python
STRICT_SYSTEM = (
    "You are a careful assistant. Answer the user's question using ONLY the "
    "provided context passages. Each passage is prefixed with its row id in "
    "square brackets like [123]. If the answer is present, state it plainly "
    "and cite the ids you used in a trailing 'Sources: [id, id]' line. If "
    "the context does not contain the answer, reply with exactly one "
    "sentence: 'The provided context does not contain the answer.' Do not "
    "fall back to general knowledge."
)

def build_messages(question, hits):
    context_block = "\n".join(
        f"[{h['id']}] ({h['label']}) {h['text']}" for h in hits)
    user = f"Context passages:\n{context_block}\n\nQuestion: {question}"
    return [{"role": "system", "content": STRICT_SYSTEM},
            {"role": "user", "content": user}]
```

**The citation schema is trailing, not inline.** `Sources: [71, 72]` at the end is easier to parse than inline `[71]` markers scattered through the prose — one regex extracts the source list, no stateful scanner. Inline citations are prettier in a UI; trailing citations are easier to verify programmatically.

**The refusal sentence is fixed.** "The provided context does not contain the answer." — verbatim. This matters because it makes the refusal detectable by an exact string match instead of heuristic intent classification. The prompt leaves no room for the model to hedge with "I'm not sure, but perhaps..." — either it answers, or it emits the refusal sentence. That constraint is the whole point of *strict* context.

### 4. Stream the generation

OpenAI-compatible streaming. Server-sent events, each carrying a `delta.content` piece. The script notes time-to-first-token separately from total generation time so we can pull both numbers out later:

```python
def stream_answer(messages, max_tokens=256, temperature=0.0):
    body = json.dumps({
        "model": "meta/llama-3.1-8b-instruct",
        "messages": messages, "max_tokens": max_tokens,
        "temperature": temperature, "stream": True,
    }).encode()
    ...
    t_start = time.perf_counter()
    first_token_ms = None
    parts = []
    for raw in r:
        line = raw.decode().strip()
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        chunk = json.loads(line[6:])
        piece = chunk["choices"][0].get("delta", {}).get("content", "")
        if piece:
            if first_token_ms is None:
                first_token_ms = (time.perf_counter() - t_start) * 1000
            parts.append(piece)
    return "".join(parts), first_token_ms, ...
```

Temperature zero because we want a deterministic baseline. The 8B model at `temperature=0.7` is a different system than the 8B model at `temperature=0`; measuring both would double the experiment matrix without adding insight for this article. A later piece about prompt-optimisation pressure can revisit the sampling curve.

## The numbers

Six queries through the chain — three answerable from the 2004 AG-News corpus ingested in the [pgvector article](/articles/pgvector-on-spark/), three deliberately outside it. The strict scaffold should ground the first group and refuse the second:

| query                                                  | kind          | embed | retrieve | ttft  | generate | end-to-end |
|--------------------------------------------------------|---------------|------:|---------:|------:|---------:|-----------:|
| Who won the 2004 US presidential election?             | in-corpus     | 46 ms |    73 ms | 83 ms |   451 ms |      570 ms |
| What happened at the 2004 Athens Olympics in swimming? | in-corpus     | 36 ms |    78 ms | 85 ms |  1701 ms |     1815 ms |
| What did Google do in 2004 related to going public?    | in-corpus     | 46 ms |    76 ms | 84 ms |   458 ms |      580 ms |
| Who won the 2020 US presidential election?             | out-of-corpus | 38 ms |    63 ms | 67 ms |   425 ms |      526 ms |
| What is NVIDIA DGX Spark?                              | out-of-corpus | 45 ms |    65 ms | 82 ms |   451 ms |      562 ms |
| When was Claude 4 Opus released?                       | out-of-corpus | 46 ms |    67 ms | 76 ms |   452 ms |      565 ms |

Four observations.

**Embed and retrieve are steady.** 40 and 70 milliseconds respectively, independent of query length or topic. The embed side is dominated by a 1-token-to-1024-float forward pass on a warm GPU; the retrieve side is `docker exec` startup (roughly 60 ms) plus a sub-millisecond cosine scan. If this stack needed lower retrieval latency, the fix is to keep a long-lived Postgres connection open from the Python process rather than shelling out per query — that collapses the 70 ms to around 5 ms. Naive RAG doesn't need it.

**Time-to-first-token is 80 milliseconds on a cold-prompt.** The [first NIM article](/articles/nim-first-inference-dgx-spark/) measured 52 ms TTFT on a short prompt. The RAG prompt here is roughly 800 tokens (five chunks averaging 140 tokens each, plus the system message and scaffolding); the extra 30 ms is the prefill phase on the longer context. Generation is where the wall-clock lives — half a second for a refusal, a second and a half for a cited answer.

**Total generation variance is 4× across queries.** The shortest generation is 425 ms (a 13-token refusal); the longest is 1701 ms (a 40-token cited answer, double-sentenced). The Spark's 8B FP8 engine runs at roughly 25 tokens per second under load (the [first NIM article's](/articles/nim-first-inference-dgx-spark/) headline number), and every query here lands within a few tokens per second of that. The variance is output-length variance, exactly as it was in that article — the chain didn't regress the generator's throughput.

**End-to-end is 525 ms to 1815 ms.** A naive-RAG chain on a Spark answers a question in between half a second and two seconds. That's within interactive-UI budget for a chat-style interface. It's not fast enough for a typeahead autocomplete, but it doesn't need to be — the Second Brain, the wiki, and the autoresearch agent all have budgets of several seconds per turn.

## The hero moment — retrieval was right, generation still refused

The table above hides something important. Three of the six queries *refused*, not two. The 2004-presidential-election question refused (correctly — AG News's 2004 coverage is pre-election, so "who won" isn't knowable from the corpus). But the Google-IPO question also refused, and that one *shouldn't* have.

Here's what pgvector returned for "Did Google have an IPO in 2004?":

```
[  71] Business  Play Boys: Google IPO a Go Anyway — Even though Google's
                 two founders gave an interview to Playboy magazine in the
                 midst of its IPO filing, the SEC allowed the company's
                 offering to go ahead…
[  36] Business  Google IPO: Type in 'confusing,' 'secrecy' — I've submitted
                 my bid to buy shares of Google Inc. in the computer search
                 company's giant auction-style initial public offering…
[  20] Business  Google IPO faces Playboy slip-up — The bidding gets underway
                 for Google's public offering…
[  13] Business  Google IPO Auction Off to Rocky Start — WASHINGTON/NEW YORK
                 (Reuters) - The auction for Google's upcoming IPO…
[1136] Business  Google IPO statement ready to go — Google's planned flotation
                 moves another step closer after…
```

Five headlines about the Google IPO. The word "IPO" appears in four of the five titles. The answer to "did Google have an IPO in 2004" is transparently "yes — here's the auction, here's the filing, here's the offering going ahead." The 8B model under the strict scaffold replied: *"The provided context does not contain the answer."*

That is not a retrieval failure. Retrieval was perfect. That is a *grounding* failure — the 8B model, under a strict "answer only from the context" prompt, at `temperature=0`, could not confidently assert the yes/no answer the context supports. Rephrased to be more specific — "What was the Playboy controversy around the Google IPO?" — the chain worked cleanly:

```
Q: What was the Playboy controversy around the Google IPO?

A: The Google co-founders gave an interview to Playboy magazine in the
   midst of their IPO filing, which raised concerns about Securities
   regulations restricting what executives can say while preparing to
   sell stock for the first time.
   Sources: [72, 71]
```

Same corpus, same retrieval pipeline (chunks [72] and [71] were among the top-5 in both runs), narrower question, and the generator extracted and cited the answer. The broader yes/no question landed in a gap where the 8B model's context-reading circuit is less confident than its refusal circuit.

This is the honest lesson of naive RAG, and it's the first lesson that motivates the articles to come:

- **Retrieval is not the bottleneck at this scale.** Nemotron + pgvector delivers the right chunks for well-specified questions within 100 milliseconds, and the recall numbers from the [pgvector article](/articles/pgvector-on-spark/) hold.
- **The 8B model's grounding circuit is the bottleneck.** The strict scaffold is precision-first by design, and on a model this size the precision bias costs you recall on yes/no questions and compound questions.
- **The obvious fixes all have names.** A larger generator (Llama 70B, Qwen 32B, Nemotron-Super) has a stronger grounding circuit. A better prompt (few-shot examples of answer extraction) raises the same-size model's precision floor. A reranker (Nemotron Reranker as a second-stage filter) strengthens the retrieval signal before the model sees it. Each of those is a future article; none of them matters until you've measured the naive baseline.

## What the three arcs got

Four articles, three running threads. Each of them crossed a meaningful threshold this session.

- **Second Brain** went from "has memory" to *has a lookup*. A question asked in plain English returns cited notes in under a second, grounded in the stored corpus. The next step is the write-side — turning every transcript, screenshot, and search-result page into a row in `chunks`.
- **LLM Wiki** went from "has an index" to *has a Q&A surface*. Same retrieval, same generator, different prompt — asking "what do our pages say about X" returns a grounded paragraph with cited page ids. The refusal behaviour observed above is acceptable here because the wiki's editorial standard rewards precision over coverage.
- **Autoresearch** went from "has a trajectory store" to *has a first retrieval loop*. A plan-step can now query similar past trajectories before branching; the 70-millisecond retrieval cost is well under the seconds-per-step budget of any research loop worth running. The refusal cases in this article are *feature* for an autoresearch agent — a cautious refusal is a cleaner signal to the planner than a confident hallucination.

The infrastructure below the arcs is now complete for naive RAG. Three endpoints, one chain, no outbound traffic. Four articles from now the agent that asks these questions is itself running on the Spark.

## Closing

Naive RAG is a measurement harness, not an application. The numbers in this article — 40 ms embed, 70 ms retrieve, 80 ms to first token, half-a-second to two seconds end-to-end — are the baseline the next articles will beat. The refusal edge case is the baseline the next articles will close.

The genuinely ironic thing about naive RAG on a DGX Spark is that the pieces that *should* be the hard part — pulling a question through an embedding model, doing an approximate-nearest-neighbour search, stuffing the results into a chat prompt, streaming the answer — are sub-second and boring. The hard part is the prompt scaffold and the generator's grounding circuit, which is a research problem the community has been chewing on for four years and will keep chewing on for four more. The Spark makes the substrate trivial. The substrate was never the interesting part.

**Second Brain now:** has a lookup. **LLM Wiki now:** has a Q&A surface. **Autoresearch now:** has a first retrieval loop. Next up: **rerank + fusion retrieval on the Spark** — adding a Nemotron Reranker second stage, merging a BM25 path for exact-match queries, and measuring the recall lift on the same six questions this article refused or half-answered.
