---
module: lineage
title: fieldkit.lineage
summary: Append-only trial log plus deterministic prompt rendering — every experiment lands as one typed TSV row, and a Markdown lineage block briefs the next session on entry.
order: 6
---

## What it is

The release_artifacts pattern from cxcscmu's *Auto-Research-Recipes* harness, decomposed into Python. Four dataclasses, one enum, ~200 lines of pure-stdlib code — and a determinism contract: same TSV state in, same rendered Markdown out.

The case for the primitive sits in cxcscmu's own `pg_ablation_lineage_on` vs `pg_ablation_lineage_off` runs. Same agent. Same prompt template. Same 201 trials of search budget on Parameter Golf. Same Claude Opus on each specialist. The only difference is whether the agent's session prompt includes the rendered lineage block. With lineage on: 16 keeps (8.0%), 38 eval-budget overruns (19%), best `val_bpb` 1.073142. With lineage off: 3 keeps (1.5%), **123 eval-budget overruns (61%)**, best `val_bpb` 1.077413. **5.3× more keeps · 3.2× fewer wall-wastes · 0.004 val_bpb deeper.** The intervention isn't the agent. The intervention is letting the agent see what was tried.

`fieldkit.lineage` is the portable substrate that lets you give that intervention to your own loops — no model weights, no GPUs, no NIM containers, no Claude budget. A TSV writer with `fcntl.flock` for concurrent specialist writes, a small enum, a deterministic Markdown renderer.

## Public API

```python
from fieldkit.lineage import (
    FailureLabel,
    Trial,
    RecipeEdit,
    LineageSnapshot,
    LineageStore,
)
```

### `FailureLabel`

String-valued enum with 10 classes; `value` round-trips identically to cxcscmu's TSV `status` column.

| value | meaning |
|---|---|
| `keep` | Trial ran to completion, improved the leaderboard, snapshot archived |
| `discard` | Trial ran to completion, didn't improve — informational, the clean failure mode |
| `crash` | Trial died mid-run (exception, OOM, NCCL error) |
| `eval_budget_overrun` | Trained inside budget, eval phase exceeded its wall — partial signal |
| `train_budget_overrun` | Training phase exceeded its wall |
| `size_blocked` | Killed by an artifact-size constraint |
| `preflight_crash` | Died before the trial proper started (infrastructure) |
| `harness_abort` | Bookkeeping kill (the only non-informational class) |
| `disqualified` | Vision-side: completed but failed a structural gate (CIFAR) |
| `baseline` | The seed every run starts from |

The `is_informational` property returns `False` only for `harness_abort` — everything else carries signal for the next agent.

### `Trial`

Frozen dataclass for one TSV row. 17 fields in canonical order: `exp_id`, `timestamp`, `specialist`, `parent_exp`, `baseline_exp`, `domain`, `hypothesis`, `expected_delta`, `status`, `core_metric`, `val_bpb`, `delta_vs_best`, `train_s`, `total_s`, `job_name`, `snapshot_path`, `notes`.

`core_metric` is the task-agnostic primary metric — for language-model runs it mirrors `val_bpb`; for vision tasks it carries top-1 error or whatever the leaderboard sorts on. The duplicated `val_bpb` column is preserved for direct interop with cxcscmu-shaped TSVs.

```python
Trial.header()         # canonical TSV header (17 field names in order)
trial.to_row()         # ['000', '2026-05-11T10:00:00Z', 'baseline', ...]
Trial.from_row(rowdict)  # parse one csv.DictReader row back to a Trial
```

### `LineageStore(root, *, lower_is_better=True)`

Append-only TSV writer at `root/results.tsv` plus read-side accessors. All writes hold an exclusive `fcntl.flock` across the header-write + row-write sequence, so multiple specialists can write concurrently without interleaving.

```python
from pathlib import Path
from fieldkit.lineage import LineageStore, Trial, FailureLabel

store = LineageStore(Path("magent_state/blackboard"))
store.append(Trial(exp_id="000", ..., status=FailureLabel.BASELINE, ...))

store.all_trials()        # list[Trial] in insertion order
store.latest(n=30)        # tuple[Trial, ...] most recent
store.best()              # Trial | None — best informational row by core_metric
store.chain_to("014")     # tuple[Trial, ...] root-first, walking parent_exp
```

### `LineageStore.render_prompt(for_specialist, *, top_k=20, recent_n=30, last_m_full=10, session_timestamp="")`

The deterministic Markdown renderer. Returns a `LineageSnapshot` carrying both the rendered string and the underlying structured data (so callers can index in without re-parsing). Output mirrors cxcscmu's `release_artifacts/example_lineage_pg_lineage_on_arch.txt` shape: header line, `## LEADERBOARD.md` (current best + top-K kept table), `## KNOWLEDGE.md` (current-best lineage as a nested `└─` chain + recent-activity table + last-M detailed entries).

```python
snap = store.render_prompt(
    for_specialist="opt",
    top_k=20,
    recent_n=30,
    last_m_full=10,
    session_timestamp="2026-05-11T11:00:00Z",
)
print(snap.rendered_prompt)          # the Markdown block
snap.current_best                    # the Trial it pointed at
snap.chain_to_best                   # tuple[Trial, ...] root → best
snap.top_k_leaderboard               # tuple[Trial, ...] sorted by core_metric
```

### `RecipeEdit`

Frozen dataclass pairing a keep trial with its workdir snapshot and the parent snapshot. `diff()` computes a unified diff of every text file in the snapshot vs the parent on first call (binary files emit a `Binary files ... differ` marker).

```python
edit = RecipeEdit(
    trial=keep_trial,
    snapshot_path=Path("snapshots/014_opt"),
    parent_snapshot_path=Path("snapshots/000_baseline"),
)
print(edit.diff())   # unified diff a/train.py → b/train.py
```

The baseline trial returns an empty diff (no parent).

## Why this surface

Three things to notice about the shape. First, `FailureLabel.is_informational` is the cxcscmu `_QUARANTINED_STATUSES` rule made into a method — any downstream consumer can read it without re-implementing the policy. Second, `LineageSnapshot` is a record of *what the agent saw* (including the rendered prompt), not just a reference to the underlying TSV state. That matters for reproducibility: if you want to know why the agent at iteration 178 made the choice it did, you read the snapshot, not the TSV. Third, `LineageStore.render_prompt` is the same deterministic function cxcscmu's `harness/blackboard.py` implements (~600 lines of careful Markdown assembly); the `fieldkit.lineage` version is the published, testable, pure-stdlib port.

The module lands at the top level of `fieldkit` because lineage is task-agnostic. Parameter Golf uses it. NanoChat-D12 uses it. CIFAR uses it — and its `disqualified` class is the evidence that this primitive isn't language-model-specific. Putting it under `fieldkit.training` would suggest LM specificity that isn't there.

## Samples

- [`samples/hello-lineage.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/fieldkit/samples/hello-lineage.py) — five-trial worked example: baseline, two keeps, one discard, one `eval_budget_overrun`. Prints the rendered prompt.
- [`articles/auto-research-loop-on-spark/`](https://ainative.business/field-notes/auto-research-loop-on-spark/) — anchor article. Walks the 17-column schema, the 10-class enum semantics, and the `pg_ablation_lineage_on/off` ablation that proves the primitive's value.
