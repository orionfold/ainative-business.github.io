---
name: spark-serve
description: Bring up, switch, inspect, or tear down a single local model serving lane on NVIDIA DGX Spark using NIM, llama.cpp, vLLM, or Ollama within the 128 GB memory envelope.
---

# Codex bridge: spark-serve

Read `.claude/skills/spark-serve/SKILL.md` and follow it as the authoritative Spark serving runbook.

- Enforce one resident serving lane at a time.
- Prove memory headroom before starting a lane.
- Tear down cleanly and verify the port/process state when done.
- Keep Codex-specific notes in `CODEX-CC.md`; leave `.claude/` unchanged.
