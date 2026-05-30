#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Hello-world for fieldkit.lineage — write a small lineage and render the prompt.

Walks the same primitive cxcscmu's release_artifacts implement: append a
baseline, a couple of keeps, a discard, and an eval_budget_overrun, then
render the Markdown block a specialist would see at session entry.

This is the portable part of the auto-research-loop study — the agent
infrastructure is unportable (it needs 8xH100 nodes and a Claude Opus
subscription per specialist), but the TSV writer and the render function
are pure-stdlib Python and run anywhere.

Run:
    python samples/hello-lineage.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fieldkit.lineage import FailureLabel, LineageStore, Trial


def make_trial(
    exp_id: str,
    *,
    timestamp: str,
    specialist: str,
    parent: str,
    hypothesis: str,
    status: FailureLabel,
    core_metric: float | None,
    delta: float | None,
    notes: str = "",
) -> Trial:
    return Trial(
        exp_id=exp_id,
        timestamp=timestamp,
        specialist=specialist,
        parent_exp=parent,
        baseline_exp="000",
        domain=specialist,
        hypothesis=hypothesis,
        expected_delta=f"{delta:+.4f}" if delta is not None else "",
        status=status,
        core_metric=core_metric,
        val_bpb=core_metric,
        delta_vs_best=delta,
        train_s=540.0 if status is not FailureLabel.BASELINE else None,
        total_s=1120.0 if status is not FailureLabel.BASELINE else None,
        job_name=f"exp_{exp_id}",
        snapshot_path=f"snapshots/{exp_id}_{specialist}" if status is FailureLabel.KEEP else "",
        notes=notes,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lineage_demo_") as d:
        store = LineageStore(Path(d), lower_is_better=True)

        # Baseline: the seed every run starts from.
        store.append(
            make_trial(
                "000",
                timestamp="2026-05-11T10:00:00Z",
                specialist="baseline",
                parent="",
                hypothesis="PR #1758 seed (CaseOps + PreQuant TTT)",
                status=FailureLabel.BASELINE,
                core_metric=1.081,
                delta=None,
            )
        )

        # exp_014: clean keep — Muon weight-decay split + TTT epoch reduction.
        store.append(
            make_trial(
                "014",
                timestamp="2026-05-11T10:14:00Z",
                specialist="opt",
                parent="000",
                hypothesis=(
                    "Split Muon MLP weight decay (muon_wd=0.095 attn, "
                    "muon_wd_mlp=0.115 MLP) + reduce ttt_epochs from 3 to 2"
                ),
                status=FailureLabel.KEEP,
                core_metric=1.078777,
                delta=-0.002223,
                notes="3-seed mean clears noise floor; clean win on TTT-cost too",
            )
        )

        # exp_015: eval_budget_overrun — informational but no metric.
        store.append(
            make_trial(
                "015",
                timestamp="2026-05-11T10:15:00Z",
                specialist="arch",
                parent="014",
                hypothesis="Per-head q_gain bifurcation with full RoPE pass",
                status=FailureLabel.EVAL_BUDGET_OVERRUN,
                core_metric=None,
                delta=None,
                notes="trained inside budget but eval overran 600s wall",
            )
        )

        # exp_030: keep — bifurcated q_gain (succeeded after fixing exp_015's eval cost).
        store.append(
            make_trial(
                "030",
                timestamp="2026-05-11T10:30:00Z",
                specialist="arch",
                parent="014",
                hypothesis="Bifurcate per-head q_gain into [H, 2] (RoPE-rotated + non-rotated)",
                status=FailureLabel.KEEP,
                core_metric=1.078041,
                delta=-0.000736,
                notes="exp_015 lineage prevented re-attempting full-RoPE variant",
            )
        )

        # exp_031: discard — informational but didn't improve.
        store.append(
            make_trial(
                "031",
                timestamp="2026-05-11T10:31:00Z",
                specialist="reg",
                parent="030",
                hypothesis="Stochastic depth with linear scaling (max_rate=0.1)",
                status=FailureLabel.DISCARD,
                core_metric=1.080500,
                delta=0.002459,
                notes="DropPath applied to delta, hurt val_bpb by 0.0025",
            )
        )

        # Read side — what did we end up with?
        all_trials = store.all_trials()
        print(f"=== lineage store at {store.results_path} ===")
        print(f"trials appended: {len(all_trials)}")
        print(f"best: exp_{store.best().exp_id} "
              f"(core_metric={store.best().core_metric:.6f})")
        chain = store.chain_to(store.best().exp_id)
        print(f"chain to best: {' -> '.join(f'exp_{t.exp_id}' for t in chain)}")
        print()

        # The portable part — render the prompt a specialist sees at session entry.
        snap = store.render_prompt(
            for_specialist="tok",
            top_k=10,
            recent_n=10,
            last_m_full=3,
            session_timestamp="2026-05-11T11:00:00Z",
        )
        print("=== rendered prompt (what the next specialist reads) ===")
        print(snap.rendered_prompt)


if __name__ == "__main__":
    main()
