---
title: "Access First, Models Second — How I Set Up My DGX Spark for Solo AI Work"
date: 2026-04-21
author: Manav Sehgal
product: Foundation
stage: foundations
difficulty: intermediate
time_required: "~6 hours spread across a week"
hardware: "NVIDIA DGX Spark"
tags: [foundations, interaction-stack, remote-access, agentic, personal-ai, solo-builder, claude-code]
summary: "Most DGX Spark walkthroughs open with CUDA and tokens/sec. This one opens with streaming, AI-pair-programming, sandboxed agents, and browser automation — the access layer. For a solo edge builder, that interaction stack is more load-bearing than the model stack."
signature: AccessLayer
also_stages: [dev-tools]
---

<!-- Screenshots for this article are pending a future polish pass — Playwright-MCP
     was registered during the session that produced this draft but the tool
     schema wasn't yet loaded. See transcript.md for details. -->

The conventional DGX unboxing story is well-worn: plug in, install CUDA, run `nvidia-smi`, benchmark Llama, post a tokens-per-second chart. I skipped almost all of that in my first week with the Spark. Before I ran a single inference, I set up four things that have nothing to do with models: a remote-desktop streaming server, an AI-pair-programming CLI that lives on the machine itself, a sandboxed agent runtime, and a browser automation layer that the AI can drive. I built the **access layer** first.

The claim this article backs up: **for a solo edge builder working on one machine, the interaction stack is more load-bearing than the model stack.** Models are fungible — every six months there's a new state-of-the-art you swap in. How you reach the machine, how agents reach the world, and how what you learn becomes a public artifact — those decisions compound, and they're painful to change once laid down.

## Why this matters for a personal AI builder

An individual building with AI on their own hardware has a different bottleneck than a team on a cluster. It isn't GPU count. It isn't model choice. It's **attention, feedback loops, and publishing cadence**. You ship, or your rig becomes an expensive paperweight.

The interaction stack governs all three. It determines how many hours of your week you have to be physically at the machine. It determines how much of your work an agent can take off your plate. It determines whether every interesting session produces only a commit, or also a learning artifact that others can find, read, and cite.

The DGX Spark is uniquely well-suited to this posture because it's *one* machine you can treat as a personal cloud. You don't have the distributed-systems overhead of a cluster; you also don't have the constraints of a laptop. You have enough compute to run real workloads and enough continuity to build a rig that supports you.

:::why[Interaction-stack decisions outlive every model decision]
Models are fungible — every six months a new SOTA arrives and you swap weights. How you reach the machine, how agents reach the world, how sessions become artifacts — those decisions are sticky. Migrate from SSH-only to Sunshine streaming six months in and your tool-by-tool habits all break. Get the access layer right on Day 1 and every subsequent model decision compounds against a stable substrate. Time spent on this layer is the highest-leverage week you'll ever spend on a personal AI rig.
:::

## Where this sits in the stack

I'll use "access layer" throughout this piece. What I mean by it, in five roles:

<figure class="fn-diagram" aria-label="The access layer stack — a hexagonal You hub at centre connects via five spokes to a pentagon of tool chips: Sunshine+Moonlight for reach, Claude Code for collaboration, Playwright-MCP for browser exploration, NemoClaw for safe sandboxed automation, and git+blog for publishing.">
  <svg viewBox="0 0 900 600" role="img" aria-label="The access layer stack — a hexagonal You hub at centre connects via five spokes to a pentagon of tool chips: Sunshine+Moonlight for reach, Claude Code for collaboration, Playwright-MCP for browser exploration, NemoClaw for safe sandboxed automation, and git+blog for publishing." preserveAspectRatio="xMidYMid meet">
    <defs>
      <radialGradient id="d01-access-hub-halo-grad" cx="0.5" cy="0.5" r="0.55">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d01-access-hub-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="390" y="248" width="120" height="104" fill="url(#d01-access-hub-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 450 300 L 450 90" />
      <path class="fn-diagram__edge" pathLength="100" d="M 450 300 L 650 235" />
      <path class="fn-diagram__edge" pathLength="100" d="M 450 300 L 573 470" />
      <path class="fn-diagram__edge" pathLength="100" d="M 450 300 L 327 470" />
      <path class="fn-diagram__edge" pathLength="100" d="M 450 300 L 250 235" />
    </g>
    <g class="fn-diagram__nodes">
      <path class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" d="M 510 300 L 480 248 L 420 248 L 390 300 L 420 352 L 480 352 Z" style="fill: url(#d01-access-hub-accent-grad)" />
      <rect class="fn-diagram__node" x="355" y="37" width="190" height="106" rx="8" />
      <rect class="fn-diagram__node" x="555" y="182" width="190" height="106" rx="8" />
      <rect class="fn-diagram__node" x="478" y="417" width="190" height="106" rx="8" />
      <rect class="fn-diagram__node" x="232" y="417" width="190" height="106" rx="8" />
      <rect class="fn-diagram__node" x="155" y="182" width="190" height="106" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="450" y="327" text-anchor="middle">YOU</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="450" y="87" text-anchor="middle">REACH · STREAMING</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="450" y="109" text-anchor="middle">Sunshine + Moonlight</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="450" y="129" text-anchor="middle">anywhere</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="650" y="232" text-anchor="middle">COLLABORATE · AI PAIR</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="650" y="254" text-anchor="middle">Claude Code</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="650" y="274" text-anchor="middle">on the Spark</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="573" y="467" text-anchor="middle">EXPLORE · BROWSER</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="573" y="489" text-anchor="middle">Playwright-MCP</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="573" y="509" text-anchor="middle">the web</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="327" y="467" text-anchor="middle">AUTOMATE · SANDBOX</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="327" y="489" text-anchor="middle">NemoClaw</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="327" y="509" text-anchor="middle">safely</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="250" y="232" text-anchor="middle">PUBLISH · COMPOUND</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="250" y="254" text-anchor="middle">Git + blog</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="250" y="274" text-anchor="middle">what you learn</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(434 268) scale(1.33)"><path d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/></g>
      <g class="fn-diagram__icon" transform="translate(438 39)"><path d="M9.348 14.651a3.75 3.75 0 010-5.303m5.304 0a3.75 3.75 0 010 5.303m-7.425 2.122a6.75 6.75 0 010-9.546m9.546 0a6.75 6.75 0 010 9.546M5.106 18.894c-3.808-3.807-3.808-9.98 0-13.788m13.788 0c3.808 3.807 3.808 9.98 0 13.788"/></g>
      <g class="fn-diagram__icon" transform="translate(638 184)"><path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/></g>
      <g class="fn-diagram__icon" transform="translate(561 419)"><path d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582"/></g>
      <g class="fn-diagram__icon" transform="translate(315 419)"><path d="M9 12.75L11.25 15 15 9.75M12 21.75l-7.5-4.5V7.5L12 3l7.5 4.5v9.75l-7.5 4.5z"/></g>
      <g class="fn-diagram__icon" transform="translate(238 184)"><path d="M6 12L3.269 3.125A59.769 59.769 0 0121.485 12 59.768 59.768 0 013.27 20.875L5.999 12zm0 0h7.5"/></g>
    </g>
  </svg>
  <figcaption>The tools are interchangeable; the breadth of the surface is what compounds.</figcaption>
</figure>

Each role corresponds to a decision I made in the first days with the machine. Notably absent from this diagram: any NVIDIA model, inference server, or training framework. Those come next — and they drop into a rig that's ready to receive them.

## The journey

### Streaming: the rig is remote by design

The first thing I installed wasn't CUDA. It was [Sunshine](https://github.com/LizardByte/Sunshine), the open-source game-streaming server, paired with Moonlight clients on my laptop and phone.

:::define[Sunshine + Moonlight]
Open-source low-latency game-streaming stack repurposed as a remote desktop. Sunshine is the host server (runs on the Spark, hardware-encodes the desktop video), Moonlight is the client (runs on a laptop, phone, or tablet). Originally designed for streaming PC games to handhelds at sub-30ms latency, which is overkill for desktop work and exactly what makes the rig feel "in the room" from anywhere. Replaces the traditional X11/VNC pairing for AI work where rendered browsers and GUI dashboards matter alongside the terminal.
:::

SSH is the traditional remote for a Linux box. For AI work, SSH isn't enough. I need to see rendered browsers (NGC catalog, build.nvidia.com, dashboards), GUI tools that don't have a TTY mode, and — critically — a proper desktop where I can watch a long-running training job without tailing logs. Sunshine gives me that desktop with hardware-encoded video, at latency low enough to feel like a local session.

:::define[NGC — NVIDIA GPU Cloud]
NVIDIA's container and model registry at `nvcr.io`. The catalog at `catalog.ngc.nvidia.com` and `build.nvidia.com` is where containerized inference engines (NIM), pre-built training images (PyTorch, NeMo, Triton, TensorRT-LLM), and ready-to-pull model weights live. An NGC API key — created free at `build.nvidia.com` — is required to pull anything from `nvcr.io`. The most common Day-1 blocker for new Spark owners is realizing the key has to be supplied to *both* the Docker daemon (`docker login nvcr.io`) and the running container (env-var) for image-pull and weight-fetch to work.
:::

```bash
# Host: Sunshine runs as a user service on the Spark
systemctl --user is-active sunshine
# Client: Moonlight picks up the host on the LAN, or via a Tailscale IP
```

This decision sets an assumption the rest of the stack inherits: **I never need to be in the room with the machine.** The Spark lives in a corner. Nothing downstream requires me to walk over to it.

<!-- screenshot TODO: Sunshine web UI (https://localhost:47990) with the Apps tab visible -->

### Claude Code: the AI pair lives on the rig, not my laptop

The second install was Claude Code itself — on the Spark, not on the laptop I use to drive it. This is a choice worth thinking about. A lot of AI-coding workflows have the IDE and the AI living on the developer's client machine, talking to a remote runtime over SSH. I inverted that.

The agent runs where the files are. It owns the local disk, the `DISPLAY`, the Docker socket. When I ask it to "install Playwright-MCP and take a screenshot," it doesn't marshal commands over SSH and fight permission mismatches — it just does them, on the box, as itself. The latency between decision and action is zero hops.

```bash
# On the Spark
claude --version
# claude-code is installed as a user-level tool; sessions persist in
# ~/.claude/projects/<sanitized-cwd>/
```

The corollary of this choice: my laptop becomes a thin client. Browser for email, Moonlight for the rig, nothing heavy. The Spark is the workstation.

:::define[NIM — NVIDIA Inference Microservices]
NVIDIA's container-packaged inference services. Each NIM bundles model weights, a tokenizer, prompt templates, an OpenAI-compatible HTTP server on port 8000, and a tuned engine (vLLM or TensorRT-LLM, picked at runtime to match the host hardware). One `docker run` produces a working `/v1/chat/completions` endpoint — no engine choice, no quantization plumbing, no per-token bill. NIM is the path of least resistance for Day-1 inference; the next foundations article walks the first NIM install end-to-end.
:::

### Playwright-MCP: giving the AI a real browser

Most common agentic task in my workflow so far: "go look this up and bring me the relevant piece." Claude Code has `WebFetch` for URL content and `WebSearch` for queries — they're adequate for reading static pages. For anything dynamic — logged-in dashboards, JS-heavy SPAs, the NIM playground, the NGC catalog with its faceted filters — they fall short.

I registered [Playwright-MCP](https://github.com/microsoft/playwright-mcp) as a user-scope MCP server:

```bash
claude mcp add -e DISPLAY=:1 --scope user --transport stdio \
    playwright -- npx -y @playwright/mcp@latest
npx -y playwright@latest install chromium
```

:::define[MCP — Model Context Protocol]
Anthropic's open spec for letting any LLM agent call out to a server full of named tools. JSON-RPC 2.0 over stdio (local) or streaming HTTP (remote); a server announces tools with names, descriptions, and JSON-schema inputs, and the calling agent picks which tool to invoke each turn. Playwright-MCP is one such server (browser-driving tools); a future article in this arc wraps the Second Brain RAG chain as a four-tool MCP server. The protocol is what turns "an LLM that reads text" into "an LLM that takes actions on this machine."
:::

After a session restart, Claude Code gets a set of `mcp__playwright__browser_*` tools: navigate, click, type, snapshot, screenshot. The AI can now *drive* a browser rather than just read it. The `DISPLAY=:1` env var means I can flip to headed mode and watch it work when I'm debugging.

The quiet part: this tool also produces the screenshots in my blog articles. When a writeup needs a shot of the NGC product page, the agent navigates there, takes the capture, crops it, and embeds it — without me switching windows.

<!-- screenshot TODO: output of `claude mcp list` showing the four connected servers
     including playwright ✓ Connected -->

### NemoClaw sandboxes: making agents safe to automate

The fourth install was NemoClaw — NVIDIA Nemotron-backed agent sandboxes running on `k3s` inside OpenShell containers. If you've never looked at this stack: think "isolated POSIX environments where an agent can freely `apt install`, `rm -rf`, `curl | sh`, and the worst-case blast radius is the sandbox itself."

NemoClaw sits between my files and whatever an agent wants to try next. Without it, I'd have to choose between (a) agents that are crippled because I won't give them shell, or (b) agents that can wreck my config. With it, the answer is: give the agent its own directory, its own user, its own cgroup budget. Let it go.

```bash
# Agents run in their own sandboxes, orchestrated via the nemoclaw CLI
nemoclaw onboard
# ...one-time setup, then agents can be spun up per-task
```

This is the piece that converts "I can imagine agents being useful here" into "agents do real work on this rig." The Nemotron backing matters because those models are tuned for the call-and-response agent rhythm — long horizons, tool use, recovering from their own errors.

:::define[Sandboxed agent runtime]
Isolated execution environment where an AI agent can freely run shell commands, install packages, and modify files without endangering the host. Built on Linux primitives — namespaces, cgroups, often a small VM or a `k3s` pod — that bound the agent's blast radius to a specific directory tree, user, and resource budget. The unblocker for "let the agent try things." Without a sandbox, the calculus is *agent-can-break-my-config* vs *agent-cripples-itself*; with one, the agent gets full shell and the worst case is throwing away one container.
:::

<!-- [TODO: confirm with author — was NemoClaw set up on this specific Spark already?
     The nemoclaw-guru skill suggests yes, but the exact install sequence isn't
     in my session transcript.] -->

### Publishing as a foundation, not an afterthought

The last thing I set up in this first-week batch isn't a tool at all — it's a pipeline. A GitHub repository (`manavsehgal/nvidia-learn`) wired as the `origin` remote on a fresh folder, an `articles/` subfolder with Jekyll-ready frontmatter, and a `tech-writer` Claude Code skill that knows how to turn a session into an essay with embedded screenshots from Playwright-MCP.

```bash
git init
git remote add origin https://github.com/manavsehgal/nvidia-learn.git
git branch -m main
```

Most setup posts treat publishing as something you do *if you feel like it*. I want every serious session on this rig to produce a learning artifact — partly because that's the only way solo work compounds into a reputation, and partly because having to explain something publicly is the best forcing function for understanding it.

The `tech-writer` skill lives at `~/.claude/skills/tech-writer/`. It has an enforced editorial voice ("deep-dive essay, not cookbook"), a mandatory privacy scrub pass on every commit, and a shell script that blocks commits containing API keys, personal IPs, or other leakage patterns. The article you're reading was produced by it — first draft written by the skill, this polish by me.

<figure class="fn-diagram" aria-label="The publishing pipeline — five horizontal stages transforming a working session into a public learning artifact: session transcript, tech-writer draft, privacy scrub, git commit, public reader. An oxblood particle travels the path continuously, representing the feedback loop closing.">
  <svg viewBox="0 0 900 240" role="img" aria-label="The publishing pipeline — five horizontal stages transforming a working session into a public learning artifact: session transcript, tech-writer draft, privacy scrub, git commit, public reader. An oxblood particle travels the path continuously, representing the feedback loop closing." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d02-flow-band-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
        <stop offset="50%"  stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d02-endpoint-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d02-public-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="20" y="100" width="860" height="60" rx="4" fill="url(#d02-flow-band-grad)" stroke="none"/>
    <rect x="670" y="70" width="140" height="120" rx="8" fill="url(#d02-endpoint-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path id="d02-flow-path" class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 170 130 L 740 130" />
      <path class="fn-diagram__edge" pathLength="100" d="M 170 130 L 190 130" />
      <path class="fn-diagram__edge" pathLength="100" d="M 330 130 L 350 130" />
      <path class="fn-diagram__edge" pathLength="100" d="M 490 130 L 510 130" />
      <path class="fn-diagram__edge" pathLength="100" d="M 650 130 L 670 130" />
    </g>
    <circle class="fn-diagram__flow" r="7"><animateMotion dur="3.8s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" begin="1.6s"><mpath href="#d02-flow-path" /></animateMotion></circle>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="30" y="70" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node" x="190" y="70" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node" x="350" y="70" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node" x="510" y="70" width="140" height="120" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="670" y="70" width="140" height="120" rx="8" style="fill: url(#d02-public-accent-grad)" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="100" y="138" text-anchor="middle">SESSION</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="100" y="158" text-anchor="middle">transcript</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="176" text-anchor="middle">what happened</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="260" y="138" text-anchor="middle">DRAFT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="260" y="158" text-anchor="middle">tech-writer</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="260" y="176" text-anchor="middle">essay voice</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="420" y="138" text-anchor="middle">SCRUB</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="420" y="158" text-anchor="middle">privacy check</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="420" y="176" text-anchor="middle">keys, PII, paths</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="580" y="138" text-anchor="middle">COMMIT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="580" y="158" text-anchor="middle">git</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="580" y="176" text-anchor="middle">local only</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="740" y="138" text-anchor="middle">PUBLIC</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="740" y="158" text-anchor="middle">reader</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="740" y="176" text-anchor="middle">compounder</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(88 88)"><path d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/><path d="M10.5 2.25a9 9 0 019 9v.375c0 .621-.504 1.125-1.125 1.125h-5.25a1.125 1.125 0 01-1.125-1.125V3.375c0-.621.504-1.125 1.125-1.125h.375z"/></g>
      <g class="fn-diagram__icon" transform="translate(248 88)"><path d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"/></g>
      <g class="fn-diagram__icon" transform="translate(408 88)"><path d="M9 12.75L11.25 15 15 9.75M12 21.75l-7.5-4.5V7.5L12 3l7.5 4.5v9.75l-7.5 4.5z"/></g>
      <g class="fn-diagram__icon" transform="translate(568 88)"><path d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(728 88)"><path d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582"/></g>
    </g>
  </svg>
  <figcaption>Every serious session closes into an artifact; the loop is the compounder.</figcaption>
</figure>

## Verification — what "it's working" feels like on DGX Spark

The access layer is working when I do this, and it feels ordinary:

I'm at a café. I open Moonlight on my laptop, pick the Spark from the device list, and I'm looking at my desktop — same one I'd see standing next to the machine at home. I open Claude Code in the `nvidia-learn` directory. I say: "remember the NIM setup session from yesterday? Write it up as an article." The agent reads the session transcript, walks the NGC catalog via Playwright-MCP to grab fresh screenshots, drafts the piece with my voice, runs the scrub, commits it locally. I skim, make two edits, run `git push`. The article is public before my flat white is done.

I didn't touch a terminal as a terminal. I didn't type a `docker` command. I didn't think about SSH, port forwarding, or file transfer. The interaction stack carried the entire session.

When this feels ordinary, the foundation is working. If anything in that story feels awkward — if the agent can't browse authenticated pages, if the screenshots come out wrong, if the commit touches files it shouldn't — that's where the next polish pass goes.

## Tradeoffs and surprises

**Sunshine over Tailscale has rough edges.** LAN is smooth. Going over a mesh VPN introduces codec negotiation issues for some client/host pairs and occasionally a low-bitrate fallback that's useless for reading small UI text. <!-- [TODO: confirm with author — any specific Tailscale tuning you ended up doing?] -->

**Ubuntu 24.04 and cgroup v2 confuse older sandbox tooling.** NemoClaw handles this in its installer. If you tried to roll your own containerized agent stack from scratch on 24.04, you'd fight it — the OpenShell / k3s / cgroup v2 combination has edge cases that aren't well-documented yet. Let the tooling do the plumbing.

**Claude Code sessions are per-directory.** Context isn't shared across projects without explicit memory files. For cross-cutting blog writing that references work in several directories, this is mild friction — I ended up putting the editorial-direction memory in the project memory of the `nvidia-learn` cwd specifically so the `tech-writer` skill finds it consistently.

**Playwright-MCP's default profile doesn't persist logins.** If you want to routinely screenshot authenticated pages (your NGC dashboard, your build.nvidia.com account), you need to re-register the MCP server with `--user-data-dir=/home/nvidia/.cache/playwright-mcp-profile` so cookies survive. I didn't do this in the first pass and paid for it the first time I wanted an NGC API-keys-page shot.

:::pitfall[Putting Claude Code on the laptop instead of the rig is the wrong default]
The intuitive setup is IDE+agent on the laptop talking to the Spark over SSH. It feels portable. It also forces every action through a network hop, fights file-permission mismatches, and breaks the moment the agent wants to run `docker` or touch `DISPLAY`. The agent should run *where the files are* — on the Spark itself, owning the local disk, the Docker socket, the X server. The laptop becomes a thin client driving Moonlight, and the latency between agent decision and side-effect drops to zero hops.
:::

**The access layer is not a one-afternoon project.** It took roughly six hours of focused work spread across a week. I'd budget a full weekend if you're doing this for the first time, with another evening for re-tuning each piece after it meets the others (the Sunshine/Tailscale combination especially benefits from a second pass).

## What this unlocks

With the access layer in place, here are three things I can do this week that I couldn't last week:

1. **Remote AI-driven benchmarks.** I can kick off a long-running training or inference benchmark before leaving the house, close the lid on my laptop, and check in on progress from any device running Moonlight. The agent monitors for me and pings when it's done or stuck.

2. **Daily agentic workflows with real side effects.** Agents on this rig can execute code, modify files, browse authenticated dashboards, and commit results — without me worrying they'll break my shell or leak credentials. "Let the agent do it" stops being hypothetical.

3. **Publishing as a continuous byproduct of learning.** Every evaluation session, every new model I try, every failed experiment turns into a committed article draft with roughly the same effort it'd take to write a few notes. The rig is a learning compounder, not just a runtime.

The next article in this series will be the first ML workload — likely a NIM deployment and what it tells me about on-device inference economics vs. the cloud API I used to pay for.

## Closing

Models are fungible. Six months from now, there will be a new state-of-the-art you swap in, and the year after that another one. The interaction stack is not fungible — changing how you reach your machine, how agents work alongside you, how safely you let them run, and how you turn your sessions into published artifacts is expensive and disruptive.

Getting it right on Day 1 means every subsequent decision about which model, which inference server, which fine-tuning library compounds against a stable base. The DGX Spark is the right hardware for this kind of solo-power-user posture — enough compute to be serious, enough continuity to be a partner — but the hardware is only half of it. The other half is the stack above, and that's what I wanted to get down while the choices were still fresh.

:::deeper
- [Sunshine + Moonlight](https://github.com/LizardByte/Sunshine) — host server (Sunshine) and clients (Moonlight) for low-latency desktop streaming over LAN or Tailscale.
- [Playwright-MCP](https://github.com/microsoft/playwright-mcp) — Microsoft's MCP server that gives any agent a real Chromium browser to navigate, click, type, and screenshot.
- [Model Context Protocol spec](https://modelcontextprotocol.io/) — Anthropic's open standard for tool servers; the same wire format used by every MCP integration in this stack.
- [build.nvidia.com](https://build.nvidia.com/) — NGC's playbook hub for DGX Spark; ten Spark-specific inference walkthroughs (NIM, vLLM, SGLang, TRT-LLM, llama.cpp, NVFP4) live here.
:::

:::hardware[The access-layer pattern scales up the DGX ladder]
Sunshine + Moonlight + Claude-on-the-rig + sandboxed agents is not Spark-specific — it is the *workstation pattern*. On a DGX Station (4× B200, 784 GB unified-ish memory) the same stack is what makes a single researcher productive against a multi-GPU box without IT-managed Jupyter Hub. On a SuperPOD slice the streaming desktop becomes a bastion-host workflow but the agent-on-the-rig invariant holds: the agent runs where the GPUs are, never marshaling commands across SSH. The pattern this article installs on a $4K Spark is the same one that scales to a $400K rack — the access layer is hardware-independent infrastructure that compounds against any future GPU you put behind it.
:::

Next up: **the first real NIM inference on the Spark, and what the cold-start numbers tell me about replacing my API spend.**
