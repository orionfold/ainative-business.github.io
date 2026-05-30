# Data shape — papers/ folder layout

Frontier Scout writes a top-level `papers/` folder of human-readable markdown plus a `papers.json` sidecar. Everything is browsable on GitHub directly — no Astro, no build step.

## Authority rules (load-bearing)

- **`papers/papers.json` is canonical** for triage data. Frontmatter in `paper.md` mirrors a subset for human grep + readability; if the two diverge, JSON wins.
- **Regenerated each refresh:** `papers/papers.json`, `papers/<id>/paper.md`, `papers/runs/<date>/refresh-summary.md`, `papers/README.md`. Do not hand-edit these — your changes will be overwritten.
- **Append-only:** `papers/runs/index.md`. Each refresh adds one line at the bottom.
- **Immutable once written:** `papers/<id>/eval.md`, `papers/<id>/retrospective.md`. `eval` mode refuses to overwrite. To revise a verdict, use `annotate` mode.

## Folder layout

```
papers/
├── README.md                      ← derived index — leads with "Recommended dive-deep candidates"
├── papers.json                    ← canonical machine-readable triage store
├── runs/
│   ├── index.md                   ← append-only run log
│   └── <YYYY-MM-DD>/
│       └── refresh-summary.md     ← per-day summary; overwrites on same-day re-runs
└── <arxiv-id>/
    ├── paper.md                   ← per-paper card (regenerated each refresh)
    ├── eval.md                    ← optional deep eval (immutable once written)
    └── retrospective.md           ← optional annotate-mode retrospective
```

## papers/papers.json

```json
{
  "generated_at": "2026-05-01T22:18:00.000Z",
  "config": {
    "hf_days": 30,
    "arxiv_limit": 60,
    "relevance_threshold": 0.5
  },
  "counts": {
    "total": 21,
    "classified_this_run": 16,
    "dropped_low_relevance": 9
  },
  "papers": [
    {
      "arxiv_id": "2604.26904",
      "title": "ClawGym: A Scalable Framework for Building Effective Claw Agents",
      "authors": ["Alice X.", "Bob Y."],
      "abstract": "...",
      "published": "2026-04-28T20:00:00.000Z",
      "primary_category": "cs.AI",
      "abs_url": "https://arxiv.org/abs/2604.26904",
      "pdf_url": "https://arxiv.org/pdf/2604.26904",

      "hf_upvotes": 43,
      "hf_paper_url": "https://huggingface.co/papers/2604.26904",
      "citations": 0,

      "repos": [
        {
          "url": "https://github.com/ClawGym/ClawGym",
          "stars": 142,
          "forks": 18,
          "last_commit": "2026-04-30T11:00:00Z",
          "language": "Python",
          "framework": "PyTorch",
          "is_official": true,
          "framework_hint": "Python"
        }
      ],
      "has_code": true,

      "classify": {
        "suggested_stage": "agentic",
        "suggested_series": "Machine that Builds Machines",
        "topic_tags": ["agentic", "sandboxing", "fine-tuning", "lora", "peft", "rag"],
        "nvidia_stack": ["NemoClaw", "NeMo", "NIM", "Guardrails"],
        "relevance_score": 0.82,
        "fast_verdict": "spark-feasible",
        "chapter_alignment": [10],
        "mtbm_station": "forge",
        "one_line_rationale": "Claw-style sandboxed agent SFT + lightweight RL maps onto NemoClaw + NeMo within the 128 GB envelope."
      },
      "popularity_score": 29,

      "deep_eval": {
        "path": "papers/2604.26904/eval.md",
        "evaluated_at": "2026-05-02T10:30:00.000Z",
        "verdict": "spark-feasible"
      },
      "promoted_to": {
        "article_slug": "clawgym-on-spark",
        "status": "upcoming"
      }
    }
  ]
}
```

### Field semantics

- `arxiv_id` is the primary key. Form `YYMM.NNNNN`, no `vN` suffix.
- `classify.suggested_series` ∈ `Foundations | Second Brain | LLM Wiki | Machine that Builds Machines | Looking Beyond Spark | Frontier Scout`. **Legacy alias:** entries with `"Autoresearch"` (pre-2026-05-08) auto-resolve to `"Machine that Builds Machines"` at read time; the next refresh writes the new name in place. Do not emit `"Autoresearch"` from the classifier.
- `classify.suggested_stage` ∈ `foundations | training | fine-tuning | inference | deployment | agentic | observability | dev-tools`.
- `classify.fast_verdict` ∈ `spark-feasible | borderline | out-of-envelope`.
- `classify.chapter_alignment` (optional, MTBM only): integer array of `/book/` chapter numbers 1–14 the paper grounds (e.g., `[10]` for "The Machine That Builds Machines," `[10, 11]` if it also exercises meta-programming). Empty / absent for non-MTBM papers.
- `classify.mtbm_station` (optional, MTBM only): one of `refinery | forge | planner | validator | knowledge-graph` — the book Ch2 / 8090.ai factory station the paper advances. Skip when ambiguous.
- `popularity_score` is an integer 0–100. Computed as: `round(100 * clamp01((0.5 * upvotes_norm + 0.3 * stars_norm + 0.2 * citations_norm) * recency_decay))` where each `_norm = log10(value+1) / log10(K)` (K = 500 for upvotes, 20000 for stars, 2000 for citations) and `recency_decay = exp(-age_days / 90)`.
- `deep_eval.path` is always `papers/<arxiv-id>/eval.md` when present.
- `deep_eval` and `promoted_to` are `null` until the user runs `eval` and `promote` respectively. Preserve them across refreshes.

## papers/<arxiv-id>/paper.md

Light frontmatter (human-grep mirror, not source of truth) + body. Regenerated each refresh.

```markdown
---
arxiv_id: 2604.26904
title: "ClawGym: A Scalable Framework for Building Effective Claw Agents"
published: 2026-04-28
primary_category: cs.AI
hf_upvotes: 43
popularity_score: 29
suggested_stage: agentic
suggested_series: Machine that Builds Machines
fast_verdict: spark-feasible
relevance_score: 0.82
has_deep_eval: true
deep_verdict: spark-feasible
promoted_to: clawgym-on-spark
abs_url: https://arxiv.org/abs/2604.26904
pdf_url: https://arxiv.org/pdf/2604.26904
hf_paper_url: https://huggingface.co/papers/2604.26904
---

# ClawGym: A Scalable Framework for Building Effective Claw Agents

**Verdict:** spark-feasible · **Series:** Machine that Builds Machines · **Stage:** agentic · **Relevance:** 0.82 · **Popularity:** 29/100

> Claw-style sandboxed agent SFT + lightweight RL maps onto NemoClaw + NeMo within the 128 GB envelope.

## Abstract

{full abstract verbatim}

## Why this matters for ai-field-notes

- **Topic tags:** agentic, sandboxing, fine-tuning, lora, peft, rag
- **NVIDIA stack:** NemoClaw, NeMo, NIM, Guardrails
- **Fast verdict rationale:** {classify.one_line_rationale}

## Repos

| Repo | Stars | Forks | Last commit | Language |
|------|------:|------:|-------------|----------|
| [ClawGym/ClawGym](https://github.com/ClawGym/ClawGym) | 142 | 18 | 2026-04-30 | Python |

(or `_No public repo yet._` if `repos` is empty)

## Citations

`citations: 0` (or `not yet indexed` if null)

## Links

- [arXiv abstract]({abs_url})
- [PDF]({pdf_url})
- [HuggingFace daily papers]({hf_paper_url})

## Deep eval

[Full feasibility eval →](./eval.md) (verdict: **spark-feasible**, evaluated 2026-05-02)

(omit the section entirely if `has_deep_eval: false`)

## Promoted

This paper has been promoted to `articles/clawgym-on-spark/` (status: upcoming).

(omit if `promoted_to: null`)
```

## papers/<arxiv-id>/eval.md

The deep feasibility eval. Template lives in `references/feasibility-prompt.md`. Section ordering is load-bearing — `papers-promote` extracts sections by exact heading.

```markdown
# {Paper title}

## Hypothesis
One paragraph, plain prose.

## Memory budget
Show the params × bytes + KV cache arithmetic. Reference the 128 GB envelope.

## Proposed Spark recipe
Concrete sequenced steps using NIM / NeMo / TRT-LLM / etc.

## Blockers
Bulleted list of what would prevent reproduction.

## Verdict
**spark-feasible** — one-sentence justification.

## Article suggestion
- **Would write?** yes
- **Suggested slug:** kebab-case-slug
- **Suggested stage:** agentic
- **Suggested series:** Machine that Builds Machines
- **Suggested tags:** agentic, sandboxing, lora
- **Suggested summary:** ≤300 chars summary that becomes the article frontmatter.
```

The `## Verdict` section's first non-empty line must start with `**<verdict>**` so the verdict can be parsed back into `papers.json` deterministically.

## papers/runs/<YYYY-MM-DD>/refresh-summary.md

Per-day summary. Overwritten if refresh is re-run on the same day.

```markdown
---
date: 2026-05-01
total_papers: 21
new_this_run: 16
dropped_low_relevance: 9
classified_this_run: 25
---

# Refresh — 2026-05-01

## Recommended dive-deep candidates

1. **[Heterogeneous Scientific FM Collaboration](../../2604.27351/paper.md)** · 181 upv · spark-feasible — _Lightweight LLM-orchestrator over domain FMs maps onto NemoClaw + NIM._
2. **[Nemotron 3 Nano Omni](../../2604.24954/paper.md)** · 12 upv · spark-feasible — _Native NVIDIA 30B-A3B MoE with FP4 weights ships ready for the Spark._
3. ...

## New papers this run (16)

| arXiv | Title | Series | Verdict | Score |
|-------|-------|--------|---------|------:|
| 2604.27351 | Heterogeneous Scientific FM Collaboration | Machine that Builds Machines | spark-feasible | 41 |
| ... | ... | ... | ... | ... |

## Dropped under relevance threshold (9)

- 2604.28185 (0.35) — _Conceptual taxonomy survey, no reproducible technique._
- 2604.26067 (0.30) — _Open-vocab SLAM, robotics-only._
- ...

## Verdict distribution

- spark-feasible: 15
- borderline: 6

## Series distribution

- Machine that Builds Machines: 11
- LLM Wiki: 4
- Frontier Scout: 4
- Looking Beyond Spark: 1
- Foundations: 1
```

## papers/runs/index.md

Append-only audit trail across all runs. One line per refresh. Cheap, never overwrites.

```markdown
# Frontier Scout — refresh log

| Run | Added | Dropped | Total | Top picks |
|-----|------:|--------:|------:|-----------|
| [2026-05-01](2026-05-01/refresh-summary.md) | 16 | 9 | 21 | 2604.27351, 2604.26752, 2604.24954 |
| [2026-05-15](2026-05-15/refresh-summary.md) | 12 | 7 | 28 | ... |
```

The header (first 3 lines) is written once on the first ever refresh. Subsequent refreshes append rows.

## papers/README.md

The user-facing entry point. Regenerated each refresh.

```markdown
# Frontier Scout — paper triage

_Last refresh: 2026-05-01 · 21 papers tracked · [run history](runs/index.md)_

## Recommended dive-deep candidates

These are the papers most worth running through `/frontier-scout eval <id>` next, ranked by combined relevance × popularity × verdict-feasibility:

1. **[Heterogeneous Scientific FM Collaboration](2604.27351/paper.md)** · 181 upv · spark-feasible · Machine that Builds Machines
   _Lightweight LLM-orchestrator over domain FMs maps onto NemoClaw + NIM._
2. **[Nemotron 3 Nano Omni](2604.24954/paper.md)** · 12 upv · spark-feasible · Foundations
   _Native NVIDIA 30B-A3B MoE with FP4 weights — Foundations candidate._
3. **[Speculative Decoding in NeMo-RL](2604.26779/paper.md)** · 6 upv · spark-feasible · LLM Wiki
   _Spec decoding inside NeMo-RL at 8B scale — explicitly Spark-class._
4. ...

## What's new this run

See [runs/2026-05-01/refresh-summary.md](runs/2026-05-01/refresh-summary.md) for new + dropped + distributions.

## Full listing

### Machine that Builds Machines (11)

#### spark-feasible (8)
- [2604.26904 ClawGym](2604.26904/paper.md) · 29 · _Claw-style sandboxed agent SFT + lightweight RL._ · [eval](2604.26904/eval.md) · → `articles/clawgym-on-spark/`
- ...

#### borderline (3)
- ...

### LLM Wiki (4)
...

### Frontier Scout (4)
...

## Stats

| Metric | Value |
|--------|------:|
| Total tracked | 21 |
| Classified this run | 16 |
| Dropped under threshold | 9 |
| spark-feasible | 15 |
| borderline | 6 |
| out-of-envelope | 0 |

## Run history

[Append-only refresh log →](runs/index.md)
```

## How `papers.json` is canonical

Every regeneration of `paper.md` and `README.md` reads from `papers.json`. Carry-over in refresh works as:

1. Read existing `papers/papers.json` if present.
2. Build a map of `arxiv_id` → `{ classify, deep_eval, promoted_to }`.
3. After fetching + dedup-ing fresh candidates, merge: if a candidate already exists in the map, carry over the `deep_eval` and `promoted_to` fields verbatim and reuse the prior `classify` (skip re-classification).
4. Write the new `papers.json`, then derive every `paper.md` + `README.md` from it.

If `papers/papers.json` is corrupted, the per-paper folders survive but the carry-over is lost — the next refresh classifies everything fresh. (`paper.md` frontmatter is human-readable; you can grep across it to reconstruct triage state if needed, but JSON is faster and lossless.)
