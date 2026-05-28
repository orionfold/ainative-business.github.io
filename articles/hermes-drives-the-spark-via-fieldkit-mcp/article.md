---
title: "Hermes Drives the Spark via fieldkit-as-MCP — The Agent That Operates Its Own Machine"
date: 2026-05-26
author: Manav Sehgal
product: Foundation
stage: agentic
difficulty: intermediate
time_required: "~3 hours, including the live tool-call gate against a local NIM"
hardware: "NVIDIA DGX Spark"
tags: [hermes, agentic, mcp, fieldkit, tool-calling, local-first, agentskills, dgx-spark]
summary: "The keystone of the Harnesses series: expose a curated slice of fieldkit as MCP tools and the local Hermes agent can measure, quantize, publish, and retrieve on the box itself. The gate is a real llama-bench run the agent drove end-to-end — 0% tool-call format error, no API key."
signature: HermesFieldkitMCP
series: Harnesses
book_chapters: [10, 11]
also_stages: [dev-tools, deployment]
fieldkit_modules: [harness, capabilities, quant, publish, rag]
---

A while back I wired an agent to run overnight machine-learning experiments unsupervised — an [autonomous loop](/field-notes/autoresearch-agent-loop/) that proposed a change, trained, read the metric, and proposed the next one until morning. It worked, and it was completely bespoke: a harness welded to exactly one job, with the tool surface hard-coded into the loop. The lesson that stuck wasn't "agents can run overnight." It was that the *valuable* part — the tools the agent reaches for — wanted to be a reusable surface, not a script. This article is the general version of that idea. Take a frontier open-source harness (Hermes, the one the previous three articles installed, tuned, and hardened), and instead of welding tools into a loop, hand it a *curated, versioned* slice of `fieldkit` — the same Python package the rest of this blog uses to quantize and publish models — over the Model Context Protocol. The agent can now measure a GGUF, run a guarded quantize, stage a model card, and query my notes corpus, because those are tools it can call, not code I had to fuse into its prompt.

The claim this article backs up is narrow and testable: **a local agent, with no API key and no cloud round-trip, can operate the Spark's own model pipeline through one MCP surface — and we can prove it ran by reading the trace.** Not "could in principle." The gate for this piece is a real `llama-bench` invocation that Hermes decided to make, drove to completion, and reported back from, with the tool call coming through cleanly. The same MCP tool surface, incidentally, is the one that gave a Claude Code session a [Second Brain over my blog corpus](/field-notes/mcp-second-brain-in-claude-code/) — two different harnesses, one protocol, one set of tools. That symmetry is the whole point.

:::define[Model Context Protocol (MCP)]
An open JSON-RPC standard for exposing tools, resources, and prompts to an LLM agent over a transport (stdio or HTTP). The agent's harness speaks the client side; your server advertises a tool list with typed schemas, and the model calls them by name. It decouples *what an agent can do* from *which agent it is* — the same server works for Hermes, Claude Code, or any MCP client.
:::

## Why a personal box makes "the agent operates the pipeline" actually mean something

On a managed cloud, an agent that "operates your ML pipeline" is operating someone else's hardware on your behalf, metered per call, with the model weights and the build tools sitting on infrastructure you rent. The interesting inversion on a DGX Spark is that the box holds *both halves* at once: the models, and the toolkit that makes models. 128 GB of unified memory is enough to keep a NIM resident as the agent's brain *and* have the quantizer, the perplexity harness, and a vector store of your own writing all one tool-call away. When the agent and the foundry live on the same machine, "wire the agent to the pipeline" stops being an integration project and becomes a config line.

That's the personal-power-user payoff and the thread this series has been pulling toward. The [overnight ML loop](/field-notes/autoresearch-agent-loop/) was the *machine that builds machines* in its most literal form — an agent improving models without a human in the chair. Doing that as a one-off taught me it should be a product, not a script: a curated tool surface any harness can pick up. Local-first is what makes it safe to even contemplate handing an agent the quantizer — there's no bill that a runaway loop can run up, no data leaving the box, and (because the previous article hardened it) a sandbox the agent can't escape.

:::why[The machine that builds machines wants a productized tool surface, not a bespoke loop]
The bespoke overnight loop proved the behavior; it didn't generalize. Welding tools into one agent's prompt means the next agent re-implements them. A versioned MCP server flips it: the *tools* are the durable asset, the harness is swappable. That's the difference between "I automated one job" and "I built a surface my agents operate the box through."
:::

## Where MCP sits, and why curation is the containment

Hermes already speaks MCP on the client side — it's how it picks up any community tool server. What's new here is the *server*: a small module, `fieldkit.harness.mcp`, that advertises a deliberately small, opinionated tool list rather than re-exposing the whole package. That smallness is a security decision, not an ergonomic one. The previous article hardened Hermes by putting its shell inside a network-denied Docker sandbox — containment at the *execution* layer. The MCP server runs on the host (it *is* the box-driver; you can't sandbox the thing whose job is to touch the GPU), so its containment lives at the *tool* layer instead: the shape of the list is the policy.

So the seven tools split cleanly. The two capability tools — "what's the inference envelope for a 70B at fp8?", "how many GB does an 8B weigh?" — are pure reads, marked `readOnlyHint`, and can't touch disk or GPU. The two measurement tools (throughput, perplexity) do real GPU work but only against a GGUF path you pass them. The one genuinely expensive write, `quantize_gguf`, defaults to `dry_run=True` and is guarded against a source that wouldn't fit the envelope. And `publish_quant_dry_run` is dry-run *forced*: it can stage a model card and show you the file list, but the code path that executes a real Hugging Face push is simply not reachable through the server. An agent that gets confused, or gets prompt-injected, can preview a publish; it cannot ship one.

:::define[Tool annotations (`readOnlyHint`)]
MCP lets a server tag each tool with hints — `readOnlyHint`, `idempotentHint`, `openWorldHint`. They're advisory metadata the harness can surface or gate on, not enforcement. Here they're load-bearing as *documentation of intent*: the read-only tools declare they touch nothing, so a hardened harness can treat them differently from the write tools that follow.
:::

<figure class="fn-diagram" aria-label="A hardened Hermes agent on the left calls one curated fieldkit MCP surface in the center, which operates the DGX Spark on the right. The single solid edge from Hermes to the MCP surface carries the agent's tool call; a flow particle travels it. A second solid edge runs from the surface to the box, where the measure tool ran llama-bench. The accent center node lists seven tools split into read-only and dry-run-default writes. The verdict strip reads: the agent drove a real measure end to end, 41.75 tokens per second generation, zero tool-call format errors.">
  <svg viewBox="0 0 900 440" role="img" aria-label="A hardened Hermes agent on the left calls one curated fieldkit MCP surface in the center, which operates the DGX Spark on the right. The single solid edge from Hermes to the MCP surface carries the agent's tool call; a flow particle travels it. A second solid edge runs from the surface to the box, where the measure tool ran llama-bench. The accent center node lists seven tools split into read-only and dry-run-default writes. The verdict strip reads: the agent drove a real measure end to end, 41.75 tokens per second generation, zero tool-call format errors." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d04-agent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d04-mcp-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d04-mcp-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="50" y="160" width="200" height="120" rx="10" fill="url(#d04-agent-grad)" stroke="none"/>
    <rect x="360" y="150" width="220" height="160" rx="10" fill="url(#d04-mcp-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path id="d04-call-path" class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 250 220 L 360 220" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 580 220 L 690 220" />
    </g>
    <circle class="fn-diagram__flow" r="6"><animateMotion dur="3s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" begin="1.4s"><mpath href="#d04-call-path" /></animateMotion></circle>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="170" width="180" height="100" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="360" y="150" width="220" height="160" rx="10" style="fill: url(#d04-mcp-accent-grad)" />
      <rect class="fn-diagram__node" x="690" y="170" width="170" height="100" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="150" y="166" text-anchor="middle">HARDENED · H3</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="150" y="232" text-anchor="middle">Hermes</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="150" y="252" text-anchor="middle">local NIM · no key</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="470" y="146" text-anchor="middle">CURATED MCP SURFACE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="470" y="212" text-anchor="middle">fieldkit · 7 tools</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="470" y="238" text-anchor="middle">envelope · measure  (read-only)</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="470" y="258" text-anchor="middle">quantize · publish  (dry-run)</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="470" y="278" text-anchor="middle">ask_second_brain  (read-only)</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="775" y="166" text-anchor="middle">OPERATED</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="775" y="232" text-anchor="middle">the box</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="775" y="252" text-anchor="middle">GPU · 128 GB</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(138 182)"><path d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(458 162)"><path d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z"/></g>
      <g class="fn-diagram__icon" transform="translate(763 182)"><path d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z"/></g>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="305" y="208" text-anchor="middle">tool call</text>
      <text class="fn-diagram__annotation" x="635" y="208" text-anchor="middle">llama-bench</text>
      <text class="fn-diagram__annotation" x="450" y="402" text-anchor="middle">the agent drove a real measure — 41.75 tok/s gen · 0% format error · no key</text>
    </g>
  </svg>
  <figcaption>The agent reaches the box only through the curated list. Curation is the containment: read-only tools touch nothing, the one expensive write defaults to a plan, and publish can stage but never ship.</figcaption>
</figure>

## Building the server, and getting Hermes to pick it up

The server is one file. `fieldkit.harness.mcp` defines seven plain Python functions — `spark_inference_envelope`, `spark_weight_footprint`, `measure_gguf_throughput`, `measure_gguf_perplexity`, `quantize_gguf`, `publish_quant_dry_run`, `ask_second_brain` — and a `build_mcp_server()` that registers them on a `FastMCP` instance with descriptions and the `readOnlyHint` annotations. The tool functions delegate to the rest of the package (`fieldkit.capabilities`, `fieldkit.quant`, `fieldkit.publish`, `fieldkit.rag`), so the MCP layer adds almost no logic of its own — it's a *curation and transport* layer over surfaces this blog already trusts. Keeping the heavy `mcp` SDK behind an optional `fieldkit[harness]` extra means plain `import fieldkit.harness` stays stdlib-only; the SDK loads only when `build_mcp_server` is actually called.

```python
from fieldkit.harness import build_mcp_server, MCP_TOOL_SPECS

# MCP_TOOL_SPECS is pure data — the curated surface, importable without the SDK
for spec in MCP_TOOL_SPECS:
    print(f"{spec.name:26s} {spec.surface:12s} read_only={spec.read_only}")

# the stdio entrypoint Hermes launches: `python -m fieldkit.harness.mcp`
build_mcp_server().run()   # serves the seven tools over JSON-RPC on stdio
```

Wiring it into Hermes is `hermes mcp add` — and this is where the afternoon lost twenty minutes to two small things. The obvious invocation, `hermes mcp add fieldkit --command python --args -m fieldkit.harness.mcp`, fails: Hermes's own argument parser swallows the `-m` as if it were its own model flag, because `--args` takes a variadic list and argparse won't hand a dash-prefixed token to it. The fix is a one-line launcher script — `exec python -m fieldkit.harness.mcp` — pointed at by `--command`, with no dash-args for Hermes to misread. The second snag: `hermes mcp add` does a "discovery-first" probe — it launches the server, lists the tools, and then prompts `Enable all 7 tools? [Y/n]`. Run headless without answering, and it cancels. Pipe a `Y` and it writes the server into `~/.hermes/config.yaml` with all seven enabled.

:::pitfall[`--args` won't take `-m`: wrap the entrypoint in a launcher]
`hermes mcp add --command python --args -m mod` silently fails — argparse treats the `-m` as a Hermes flag and reports "unrecognized arguments." It's not a bug you'll diagnose from the error. Point `--command` at a two-line shell script that `exec`s `python -m …` instead; the launcher also pins `LLAMA_CPP_BIN` so the measure tools resolve `llama-bench`.
:::

## The gate: the agent drives a real measurement

With the server enabled, the test is a single headless turn. The local NIM (Nemotron-Nano-9B-v2, the lane this series has used since [article one](/field-notes/the-hermes-harness-on-spark/)) is the brain; the prompt asks for a throughput measurement of a real GGUF on disk — one of the patent-strategist quants this blog published earlier.

```bash
hermes -z "Using your fieldkit tools, measure the single-stream throughput of \
the GGUF at /home/nvidia/data/quants/patent-strategist-v3-nemo/model-Q4_K_M.gguf. \
Report the prompt-processing and generation tokens/sec." --yolo
```

What came back is the whole article in one exchange. Hermes reasoned about the request, emitted a well-formed call to `measure_gguf_throughput`, the MCP server ran `llama-bench` against the 4.7 GB Q4 GGUF on the GPU, and the model summarized the result:

```text
- Prompt processing: 2,746.65 tokens/second
- Generation: 41.75 tokens/second
This shows a significant difference between prompt handling (very fast) and
generation (slower, as expected for model output).
```

That generation number is a real benchmark of a real model, produced by a tool the agent chose to call — not a figure I typed into the prompt. A second turn ("what's the inference envelope for a 70B at fp8?") exercised the read-only side: the agent called `spark_inference_envelope` and quoted the verdict back verbatim — *"~70 GB weights; leaves ~50 GB for KV + activations + system; tight but possible."* Two tool kinds, two clean calls.

:::define[stdio transport]
The simplest MCP transport: the server is a child process, and JSON-RPC messages flow over its stdin/stdout while logs go to stderr. No port, no auth, no network surface — the harness spawns the server, talks to it down the pipe, and reaps it when the session ends. It's why a local tool server needs zero deployment.
:::

## What success looks like: read the trace, not the vibe

The reason the previous article measured tool-call reliability is that for an agent, a beautiful answer built on a malformed tool call is a failure dressed as a success. Hermes persists every run in a SQLite session store, and `hermes sessions export` dumps it to JSONL — the structured trace `fieldkit.harness` parses into the same `AgentRun` objects the H2 bakeoff used. Running the reducer over the gate session is the actual verification:

```python
from fieldkit.harness import agent_runs_from_hermes_sessions, tool_call_reliability

runs = agent_runs_from_hermes_sessions(gate_session)        # the exported JSONL
print(tool_call_reliability(runs))
# {'n_runs': 1, 'tool_calls': 1, 'tool_format_errors': 0,
#  'format_error_rate': 0.0, 'clean_run_rate': 1.0, 'finished_rate': 1.0}
```

One run, one tool call, zero format errors, finished clean. That's what "the agent drove the box" reduces to when you stop trusting the prose and read the record. Success on this machine isn't a green checkmark — it's a `format_error_rate` of `0.0` over a call that loaded a model onto the GPU and came back with a number.

## The skills you already wrote load into Hermes unchanged

There's a second half to "one protocol, two harnesses." Hermes's skills use the [agentskills.io](https://agentskills.io/specification) standard — the same `SKILL.md` + YAML-frontmatter format Claude Code uses. So a skill I wrote for Claude Code should load into Hermes with no edits, and it does: I copied `.claude/skills/nvidia-learn-stats/` verbatim into Hermes's skills directory, and `hermes skills list` shows it `enabled`, `diff` confirming the file is byte-identical. The richer agentskills.io fields (`version`, `platforms`, `metadata.hermes.tags`) are optional additions on top of the Claude-Code subset.

That portability is worth productizing, so I wrote two new Spark-specific skills — `spark-serve` (bring up one serving lane inside the 128 GB envelope, one at a time, tear it down cleanly) and `vertical-route` (route a request to the right Orionfold domain-expert GGUF) — and pushed them to a public repo, [`manavsehgal/spark-skills`](https://github.com/manavsehgal/spark-skills). The skills.sh registry that backs agentskills.io indexed it on its own crawl; `hermes skills inspect manavsehgal/spark-skills/spark-serve` now resolves it as a `community` skill with a `skills.sh` detail page. The skill is published and installable by anyone, without me building a registry.

:::why[The skills you write for Claude Code load into Hermes unchanged]
agentskills.io is the same `SKILL.md` standard Claude Code uses, so a skill is harness-portable the way a Docker image is host-portable. The work you put into one agent's playbook isn't stranded when you switch harnesses — it's a file. That's the same decoupling MCP gives tools, applied to procedural knowledge.
:::

## Tradeoffs, and what I'd warn you about

The honest framing of "curation is the containment" is that it's a *policy expressed as a tool list*, not an enforcement boundary. The MCP server runs on the host with whatever the launching user can do; a tool I add carelessly is a hole I opened. The discipline is that the surface stays small and the dangerous verb defaults to safe — `quantize_gguf` plans unless you pass `dry_run=False`, `publish_quant_dry_run` can't push at all. If you fork this, resist the urge to "just expose `publish_quant` directly" — the dry-run-forced wrapper exists precisely so a confused agent can't ship to your org. Pair the server with a hardened Hermes (the [previous article](/field-notes/hardening-the-hermes-harness-on-spark/)); an MCP surface handed to a `--yolo` agent with a network-open shell is a different risk calculus entirely.

The other honest note: `ask_second_brain` is in the surface but needs the RAG stack (the embedder and generator NIMs plus pgvector) up to answer; it raises a clear error otherwise rather than pretending. That's deliberate — the tool is the same one the Claude Code [Second Brain](/field-notes/mcp-second-brain-in-claude-code/) uses, so when both stacks are warm, the agent and the editor query the same corpus through the same code. The gate for *this* article only needed the measurement tools and the local NIM, which is why the box ran at ~96 GB during the test and idled clean afterward.

:::deeper
- [The Model Context Protocol specification](https://modelcontextprotocol.io/) — transports, tool/resource/prompt primitives, the JSON-RPC envelope.
- [agentskills.io specification](https://agentskills.io/specification) — the `SKILL.md` format shared by Hermes and Claude Code.
- [The Second Brain over MCP](/field-notes/mcp-second-brain-in-claude-code/) — the sibling server: the same protocol, a different harness, a read-only corpus.
- [Hardening the Hermes harness](/field-notes/hardening-the-hermes-harness-on-spark/) — why the MCP write surface only ships after the sandbox does.
:::

## What this unlocks

Three things are newly buildable the moment the agent can call the foundry. **An overnight quantize-and-measure loop** — point the agent at a freshly fine-tuned model, let it run the variant ladder via `quantize_gguf`, measure each with `measure_gguf_throughput`, and stage a card with `publish_quant_dry_run`, so you wake up to a reviewed dry-run instead of a checklist. That's the [autonomous ML loop](/field-notes/autoresearch-agent-loop/) generalized: the bespoke harness replaced by a frontier one plus a tool surface. **A cross-harness toolkit** — because the server is just MCP and the skills are just `SKILL.md`, the same envelope, measure, and routing tools you give Hermes are one config line away in Claude Code or any other client. **A self-documenting publish pre-flight** — the agent stages the card, surfaces the file list and a preview, and you make the ship/no-ship call, with the dangerous verb structurally out of the agent's reach.

:::hardware[The same surface, a bigger foundry]
On the Spark the agent measures a 4.7 GB Q4 at ~42 tok/s and quantizes inside 128 GB. The MCP surface doesn't change on bigger iron — point the same `measure_gguf_throughput` and `quantize_gguf` at an H100 node or a DGX with 8× the memory and the agent operates a foundry that fits 70B-class models at full precision. The tool list is the contract; the envelope underneath it is the only thing that scales.
:::

## Closing

The Harnesses series set out to build a cockpit you'd actually drive the Spark from: installed it (H1), tuned its serving lane (H2), hardened it (H3), and now wired it to the box's own toolkit (H4). That's a complete story — the *machine that builds machines*, productized down to a config line, running local with no API key and a trace you can read. Hermes can now measure, quantize, stage, and retrieve on the Spark because those are tools, not scripts, and the same tools answer to a different harness tomorrow. The remaining two articles (a five-expert vertical router, a measured local-vs-OpenRouter cost curve) are leverage on top of a foundation that already stands. Monday morning, the move is to point a hardened local agent at your own model pipeline and let it operate — and to read the session trace afterward to confirm it actually did.

---

**Catalog page:** [`/artifacts/skills/spark-hermes-skills/`](/artifacts/skills/spark-hermes-skills/) — positioning, the agentskills.io-format skill variants, the recommended variant, and bounded drift — the full skill bundle.
