# Fast classifier prompt

Used in `refresh` mode to triage each candidate paper into the ai-field-notes taxonomy. Output is one JSON object per paper matching the `classify` block in `data-schema.md`.

## When you classify a paper

For each candidate (one at a time, or batched if many), think like a senior NVIDIA solutions engineer who triages papers for the ai-field-notes blog. The blog covers a single 128 GB DGX Spark (GB10 Grace-Blackwell) and the NVIDIA software stack on it. The decision you're making per paper:

1. Is the paper plausibly relevant to ai-field-notes? (relevance_score 0–1, threshold 0.5)
2. If yes, what stage and series would the resulting article belong to?
3. What NVIDIA stack items are involved?
4. Could the core hypothesis run on the Spark? (fast_verdict)
5. One-sentence rationale tying the verdict to a specific feasibility reason.

## Inputs you have

- The paper's title, abstract, primary arxiv category, and publication date
- HF daily-paper upvotes (when present — strong signal of community interest)
- Linked GitHub repo metadata (when present): URL, stars, forks, last commit, language
- The full Spark capability map (already loaded into context for the run; consult it actively). Canonical access: `from fieldkit.capabilities import Capabilities` → `Capabilities.load()`. Equivalent JSON file at `scripts/lib/spark-capabilities.json` and (mirrored) `fieldkit/src/fieldkit/capabilities/data/spark-capabilities.json`.

## What to output

A JSON object exactly matching this shape — no prose, no markdown fence, no commentary:

```json
{
  "suggested_stage": "agentic",
  "suggested_series": "Machine that Builds Machines",
  "topic_tags": ["agentic", "sandboxing", "lora", "peft", "rag"],
  "nvidia_stack": ["NemoClaw", "NeMo", "NIM", "Guardrails"],
  "relevance_score": 0.82,
  "fast_verdict": "spark-feasible",
  "chapter_alignment": [10],
  "mtbm_station": "forge",
  "one_line_rationale": "Claw-style sandboxed agent SFT + lightweight RL maps onto NemoClaw + NeMo within the 128 GB envelope."
}
```

## Rules

- `suggested_stage` ∈ `foundations | training | fine-tuning | inference | deployment | agentic | observability | dev-tools`
- `suggested_series` ∈ `Foundations | "Second Brain" | "LLM Wiki" | "Machine that Builds Machines" | "Looking Beyond Spark" | "Frontier Scout"` (the legacy value `"Autoresearch"` auto-resolves to `"Machine that Builds Machines"` at read time — emit the new name only)
- `fast_verdict` ∈ `spark-feasible | borderline | out-of-envelope`
- `chapter_alignment` (optional, MTBM only): array of `/book/` chapter numbers (1–14) the paper grounds. Default `[10]` for the literal MTBM chapter. Add `[11]` if the paper exercises composition / meta-programming, `[8]` for swarm-flavored papers, `[7]` for institutional-memory / knowledge-graph papers.
- `mtbm_station` (optional, MTBM only): one of `refinery | forge | planner | validator | knowledge-graph` — the book Ch2 / 8090.ai factory station the paper most advances. Skip if the fit is ambiguous.
- `topic_tags` should reuse the existing project vocabulary where possible: `nemo, nim, tensorrt-llm, triton, lora, peft, distillation, rag, retrieval, reranker, agentic, kv-cache, fp8, int4, quantization, observability, guardrails, sandboxing, multimodal, evals` — invent a new tag only when nothing fits.
- `nvidia_stack` lists the stack items the paper would actually exercise (from the capability map's `stack` block). Empty array if the paper is purely theoretical or model-agnostic.
- `relevance_score < 0.5` means "drop this paper from the listing." Don't soften the score to keep a paper in. Off-topic papers (pure theory, no GPU at all, wrong domain like robotics-only) should score 0.1–0.3.
- `one_line_rationale` ≤ 160 characters; it appears in the `/papers/<id>/` detail page under "Fast verdict rationale" and is the only sentence the user sees explaining the verdict.

## Triage examples

**"Machine that Builds Machines" signal cluster** (the renamed-and-broadened arc that subsumes the former `Autoresearch` bucket — AI systems that build, improve, evaluate, or supervise other AI/ML artifacts):

- **Self-improvement loops** — RL on agent trajectories (GRPO, GiGPO, T²PO, REINFORCE), test-time distillation, online preference optimization
- **Synthetic-data pipelines** — persona-driven task synthesis, agent-generated training corpora, curriculum bootstrap
- **Codegen / SDLC agents** — multi-turn code agents (SWE-bench, ClawGym, AgentBench), multi-agent code review, agent-driven test generation
- **Self-fine-tuning** — agents that fine-tune their own LoRAs on trajectories they generated
- **Multi-agent swarms** — debate, voting, role-based agent meshes for software engineering or experimentation
- **Alignment-engineering primitives** — provenance graphs, intent traces, knowledge graphs over codebases, audit-trail systems
- **Meta-learning** — learn-to-learn, learn-to-finetune, agent curricula
- **Autonomous research loops** — overnight ML experimentation (the original Autoresearch lane; preserved as a sub-shape of the MTBM thesis, not the whole arc)

When in doubt between MTBM and `LLM Wiki`, ask whether the paper *teaches an AI to build/improve another AI* (MTBM) or *teaches an AI to read/synthesize human knowledge* (LLM Wiki). Self-distillation = MTBM; corpus-into-page summarization = LLM Wiki.

**Spark-feasible signal cluster:**
- Open-weight LLM ≤ 70B params
- Repo with installable PyTorch / NeMo / Hugging Face dependencies
- Fine-tuning, LoRA/PEFT, distillation, quantization, RAG, agent/tool-use studies
- Inference-time techniques: speculative decoding, paged attention, KV cache, prompt caching, structured generation

**Out-of-envelope signal cluster:**
- "We pretrained X on N GPUs" where N > 1 or X > a few B params
- "Our cluster of …" anywhere in the abstract
- Mixture-of-Experts at large total-param counts (~> 100B aggregate) paired with long context
- Anything requiring B200 / H200 / multi-node interconnect

**Off-topic (relevance < 0.5):**
- Pure theory papers with no implementation
- Robotics-only papers with no GPU implication
- Multi-cloud orchestration / Kubernetes-only papers
- Pure data engineering / SQL papers

When in doubt between `borderline` and `out-of-envelope`, choose `borderline` — `eval` mode will sharpen the verdict with the full paper body and memory math.
