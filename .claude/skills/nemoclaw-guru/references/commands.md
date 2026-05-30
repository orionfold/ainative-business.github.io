# NemoClaw CLI Reference (consolidated)

Synthesized from `instructions.md`, `troubleshooting.md`, and `repo-overview.md` in this skill. Only commands confirmed by those sources appear here; commands from unverified third-party posts are omitted. If a command isn't listed here, consult the official CLI reference at docs.nvidia.com/nemoclaw/latest/ before recommending it.

Conventions: `<name>` is the sandbox name chosen during `nemoclaw onboard`. All `nemoclaw …` commands run on the host unless noted otherwise.

## Lifecycle

| Command | Purpose |
|---|---|
| `curl -fsSL https://www.nvidia.com/nemoclaw.sh \| bash` | One-shot installer (Node.js + OpenShell + NemoClaw + onboard wizard) |
| `nemoclaw onboard` | Re-run the onboarding wizard (interactive) |
| `cd ~/.nemoclaw/source && ./uninstall.sh [--yes] [--keep-openshell] [--delete-models]` | Full uninstall |
| `curl -fsSL https://raw.githubusercontent.com/NVIDIA/NemoClaw/refs/heads/main/uninstall.sh \| bash` | Uninstall without a local source clone |

## Sandbox management

| Command | Purpose |
|---|---|
| `nemoclaw list` | List all registered sandboxes |
| `nemoclaw <name> connect` | Shell into the sandbox |
| `nemoclaw <name> status` | Sandbox health + inference config |
| `nemoclaw <name> logs --follow` | Stream sandbox logs |

## Network policies

| Command | Purpose |
|---|---|
| `nemoclaw <name> policy-add` | Interactively add a preset (e.g. `telegram`) |

## Auxiliary host services (Telegram bridge, cloudflared)

| Command | Purpose |
|---|---|
| `nemoclaw start` | Start auxiliary services (Telegram bridge starts only if `TELEGRAM_BOT_TOKEN` is exported) |
| `nemoclaw stop` | Stop auxiliary services (known bug: may not fully kill the Telegram bridge — fall back to `kill -9 <PID>` from `nemoclaw start` output) |
| `nemoclaw status` | Show running host services |

## DGX Spark host helpers

| Command | Purpose |
|---|---|
| `sudo nemoclaw setup-spark` | Applies the Docker `default-cgroupns-mode: host` fix automatically (used when gateway errors with "Failed to start ContainerManager") |

## OpenShell commands (host)

| Command | Purpose |
|---|---|
| `openshell term` | Monitoring TUI on the host |
| `openshell forward list` | List active port forwards |
| `openshell forward start 18789 <name> --background` | Start Web UI port forward on 18789 |
| `openshell forward stop 18789 [<name>]` | Stop a port forward |
| `openshell gateway destroy [-g <name>]` | Destroy the OpenShell gateway (used to clear stale state or free port 8080) |
| `openshell gateway start` | Start the OpenShell gateway |

## OpenClaw commands (inside sandbox)

Run these after `nemoclaw <name> connect`.

| Command | Purpose |
|---|---|
| `openclaw tui` | Interactive terminal UI (`Ctrl+C` to exit) |
| `openclaw agent --agent main --local -m "hello" --session-id test` | Send a single message via CLI |
| `curl -sf https://inference.local/v1/models` | Verify inference route is reachable from within the sandbox |

## Environment variables

| Variable | Where used |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Required for `nemoclaw start` to launch the Telegram bridge |
| `SANDBOX_NAME` | Required for Telegram bridge; must match the sandbox name from onboarding |
| `NVIDIA_API_KEY` | Used by NVIDIA-hosted inference providers |
| `OLLAMA_HOST=0.0.0.0` | Set via systemd override so the sandbox can reach host Ollama |

## Ports to know

| Port | Service |
|---|---|
| 8080 | OpenShell gateway (host) |
| 11434 | Ollama (host) |
| 18789 | NemoClaw Web UI dashboard (via `openshell forward …`) |

## Dashboard access

- Local: `http://127.0.0.1:18789/#token=<token>` (must be `127.0.0.1`, not `localhost`).
- Remote: `openshell forward start 18789 <name> --background` on the Spark, then SSH tunnel `ssh -L 18789:127.0.0.1:18789 <user>@<spark-ip>` from the client.

## What's deliberately NOT listed here

Commands that are plausible but not confirmed by the three official sources in this skill (e.g., `nemoclaw debug`, `nemoclaw credentials reset`, `nemoclaw <name> rebuild`, `nemoclaw <name> snapshot …`, `nemoclaw backup-all`, `nemoclaw <name> destroy`, `nemoclaw <name> skill install`, `nemoclaw upgrade-sandboxes`). These may exist in the product but must be verified against `docs.nvidia.com/nemoclaw/latest/reference/commands.html` or `nemoclaw help` on the user's machine before recommending — do **not** invent command output. When the user asks about any of these, verify first.
