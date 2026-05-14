---
module: eval
title: fieldkit.eval
summary: Bench, Judge, Trajectory, the project's refusal detector — plus the v0.2 verifier-loop additions (AssertionGrader, PassAtK, AgentRun, MatchedBaseComparison) for agent + RL benchmarks.
order: 4
---

## What it is

The eval harnesses the project keeps reinventing: a per-call latency benchmarker that emits the same JSON shape as `articles/*/evidence/benchmark.py`, an LLM-as-judge with the three rubrics from `rag-eval-ragas-and-nemo-evaluator`, a trajectory analyzer for agent-loop JSONL, and a refusal regex catalog unioned across the project's articles.

**v0.4.x additions** (vertical-curator surface for the G3 GGUF publisher pipeline):

- `VerticalBench` — Spark-overlay scorer for FinanceBench / LegalBench / SemEval-style JSONL test sets. Wraps `Bench`, so latency aggregates alongside accuracy and refusal. Network access lives in the caller (`llama-cli`, NIM, vLLM) — the bench itself is offline-only and unit-testable.
- `VerticalQA` — one test case (qid + question + expected + tags) lifted from a vertical-eval JSONL.
- `exact_match` / `contains` / `numeric_match` — the three built-in scorers. `numeric_match` is the FinanceBench default (first-number ±1% rel-tol); `exact_match` is the LegalBench default; `contains` is the right pick when the model answers in prose around a key fact.

**v0.2 additions** (verifier-loop and agent-bench primitives):

- `AssertionGrader` — pure file-system grader over five assertion primitives (`file_exists`, `file_not_exists`, `file_contents_contain`, `file_contents_match_regex`, `file_unchanged`). Lifted from `clawgym-on-spark`'s deterministic grader.
- `PassAtK` + `pass_at_k_estimator` — verifier-loop with the Chen 2021 unbiased pass@k estimator. Lifted from the `pass-at-k-after-the-seventh-patch` follow-up.
- `AgentRun` + `TurnDetail` + `summarize_agent_runs` — per-question agent-bench schema with overrideable field-name path tuples for non-AutoResearchBench layouts. Lifted from `autoresearchbench-on-spark`.
- `MatchedBaseComparison` + `GroupStats` + `MatchedBaseComparisonResult` — two-rollout B−A driver with per-group + per-assertion-kind delta and a markdown `.report()`. Lifted from the `clawgym-on-spark` Phase 5 SFT-vs-base eval.

## Public API

```python
from fieldkit.eval import (
    # v0.1
    Bench, BenchCall,
    Judge, JudgeResult, JudgeError,
    Trajectory, TrajectoryIter,
    RUBRIC_CORRECTNESS, RUBRIC_FAITHFULNESS, RUBRIC_RELEVANCE,
    BUILTIN_RUBRICS,
    REFUSAL_PATTERNS,
    is_refusal,
    summarize_metric,

    # v0.2 — assertion grader
    ASSERTION_KINDS,
    AssertionGrader, AssertionResult, GradeResult,

    # v0.2 — pass@k
    PassAtK, PassAtKResult,
    pass_at_k_estimator,

    # v0.2 — agent runs
    AgentRun, TurnDetail,
    summarize_agent_runs,

    # v0.2 — matched-base comparison
    MatchedBaseComparison, MatchedBaseComparisonResult, GroupStats,

    # v0.4.x — vertical-curator surface
    VerticalBench, VerticalQA,
    contains, exact_match, numeric_match,
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

### `AssertionGrader()` *(v0.2)*

Pure-function grader over five file-system assertion primitives — no LLM, no fuzzy matching, no scoring. The five supported kinds are listed in `ASSERTION_KINDS`; an unknown kind fails the assertion with `"unknown kind: <k>"` rather than crashing the grade.

```python
from pathlib import Path
from fieldkit.eval import AssertionGrader

grader = AssertionGrader()
result = grader.grade(
    task,                                 # SynthTask-shaped dict OR bare list
    post_state_root=Path("/tmp/sandbox-N"),
)
print(result.passed, result.n_passed, result.n_total)
```

`task` accepts either a SynthTask-shaped dict (must have `verifiable_assertions`; may have `task_id` and `workspace_seed.files`, the latter auto-populates `seed_files` for `file_unchanged` checks) or a bare list of assertion dicts (each with `kind`, `path`, plus kind-specific keys like `must_contain` / `regex`). Pass `seed_files=` explicitly to enforce `file_unchanged`; without it those assertions report "skipped (no seed content)" and count as pass.

`GradeResult` is JSON-serializable via `.to_dict()` and carries per-assertion outcomes plus the binary AND across all assertions. `AssertionResult.detail` is empty on pass; on failure it records the proximate cause (missing path, regex did not match, divergent contents, etc.) so a grade dump is debuggable without re-running the rollout.

### `PassAtK(ks=(1,))` and `pass_at_k_estimator(n, c, k)` *(v0.2)*

Verifier-loop primitive: pass@k from per-task n-sample grades, using the **Chen et al. (2021) unbiased estimator** `1 - C(n-c, k) / C(n, k)`. Lower variance than the naive `1 - (1-p)^k` for finite n; the naive form silently over-estimates when c is small relative to n.

```python
from fieldkit.eval import PassAtK

pak = PassAtK(ks=(1, 8))
result = pak.score(
    problems=[{"task_id": "HumanEval/0", "test": "...", ...}, ...],
    samples=[["sample1", "sample2", ...], ...],   # K per problem
    grader=lambda text, problem: humaneval_run(text, problem),
)
print(result.pass_at)            # {1: 0.7050, 8: 0.8415}
```

`samples` is a sequence-of-sequences with one fixed sample count across problems; `PassAtK.score` raises if they diverge. `extras_fn(problem, samples) -> dict` is an optional hook for attaching per-problem metadata (first-sample tail, decode-token counts, etc.) onto each `per_task` row without bloating the grader interface.

When you've already graded the rollout offline (e.g. you have a `comparison.json` from a prior bench), use `pak.from_rows(rows)` with pre-counted `(task_id, n, passed)` triples to skip re-grading.

The standalone `pass_at_k_estimator(n, c, k)` is exported separately for callers who already have `(n, c)` rows.

### `AgentRun` + `TurnDetail` + `summarize_agent_runs(runs)` *(v0.2)*

Canonical schema for any third-party agent bench that emits a per-question record with a status, total wall time, and a list of turn dicts. Covers AutoResearchBench, autoresearch-agent-loop, and clawgym-on-spark rollouts out of the box; field-name path tuples on `from_record` cover the rest.

```python
from fieldkit.eval import AgentRun, summarize_agent_runs

runs = AgentRun.from_jsonl(
    "evidence/runs/llama-3.1-8b/inference_output.jsonl"
)
print(summarize_agent_runs(runs, label="llama-3.1-8b"))

# Custom bench shape — override the path tuples
custom = AgentRun.from_record(
    raw,
    question_id_field="task_id",
    question_id_path=(),                   # top-level
    inference_path=("result",),            # not inference_results[0]
    turns_field="trace",
)
```

`TurnDetail` keeps five canonical fields (`turn`, `action`, `duration_s`, `input_tokens`, `output_tokens`) and stuffs everything else from the source record into `extras` so the canonical accessors stay stable while bench-specific fields (`papers_retrieved`, `parse_errors`, `candidate_cfg`) survive round-tripping.

Convenience accessors on `AgentRun` are pure derivations of `turns`: `tool_calls()` (action == "tool"), `tool_format_errors()` (action == "error"), `total_input_tokens()`, `total_output_tokens()`, `succeeded()` (status == "finished" AND ≥1 candidate). Override `succeeded()` for benches with different success semantics.

`summarize_agent_runs(runs, label="...")` aggregates per-status counts plus `summarize_metric` rollups for `wall_seconds`, `turns`, `candidates`, `tool_calls`, `tool_format_errors`. Mirrors the JSON shape `articles/autoresearchbench-on-spark/scripts/analyze_run.py` writes — pass straight to `json.dumps`.

### `MatchedBaseComparison(group_extractor=...)` *(v0.2)*

Two-rollout B−A comparison over a held-out task set. The "filter held-out by training-set membership → run rollout twice with different `--model` → emit B − A comparison" pattern is reusable for any LoRA / adapter ablation — GRPO-vs-SFT, fine-tuned-vs-base, system-prompt-A-vs-B.

Trajectory record schema (one dict per task):

```json
{
    "task_id": "synth-<persona>-NN",
    "final_grade": {
        "passed": true,
        "n_passed": 3,
        "n_total": 3,
        "assertions": [{"kind": "file_exists", "passed": true}, ...]
    },
    "stopped": "task_complete",
    "n_turns": 5,
    "wall_seconds": 12.3
}
```

```python
from fieldkit.eval import MatchedBaseComparison
import json

cmp = MatchedBaseComparison()
result = cmp.compare(
    baseline=base_trajectories,    # list of dicts OR path/JSONL
    candidate=sft_trajectories,
)
print(result.report())             # markdown headline + per-group + per-kind
json.dump(result.to_dict(), open("comparison.json", "w"), indent=2)
```

`group_extractor` defaults to a synth-persona splitter (`synth-data-science-researcher-03 → data-science-researcher`); pass any `Callable[[str], str]` for arxiv-id prefixes, Bench question categories, or other task-id schemes. Set to `None` to disable per-group breakdown.

`GroupStats` aggregates one rollout: total + per-passed task counts, per-assertion totals, `by_group` and `by_kind` buckets, stop-reason histogram, mean turns, mean wall. `MatchedBaseComparisonResult.overall_delta` carries the headline four numbers — task and per-assertion deltas in percentage points, plus mean-turns and mean-wall deltas. `.report()` renders a markdown summary table; `.to_dict()` serializes the full comparison for `comparison.json` files.

`MatchedBaseComparison.stats(rows)` is exposed separately when you only need single-rollout aggregation (no comparison). Accepts a list/iterable of dicts or a JSONL path.

### `VerticalBench(name, questions, scorer=exact_match, ...)` *(v0.4.x)*

Spark-overlay scorer for vertical-domain test sets — FinanceBench, LegalBench, SemEval-style JSONL — that the G3 GGUF publisher pipeline uses as its fourth measurement axis alongside perplexity, tok/s, and sustained-load minutes.

The bench is intentionally callable-shaped: it accepts a `model_fn(prompt) -> str` and times each call via the existing `Bench` harness, so latency aggregates alongside accuracy and refusal. Network access lives in the caller (llama-cli, NIM, vLLM), keeping the bench offline-only for unit tests.

```python
from fieldkit.eval import VerticalBench, numeric_match

vb = VerticalBench.from_jsonl(
    "financebench.jsonl",
    scorer=numeric_match,         # FinanceBench → first-number ±1%
    limit=50,
)

def model_fn(prompt: str) -> str:
    return llama_cli_call(gguf_path, prompt)

bench = vb.run(model_fn, extra_tags={"variant": "Q4_K_M"})
print(bench.report())             # accuracy + refusal_rate + latency
```

`VerticalBench.from_jsonl(path, *, format="auto", limit=None, scorer=None, scorer_kwargs=None)` auto-sniffs FinanceBench / LegalBench / generic schemas from the first JSON row. Rows missing the question or expected field are silently dropped (the row-count delta vs the JSONL is the diagnostic). The default scorer is `numeric_match` for FinanceBench and `exact_match` everywhere else; pass `scorer=` to override.

`VerticalBench.run(model_fn, *, limit=None, on_error="record", extra_tags=None)` returns the underlying `Bench` so callers route through the existing `.summary()` / `.report()` / `.dump()` pipeline. Each `BenchCall` carries `accuracy` (0.0/1.0 from the scorer) and `refusal` (0.0/1.0 from `is_refusal`) metrics; per-row metadata (company, doc_period, question_type) flows through to `BenchCall.tags` for downstream slice-by aggregation.

`VerticalBench.summary()` produces a lightweight `{name, n, scorer, tag_keys}` dict without invoking the model — useful in the lineage entry recording *what* the bench will measure before the model has actually run.

### `VerticalQA` *(v0.4.x)*

```python
@dataclass(frozen=True, slots=True)
class VerticalQA:
    qid: str                              # FinanceBench `financebench_id`, etc.
    question: str
    expected: str
    tags: dict[str, Any] = field(default_factory=dict)
```

One vertical-eval test case. The `qid` is the row's stable id so per-row scores can be cross-referenced against the source JSONL; `tags` carry per-row metadata (company, doc_period, question_type) that flow through to `Bench` for slice-by aggregation downstream.

### Scorers — `exact_match` / `contains` / `numeric_match` *(v0.4.x)*

Pluggable `Callable[[predicted, expected], float]` returning 1.0 / 0.0. Pass any custom callable into `VerticalBench(scorer=...)`; the three built-ins cover the dominant patterns:

```python
exact_match("yes", "Yes")                          # 1.0 — whitespace + case-insensitive
contains("The 2023 revenue was $4.5B.", "$4.5B")   # 1.0 — substring match
numeric_match("Revenue was $4.55B", "4.5B")        # 1.0 — first number, ±1% rel-tol
numeric_match("Revenue was $4.55B", "4.5B",
              rel_tolerance=0.001)                 # 0.0 — tighter tol
```

| Scorer | When to use it |
|---|---|
| `exact_match(p, e)` | LegalBench-style single-label classification (`yes` / `no` / `hold` / `overrule`). Whitespace- and case-insensitive. |
| `contains(p, e)` | The model is asked to answer in prose and the reference is a key fact/number/phrase that must appear somewhere in the answer. |
| `numeric_match(p, e, *, rel_tolerance=0.01)` | FinanceBench-style quantitative answers. Extracts the first number from each side (commas stripped), compares under relative tolerance. Defaults to ±1% per FinanceBench's grading convention. Returns 0.0 if either side has no parseable number — including refusals, so the refusal counter elsewhere doesn't need to gate this scorer. |

## Samples

- [`samples/bench-rag.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/fieldkit/samples/bench-rag.py) — offline `Bench` + `Judge.parse` walkthrough.
- [`articles/naive-rag-on-spark/evidence/benchmark.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/articles/naive-rag-on-spark/evidence/benchmark.py) — the original article's benchmark, rewritten on top of `fieldkit.eval.Bench`. Reproduces the same behavioral fingerprint: 5 of 6 refusals (incl. the canonical Google-IPO false refusal) plus the Ian Thorpe grounded answer.
