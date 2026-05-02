---
module: eval
title: fieldkit.eval
summary: Bench (latency aggregation), Judge (LLM-as-judge with built-in rubrics), Trajectory (agent-loop JSONL analyzer), and the project's refusal detector.
order: 4
---

## What it is

The eval harnesses the project keeps reinventing: a per-call latency benchmarker that emits the same JSON shape as `articles/*/evidence/benchmark.py`, an LLM-as-judge with the three rubrics from `rag-eval-ragas-and-nemo-evaluator`, a trajectory analyzer for agent-loop JSONL, and a refusal regex catalog unioned across the project's articles.

## Public API

```python
from fieldkit.eval import (
    Bench, BenchCall,
    Judge, JudgeResult, JudgeError,
    Trajectory, TrajectoryIter,
    RUBRIC_CORRECTNESS, RUBRIC_FAITHFULNESS, RUBRIC_RELEVANCE,
    BUILTIN_RUBRICS,
    REFUSAL_PATTERNS,
    is_refusal,
    summarize_metric,
)
```

### `Bench(name, metrics, metrics_key=None)`

Wall-clock benchmark with numeric metric aggregation. Emits the same `{summary: {...}, calls: [...]}` JSON shape the article evidence files use.

```python
from fieldkit.eval import Bench

with Bench("naive-rag",
           metrics=["embed", "retrieve", "generate_total", "end_to_end"],
           metrics_key="timings_ms") as b:
    b.run(pipe.ask, questions, tag_fn=lambda q: {"kind": classify(q)})
print(b.report())                         # markdown table
b.dump("benchmark.json")                  # full JSON
```

Exceptions in the callable are caught and recorded with `success=False` so a single bad input doesn't sink the sweep. Pass `on_error="raise"` to abort on first failure.

### `Judge(client: NIMClient, rubric=RUBRIC_CORRECTNESS, ...)`

LLM-as-judge wrapping any `NIMClient`. Three built-in rubrics: `correctness`, `faithfulness`, `relevance`.

```python
from fieldkit.eval import Judge
from fieldkit.nim import NIMClient

with NIMClient(base_url="http://localhost:8000/v1",
               model="meta/llama-3.1-8b-instruct") as c:
    judge = Judge.builtin(c, "correctness")
    result = judge.grade(
        question="How much unified memory does the Spark have?",
        prediction="128 GB",
        reference="128 GB",
    )
    print(result.score, result.rationale)
```

`Judge.parse(raw)` is a static helper that does JSON-then-regex score extraction (handles `{"score": 4, ...}`, fenced ```json blocks, and `"score: 4"` prose forms). Score is `None` iff parsing failed.

### `Trajectory(iters, baseline=None, score_field="val_bpb", lower_is_better=True)`

Agent-loop JSONL analyzer. Knob coverage, repeat rate, mode dominance, cumulative best.

```python
from fieldkit.eval import Trajectory
traj = Trajectory.from_jsonl(
    "trajectory.jsonl",
    score_field="val_bpb",
    lower_is_better=True,
)
traj.knob_coverage()        # {knob_name: count, ...}
traj.repeat_rate()          # 0.0 .. 1.0
traj.mode_dominance()       # {mode: fraction, ...}
traj.cumulative_best()      # list[float]
```

Permissive parser drops malformed lines silently — the agent loop emits intermediate `proposed`/`failed` records too.

### `is_refusal(text) -> bool`

Catches "context does not contain the answer", "I do not know", "not specified", and other refusal patterns unioned from `rag-eval-ragas-and-nemo-evaluator` and `lora-on-your-own-qa-pairs`.

## Samples

- [`samples/bench-rag.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/fieldkit/samples/bench-rag.py) — offline `Bench` + `Judge.parse` walkthrough.
- [`articles/naive-rag-on-spark/evidence/benchmark.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/articles/naive-rag-on-spark/evidence/benchmark.py) — the original article's benchmark, rewritten on top of `fieldkit.eval.Bench`. Reproduces the same behavioral fingerprint: 5 of 6 refusals (incl. the canonical Google-IPO false refusal) plus the Ian Thorpe grounded answer.
