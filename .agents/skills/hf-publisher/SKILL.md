---
name: hf-publisher
description: Prepare, validate, and publish Hugging Face datasets, model cards, GGUFs, LoRAs, or related artifacts.
---

# Codex bridge: hf-publisher

Read `.claude/skills/hf-publisher/SKILL.md` before publishing Hugging Face artifacts.

- Verify license, README/card metadata, and artifact integrity before any push.
- Keep tokens in environment or `.env.local`; never commit credentials.
- Use explicit user approval before network publishing if the command requires it.
