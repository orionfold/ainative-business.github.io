---
title: "One Substrate, Three Apps — Where the Foundation Forks"
date: 2026-04-22
author: Manav Sehgal
product: Foundation
stage: foundations
difficulty: intermediate
time_required: "10-minute read; no hands-on"
hardware: "NVIDIA DGX Spark"
tags: [foundation, second-brain, llm-wiki, autoresearch, arc, bridge, dgx-spark]
summary: "Seven articles installed one stack on the Spark — NIM, Embed, pgvector, RAG glue, reranker, generator A/B, Guardrails. This bridge retells that install as three different answers to one question — corpus plus 128 GB — and walks readers to the top of three tracks."
signature: OneSubstrateThreeApps
series: Foundations
---

Nine articles ago the Spark was a blinking power light. Now it is an answering machine, a search index, a policy gate, and a retrieval chain fast enough to lose its own latency inside the generator's. The install is done. What it runs is the question the next twenty articles answer — in three different voices.

This article is a bridge. It installs nothing. It runs no benchmark. It exists to turn a pile of commodity parts into a coherent story, declare the fork, and walk the reader to the top of whichever track fits their cost profile. By the end of it, the arc detector points at three different "next article" slugs and readers pick based on which shape of cost they want to pay.

## Why the fork has to happen now

An individual building on one Spark is not an enterprise, and enterprise RAG tutorials translate badly. The cost shape of a thing you own outright is different from the cost shape of something you rent per call — not just cheaper, but *structurally* different. Privacy flips (your archive never leaves the box), data gravity flips (the compute comes to where the data already is), and the arithmetic of ambitious designs flips with it. Designs that would be laughed out of a cost review at 3¢ per thousand tokens become trivially affordable when the tokens are yours.

But "cheap" is not a design. Every piece of software eventually answers a specific question; three specific questions are worth answering on one Spark, and they fight for the same memory, the same retrieval chain, and the same 8B NIM. Declaring the fork lets each answer find its own shape without negotiating with the other two.

## The three apps, the three costs

<figure class="fn-diagram" aria-label="Where the cost lives per arc. Second Brain spends its cost at query time — retrieve, rerank, and generate on every user question. LLM Wiki spends its cost at ingest — read each source once and update ten or fifteen pages across the wiki. Autoresearch spends nothing at query or ingest and spends all its cost in the overnight loop. Three different cost profiles, one shared substrate.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Cost distribution across three arcs — Second Brain dominated by per-query cost, LLM Wiki dominated by ingest cost, Autoresearch dominated by loop cost" preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d08-ingest" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)"   stop-opacity="0.45"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)"   stop-opacity="0.15"/>
      </linearGradient>
      <linearGradient id="d08-query" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)"   stop-opacity="0.45"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)"   stop-opacity="0.15"/>
      </linearGradient>
      <linearGradient id="d08-loop" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.45"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.15"/>
      </linearGradient>
    </defs>
    <g class="fn-diagram__nodes">
      <!-- legend chips -->
      <rect class="fn-diagram__node" x="260" y="56" width="60" height="24" rx="4" style="fill: url(#d08-ingest)"/>
      <rect class="fn-diagram__node" x="420" y="56" width="60" height="24" rx="4" style="fill: url(#d08-query)"/>
      <rect class="fn-diagram__node" x="580" y="56" width="60" height="24" rx="4" style="fill: url(#d08-loop)"/>
      <!-- SB row: ingest 70, query 530, loop 40 -->
      <rect class="fn-diagram__node" x="180" y="120" width="70"  height="50" rx="4" style="fill: url(#d08-ingest)"/>
      <rect class="fn-diagram__node" x="252" y="120" width="530" height="50" rx="4" style="fill: url(#d08-query)"/>
      <rect class="fn-diagram__node" x="784" y="120" width="40"  height="50" rx="4" style="fill: url(#d08-loop)"/>
      <!-- Wiki row: ingest 480, query 80, loop 80 -->
      <rect class="fn-diagram__node" x="180" y="210" width="480" height="50" rx="4" style="fill: url(#d08-ingest)"/>
      <rect class="fn-diagram__node" x="662" y="210" width="80"  height="50" rx="4" style="fill: url(#d08-query)"/>
      <rect class="fn-diagram__node" x="744" y="210" width="80"  height="50" rx="4" style="fill: url(#d08-loop)"/>
      <!-- Auto row: ingest 30, query 30, loop 580 -->
      <rect class="fn-diagram__node" x="180" y="300" width="30"  height="50" rx="4" style="fill: url(#d08-ingest)"/>
      <rect class="fn-diagram__node" x="212" y="300" width="30"  height="50" rx="4" style="fill: url(#d08-query)"/>
      <rect class="fn-diagram__node" x="244" y="300" width="580" height="50" rx="4" style="fill: url(#d08-loop)"/>
    </g>
    <g class="fn-diagram__labels">
      <!-- legend labels -->
      <text class="fn-diagram__label fn-diagram__label--mono" x="290" y="72" text-anchor="middle">INGEST</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="450" y="72" text-anchor="middle">QUERY</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="610" y="72" text-anchor="middle">LOOP</text>
      <!-- row labels on left -->
      <text class="fn-diagram__label fn-diagram__label--accent" x="170" y="138" text-anchor="end">SECOND BRAIN</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="170" y="156" text-anchor="end">per query</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="170" y="228" text-anchor="end">LLM WIKI</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="170" y="246" text-anchor="end">per source</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="170" y="318" text-anchor="end">AUTORESEARCH</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="170" y="336" text-anchor="end">per loop</text>
      <!-- segment labels inside dominant segments -->
      <text class="fn-diagram__label fn-diagram__label--display" x="517" y="150" text-anchor="middle">83%</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="420" y="240" text-anchor="middle">75%</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="534" y="330" text-anchor="middle">91%</text>
      <!-- right-side cost profile descriptors -->
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="400" text-anchor="middle">cost normalized per row · three different answers to "corpus + 128 GB GPU"</text>
    </g>
  </svg>
  <figcaption>Each row sums to 100%. The difference is <em>where</em> the cost lives. Second Brain spends it at user-question time; the Wiki spends it once per source and then coasts on a pre-compiled artifact; Autoresearch spends it overnight, with the agent as the only user. Same substrate; three cost shapes.</figcaption>
</figure>

Read the diagram row-by-row. The first row is the RAG pattern everyone knows — retrieve, rerank, generate, on every question. If you use it rarely, it is free in practice; if you use it constantly, the per-query cost adds up. The second row inverts: read each source once, do a bunch of work to update a pile of markdown pages, then answer queries almost for free against the compiled wiki. The third row has no user at all — just a loop that edits code, runs a five-minute training, decides whether to keep the change, and repeats a hundred times overnight.

These are not sub-cases of the same thing. They are three genuinely different deals you can make with a 128 GB GPU and your own corpus.

## Fast-forwarding through the foundation

The seven foundation articles each installed one piece that all three arcs use. Reading them in order shows how the stack was built; reading them against the arc map shows what each piece costs *in* each arc. Here is the compressed version.

**[NIM first inference on DGX Spark](/articles/nim-first-inference-dgx-spark/).** Llama 3.1 8B running at `:8000` as an OpenAI-compatible endpoint, local-first. Second Brain's answerer, the Wiki's ingest writer, Autoresearch's driver — all the same binary, loaded once.

**[Nemotron Retriever embeddings, local](/articles/nemo-retriever-embeddings-local/).** 1 B embedding NIM at `:8001`. Produces 2048-D vectors for Second Brain's corpus, for the Wiki's page-similarity checks, for Autoresearch's trajectory log. One model, three semantic spaces.

**[pgvector on Spark](/articles/pgvector-on-spark/).** Postgres + HNSW + BM25 in one container. The shared vector store; the Wiki uses it most lightly because the wiki itself is the artifact.

**[Naive RAG on Spark](/articles/naive-rag-on-spark/).** Embed + top-K + strict-context prompt. The Second Brain MVP. The baseline the Wiki arc will explicitly argue against (*compile-time > query-time*). Autoresearch's first-pass trajectory retrieval.

**[Hybrid retrieval: BM25, dense, fusion, rerank](/articles/rerank-fusion-retrieval-on-spark/).** The retrieval-quality climb — 79% BM25 recall@5, 92% naive dense, 97% with the Nemotron reranker at K=10. Finding: retrieval isn't the bottleneck on AG News, an 8B strict-context generator is.

**[Bigger generator grounding](/articles/bigger-generator-grounding-on-spark/).** 8B local vs. 49B hosted vs. 70B hosted, same retrieval, 30-query qrels. Finding: bigger models over-refuse. The NVIDIA-native Nemotron-Super-49B refused *twice* as often as the 8B on perfect retrieval. The takeaway: generator size isn't the right lever for grounding — fine-tuning is.

**[Guardrails on the retrieval path](/articles/guardrails-on-the-retrieval-path/).** NeMo Guardrails installed once with three arc-specialized configs: PII scrub for Second Brain, write-policy for the Wiki, code-safety for Autoresearch. Fifteen synthetic queries, 100% block recall, 100% clean pass. One product, three policies.

Seven articles, one stack. Each one added a capability all three apps use. The pieces didn't fork; the *applications* do.

## What each track installs next

After this bridge the three tracks diverge. Each one names its own first article and takes responsibility for the specialization from that point forward.

**Second Brain, next article: S1 — Triton + TensorRT-LLM, query-latency profile.** The 8B NIM's latency is already good. Triton's TRT-LLM engine on a Spark will push token throughput and first-token latency hard enough that a Claude-Code-hosted Second Brain MCP tool answers faster than any hosted RAG — *because the retrieval is local too*. This is the Spark's unified-memory tell: the model and the vector store are in the same 128 GB pool, so the fetch doesn't cross PCI-e twice per query.

**LLM Wiki, next article: W1 — the wiki schema and the LLM bookkeeper.** No NVIDIA product earned here; the architecture piece. Defines the `index.md`, `log.md`, per-entity page structure from Karpathy's gist, and sketches the bookkeeper agent that updates 10–15 pages per incoming source. The product installs start in W2 (Curator for source sanitization).

**Autoresearch, next article: A1 — NeMo Framework on Spark.** The first training-side article. Validates that a full training-loop runtime fits on one Spark, that the 8B base model can be resumed from checkpoint, and that a five-minute evaluation (`val_bpb`) is a tight enough feedback signal for an agent to iterate on. The agent itself lands in A4.

The menu is three items. A reader who wants to build a private RAG answerer fast goes to S1. A reader who wants to turn a growing archive into a maintained knowledge base goes to W1. A reader who wants to run an agent overnight against training code goes to A1. All three can be read in parallel; the foundation is the same.

## Where each arc is the *weakest* choice

Honesty matters more here than in any single-product article, because picking the wrong arc wastes months. Each of the three is measurably the worst answer for specific use cases:

**Second Brain is the wrong arc if you re-ask the same thing every day.** Query-time RAG re-does retrieval and re-generates on every call. If the questions and sources are stable, you are paying for the same synthesis over and over. The Wiki eats that lunch: compile once, read many times, free per query. Use Second Brain when *the queries are new each time* — research over a corpus where you don't know yet what you'll ask.

**LLM Wiki is the wrong arc if your corpus changes faster than the wiki can recompile.** Every new source triggers a bookkeeper pass that updates 10–15 pages; if sources arrive every few seconds (Slack firehose, news feed), the compile loop never catches up and the wiki goes stale in a way that's hard to detect. Second Brain handles that shape cleanly — the corpus is the current state, the query is now.

**Autoresearch is the wrong arc if there's no measurable outcome in under ten minutes.** The loop is only worth running if the agent can distinguish a good edit from a bad one quickly. If your evaluation takes an hour, the agent explores 8 options overnight instead of 100, and the whole case for autonomy evaporates — you'd be better off with a human making slower but better-informed choices. Autoresearch belongs to problem classes with tight feedback signals.

None of these are criticisms of the arc; they're how to tell which one fits your problem. If the answer is genuinely *all three*, the foundation you've installed already supports that.

## The invitation

Pick a track. Read it through. Come back for the other two when the first one is running.

The arc detector in the `tech-writer` skill will prefer the foundation articles until all seven exist on disk; after this article lands, it will ask instead: *"Second Brain, LLM Wiki, or Autoresearch?"* A one-word answer routes the next article. A specific slug overrides the routing if a later piece calls to you first.

Reading in parallel is fine. Articles within a track build on each other; articles across tracks are independent after this point. The three Triton articles (S1, W4, A7) will cross-link — same product, three optimization profiles — as will the three Customizer articles (S2, W5, A8) and the three Evaluator articles (S3, W6, A9). Cross-track readers get the full topology; single-track readers get a clean spine.

## Closing — three tracks, measured in articles

Second Brain is four articles from here to an MCP-mounted private RAG tool in Claude Code. LLM Wiki is seven articles from here to an Obsidian-mounted knowledge base the 8B maintains at ingest. Autoresearch is nine articles from here to an agent that runs overnight against a training loop you don't have to supervise.

Same Spark. Same 128 GB. Same seven-product foundation. Three different answers to the same question about what one person should do with their own corpus and the first consumer machine on which all of this is *locally affordable*. Pick your arc — the detail starts in the next article of whichever track you chose.
