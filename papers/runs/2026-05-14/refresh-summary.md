# Frontier Scout refresh — 2026-05-14

Run from Spark CC session 8 (parallel to a 36 GB HF push for `Orionfold/Saul-7B-Instruct-v1-GGUF`). Source streams: HuggingFace daily-papers (last 30 days, 50 candidates), arXiv recent listings (60 candidates). Dedupe by arxiv_id, prefer HF entries. Candidate cap: top 25 by HF upvotes for in-context classification.

## Top dive-deep candidates

1. **[MinT (2605.13779)](../../2605.13779/paper.md)** · 137 HF upvotes · `mtbm` · `spark-feasible` · relevance 0.92 — Managed infra for LoRA post-training + online serving of many policies over few base deployments. Architectural sibling to the `fieldkit.publish` + `g3_build_first_quant.sh` flow this repo is actively shipping.
2. **[HAGE (2605.09942)](../../2605.09942/paper.md)** · 10 HF upvotes · `second-brain` · `spark-feasible` · relevance 0.88 — RL-driven weighted graph evolution for agentic memory. Replaces flat vector search + fixed binary relational graphs with query-dependent graph weights. Direct fit for the Second-Brain arc on the Spark.
3. **[Useful Memories Become Faulty (2605.12978)](../../2605.12978/paper.md)** · 16 HF upvotes · `second-brain` · `spark-feasible` · relevance 0.85 — Counter-narrative to consolidation-based agentic memory: episodic traces stay reliable; consolidated abstractions drift over rewrites. A publishable "what NOT to do" piece.
4. **[Retrieval is Cheap, Show Me the Code (2605.12975)](../../2605.12975/paper.md)** · 7 HF upvotes · `llm-wiki` · `spark-feasible` · relevance 0.83 — Executable multi-hop reasoning for RAG. Code-generation in the retrieval loop. Maps to `fieldkit.rag` composition.
5. **[Covering Human Action Space for CUAs (2605.12501)](../../2605.12501/paper.md)** · 13 HF upvotes · `mtbm` · `spark-feasible` · relevance 0.80 — Computer-use agents via data synthesis + benchmark. Adjacent to ClawGym / clawnav work; agentic + benchmark.

## What's new (relevance ≥ 0.5)

| Arxiv ID    | Series        | Verdict          | Stage       | Title (truncated) |
|-------------|---------------|------------------|-------------|-------------------|
| 2605.13779  | mtbm          | spark-feasible   | fine-tuning | MinT: Managed Infrastructure for Training and Serving Millions of LLMs |
| 2605.09942  | second-brain  | spark-feasible   | agentic     | HAGE: Harnessing Agentic Memory via RL-Driven Weighted Graph Evolution |
| 2605.12978  | second-brain  | spark-feasible   | agentic     | Useful Memories Become Faulty When Continuously Updated by LLMs |
| 2605.12975  | llm-wiki      | spark-feasible   | inference   | Retrieval is Cheap, Show Me the Code: Executable Multi-Hop Reasoning for RAG |
| 2605.12501  | mtbm          | spark-feasible   | agentic     | Covering Human Action Space for Computer Use: Data Synthesis + Benchmark |
| 2605.13511  | foundations   | borderline       | foundations | Many-Shot CoT-ICL: Making In-Context Learning Truly Learn |
| 2605.12004  | mtbm          | borderline       | training    | Learning Agentic Policy from Action Guidance |
| 2605.11136  | mtbm          | borderline       | agentic     | EVOCHAMBER: Test-Time Co-evolution of Multi-Agent System |
| 2605.12825  | looking-beyond| borderline       | inference   | Orthrus: Memory-Efficient Parallel Token Generation via Dual-View Diffusion |
| 2605.12411  | mtbm          | spark-feasible   | agentic     | Predicting Decisions of AI Agents from Limited Interaction |
| 2605.12913  | mtbm          | spark-feasible   | agentic     | Revisiting DAgger in the Era of LLM-Agents |
| 2605.08518  | mtbm          | spark-feasible   | observability | CODS 2025 AssetOpsBench Challenge Retrospective |
| 2605.13775  | mtbm          | borderline       | training    | RoboEvolve: Co-Evolving Planner-Simulator for Robotic Manipulation |

## What was dropped (relevance < 0.5)

Image / video / voice / robot-tele-op papers off the Spark text/code mainline. Examples:

- 2605.13724 (AnyFlow video diffusion) — modality mismatch
- 2605.13565 (Qwen-Image-VAE-2.0) — image generation
- 2605.13062 (Edit-Compass) — image editing bench
- 2605.13724, 2605.12587, 2605.11550 — video / 3D / world-action
- 2605.13841 (EVA-Bench voice agents) — speech modality
- 2605.13757 (FrameSkip VLA) — robot tele-op

## Stats

- **New papers classified this run:** 13 (after relevance≥0.5 filter)
- **New papers dropped (off-mainline):** ~12 (of top 25)
- **Existing index entries preserved:** 19 (no classification changes — carried forward)
- **Total in papers.json:** 32 papers
- **Verdict mix (new):** 8 spark-feasible · 5 borderline · 0 out-of-envelope-but-relevant
- **Series mix (new):** 7 mtbm · 2 second-brain · 1 llm-wiki · 2 foundations · 1 looking-beyond

## Spark-side context for this run

The refresh ran while a 36 GB HF push (`Orionfold/Saul-7B-Instruct-v1-GGUF`) was uploading sequentially via the new `hf_push_resilient.py` (lesson from earlier crash today). Both ran cleanly side-by-side on the Spark — the scout is fetch-and-classify-only with no GPU dependency.

## Next steps

User picks a paper from the top 5; CC invokes:

```bash
# Deep evaluate the pick:
/frontier-scout eval 2605.13779   # → papers/2605.13779/eval.md
# Or promote to an article scaffold (only after eval):
/frontier-scout promote 2605.13779
```

> Generated by `frontier-scout refresh` on 2026-05-14.
