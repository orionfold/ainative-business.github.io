---
name: vertical-route
description: "Route a user request to the right Orionfold domain-expert GGUF on an NVIDIA DGX Spark (patent / legal / finance / cyber / medical), serving one expert at a time within the unified-memory envelope, and escalate to a frontier model only when local confidence is low. Trigger when the user asks a domain question that a specialist local model would answer better, or wants to set up / explain local expert routing on the Spark."
version: 1.0.0
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [dgx-spark, routing, gguf, domain-expert, local-first, orionfold]
    related_skills: [spark-serve]
  agentskills:
    homepage: https://ainative.business/field-notes/hermes-drives-the-spark-via-fieldkit-mcp/
    origin: ai-field-notes / fieldkit.harness
---

# vertical-route — one box, five local experts

Pick the right local domain-expert model for a request and serve it, instead of
sending every question to one generalist. The Spark holds a library of
specialist GGUFs; only one is resident at a time, so routing is a
**classify → serve the chosen expert → answer → release** loop, not a
load-everything fan-out.

## The experts (Orionfold GGUFs)

| Domain | Model | Route when the request is about… |
|---|---|---|
| patent | `Orionfold/patent-strategist-v3-nemo-GGUF` | claims, prior art, prosecution strategy, MPEP |
| legal | `Orionfold/Saul-7B-Instruct-v1-GGUF` | contracts, statutes, case reasoning |
| finance | `Orionfold/finance-chat-GGUF` | filings, markets, accounting, valuation |
| cyber | `Orionfold/SecurityLLM-GGUF` | threats, CVEs, detection, defensive security |
| medical | `Orionfold/II-Medical-8B-GGUF` | clinical reasoning, terminology, guidelines |

## Routing

1. **Classify the request** with a deterministic predicate first — keyword sets
   per domain, not a runtime LLM classifier. Tie-break toward the most specific
   domain; if nothing matches, stay on the generalist lane.
2. **Serve the chosen expert** via `spark-serve` (one lane at a time). If the
   currently-resident expert already matches, reuse it — don't reload.
3. **Answer** through the served model.
4. **Escalate only on low confidence.** If the local expert hedges or the
   question needs reasoning beyond its size, escalate to a frontier model
   (e.g. via OpenRouter) — and say you did. Local-first is the default; the
   escalation is the exception, and it's the only step that costs money.

## Guardrails

- One expert resident at a time (the Spark unified-memory rule — see
  `spark-serve`). Switching domains = teardown + bring-up, not co-residence.
- Reasoning experts (R1-distill shapes like patent-strategist) need a generous
  generation budget or the `<think>` block truncates before the answer; serve
  with `--reasoning-format none` so the answer text comes back in `content`.
- Routing is deterministic and auditable: log which expert handled each request.

This skill is the operational face of `fieldkit.harness.build_vertical_router`
over the five published Orionfold verticals; see the ai-field-notes Harnesses
series for the measured router behind it.
