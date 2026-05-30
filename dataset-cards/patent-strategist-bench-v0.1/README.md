---
license: cc-by-4.0
task_categories:
- question-answering
- multiple-choice
- text-generation
language:
- en
size_categories:
- n<1K
tags:
- patent
- legal
- mpep
- reasoning
- benchmark
- ipc
- prior-art
- patentmatch
- bigpatent
pretty_name: Patent-Strategist Bench v0.1
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.jsonl
---

# Patent-Strategist Bench v0.1

A 200-question, seven-shape benchmark for patent-prosecution reasoning, anchored
to three public sources (USPTO MPEP, HPI-Naumann PatentMatch, BIGPATENT) with
oracle context attached to every row. Built to evaluate whether a small open
LLM can perform the day-to-day reasoning tasks of a patent practitioner.

Companion artifact to two methodology articles:

1. [Patent-Strategist v1 baseline on Spark](https://ainative.business/field-notes/patent-strategist-v1-baseline-on-spark/) — establishes the first tri-mode (closed-book / retrieval / oracle) baseline numbers on this bench using `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` Q5_K_M.
2. [Fine-tune data-prep decisions on Spark](https://ainative.business/field-notes/fine-tune-data-prep-decisions-on-spark/) — documents the corpus-contamination, BOS/EOS-bookend, and catastrophic-forgetting axes that the next paired-prediction drop has to clear.

## Quick stats

| Shape | Family | Source | n | What it measures |
|---|---|---|---:|---|
| `A` | Claim drafting + validity | BIGPATENT | 50 | Identify a "white-space" angle adjacent to a granted claim |
| `B` | Prior-art ranking | PatentMatch | 40 | Pick the cited document most relevant to a target claim |
| `C` | C-family landscape | BIGPATENT | 20 | Reason about an IPC-class subset for FTO / cross-licensing |
| `D-mcq` | MPEP-grounded MCQ | MPEP | 40 | 4-choice with a single correct letter on a precise MPEP section |
| `D-irac` | MPEP-grounded IRAC | MPEP | 10 | Free-text IRAC analysis (Issue/Rule/Application/Conclusion) |
| `D-oa` | Office-action argument | MPEP | 10 | Draft a written argument rebutting an examiner rejection |
| `E` | Patent strategy free-text | BIGPATENT | 30 | Open-ended strategic question on a granted abstract |
| **Total** | | | **200** | |

Every row carries an `oracle_context` field — the controlling MPEP subsection,
the canonical PatentMatch pair, or the BIGPATENT abstract — so the bench can be
run in three modes:

| Mode | What the model sees | Question it answers |
|---|---|---|
| **closed-book** | `question` only | What does the model already know? |
| **retrieval** | `question` + top-k retrieved chunks (BGE-small / MPEP+PatentMatch) | Is the retriever good enough? |
| **oracle** | `question` + `oracle_context` | Is the model's reasoning bottleneck the retriever or the model itself? |

## Baseline numbers — DeepSeek-R1-0528-Qwen3-8B Q5_K_M (llama.cpp, temp 0.6)

On the 90 deterministic-scoring rows (B + D-mcq + D-irac), aggregated across the
60 MPEP-grounded shapes for the D-mcq sub-ladder:

| Mode | Overall mean | D-mcq |
|---|---:|---:|
| closed-book | 0.397 | 0.625 |
| retrieval (BGE-small + FAISS over MPEP + PatentMatch) | 0.489 | 0.850 |
| oracle | 0.541 | 0.950 |

The **closed-to-retrieval gap (+0.225) is 2.25× the retrieval-to-oracle gap
(+0.100)** — meaning fine-tuning the model closes a bigger lift than improving
the retriever for an 8B reasoning model on patent prosecution. This was the
headline finding of the baseline article.

`A`, `C`, `D-oa`, `E` rows are scored by LLM judge (Claude) against the rubric
notes carried in each row; baselines on those will be added to v0.2.

## Schema

```
qid               str         # stable id (e.g., ps-D-D1-9e74cd9b0a)
question          str         # the prompt
family            str         # A / B / C / D / E
shape             str         # A / B / C / D-mcq / D-irac / D-oa / E
use_case          str         # A1, A2, B1, ... — finer-grained slot
scoring_mode      str         # 'oracle' for all v0.1 rows
gold_label        str         # exact gold answer / letter / free-text
options           List[str]   # 4-tuple A/B/C/D for D-mcq; empty otherwise
oracle_context    str         # MPEP subsection / PatentMatch pair / BIGPATENT abstract
source            str         # 'mpep' / 'patentmatch' / 'bigpatent'
source_status     str         # 'anchored' (sourced directly) — all v0.1 rows
rubric_notes      str         # reviewer rubric used when scoring (LLM-judge for A/C/D-oa/E)
source_metadata   str (JSON)  # source-specific subkeys (ipc_class / chapter / url / claim_id …)
```

`source_metadata` is JSON-serialized to keep the table schema flat. Parse with
`json.loads(row["source_metadata"])` — fields vary by source:

* `bigpatent` (shapes A, C, E): `ipc_class`
* `mpep` (shapes D-*): `chapter`, `section_id`, `url`
* `patentmatch` (shape B): `cited_document_id`, `claim_id`, `patent_application_id`, `label_letter`

## How to use

```python
from datasets import load_dataset

ds = load_dataset("Orionfold/patent-strategist-bench-v0.1", split="train")
print(ds)  # 200 rows

# Filter to MPEP-grounded MCQs only:
mcq = ds.filter(lambda r: r["shape"] == "D-mcq")
print(mcq[0]["question"])
print(mcq[0]["options"])
print("gold:", mcq[0]["gold_label"])
```

Pair with [`fieldkit`](https://pypi.org/project/fieldkit/) for ready-to-use
scorers — `fieldkit.eval.score_prediction(shape, predicted, gold_label,
oracle_context=...)` dispatches to the right scorer per shape:

```python
from fieldkit.eval import score_prediction

for row in mcq:
    predicted_letter = my_model(row["question"], row["options"])
    score = score_prediction("D-mcq", predicted_letter, row["gold_label"])
```

## Sources & licensing

| Source | License | What we used |
|---|---|---|
| **USPTO MPEP** | Public domain (U.S. government work) | 2,047 MPEP subsections → 4,437 RAG chunks → `D-*` row seeds |
| **HPI-Naumann PatentMatch** ([huggingface.co/datasets/pakuvis/PatentMatch](https://huggingface.co/datasets/pakuvis/PatentMatch)) | CC-BY-4.0 | 25,340 EPO claim↔prior-art pairs → `B` row seeds |
| **BIGPATENT** ([huggingface.co/datasets/big_patent](https://huggingface.co/datasets/big_patent)) | CC-BY-4.0 | 1.3M U.S. patent abstracts → `A`, `C`, `E` row seeds |

This bench is released under **CC-BY-4.0** matching the most-restrictive source
license. Questions and rubric notes were synthesized with Anthropic Claude
Sonnet 4.6 against the source materials (synthesis is a transformative use;
attribution to upstream sources preserved per-row in `source_metadata`).

## Limitations

* **Single language**: English-only. EPO claims in PatentMatch were already
  English-translated; non-English patent corpora are not represented.
* **Time bound**: MPEP citations are current to the 2026-05 mirror; later MPEP
  revisions may move section numbers.
* **Single annotator (Claude Sonnet 4.6)**: the rubric notes attached to each
  row are synthesized, not human-reviewed. v0.2 will land human-reviewer flags
  on the `D-mcq` block.
* **Small n per shape**: 10 rows is a sketch, not statistical evidence. The
  bench is sized for tight feedback loops in fine-tuning experiments; if you
  need confidence intervals, sample with replacement or supplement with your
  own seeds.

## Citation

```bibtex
@dataset{patent_strategist_bench_2026,
  title  = {Patent-Strategist Bench v0.1: a 200-question seven-shape benchmark for patent-prosecution reasoning},
  author = {Sehgal, Manav and Orionfold},
  year   = {2026},
  month  = {5},
  url    = {https://huggingface.co/datasets/Orionfold/patent-strategist-bench-v0.1},
  note   = {Companion to "Patent-Strategist v1 baseline on Spark", ainative.business/field-notes/patent-strategist-v1-baseline-on-spark/}
}
```

## Roadmap

* **v0.2** — add A-shape and D-oa LLM-judge baselines; flag double-reviewed rows
  on the D-mcq block
* **v0.3** — add 50 rows for the C-family-landscape and E-shape strategic blocks
  from Google Patents BigQuery (Family C2 cross-licensing question type)
* **v1.0** — paired closed-book / retrieval / oracle and fine-tuned predictions
  shipped alongside the bench. Specific base model pending; see the
  methodology articles for the constraints the next attempt has to clear.

## Provenance

This bench is the W2 milestone of the open patent-strategist project. The
seed-generation, scoring, and three-mode baseline harness live as open Python
in the source repo: [github.com/manavsehgal/ai-field-notes](https://github.com/manavsehgal/ai-field-notes)
under `scripts/seed_patent_bench.py`, `scripts/run_rag_baseline.py`, and
`fieldkit/src/fieldkit/eval/__init__.py`.
