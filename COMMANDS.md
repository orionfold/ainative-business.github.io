# COMMANDS

Repeat commands for the local AI stack on this DGX Spark. Sandbox name is `clawnav`. Current default model is `glm-4.7-flash:latest`.

## Ollama (inference backend)

```bash
# Service lifecycle
sudo systemctl start ollama
sudo systemctl stop ollama
sudo systemctl restart ollama
systemctl is-active ollama

# Models on disk
ollama list

# Models currently resident in UMA + ctx + expiry
curl -s http://127.0.0.1:11434/api/ps | python3 -m json.tool

# Unload a specific model from UMA (free memory without stopping Ollama)
curl -s -X POST http://127.0.0.1:11434/api/generate \
  -d '{"model":"<model-name>","keep_alive":0}'

# Warm-load a model into UMA
ollama run <model> "hi" < /dev/null

# One-off chat
ollama run glm-4.7-flash

# Pull / remove
ollama pull <model>
ollama rm <model>
```

## NemoClaw sandbox (clawnav)

```bash
# Status — model, policies, inference health
nemoclaw clawnav status

# Stream sandbox logs
nemoclaw clawnav logs --follow

# Open a host shell inside the sandbox (prompt becomes sandbox@clawnav:~$)
nemoclaw clawnav connect

# Rebuild the sandbox agent container (picks up config/policy changes)
nemoclaw clawnav rebuild

# Destroy and recreate from scratch (interactive wizard)
nemoclaw onboard

# List registered sandboxes + host service state
nemoclaw status
nemoclaw list

# Auxiliary host services (cloudflared tunnel, legacy Telegram bridge)
nemoclaw start
nemoclaw stop
```

## OpenClaw TUI (inside sandbox)

```bash
# Step 1: enter the sandbox
nemoclaw clawnav connect

# Step 2: launch the TUI (Ctrl+C to exit)
openclaw tui

# Exit the sandbox shell
exit
```

Single-shot message without the TUI:

```bash
openclaw agent --agent main --local -m "hello" --session-id scratch
```

## OpenShell gateway (host)

```bash
# Gateway-level monitoring TUI (egress approvals, sandbox state)
openshell term

# Port-forward the OpenClaw dashboard on 18789
openshell forward start 18789 clawnav --background
openshell forward list
openshell forward stop 18789

# Last-resort gateway restart (kills all sandboxes)
openshell gateway destroy
openshell gateway start
```

Dashboard URL: `http://127.0.0.1:18789/#token=<token-from-onboard>`. Must be `127.0.0.1`, not `localhost` — gateway origin check is strict.

## Copy a file into the sandbox

`openshell sandbox upload` is broken on v0.0.26 — reports success, writes nothing. Use exec+stdin:

```bash
# Ensure target dir exists
openshell sandbox exec -n clawnav -- mkdir -p /sandbox/.openclaw-data/workspace/<subdir>

# Stream the file in
cat <host-path> | openshell sandbox exec -n clawnav --no-tty -- \
  sh -c 'cat > /sandbox/.openclaw-data/workspace/<subdir>/<filename>'

# Verify
openshell sandbox exec -n clawnav -- ls -la /sandbox/.openclaw-data/workspace/<subdir>/
```

Agent sees the file by path relative to workspace root, e.g. `nvidia-learn/ideas/foo.md`.

Writable roots inside the sandbox: `/sandbox`, `/sandbox/.openclaw-data`, `/sandbox/.nemoclaw`. `/sandbox/.openclaw` is read-only.

## Telegram channel

The Telegram bridge runs as an OpenClaw native channel inside the sandbox (not a host-side `nemoclaw` service on v0.0.21). It auto-starts with the agent. No command needed.

To test: message your bot. To see traffic:

```bash
nemoclaw clawnav logs --follow
```

To rotate the bot token: `nemoclaw credentials reset TELEGRAM_BOT_TOKEN` then `nemoclaw onboard`.

## Troubleshooting

### Shell doesn't have docker group (nemoclaw onboard fails at docker pull)

```bash
newgrp docker         # activates docker group in this shell only
# OR log out and back in for all shells to pick it up
```

### UMA feels full even though nothing is loaded

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

### GLM taking too much RAM due to 202K auto-context

Create a smaller-ctx variant via Modelfile:

```bash
cat > /tmp/glm-Modelfile <<'EOF'
FROM glm-4.7-flash:latest
PARAMETER num_ctx 32768
EOF
ollama create glm-4.7-flash:32k -f /tmp/glm-Modelfile
```

Then point clawnav at `glm-4.7-flash:32k` via `nemoclaw onboard` (or edit `/home/nvidia/.nemoclaw/sandboxes.json` and rebuild).

### Dashboard / Telegram not responding after fresh boot

```bash
sudo systemctl status ollama docker
nemoclaw clawnav status
nemoclaw clawnav logs --follow
```

## State files

- `/home/nvidia/.nemoclaw/sandboxes.json` — sandbox config, model pin
- `/home/nvidia/.nemoclaw/credentials.json` — hashed credential vault
- `/home/nvidia/.nemoclaw/source/` — cloned NemoClaw source + uninstaller
- `/etc/systemd/system/ollama.service.d/override.conf` — `OLLAMA_HOST=0.0.0.0`
