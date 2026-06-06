---
name: dashboard
description: Use when the operator wants to SEE the Arena cockpit dashboard —
  triggers on "/dashboard", "open the dashboard", "show me the cockpit",
  "pull up the dashboard". Launches the local Arena cockpit sidecar on :7866
  (if not already up) and opens it in the browser on the Spark's display.
  Read-only — do NOT use this skill to log or edit data, dispatch jobs, or
  drive the cockpit over CDP. For restart/teardown/browser-use(CDP) mode or a
  wedged sidecar, that's arena-lifecycle; for serving model lanes, spark-serve.
---

# /dashboard — Arena cockpit (local-only, operator-triggered)

Adopted 2026-06-06 from the relayed [`_SPECS/dashboard-skill-v1.md`](../../../_SPECS/dashboard-skill-v1.md).
For this repo the "dashboard" is the **Orionfold Arena cockpit**
(`_SPECS/spark-arena-v1.md`): the FastAPI sidecar serving the baked web UI on
`:7866`. This skill is the thin *"show me it"* wrapper; the heavy lifecycle
(restart, teardown, CDP browser-use mode, venv rebuild) stays with the
**arena-lifecycle** skill, whose script this one reuses for the launch.

## Launch policy: operator-triggered only

Spawn only when the operator asks (this skill triggering IS the ask).
Never auto-start from hooks, session start, or background jobs — the
SessionStart auto-launch experiment was rolled back 2026-06-06. If a tab
is already open, opening one more is fine — simplicity beats dedup.

## Launch

```bash
curl -fs --max-time 1 http://127.0.0.1:7866/healthz >/dev/null \
  || .claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh up
{ DISPLAY="${ARENA_DISPLAY:-:1}" nohup xdg-open http://127.0.0.1:7866/arena/leaderboard/ \
  >/tmp/spark-dashboard-open.log 2>&1 </dev/null & disown; }
```

Run from the repo root (`/home/nvidia/ainative-business.github.io`) — the
lifecycle script resolves `.env.local` + the `/tmp/arena-venv` from there.
Report the URL (`http://127.0.0.1:7866/arena/leaderboard/`; LAN
`http://10.0.0.209:7866/…` if the operator is on another machine). Note any
degraded panels the lifecycle script flags (e.g. `OpenRouter key NOT in env`
⇒ cloud lanes cold).

Why this shape (per the spec, adapted to this repo's own code):

- **Health check hits `/healthz`**, not `/` — the sidecar 404s at root
  (pages live under `/arena/`), so the skeleton's bare `/` probe would lie.
- **Start command is `arena_lifecycle.sh up`**, not a raw server line — it is
  this repo's proven launcher: idempotent, sources `.env.local` so cloud lanes
  come up hot, rebuilds the reboot-ephemeral `/tmp/arena-venv`, health-polls,
  and **already detaches the sidecar with the §4-equivalent form**
  (`setsid --fork … </dev/null`, log `/tmp/arena-cockpit.log`). The script
  itself runs in the foreground and exits when health passes — that's the
  ✓-report, not a held pipe.
- **The browser-open step uses the §4 detached form verbatim** — `xdg-open`'s
  spawned browser child would otherwise hold stdout/stderr and hang the tool
  call. `DISPLAY` defaults to `:1` (the Spark's visible session). If the box
  is headless/remote (no display), skip the open line and just print the URL.

## Guardrails

- **Loopback bind only**; refuse non-loopback hosts.
- **Local-only**: the cockpit serves the operator on this machine; it is not
  a published surface (nothing under `public/`/`src/` — GitHub Pages must
  not pick it up; `arena-app/` bakes separately).
- **Read-only renderer** in this skill's scope: open and look. Dispatching
  jobs, arming lanes, editing settings, or driving over CDP are other
  skills'/sessions' jobs.
- **Graceful degradation**: missing/unparseable source → "no data — <reason>",
  never a crash, never a fabricated zero (design-system §5.7).
- **Dependency-light**: everything above is already in the repo — no new deps.
