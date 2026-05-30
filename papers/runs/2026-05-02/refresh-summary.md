---
date: 2026-05-02
total_papers: 21
new_this_run: 0
dropped_low_relevance: 9
classified_this_run: 0
note: migration from src/data/papers.json
---

# Refresh — 2026-05-02

_This run is the one-shot migration from the legacy `src/data/papers.json` location to `papers/`. No new fetching was performed; existing entries were carried over verbatim._

## Recommended dive-deep candidates

1. **[Heterogeneous Scientific Foundation Model Collaboration](../../2604.27351/paper.md)** · 181 upv · spark-feasible — _Lightweight LLM-orchestrator over domain foundation models is software glue that fits NemoClaw/NIM; underlying scientific FMs would be hosted as endpoints._
2. **[ClawGym: A Scalable Framework for Building Effective Claw Agents](../../2604.26904/paper.md)** · 44 upv · spark-feasible — _Claw-style sandboxed agent SFT + lightweight RL on per-task sandboxes maps directly onto NemoClaw + NeMo fine-tuning within the 128 GB envelope._
3. **[Large Language Models Explore by Latent Distilling](../../2604.24927/paper.md)** · 59 upv · spark-feasible — _Lightweight test-time distiller plus reweighted sampling on existing open-weight reasoning models fits comfortably within Spark's 128 GB inference envelope._
4. **[AutoResearchBench: Benchmarking AI Agents on Complex Scientific Literature Discovery](../../2604.25256/paper.md)** · 27 upv · spark-feasible — _Agent-driven literature discovery benchmark fits Autoresearch arc; runnable on Spark via NemoClaw + NIM + NeMo Retriever with pgvector, no training needed._
5. **[Claw-Eval-Live: A Live Agent Benchmark for Evolving Real-World Workflows](../../2604.28139/paper.md)** · 22 upv · spark-feasible — _Live agent benchmark with execution traces and graders maps cleanly onto NemoClaw/OpenClaw sandboxed agents on Spark for local workflow eval._

## Carried-over papers (21)

| arXiv | Title | Series | Verdict | Score |
|-------|-------|--------|---------|------:|
| [2604.27351](../../2604.27351/paper.md) | Heterogeneous Scientific Foundation Model Collaboration | Autoresearch | spark-feasible | 41 |
| [2604.26752](../../2604.26752/paper.md) | GLM-5V-Turbo: Toward a Native Foundation Model for Multimoda | Autoresearch | borderline | 35 |
| [2604.24927](../../2604.24927/paper.md) | Large Language Models Explore by Latent Distilling | LLM Wiki | spark-feasible | 31 |
| [2604.26904](../../2604.26904/paper.md) | ClawGym: A Scalable Framework for Building Effective Claw Ag | Autoresearch | spark-feasible | 30 |
| [2604.26951](../../2604.26951/paper.md) | Turning the TIDE: Cross-Architecture Distillation for Diffus | Frontier Scout | borderline | 29 |
| [2604.27083](../../2604.27083/paper.md) | Co-Evolving Policy Distillation | Frontier Scout | borderline | 28 |
| [2604.25256](../../2604.25256/paper.md) | AutoResearchBench: Benchmarking AI Agents on Complex Scienti | Autoresearch | spark-feasible | 26 |
| [2604.27085](../../2604.27085/paper.md) | Efficient Training on Multiple Consumer GPUs with RoundPipe | Looking Beyond Spark | borderline | 26 |
| [2604.28139](../../2604.28139/paper.md) | Claw-Eval-Live: A Live Agent Benchmark for Evolving Real-Wor | Autoresearch | spark-feasible | 25 |
| [2604.27505](../../2604.27505/paper.md) | Leveraging Verifier-Based Reinforcement Learning in Image Ed | Frontier Scout | borderline | 23 |
| [2604.27039](../../2604.27039/paper.md) | Length Value Model: Scalable Value Pretraining for Token-Lev | LLM Wiki | spark-feasible | 22 |
| [2604.28158](../../2604.28158/paper.md) | Intern-Atlas: A Methodological Evolution Graph as Research I | Autoresearch | spark-feasible | 21 |
| [2604.25719](../../2604.25719/paper.md) | Step-Audio-R1.5 Technical Report | Frontier Scout | borderline | 20 |
| [2604.24954](../../2604.24954/paper.md) | Nemotron 3 Nano Omni: Efficient and Open Multimodal Intellig | Foundations | spark-feasible | 20 |
| [2604.27419](../../2604.27419/paper.md) | InteractWeb-Bench: Can Multimodal Agent Escape Blind Executi | Autoresearch | spark-feasible | 18 |
| [2604.28181](../../2604.28181/paper.md) | Synthetic Computers at Scale for Long-Horizon Productivity S | Autoresearch | spark-feasible | 18 |
| [2604.27151](../../2604.27151/paper.md) | Step-level Optimization for Efficient Computer-use Agents | Autoresearch | spark-feasible | 17 |
| [2604.25135](../../2604.25135/paper.md) | FAMA: Failure-Aware Meta-Agentic Framework for Open-Source L | Autoresearch | spark-feasible | 17 |
| [2604.24658](../../2604.24658/paper.md) | The Last Human-Written Paper: Agent-Native Research Artifact | Autoresearch | spark-feasible | 16 |
| [2604.26779](../../2604.26779/paper.md) | Accelerating RL Post-Training Rollouts via System-Integrated | LLM Wiki | spark-feasible | 15 |
| [2604.27251](../../2604.27251/paper.md) | Compliance versus Sensibility: On the Reasoning Controllabil | LLM Wiki | spark-feasible | 14 |

## Verdict distribution

- spark-feasible: 15
- borderline: 6

## Series distribution

- Autoresearch: 11
- LLM Wiki: 4
- Frontier Scout: 4
- Looking Beyond Spark: 1
- Foundations: 1

## Stage distribution

- agentic: 11
- inference: 4
- fine-tuning: 4
- training: 2
