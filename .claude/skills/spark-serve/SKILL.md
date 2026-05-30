---
name: spark-serve
description: "Bring up a single local model serving lane on an NVIDIA DGX Spark (NIM, llama.cpp, vLLM, or Ollama) inside the 128 GB unified-memory envelope, one lane at a time, and tear it down cleanly. Trigger when the user wants to serve / host / run a model locally on the Spark, switch serving lanes, or free the box after serving."
version: 1.0.0
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [dgx-spark, serving, nim, llama-cpp, vllm, ollama, local-first, unified-memory]
    related_skills: [vertical-route]
  agentskills:
    homepage: https://ainative.business/field-notes/hermes-drives-the-spark-via-fieldkit-mcp/
    origin: ai-field-notes / fieldkit.harness
---

# spark-serve — one local serving lane on a DGX Spark

Bring up exactly one model serving lane on a DGX Spark, prove it is inside the
128 GB unified-memory envelope before you start it, and tear it down so the box
returns to idle. The Spark shares CPU and GPU memory, so the cardinal rule is
**one lane at a time** — stacking a second model (or pairing a MoE with a long
context) can hard-hang the machine.

## When to use

- "serve / host / run `<model>` locally on the Spark"
- "switch from the NIM lane to a llama.cpp GGUF lane"
- "is there room to serve `<model>`?"
- "free the box" / "stop the model" after a serving session

## The lanes

| Lane | Best for | Notes |
|---|---|---|
| **NIM** | Nemotron + validated tool-calling | ships the correct chat template + engine config; warm ~145 s; set `NIM_MAX_BATCH_SIZE=32` for Nemotron-Nano-9B |
| **llama.cpp** | GGUF quants, MoE | fastest single-stream tok/s on the Spark; `--reasoning-format none` for R1-distill models |
| **vLLM** | FP8 dense/MoE | needs `--enable-auto-tool-choice --tool-call-parser hermes` for tool calls; sweep orphaned EngineCore PIDs on teardown |
| **Ollama** | quick local pulls | convenient; not the throughput leader |

## Procedure

1. **Size first, start second.** Estimate the weight + KV footprint and compare
   against `MemAvailable`. Refuse (don't "try it and see") if the lane would
   leave less than ~8 GB headroom. A 9B at fp16 is ~16 GB weights; a 30B-A3B MoE
   Q4 GGUF is ~20 GB; a 70B fp8 is ~70 GB — all single-lane-only.
2. **Confirm the box is idle.** No other model resident (`free -h`; check for a
   stray `llama-server`, `vllm`, or NIM container). Stop anything first.
3. **Start the lane** and wait for warm — poll the health/`/v1/models`
   endpoint, do not trust a fixed sleep.
4. **Verify it bound the right model.** Read the load log (`general.name` for a
   GGUF) before trusting `/health` — a stale server on the same port will answer
   for the *wrong* model.
5. **Tear down on exit.** Stop the container/process; for vLLM also sweep
   orphaned `EngineCore` PIDs (they hold ~100 GB and survive `pkill`). Verify
   `free -h` returns to baseline.

## Guardrails

- One lane at a time. Never stack. This is the difference between "fast local
  inference" and "the box is hung and needs a power cycle."
- `MemAvailable` from `/proc/meminfo`, not `free`'s "free" column — buff/cache is
  reclaimable.
- Slow local serving: give the harness a long stream read timeout (e.g. 1800 s)
  so a cold first token doesn't look like a hang.

This skill is the operational distillation of the `fieldkit.harness` serving
lanes (`serve_lane(spec, guard=True)`); see the ai-field-notes "Hermes serving
lane" deep-dive for the measured bakeoff behind the table above.
