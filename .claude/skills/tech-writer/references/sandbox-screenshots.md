# Screenshotting sandboxed / containerized web UIs

This reference covers the case where the web UI you want to screenshot lives
inside an OpenShell/NemoClaw sandbox (or any other local-only container)
whose port is only reachable from the host via a 1:1 port forward — and
another service on the host already binds that same port.

The canonical case: **NemoClaw's sandbox dashboard** runs on the sandbox's
own `127.0.0.1:18789`, but the **host OpenClaw gateway** also binds host
`127.0.0.1:18789` when installed. `openshell forward` does **1:1 port
mapping only** (no remap), so to reach the sandbox dashboard from a
host-side browser you must first vacate host :18789.

## Pattern: temporary gateway swap

```bash
# 1. Stop the host gateway (releases :18789 on the host).
systemctl --user stop openclaw-gateway

# 2. Open a 1:1 forward sandbox :18789 → host :18789 in the background.
openshell forward start -d 18789 <sandbox-name>

# 3. Fetch the sandbox's dashboard token from its gateway config.
TOKEN=$(openshell sandbox exec -n <sandbox-name> --no-tty -- \
  cat /sandbox/.openclaw/openclaw.json \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["gateway"]["auth"]["token"])')

# 4. Screenshot the sandbox dashboard.
node ~/.claude/skills/tech-writer/scripts/playwright-screenshot.js \
  "http://127.0.0.1:18789/#token=${TOKEN}" \
  articles/<slug>/screenshots/NN-sandbox-dashboard.png

# 5. Tear down the forward; restart the host gateway.
openshell forward stop 18789 <sandbox-name>
systemctl --user start openclaw-gateway
```

## Before you run

- **Check for live clients on host :18789.** A running Firefox/Chrome tab on
  the host gateway holds an ESTABLISHED connection. Stopping the gateway
  will break the tab — the user reloads, no data is lost, but surprise the
  user and you've earned a correction. Check first:
  ```bash
  ss -tnp 2>&1 | grep ':18789' | grep -v LISTEN
  ```
  If any connection is owned by a browser process, ask the user before
  proceeding.

- **Confirm both gateways share the port.** Output of `ss -ltnp | grep 18789`
  should show `openclaw-gateway` on the host. If it shows something else,
  don't blindly stop it — investigate.

- **Skip the swap entirely if the sandbox exposes a second port.** Some
  sandboxes publish a read-only observability endpoint on a different port
  that doesn't collide. Check `openclaw.json` for additional listeners
  before dismantling shared infrastructure.

## What to capture

The sandbox dashboard's point is the **policy surface** — what the agent
can and can't reach, the writable dirs, the allowed-egress set, the live
session list. Favor a shot that shows those side-by-side with a real
session in progress. Avoid the login screen (it tells the reader nothing
beyond "there's a token").

## Redaction checklist specific to sandbox UIs

- **Session IDs** — visible in the URL and the Sessions tab. Treat as
  low-sensitivity but be ready to redact per the user's preference.
- **Sandbox UUIDs** — shown in some dashboard panes. Match the handoff
  doc policy; previous articles redacted the first 8 hex chars.
- **Bridge credentials** (Telegram, WhatsApp, Slack, Discord) — should
  never appear on a dashboard page, but verify by reading the PNG before
  committing.
- **Ollama / backend URLs** with auth query strings — unlikely but check.

## A full worked example

Wrap the above into a single shell script and run it with one command
(avoids terminal line-wrap mangling when multiple operators need chaining):

```bash
cat > /tmp/grab-sandbox-dashboard.sh <<'EOF'
#!/usr/bin/env bash
set -e
SANDBOX="${1:-clawnav}"
OUT="${2:?usage: grab-sandbox-dashboard.sh <sandbox-name> <out.png>}"

systemctl --user stop openclaw-gateway
openshell forward start -d 18789 "$SANDBOX"
sleep 1
TOKEN=$(openshell sandbox exec -n "$SANDBOX" --no-tty -- \
  cat /sandbox/.openclaw/openclaw.json \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["gateway"]["auth"]["token"])')
node ~/.claude/skills/tech-writer/scripts/playwright-screenshot.js \
  "http://127.0.0.1:18789/#token=${TOKEN}" "$OUT"
openshell forward stop 18789 "$SANDBOX" || true
systemctl --user start openclaw-gateway
ls -lh "$OUT"
EOF
bash /tmp/grab-sandbox-dashboard.sh clawnav \
  articles/<slug>/screenshots/01-nemoclaw-dashboard.png
```

The host gateway is down for ~5–15 seconds. Firefox tabs reconnect on
reload; no state is lost on either side.
