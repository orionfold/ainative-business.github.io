---
title: "Where Your Vectors Live — pgvector on a DGX Spark"
date: 2026-04-22
author: Manav Sehgal
product: pgvector
stage: inference
difficulty: intermediate
time_required: "~15 minutes first install, re-runs in seconds"
hardware: "NVIDIA DGX Spark"
tags: [pgvector, postgres, hnsw, ivfflat, matryoshka, nemotron, retrieval, dgx-spark]
summary: "The substrate between the embed call and the retrieve call — pgvector 0.8.2 running as a Postgres 16 container on GB10, with 1000 Nemotron vectors, HNSW and ivfflat both indexed, and a planner that prefers seq scan until you tell it otherwise."
signature: PgvectorStore
series: Foundations
fieldkit_modules: [rag]
---

One inference endpoint became a NIM. One embedding endpoint became the Nemotron Retriever. This time the substrate becomes `pgvector` — the column where the vectors *live* between the embed call and the retrieve call. Three arcs share this table; only the query predicates differ. A Second Brain asks "which notes look like what I just wrote?", a personal wiki asks "which pages duplicate this passage?", and an autoresearch agent asks "which prior trajectories resembled this plan?". All three push the same row shape through the same operator, `<=>`, against the same index.

The short version: pgvector 0.8.2 pulls cleanly onto a Spark as the official `pgvector/pgvector:pg16` container, mounts a persistent volume, and exposes Postgres on `:5432` with the vector type already compiled. A thousand AG-News chunks embedded through the [embedding NIM article's](/articles/nemo-retriever-embeddings-local/) Nemotron NIM and streamed into a `vector(1024)` column land at 99 documents per second end-to-end. Both HNSW and IVFFlat indexes build in under a second. Neither wins by default — the planner prefers a sequential scan at this corpus size, and forcing an approximate index costs you between 3 and 37 points of recall depending on the knob you turn. The longer version is more interesting because the planner's reluctance is itself the lesson: at a thousand rows, on an aarch64 Grace CPU, pgvector's `ORDER BY <=>` runs in two milliseconds without an index at all.

## Why pgvector instead of a purpose-built store

The fastest way to finish a RAG project is to put its vectors next to its rows. A personal corpus already wants a database for the non-vector columns — chunk text, source URL, ingest timestamp, tag set, provenance. You can run two stores and join across a network (Qdrant + Postgres, Milvus + Postgres, Pinecone + anything) or one store that speaks both languages. The second shape has fewer moving parts, one backup story, one auth model, one set of credentials, and one transactional boundary — `INSERT` the chunk text and its embedding in the same statement and either both land or neither does. Pre-pgvector, you couldn't do that without exotic plugins. With pgvector it's a typed column.

The case *against* pgvector is real at scale: a billion-vector index on a cloud deployment is genuinely easier on Milvus or a dedicated ANN service, because their index structures are tuned for that regime and their operators accept purpose-built hardware. A Spark is not that regime. A personal corpus is hundreds of thousands of rows at the upper end. Postgres plus pgvector handles that comfortably on a single node, and the engineering slope of "add a column" is much shorter than the slope of "stand up a second datastore."

## Where this sits in the stack

pgvector is not a database. It's a *Postgres extension* — a shared library loaded into an existing `postgres` process that adds a new datatype (`vector`), five new operators (`<->` L2, `<=>` cosine, `<#>` inner product, plus `<+>` and `<~>` for L1 and Hamming on newer types), and two new index access methods (ivfflat and hnsw). Everything else — WAL, transactions, replication, the query planner, the cache — comes from Postgres unchanged. The mental model that keeps you out of trouble is that a vector column is a column like any other, except the B-tree index you'd normally reach for is replaced by something graph-shaped or cluster-shaped.

<figure class="fn-diagram" aria-label="The pgvector layered stack on DGX Spark — your application talks to a Postgres driver, which speaks wire protocol to Postgres 16, which delegates vector operations to the pgvector 0.8.2 extension, which reads 8 KB pages from local disk. pgvector is the thesis-critical layer: a shared library loaded into the same Postgres process, not a separate service.">
  <svg viewBox="0 0 900 440" role="img" aria-label="The pgvector layered stack on DGX Spark — your application talks to a Postgres driver, which speaks wire protocol to Postgres 16, which delegates vector operations to the pgvector 0.8.2 extension, which reads 8 KB pages from local disk. pgvector is the thesis-critical layer: a shared library loaded into the same Postgres process, not a separate service." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d03-stack-band-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
        <stop offset="50%"  stop-color="var(--svg-accent-teal)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d03-pgv-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d03-pgv-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="80" y="20" width="740" height="400" rx="10" fill="url(#d03-stack-band-grad)" stroke="none"/>
    <rect x="120" y="208" width="660" height="76" rx="10" fill="url(#d03-pgv-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges"></g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="120" y="40" width="660" height="56" rx="8" />
      <rect class="fn-diagram__node" x="120" y="112" width="660" height="56" rx="8" />
      <rect class="fn-diagram__node" x="120" y="300" width="660" height="56" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="120" y="208" width="660" height="76" rx="10" style="fill: url(#d03-pgv-accent-grad)" />
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="120" y="372" width="660" height="48" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="180" y="62" text-anchor="start">YOUR APP</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="180" y="84" text-anchor="start">ingest · query</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="74" text-anchor="end">python · node · go · rust</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="180" y="134" text-anchor="start">DRIVER</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="180" y="156" text-anchor="start">psycopg · pg · pgx</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="146" text-anchor="end">wire protocol · TLS</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="180" y="230" text-anchor="start">EXTENSION</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="180" y="254" text-anchor="start">pgvector 0.8.2</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="180" y="272" text-anchor="start">vector type · &lt;=&gt; operator · ivfflat + hnsw</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="248" text-anchor="end">shared library · one process</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="180" y="322" text-anchor="start">DATABASE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="180" y="344" text-anchor="start">Postgres 16.13</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="334" text-anchor="end">planner · WAL · cache</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="180" y="392" text-anchor="start">STORAGE</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="720" y="404" text-anchor="end">8 KB pages · docker volume</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(136 48)"><path d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0V12a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 12V5.25"/></g>
      <g class="fn-diagram__icon" transform="translate(136 120)"><path d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13L21 7.5m0 0L16.5 12M21 7.5H7.5"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(136 220)"><path d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125"/></g>
      <g class="fn-diagram__icon" transform="translate(136 308)"><path d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z"/></g>
      <g class="fn-diagram__icon" transform="translate(136 380)"><path d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3"/></g>
    </g>
  </svg>
  <figcaption>pgvector is the middle band — a shared library in the same Postgres process, not a separate service. Your driver still speaks Postgres wire protocol; Postgres still writes 8 KB pages. The only new thing is the column type and the two index access methods that know what to do with it.</figcaption>
</figure>

That framing matters because it changes the operations story. There is no extra daemon to supervise, no extra port to open, no extra replication topology to reason about. The Spark runs one more Docker container — pgvector — and that container is just "Postgres with one extra `.so` loaded." Backups are `pg_dump`. High availability is the same streaming replication you'd set up for any Postgres.

## The journey

### Install — container-first

The handoff queued a choice between an apt-installed Postgres and a containerized one. Containerized wins on a blog where every other piece — NIM, NemoClaw, Ollama — already runs as a container; operationally it's one more `docker run` and the host stays clean. The official image at `pgvector/pgvector:pg16` bundles Postgres 16 with pgvector already built, and the `arm64/v8` layer in the manifest confirms it runs native on the Grace CPU rather than under qemu-translation:

```bash
docker pull pgvector/pgvector:pg16

docker volume create pgvector-data

docker run -d \
  --name pgvector \
  --restart unless-stopped \
  -e POSTGRES_PASSWORD=spark \
  -e POSTGRES_DB=vectors \
  -e POSTGRES_USER=spark \
  -v pgvector-data:/var/lib/postgresql/data \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

Thirteen seconds after the container starts, the server is listening. The first `psql` pins the architecture and confirms the extension is available:

```
PostgreSQL 16.13 (Debian 16.13-1.pgdg12+1) on aarch64-unknown-linux-gnu,
  compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit

 extname | extversion
---------+------------
 vector  | 0.8.2
```

`aarch64-unknown-linux-gnu` is the line that matters on a Spark. pgvector's `<=>` operator is a vectorised loop over float arrays — it benefits from Neon SIMD on the Grace CPU the same way it would benefit from AVX-512 on x86. A qemu-translated x86_64 build would silently cost you a multiplicative factor on every distance calculation; the native arm64 build doesn't.

### Commit to a dimension

The [embedding NIM article](/articles/nemo-retriever-embeddings-local/) kept the Nemotron embedding NIM deliberately agnostic on output size. pgvector can't. `vector(N)` is a typed column; `N` is fixed at `CREATE TABLE` time, and every row the column ever holds must have exactly `N` components. So this article has to pick one.

The Nemotron Retriever model card lists Matryoshka cut points at 384, 512, 768, 1024, and 2048 dimensions. The quality curve from the card puts 2048 at the top, 1024 about four points below it on NDCG@10, and the shorter truncations roughly another point apart. The storage curve is the inverse — 2048-d at 4 bytes per component is 8 KB per vector, 1024-d is 4 KB, 384-d is 1.5 KB. A hundred thousand chunks at 2048-d is 800 MB of vector data alone, plus whatever the HNSW graph adds on top. Same corpus at 1024-d is 400 MB. *1024-d is the quality/storage sweet spot for a personal-scale corpus* — you pay four NDCG points and halve the footprint. Everything in this article uses 1024-d.

The Nemotron NIM accepts an OpenAI-compatible `dimensions` parameter on the embed call, and a thirty-second sanity check confirms the server is doing real Matryoshka truncation — the 1024-d response is the first 1024 components of the 2048-d response, L2-renormalised to unit length:

```python
v2048 = embed("hello world", dimensions=2048)   # ‖v‖ = 1.000
v1024 = embed("hello world", dimensions=1024)   # ‖v‖ = 1.000

# Renormalised prefix of v2048 matches v1024 under 1e-4:
prefix = v2048[:1024]
normed = [x / norm(prefix) for x in prefix]
all(abs(a - b) < 1e-4 for a, b in zip(normed, v1024))   # True
```

That's reassuring. The server isn't slicing the vector server-side and returning an unnormalised prefix; it's doing the full projection-then-renormalise that the Matryoshka paper prescribes. Downstream cosine distance against a 1024-d query vector is comparing vectors that both live on the 1023-sphere, which is exactly what cosine similarity expects.

### Schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    id         BIGINT PRIMARY KEY,
    label      TEXT   NOT NULL,
    text       TEXT   NOT NULL,
    embedding  vector(1024) NOT NULL
);

CREATE INDEX chunks_label_idx ON chunks (label);
```

Three observations. First, `vector(1024)` is a real type — Postgres enforces the dimension on every write, so an off-by-one in client code fails at `INSERT` rather than at the next query. Second, there is no vector index yet; `ORDER BY embedding <=> 'q'` works against the raw column and the planner can choose a sequential scan, which is the right default until the corpus grows. Third, the `text` column earns its place in the same row as the embedding — retrieval returns the chunk alongside its neighbours in a single round trip, no second lookup to a key-value store required.

### Ingest — 99 documents per second end-to-end

The corpus is 1000 AG News headlines, stratified 250 each across the paper's four topic classes (World, Sports, Business, Sci/Tech). Stratification matters for the recall benchmark later — if 47 % of the rows were Sci/Tech (which is what a naive first-1000-rows pull returns) then a query about sports would have fewer true positives to land on and the recall numbers would be confounded by class imbalance.

The ingest script is stdlib-only. It batches 32 chunks per embed call, streams `COPY chunks FROM STDIN` records into the Postgres container via `docker exec -i`, and never imports psycopg:

```python
proc = subprocess.Popen(
    ["docker", "exec", "-i", "pgvector",
     "psql", "-U", "spark", "-d", "vectors", "-v", "ON_ERROR_STOP=1",
     "-c", "COPY chunks (id, label, text, embedding) FROM STDIN"],
    stdin=subprocess.PIPE, text=True)

for batch in chunks(corpus, size=32):
    vectors = embed(texts=[r["text"] for r in batch], dimensions=1024)
    for row, vec in zip(batch, vectors):
        proc.stdin.write(
            f"{row['id']}\t{row['label']}\t{tsv_escape(row['text'])}\t"
            f"[{','.join(f'{x:.6f}' for x in vec)}]\n")

proc.stdin.close()
proc.wait()
```

The pgvector text format inside a COPY stream is the same bracketed comma-separated list the SQL type accepts directly — `[0.123,0.456,...]`. No special escaping beyond the standard TSV rules for the other columns.

End-to-end throughput comes in at **99.5 documents per second** — 1000 rows embedded and persisted in 10.1 seconds. That's a 3.5× improvement over the [embedding NIM article's](/articles/nemo-retriever-embeddings-local/) 28.7 docs/s at 2048-d because the output payload halves (the HTTP body is 1024 floats instead of 2048) and the chunks themselves are short AG-News leads instead of 540-token passages. Batch size sits at the sweet spot that article found; larger batches don't help because the bottleneck is token-rate on the embedding side, not round-trip count.

The resulting relation is six megabytes for 1000 rows:

```
 rows |  heap  |  total
------+--------+---------
 1000 | 512 kB | 6048 kB

  label   | count
----------+-------
 Business |   250
 Sci/Tech |   250
 Sports   |   250
 World    |   250
```

Four megabytes of that is the vector column, stored in TOAST out-of-line because each vector exceeds Postgres's 2 KB in-line threshold. The 512 KB heap contains the `id`, `label`, `text`, and the pointers into TOAST. That structure matters when you index — HNSW and ivfflat read the vector bytes, and TOAST decompression is on the critical path for every distance calculation.

### Benchmark — exact, ivfflat, HNSW

The measurement harness takes 20 hand-crafted queries (five per topic class), embeds each at 1024-d with the Nemotron NIM, and runs the same `ORDER BY embedding <=> $1 LIMIT 10` against three configurations: a sequential scan with `enable_indexscan=off`, an IVFFlat index with `lists=32` swept across `probes ∈ {1, 4, 10, 32}`, and an HNSW index with `m=16, ef_construction=64` swept across `ef_search ∈ {10, 40, 100}`. For each configuration, two numbers: median latency across the 20 queries, and mean recall@10 measured against the exact seq-scan top-10.

| config                    | p50 (ms) | p95 (ms) | recall@10 |
|---------------------------|---------:|---------:|----------:|
| exact (seq scan)          |     2.71 |     3.47 |     1.000 |
| ivfflat probes=1          |     0.27 |     0.39 |     0.630 |
| ivfflat probes=4          |     0.48 |     0.56 |     0.860 |
| ivfflat probes=10         |     0.72 |     0.80 |     0.970 |
| ivfflat probes=32         |     1.53 |     1.62 |     1.000 |
| **hnsw ef\_search=10**    | **0.57** | **0.73** | **0.950** |
| hnsw ef\_search=40        |     0.91 |     1.29 |     0.980 |
| hnsw ef\_search=100       |     1.40 |     1.59 |     1.000 |

Three readings of that table.

**The approximate indexes work.** HNSW at `ef_search=10` is the frontier: 4.8× faster than the exact scan for a 5-point recall hit. IVFFlat at `probes=10` lands a fraction behind — 3.8× speedup for a 3-point recall hit, and at `probes=32` matches exact recall at roughly twice the index's minimum latency because `probes=32 = lists=32` means it scans every list. HNSW at `ef_search=100` also recovers full recall at a slightly lower cost than ivfflat at full probes.

**The index sizes diverge sharply.** The ivfflat index is about the same size as its sorted input — the structure is a flat cluster assignment, a few kilobytes per list. The HNSW index is `8,008 KB` — almost 2× the raw vector bytes, because the graph stores `M = 16` neighbour pointers per node at each layer plus the full vector in every leaf. For a personal corpus that's a non-issue; at a billion vectors that 2× overhead is the reason cloud vector databases exist.

**Neither index wins by default.** An unforced query against the raw HNSW-indexed table runs at the exact-scan latency because Postgres's planner picks sequential scan over both approximate indexes at 1000 rows. You can see it in the `EXPLAIN` output with no planner overrides:

```text
Limit  (cost=98.11..98.13 rows=10 width=16)
  ->  Sort  (cost=98.11..100.61 rows=1000 width=16)
        Sort Key: (embedding <=> '[...1024 floats...]'::vector)
        ->  Seq Scan on chunks  (cost=0.00..76.50 rows=1000 width=16)
```

The index is sitting right there on disk. The planner looks at it, costs it, decides `Seq Scan` at 76.50 cost units is cheaper than the IVFFlat scan at 2858.50 or the HNSW traversal's higher startup cost, and picks the linear walk. The numbers in the benchmark table above come from a `SET enable_seqscan = off` override that *forces* the planner onto the index. Without that override, every "ivfflat" or "hnsw" configuration silently executes the exact scan and lands at the exact-scan latency.

That's not a bug. It's the planner doing its job. At 1000 rows × 1024 dimensions × 4 bytes, the vector table is six megabytes — it fits in L3 cache on Grace, and a sequential SIMD loop over that memory hits two milliseconds because there is nothing faster than "touch every row in order when the rows are already in cache." The crossover at which HNSW's `log n` dominates seq scan's `n` is empirical, but the theory puts it somewhere between ten and a hundred thousand rows for a 1024-d index on a Grace CPU. At the low end of that range, the graph traversal's setup cost still eats the savings. Past it, the gap opens quickly.

Knowing that matters because it reframes when the approximate index is worth adding. You don't index at 1000 rows — you add the column, you ship, and you revisit when the query latency crosses whatever threshold the downstream application can tolerate. The cost of `CREATE INDEX ... USING hnsw` is 0.28 seconds on 1000 rows and grows roughly with `n log n`; a hundred thousand rows takes tens of seconds. The index is fast to build, cheap to drop, and re-creatable any time the dimension count or the distance operator changes.

### Topic-precision sanity check

Orthogonal to recall@10 (which measures whether the approximate index agrees with the exact scan) is *topic precision* — given a query about, say, tennis, what fraction of the top-10 retrieved chunks actually are Sports? The benchmark records this per class, and the pattern is consistent across every configuration:

```
           Sports  World  Business  Sci/Tech
exact        0.90   0.70      0.80      0.66
hnsw ef=10   0.96   0.70      0.80      0.68
```

Sports queries land cleanly — "tennis tournament" retrieves tennis headlines — because the vocabulary is distinctive. Sci/Tech is the hardest class at 0.66, because a 2004-era "google search engine" query legitimately pulls in headlines that a reader might also classify as Business ("Google IPO", "Google earnings"). The embedding model is not mislabeling — it's disambiguating on semantic proximity, and the AG News label set is less clean than the benchmark frames. A more robust evaluation would use explicit query–passage pairs like BEIR, but the cheap sanity check is enough to confirm the retrieval pipeline preserves topic signal end-to-end.

## What changes at scale

Three things shift as the corpus grows from a thousand rows toward a hundred thousand.

**The planner starts preferring the index.** Seq scan's cost is linear in row count; IVFFlat's cost is linear in `probes × rows / lists`; HNSW's is logarithmic in the node count. Somewhere between ten thousand and a hundred thousand rows, the HNSW cost estimate crosses below seq scan's, and queries start returning sub-millisecond latencies without any `SET` overrides. The exact crossover depends on the dimension count, the HNSW parameters, and the cache pressure.

**Index build time becomes something to plan.** HNSW at `m=16, ef_construction=64` on 1000 rows is 0.28 seconds. At 100,000 rows it's tens of seconds; at a million rows it's minutes. Building the index online (with writes happening) costs more than building it offline on a snapshot. For a Second Brain that grows by tens of notes a day, a nightly rebuild is fine; for a high-ingest wiki, you'll want concurrent inserts and incremental HNSW updates, which pgvector supports but at a cost.

**TOAST pressure matters.** Each 1024-d vector is 4 KB of floats, plus 8 bytes of header, which puts it above Postgres's 2 KB in-line threshold, which means it lives in TOAST out-of-line. Every distance calculation reads that TOAST tuple. At a thousand rows the working set fits in `shared_buffers` trivially; at a hundred thousand rows it's 400 MB of vector data and you need to size buffers deliberately. The default 128 MB `shared_buffers` in the container image is *not* what you want for a production-scale retrieval workload.

None of those are reasons to pick a different store. They're knobs to know about. For every project the three arcs will finish on this Spark — a Second Brain, a personal wiki, an autoresearch agent — the corpus sits in the hundreds-of-thousands range and fits inside one Postgres node with room to spare.

## The three-arc payoff

One inference endpoint became NIM. One memory layer became Nemotron Retriever. This time the substrate becomes pgvector — the place the vectors live between the embed call and the retrieve call. Three arcs share this table; only the query predicates differ.

- **Second Brain now has memory.** Notes become rows; the embedding column is the index. A `SELECT text FROM chunks ORDER BY embedding <=> $1 LIMIT 10` is the whole retrieval primitive. The rest is UI.
- **LLM Wiki now has an index.** Pages become rows with full text alongside the vector; duplicate detection is `WHERE embedding <=> $candidate < 0.2` and one more join for link management.
- **Autoresearch now has a trajectory store.** Agent runs are rows keyed by a trajectory ID, with vector columns for plan, observation, and outcome. "Have I done something like this before" becomes a three-column cosine query.

The [naive RAG article](/articles/naive-rag-on-spark/) wires naive RAG on top of this — take a question, embed it, retrieve the top-K chunks, stuff them into a Llama 3.1 8B NIM prompt, return the answer. Three article-stack pieces now: the LLM, the embedder, the store. One more — the generator wiring — and the three arcs share an end-to-end retrieval loop.
