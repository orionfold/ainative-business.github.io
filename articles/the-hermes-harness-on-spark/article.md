---
title: "The Hermes Harness on a DGX Spark — A Local Cockpit That Holds Tools, With No API Key"
date: 2026-05-26
author: Manav Sehgal
product: NIM
stage: agentic
difficulty: intermediate
time_required: "~1 hour, most of it the NIM's first cold-start"
hardware: "NVIDIA DGX Spark"
tags: [hermes, nim, nemotron, agentic, tool-calling, local-first, mcp, dgx-spark]
summary: "Installing the Hermes agent harness on a DGX Spark and running the first local agent turn against the cached Nemotron-Nano-9B-v2 NIM — reliable tool calls, no API key, no cloud hop. The defensible angle is NIM-first; everyone else's Spark Hermes write-up leads with Ollama."
signature: HermesCockpit
series: Harnesses
also_stages: [inference, deployment]
fieldkit_modules: [nim, capabilities, harness]
---

Every model I've published on this machine has been a *thing you download and run* — a quantized GGUF, a card, a notebook, a one-line `pip` of `fieldkit`. Useful, finished, inert. What's been missing is the other half of the loop: the **cockpit**. Not another model to run, but the thing you actually *drive the box from* — the harness that turns a published model and an API into a daily-use personal agent that can read your files, run a command, and hand the result back to the model, all on one desk, with nothing leaving it.

This is the first article in a new series about exactly that. The harness is **Hermes Agent** (Nous Research, MIT-licensed), and the question this piece answers is the one that decides whether the whole series is worth writing: *can a frontier open-source agent harness drive a model that runs entirely on the Spark — with reliable tool calls, and no API key?* The answer is yes, and the load-bearing detail is which model. Every other DGX Spark Hermes write-up I've seen leads with Ollama. This one leads with the tuned **NIM Nemotron** lane — the same `nemotron-nano-9b-v2-dgx-spark` container I've measured at 325 tok/s — because that's the lane nobody else documents and the one that makes the agent feel local instead of merely private.

:::define[Agent harness]
The software shell around a model that turns single completions into a *loop*: it parses the model's tool calls, executes them (shell, file read, web fetch), feeds results back, and repeats until the task is done. The model reasons; the harness acts. Hermes, Claude Code, Cursor, and Codex CLI are all harnesses. Swap the model behind one and the loop is unchanged.
:::

## Why a local cockpit is a different proposition

The three application arcs on this blog — a Second Brain that RAGs over my corpus, an LLM Wiki that compiles knowledge at ingest, a Machine that Builds Machines that runs experiments overnight — all answer *what you run* on the Spark. A harness answers a different question: *what you drive it from, and how much of yourself you're willing to hand it.* The moment an agent can read your files and run commands, "private" stops being about where the weights live and starts being about where the **tool calls** resolve. A cloud-hosted agent that reaches into your home directory has to send the contents of that directory somewhere to reason about it. A local one doesn't.

That's the uber-theme tie for this series, and it's sharper here than anywhere else on the blog: the Spark is always on at home, so a hardened local Hermes becomes a private always-on agent you can text from your phone — 100% local, no cloud, no API key, no per-token bill, escalating to a paid model only when a task genuinely needs one. Independence isn't a nice-to-have for an agent that holds tools; it's the whole point. Today is step one of that: install, wire it to the local NIM, and prove the tool-call loop closes without a key.

:::why[A harness that holds tools is a different trust question]
Running a model locally protects your *prompts*. Running the *harness* locally protects your *filesystem and shell* — because an agent that can `read_file` and run commands only stays private if the reasoning that decides *which* file to read also happens on your box. The provider boundary, not the weights, is where the privacy line actually sits once tools enter the loop.
:::

## Where Hermes sits, and why NIM is the hero

Hermes is provider-agnostic. Out of the box it'll talk to Anthropic, OpenAI, OpenRouter, or a dozen others if you hand it a key — but it also speaks the plain OpenAI `/v1/chat/completions` dialect, which is exactly what a local NIM serves. That's the seam this series lives in: point Hermes's provider at `http://127.0.0.1:8000/v1` and the harness has no idea it's no longer talking to the cloud. The agent loop, the 40-odd built-in tools, the skills system — all of it runs against a model that never leaves the Spark.

<figure class="fn-diagram" aria-label="One Hermes agent turn on the DGX Spark — a one-shot prompt flows through the Hermes agent loop to the local NIM Nemotron lane, which decides the tool call; a sandboxed tool executes and the result returns through the model to a reply, with no API key set anywhere.">
  <svg viewBox="0 0 900 260" role="img" aria-label="One Hermes agent turn on the DGX Spark — a one-shot prompt flows through the Hermes agent loop to the local NIM Nemotron lane, which decides the tool call; a sandboxed tool executes and the result returns through the model to a reply, with no API key set anywhere." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d01-hermes-band-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
        <stop offset="50%" stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d01-nim-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d01-nim-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="20" y="110" width="860" height="60" rx="4" fill="url(#d01-hermes-band-grad)" stroke="none"/>
    <rect x="350" y="80" width="140" height="120" rx="8" fill="url(#d01-nim-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path id="d01-hermes-flow-path" class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 170 140 L 740 140" />
      <path class="fn-diagram__edge" pathLength="100" d="M 170 140 L 190 140" />
      <path class="fn-diagram__edge" pathLength="100" d="M 330 140 L 350 140" />
      <path class="fn-diagram__edge" pathLength="100" d="M 490 140 L 510 140" />
      <path class="fn-diagram__edge" pathLength="100" d="M 650 140 L 670 140" />
    </g>
    <circle class="fn-diagram__flow" r="7"><animateMotion dur="3.8s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" begin="1.6s"><mpath href="#d01-hermes-flow-path" /></animateMotion></circle>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="30" y="80" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node" x="190" y="80" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="350" y="80" width="140" height="120" rx="8" style="fill: url(#d01-nim-accent-grad)" />
      <rect class="fn-diagram__node" x="510" y="80" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node" x="670" y="80" width="140" height="120" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="100" y="138" text-anchor="middle">ONE-SHOT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="100" y="158" text-anchor="middle">hermes -z</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="176" text-anchor="middle">--yolo</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="260" y="138" text-anchor="middle">HARNESS</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="260" y="158" text-anchor="middle">Hermes</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="260" y="176" text-anchor="middle">agent loop</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="420" y="138" text-anchor="middle">LOCAL LANE</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="420" y="158" text-anchor="middle">NIM Nemotron</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="420" y="176" text-anchor="middle">:8000 · custom</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="580" y="138" text-anchor="middle">TOOL</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="580" y="158" text-anchor="middle">read_file</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="580" y="176" text-anchor="middle">shell · fs</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="740" y="138" text-anchor="middle">REPLY</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="740" y="158" text-anchor="middle">answer</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="740" y="176" text-anchor="middle">local · no key</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(88 90)"><path d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z"/></g>
      <g class="fn-diagram__icon" transform="translate(248 90)"><path d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25zm.75-12h9v9h-9v-9z"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(408 90)"><path d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z"/></g>
      <g class="fn-diagram__icon" transform="translate(568 90)"><path d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437"/></g>
      <g class="fn-diagram__icon" transform="translate(728 90)"><path d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></g>
    </g>
  </svg>
  <figcaption>The whole turn happens between the two endpoints of your own LAN. The accent node is the only one that "thinks" — and it's local, so the decision to read your file never leaves the box.</figcaption>
</figure>

:::define[Tool calling]
The protocol by which a model asks the harness to run something. The model emits a structured `tool_calls` block — a function name plus JSON arguments — instead of (or alongside) prose; the harness runs the function and returns the result as a new message. It's the difference between a chatbot that *describes* reading a file and an agent that actually reads it. Reliability here is binary-critical: a malformed tool call stalls the whole loop.
:::

NIM is the hero lane for a specific, measured reason: it ships the *correct* tokenizer, chat template, and engine config for Nemotron, where stock inference servers have historically mangled them. I trust this lane to emit well-formed tool calls in a way I don't trust a hand-rolled server. The cost is cold-start and memory footprint, which the rest of this piece quantifies honestly.

## Installing the harness

The install is a single piped script. I never pipe a remote script to a shell without reading it first, so I pulled `install.sh` down and walked its 2,071 lines: for a non-root user it git-clones into `~/.hermes/`, builds a `uv` virtualenv, drops a `hermes` shim in `~/.local/bin`, and only reaches for `sudo` to install *optional* niceties like ripgrep. No Docker pulls, nothing system-wide. Reversible with `rm -rf ~/.hermes`. With that confirmed:

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
# ... clones, builds venv, bundles 90 skills to ~/.hermes/skills/
hermes --version
# Hermes Agent v0.14.0 (2026.5.16)
```

The install bundled **90 skills** into `~/.hermes/skills/` on the way in — and they're in the agentskills.io `SKILL.md` format, which is the same format Claude Code uses. That cross-compatibility is a thread I'll pull hard in a later article; for now it's a pleasant signal that the skills I've already written are portable. The thing I cared about today was the health check:

```text
$ hermes doctor
◆ Python Environment        ✓ Python 3.11.15   ✓ Virtual environment active
◆ Required Packages         ✓ OpenAI SDK   ✓ HTTPX   ✓ PyYAML   ...
◆ Configuration Files       ✓ ~/.hermes/.env   ✓ ~/.hermes/config.yaml (v24)
◆ Directory Structure       ✓ skills/   ✓ memories/   ✓ SOUL.md   ...
◆ Tool Availability         ✗ discord (missing DISCORD_BOT_TOKEN)   ✗ spotify ...
```

Every core check is green — Python, packages, config, directory layout — which is the only part that gates a working agent on aarch64 / DGX OS. But `hermes doctor` also emits a *wall* of red ✗ marks below that, and the first time you run it the instinct is to panic. They're integrations you haven't configured: Discord, Spotify, web-search providers that want API keys you don't have. None of them matter for a local agent. This honestly tripped my own tooling — when I codified the doctor parse into `fieldkit`, my first pass treated every ✗ as a failure and declared a clean install broken.

:::pitfall[`hermes doctor`'s red ✗ marks are mostly optional integrations]
The doctor prints ~73 checks across a dozen sections, and on a fresh install a couple of dozen are ✗ — Discord, Spotify, Feishu, web-search keys. Those are opt-in features you haven't wired, not failures. Only six sections (Python Environment, Required Packages, Configuration Files, Directory Structure, Command Installation, Security Advisories) actually gate a working agent. Classify by *section*, not by the color of the mark, or you'll declare a healthy install dead.
:::

## Wiring Hermes to the local NIM

Here's the gotcha that would have cost me an hour if I hadn't read the config comments carefully. Hermes ships a native `nvidia` provider — and it is *not* what you want. That provider points at `build.nvidia.com`, the cloud NIM endpoint, and demands an `NVIDIA_API_KEY`. For a model running on your own box you use the **`custom`** provider, the generic OpenAI-compatible path, with an explicit `base_url`. (Hermes aliases `ollama`, `vllm`, and `llamacpp` to `custom` too — they're all the same code path.)

:::pitfall[Use `provider: custom`, not the native `nvidia` provider]
Hermes's built-in `nvidia` provider is the *cloud* NIM at build.nvidia.com and needs an API key — the opposite of what this series is about. A *local* NIM is just an OpenAI-compatible endpoint, so it's `provider: custom` + `base_url: http://127.0.0.1:8000/v1`. The naming overlap is a trap precisely because both say "NVIDIA."
:::

First the model. I started the cached NIM the way I always do — `--network host`, the cache mount, the NGC key from an env-file, and `NIM_MAX_BATCH_SIZE=32`, the batch knob I'd measured at 325 tok/s on this hybrid-Mamba model. It warmed in **145 seconds** and settled at **91 GB used, 29 GB free** — comfortably inside the 128 GB envelope, with no room to spare for a second large model, which is exactly the discipline the next article is about. Then I pointed Hermes at it:

```bash
hermes config set model.provider custom
hermes config set model.base_url http://127.0.0.1:8000/v1
hermes config set model.default  nvidia/nemotron-nano-9b-v2
# ~/.hermes/.env — a dummy key; the NIM accepts any non-empty bearer
OPENAI_BASE_URL=http://127.0.0.1:8000/v1
OPENAI_API_KEY=local
```

`OPENAI_API_KEY=local` is the quiet headline of the whole piece. It's a placeholder the NIM doesn't check — there is no real credential anywhere in this setup, no cloud account, no billing relationship. The harness is fully wired and there's nothing to leak.

## Does the lane actually do tool calls?

Before trusting the full agent loop, I tested the narrow thing the whole series hinges on: can the Nemotron NIM emit a well-formed tool call at all? A harness can't paper over a model that can't. One direct `/v1/chat/completions` with a `tools` array and `tool_choice: auto` settled it:

```json
finish_reason: "tool_calls"
tool_calls: [{"type":"function",
  "function":{"name":"get_weather","arguments":"{\"city\": \"Paris\"}"}}]
```

Clean. Correct function, correct JSON arguments, the right `finish_reason`. The model's reasoning showed up in the `content` field ahead of the call, which is the Nemotron `<think>`-prefix behavior I've documented elsewhere — but the structured call came through untouched. The lane can do the agent-critical thing. Now the harness.

## The first local agent turn

Hermes has a headless one-shot mode — `hermes -z "<prompt>"` — that prints only the reply, and a `--yolo` flag that bypasses the interactive tool-approval prompt so it runs unattended. I planted a file with a known phrase and asked the agent to *use a tool* to read it back. This forces a real `read_file` call routed through the local model — the full loop, not a chat completion:

```text
$ echo "The secret pass-phrase is ORIONFOLD-NIM-7741." > secret.txt
$ hermes -z "Read secret.txt and tell me the exact pass-phrase. Use your tools." --yolo

[reasoning] ... I used the read_file tool with a limit of 500 lines and an
offset of 1 ... the file has one line containing the pass-phrase ...
The secret pass-phrase in `secret.txt` is: **ORIONFOLD-NIM-7741**.
```

That's the loop closing. The local model decided to call `read_file`, Hermes executed it against my filesystem, fed the contents back, and the model composed the answer — every step on the Spark, no key, no network. The reasoning trace even names the exact tool and arguments it chose. A chatbot would have told me it *couldn't* read the file; the harness read it.

One turn is an anecdote, so I ran a small battery of four tasks that each force a different tool — a directory listing, a line count, a create-then-read round-trip, and a shell command — and recorded whether each produced a well-formed tool call and a correct final answer:

| Task | Tool | Wall | Tool call | Answer |
|---|---|---:|:---:|:---:|
| read a planted phrase | `read_file` | ~40 s | ✅ | ✅ exact |
| count lines in a file | `read_file` | 42 s | ✅ | ✅ "4 lines" |
| create + read back a file | write + read | 72 s | ✅ | ✅ verified |
| today's date via shell | shell | 44 s | ✅ | ✅ `2026-05-26` |
| list a directory | list/glob | 41 s | ✅ | ❌ reported "empty" |

**Four of five tool calls were well-formed with zero format errors; three of five final answers were fully correct.** The one miss is honest and worth keeping: on the directory listing, the model called the tool, got the results, and then *summarized them wrong* — reported the folder empty when it wasn't. That's a small-model reasoning slip, not a harness or tool-format failure, and it's precisely why the next article measures tool-call reliability as a first-class number across serving lanes rather than asserting it.

## Codifying the path in fieldkit

Everything above is reproducible by hand, but I don't want to rebuild the NIM launch recipe and the config-rendering from memory every session, so it's now a small deterministic surface in `fieldkit` — the same package that backs the rest of this blog. The lane launch, the warm-wait, the unified-memory guard, and the `provider: custom` config all collapse to a few lines:

```python
from fieldkit.harness import LaneSpec, serve_lane, configure_hermes

# Brings the NIM up (guarded against OOM-stacking via fieldkit.capabilities),
# waits for warm, tears it down on exit — one model at a time.
with serve_lane(LaneSpec("nim", "nemotron-nano-9b-v2-dgx-spark", port=8000)) as lane:
    config, env = configure_hermes(lane=lane, model="nvidia/nemotron-nano-9b-v2")
    # config.render() -> the model: block of ~/.hermes/config.yaml
    # env.render()    -> ~/.hermes/.env  (base_url + a dummy key + slow-serving timeout)
```

The `serve_lane` guard reuses the same `fieldkit.capabilities` memory math the rest of the blog uses for envelope sizing — it refuses to start a lane that would tip the 128 GB budget, and the context manager's teardown is what enforces the one-model-at-a-time rule the NIM's 91 GB footprint demands. It's deliberately thin. The harness module isn't trying to *be* Hermes; it's trying to make the Spark-specific parts — the NIM recipe, the memory guard, the config shape — repeatable.

:::define[MCP — Model Context Protocol]
An open standard for exposing tools and data to an agent as a uniform server interface. Hermes speaks it, which means later in this series I can expose `fieldkit` itself — quantize, measure, publish, retrieve — as MCP tools and let the harness *operate the Spark*, not just read its files. That's the keystone the series builds toward; today's `read_file` is the trailhead.
:::

## What this unlocks

With the cockpit installed and proven local, three things are newly buildable this week. **A private file agent** that triages a directory, summarizes documents, and renames things on request — pointed at your actual home folder, because the reasoning never leaves it. **A no-bill scripting assistant** wired into a shell binding, where "ask the agent to write and run a one-off script" costs electricity and nothing else, so you stop rationing the calls the way a metered API trains you to. And **a foundation for the always-on phone agent** that closes the series: the same `hermes -z` turn, reached through Hermes's messaging gateway, hardened, answering from your desk while you're out.

The honest caveat is the one the battery surfaced: a 9B model is a capable *actor* but a fallible *reasoner*. It will occasionally execute a perfect tool call and then misread the result. For agent work where a wrong summary is cheap to catch, that's fine; where it isn't, the answer is a bigger lane or a verifier — both of which the next two articles are about.

## Closing

The DGX Spark earns its keep here by collapsing a distance that the cloud keeps wide: the distance between the agent's reasoning and your data. A local harness driving a local NIM means the decision to read a file, run a command, or call a tool happens on the same machine the file lives on — no key, no hop, no bill, 145 seconds from cold to a closed agent loop. That's a different kind of "private" than a local model alone buys you, and it's the foundation the rest of this series is built on.

:::why[NIM-first is the defensible angle]
Every Spark Hermes guide reaches for Ollama because it's the lowest-friction first turn. NIM is more work — cold-start, memory footprint, an NGC key for the pull — but it ships the correct tokenizer, chat template, and engine config for Nemotron, which is what makes its tool calls trustworthy. For a chatbot the difference is cosmetic; for a harness that *acts* on tool calls, a reliably-formatted call is the entire job. That's the trade this series is willing to make, and the reason it leads with the lane nobody else documents.
:::

:::deeper
- [Hermes Agent (Nous Research, MIT)](https://github.com/NousResearch/hermes-agent) — the harness; install script, provider list, and the `hermes mcp` server mode.
- [NVIDIA — Run Hermes Agent with Local Models on DGX Spark](https://build.nvidia.com/spark/hermes-agent/instructions) — the official playbook (Ollama-first; this article is the NIM-first counterpart).
- [Your First NIM on a DGX Spark](/field-notes/nim-first-inference-dgx-spark/) — the sibling foundation piece on the NIM lane this harness drives.
- [agentskills.io specification](https://agentskills.io/specification) — the `SKILL.md` format Hermes shares with Claude Code; the basis for a later article in this series.
:::

Next up: **the serving-lane bakeoff** — Qwen3 35B-A3B MoE versus a 27B dense model on the 128 GB envelope, measured on tok/s, sustained load, and the number that actually decides a harness's worth: **tool-call reliability** per lane. The cockpit is installed; now we make it fast without tipping the box over.

:::hardware[Same tool-call loop, frontier latency]
The loop in the diagram is hardware-invariant — only the model node's speed changes. On the Spark the Nemotron lane turns a tool-calling step in a few seconds, bandwidth-bound by GB10's unified memory. The same 9B-class model on an H100 (3.35 TB/s HBM3) closes each model-side hop 5–6× faster; an H200 (4.8 TB/s) another ~40%; a B200 (8 TB/s) doubles it again. A frontier box doesn't change *what* the harness does — it changes how many tool-call round-trips you'll sit through per minute. The architecture on this page is the one you'd run at any scale; the Spark is just where it costs nothing per call.
:::
