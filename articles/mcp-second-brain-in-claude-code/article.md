---
title: "Second Brain as a Tool — Wrapping the RAG Stack in MCP for Claude Code"
date: 2026-04-24
author: Manav Sehgal
product: NIM
stage: agentic
difficulty: intermediate
time_required: "~90 minutes — 30 min to design the tool surface, 30 min to wire FastMCP + pgvector, 15 min to register with Claude Code, 15 min for the demo and trace"
hardware: "NVIDIA DGX Spark"
tags: [mcp, claude-code, second-brain, rag, agentic, fastmcp, pgvector, nim, dgx-spark]
summary: "Closing the Second Brain arc. Four MCP tools wrap the RAG chain — embed, retrieve, optionally rerank, generate — and any Claude Code session anywhere on the box becomes a grounded research client. 200 lines of Python, one launcher, one .mcp.json entry."
signature: SecondBrainMcp
also_stages: [inference, dev-tools]
series: Second Brain
---

The previous article ([Ragas, Reranked](/articles/rag-eval-ragas-and-nemo-evaluator/)) closed with a scoreboard. Four variants, 44 held-out questions, the rerank variant landing at 4.27/5 with zero refusals. The chain works. The harder question is the one no eval table answers: *what do you actually do with a working Second Brain?*

The honest first answer for most personal-corpus RAG projects is "open a browser, type into a search box, scan the citations." That is fine. It is also a regression from where my day actually happens. My day happens in a Claude Code window — sometimes editing this very repo, sometimes inspecting an unrelated codebase, sometimes drafting an outline in `_drafts/`. The Second Brain is downstairs, in pgvector and a NIM container; my work is upstairs, in a terminal. A web search box would put two more clicks between a question and an answer that is already on this machine.

The fix is **MCP — the Model Context Protocol** — Anthropic's spec for letting any agent call out to a server full of named tools. Wrapping the Second Brain as four MCP tools (`search_blog`, `ask_blog`, `list_articles`, `read_article_chunk`), registering the server in a project-scope `.mcp.json`, and now the entire blog corpus is something the agent in front of me can reach for the same way it reaches for `Read` or `Grep`. The Second Brain stops being a destination. It becomes a verb.

## Why this matters for the personal AI power user

Three things change when a private corpus is exposed as MCP tools instead of a search UI.

**The corpus never leaves.** Every call lands on `127.0.0.1`. Embedding, vector search, rerank logits, generated answer — all of it stays inside the Spark's loopback. The only network round-trip in the whole chain is the hosted reranker (one 200ms POST to `ai.api.nvidia.com` carrying the question and ~20 candidate passages, gone the second the response returns). There is no "send my notes to the LLM" event happening here, which is exactly the boundary that prevents a personal-corpus assistant from ever existing on a laptop that talks to a cloud LLM.

**Composition replaces context.** A Claude Code session that has the Second Brain MCP available does not need to be told *"here is my blog, please use it as background."* The agent reads the tool descriptions in its system prompt at session start, and decides — turn by turn — whether the question in front of it is the kind that wants a `search_blog` first. Twelve articles' worth of architectural decisions stay queryable without taking up a single token of the agent's context until it actually reaches for them.

**The four-tool surface is portable.** The same MCP server that this Astro repo uses today wires unchanged into a Cursor session in another directory, into a Claude Desktop conversation, into the next CLI client to ship — anywhere the protocol is spoken. That portability is what justifies the 90 minutes of building it. A custom search UI would have been faster for *this* project; the MCP investment compounds across every agentic surface I'll use over the next year.

## Where MCP sits in the Second Brain stack

<figure class="fn-diagram" aria-label="Second Brain MCP architecture. Any Claude Code session on the Spark connects via stdio JSON-RPC to a single FastMCP server that exposes four tools — search_blog, ask_blog, list_articles, read_article_chunk. Each tool composes one or more of the existing backing services: NIM Nemotron-Embed-1B at port 8001, pgvector at port 5432, the hosted Llama 3.2 NV-RerankQA at ai.api.nvidia.com, and NIM Llama 3.1 8B at port 8000. The MCP server runs as a child process of the Claude Code session, started on demand and torn down at session end.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Hub-and-spoke diagram. Left: a claude-code client chip. Center accent: the second-brain MCP server. Right: four tool chips fanning out, each annotated with the backing services it composes." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-sb-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
        <stop offset="50%"  stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d-sb-accent" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d-sb-halo" cx="0.5" cy="0.5" r="0.65">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.16"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="40" y="20" width="820" height="400" rx="10" fill="url(#d-sb-band)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 220 220 L 360 220"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 540 220 L 660 80"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 540 220 L 660 175"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 540 220 L 660 270"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 540 220 L 660 360"/>
    </g>
    <rect x="360" y="160" width="180" height="120" rx="10" fill="url(#d-sb-halo)" stroke="none"/>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="170" width="160" height="100" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="360" y="160" width="180" height="120" rx="10" style="fill: url(#d-sb-accent)"/>
      <rect class="fn-diagram__node" x="660" y="40" width="200" height="80" rx="8"/>
      <rect class="fn-diagram__node" x="660" y="135" width="200" height="80" rx="8"/>
      <rect class="fn-diagram__node" x="660" y="230" width="200" height="80" rx="8"/>
      <rect class="fn-diagram__node" x="660" y="320" width="200" height="80" rx="8"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="140" y="208" text-anchor="middle" font-weight="600">CLAUDE CODE</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="140" y="227" text-anchor="middle" font-size="10">any session</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="140" y="245" text-anchor="middle" font-size="10">on the Spark</text>
      <text class="fn-diagram__label" x="450" y="207" text-anchor="middle" font-weight="700">second-brain MCP</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="450" y="226" text-anchor="middle" font-size="10">FastMCP · stdio</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="450" y="244" text-anchor="middle" font-size="10">JSON-RPC 2.0</text>
      <text class="fn-diagram__label" x="760" y="68" text-anchor="middle" font-weight="600">search_blog</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="760" y="86" text-anchor="middle" font-size="10">embed → pgvector → rerank</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="760" y="102" text-anchor="middle" font-size="10">returns ranked chunks</text>
      <text class="fn-diagram__label" x="760" y="163" text-anchor="middle" font-weight="700">ask_blog</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="760" y="181" text-anchor="middle" font-size="10">search_blog → NIM 8B</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="760" y="197" text-anchor="middle" font-size="10">grounded answer + cites</text>
      <text class="fn-diagram__label" x="760" y="258" text-anchor="middle" font-weight="600">list_articles</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="760" y="276" text-anchor="middle" font-size="10">pgvector aggregate</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="760" y="292" text-anchor="middle" font-size="10">discovery surface</text>
      <text class="fn-diagram__label" x="760" y="348" text-anchor="middle" font-weight="600">read_article_chunk</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="760" y="366" text-anchor="middle" font-size="10">pgvector lookup</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="760" y="382" text-anchor="middle" font-size="10">verbatim chunk</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="290" y="212" text-anchor="middle" font-size="10" fill="var(--svg-text-faint)">spawn</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="290" y="230" text-anchor="middle" font-size="10" fill="var(--svg-text-faint)">stdio</text>
    </g>
  </svg>
  <figcaption>The whole second-brain MCP server is one Python process started on demand by Claude Code, talking JSON-RPC over a pipe pair. The four tools are progressively richer compositions of the existing backing services: <code>list_articles</code> is one SQL aggregate, <code>read_article_chunk</code> is one row lookup, <code>search_blog</code> walks embed → pgvector → optional rerank, and <code>ask_blog</code> stacks <code>search_blog</code> on top of NIM 8B. Adding a fifth tool means deciding what new composition is worth its place on the surface — not whether the chain underneath supports it.</figcaption>
</figure>

The protocol is simpler than the wrapping makes it sound. MCP is JSON-RPC 2.0 with a small set of well-known methods: `initialize`, `tools/list`, `tools/call`, `notifications/initialized`. A server announces capabilities, the client lists tools, the client calls tools, the server returns content. There is a streaming HTTP transport for remote services and a stdio transport for local ones; for a server that runs on the same machine as the client, stdio wins on every dimension — no port, no auth, no service-manager unit, no certificate. Claude Code spawns the launcher script, writes JSON-RPC frames to its stdin, reads responses from its stdout, and tears the process down at session end.

The four tools are not the only possible surface. A naive implementation would expose nine — one per backing endpoint plus the raw SQL — and call that "complete API coverage". A better one stops at the four compositions a working agent actually wants. The `search_blog`/`ask_blog` split is the meaningful one: `search_blog` returns chunks the agent can reason over and combine, `ask_blog` synthesizes for the impatient case where the agent just wants the answer with citations and isn't going to do anything fancier with the raw passages. The remaining two — `list_articles` for discovery and `read_article_chunk` for verbatim follow-up — exist because the agent will sometimes want them, and adding them costs nothing once the connection to pgvector is open.

## Building the server in 200 lines of FastMCP

The whole server is [`evidence/server.py`](./evidence/server.py) — 250 lines including imports, type hints, and four tool docstrings. The skeleton is unsurprising: import the SDK, instantiate `FastMCP("second-brain")`, decorate four functions with `@mcp.tool(...)`, call `mcp.run()` at the bottom. The interesting part is the *backing-service plumbing* underneath the decorators, because each tool lives at a different point on the staleness/cost axis.

**Embedding.** The query side of `nemo-retriever-embeddings-local` runs at port 8001. One urllib POST per query, 30-millisecond p50 in practice. The MCP server has no state of its own — it embeds afresh on every tool call. That keeps the design honest: there is no "embedding cache layer" to invalidate.

**Vector search.** The first version of this server shelled out to `docker exec pgvector psql ...`, copied directly from [`retrieve.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/articles/rag-eval-ragas-and-nemo-evaluator/evidence/retrieve.py) where it does its job inside the eval harness. That collapsed under MCP's process model — the server is a *long-lived* child of Claude Code, not a one-shot script, and forking a `docker exec` per query for the rest of the session is the kind of choice that becomes a noticeable bottleneck a week later. Replacement: one `psycopg.connect(PG_DSN)` against `127.0.0.1:5432` per tool call, parameterized queries, no shell quoting, no docker plumbing. The pgvector container exposes the port; the connection lives inside the python process.

**Rerank.** The hosted Nemotron RerankQA at `ai.api.nvidia.com` is the one cloud dependency in the chain — the [rerank-fusion article](/articles/rerank-fusion-retrieval-on-spark/) called this out as a compat gap, and it persists. The server reads `NGC_API_KEY` from its environment; the launcher script sources `~/.nim/secrets.env` before exec'ing python so the secret never appears in `.mcp.json` itself. When the reranker eventually ships as a Spark-runnable NIM, this part of the server changes one URL and the cloud round-trip disappears.

**Generation.** NIM Llama 3.1 8B at port 8000, top-3 chunks with each chunk trimmed to 500 words to stay safely under the 8192-token context ceiling — the ceiling that bit the eval harness as an opaque HTTP 400 last week and got noted as a project-wide landmine. The same trim, applied here at tool-call time, prevents a curious agent from accidentally constructing a context too big for the answerer. The error message on overflow now points at the cause explicitly:

```python
except urllib.error.HTTPError as e:
    detail = e.read().decode("utf-8", errors="replace")[:300]
    raise RuntimeError(
        f"NIM HTTP {e.code}: {detail}. The 8B has an 8192-token context "
        "ceiling; if this is HTTP 400, try a smaller top_k or shorter chunks."
    ) from None
```

That single block — which would normally not exist in production code, since the validation should already prevent it — pays for itself the first time it surfaces in a Claude Code session. An actionable error keeps the agent from re-trying the same broken call three times before giving up. *Errors are an interface*, more so for an MCP tool than for any other code in the chain, because the only consumer is another LLM.

The four tool decorators look like this — `search_blog` is representative:

```python
@mcp.tool(
    description=(
        "Semantic search over Manav's ai-field-notes blog corpus (articles on "
        "running AI locally on the NVIDIA DGX Spark). Returns top-k chunks "
        "with slug, chunk index, and prose. Use this to ground answers in the "
        "blog, find related articles, or pull verbatim excerpts. Set "
        "rerank=true (default) for high-precision retrieval; rerank=false is "
        "naive cosine and is faster but less accurate."
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
def search_blog(query: str, top_k: int = 5, rerank: bool = True) -> dict:
    ...
```

The `description` matters more than any other field on the surface — it is the only thing the calling agent reads at session start to decide whether this tool is the right one for a given turn. The temptation is to keep it short. Resist. A good description names what the tool does, when to reach for it (vs. a sibling tool), and what its sharp edges are. The cost is a few hundred tokens in the agent's context budget; the payoff is the agent picking `search_blog` instead of `WebSearch` for questions about the user's own writing.

The `annotations` block is the under-used part of the MCP spec. `readOnlyHint: True` tells the client this tool can be safely auto-allowed inside Claude Code's permission system — the user does not need to be prompted on every call the way a `git push` or `rm -rf` would. `idempotentHint: True` lets the client batch or retry on transport errors. `openWorldHint: False` tells the client the tool returns deterministic, scoped data (a corpus, not the open web), which affects how the agent reasons about freshness. None of the four tools mutate anything, so all four carry the same annotation triple. A future `ingest_blog` tool would flip those bits the moment it lands on the surface.

## Wiring it into Claude Code

Two artifacts. The launcher at `evidence/launch.sh`:

```bash
#!/usr/bin/env bash
set -eu
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$HOME/.nim/secrets.env" ]; then
  set -a
  . "$HOME/.nim/secrets.env"
  set +a
fi
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/server.py"
```

Three lines of work — find the script's own directory, source the NGC API key into the env, exec the venv's python at the server. `set -a` is the part that is easy to get wrong; bare `source` does not export to subprocess children, and the rerank tool would silently fail. The launcher is at `/home/nvidia/second-brain-mcp/launch.sh` outside the article repo, with a copy in [`evidence/`](./evidence/launch.sh) for reference.

The project-scope `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "second-brain": {
      "command": "/home/nvidia/second-brain-mcp/launch.sh",
      "args": [],
      "env": {}
    }
  }
}
```

Eight lines. Project-scope means anyone running Claude Code from this directory gets the MCP automatically; user-scope lives in `~/.claude.json` and follows me into every directory. The choice is not arbitrary — the Second Brain is a property of *this* corpus, so binding it to the repo that contains the corpus is the correct scope. A future `wiki-mcp` (the `W7` arc closer) would similarly bind to the wiki repo it serves.

A fresh Claude Code session in the repo confirms the registration:

```
$ claude mcp list
Checking MCP server health…

claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - ✓ Connected
claude.ai Google Calendar: https://calendarmcp.googleapis.com/mcp/v1 - ✓ Connected
claude.ai Google Drive: https://drivemcp.googleapis.com/mcp/v1 - ✓ Connected
playwright: npx -y @playwright/mcp@latest --executable-path … - ✓ Connected
second-brain: /home/nvidia/second-brain-mcp/launch.sh  - ✓ Connected
```

The `✓ Connected` status is the result of Claude Code spawning the launcher, completing the `initialize` handshake, listing the four tools, and tearing the process down — all in the time it took to print that line. The same handshake will happen again the moment an agent in the session decides to call one of the tools.

## Verification — what success looks like on Spark

The clean way to verify the chain end-to-end is to ask Claude Code itself a question that requires the corpus, in `--print` mode so the whole transcript can be captured to a file:

```bash
echo "How fast did the first NIM inference run on the Spark, and was that \
latency-bound or throughput-bound? Cite the article slug." \
  | claude -p \
      --output-format stream-json \
      --include-partial-messages --verbose \
      --permission-mode bypassPermissions \
      --allowedTools 'mcp__second-brain__list_articles' \
                     'mcp__second-brain__search_blog' \
                     'mcp__second-brain__ask_blog' \
                     'mcp__second-brain__read_article_chunk' \
  > evidence/claude_code_stream.jsonl
```

The full JSONL stream is preserved at [`evidence/claude_code_stream.jsonl`](./evidence/claude_code_stream.jsonl) (116 KB). Three turns matter, transcribed here:

```
TOOL_USE: mcp__second-brain__ask_blog({
  "question": "How fast did the first NIM inference run on the DGX Spark,
               and was that latency-bound or throughput-bound?",
  "top_k": 3, "rerank": true
})
TOOL_RESULT: {
  "answer": "The first NIM inference run on the Spark answered a 96-token
             completion in 8.9 seconds (24.84 tokens/sec). It was
             latency-bound; the per-token decode rate did not improve when
             NIM_GPU_MEM_FRACTION was raised from 0.5 to 0.8 …",
  "sources": [{"slug": "nim-first-inference-dgx-spark", "chunk_idx": 1}, …],
  "wall_s": 6.4, "generate_wall_s": 4.5,
  "prompt_tokens": 3014, "completion_tokens": 142
}
TOOL_USE: mcp__second-brain__search_blog({
  "query": "NIM first inference latency-bound throughput-bound single-user
            concurrency", "top_k": 5
})
TOOL_RESULT: { 5 ranked chunks from nim-first-inference-dgx-spark, … }
```

Two turns. The first reaches for `ask_blog` because the question shape is "give me the answer with citations". The second reaches for `search_blog` to pull verbatim passages and check the synthesized answer against them — the agent is doing its own grounding pass before producing prose. The final assistant message is a 250-word answer that names the right number (24.8 t/s), names the right gotcha (the GPU-memory-fraction non-effect), and cites `nim-first-inference-dgx-spark` — exactly the slug `ask_blog` returned in the first turn.

End-to-end wall clock: **18.5 seconds**, three agent turns, $0.32 in Claude API tokens. About 6.4 seconds of that lives in the MCP server (one `ask_blog` round-trip plus one `search_blog`). The rest is Claude reasoning over the tool output and writing the final answer. The interactive client returns an answer in less than 20 seconds for a question that, without the MCP, would require the agent to either guess from training data or fall back to an unproductive web search.

A complementary trace is at [`evidence/demo_trace.jsonl`](./evidence/demo_trace.jsonl) — the [`evidence/demo_trace.py`](./evidence/demo_trace.py) harness drives the launcher directly, exercising all four tools without going through Claude Code. That trace is the cleaner artifact for understanding what each tool returns; the streamed Claude Code trace is the more interesting artifact for understanding how an agent *uses* the surface.

## Tradeoffs — what the four-tool surface leaves on the table

**Staleness is a property of the corpus, not the server.** The MCP server reads from `blog_chunks` whatever pgvector has at the moment of the call. Right now that table holds 12 articles — the corpus as of the [Ragas eval ingest](/articles/rag-eval-ragas-and-nemo-evaluator/), one article behind today's count. An `ask_blog` question about the rerank-fusion-retrieval scoreboard returns a grounded answer; the same question about *this* article's MCP design returns "the provided context does not contain the answer." That refusal is the system working: the agent did not hallucinate from adjacent chunks, the strict-context system prompt held. A `cron`-driven `ingest_blog.py` that re-embeds on every git push would close the gap to under a minute. Today the gap is "as long as it has been since the last manual ingest", which is fine for a personal blog and would be unacceptable for any corpus where readers expect freshness.

**Refusal vs. hallucination, in the small.** The same refusal mechanism that prevents made-up answers also prevents partially-grounded ones. If `search_blog` returns three chunks where two are off-topic and one is a perfect hit, the strict-context prompt may still refuse, because the prompt was written to err toward refusal. There is a knob here — relaxed refusals, paragraph-citations instead of slug-citations, partial-credit answers — and the MCP surface deliberately does not expose it. A future article in this arc could add a `mode: "strict" | "lenient"` parameter to `ask_blog`. For now the strict default is the right floor.

**The hosted reranker is the one remaining cloud dep.** Every `rerank=True` call hits `ai.api.nvidia.com` for one ~200ms round-trip. That is the [F5 compat gap](/articles/rerank-fusion-retrieval-on-spark/) showing up at the application layer: when the model finally ships as a Spark-runnable NIM (Triton or vLLM-backed), the URL in `server.py` changes and the chain becomes fully local. Until then, anyone pulling this MCP server into a stricter-privacy setting can pass `rerank=False` and accept the [P@3 drop from 96% to 66%](/articles/rag-eval-ragas-and-nemo-evaluator/) the eval already measured.

**The four tools are not a complete API.** A reasonable agent would also benefit from `find_related_chunks(slug, chunk_idx, k)` — embedding lookup centered on an existing chunk for "what else in the corpus discusses this idea" — and from `cite(slug, chunk_idx)` returning a markdown link the agent can drop directly into prose. Both are additions of 30 lines each and were left out of the first cut to keep the surface small enough to argue with. Tool surfaces, like APIs, are easier to grow than to shrink.

**Process model has a wrinkle.** The launcher script is invoked fresh on every Claude Code session start, which means a per-session ~600ms cost to import psycopg, FastMCP, and the python runtime. For interactive use this is invisible; for a CI job that calls Claude Code dozens of times in series, it is not. If that becomes a real cost, the fix is a long-running server bound to a Unix socket and a tiny `claude_code_proxy` MCP that forwards tool calls — a streaming-HTTP-transport variant of the same server, wearing different transport clothes.

## What this unlocks

**Architecture autocomplete.** When I am drafting a new article and reach a paragraph where I want to claim *"as the bigger-generator article showed, going from 8B to 49B costs more refusals than it earns correctness"*, I can ask the agent to verify the claim against the actual source. The MCP `ask_blog` returns the grounded answer with the slug; if my recollection was wrong, the answer corrects me before the wrong claim ships. This is the use case I will reach for daily.

**Cross-session memory without a vector DB per app.** The same MCP works from a Claude Code session that is editing this Astro repo, from one editing my Obsidian vault, from one I haven't started yet. The corpus is one place; the agents are many. When the [LLM Wiki MCP](/articles/one-substrate-three-apps/) ships in the W7 article, both servers will register on the same `.mcp.json` and an agent can do `search_blog` for the source-of-truth essay and `query_wiki` for the compiled summary in the same turn — the Karpathy-gist read-side, with the Spark doing the inference for both.

**A teachable surface for what agentic software architecture looks like at the edge.** The four tools are a small, complete artifact someone reading this article could re-implement against their own corpus in an afternoon — embed model + vector store + (optional rerank) + chat model, wrapped in any MCP SDK they like. The lesson is not the specific Python; it is the *shape*: corpus is local, tool surface is small and strict, descriptions are written for a calling agent (not a human), and errors are written to keep the agent un-stuck. That is the shape every personal-AI tool surface on the Spark will take.

## Closing — Second Brain, end-to-end

The Second Brain track is complete. **S1** ([Triton + TRT-LLM for query latency](/articles/trtllm-and-triton-on-spark/)) made the answerer fast. **S2** ([LoRA on your own Q&A](/articles/lora-on-your-own-qa-pairs/)) gave it the user's voice. **S3** ([Ragas + NeMo Evaluator](/articles/rag-eval-ragas-and-nemo-evaluator/)) showed retrieval quality is the lever. **S4** — this article — wrapped the chain as four MCP tools so any Claude Code session can call it without leaving the box.

**Second Brain now:** a brain (NIM 8B), a memory (pgvector + 12 articles), a measured-good ranker, and a tool surface (four MCP calls). What started as a curiosity in [F1](/articles/nim-first-inference-dgx-spark/) is, six months in, a daily-use research assistant that answers questions in 6.4 seconds against my own writing without sending a single token off the box.

The two sibling arcs remain. **LLM Wiki (W1–W7)** picks up next, starting with `wiki-schema-and-llm-bookkeeper` — the LLM as ingest-time author of a markdown knowledge base, the inverted-RAG economics that compile at write-time so query-time is free. **Autoresearch (A1–A9)** is patient on the bench, waiting for a NeMo Framework + agent-loop article to kick off the overnight-experiment cadence the 128 GB pool was bought for.

Three apps, one substrate, one Spark — and now the first of the three has a tool you can call from anywhere on the box. Next up: deciding whether to compile or to query — the Wiki arc opens.
