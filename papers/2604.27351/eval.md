> **FIELDKIT FIT (2026-05-02):** retro-annotation; eval predates the v0.1 template.
> - **Would import:** `fieldkit.nim` (the planner-side 8B chat client + `wait_for_warm` for the ~90s NIM cold start); `fieldkit.capabilities` (joint envelope math for 8B planner + ≤3 specialist FMs + KV).
> - **Would extend:** nothing in v0.1.
> - **Would propose for v0.x:** `fieldkit.agents` — planner-and-tool-call routing primitives over NemoClaw, the canonical orchestration shape this paper needs (v0.2). `fieldkit.guardrails` — boundary-check policies at the planner edge so off-domain prompts route to refusal rather than calling specialists with garbage inputs (v0.2).

# Heterogeneous Scientific Foundation Model Collaboration

## Hypothesis

Eywa wraps domain-specific scientific foundation models (e.g. weather, protein, materials, genomics predictors) behind a language-model reasoning interface so a planner LLM can drive them as tools. Three deployment shapes are proposed: a single-agent drop-in (EywaAgent), a replacement for one role inside an existing multi-agent system (EywaMAS), and a planner-coordinated orchestra mixing standard agents with Eywa-wrapped specialists (EywaOrchestra). The win comes from *not* re-encoding structured non-language data through a language interface — specialist FMs handle their native modality and the LLM only does plan-and-route reasoning.

## Memory budget

The paper does not name specific model sizes for either the planner LLM or the wrapped scientific FMs, so the budget is shape-driven rather than line-by-line. The natural Spark configuration:

- **Planner LLM**: Llama 3.1 8B Instruct via NIM — 16 GB bf16 weights, ~24.8 tok/s measured, fits with room.
- **Specialist FMs**: typically 0.1–3B in scientific domains (AlphaFold-class, ClimaX-class, MatterGPT-class). At 3B bf16 = 6 GB each. Even three concurrently loaded specialists (~18 GB) leave headroom.
- **KV cache** for the planner at 8192 ctx, batch=1, Llama-class (n_layers=32, hidden=4096, bf16): `2 × 4096 × 2 × 32 × 8192 × 1 / 1e9 ≈ 4.3 GB`.

Total in the comfortable case: 16 (planner) + 18 (3 specialists) + 4.3 (KV) ≈ 38 GB. Well inside the 128 GB envelope, with ~90 GB for OS, Triton overhead, and a second concurrent specialist.

## Proposed Spark recipe

1. **Pick a concrete domain** for the first walkthrough — weather forecasting via Pangu-Weather (~3B) is the cleanest demo because input/output is tensor-on-disk rather than tokens.
2. **Serve the planner LLM via NIM**: `llama-3.1-8b-instruct` container exposes the OpenAI-compatible chat endpoint already documented in `nim-first-inference-dgx-spark`. `NIM_GPU_MEM_FRACTION=0.4` to reserve room for the specialist.
3. **Serve the specialist FM via Triton** with a Python backend wrapping the model's native inference (`trtllm-and-triton-on-spark` shows the pattern). Expose it as `predict_weather(state_tensor) -> forecast_tensor`.
4. **Build the EywaAgent loop inside NemoClaw** as a custom skill: planner receives a question, decides whether to call the specialist, marshals the structured inputs, gets back a tensor, and renders a natural-language summary. NemoClaw's tool-call protocol (verified in `nemoclaw-vs-openclaw-dgx-spark` and `autoresearch-agent-loop`) handles the routing.
5. **Add NeMo Guardrails** at the planner boundary so off-domain prompts route to a refusal rather than calling the specialist with garbage inputs (`guardrails-on-spark`).
6. **Measure two things**: planner-only vs Eywa accuracy on a held-out domain question set (paper claims improvement on structured-data tasks), and end-to-end latency budget (planner tok/s × tokens-per-step + specialist forward-pass time).

## Blockers

- No public repo at eval time — paper says "Eywa, a heterogeneous agentic framework" but there is no released code under the names searched. Article would have to reproduce the agent shell from the paper's description rather than clone it.
- Specific scientific FMs the paper evaluates are not enumerated in the abstract — the article would pick its own canonical specialist (Pangu-Weather, ESM-2, etc.) and adapt the framework, which is fine but worth flagging as a deviation from the paper's exact setup.
- No accuracy numbers in the abstract to anchor an "is the orchestration actually helping" claim until the full paper or repo arrives.

## Verdict

**spark-feasible** — every component fits comfortably in the 128 GB envelope (8B planner + ≤3 specialists + Guardrails ≤ 50 GB), and the agent shell maps directly onto NemoClaw's existing tool-routing protocol; the only friction is reconstructing the framework from the paper's prose since code isn't out yet.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** scientific-foundation-models-as-tools
- **Suggested stage:** agentic
- **Suggested series:** Autoresearch
- **Suggested tags:** agentic, tool-use, foundation-models, multimodal, nemoclaw, nim, triton, guardrails
- **Suggested summary:** Wrap a domain foundation model (Pangu-Weather) as a Triton tool, drive it from a NIM-served Llama 3.1 8B planner via NemoClaw, and show when specialist routing beats language-only reasoning — all inside the Spark's 128 GB envelope.
