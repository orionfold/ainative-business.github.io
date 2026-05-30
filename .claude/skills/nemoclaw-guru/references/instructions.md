# NemoClaw on DGX Spark — Installation & Setup

Source: https://build.nvidia.com/spark/nemoclaw/instructions
Captured: 2026-04-21 (one-time traversal)
Playbook title: *NemoClaw with Nemotron 3 Super and Telegram on DGX Spark* (est. 30 minutes)

## Summary

Install NemoClaw on a fresh DGX Spark (Ubuntu 24.04, cgroup v2) with local Ollama inference and an optional Telegram bot bridge. Four phases:

1. Prerequisites — Docker + NVIDIA runtime, Ollama, model pull
2. Install and run NemoClaw — `nemoclaw.sh` one-liner, onboard wizard, sandbox verify
3. Telegram bot (optional)
4. Cleanup / uninstall

---

## Phase 1: Prerequisites

> Skip to Phase 2 if Docker, the NVIDIA runtime, and Ollama are already configured.

### Step 1 — Configure Docker and the NVIDIA container runtime

OpenShell's gateway runs k3s inside Docker. On DGX Spark (Ubuntu 24.04, cgroup v2), Docker must be configured with the NVIDIA runtime and host cgroup namespace mode.

Configure the NVIDIA container runtime for Docker:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
```

Set the cgroup namespace mode required by OpenShell on DGX Spark:

```bash
sudo python3 -c "
import json, os
path = '/etc/docker/daemon.json'
d = json.load(open(path)) if os.path.exists(path) else {}
d['default-cgroupns-mode'] = 'host'
json.dump(d, open(path, 'w'), indent=2)
"
```

Restart Docker:

```bash
sudo systemctl restart docker
```

Verify the NVIDIA runtime works:

```bash
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

If you hit `permission denied` on `docker`, add your user to the Docker group and activate it in the current session:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

`newgrp docker` applies the group change immediately. Alternatively, log out and back in.

> **Why this matters on DGX Spark:** DGX Spark uses cgroup v2. OpenShell's gateway embeds k3s inside Docker and needs host cgroup namespace access. Without `default-cgroupns-mode: host`, the gateway fails with "Failed to start ContainerManager" errors.

### Step 2 — Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Configure Ollama to listen on all interfaces so the sandbox container can reach it:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0"\n' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Verify:

```bash
curl http://0.0.0.0:11434
```

Expected: `Ollama is running`. If not, start it: `sudo systemctl start ollama`.

> **IMPORTANT:** Always start Ollama via systemd (`sudo systemctl restart ollama`) — **do not** use `ollama serve &`. A manually-started Ollama process does not pick up the `OLLAMA_HOST=0.0.0.0` setting above, and the NemoClaw sandbox will not be able to reach the inference server.

### Step 3 — Pull the Nemotron 3 Super model

Download Nemotron 3 Super 120B (~87 GB; 15–30 minutes typical):

```bash
ollama pull nemotron-3-super:120b
```

Pre-load weights into memory (type `/bye` to exit):

```bash
ollama run nemotron-3-super:120b
```

Verify:

```bash
ollama list
```

You should see `nemotron-3-super:120b`.

---

## Phase 2: Install and Run NemoClaw

### Step 4 — Install NemoClaw

Single command handles everything: installs Node.js (if needed), installs OpenShell, clones the latest stable NemoClaw release, builds the CLI, and runs the onboard wizard to create a sandbox:

```bash
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
```

The onboard wizard asks for:

- **Sandbox name** — lowercase alphanumeric with hyphens only (e.g. `my-assistant`).
- **Inference provider** — select **Local Ollama** (option 7).
- **Model** — select **nemotron-3-super:120b** (option 1).
- **Policy presets** — accept suggested presets (hit `Y`).

On success you see something like:

```
──────────────────────────────────────────────────
Dashboard    http://localhost:18789/
Sandbox      my-assistant (Landlock + seccomp + netns)
Model        nemotron-3-super:120b (Local Ollama)
──────────────────────────────────────────────────
Run:         nemoclaw my-assistant connect
Status:      nemoclaw my-assistant status
Logs:        nemoclaw my-assistant logs --follow
──────────────────────────────────────────────────
```

> **IMPORTANT:** Save the tokenized Web UI URL printed at the end — you need it in Step 8. It looks like:
>
> `http://127.0.0.1:18789/#token=<long-token-here>`

If `nemoclaw` is not found after install, run `source ~/.bashrc` to reload the shell PATH.

### Step 5 — Connect to the sandbox and verify inference

```bash
nemoclaw my-assistant connect
```

You will see `sandbox@my-assistant:~$` — you are inside the sandboxed environment.

Verify the inference route:

```bash
curl -sf https://inference.local/v1/models
```

Expected: JSON listing `nemotron-3-super:120b`.

### Step 6 — Talk to the agent (CLI)

Still inside the sandbox, send a test message:

```bash
openclaw agent --agent main --local -m "hello" --session-id test
```

The agent responds via Nemotron 3 Super. First responses can take 30–90 seconds for a 120B model running locally.

### Step 7 — Interactive TUI

```bash
openclaw tui
```

`Ctrl+C` to exit.

### Step 8 — Exit the sandbox and access the Web UI

```bash
exit
```

**Local access (keyboard + monitor on the Spark):** open a browser to the tokenized URL from Step 4:

```
http://127.0.0.1:18789/#token=<long-token-here>
```

**Remote access:** set up an SSH tunnel.

Find the Spark's primary IP:

```bash
hostname -I | awk '{print $1}'
```

On the Spark host, start the port forward:

```bash
openshell forward start 18789 my-assistant --background
```

From the remote machine:

```bash
ssh -L 18789:127.0.0.1:18789 <your-user>@<your-spark-ip>
```

Then open the tokenized URL in the remote browser.

> **IMPORTANT:** Use `127.0.0.1`, not `localhost` — the gateway origin check requires an exact match.

---

## Phase 3: Telegram Bot (optional)

> If Telegram was configured during the onboard wizard (step 5/8), skip this phase.

### Step 9 — Create a Telegram bot

Open Telegram, find `@BotFather`, send `/newbot`, follow the prompts. Copy the bot token.

### Step 10 — Configure and start the Telegram bridge

Run on the **host** (not inside the sandbox — `exit` first if you are).

Set environment variables. `SANDBOX_NAME` must match the name you chose in the onboard wizard:

```bash
export TELEGRAM_BOT_TOKEN=<your-bot-token>
export SANDBOX_NAME=my-assistant
export NVIDIA_API_KEY=<your-nvidia-api-key>
```

Add the Telegram network policy to the sandbox:

```bash
nemoclaw my-assistant policy-add
```

When prompted, select `telegram` and hit `Y`.

Start the Telegram bridge:

```bash
export TELEGRAM_BOT_TOKEN=<your-bot-token>
nemoclaw start
```

The Telegram bridge starts only when `TELEGRAM_BOT_TOKEN` is set. Verify:

```bash
nemoclaw status
```

Open Telegram, find your bot, send a message. First response: 30–90 seconds.

If the bridge does not appear in `nemoclaw status`, make sure `TELEGRAM_BOT_TOKEN` is exported in the same shell session where you run `nemoclaw start`. Restart if needed:

```bash
nemoclaw stop
export TELEGRAM_BOT_TOKEN=<your-bot-token>
nemoclaw start
```

For restricting which Telegram chats can interact with the agent, see the NemoClaw Telegram bridge documentation.

---

## Phase 4: Cleanup and Uninstall

### Step 11 — Stop services

Stop auxiliary services (Telegram bridge, cloudflared tunnel):

```bash
nemoclaw stop
```

Stop the port forward:

```bash
openshell forward list          # find active forwards
openshell forward stop 18789    # stop the dashboard forward
```

### Step 12 — Uninstall NemoClaw

Run the uninstaller from the cloned source directory. It removes all sandboxes, the OpenShell gateway, Docker containers/images/volumes, the CLI, and all state files. Docker, Node.js, npm, and Ollama are preserved.

```bash
cd ~/.nemoclaw/source
./uninstall.sh
```

**Uninstaller flags:**

| Flag | Effect |
|---|---|
| `--yes` | Skip the confirmation prompt |
| `--keep-openshell` | Leave the `openshell` binary in place |
| `--delete-models` | Also remove the Ollama models pulled by NemoClaw |

Remove everything including the Ollama model:

```bash
./uninstall.sh --yes --delete-models
```

**Uninstaller steps (6):**
1. Stop NemoClaw helper services and port-forward processes
2. Delete all OpenShell sandboxes, the NemoClaw gateway, and providers
3. Remove the global `nemoclaw` npm package
4. Remove NemoClaw / OpenShell Docker containers, images, and volumes
5. Remove Ollama models (only with `--delete-models`)
6. Remove state directories (`~/.nemoclaw`, `~/.config/openshell`, `~/.config/nemoclaw`) and the OpenShell binary

> The source clone at `~/.nemoclaw/source` is removed in step 6 of the uninstaller. Back it up first if you want to keep a local copy.

---

## Useful host commands (quick reference)

| Command | Description |
|---|---|
| `nemoclaw my-assistant connect` | Shell into the sandbox |
| `nemoclaw my-assistant status` | Sandbox status and inference config |
| `nemoclaw my-assistant logs --follow` | Stream sandbox logs |
| `nemoclaw list` | List all registered sandboxes |
| `nemoclaw start` | Start auxiliary services (Telegram bridge, cloudflared) |
| `nemoclaw stop` | Stop auxiliary services |
| `openshell term` | Monitoring TUI on the host |
| `openshell forward list` | List active port forwards |
| `openshell forward start 18789 my-assistant --background` | Restart port forwarding for Web UI |
| `cd ~/.nemoclaw/source && ./uninstall.sh` | Remove NemoClaw (preserves Docker, Node.js, Ollama) |
| `cd ~/.nemoclaw/source && ./uninstall.sh --delete-models` | Remove NemoClaw and Ollama models |

## Related resources (not fetched in this traversal)

- NemoClaw Documentation (docs.nvidia.com/nemoclaw/latest/...)
- OpenClaw Documentation
- DGX Spark Documentation
- DGX Spark Forum

If the user needs version-specific details that aren't covered here, point them at the NemoClaw Documentation rather than refetching at runtime.
