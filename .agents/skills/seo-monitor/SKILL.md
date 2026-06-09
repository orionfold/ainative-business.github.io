---
name: seo-monitor
description: Audit and monitor ainative.business SEO health using GSC, GA4, PageSpeed, and local site checks; write `seo-progress.md` and per-run `seo/YYYY-MM-DD-HHMM.md` snapshots.
---

# Codex bridge: seo-monitor

Use `.claude/skills/seo-monitor/SKILL.md` and its referenced playbooks for the monitoring workflow.

- Treat browser-authenticated GSC/GA4 data as operator-private.
- Make code-level SEO fixes only after surfacing the proposed fix set.
- Do not use this for cheap `_STATUS.json` beacon refreshes; use `status-beacon`.
- Keep generated SEO reports in the existing repo locations.
