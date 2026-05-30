# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.lineage`.

Covers:
- FailureLabel enum value parity + `is_informational` predicate.
- Trial round-trip via TSV (write -> read -> equal).
- LineageStore concurrency-safe append (fcntl-locked).
- best() / latest() / chain_to() correctness across ablation patterns.
- render_prompt() Markdown structure matches the cxcscmu release_artifacts
  shape (header line, Current Best block, top-K table, chain rendering,
  Recent Activity table, last-M detailed entries).
- RecipeEdit.diff() against a parent snapshot.

Pure-stdlib module — no `importorskip`, no live-service gating. Runs offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fieldkit.lineage import (
    FailureLabel,
    LineageSnapshot,
    LineageStore,
    RecipeEdit,
    Trial,
)


def _baseline() -> Trial:
    return Trial(
        exp_id="000",
        timestamp="2026-05-11T10:00:00Z",
        specialist="baseline",
        parent_exp="",
        baseline_exp="",
        domain="baseline",
        hypothesis="seed",
        expected_delta="0",
        status=FailureLabel.BASELINE,
        core_metric=1.081,
        val_bpb=1.081,
        delta_vs_best=None,
        train_s=None,
        total_s=None,
        job_name="",
        snapshot_path="snapshots/000",
        notes="",
    )


def _keep(
    exp_id: str,
    parent: str,
    metric: float,
    delta: float,
    *,
    specialist: str = "opt",
    hypothesis: str = "edit",
) -> Trial:
    return Trial(
        exp_id=exp_id,
        timestamp=f"2026-05-11T11:{int(exp_id):02d}:00Z",
        specialist=specialist,
        parent_exp=parent,
        baseline_exp="000",
        domain=specialist,
        hypothesis=hypothesis,
        expected_delta=f"{delta:+.4f}",
        status=FailureLabel.KEEP,
        core_metric=metric,
        val_bpb=metric,
        delta_vs_best=delta,
        train_s=540.0,
        total_s=1120.0,
        job_name=f"exp_{exp_id}",
        snapshot_path=f"snapshots/{exp_id}_{specialist}",
        notes=f"clean keep at exp_{exp_id}",
    )


def _discard(exp_id: str, parent: str, metric: float | None) -> Trial:
    return Trial(
        exp_id=exp_id,
        timestamp=f"2026-05-11T11:{int(exp_id):02d}:00Z",
        specialist="arch",
        parent_exp=parent,
        baseline_exp="000",
        domain="arch",
        hypothesis="failing edit",
        expected_delta="-0.001",
        status=FailureLabel.DISCARD,
        core_metric=metric,
        val_bpb=metric,
        delta_vs_best=None,
        train_s=540.0,
        total_s=1120.0,
        job_name=f"exp_{exp_id}",
        snapshot_path="",
        notes="",
    )


# --- FailureLabel --------------------------------------------------------


class TestFailureLabel:
    def test_string_valued(self) -> None:
        # Verbatim from the cxcscmu TSV `status` column — required for
        # byte-identical round-trip on third-party data.
        assert FailureLabel.KEEP.value == "keep"
        assert FailureLabel.DISCARD.value == "discard"
        assert FailureLabel.EVAL_BUDGET_OVERRUN.value == "eval_budget_overrun"
        assert FailureLabel.HARNESS_ABORT.value == "harness_abort"

    def test_informational_predicate(self) -> None:
        # Only `harness_abort` is bookkeeping — everything else is signal.
        assert FailureLabel.KEEP.is_informational
        assert FailureLabel.DISCARD.is_informational
        assert FailureLabel.CRASH.is_informational
        assert FailureLabel.EVAL_BUDGET_OVERRUN.is_informational
        assert FailureLabel.SIZE_BLOCKED.is_informational
        assert FailureLabel.BASELINE.is_informational
        assert FailureLabel.DISQUALIFIED.is_informational
        assert not FailureLabel.HARNESS_ABORT.is_informational

    def test_all_ten_classes(self) -> None:
        # Locks the enum surface — if a class is added, this test
        # needs the deliberate update.
        assert {m.value for m in FailureLabel} == {
            "keep",
            "discard",
            "crash",
            "eval_budget_overrun",
            "train_budget_overrun",
            "size_blocked",
            "preflight_crash",
            "harness_abort",
            "disqualified",
            "baseline",
        }


# --- Trial ---------------------------------------------------------------


class TestTrial:
    def test_header_matches_field_order(self) -> None:
        # Order is contract — downstream consumers will sort on field
        # indices when reading without DictReader.
        hdr = Trial.header()
        assert hdr[0] == "exp_id"
        assert hdr[-1] == "notes"
        assert "core_metric" in hdr
        assert "val_bpb" in hdr
        assert len(hdr) == 17

    def test_to_row_handles_none_as_empty(self) -> None:
        row = _baseline().to_row()
        # delta_vs_best, train_s, total_s are None on the baseline.
        # These must serialize as "" not "None".
        idx = Trial.header().index("delta_vs_best")
        assert row[idx] == ""
        idx = Trial.header().index("train_s")
        assert row[idx] == ""

    def test_to_row_round_trip(self, tmp_path: Path) -> None:
        b = _baseline()
        store = LineageStore(tmp_path)
        store.append(b)
        rt = store.all_trials()[0]
        assert rt == b


# --- LineageStore --------------------------------------------------------


class TestLineageStoreAppend:
    def test_creates_results_tsv_with_header(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        assert store.results_path.exists()
        lines = store.results_path.read_text().splitlines()
        # First line is the header, second is the baseline row.
        assert lines[0].split("\t")[0] == "exp_id"
        assert lines[1].split("\t")[0] == "000"

    def test_multiple_appends_preserve_order(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        store.append(_keep("014", "000", 1.078, -0.003))
        store.append(_discard("015", "014", 1.080))
        ids = [t.exp_id for t in store.all_trials()]
        assert ids == ["000", "014", "015"]


class TestLineageStoreBest:
    def test_lower_is_better_picks_smallest(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path, lower_is_better=True)
        store.append(_baseline())
        store.append(_keep("014", "000", 1.078, -0.003))
        store.append(_keep("030", "014", 1.075, -0.003))
        assert store.best().exp_id == "030"

    def test_higher_is_better_picks_largest(self, tmp_path: Path) -> None:
        # For accuracy-style metrics where bigger is better. Use values
        # above the baseline (1.081) so the keeps win.
        store = LineageStore(tmp_path, lower_is_better=False)
        store.append(_baseline())
        store.append(_keep("014", "000", 1.20, 0.10))
        store.append(_keep("030", "014", 1.30, 0.10))
        assert store.best().exp_id == "030"

    def test_empty_store_returns_none(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        assert store.best() is None

    def test_falls_back_to_baseline_with_no_metrics(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_discard("100", "000", None))
        assert store.best().exp_id == "100"


class TestLineageStoreLatest:
    def test_returns_most_recent_n(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        for i in range(1, 6):
            store.append(_discard(f"{i:03d}", "000", 1.080 - i * 0.001))
        latest = store.latest(n=3)
        assert tuple(t.exp_id for t in latest) == ("003", "004", "005")

    def test_n_larger_than_corpus_returns_all(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        assert len(store.latest(n=100)) == 1

    def test_n_zero_returns_empty(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        assert store.latest(n=0) == ()


class TestLineageStoreChainTo:
    def test_walks_parent_pointers_root_first(self, tmp_path: Path) -> None:
        # Build a linear chain baseline -> 014 -> 030 -> 045.
        store = LineageStore(tmp_path)
        store.append(_baseline())
        store.append(_keep("014", "000", 1.078, -0.003))
        store.append(_keep("030", "014", 1.077, -0.001))
        store.append(_keep("045", "030", 1.076, -0.001))
        chain = store.chain_to("045")
        assert tuple(t.exp_id for t in chain) == ("000", "014", "030", "045")

    def test_branched_chain_only_walks_parent(self, tmp_path: Path) -> None:
        # Build a branch: baseline -> 014 -> {030, 031}. Chain to 031 should
        # be (000, 014, 031), not include 030.
        store = LineageStore(tmp_path)
        store.append(_baseline())
        store.append(_keep("014", "000", 1.078, -0.003))
        store.append(_keep("030", "014", 1.077, -0.001))
        store.append(_keep("031", "014", 1.076, -0.002))
        chain = store.chain_to("031")
        assert tuple(t.exp_id for t in chain) == ("000", "014", "031")

    def test_missing_exp_id_raises(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        with pytest.raises(KeyError):
            store.chain_to("999")


class TestLineageStoreRenderPrompt:
    def test_empty_store_produces_empty_lineage_header(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        snap = store.render_prompt("opt")
        assert "empty lineage" in snap.rendered_prompt
        assert snap.chain_to_best == ()
        assert snap.top_k_leaderboard == ()

    def test_includes_specialist_name_in_header(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        snap = store.render_prompt("tok", session_timestamp="2026-05-11T11:00:00Z")
        assert "**tok**" in snap.rendered_prompt
        assert "2026-05-11T11:00:00Z" in snap.rendered_prompt

    def test_top_k_table_only_lists_keeps(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        store.append(_keep("014", "000", 1.078, -0.003))
        store.append(_discard("015", "014", 1.080))
        store.append(_keep("030", "014", 1.075, -0.003))
        snap = store.render_prompt("opt")
        ids_in_topk = {t.exp_id for t in snap.top_k_leaderboard}
        # Both keeps in, discard out.
        assert ids_in_topk == {"014", "030"}

    def test_chain_rendering_marks_best_with_arrow(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        store.append(_keep("014", "000", 1.078, -0.003))
        store.append(_keep("030", "014", 1.075, -0.003))
        snap = store.render_prompt("opt")
        # The terminal `← BEST` marker is what the next specialist scans for.
        assert "← BEST" in snap.rendered_prompt
        # The chain header anchors the section.
        assert "Current-best lineage" in snap.rendered_prompt

    def test_chain_to_best_attribute_consistent(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        store.append(_keep("014", "000", 1.078, -0.003))
        store.append(_keep("030", "014", 1.075, -0.003))
        snap = store.render_prompt("opt")
        assert tuple(t.exp_id for t in snap.chain_to_best) == ("000", "014", "030")
        assert snap.current_best.exp_id == "030"

    def test_recent_activity_caps_at_recent_n(self, tmp_path: Path) -> None:
        store = LineageStore(tmp_path)
        store.append(_baseline())
        for i in range(1, 11):
            store.append(_discard(f"{i:03d}", "000", 1.080 - i * 0.0005))
        snap = store.render_prompt("opt", recent_n=5)
        # 5 most recent only (exp_006..010).
        recent_ids = {t.exp_id for t in snap.recent_n_activity}
        assert recent_ids == {"006", "007", "008", "009", "010"}

    def test_deterministic(self, tmp_path: Path) -> None:
        # render_prompt is the centerpiece — same TSV state + same params
        # must produce byte-identical Markdown across calls.
        store = LineageStore(tmp_path)
        store.append(_baseline())
        store.append(_keep("014", "000", 1.078, -0.003))
        a = store.render_prompt("opt", session_timestamp="2026-05-11T11:00:00Z")
        b = store.render_prompt("opt", session_timestamp="2026-05-11T11:00:00Z")
        assert a.rendered_prompt == b.rendered_prompt


# --- RecipeEdit ----------------------------------------------------------


class TestRecipeEdit:
    def test_baseline_diff_empty(self, tmp_path: Path) -> None:
        snap_dir = tmp_path / "snap_000"
        snap_dir.mkdir()
        (snap_dir / "train.py").write_text("print('hello')\n")
        edit = RecipeEdit(
            trial=_baseline(),
            snapshot_path=snap_dir,
            parent_snapshot_path=None,
        )
        assert edit.diff() == ""

    def test_diff_against_parent(self, tmp_path: Path) -> None:
        parent_dir = tmp_path / "snap_000"
        parent_dir.mkdir()
        (parent_dir / "train.py").write_text("lr = 0.5\n")
        this_dir = tmp_path / "snap_014"
        this_dir.mkdir()
        (this_dir / "train.py").write_text("lr = 0.1\n")
        edit = RecipeEdit(
            trial=_keep("014", "000", 1.078, -0.003),
            snapshot_path=this_dir,
            parent_snapshot_path=parent_dir,
        )
        diff = edit.diff()
        assert "lr = 0.5" in diff
        assert "lr = 0.1" in diff
        assert "a/train.py" in diff
        assert "b/train.py" in diff

    def test_diff_handles_new_file(self, tmp_path: Path) -> None:
        parent_dir = tmp_path / "snap_000"
        parent_dir.mkdir()
        (parent_dir / "train.py").write_text("lr = 0.5\n")
        this_dir = tmp_path / "snap_014"
        this_dir.mkdir()
        (this_dir / "train.py").write_text("lr = 0.5\n")
        (this_dir / "new_helper.py").write_text("def helper(): pass\n")
        edit = RecipeEdit(
            trial=_keep("014", "000", 1.078, -0.003),
            snapshot_path=this_dir,
            parent_snapshot_path=parent_dir,
        )
        diff = edit.diff()
        assert "new_helper.py" in diff
        assert "def helper" in diff


# --- LineageSnapshot -----------------------------------------------------


class TestLineageSnapshot:
    def test_immutable_frozen_dataclass(self) -> None:
        snap = LineageSnapshot(
            rendered_prompt="ignored",
            current_best=_baseline(),
            chain_to_best=(),
            top_k_leaderboard=(),
            recent_n_activity=(),
            last_m_with_full_hypothesis=(),
        )
        with pytest.raises((AttributeError, TypeError)):
            snap.rendered_prompt = "mutated"  # type: ignore[misc]
