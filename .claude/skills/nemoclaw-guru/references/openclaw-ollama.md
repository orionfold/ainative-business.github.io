# OpenClaw (via Ollama integration) — reference

This reference covers **OpenClaw launched as an Ollama integration** (`ollama launch openclaw`), a *different* product from NVIDIA NemoClaw. The rest of this skill is about NemoClaw (the OpenClaw-in-OpenShell sandbox stack). Route here when the user is running or asking about `ollama launch openclaw` / `ollama launch clawdbot` / `ollama launch moltbot` specifically, or when their DGX Spark shows the Ollama integration present but no NemoClaw state.

Captured from official sources (April 2026):
- https://docs.ollama.com/integrations/openclaw
- https://ollama.com/blog/openclaw
- https://ollama.com/blog/openclaw-tutorial
- https://openclaw-ai.com/en/docs/providers/ollama/

## What it is

> "OpenClaw is a personal AI assistant that runs on your own devices" and "bridges messaging services (WhatsApp, Telegram, Slack, Discord, iMessage, and more) to AI coding agents through a centralized gateway."

Previously named **Clawdbot** and **Moltbot** — both names still work as Ollama integration aliases. Ollama 0.18+ ships OpenClaw as a built-in integration target of the `ollama launch` command.

**This is not a sandbox.** OpenClaw-via-Ollama runs on the host. It has no OpenShell container, no k3s gateway, no `~/.nemoclaw/` state, no `nemoclaw` CLI. Isolation must come from something else if you need it.

## Launch commands

```bash
# Interactive: pulls model if missing, installs OpenClaw if missing, starts gateway, opens TUI
ollama launch openclaw

# Pick a specific model
ollama launch openclaw --model kimi-k2.5:cloud

# Headless (auto-pull model, skip selectors) — for Docker, CI/CD, scripts. --model is required.
ollama launch openclaw --model kimi-k2.5:cloud --yes

# Configure without launching the gateway
ollama launch openclaw --config

# Aliases — all equivalent
ollama launch clawdbot
ollama launch moltbot
```

Ollama `launch` subcommand help (verified locally): `--config`, `--model <string>`, `-y/--yes`, plus trailing `-- <extra args>` passed through to the integration.

## Messaging channels

Configured separately from launch:

```bash
openclaw configure --section channels
```

Supported: WhatsApp, Telegram, Slack, Discord, iMessage, and more. Official docs do not currently document specific token/credential formats — if the user needs that detail, point them at `openclaw configure --section channels` on their machine and the OpenClaw docs.

## Gateway

- Starts in the background on `ollama launch openclaw` and opens the TUI.
- Stop it: `openclaw gateway stop`.
- Web search and fetch are enabled **automatically** when OpenClaw is launched through Ollama. For local models, web search requires `ollama signin`.
- Specific gateway port / origin-check rules are not in the captured sources. Don't invent them. If the user needs the port, have them check `ss -ltnp` or `openclaw gateway status` (plausible but unverified — suggest `openclaw --help` first).

## Ollama as the model provider — config details

OpenClaw talks to Ollama at `http://127.0.0.1:11434` by default (native `/api/chat`, which supports streaming + tool calling).

**Implicit discovery (recommended):**

```bash
export OLLAMA_API_KEY="ollama-local"
```

With that set and no explicit `models.providers.ollama` entry in the OpenClaw config, OpenClaw auto-discovers tool-capable models from the local Ollama.

**Explicit config** (when Ollama is on another host/port, or you want to pin models):

```json
{
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "http://ollama-host:11434",
        "apiKey": "ollama-local",
        "api": "ollama",
        "models": [
          {
            "id": "gpt-oss:20b",
            "name": "GPT-OSS 20B",
            "reasoning": false,
            "input": ["text"],
            "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
            "contextWindow": 8192,
            "maxTokens": 81920
          }
        ]
      }
    }
  }
}
```

**OpenAI-compat fallback** (use only if you need it): set `"api": "openai-completions"` and `"baseUrl": "http://ollama-host:11434/v1"`. Caveat from the docs: this endpoint may not support streaming with tool calling simultaneously — set `"params": { "streaming": false }` if tool calls break.

## Models

The docs call out these as current recommendations:

- **Cloud:** `kimi-k2.5`, `qwen3.5`, `glm-5.1`, `minimax-m2.7`
- **Local:** `gemma4` (~16 GB VRAM), `qwen3.5` (~11 GB VRAM), plus `qwen3-coder`, `glm-4.7`, and the `gpt-oss` series

**Hard requirement: ≥ 64k context window**, and the model must support tool calling. Anything smaller makes agents unreliable.

Models in use on the user's DGX Spark (as of 2026-04-21): `nemotron-3-super:latest` (86 GB, nemotron_h_moe, 123.6B params, 262k ctx, tools+thinking) and `glm-4.7-flash:latest` (19 GB). Both are well above the 64k floor.

## OpenClaw-via-Ollama vs NemoClaw — when to route where

| Signal | OpenClaw-via-Ollama (this file) | NemoClaw (rest of skill) |
|---|---|---|
| Entry command | `ollama launch openclaw` / `clawdbot` / `moltbot` | `nemoclaw` CLI, `nemoclaw onboard`, `nemoclaw.sh` |
| State on disk | Ollama's own dirs; no `~/.nemoclaw/` | `~/.nemoclaw/`, OpenShell containers |
| Isolation | None — runs on host | OpenShell sandbox (Docker + k3s gateway) |
| Messaging bridge | `openclaw configure --section channels` | NemoClaw's own Telegram bridge setup |
| Fails with | "openclaw: integration not found" (old Ollama), missing model | cgroup v2 errors, k3s/CoreDNS, origin-check on `localhost` |

If the survey block at the top of SKILL.md shows **no** `nemoclaw`, `openshell`, `~/.nemoclaw/`, or nemoclaw containers, but `ollama` is active and `ollama launch --help` lists `openclaw`, the user is on the Ollama-integration path — use this file, not the NemoClaw references.

## What is NOT in these sources (do not invent)

- Gateway port numbers, origin-allowlist rules.
- Exact on-disk path of the OpenClaw config file.
- Credential formats for Telegram/WhatsApp/Slack/Discord/iMessage bridges.
- Sandboxing / seccomp / user-namespace behavior (there is none documented for this path).
- A `debug` subcommand. Suggest `openclaw --help` on the user's machine before recommending anything unlisted.

If the user asks about any of the above, say it isn't in the captured references and point them at `openclaw --help` / `docs.ollama.com/integrations/openclaw` / `openclaw-ai.com/en/docs/`.
