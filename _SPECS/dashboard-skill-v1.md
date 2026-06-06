# /dashboard skill — operator-triggered local dashboard launch (shared pattern)

_Status: relayed 2026-06-06 via PR from the operator's agency cockpit. Pattern is live in self-health and agency (both `.claude/skills/dashboard/SKILL.md`); this doc is the implementation instruction for adopting it here. Companion: [`design-system-v1.md`](design-system-v1.md) for the visual layer._

## 1. What it is

A Claude Code skill that launches this repo's local dashboard **only when the
operator asks** ("/dashboard", "open the dashboard", "show me the cockpit").
The skill owns: a port check, a detached server launch, and opening the
browser. Nothing else — no tab dedup, no multi-instance checks, no
browser-automation tools.

For this repo the "dashboard" is the **Arena cockpit** (`spark-arena-v1.md`)
— the skill wraps launching whatever serves it locally; it does not build a
new surface.

## 2. Why operator-triggered (the rollback record)

Both self-health and agency tried a **SessionStart-hook auto-launch** (server
start + AppleScript Chrome tab-dedup) and **rolled it back the same day,
2026-06-06** — operator: "not working as I expected … keep it simple this
time." Lessons, so this repo skips the dead end:

- Auto-launch stacked complexity (hooks, AppleScript, macOS Automation
  consent, detached-launch traps) for a marginal win over just asking.
- Hooks + browser opening are timing-fragile and platform-specific.
- Duplicate tabs are harmless; duplicate *servers* on one port self-prevent
  (bind fails). Dedup only where collision actually breaks something.

**Policy: never auto-start the dashboard from hooks, session start, or
background jobs.** The skill triggering on an operator ask IS the launch gate.

## 3. SKILL.md skeleton

Create `.claude/skills/dashboard/SKILL.md`:

```markdown
---
name: dashboard
description: Use when the operator wants to SEE the <project> dashboard —
  triggers on "/dashboard", "open the dashboard", "show me the cockpit".
  Launches the local dashboard server on :<PORT> and opens it in the browser.
  Read-only — do NOT use this skill to log or edit data.
---

# /dashboard — <project> (local-only, operator-triggered)

## Launch policy: operator-triggered only
Spawn only when the operator asks (this skill triggering IS the ask).
Never auto-start from hooks, session start, or background jobs — the
SessionStart auto-launch experiment was rolled back 2026-06-06. If a tab
is already open, opening one more is fine — simplicity beats dedup.

## Launch
curl -s -o /dev/null --max-time 1 http://127.0.0.1:<PORT>/ \
  && <OPEN_CMD> http://127.0.0.1:<PORT>/ \
  || { nohup <START_COMMAND> \
       >/tmp/<project>-dashboard.log 2>&1 </dev/null & disown; }

Report the URL. Note any degraded panels.
```

Fill `<PORT>` / `<START_COMMAND>` **from this repo's own code** (do not guess
— venv/uvicorn/node setups differ; for Arena, use whatever `_GUIDES/
local-ai-stack-commands.md` already records as the serve command). `<OPEN_CMD>`
is `open` on macOS, `xdg-open` on Linux (DGX) — or skip the open step and just
print the URL if the box is headless/remote.

## 4. The detached-launch form (load-bearing — keep exactly)

```
{ nohup <cmd> >/tmp/<log> 2>&1 </dev/null & disown; }
```

Three production hangs (self-wealth, self-health, agency — 2026-06-06) taught
this shape. The harness running a tool call waits on **pipe EOF, not process
exit**: any spawned descendant still holding stdout/stderr/stdin keeps the
call (or hook) hanging until timeout. Hence:

- **No subshell** — `( cmd & )` leaves the forked subshell in `wait4()`
  holding the pipe; script-level background jobs are not waited on.
- **All three stdio fds detached** — `</dev/null` is the one people forget.
- **Log to a file, not /dev/null** — silent launches are undiagnosable.
- Verify: the detached child's PPID should be 1, and a piped invocation of
  the launch line should return in well under a second.

## 5. Guardrails (same posture as the peers)

- **Loopback bind only**; refuse non-loopback hosts.
- **Local-only**: the dashboard serves the operator on this machine; it is
  not a published surface (nothing under `public/`/`src/` — GitHub Pages
  must not pick it up).
- **Read-only renderer**: the dashboard renders what sessions/skills already
  wrote; it does not mutate records.
- **Graceful degradation**: missing/unparseable source → "no data — <reason>",
  never a crash, never a fabricated zero (design system §5.7).
- **Dependency-light**: prefer what the repo already runs; no new heavyweight
  deps just for the skill.

## 6. Adoption checklist

- [ ] `.claude/skills/dashboard/SKILL.md` exists with the launch-policy
      section verbatim (the rollback record is the point).
- [ ] Port + start command confirmed from this repo's own code.
- [ ] Launch line uses the §4 detached form; piped test returns <1s; child
      PPID = 1.
- [ ] No SessionStart hook (or any hook) starts the dashboard.
- [ ] New operator-facing panes follow `design-system-v1.md` §3 tokens
      (suggested spark accent, from the §2.1 palette: orange
      `#F7653B` / ink `#D74D26` / soft `#FEE2D5` — distinct from
      self-health teal, self-wealth blue, agency purple).
