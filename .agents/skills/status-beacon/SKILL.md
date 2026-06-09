---
name: status-beacon
description: Maintain `_STATUS.json`, the Agency cockpit status beacon. Use at session end with HANDOFF updates or when the user asks to refresh the beacon, update status, or force a beacon SEO refresh.
---

# Codex bridge: status-beacon

Use `.claude/skills/status-beacon/SKILL.md` as the source workflow and adapt only the operator-facing wording to Codex.

- Keep `_STATUS.json` short, factual, and compatible with the contract in `CLAUDE.md`.
- Run the existing script when appropriate: `node .claude/skills/status-beacon/scripts/update_beacon.mjs`.
- Do not bump expensive GSC/GA4 metric dates unless a real check happened.
- Log any Codex-side workflow change in `CODEX-CC.md`.
