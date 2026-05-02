---
title: "The Sandbox Tax That Wasn't — NemoClaw vs OpenClaw on One DGX Spark"
date: 2026-04-21
author: Manav Sehgal
product: NemoClaw
stage: agentic
difficulty: intermediate
time_required: "~2 hours after prerequisites"
hardware: "NVIDIA DGX Spark"
tags: [agentic, nemoclaw, openclaw, ollama, sandboxing, nemotron, claude-code, personal-ai, solo-builder]
summary: "I ran NemoClaw's sandboxed agent stack and the host Ollama-OpenClaw CLI side by side on one DGX Spark with the same 123B Nemotron model. The sandbox overhead I went looking for is real but modest (~2× raw inference); the real tax is onboarding, and NemoClaw paid it at install time."
signature: NemoClawTurns
---

The assumption I brought to this experiment was: **sandboxing an agent must cost something measurable**. NemoClaw wraps the same OpenClaw agent you can run directly on the host — but slides it into an OpenShell container, puts Landlock + seccomp + a network namespace around it, fronts it with a k3s gateway, and routes inference through an auth proxy. That's a stack of indirection. What does it buy you, and what does it cost?

I ran both, on one DGX Spark, against the same Ollama backend and the same Nemotron 3 Super weights. The measurement I was hunting for is there — the sandbox adds ~2× to steady-state per-turn wall-clock. But the *interesting* number is somewhere else entirely. On a fresh install, the **host** path is the slow one, because the host-side OpenClaw agent stalls on a multi-turn USER.md onboarding dialog before it will answer any question. NemoClaw folds that same onboarding into its 28-minute install wizard, so the sandbox is ready to work the moment the install completes.

The "sandbox tax" I went looking for exists. It's just smaller than the onboarding tax it replaces.

## Why this matters for one person on one machine

Agent sandboxing is usually discussed in an enterprise frame — compliance, SOC2, per-tenant isolation. That framing misses something a solo builder cares about: **blast radius on the one machine they actually work on**. When an agent's tool call can read your `~/.ssh/`, write into your git working tree, or exfiltrate anything it finds in `/home`, "ship fast with agents" and "don't lose my own machine" start pulling against each other.

A DGX Spark intensifies that tension. It's enough computer to run real agentic workloads, but it's *also* your development machine — the same box that holds your drafts, your credentials, your browser profile. You don't get to spin up a fresh VM for each experiment; the machine is the environment. Sandboxing *on the edge* is different from sandboxing *in a datacenter*: the cost-benefit math has to be legible to you, personally, within minutes — not amortized across a fleet.

That's the question this piece really answers. Not "how do I install NemoClaw" — the [official instructions](https://build.nvidia.com/spark/nemoclaw/instructions) do that competently. The question is: *as a personal power-user, is the sandbox cheap enough to default to?* For my workload, on this machine, it is. Here's how I got to that answer — and, along the way, the reusable method I built for absorbing product docs into a Claude Code skill so the next install (of the next agent product) goes the same way.

## Where these two products sit on the map

NemoClaw and OpenClaw are the kind of near-homophones that, combined with shared lineage, sow real confusion. One paragraph of disambiguation — a gift to the reader — before we go further:

**OpenClaw** is a personal AI agent CLI (previously known as Clawdbot / Moltbot). Ollama ships it as a first-class integration target: `ollama launch openclaw` installs it if missing, starts a local gateway on `127.0.0.1:18789`, opens a TUI. It runs on the host. There's no sandbox. If an agent tool call does `rm -rf ~`, it reaches your home directory.

**NemoClaw** is NVIDIA's productization of the same OpenClaw agent, wrapped inside an **OpenShell sandbox**. OpenShell contributes a Docker-hosted k3s mini-cluster called a "gateway," a Landlock + seccomp + netns triple around each sandbox container, and a service mesh that lets the agent reach the host Ollama through a named TLS route (`https://inference.local/v1`) instead of talking to the network directly. NemoClaw also folds in its own Telegram bridge and a policy system for what the sandbox can reach out to. Same agent; a very different containment model.

Both stacks ultimately call the same Ollama process on the host:

<figure class="fn-diagram" aria-label="Two paths to one Ollama. Host OpenClaw reaches Ollama directly on port 11434. The NemoClaw sandbox (OpenClaw inside a dashed container with a hexagonal k3s gateway offering the inference.local route) reaches the same Ollama by crossing the sandbox boundary and passing through an auth-proxy on port 11435. Both paths converge on the Ollama cylinder, which pulses softly.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Two paths to one Ollama. Host OpenClaw reaches Ollama directly on port 11434. The NemoClaw sandbox (OpenClaw inside a dashed container with a hexagonal k3s gateway offering the inference.local route) reaches the same Ollama by crossing the sandbox boundary and passing through an auth-proxy on port 11435. Both paths converge on the Ollama cylinder, which pulses softly." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d01-host-lane-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d01-sandbox-lane-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d01-ollama-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.20"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d01-ollama-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="50" y="20" width="260" height="155" rx="10" fill="url(#d01-host-lane-grad)" stroke="none"/>
    <rect x="30" y="255" width="410" height="170" rx="10" fill="url(#d01-sandbox-lane-grad)" stroke="none"/>
    <rect x="690" y="152" width="140" height="156" fill="url(#d01-ollama-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 270 100 L 690 180" />
      <path class="fn-diagram__edge" pathLength="100" d="M 240 340 L 285 340" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 395 340 L 470 340" />
      <path class="fn-diagram__edge" pathLength="100" d="M 610 340 L 690 280" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="30" y="255" width="410" height="170" rx="10" />
      <rect class="fn-diagram__node" x="90" y="45" width="180" height="110" rx="8" />
      <rect class="fn-diagram__node" x="80" y="295" width="160" height="90" rx="8" />
      <path class="fn-diagram__node" d="M 395 340 L 367.5 292.4 L 312.5 292.4 L 285 340 L 312.5 387.6 L 367.5 387.6 Z" />
      <rect class="fn-diagram__node" x="470" y="295" width="140" height="90" rx="8" />
      <path class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" d="M 690 170 L 690 290 A 70 18 0 0 0 830 290 L 830 170" style="fill: url(#d01-ollama-accent-grad)" />
      <ellipse class="fn-diagram__node fn-diagram__node--accent" cx="760" cy="170" rx="70" ry="18" style="fill: url(#d01-ollama-accent-grad)" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--accent" x="50" y="245" text-anchor="start">NEMOCLAW SANDBOX</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="180" y="92" text-anchor="middle">HOST · DIRECT</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="180" y="118" text-anchor="middle">OpenClaw</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="180" y="140" text-anchor="middle">→ :11434</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="160" y="345" text-anchor="middle">OpenClaw</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="160" y="365" text-anchor="middle">in container</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="340" y="348" text-anchor="middle">k3s gateway</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="340" y="368" text-anchor="middle">inference.local</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="540" y="345" text-anchor="middle">auth-proxy</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="540" y="365" text-anchor="middle">:11435</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="760" y="205" text-anchor="middle">SHARED BACKEND</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="760" y="232" text-anchor="middle">Ollama</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="760" y="256" text-anchor="middle">:11434 · nemotron</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="400" y="330" text-anchor="start">sandbox boundary</text>
      <text class="fn-diagram__annotation" x="760" y="395" text-anchor="middle">one blob, two routes</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(168 44)"><path d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z"/></g>
      <g class="fn-diagram__icon" transform="translate(148 296)"><path d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z"/></g>
      <g class="fn-diagram__icon" transform="translate(328 300)"><path d="M21 7.5l-2.25-1.313M21 7.5v2.25m0-2.25l-2.25 1.313M3 7.5l2.25-1.313M3 7.5l2.25 1.313M3 7.5v2.25m9 3l2.25-1.313M12 12.75l-2.25-1.313M12 12.75V15m0 6.75l2.25-1.313M12 21.75V19.5m0 2.25l-2.25-1.313m0-16.875L12 2.25l2.25 1.313M21 14.25v2.25l-2.25 1.313m-13.5 0L3 16.5v-2.25"/></g>
      <g class="fn-diagram__icon" transform="translate(528 296)"><path d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(748 128)"><path d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3"/></g>
    </g>
  </svg>
  <figcaption>Same backend, different routes; the sandbox's extra hops are what make its requests auditable.</figcaption>
</figure>

The auth proxy on 11435 is the wiring the NemoClaw captured docs mostly skip over: it injects tokens so the sandbox's requests can be audited and policy-filtered without the sandbox itself knowing about Ollama's (otherwise open) API. It's the "why is this more than just Docker" answer in one process.

## Turning docs into a skill, before turning a skill into an install

The meta-move that made this install clean — worth naming before I walk through the install itself — was building a Claude Code skill out of NemoClaw's documentation *first*, then running the install *through* that skill.

The skill lives at `~/.claude/skills/nemoclaw-guru/`. Its shape:

| File | Lines | Purpose |
|---|---:|---|
| `SKILL.md` | 78 | Always loaded. Survey commands + routing + hoisted DGX Spark gotchas. |
| `references/instructions.md` | 355 | Four-phase install walkthrough, captured from [build.nvidia.com](https://build.nvidia.com/spark/nemoclaw/instructions). |
| `references/troubleshooting.md` | 179 | Symptom → cause → fix table. |
| `references/commands.md` | 90 | Confirmed vs. plausible-but-unverified CLI flags. |
| `references/repo-overview.md` | 127 | Project shape from the NVIDIA GitHub repo. |
| `references/openclaw-ollama.md` | 130 | Sibling product: added after a disambiguation pass. |

959 lines total. Captured at skill-creation time, **not** re-fetched on every invocation. Three design choices from that skill are worth naming because they kept the actual install boring:

- **Survey before advise.** The skill opens every session with five read-only probes: `nemoclaw --version`, `openshell --version`, `ls ~/.nemoclaw/`, `docker ps`, `systemctl is-active ollama`. Advice branches from the snapshot, not from an assumed-clean host.

- **Sibling-product routing.** If the survey shows `openclaw` on `PATH` but no `~/.nemoclaw/`, route to the Ollama-OpenClaw reference — *don't* suggest the NemoClaw install flow. That rule exists because both products share lineage and half their vocabulary, and mis-routing costs an hour. On this Spark, that exact scenario was live at start: host OpenClaw running, NemoClaw absent. The skill knew to explain the relationship, not conflate them.

- **Don't invent flags.** `references/commands.md` tags each command as confirmed-from-source or plausible-but-unverified. When in doubt, the skill tells Claude to run `nemoclaw help` on the live install rather than guess a flag. One place captured docs lie is in their flag lists — easily, and without you noticing.

Building the skill was an hour. The dividend showed up immediately. Before Docker could fail on cgroup v2, the skill had hoisted the `default-cgroupns-mode: host` fix. Before the install wizard could bail on "No GPU detected," the skill had pre-framed that message as expected on GB10's unified memory. Before port 18789 could collide between the running host gateway and the incoming sandbox gateway, the skill had flagged the collision and proposed sequential operation. None of those are findings; they're all documented somewhere. The skill is what converts *"documented somewhere"* into *"surfaced the moment it matters."*

## The install, pre-empted into boredom

With prerequisites already satisfied on the Spark — Ollama running under systemd, Docker installed, Node 22, Nemotron 3 Super already pulled as `:latest` — the skill's install walkthrough gave me three prep edits and one installer invocation. Each had a specific known-in-advance trap.

**Bind Ollama beyond loopback.** The default binding is `127.0.0.1:11434`, reachable only from the host. NemoClaw's sandbox runs inside Docker and can't reach a loopback-only Ollama. The fix — a systemd drop-in — is additive:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0"\n' \
  | sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

The non-obvious bit: **don't** use `ollama serve &` to apply the new binding. A manual-start Ollama won't pick up the `OLLAMA_HOST` from the systemd drop-in, the sandbox silently can't find it, and the install wizard's "connection to inference" smoke test hangs. After the restart, `ss -ltnp` shows the listener move from `127.0.0.1:11434` to `*:11434` — call out on a trusted LAN that this does widen Ollama's exposure; if you're on a less-trusted network, bind to the Docker bridge IP instead.

**Fix Docker's cgroup namespace.** DGX Spark runs cgroup v2; OpenShell's in-Docker k3s needs host cgroup namespace access or it fails to start its container manager. The fix merges into `/etc/docker/daemon.json`:

```json
{
  "runtimes": {
    "nvidia": { "args": [], "path": "nvidia-container-runtime" }
  },
  "default-cgroupns-mode": "host"
}
```

An `nvidia-smi` through `--runtime=nvidia --gpus all` smoke test confirms both halves at once: runtime plumbing and GPU pass-through. On GB10 the table shows "Memory: Not Supported" — that's the unified-memory footprint, not a driver fault.

**Free port 18789.** The existing host `openclaw-gateway.service` holds it; NemoClaw's sandbox dashboard wants it. `openclaw gateway stop` frees it as a first-class systemd action. (Worth noting: the captured OpenClaw-via-Ollama docs don't mention that it runs as a named systemd service. Cleaner than the docs suggest; running things through `ss -ltnp` during the survey is how you'd find out.)

**The installer.** One line:

```bash
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
```

The interactive wizard wants a sandbox name (`clawnav`), an inference provider (Local Ollama), a model tag (`nemotron-3-super:latest`), policy presets (accept), and — if you enable the Telegram bridge — your Telegram user ID. One friction worth flagging: if you try to find your Telegram user ID by opening `web.telegram.org/a/#<number>`, the number in the URL hash is the *currently open chat*, not your own user id. Message `@userinfobot` from within Telegram; it tells you yours in two seconds.

Wall clock for the whole wizard: **1,690 seconds. Twenty-eight minutes.** That number matters, and I'll come back to it.

What the wizard leaves you with is three listeners and a tokenized URL:

```
0.0.0.0:8080     → openshell gateway
0.0.0.0:11435    → nemoclaw ollama-auth-proxy
127.0.0.1:18789  → openclaw dashboard (tokenized)

Dashboard: http://127.0.0.1:18789/#token=<64-hex-token>
```

The token is an anti-CSRF gate, not an account password. It's bound to the install; rotate via `nemoclaw <sandbox> config rotate-token` if you ever need to. And the dashboard is origin-checked against the exact string `127.0.0.1` — `localhost` will be rejected. Obvious once you know, non-obvious until you've been bitten.

## What success feels like, and one small paradox

`nemoclaw clawnav status` prints the summary view, and it carries two details worth pausing on:

```text
Inference: healthy (http://127.0.0.1:11434/api/tags)
GPU:       yes
Agent:     OpenClaw v2026.4.2

Policies: npm, pypi, huggingface, brew, brave, local-inference, telegram

filesystem_policy:
  read_only:  [/usr, /lib, /proc, /dev/urandom, /app, /etc, /var/log,
               /sandbox, /sandbox/.openclaw]
  read_write: [/tmp, /dev/null, /sandbox/.openclaw-data,
               /sandbox/.nemoclaw, /sandbox]
landlock:    compatibility: best_effort
```

![NemoClaw dashboard (v2026.4.2) with an active glm-4.7-flash session — the left sidebar exposes every control surface the sandbox owns (Chat, Channels, Instances, Sessions, Usage, Cron Jobs, Agents, Skills, Nodes, Config, Communications, Docs) while the main pane shows a live agent response flowing through the gateway](./screenshots/01-nemoclaw-dashboard.png)

*The dashboard is the visual face of the same policy `clawnav status` prints. A chat session talking to host `local-inference` via the gateway, tool calls bounded by the allowed-egress set, writes bounded to `/sandbox/.openclaw-data` and `/sandbox/.nemoclaw`. Narrow ingress, narrow egress, narrow write surface — rendered.*

The **GPU paradox**: the install wizard said "No GPU detected" — the GB10's unified memory doesn't report VRAM the way the wizard's probe expects. But `nemoclaw status` says `GPU: yes`, because the sandbox sees devices passed through via `--runtime=nvidia`. Two different signals, two different answers, both correct. File that away.

The **version skew**: the sandbox ships OpenClaw v2026.4.2; the host's independently-updated OpenClaw is v2026.4.20. Two weeks of the OpenClaw release cadence. If I later measure a quality difference between the two paths, that gap is a confound.

And the **narrow policy surface**: `npm, pypi, huggingface, brew, brave, local-inference, telegram` is a legible allowlist. The sandbox can reach package ecosystems, Hugging Face, the Brave search API, the host Ollama, and the Telegram bridge. Not the open internet. Not my git repos. Not my shell history. That's the product in one line.

Inside the sandbox shell (`nemoclaw clawnav connect`), one documented command from the captured NemoClaw instructions immediately reminds you this is not the host:

```text
sandbox$ openclaw agent --agent main --local -m "hello" --session-id test

Error: 'openclaw agent --local' is not supported inside NemoClaw sandboxes.
The --local flag bypasses the gateway's security protections (secret
scanning, network policy, inference auth) and can crash the sandbox.
```

That's the point. The `--local` flag bypasses the gateway, which is the *whole reason* you're in a sandbox. The flag is explicitly closed inside the box. The captured documentation is from a slightly earlier OpenClaw era and hadn't caught up — a small but exact example of why skill-references frozen at time T need a refresh lifecycle. I fixed the reference in-session; the next install won't trip on it.

## The A/B that went somewhere unexpected

The question I cared about: same prompt, same Nemotron weights, same Ollama — how much does the sandbox layer add? Before measuring anything, one sanity receipt. Both stacks configured for `nemotron-3-super`; both tags (`:latest` and `:120b`) registered against image ID `95acc78b3ffd` in Ollama's registry; `ollama show` confirms the underlying model is **`nemotron_h_moe`, 123.6 B parameters, Q4_K_M, 262k context**. One blob, three labels, both paths invoke it. The popular "128 B" number is an approximation — the H-MoE family has several sizes at that order and the right number matters.

With that confirmed, three-way measurement of one question ("In one sentence, what model are you and what size?"):

| Path | Wall clock | What actually happened |
|---|---:|---|
| Raw Ollama (`ollama run`) | **10 s** | Clean answer. The reasoning trace shows the model *noticed* the system message didn't specify a size and explicitly declined to invent one. |
| Host OpenClaw `--local` | 77 s | Greeting, not an answer — "Hey. I just came online. Who am I?" |
| NemoClaw sandbox | 140 s | Answer, but with a hallucinated size ("22 billion parameters"). |

The 10-second raw baseline is what Ollama does on its own. The 140-second sandbox number is **14× that**, which would be an easy and wrong headline. So I ran a second prompt — the Fibonacci one-liner — to pull apart what I was actually measuring.

| Path | Round 2 wall clock | Overhead vs raw |
|---|---:|---:|
| Raw Ollama | 26 s | 0 |
| NemoClaw sandbox | **52 s** | **+26 s (~2× raw)** |
| Host OpenClaw `--local` | stuck in USER.md bootstrap | n/a |

<figure class="fn-diagram" aria-label="Per-turn wall-clock across the first two turns of interaction. Raw Ollama stays low at 10 and 26 seconds. NemoClaw sandbox drops sharply from 140 seconds at turn 1 to 52 seconds at turn 2, converging toward the raw baseline. The host OpenClaw measures 77 seconds at turn 1 and then stalls in USER.md onboarding, never returning an answer — indicated by a dashed trajectory diverging upward with a warning glyph.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Per-turn wall-clock across the first two turns of interaction. Raw Ollama stays low at 10 and 26 seconds. NemoClaw sandbox drops sharply from 140 seconds at turn 1 to 52 seconds at turn 2, converging toward the raw baseline. The host OpenClaw measures 77 seconds at turn 1 and then stalls in USER.md onboarding, never returning an answer — indicated by a dashed trajectory diverging upward with a warning glyph." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d02-plot-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    <rect x="110" y="40" width="730" height="320" fill="url(#d02-plot-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 110 360 L 840 360" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 110 280 L 840 280" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 110 200 L 840 200" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 110 120 L 840 120" />
      <path class="fn-diagram__edge fn-diagram__edge--ghost" d="M 110 40 L 840 40" />
      <path class="fn-diagram__edge" pathLength="100" d="M 110 40 L 110 360" />
      <path class="fn-diagram__edge" pathLength="100" d="M 110 360 L 840 360" />
      <path class="fn-diagram__edge" pathLength="100" d="M 315 344 L 645 318" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 315 136 L 645 276" />
      <path class="fn-diagram__edge fn-diagram__edge--dashed" d="M 315 236 L 820 52" />
    </g>
    <g class="fn-diagram__nodes">
      <circle class="fn-diagram__dot" cx="315" cy="344" r="5" />
      <circle class="fn-diagram__dot" cx="645" cy="318" r="5" />
      <circle class="fn-diagram__dot fn-diagram__dot--accent" cx="315" cy="136" r="7" />
      <circle class="fn-diagram__dot fn-diagram__dot--accent" cx="645" cy="276" r="7" />
      <circle class="fn-diagram__dot fn-diagram__dot--ghost" cx="315" cy="236" r="5" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="364" text-anchor="end">0</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="284" text-anchor="end">50</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="204" text-anchor="end">100</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="124" text-anchor="end">150</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="100" y="44" text-anchor="end">200</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="315" y="398" text-anchor="middle">TURN 1 · COLD</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="645" y="398" text-anchor="middle">TURN 2 · WARM</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="110" y="26" text-anchor="start">wall-clock (seconds)</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="340" y="130" text-anchor="start">NemoClaw sandbox</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="660" y="272" text-anchor="start">52s</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="300" y="128" text-anchor="end">140s</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="660" y="326" text-anchor="start">raw Ollama</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="660" y="342" text-anchor="start">26s</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="340" y="232" text-anchor="start">host OpenClaw — 77s, then stuck</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="800" y="76" text-anchor="end">never converges</text>
      <text class="fn-diagram__annotation" x="300" y="156" text-anchor="end">onboarding pre-paid at install (28 min)</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon fn-diagram__icon--accent" transform="translate(485 110) scale(0.9)"><path d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941"/></g>
      <g class="fn-diagram__icon fn-diagram__icon--muted" transform="translate(630 320) scale(0.8)"><path d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5m.75-9l3-3 2.148 2.148A12.061 12.061 0 0116.5 7.605"/></g>
      <g class="fn-diagram__icon" transform="translate(810 24) scale(0.9)"><path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.008v.008H12v-.008z"/></g>
    </g>
  </svg>
  <figcaption>NemoClaw converges on the raw baseline because the wizard absorbed the onboarding; the host can't, because it's still running it.</figcaption>
</figure>

The NemoClaw second-prompt number drops from 140 s to 52 s — a factor of 2.7 — once Ollama's weights are warm in unified memory and the agent's session is live. That leaves **~26 seconds of steady-state sandbox tax** on top of ~26 seconds of raw inference. A clean 2× per turn.

The host number won't converge, though. Every new `openclaw agent --local` call, warm session or cold, returns the same thing: a polite onboarding dialog asking my name, pronouns, timezone, and notes for a USER.md file, promising to "answer your Python Fibonacci question" *after* we finish setup. Each of those stalled turns is a full inference round-trip — 67 to 142 seconds — and I'm never going to get to steady state on the host without completing the ceremony.

**NemoClaw paid the onboarding cost once, inside its 28-minute install wizard.** The SOUL.md and USER.md that the host demands were prefilled in the container image. That's what the 1,690 seconds was actually buying: a ready-to-work agent, not just a Landlock-and-seccomp container.

The essay's headline is not "NemoClaw is 2× slower." It's this:

- For a solo builder on a **fresh** DGX Spark, NemoClaw is the **faster** path to first useful answer, because it absorbs the onboarding fight into the installer. The host path is faster *per turn once you've done the ceremony*; the sandbox is faster *to get to the first answer of any kind*.
- The steady-state sandbox tax is **~2× raw inference** per turn. That's the cost of: OpenAI-compat wrapping, k3s routing, an SSH-tunneled gateway, the auth-proxy on 11435, and two weeks of OpenClaw improvements the sandbox's pinned image doesn't have yet.
- Cold-start in round 1 was confounded by Ollama loading 86 GB of Nemotron into unified memory *simultaneously* with the agent framework establishing its first session. Round 2 separates the two. Any single-shot benchmark that doesn't warm both layers first is going to print the wrong number by ~3×.

Three smaller findings that didn't fit a table, but should:

- **The model lies about itself more inside the agent framework.** Raw Ollama's trace explicitly declined to assert a parameter count it wasn't told. The same model running under OpenClaw's system prompt confidently said "22 billion." That's an agent-framework effect on model honesty, not a model property — and it's a reason to avoid benchmarking "model behavior" by asking the model about itself.
- **The dashboard's token looks like a password and isn't.** It's an anti-CSRF gate bound to a loopback-only listener. Treat it like a session cookie, not like an account credential. Rotate via `nemoclaw clawnav config rotate-token` if you commit it somewhere by accident.
- **Version drift inside the container is real.** The sandbox's OpenClaw is two weeks behind the host's. Over a quarter, that gap grows. Rebuild periodically — `nemoclaw <name> rebuild` upgrades the agent inside — or the sandbox's disadvantage widens for reasons that have nothing to do with sandboxing.

## What this unlocks for a personal AI builder

Three concrete things you can do this week once these two claws live on one Spark:

**Use NemoClaw as the default for anything exploratory.** If you're letting an agent run shell commands, grep your filesystem, or chase a tool call down a rabbit hole, do it in the sandbox. The 2× per-turn tax is small enough not to notice on tasks where you're already tolerant of 30-60 second agent latency, and the Landlock + seccomp + netns containment means a bad tool call can't wander out of `/sandbox`. The host OpenClaw is the tool you use for *you* — your real USER.md, your real work — once it's onboarded. Different machines for different risk profiles, on the same machine.

**Turn any product's docs into a one-session Claude Code skill before you install the product.** The pattern this piece used — absorb three to six canonical sources into a six-file skill with routing logic, then execute the install through the skill — is reproducible for anything you're about to touch for the first time. NeMo Microservices, NIM Agent Blueprints, Triton, TensorRT-LLM Serve — each has its own documentation maze and its own per-hardware gotchas. Front-loading an hour of skill-authoring turns a three-hour "figure it out as you go" install into a 30-minute pre-empted one. And the skill keeps paying rent on every subsequent debug, because the gotchas are hoisted where you and your editor can both see them.

**A/B the cloud alternative without leaving your desk.** The same sandbox that isolates NemoClaw can host an agent pointing at Anthropic or OpenAI instead of local Ollama (NemoClaw's provider picker has options for both). Same prompts, same harness, same box — the numbers tell you what you're actually paying for cloud inference above the value you'd get locally. On a DGX Spark that fits a 123 B model in memory, that comparison lands differently than it would on a laptop.

## The tax math for one person on one machine

The blast-radius math for a solo builder on one machine is not the same as for a team on a cluster. An enterprise running agents at scale can afford a sandbox tier, an identity tier, a per-tenant-key tier. I can't — or rather, I can, but the accounting has to balance on my own time, on this one Spark, in the afternoons I can give it. That's why "what does the sandbox cost" is a real question and "what do I get for it" is a shorter answer than it looks.

What I got was: 28 minutes of wizard in exchange for an agent that was *done* with onboarding when the install finished, a 2× steady-state inference tax as the rent on isolation, a legible filesystem policy that prints every time I check the status, and a disambiguation pass between NemoClaw and OpenClaw-via-Ollama that I no longer need to redo. What I also got was a skill — `nemoclaw-guru` — that pre-empted every install hazard the captured documentation covers, and one hazard it didn't, and will take thirty seconds to update when NemoClaw ships v0.0.22.

The next essay is the one where I push steady-state harder: same NemoClaw sandbox, same Nemotron, but a multi-turn tool-use harness instead of the single-shot toy prompts this piece used. Does the 2× hold when the agent is actually *agenting* — running tools, recovering from errors, stitching context across turns? I suspect the answer is "no, it's different again, and the onboarding frame we landed in this piece is going to show up somewhere else in the steady-state one." That's the follow-up to read if you care about what the DGX Spark is for on a Monday morning.

## Postscript: decomposing the 2× tax

The "2× steady-state sandbox tax" I landed on above is a wall-clock number through the whole agent loop. Later the same afternoon I went back and measured the one piece of the stack I could isolate — the inference hop itself — with `curl` against both endpoints, same prompt, same Nemotron weights, no agent framework in the path.

```
Native :11434 (host OpenClaw path): 0.659 / 0.680 / 0.702 s  → p50 ~680 ms
NemoClaw auth-proxy :11435:         0.711 / 0.719 / 0.683 s  → p50 ~700 ms
```

Three warm runs each, 8-token reply, `curl -w %{time_total}`. **The auth-proxy hop adds ~20–30 ms per request.** That's a small enough fraction of the ~26-second steady-state tax that I can finally say where the rest is going: OpenAI-compat wrapping, k3s routing, and OpenClaw's own session and tool-loop overhead inside the container. The network is not the bottleneck. The agent framework is.

While I was already poking, I pulled the actual model params for the two weights present on this Spark:

| Model | Arch | Params | Context | Quant | Eval tok/s | Cold load |
|---|---|---:|---:|---|---:|---:|
| `nemotron-3-super:latest` | nemotron_h_moe | 123.6 B | 262,144 | Q4_K_M | ~22 | ~15 s (86 GB) |
| `glm-4.7-flash:latest` | glm4moelite | 29.9 B | 202,752 | Q4_K_M | ~65 | ~10.5 s (19 GB) |

Both carry `completion + tools + thinking` capabilities; both sit well above OpenClaw's documented 64k-context floor.

The takeaway for a solo builder on one Spark: **"NemoClaw feels slower" is usually a model-pinning story, not a sandboxing story.** `clawnav` is pinned to Nemotron (22 tok/s); a fresh host `ollama launch openclaw` would happily pick `glm-4.7-flash` (~3× the throughput, ~5 s faster off cold start). Rebuild the sandbox on the smaller model and you get OpenClaw-class responsiveness *inside* the sandbox. The choice between the two stacks should be about isolation versus host access — not perceived throughput.
