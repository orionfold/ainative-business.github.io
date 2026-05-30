---
arxiv_id: 2605.06614
title: "SkillOS: Learning Skill Curation for Self-Evolving Agents"
published: 2026-05-06
primary_category: cs.AI
hf_upvotes: 6
popularity_score: 15
suggested_stage: agentic
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.85
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: skill-os-on-spark
chapter_alignment: [10]
mtbm_station: forge
abs_url: https://arxiv.org/abs/2605.06614
pdf_url: https://arxiv.org/pdf/2605.06614
hf_paper_url: https://huggingface.co/papers/2605.06614
---

# SkillOS: Learning Skill Curation for Self-Evolving Agents

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** agentic · **Relevance:** 0.85 · **Popularity:** 15/100

> RL-trained skill curator over an external SkillRepo with frozen executor — clean self-evolving-agent shape that fits sub-70B on a Spark.

## Abstract

LLM-based agents are increasingly deployed to handle streaming tasks, yet they often remain one-off problem solvers that fail to learn from past interactions. Reusable skills distilled from experience provide a natural substrate for self-evolution, where high-quality skill curation serves as the key bottleneck. Existing approaches either rely on manual skill curation, prescribe heuristic skill operations, or train for short-horizon skill operations. However, they still struggle to learn complex long-term curation policies from indirect and delayed feedback. To tackle this challenge, we propose SkillOS, an experience-driven RL training recipe for learning skill curation in self-evolving agents. SkillOS pairs a frozen agent executor that retrieves and applies skills with a trainable skill curator that updates an external SkillRepo from accumulated experience. To provide learning signals for curation, we design composite rewards and train on grouped task streams based on skill-relevant task dependencies, where earlier trajectories update the SkillRepo, and later related tasks evaluate these updates. Across multi-turn agentic tasks and single-turn reasoning tasks, SkillOS consistently outperforms memory-free and strong memory-based baselines in both effectiveness and efficiency, with the learned skill curator generalizing across different executor backbones and task domains. Further analyses show that the learned curator produces more targeted skill use, while the skills in SkillRepo evolve into more richly structured Markdown files that encode higher-level meta-skills over time.

## Why this matters for ai-field-notes

- **Topic tags:** agentic, reinforcement-learning, self-improvement, skills
- **NVIDIA stack:** NemoClaw, NeMo
- **Chapter alignment:** Ch10
- **MTBM station:** forge
- **Fast verdict rationale:** RL-trained skill curator over an external SkillRepo with frozen executor — clean self-evolving-agent shape that fits sub-70B on a Spark.

## Repos

_No public repo yet._

## Citations

_not yet indexed_

## Links

- [arXiv abstract](https://arxiv.org/abs/2605.06614)
- [PDF](https://arxiv.org/pdf/2605.06614)
- [HuggingFace daily papers](https://huggingface.co/papers/2605.06614)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-08)

## Promoted

This paper has been promoted to `articles/skill-os-on-spark/` (status: upcoming).
