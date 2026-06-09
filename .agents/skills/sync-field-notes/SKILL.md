---
name: sync-field-notes
description: Sync field-notes articles, evidence, screenshots, signature SVGs, fieldkit docs, and related UX changes from the ai-field-notes source repo into this website.
---

# Codex bridge: sync-field-notes

Use `.claude/skills/sync-field-notes/SKILL.md` as the source sync workflow.

- Sync from committed/pushed source state, not an uncommitted live working tree.
- Preserve the destination website's content collection and rendering contracts.
- Verify with the documented Astro build and rendering verifiers.
- Do not modify `.claude/skills/sync-field-notes/` unless explicitly asked.
