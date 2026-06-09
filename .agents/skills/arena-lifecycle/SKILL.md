---
name: arena-lifecycle
description: Restart, relaunch, stop, status-check, or bring up the Orionfold Arena cockpit/sidecar on the DGX Spark, optionally with visible CDP Chromium browser-use mode. Use after arena-app edits or when the cockpit/CDP is stale.
---

# Codex bridge: arena-lifecycle

Use the established workflow in `.claude/skills/arena-lifecycle/SKILL.md`, but execute it as Codex:

- Read the Claude skill file first for current runbook details.
- Do not edit `.claude/` scripts or instructions unless the user explicitly asks for Claude-side changes.
- Prefer the existing command shape: `.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh <up|down|restart|status> [--browser|--no-browser]`.
- After `arena-app/` edits, rebake with the documented `fieldkit arena build --repo-root arena-app` flow before restarting the cockpit.
- Report the sidecar URL `http://127.0.0.1:7866/` and CDP port `9222` when browser mode is active.

## Codex Sandbox Notes

- Localhost browser-use checks can be blocked inside Codex's sandbox. If `puppeteer.connect({ browserURL: "http://127.0.0.1:9222" })` fails with `EPERM`, rerun the read-only CDP attach with `sandbox_permissions: "require_escalated"`.
- `arena_lifecycle.sh status --browser` may falsely report `:7866` / `:9222` down from inside the sandbox even when the cockpit and CDP browser are reachable. Recheck status with escalation before concluding the live browser is gone.
- Starting `arena_lifecycle.sh up --browser` may need escalation when `/tmp/arena-venv` has to be rebuilt and pip must download build dependencies. Use the same lifecycle command with escalation rather than hand-launching Chromium.
- For screenshots, keep `defaultViewport: null` and use the operator-resized real browser window. Do not set a fixed viewport; it can leave the visible browser boxed after disconnect.
