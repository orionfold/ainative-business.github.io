---
arxiv_id: 2605.06200
title: "A^2TGPO: Agentic Turn-Group Policy Optimization with Adaptive Turn-level Clipping"
published: 2026-05-06
hf_upvotes: 7
popularity_score: 16
suggested_stage: fine-tuning
suggested_series: "Machine that Builds Machines"
fast_verdict: spark-feasible
relevance_score: 0.85
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: a2tgpo-turn-clipping-on-spark
chapter_alignment: [10]
mtbm_station: forge
hf_paper_url: https://huggingface.co/papers/2605.06200
---

# A^2TGPO: Agentic Turn-Group Policy Optimization with Adaptive Turn-level Clipping

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** fine-tuning · **Relevance:** 0.85 · **Popularity:** 16/100

> Turn-level adaptive clipping fixes credit-assignment in agentic GRPO without external process reward models — directly applicable on a Spark.

## Abstract

Reinforcement learning for agentic large language models (LLMs) typically relies on a sparse, trajectory-level outcome reward, making it difficult to evaluate the contribution of individual tool-calls within multi-turn interactions. Existing approaches to such process credit assignment either depend on separate external process reward models that introduce additional consumption, or tree-based structural rollout that merely redistributes the outcome signal while constraining trajectory diversity. A promising alternative leverages the per-turn change in the policy's predicted probability of the ground-truth, termed Information Gain (IG), as an intrinsic process signal without an external evaluator. However, prior work on leveraging IG signals within the RL training loop faces three systematic challenges: normalizing across turns that face heterogeneous positional contexts can distort the relative standing of individual turns, accumulating a variable number of terms causes advantage magnitudes to drift with trajectory depth, and a fixed clipping range governs policy updates identically for turns with vastly different IG signals. In this paper, we propose A^2TGPO (Agentic Turn-Group Policy Optimization with Adaptive Turn-level Clipping), which retains IG as the intrinsic signal but re-designs how it is normalized, accumulated, and consumed: (i) turn-group normalization: normalizes IG within each (prompt, turn-index) group so that each turn is compared only against peers at the same interaction depth; (ii) variance-rescaled discounted accumulation: divides cumulative normalized IG by square root of accumulated terms to keep advantage magnitudes comparable across turn positions; and (iii) adaptive turn-level clipping: modulates each turn's clipping range based on its normalized IG, widening the update region for informative turns and narrowing it for uninformative ones.

## Why this matters for ai-field-notes

- **Topic tags:** reinforcement-learning, grpo, agentic, credit-assignment
- **NVIDIA stack:** NeMo
- **Chapter alignment:** Ch10
- **MTBM station:** forge
- **Fast verdict rationale:** Turn-level adaptive clipping fixes credit-assignment in agentic GRPO without external process reward models — directly applicable on a Spark.

## Repos

_No public repo yet._

## Citations

`citations: 0`

## Links

- [HuggingFace daily papers](https://huggingface.co/papers/2605.06200)

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-08)

## Promoted

This paper has been promoted to `articles/a2tgpo-turn-clipping-on-spark/` (status: upcoming).
