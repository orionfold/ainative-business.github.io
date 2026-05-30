---
name: nemoclaw-guru
description: Guide, install, operate, and troubleshoot NVIDIA NemoClaw (the OpenClaw-in-OpenShell sandbox agent stack) AND the Ollama-integrated OpenClaw CLI (`ollama launch openclaw` / `clawdbot` / `moltbot`) on NVIDIA DGX Spark and related Linux/WSL2 hosts. Use this skill whenever the user mentions NemoClaw, OpenClaw, Clawdbot, Moltbot, OpenShell sandboxes, the `nemoclaw` CLI, `nemoclaw onboard`, the `nemoclaw.sh` installer, `ollama launch openclaw`, sandbox rebuild/destroy/policy flows, k3s or CoreDNS failures in a NemoClaw context, Nemotron-backed agent sandboxes on DGX Spark, the Telegram/WhatsApp/Slack/Discord/iMessage bridge, or DGX Spark agent setup questions — even if they don't explicitly ask for documentation, don't mention "skill", and only describe a symptom ("my assistant sandbox won't start", "port 8080 is held", "origin not allowed", "cgroup v2 error on Ubuntu 24.04", "openclaw integration not found"). Prefer this skill over general web search whenever a question touches NemoClaw or OpenClaw.
---

# nemoclaw-guru

Help the user install, operate, and fix NemoClaw on their DGX Spark. A local knowledge reference (built from the three official docs at skill-creation time) lives next to this file in `references/`. Do **not** re-fetch those URLs during normal use — the local references are the source of truth for this skill, and re-fetching both costs time and loses reproducibility.

## Before recommending anything, survey the local state

Claude is running on the user's DGX Spark host. Check what actually exists before giving advice:

```bash
command -v nemoclaw && nemoclaw --version || echo "nemoclaw not on PATH"
command -v openshell && openshell --version || echo "openshell not on PATH"
ls -d ~/.nemoclaw 2>/dev/null || echo "no ~/.nemoclaw state dir"
docker ps -a --format '{{.Names}}\t{{.Image}}' 2>/dev/null | grep -i -E 'nemo|openshell|openclaw' || echo "no nemoclaw docker containers"
systemctl is-active ollama 2>/dev/null || echo "ollama not active"
```

State what you find in one short paragraph, then pick advice based on it. A user reporting an error on a half-installed system needs different help than one troubleshooting a running sandbox.

## Route to the right reference

Read only the file(s) you need — don't load all four by default.

- **Fresh install or re-onboarding** → `references/instructions.md`. It has the four-phase DGX Spark walkthrough (Docker/NVIDIA runtime → Ollama → `nemoclaw.sh` → sandbox verify → Telegram bridge → cleanup).
- **Something is broken** → `references/troubleshooting.md`. Symptom → cause → fix table, plus a diagnosis order of operations.
- **Need a specific command or flag** → `references/commands.md`. Consolidated CLI/env/port reference. Flags the commands that are NOT in the captured sources so you don't invent output.
- **Architecture / repo layout / "what is this project"** → `references/repo-overview.md`. Repo structure, state directories, where to file security issues.
- **User is running `ollama launch openclaw` / `clawdbot` / `moltbot`, or has the Ollama integration but no NemoClaw state** → `references/openclaw-ollama.md`. Covers the Ollama-integrated OpenClaw CLI (launch flags, messaging channels, `OLLAMA_API_KEY` implicit discovery, explicit provider config, model requirements). This is a **different product** from NemoClaw — no sandbox, no k3s, no `~/.nemoclaw/`.

## DGX Spark gotchas to surface proactively

These bite users repeatedly on DGX Spark specifically:

- **cgroup v2 + k3s.** DGX Spark uses cgroup v2; OpenShell's gateway needs `default-cgroupns-mode: host` in `/etc/docker/daemon.json`. Without it, the gateway fails with "Failed to start ContainerManager". The fix is in `references/instructions.md` Step 1, and `sudo nemoclaw setup-spark` applies it automatically on newer versions.
- **Unified Memory Architecture.** If the user reports memory pressure "even though I have plenty of RAM," flush the buffer cache: `sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'`. Don't recommend this pre-emptively — only when they describe symptoms.
- **aarch64 architecture.** Reject x86-only workarounds. Node.js 22.16+ and Docker arm64 images are the expected shape.
- **Ollama must run under systemd with `OLLAMA_HOST=0.0.0.0`.** `ollama serve &` does not pick up the override and the sandbox cannot reach the model. If the user says "inference times out," check this first.
- **Dashboard must be reached as `http://127.0.0.1:...`, not `localhost`.** The gateway's origin check requires the literal string match. "origin not allowed" in the browser = this.
- **"No GPU detected" during onboard is expected on DGX Spark GB10.** The wizard still works and uses Ollama.
- **Sandbox names must be lowercase alphanumeric with hyphens only.** Underscores fail.
- **NemoClaw ≠ NVIDIA NeMo ≠ NeMo-Guardrails.** Completely separate products. If a user mentions NeMo toolkit or Guardrails, confirm what they actually mean before routing them here.
- **OpenClaw (Ollama integration) ≠ NemoClaw.** `ollama launch openclaw` (aliases `clawdbot`, `moltbot`) launches an Ollama-integrated agent CLI that runs **on the host** with no sandbox. NemoClaw is a separate NVIDIA product that wraps OpenClaw inside an OpenShell sandbox with a k3s gateway and its own Telegram bridge. A DGX Spark can have either, both, or neither. If the survey shows Ollama's `openclaw` integration present but no `nemoclaw`/`openshell`/`~/.nemoclaw/`, route to `references/openclaw-ollama.md` and do NOT suggest NemoClaw install/onboard flows.

## Advising safely on a running setup

- **Never run destructive commands without explicit confirmation.** This includes `./uninstall.sh`, `openshell gateway destroy`, `nemoclaw <name> destroy` (if it exists), `docker rm`, and anything in `~/.nemoclaw/` state. Describe first, then wait for the user to say go.
- **Collect before you diagnose.** When a problem is unclear, prefer `nemoclaw status`, `nemoclaw <name> status`, `nemoclaw <name> logs --follow`, and `docker ps` over shotgun fixes. For deep issues, if the user has `nemoclaw debug` available in their version, suggest it — but note that command isn't confirmed in the references here, so tell the user it's worth trying but verify with `nemoclaw help`.
- **Don't invent commands.** `references/commands.md` flags which commands are confirmed vs. plausible-but-unverified. If a user asks about a command that isn't in that file, say so, and suggest `nemoclaw help` on their machine or the NVIDIA NemoClaw Developer Guide at docs.nvidia.com/nemoclaw/latest/.
- **Keep installs idempotent.** The `nemoclaw.sh` one-liner is safe to re-run if an install got wedged partway. The onboard wizard re-runs cleanly after fixing prerequisites.

## When the user says "fix it for me"

Work in this order:

1. Run the survey commands above, share findings.
2. Identify the step of the install/run that's broken using the diagnosis order in `references/troubleshooting.md`.
3. Quote the specific fix from the troubleshooting reference verbatim, and explain *why* it's the fix, not just what.
4. Ask before running any command that changes state outside the user's HOME (anything with `sudo`, `systemctl`, `docker rm`, `./uninstall.sh`, or edits to `/etc/`).
5. After the fix, re-run the survey commands to confirm the state changed as expected.

## When the user asks "what does NemoClaw do?"

Read `references/repo-overview.md`. Summarize in 2–3 sentences — don't dump the whole file. Then offer to walk them through install or point at a specific capability.

## Refreshing the local reference

If the user's install is on a newer NemoClaw version than these references describe, or they explicitly ask for the latest docs, offer to refresh by re-fetching:

- https://build.nvidia.com/spark/nemoclaw/instructions → `references/instructions.md`
- https://build.nvidia.com/spark/nemoclaw/troubleshooting → `references/troubleshooting.md`
- https://github.com/NVIDIA/NemoClaw → `references/repo-overview.md`
- https://docs.ollama.com/integrations/openclaw + https://ollama.com/blog/openclaw + https://ollama.com/blog/openclaw-tutorial + https://openclaw-ai.com/en/docs/providers/ollama/ → `references/openclaw-ollama.md`

Only do this refresh when asked, not at every invocation.
