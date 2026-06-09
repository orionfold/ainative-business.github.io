---
name: vertical-route
description: Route patent, legal, finance, cyber, or medical domain requests to the right local Orionfold GGUF expert on the Spark, escalating to a frontier model only when local confidence is low.
---

# Codex bridge: vertical-route

Read `.claude/skills/vertical-route/SKILL.md` for the current routing table and serve/release loop.

- Classify deterministically before loading a model.
- Serve only the selected expert; do not fan out multiple local lanes.
- Use `spark-serve` for the actual serving mechanics.
- Be explicit when a frontier escalation is an inference rather than a local-model result.
