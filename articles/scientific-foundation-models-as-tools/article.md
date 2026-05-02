---
title: 'Heterogeneous Scientific Foundation Model Collaboration — Spark reproduction notes'
date: 2026-05-02
author: 'Manav Sehgal'
product: 'NemoClaw'
stage: agentic
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: [agentic, tool-use, foundation-models, multimodal, nemoclaw, nim, triton, guardrails]
summary: 'Wrap a domain foundation model (Pangu-Weather) as a Triton tool, drive it from a NIM-served Llama 3.1 8B planner via NemoClaw, and show when specialist routing beats language-only reasoning — all inside the Spark 128 GB envelope.'
status: upcoming
series: 'Autoresearch'
---

## Source paper

- arXiv: [2604.27351](https://arxiv.org/abs/2604.27351) — Heterogeneous Scientific Foundation Model Collaboration
- Repo: _(none at promotion time — paper introduces "Eywa" framework but no code released)_
- Popularity: **41/100** · 181 HF upvotes · 0 citations

## Frontier Scout verdict

**spark-feasible** — every component fits comfortably in the 128 GB envelope (8B planner + ≤3 specialists + Guardrails ≤ 50 GB), and the agent shell maps directly onto NemoClaw's existing tool-routing protocol; the only friction is reconstructing the framework from the paper's prose since code isn't out yet.

## Proposed Spark recipe

1. **Pick a concrete domain** for the first walkthrough — weather forecasting via Pangu-Weather (~3B) is the cleanest demo because input/output is tensor-on-disk rather than tokens.
2. **Serve the planner LLM via NIM**: `llama-3.1-8b-instruct` container exposes the OpenAI-compatible chat endpoint already documented in `nim-first-inference-dgx-spark`. `NIM_GPU_MEM_FRACTION=0.4` to reserve room for the specialist.
3. **Serve the specialist FM via Triton** with a Python backend wrapping the model's native inference (`trtllm-and-triton-on-spark` shows the pattern). Expose it as `predict_weather(state_tensor) -> forecast_tensor`.
4. **Build the EywaAgent loop inside NemoClaw** as a custom skill: planner receives a question, decides whether to call the specialist, marshals the structured inputs, gets back a tensor, and renders a natural-language summary.
5. **Add NeMo Guardrails** at the planner boundary so off-domain prompts route to a refusal rather than calling the specialist with garbage inputs.
6. **Measure two things**: planner-only vs Eywa accuracy on a held-out domain question set (paper claims improvement on structured-data tasks), and end-to-end latency budget.

Full recipe with stack-map references in [`evidence/spark-recipe.md`](./evidence/spark-recipe.md).

## Open questions for the experiment

- No public repo — Eywa framework must be reimplemented from the paper's prose. ~200–400 lines of Python expected.
- Specific scientific FMs the paper evaluates aren't enumerated — pick Pangu-Weather (or ESM-2 for proteins) as the canonical specialist and call out the deviation.
- No accuracy numbers in the abstract to anchor the "is orchestration helping" claim until the full paper or a code release arrives.

## Suggested article shape

- **Stage:** agentic
- **Series:** Autoresearch
- **Tags:** agentic, tool-use, foundation-models, multimodal, nemoclaw, nim, triton, guardrails
- **Voice:** essay on *when language-only reasoning hits a structural wall* and what specialist routing buys you. Tie back to the Autoresearch arc — Eywa is one pattern for an autoresearch agent that reaches beyond text.
