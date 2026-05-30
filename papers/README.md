# Frontier Scout — paper triage

_Last refresh: 2026-05-14 · 32 papers tracked · [run history](runs/index.md)_

## Recommended dive-deep candidates

These are the papers most worth running through `/frontier-scout eval <id>` next, ranked by combined relevance × popularity × verdict-feasibility. Updated 2026-05-14:

1. **[MinT: Managed Infrastructure for Training and Serving Millions of LLMs](2605.13779/paper.md)** · 137 upv · spark-feasible · Machine that Builds Machines  
   _LoRA serving + training infra for many policies over few base deployments — architectural sibling to fieldkit.publish + g3_build_first_quant; direct MTBM Pick #1 fit._
2. **[HAGE: Harnessing Agentic Memory via RL-Driven Weighted Graph Evolution](2605.09942/paper.md)** · 10 upv · spark-feasible · Second Brain  
   _RL-driven weighted graph evolution for agentic memory; replaces flat vector search + fixed binary relational graphs with query-dependent graph weights._
3. **[Useful Memories Become Faulty When Continuously Updated by LLMs](2605.12978/paper.md)** · 16 upv · spark-feasible · Second Brain  
   _Counter-narrative: episodic traces stay reliable while consolidated abstractions drift over rewrites — publishable "what NOT to do" piece on agentic memory._
4. **[Retrieval is Cheap, Show Me the Code: Executable Multi-Hop Reasoning for RAG](2605.12975/paper.md)** · 7 upv · spark-feasible · LLM Wiki  
   _Executable multi-hop reasoning for RAG. Code-generation in the retrieval loop — maps to fieldkit.rag composition._
5. **[Covering Human Action Space for Computer Use](2605.12501/paper.md)** · 13 upv · spark-feasible · Machine that Builds Machines  
   _Computer-use agents via data synthesis + benchmark. Adjacent to ClawGym / clawnav work; agentic + benchmark in one paper._

### Carried over from prior refresh (still strong picks)

- **[OpenSearch-VL: An Open Recipe for Frontier Multimodal Search Agents](2605.05185/paper.md)** · 87 upv · spark-feasible · MTBM
- **[Skill1: Unified Evolution of Skill-Augmented Agents via RL](2605.06130/paper.md)** · 45 upv · spark-feasible · MTBM
- **[MiA-Signature: Approximating Global Activation for Long-Context Understanding](2605.06416/paper.md)** · 36 upv · spark-feasible · LLM Wiki

## What's new this run

See [runs/2026-05-14/refresh-summary.md](runs/2026-05-14/refresh-summary.md) for 13 new entries, ~12 dropped (off-mainline image/video/voice/robot), top-5 picks rationale, and stats.

## Full listing

### Second Brain (1)

#### spark-feasible (1)
- [2605.05242 Beyond Semantic Similarity: Rethinking Retrieval for Agentic Search via Direct Corpus Interaction](2605.05242/paper.md) · 15 · _Agents searching the raw corpus directly via general operators (lexical, conjunctive, multi-step) instead of fixed top-k retrieval — Second Brain extension._ · [eval](2605.05242/eval.md)

### LLM Wiki (6)

#### spark-feasible (6)
- [2604.24927 Large Language Models Explore by Latent Distilling](2604.24927/paper.md) · 29 · _Lightweight test-time distiller plus reweighted sampling on existing open-weight reasoning models fits comfortably within Spark's 128 GB inference envelope._ · [eval](2604.24927/eval.md) · → `articles/test-time-distilling-for-exploration/`
- [2605.06416 MiA-Signature: Approximating Global Activation for Long-Context Understanding](2605.06416/paper.md) · 28 · _Compressed activation-signature conditioning approximates global context for long-context LLMs — drop-in inference technique that exercises KV economics._
- [2605.04523 RaguTeam at SemEval-2026 Task 8: Meno and Friends in a Judge-Orchestrated LLM Ensemble for Faithful Multi-Turn Response Generation](2605.04523/paper.md) · 28 · _Judge-orchestrated 7-LLM ensemble for multi-turn RAG (SemEval-2026 T8 winner) — every member except gpt-oss-120b fits a single Spark._ · [eval](2605.04523/eval.md)
- [2604.27393 MiniCPM-o 4.5: Towards Real-Time Full-Duplex Omni-Modal Interaction](2604.27393/paper.md) · 27 · _Open small omni-modal model with full-duplex streaming inference — sub-10B, fits 128 GB envelope and surfaces real-time inference techniques._
- [2605.02910 CreativityBench: Evaluating Agent Creative Reasoning via Affordance-Based Tool Repurposing](2605.02910/paper.md) · 23 · _CreativityBench — affordance-grounded creativity benchmark with 14K tasks evaluating 10 LLMs; eval-pipeline-on-Spark territory._
- [2605.05662 XL-SafetyBench: A Country-Grounded Cross-Cultural Benchmark for LLM Safety and Cultural Sensitivity](2605.05662/paper.md) · 11 · _XL-SafetyBench — 5,500 country-grounded safety + cultural-sensitivity test cases evaluating LLMs; runs as a judge-pipeline against any Spark-resident model._

### Machine that Builds Machines (12)

#### spark-feasible (12)
- [2605.05185 OpenSearch-VL: An Open Recipe for Frontier Multimodal Search Agents](2605.05185/paper.md) · 49 · _Open recipe for multimodal deep-search agents trained with agentic RL — SFT + RL on a single-Spark-sized policy fits the MTBM forge._
- [2604.27351 Heterogeneous Scientific Foundation Model Collaboration](2604.27351/paper.md) · 38 · _Lightweight LLM-orchestrator over domain foundation models is software glue that fits NemoClaw/NIM; underlying scientific FMs would be hosted as endpoints._ · [eval](2604.27351/eval.md) · → `articles/scientific-foundation-models-as-tools/`
- [2605.06130 Skill1: Unified Evolution of Skill-Augmented Agents via Reinforcement Learning](2605.06130/paper.md) · 30 · _Single policy co-evolving skill selection + utilization + distillation from one task-outcome reward — clean MTBM forge case at sub-70B._
- [2604.26904 ClawGym: A Scalable Framework for Building Effective Claw Agents](2604.26904/paper.md) · 27 · _Claw-style sandboxed agent SFT + lightweight RL on per-task sandboxes maps directly onto NemoClaw + NeMo fine-tuning within the 128 GB envelope._ · [eval](2604.26904/eval.md) · → `articles/clawgym-on-spark/`
- [2604.25256 AutoResearchBench: Benchmarking AI Agents on Complex Scientific Literature Discovery](2604.25256/paper.md) · 24 · _Agent-driven literature discovery benchmark fits Machine that Builds Machines arc; runnable on Spark via NemoClaw + NIM + NeMo Retriever with pgvector, no training needed._ · [eval](2604.25256/eval.md) · → `articles/autoresearchbench-on-spark/`
- [2604.28139 Claw-Eval-Live: A Live Agent Benchmark for Evolving Real-World Workflows](2604.28139/paper.md) · 23 · _Live agent benchmark with execution traces and graders maps cleanly onto NemoClaw/OpenClaw sandboxed agents on Spark for local workflow eval._ · [eval](2604.28139/eval.md) · → `articles/claw-eval-live-on-spark/`
- [2605.05566 Nonsense Helps: Prompt Space Perturbation Broadens Reasoning Exploration](2605.05566/paper.md) · 23 · _LoPE breaks the GRPO zero-advantage trap with prompt-space perturbations — a one-line tweak applicable to any sub-70B GRPO loop on the Spark._
- [2605.02178 T^2PO: Uncertainty-Guided Exploration Control for Stable Multi-Turn Agentic Reinforcement Learning](2605.02178/paper.md) · 21 · _Uncertainty-guided exploration for multi-turn agentic RL — direct sequel to the GRPO-on-ClawGym arc._ · [eval](2605.02178/eval.md) · → `articles/t2po-uncertainty-guided-rl-on-spark/`
- [2605.05724 Auto Research with Specialist Agents Develops Effective and Non-Trivial Training Recipes](2605.05724/paper.md) · 18 · _Closed empirical-loop auto-research with specialist agents and lineage feedback — the literal MTBM picture, fully autonomous over 1,197 trials._ · [eval](2605.05724/eval.md)
- [2605.06200 A^2TGPO: Agentic Turn-Group Policy Optimization with Adaptive Turn-level Clipping](2605.06200/paper.md) · 16 · _Turn-level adaptive clipping fixes credit-assignment in agentic GRPO without external process reward models — directly applicable on a Spark._ · [eval](2605.06200/eval.md)
- [2605.06614 SkillOS: Learning Skill Curation for Self-Evolving Agents](2605.06614/paper.md) · 15 · _RL-trained skill curator over an external SkillRepo with frozen executor — clean self-evolving-agent shape that fits sub-70B on a Spark._ · [eval](2605.06614/eval.md)
- [2605.06651 AI Co-Mathematician: Accelerating Mathematicians with Agentic AI](2605.06651/paper.md) · 11 · _Stateful asynchronous AI co-mathematician workbench — agentic framework around an LLM, runs as inference + tools on a single Spark._

## Stats

| Metric | Value |
|--------|------:|
| Total tracked | 19 |
| Classified this run | 13 |
| Papers with deep eval | 11 |
| spark-feasible | 19 |
| borderline | 0 |
| out-of-envelope | 0 |

## Run history

[Append-only refresh log →](runs/index.md)
