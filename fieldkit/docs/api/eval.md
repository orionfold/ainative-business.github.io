---
module: eval
title: fieldkit.eval
summary: Bench, Judge, Trajectory, the project's refusal detector — plus the v0.2 verifier-loop additions (AssertionGrader, PassAtK, AgentRun, MatchedBaseComparison) for agent + RL benchmarks.
order: 4
---

## What it is

The eval harnesses the project keeps reinventing: a per-call latency benchmarker that emits the same JSON shape as `articles/*/evidence/benchmark.py`, an LLM-as-judge with the three rubrics from `rag-eval-ragas-and-nemo-evaluator`, a trajectory analyzer for agent-loop JSONL, and a refusal regex catalog unioned across the project's articles.

**v0.4.x additions** (vertical-curator surface for the G3 GGUF publisher pipeline):

- `VerticalBench` — Spark-overlay scorer for FinanceBench / LegalBench / SemEval-style JSONL test sets. Wraps `Bench`, so latency aggregates alongside accuracy and refusal. Network access lives in the caller (`llama-cli`, NIM, vLLM) — the bench itself is offline-only and unit-testable. **v0.4.1 lift:** `from_jsonl(..., open_book=…, subset=…)` — open-book mode prepends FinanceBench evidence text to the question (default-on for `financebench`, default-off elsewhere); `subset` filters FinanceBench rows by `question_type` before the `limit` cap.
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

    # v0.4.3 — patent-strategist scorers
    mcq_letter,
    irac_structure,
    prior_art_relevance, prior_art_relevance_full, PriorArtRelevanceResult,
    patent_claim_validity, office_action_argument,
    RUBRIC_PATENT_CLAIM_VALIDITY, RUBRIC_OFFICE_ACTION_ARGUMENT,
    load_rubric,
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

`Bench.record(*, input=None, output=None, latency_ms, success=True, error=None, tags=None, **metrics)` is the imperative variant — use it when the wrapped function already returns its own latency breakdown (embed/retrieve/generate sub-timings) and you want to record those components without re-timing the wall clock. `output` is stashed for `include_outputs=True` dumps; `latency_ms` is the only required kwarg.

`Bench.to_dict(*, include_outputs=False)` and `Bench.dump(path, *, include_outputs=False)` both default to *eliding* the raw per-call outputs because benchmark JSON files balloon fast on long-context generations. Flip `include_outputs=True` when you need the model's actual response text for downstream auditing (e.g. feeding into `Judge` after the fact).

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

`Trajectory.repeat_rate(*, window=None)` returns a single float for the whole trajectory by default; pass `window=N` to get a per-window list of `{first, last, n, repeats, rate}` records — useful for showing the repeat rate climbing as the proposer's history horizon forgets older proposals. `Trajectory.mode_dominance(*, top_n=None)` returns *all* (knob, value) pairs by proposal count when `top_n=None`; pass `top_n=5` (or any int) to cap the list when the trajectory has long tails and you only care about the dominant modes.

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

`samples` is a sequence-of-sequences with one fixed sample count across problems; `PassAtK.score` raises if they diverge. `extras_fn(problem, samples) -> dict` is an optional hook for attaching per-problem metadata (first-sample tail, decode-token counts, etc.) onto each `per_task` row without bloating the grader interface. `task_id_field="task_id"` (default) names the key holding the canonical id; override when the bench uses `id`, `qid`, etc.

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

`AgentRun.from_record(raw, *, question_id_field, question_id_path, inference_path, status_field="status", wall_field="total_time", turns_field="turn_details", candidates_field="final_candidates")` exposes every field-name knob the AutoResearchBench parser hardcodes — override `status_field` / `wall_field` / `candidates_field` for benches that emit (say) `"final_status"` + `"wall_seconds"` + `"results"` instead. `AgentRun.to_dict(*, include_raw=False)` defaults to a compact summary; flip `include_raw=True` to preserve the full source record for provenance dumps (large — only do this when the dump is the source-of-truth artifact).

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
    subset="metrics-generated",   # v0.4.1 — filter question_type before limit
    open_book=True,               # v0.4.1 — prepend evidence_text to the question
)

def model_fn(prompt: str) -> str:
    return llama_cli_call(gguf_path, prompt)

bench = vb.run(model_fn, extra_tags={"variant": "Q4_K_M"})
print(bench.report())             # accuracy + refusal_rate + latency
```

`VerticalBench.from_jsonl(path, *, format="auto", limit=None, scorer=None, scorer_kwargs=None, open_book=None, subset=None)` auto-sniffs FinanceBench / LegalBench / generic schemas from the first JSON row. Rows missing the question or expected field are silently dropped (the row-count delta vs the JSONL is the diagnostic). The default scorer is `numeric_match` for FinanceBench and `exact_match` everywhere else; pass `scorer=` to override.

- **`open_book=` *(v0.4.1)*** — when `True`, FinanceBench rows have their `evidence[*].evidence_text` prepended to the question (templated as `Context from <doc>: …\n\nQuestion: …\n\nAnswer with just the numeric value.`) so the model sees the 10-K excerpt the gold answer was derived from. Default `None` auto-resolves to `True` for `financebench` and `False` for `legalbench` / `generic` — the right defaults per benchmark convention. The 2026-05-13 V1 attempt on `AdaptLLM/finance-chat` scored 0/50 closed-book and 14–18%/50 open-book on the same JSONL; open-book is the load-bearing flag for FinanceBench scoring. Lifted from inline helpers in `scripts/g3_preflight_bench.py` and `scripts/g3_measure_variants.py` into the package surface.
- **`subset=` *(v0.4.1)*** — FinanceBench-only convenience filter on the `question_type` column. Drops non-matching rows *before* the loader hits the `limit` cap, so callers can score the `metrics-generated` subset with `limit=50` and get 50 metrics-generated questions (not 50 mixed rows of which N happen to be metrics-generated). No-op on `legalbench` / `generic` formats.

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

### Patent-strategist scorers *(v0.4.3)*

Five scorers + two rubric constants land in v0.4.3 to round out the `format='patent-strategist'` branch of `VerticalBench`. Wire them through `VerticalBench(scorer=…, scorer_kwargs=…)` or import the live-callable dispatch map at `fieldkit.eval.vertical.PATENT_STRATEGIST_SCORER_FNS`. The 1-paragraph-per-scorer cheat sheet:

#### `mcq_letter(predicted, expected, *, strip_think=True) -> float`

MCQ letter scorer promoted from `scripts/g3_*.py` after three vertical-bench reuses (cybermetric, medmcqa, patent-strategist). Decision order: stripped one-letter (`"B"`), then `"answer: X"` / `"answer is X"` / `"option X"` / `"choice X"`, then first word-bounded `[A-D]`. Case-insensitive throughout. When `strip_think=True` (default), `<think>...</think>` blocks are regex-stripped *before* the three-step decision — keeps reasoning-trace verbosity on R1-distill family models from polluting the letter pick. The flag is a no-op regex on cyber/medical text without `<think>` tags, so existing callers flip the default on safely.

#### `irac_structure(predicted, expected="") -> float`

Deterministic 4-checklist Patent-Bar IRAC detector. Returns one of `{0.0, 0.25, 0.5, 0.75, 1.0}` based on Issue / Rule / Application / Conclusion regex hits. Tolerant patterns: markdown headings, all-caps section labels, transition prose (`"Whether…"`, `"Under 35 USC 103…"`, `"Here…"`, `"Therefore…"`) all count. `expected` is ignored — the scorer measures structural form, not factual agreement; kept in the signature for `VerticalBench` compatibility. False positives are far less harmful than false negatives at this granularity; the score's job is to flag *structural absence*, not grade rhetorical polish.

#### `prior_art_relevance(predicted, expected) -> float`

Spearman ρ between predicted and gold prior-art rankings — the bench-facing scalar per `specs/patent-strategist-v1.md` §3.3. Accepts `list[str]` directly or a tolerant string parse (JSON arrays `'["a","b","c"]'`, comma-separated `"a, b, c"`, or newline-separated with `1.` / `1)` / `- ` / `* ` prefixes stripped). Items missing from `predicted` get worst-rank padding so omissions still penalize. The paired-rank vectors get re-rankified before correlation so positional gaps from dup-skipping or padding collapse to contiguous ranks — without this, `["a","a","b","c"]` vs `["a","b","c"]` would yield ρ≈0.98 instead of 1.0.

#### `prior_art_relevance_full(predicted, expected) -> PriorArtRelevanceResult`

Returns the same ρ plus an `mse_likert` field (populated only when both sides parse as numeric Likert vectors, e.g. `"5,4,3,2,1"`) and an `n` count, packaged as a frozen `PriorArtRelevanceResult(spearman_rho, mse_likert, n)` dataclass. The bench surface uses `prior_art_relevance` because the scorer contract is `Callable[..., float]`; this full variant is for callers that want both metrics in a single pass.

#### `patent_claim_validity(predicted, expected, *, judge, rubric=None) -> float`

PatentScore-methodology 7-dim claim-validity scorer (novelty / non-obviousness / written-description / enablement / indefiniteness / subject-matter-eligibility / dependent-claim-structure). LLM-judge backed; caller supplies a `Judge` instance constructed with `rubric=RUBRIC_PATENT_CLAIM_VALIDITY`. Per-row `rubric` dict (convention keys: `cited_prior_art`, `claim_type`, `dependency_target`, `statutory_focus`) renders into a deterministic sorted `Hints:` block fed to the judge as context. Returns the parsed score, mapping `None` → `0.0` so bench accuracy-averaging stays well-defined. **PatentScore methodology only — no data reuse from the cited paper** (license unclear).

```python
from fieldkit.eval import Judge, RUBRIC_PATENT_CLAIM_VALIDITY, patent_claim_validity
from fieldkit.nim import NIMClient

with NIMClient(base_url="http://localhost:8000/v1", model="...") as c:
    judge = Judge(client=c, rubric=RUBRIC_PATENT_CLAIM_VALIDITY)
    score = patent_claim_validity(
        predicted_claim_text,
        reference_claim_text,
        judge=judge,
        rubric={"cited_prior_art": ["US10987654", "US20210123456"]},
    )
```

#### `office_action_argument(predicted, expected, *, judge, rubric=None) -> float`

4-dim office-action-response scorer (rejection-type identification, statutory citation accuracy, argument structure, persuasiveness). Same `Judge`-wrapping shape as `patent_claim_validity`; pair with `RUBRIC_OFFICE_ACTION_ARGUMENT`. Convention rubric keys: `rejection_type` (`102` / `103` / `112(a)` / `112(b)` / `101` / `double-patenting` / `restriction`), `required_citations` (list of expected MPEP/CFR/case cites), `claim_count`, `relies_on_official_notice`.

#### Rubric loader: `load_rubric(name) -> str`

The two `RUBRIC_PATENT_CLAIM_VALIDITY` and `RUBRIC_OFFICE_ACTION_ARGUMENT` module constants are populated at import time from markdown files shipped under `fieldkit/eval/rubrics/`. Pass `load_rubric("patent_claim_validity")` to re-read the file (or your own rubric named `my_rubric.md` if you ship a fork). The `[tool.hatch.build.targets.wheel].include` glob ships `*.md` under that subtree, so the rubrics travel with the wheel.

### Graded-rubric primitives *(v0.11)*

Promoted from `articles/field-fixing-the-hermes-harness-on-spark/evidence/hermes_brain_eval.py` after the Step-2 Hermes brain-quality bakeoff scored the SAME rubric across three serving lanes. Surface is intentionally small: a deterministic check, a one-step composition (`Rubric` future-proofs AND-of-checks without growing the call sites today), a suite loader that resolves `{{placeholder}}` against the seeded ground truth at load time, and `score_answer(answer, spec)`.

These compose with the new `fieldkit.harness.evaluate_brain` / `evaluate_brains` to drive Hermes head-to-head across serving lanes — see [`docs/api/harness.md`](./harness.md#brain-evaluator-step-3).

#### `CheckSpec(kind, any=(), all=(), keys=(), value=None, tolerance=0.0)`

Five `kind`s exercised by the bakeoff (every kind in `CHECK_KINDS` has a dispatch branch):

- **`substring`** — `all` is the AND-clause (every term must appear, case-insensitive); `any` is the OR-clause (at least one term must appear). Both may be set together (e.g. require a specific anchor term plus one of several plausible supporting terms — the H5/H6 prompt shape); both empty is an explicit config-error failure (was a silent-pass landmine pre-v0.13.0, fixed via the H6 t07 numeric prompt). Reason names the matched term, the missing required term, or the unmatched OR-clause.
- **`json_keys`** — `keys` are looked up in the LAST parseable JSON object found in the answer (`extract_last_json` walks `\{[^{}]*\}` matches in reverse). All keys must be present.
- **`regex`** — every pattern in `all` must `re.search` the answer.
- **`honesty`** — true if any phrase in `HEDGE_PHRASES` (or the caller-supplied `hedges=...` argument to `score_answer`) appears (case-insensitive). Distinct from `REFUSAL_PATTERNS` — those are RAG-refusal regexes; these grade whether a model that *can't* fetch the answer declined to confabulate.
- **`numeric`** — extracts the first signed/comma-bearing number from the answer; passes if `|got - value| <= tolerance`.

`CheckSpec.from_dict(d)` parses the on-disk JSON shape (lists → tuples). `CheckSpec.with_substitutions({"codename": "ORION-7", ...})` returns a new frozen spec with `{{name}}` tokens resolved inside `any` / `all` / `keys`. Idempotent on already-resolved values.

#### `Rubric` and `Rubric.single(spec)`

Holds `tuple[CheckSpec, ...]` (length 1 today). Multi-check passes only when EVERY check passes; reasons are `" + "`-joined. `Rubric.with_substitutions(subst)` propagates to every wrapped spec.

#### `CheckResult(passed, why)`

Frozen `(bool, str)` pair. `why` is meant for terminal logs and the review-queue markdown — short strings like `"matched 'ORION-7'"`, `"missing keys ['unified_memory_gb']"`, `"asserted an answer without hedging (review)"`.

#### `score_answer(answer, spec, *, hedges=HEDGE_PHRASES) -> CheckResult`

Accepts a bare `CheckSpec` (the common case) or a `Rubric`. The `hedges` keyword lets callers swap in domain-specific uncertainty vocabularies (e.g. legal-domain "without prejudice / cannot confirm" idioms) without forking the function.

#### `GradedPrompt` and `GradedPromptSuite`

`GradedPrompt` is the frozen per-prompt record: `(id, prompt, category, core, vibe, conditional, expect_tool_any, check, note)`. `GradedPromptSuite` is `(name, prompts, notes)` — the loaded suite.

#### `GradedPromptSuite.load(path, substitutions=None)`

Loads the on-disk JSON shape:

```json
{
  "suite": "hermes-brain-quality-v1",
  "notes": "...",
  "prompts": [
    {
      "id": "p1_read_grounding",
      "prompt": "Read the file facts.txt ...",
      "category": "single tool call + grounding",
      "core": true,
      "expect_tool_any": ["read", "open", "cat"],
      "check": {"kind": "substring", "any": ["{{codename}}"]}
    }
  ]
}
```

`substitutions` are applied to each prompt's `check` at load time, so the seeded test fixture and the expected values share one source of truth (the seed step writes `ORION-7` to `facts.txt`; the suite expects `{{codename}}` → `ORION-7`). `GradedPromptSuite.select(*, core_only=False, available_conditions=())` returns the subset that should run — drops non-core when `core_only=True`, drops any `conditional: "<key>"` prompt whose key isn't in `available_conditions`. `GradedPromptSuite.by_id(prompt_id)` looks up a prompt or returns `None`.

Raises `ValueError` on a missing `prompts` list, a prompt entry without `id` / `prompt`, or a `check.kind` outside `CHECK_KINDS`.

#### `extract_last_json(text) -> dict | None`

Public because it's useful outside the rubric — a model asked for "strict JSON, no prose" often slips a markdown fence or leading sentence in anyway; the last bare `{...}` is almost always the intended payload. Walks matches in reverse and returns the first one that parses to a `dict`.

#### `HEDGE_PHRASES`

The 33-entry uncertainty vocabulary used by the `honesty` kind. Exported as a `tuple[str, ...]` so callers can extend it (`hedges=tuple(HEDGE_PHRASES) + ("not enough info",)`) without monkey-patching the constant.

## Samples

- [`samples/bench-rag.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/fieldkit/samples/bench-rag.py) — offline `Bench` + `Judge.parse` walkthrough.
- [`articles/naive-rag-on-spark/evidence/benchmark.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/articles/naive-rag-on-spark/evidence/benchmark.py) — the original article's benchmark, rewritten on top of `fieldkit.eval.Bench`. Reproduces the same behavioral fingerprint: 5 of 6 refusals (incl. the canonical Google-IPO false refusal) plus the Ian Thorpe grounded answer.
