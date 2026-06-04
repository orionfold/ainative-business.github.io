---
name: arena-lifecycle
description: Tear down and bring back the Orionfold Arena cockpit (the local FastAPI sidecar + baked web UI) on the NVIDIA DGX Spark, optionally alongside a visible CDP-attached Chromium for browser-use mode. Use this skill WHENEVER the user wants to restart, relaunch, recycle, stop, kill, bring up, or bring back the Arena cockpit / Arena app / Arena sidecar — phrasings like "restart the arena", "tear down the cockpit and start again", "bring the arena back up", "recycle the arena server", "kill the arena and relaunch with browser", "is the arena up?", or "reconnect to the arena in browser use mode". Also use right after editing anything under arena-app/ when the running cockpit needs to be recycled to pick up a fresh bundle, or when the cockpit/CDP looks dead (sidecar offline, port not responding). Handles sourcing .env.local so OpenRouter cloud lanes come up hot, polls health, and can launch/kill the visible Chromium on CDP :9222 for puppeteer/playwright connectOverCDP driving. Do NOT use for serving model lanes (that's spark-serve) or for building/baking the arena-app bundle (that's `fieldkit arena build`).
---

# Arena Lifecycle

Bring the Orionfold Arena cockpit up or down on the DGX Spark, reliably and the
same way every time. The cockpit is a local FastAPI sidecar (`fieldkit arena up`)
serving a pre-baked web UI on `:7866`; "browser-use mode" additionally runs a
visible snap Chromium with a CDP endpoint on `:9222` so you can drive/verify the
live app with `puppeteer-core` / `playwright-core` `connectOverCDP`.

All the fiddly, easy-to-get-wrong steps (which pids to kill, sourcing the env so
cloud lanes are hot, health polling, recreating the throwaway `/tmp` venv after a
reboot, launching Chromium on the right DISPLAY with the persistent profile) live
in **`scripts/arena_lifecycle.sh`**. Your job is to pick the verb + browser
option, run the script, and read back what it reports.

## The one command

```bash
.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh <verb> [--browser|--no-browser]
```

Run it **from the repo root** (`/home/nvidia/ainative-business.github.io`). The
script is path-independent, but the repo root is where `.env.local` and the venv
expect to resolve.

- **verbs**: `up` · `down` · `restart` · `status`
- **browser flag**: default is `--no-browser` (cockpit only). Add `--browser` to
  also launch (on `up`/`restart`) or kill (on `down`) the visible Chromium.

## Choosing the verb

- **restart** — the common case. Kills the cockpit, then brings it back with a
  freshly-sourced env. Use after an `arena-app/` rebuild or when the sidecar is
  wedged. Add `--browser` to also recycle the Chromium and leave it parked on
  `/arena/leaderboard/`, ready for a CDP attach.
- **up** — start whatever isn't already running (idempotent; it no-ops anything
  already healthy).
- **down** — stop the cockpit. Add `--browser` to also close the Chromium;
  without it, a running browser is left alone (cheap to keep around).
- **status** — read-only: are `:7866` and `:9222` answering, and which pids. If
  CDP is down but a plain Chromium is running, it flags the trap + the fix command.

> **Launching `--browser` from Claude Code's Bash tool is safe.** The script
> fully detaches the Chromium (`setsid --fork … </dev/null > log 2>&1`), so it
> survives the tool-call boundary (verified 2026-06-04 — the old "exit-144 reap,
> launch only from a Spark terminal" caveat is superseded). **Do NOT** hand-launch
> a plain `chromium` for CDP: with no `--remote-debugging-port` it exposes nothing,
> and a 2nd instance on the *default* profile just forwards the flag to the running
> window. Always use `up --browser` (it owns its own `/tmp/arena-chrome-profile`).

## Reading the result

The script prints a `✓`/`!`/`✗` line per step and ends with a status block.
Key things to confirm and relay to the user:

- **`cockpit up … (OpenRouter key loaded)`** — good. If you instead see
  **`OpenRouter key NOT in env`**, the cloud lanes will be cold; check that
  `.env.local` exists at the repo root and holds `OPENROUTER_API_KEY`.
- **`browser up on CDP :9222 (Chrome …)`** — browser-use mode is live; you can
  now `puppeteer.connect({browserURL:'http://127.0.0.1:9222'})`.
- A `✗` line is a hard failure and the script tails the relevant log
  (`/tmp/arena-cockpit.log` or `/tmp/arena-chromium.log`) — surface that.

## Browser-use mode (driving the live app)

After `--browser`, attach with `puppeteer-core` **run from the repo root** (the
module won't resolve under `/tmp`):

```js
import puppeteer from 'puppeteer-core';
const b = await puppeteer.connect({ browserURL: 'http://127.0.0.1:9222', defaultViewport: null });
const p = (await b.pages())[0];
await p.goto('http://127.0.0.1:7866/arena/leaderboard/', { waitUntil: 'load' });
```

**Always attach with `defaultViewport: null`** (as above) — and NEVER pass a
fixed `defaultViewport: {width, height}`. Puppeteer turns that into a CDP
`Emulation.setDeviceMetricsOverride` that pins the renderer to that CSS size and
**outlives your `disconnect()`** (it even survives a clear+reload). The user then
sees the app boxed in the old size with whitespace on the right/bottom + a
scrollbar when their window is actually maximized. If you need a specific size
for a deterministic screenshot, resize the *real* window instead:
`const {windowId} = await client.send('Browser.getWindowForTarget'); await
client.send('Browser.setWindowBounds', {windowId, bounds:{width, height}})` (or
`{windowState:'maximized'}`). **Recovery for an already-boxed window:**
`arena_lifecycle.sh restart --browser` (a fresh process has no override).

Screenshots go to `/tmp/aifn-smoke/` and should be cleaned up at end of turn.
Note: a click that triggers navigation can race `p.evaluate` ("execution context
destroyed") — prefer `p.goto` with human-spaced pauses when scripting a
multi-tab sweep.

## Gotchas the script already handles (so you don't relearn them)

- **Throwaway `/tmp` paths vanish on reboot.** `/tmp/arena-venv` and
  `/tmp/arena-chrome-profile` are gone after a Spark reboot. The script detects a
  missing venv and rebuilds it (`pip install -e ./fieldkit[arena]`, ~1 min); the
  Chromium profile is recreated automatically on launch.
- **Cold cloud lanes.** The cockpit only reaches OpenRouter if its *process env*
  carries the key — the script sources `.env.local` before launching and then
  verifies the key landed in `/proc/<pid>/environ`.
- **Rebuilding the bundle is a separate concern.** This skill does NOT bake the
  web UI. After editing `arena-app/`, run
  `fieldkit arena build --repo-root arena-app` **from the repo root** first, then
  `restart` here to serve it. (Running the build from elsewhere trips a
  cwd guard that complains it can't find `node_modules/astro`.)

## Overrides

Defaults match the Spark operator setup. Override via env if needed:
`ARENA_REPO_ROOT`, `ARENA_VENV`, `ARENA_COCKPIT_PORT`, `ARENA_CDP_PORT`,
`ARENA_CHROME_BIN`, `ARENA_CHROME_PROFILE`, `ARENA_DISPLAY`, `ARENA_ENV_FILE`.
