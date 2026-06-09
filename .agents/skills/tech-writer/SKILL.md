---
name: tech-writer
description: Turn a DGX Spark setup, exploration, or build session into a published deep-dive essay under `articles/<slug>/`. Use for "write this up", draft, polish, capture, publish, or blog-quality DGX Spark writeups.
---

# Codex bridge: tech-writer

Use `.claude/skills/tech-writer/SKILL.md` as the editorial workflow, with these Codex boundaries:

- Read the Claude skill and its referenced guides before writing publishable prose.
- Preserve the public-blog privacy scrub requirements.
- Prefer repo-local files and scripts; do not call Claude/Anthropic SDKs.
- Place resulting article work under `articles/<slug>/` unless the user asks for product content.
- Record any Codex-specific workflow change in `CODEX-CC.md`.
