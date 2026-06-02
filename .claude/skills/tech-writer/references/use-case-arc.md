# Use-case arcs — the running threads across ai-field-notes articles

The ai-field-notes blog is not a collection of isolated product reviews. It follows **three end-to-end applications** that share a substrate: each new article adds one NVIDIA stack product, and most articles serve *all three* apps until the pipelines fork. This reference is the source of truth for the three arcs.

When the skill drafts a new article and no specific editorial overlay was provided by the user, use these arcs as the default overlay. Per-article overlays from the user always override the arcs' default framing — the arcs are a floor, not a ceiling.

---

## The three arcs at a glance

### Arc 1 — "Second Brain" (query-time RAG)

A personal research RAG assistant. Asks questions against the user's own corpus (PDFs, research notes, local code, browser bookmarks, chat logs) and returns grounded, cited answers.

**Thesis.** *RAG over your own corpus is the one configuration where cloud LLMs measurably lose.* Privacy flips (your archive never leaves the box), data gravity flips (the corpus is already here, the GPU comes to it), and latency-of-iteration flips (re-embed in minutes, re-retrieve in milliseconds).

**Cost profile.** Cheap at ingest (just embed). Expensive per query (retrieve + rerank + generate). Good when queries are rare and sources are fresh-enough at retrieval time.

### Arc 2 — "Machine that Builds Machines" (AI systems that build, train, supervise other AI)

Renamed from *Autoresearch* on 2026-05-08 and broadened to cover the full `/book/` Part-4 *Vision* thesis (Ch10 "The Machine That Builds Machines," Ch11 "The Meta-Program"). The original karpathy-style autoresearch loop — overnight ML experimentation that edits `train.py`, measures `val_bpb`, keeps/reverts, repeats ~100× — is the spine of A1–A9 and the first installment of the arc. The renamed-and-broadened bucket also pulls in **self-improvement loops** (RL on agent trajectories — GRPO, GiGPO, T²PO; test-time distillation), **synthetic-data pipelines** (persona-driven task synthesis, agent-generated training corpora), **codegen / SDLC agents** (multi-turn agents on ClawGym / SWE-bench / AcademiClaw / Workspace-Bench shapes), and **alignment-engineering primitives** (provenance graphs, intent traces, knowledge graphs over codebases — what 8090.ai sells as a $1M/yr managed service). Same agent thesis, wider tent.

**Thesis.** *AI that builds AI is the one configuration where the Spark's 128 GB unified memory beats the cloud per dollar.* The pool holds an 8B driver + a 70B critic simultaneously; an LLM-driven research loop runs 100 experiments overnight without a bill, a rate limit, or a network hop. Self-improvement loops — RL on the agent's own trajectories, synthetic data the agent generated for itself, distillation from runs the agent already paid for — close the cost loop without a paid API.

**Cost profile.** No per-query cost — the agent is the user. The cost is wall-clock + the willingness to let the Spark run overnight. Fits compounding workloads (overnight ML experimentation, self-distillation, persona-driven synth corpora, multi-agent swarms) where each iteration consumes the previous iteration's output.

**Frontier Scout articles in the broader bucket.** Articles published under the `Frontier Scout` *series* (paper reproductions like `clawgym-on-spark`, `clawgym-on-spark-grpo`, `t2po-uncertainty-guided-rl-on-spark`) are MTBM-shaped in *thesis* but Frontier-Scout-shaped in *origin* — they keep their `series: Frontier Scout` frontmatter; the Vision-arc connection is editorial, not schema-tagged.

### Arc 3 — "LLM Wiki" (compile-time synthesis, inverted RAG)

An LLM-maintained personal knowledge base inspired by [Karpathy's LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The wiki (markdown pages, `index.md`, `log.md`, per-entity pages) is the product. At ingest, the LLM reads a new source, extracts entities and facts, updates 10–15 pages, cross-references them, and periodically lints for contradictions and orphans. Queries hit the *wiki*, not the raw sources — synthesis already happened.

**Thesis.** *The Spark makes ingest-time synthesis economically viable for one person.* Compiling a wiki over your corpus is "free" when you own the GPU — the LLM pays no API cost and has no rate limit, so it can afford to update 15 pages per source without counting tokens. Cloud LLMs cannot; the arithmetic breaks at the first 1,000 sources.

**Cost profile.** Expensive at ingest (bulk LLM work across many pages). Near-free per query (wiki is already compiled). Good when queries are frequent and the value of a polished, linted artifact compounds.

### Why three arcs and not one

The three arcs are **different answers to the same question**: *what do you do with your own corpus + a 128 GB GPU?*

- Second Brain — treat the corpus as read-only; do synthesis per query. Closest to classic cloud RAG, easiest to wire up, pays per-query.
- LLM Wiki — treat the corpus as a feed; produce a compiled artifact at ingest. Inverted economics: pays per-source, free per-query.
- Machine that Builds Machines — no corpus, no queries — the agent generates its own targets (training runs, code edits, agent trajectories) and improves on them overnight. Same LLM driver pointed at code, weights, or trajectories instead of text.

Writing all three in the blog lets readers see the **shape of the cost space**: they pick the variant whose cost profile matches their use. That's more valuable than any single implementation.

---

## Why the three arcs share a substrate

Different at the top, shared at the bottom:

| Shared piece | Second Brain | LLM Wiki | Machine that Builds Machines |
|---|---|---|---|
| NIM Llama 3.1 8B | Answers queries | Ingests sources → writes wiki pages | Drives experiment loop |
| NeMo Retriever embeddings | Embed corpus | De-dup wiki pages, find related concepts | Embed trajectory log |
| pgvector | Corpus vectors | Wiki cross-reference index (optional; markdown can also stand alone) | Trajectory vectors |
| Reranker NIM | Best retrieved passages | Best related wiki pages on a query | Most relevant prior experiments |
| NeMo Guardrails | PII scrub on retrieved context | Source-sanitization at ingest + wiki-write policy | Code-safety rails on `train.py` edits |
| Triton + TRT-LLM | Faster query-time generation | **Ingest throughput** (batched ingest is the hot path) | Agent-loop latency |
| NeMo Customizer | LoRA on Q&A pairs | LoRA on user's wiki-writing style | Distill architect behavior from good trajectories |
| NeMo Evaluator | RAG faithfulness, relevance | Wiki consistency, coverage, source-faithfulness | Trajectory quality |
| MCP server | Second Brain as a Claude Code tool | Wiki-ingest / wiki-query as tools, optionally Obsidian surface | MTBM agent loop as a Claude Code tool |

The three arcs together exercise the full NVIDIA stack:

- **Inference-side NeMo** (Retriever, Guardrails, Customizer-for-inference) — all three arcs use it.
- **Training-side NeMo** (Framework, Curator for training data, Customizer for base-model updates) — MTBM drives it; the other two benefit where they touch data prep.
- **Ingest-side NeMo** (Curator for source sanitization, Guardrails for write policy) — Wiki uses most heavily.
- **Evaluation-side NeMo** (Evaluator) — all three use it on different test sets.

Triton's multi-model serving becomes genuinely load-bearing when the agent arcs run a 70B critic + 8B driver simultaneously — that's where the Spark's 128 GB earns its line on the spec sheet.

---

## The article progression

Structured as: **shared foundation** (`F1–F7`, serve all three arcs) → **bridge article** (`B` — declares the fork) → **three parallel tracks**.

**Arc labels vs. site ordinals.** The `F` / `B` / `S` / `W` / `A` labels in this file are arc-internal — they name the position within the install chain or the track. The site renders a separate `№NN` ordinal derived from git first-add time (see `src/lib/article-order.mjs`), and that `№` is what prose cross-references must use. The two sets drift apart whenever articles outside the arcs are published (e.g., the preamble pieces `dgx-spark-day-one-access-first` and `nemoclaw-vs-openclaw-dgx-spark` that precede the foundation get `№01` and `№02`, so `F1` in this file is `№03` on the site). Do not hand-write site ordinals in this reference; look them up from git when prose needs one, or prefer slug-based cross-references.

### Shared foundation (`F1–F7`)

| Label | Slug | Product earned | Role in each arc |
|---|---|---|---|
| F1 | `nim-first-inference-dgx-spark` | NIM + NGC (Llama 3.1 8B Instruct) | SB: the answerer. W: the ingest writer. A: the agent driver. |
| F2 | `nemo-retriever-embeddings-local` | NeMo Retriever embedding NIM | SB: corpus vectors. W: page-similarity for dedup + cross-refs. A: trajectory vectors. |
| F3 | `pgvector-on-spark` | pgvector | Shared vector store — all three use it, W most lightly. |
| F4 | `naive-rag-on-spark` | Glue + first eval baseline | SB: MVP pipeline. W: the baseline this arc will explicitly reject (compile-time > query-time). A: first-pass trajectory retrieval. |
| F5 | `rerank-fusion-retrieval-on-spark` | NeMo Retriever rerank NIM + BM25 + RRF | SB: better retrieved passages. W: better related-page suggestions. A: better prior-experiment lookup. |
| F6 | `bigger-generator-grounding-on-spark` | 49B Nemotron-Super + 70B Llama 3.3 (hosted A/B vs. 8B local) | SB: measures where bigger helps on grounded QA — finding: bigger over-refuses, fine-tuning is the real lever. W: same conclusion applies to read-time generation. A: critic-NIM story reshaped — bigger alone doesn't heal driver refusals. |
| F7 | `guardrails-on-the-retrieval-path` | NeMo Guardrails | SB: retrieval-side PII scrub. W: ingest-side + write-path policy. A: code-safety rails. One product, three policy specializations. |

### Bridge (`B`)

| Label | Slug | Role |
|---|---|---|
| B | `one-substrate-three-apps` | Declare the fork. Hub-and-spoke diagram: shared foundation in the center, three apps as spokes. Short essay: **three different answers to the same question — what do you do with your corpus + a 128 GB GPU?** |

### Second Brain track (S1–S4)

| # | Slug (tentative) | Product earned | Stage |
|---|---|---|---|
| S1 | `triton-trtllm-for-query-latency` | Triton + TensorRT-LLM (query-latency profile) | deployment |
| S2 | `lora-on-your-own-qa-pairs` | NeMo Customizer (inference-side LoRA) | fine-tuning |
| S3 | `rag-eval-ragas-and-nemo-evaluator` | NeMo Evaluator + Ragas | observability |
| S4 | `mcp-second-brain-in-claude-code` | MCP surface | agentic |

### LLM Wiki track (W1–W7)

| # | Slug (tentative) | Product earned | Stage |
|---|---|---|---|
| W1 | `wiki-schema-and-llm-bookkeeper` | LLM as wiki-writer (no new product; architecture piece) | inference |
| W2 | `wiki-ingest-with-nemo-curator` | NeMo Curator (source sanitization, dedup, quality filter) | inference |
| W3 | `wiki-lint-agent` | NeMo Agent Toolkit (lint/consistency agent) | agentic |
| W4 | `triton-trtllm-for-ingest-throughput` | Triton + TRT-LLM (ingest-throughput profile — different optimization than S1) | deployment |
| W5 | `customizer-lora-for-wiki-style` | NeMo Customizer (LoRA for wiki voice) | fine-tuning |
| W6 | `wiki-eval-coverage-consistency-faithfulness` | NeMo Evaluator (Wiki-specific metrics) | observability |
| W7 | `mcp-wiki-in-obsidian-and-claude-code` | MCP surface (Obsidian integration called out, per Karpathy's gist) | agentic |

### Machine that Builds Machines track (A1–A9)

The `A` prefix and slugs (e.g. `autoresearch-agent-loop`) are preserved from the predecessor *Autoresearch* arc — slugs are URLs and survive arc renames. Future MTBM articles outside the karpathy-loop installments may use different slugs.

| # | Slug (tentative) | Product earned | Stage |
|---|---|---|---|
| A1 | `nemo-framework-on-spark` | NeMo Framework (training runtime) | training |
| A2 | `baseline-training-loop-on-spark` | PyTorch + TransformerEngine baseline | training |
| A3 | `nemo-curator-training-data-prep` | NeMo Curator (training-data specialization) | training |
| A4 | `autoresearch-agent-loop` | NeMo Agent Toolkit + edit/run/measure/decide cycle | agentic |
| A5 | `guardrails-for-code-generation` | NeMo Guardrails (code-edit policy specialization) | agentic |
| A6 | `critic-nim-70b-on-spark` | 70B-class NIM + Triton multi-model | deployment |
| A7 | `triton-trtllm-for-agent-latency` | Triton + TRT-LLM (agent-loop-latency profile) | deployment |
| A8 | `distill-architect-lora-from-trajectories` | NeMo Customizer (training-side LoRA) | fine-tuning |
| A9 | `trajectory-eval-is-the-agent-flailing` | NeMo Evaluator (agentic-eval specialization) | observability |

Optional closer: `mcp-autoresearch-in-claude-code` — write if it adds signal.

### Cross-track honesty

When a track reaches a product already covered in another track, **acknowledge the sibling article and specialize, don't re-walk the install**. The three Triton+TRT-LLM articles (S1, W4, A7) are the clearest example — same product, three optimization profiles (query latency vs. ingest throughput vs. agent-loop latency). Same for the three Customizer articles (S2, W5, A8) and the three Evaluator articles (S3, W6, A9). Cross-link generously; readers following only one arc should not have to guess why the same product reappears.

---

## Harnesses series (H1–H6)

The fourth running thread is a **series, not one of the three arcs** — same shape as Frontier Scout (a series whose articles spread across `agentic` / `deployment` / `inference` / `observability` stages with no dedicated stage). Where the three arcs answer *what you run* on the Spark, Harnesses answers *what you drive it from*: the **cockpit**. Take a frontier open-source agent harness, tune its serving lane to the 128 GB envelope, harden it, and wire it to the box itself via fieldkit-as-MCP. **Hermes Agent (Nous Research, MIT) is entry #1**; a second harness will get its own spec + sub-arc later. Source of truth: `_SPECS/hermes-harness-v1.md`.

**The defensible angle is NIM-first** — every other Spark Hermes write-up documents Ollama; this series leads with the tuned NIM Nemotron lane (the project's `NIM_MAX_BATCH_SIZE=32` → 325 tok/s knob).

| # | Slug | Thesis | Stage (also_stages) | Spine? |
|---|---|---|---|---|
| H1 | `the-hermes-harness-on-spark` | Install Hermes; first local agent turn against NIM Nemotron, no API key. The cockpit, NIM-first. | agentic (inference, deployment) | **must** |
| H2 | `hermes-serving-lane-on-spark` | Right-size the lane — Qwen3 35B-A3B MoE vs 27B dense on 128 GB; tok/s, sustained-load, **tool-call reliability**. | deployment (inference) | **must** |
| H3 | `hardening-the-hermes-harness-on-spark` | Guardrails on the loop, tool scoping, secret hygiene, restart — a harness you'd leave running on your desk. | agentic (observability) | **must** |
| H4 (keystone) | `hermes-drives-the-spark-via-fieldkit-mcp` | Expose `fieldkit` as MCP tools → Hermes quantizes / measures / publishes / retrieves. MTBM, productized. | agentic (dev-tools, deployment) | **must** |
| H5 | `hermes-vertical-router-on-spark` | One harness, five experts — route per-domain to the 5 Orionfold GGUFs, all local, zero new model work. | inference (agentic, deployment) | nice |
| H6 | `hermes-cost-routing-local-and-openrouter` | The viability close: 3-tier routing (local NIM $0 → OpenRouter cheap → frontier) with a **measured** dollar curve. | deployment (observability, agentic) | nice |

**The spine is H1–H4** (cockpit installed → fast → safe → driving the box) — a complete story on its own. **H5/H6 are leverage multipliers, explicitly optional.** Two hard sequencing rules: **H3 (harden) ships before H4 (MCP write surface)** — never expose the fieldkit MCP surface to an un-hardened Hermes; and the **Session-1 schema scaffold** (the `Harnesses` series + `harness`/`skill` kinds + the `[series].astro` `SERIES_COPY` entry) lands before any H-article.

**Threading (editorial, not schema).** H4 is the "Machine that Builds Machines" expression and the Second-Brain-over-MCP bridge, but it keeps `series: Harnesses` — the MTBM/Second-Brain ties are **editorial cross-links + `book_chapters: [10, 11]`**, never a `series:` retag (the Frontier-Scout precedent). H4 opens by acknowledging `autoresearch-agent-loop` and cross-links `mcp-second-brain-in-claude-code` (same MCP tool surface, two harnesses).

## "Where are we now?" — detecting the next article

The skill picks the next article without asking the user to recite anything:

1. List `/home/nvidia/ainative-business.github.io/articles/*/` — the published articles. Preamble pieces outside the arcs (e.g., `dgx-spark-day-one-access-first`, `nemoclaw-vs-openclaw-dgx-spark`) are published and numbered on the site but do not participate in this walk.
2. Walk the **shared foundation** (`F1` → `F7`, then `B`) in order by slug. If any foundation slug does not exist yet, **that's the next article**, regardless of which arc the user names. Foundation always completes first.
3. Once the foundation is complete, the user must name the arc — *"next in the Second Brain"*, *"next in the Wiki"*, or *"next in MTBM"* (also accept the legacy term *"next in Autoresearch"*). The skill walks the relevant track (S1–S4, W1–W7, or A1–A9) and picks the first slug that doesn't exist.
4. **Harnesses series:** when the user says *"next in Harnesses"* / *"next Hermes article"* / names a harness, walk H1 → H6 by slug and pick the first that doesn't exist — but enforce the spine gates: H4 only after H3 exists, and any H-article only after the Session-1 schema scaffold has landed. H5/H6 are optional; don't auto-pick them as "next" unless the user asks for them by name.
5. If the user names a specific slug, honor it — the arcs are defaults, not rails.
6. If the user is ambiguous after the foundation is done ("what's next?"), ask once: *"Second Brain, Wiki, MTBM, or Harnesses?"*

---

## State of the apps — closing-section pattern

### Foundation articles (`F1–F7`)

Close with a **three-line state report** — one line per arc. Keep each line one short sentence:

> **Second Brain now:** has a brain but no memory. **Wiki now:** has a writer but no pages. **MTBM now:** has a driver but nothing to drive. Next up: **NeMo Retriever embeddings** — vectorize once, reuse three times.

This pattern is what sells the triple-arc design to readers: one install, three app states advancing.

### Bridge article (`B`)

Close with one-line previews of each track's first article, and invite the reader to pick. (The user can of course read all three.)

### Track-specific articles (S*, W*, A*)

Single-arc close. Only the arc being advanced gets a state-line update. Cross-link to sibling articles in the other tracks when covering the same product (the three Triton articles, three LoRA articles, three eval articles). Readers on only one arc should still see the link as useful, not noise.

---

## Editorial overlay template (when no per-article overlay given)

**Opening hook (section 1).** For foundation articles, anchor to the shared thesis: *three apps, one substrate, one Spark.* For track-specific articles, anchor to that arc's thesis. Examples:

- Foundation `F4` (naive RAG): *"Naive RAG is the bottom of a hill the Second Brain will climb and the Wiki arc will walk away from. Same pipeline, two verdicts — today we build the baseline both arcs will argue with."*
- Wiki W2 (Curator ingest): *"At cloud prices, 1,000 sources × 15 page updates each is a budget conversation. At Spark prices, it's an overnight."*
- MTBM A4 (agent loop): *"Everything so far has been infrastructure. Tonight, the agent runs unsupervised — 100 experiments, 8 hours, one goal: lower val_bpb."*

**Why this matters for the power user (section 2).** Always name at least one of:
- **Privacy** — the corpus / wiki / trajectory never leaves
- **Data gravity** — the model comes to where the data (or the training GPU) already is
- **Independence** — no API key, no bill, no rate limit
- **Latency-of-iteration** — re-embed / re-ingest / re-experiment fast enough to stay in flow
- **Compile-time economics** — (Wiki-specific) ingest-time synthesis becomes affordable only when the LLM is yours
- **Unified-memory advantage** — 128 GB lets you hold a loadout that consumer hardware can't

Tie to the specific product the article installs.

**Closing (section 8).** Use the "state of the apps" pattern above.

---

## What this reference does NOT do

- Does not replace `references/article-structure.md` — the 8-section body and frontmatter rules still apply unchanged.
- Does not override user overlays. If the user gives a specific overlay for this article, use theirs.
- Does not prescribe voice. `references/voice-and-style.md` remains authoritative on prose style.
- Does not gate articles outside the arcs. Foundational pieces (transformers, attention), standalone comparisons, or one-offs are welcome. The arcs just tell us what "next article" means when the user doesn't specify.
- Does not lock article slugs. Slugs are tentative until the article is drafted; if a sharper title emerges, use it and update this table.
