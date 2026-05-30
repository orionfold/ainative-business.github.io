# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.training` — WeightDeltaTracker and
LoraReferenceSnapshot. Tests are guarded with ``importorskip("torch")``
so the suite skips cleanly when torch isn't installed (e.g., a pure
inference dev env).
"""

from __future__ import annotations

from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
nn = pytest.importorskip("torch.nn")

from fieldkit.training import LoraReferenceSnapshot, WeightDeltaTracker  # noqa: E402


def _make_tiny_model(*, requires_grad: bool = True) -> nn.Module:
    """Two-linear-layer module; both weights mark requires_grad by request."""
    model = nn.Sequential(nn.Linear(4, 8, bias=False), nn.Linear(8, 2, bias=False))
    for p in model.parameters():
        p.requires_grad_(requires_grad)
    return model


# --- WeightDeltaTracker --------------------------------------------------


class TestWeightDeltaTracker:
    def test_no_step_zero_delta(self) -> None:
        model = _make_tiny_model()
        tracker = WeightDeltaTracker(model)
        l2, max_abs = tracker.delta()
        assert l2 == pytest.approx(0.0, abs=1e-7)
        assert max_abs == pytest.approx(0.0, abs=1e-7)
        # Captures both linear layers' weight tensors.
        assert len(tracker) == 2

    def test_one_step_nonzero_delta(self) -> None:
        model = _make_tiny_model()
        tracker = WeightDeltaTracker(model)
        # Manual perturbation.
        with torch.no_grad():
            for p in model.parameters():
                p.add_(torch.full_like(p, 0.01))
        l2, max_abs = tracker.delta()
        assert l2 > 0.0
        # max|Δ| should equal exactly 0.01 since we added a constant.
        assert max_abs == pytest.approx(0.01, abs=1e-6)

    def test_inference_mode_yields_empty_snapshot(self) -> None:
        model = _make_tiny_model(requires_grad=False)
        tracker = WeightDeltaTracker(model)
        assert len(tracker) == 0
        l2, max_abs = tracker.delta()
        assert l2 == 0.0
        assert max_abs == 0.0

    def test_l2_norm_against_known_value(self) -> None:
        model = _make_tiny_model()
        tracker = WeightDeltaTracker(model)
        # Add 0.1 to every weight; L2 = sqrt(sum((0.1)^2 * n_params)).
        n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        with torch.no_grad():
            for p in model.parameters():
                p.add_(torch.full_like(p, 0.1))
        l2, _ = tracker.delta()
        expected = (n_params * 0.01) ** 0.5
        assert l2 == pytest.approx(expected, rel=1e-5)


# --- LoraReferenceSnapshot ----------------------------------------------


class TestLoraReferenceSnapshotInPlace:
    def test_swap_changes_weights_then_restores(self) -> None:
        model = _make_tiny_model()
        # Record pre-swap weights for restore verification.
        pre = {n: p.detach().clone() for n, p in model.named_parameters()}

        snap = LoraReferenceSnapshot(model)
        # Modify model weights AFTER snapshot, to simulate a training step.
        with torch.no_grad():
            for p in model.parameters():
                p.fill_(99.0)
        # Snapshot held the original; swap should put the original back into the model.
        with snap:
            for n, p in model.named_parameters():
                assert torch.allclose(p, pre[n])
        # After exit, model should be back to the post-modification (99.0) values.
        for p in model.parameters():
            assert torch.allclose(p, torch.full_like(p, 99.0))

    def test_nested_swap_raises(self) -> None:
        model = _make_tiny_model()
        snap = LoraReferenceSnapshot(model)
        with snap:
            with pytest.raises(RuntimeError, match="already active"):
                with snap:
                    pass

    def test_len_matches_snapshot_size(self) -> None:
        model = _make_tiny_model()
        snap = LoraReferenceSnapshot(model)
        assert len(snap) == 2  # both linear layers' weights captured

    def test_explicit_snapshot_overrides_capture(self) -> None:
        model = _make_tiny_model()
        # Hand-build a snapshot dict with a single tensor.
        first_name, first_param = next(iter(model.named_parameters()))
        explicit = {first_name: torch.zeros_like(first_param)}
        snap = LoraReferenceSnapshot(model, snapshot=explicit)
        assert len(snap) == 1
        with snap:
            for name, param in model.named_parameters():
                if name == first_name:
                    assert torch.allclose(param, torch.zeros_like(param))


class TestLoraReferenceSnapshotFromDisk:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        model = _make_tiny_model()
        with pytest.raises(FileNotFoundError):
            LoraReferenceSnapshot.from_disk(model, tmp_path / "no-adapter")

    def test_loads_via_key_transform(self, tmp_path: Path) -> None:
        # Real safetensors file. Param names in our tiny model:
        #   "0.weight", "1.weight"
        # Simulate an on-disk adapter that uses "<base>.<adapter>.weight"
        # naming live, with file keys stripping the adapter middle.
        # In our tiny model there's no peft wrapper, so file keys are
        # just "0.weight" / "1.weight" and they should match by direct
        # name fallback (no-suffix-match path in the loader).
        safetensors = pytest.importorskip("safetensors.torch")
        model = _make_tiny_model()
        # Construct a tensor dict with model-shaped values (zeros).
        zeros = {
            n: torch.zeros_like(p) for n, p in model.named_parameters()
        }
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        safetensors.save_file(zeros, str(adapter_dir / "adapter_model.safetensors"))

        # Set live weights to non-zero; load should bring zeros into snapshot.
        with torch.no_grad():
            for p in model.parameters():
                p.fill_(7.0)

        snap = LoraReferenceSnapshot.from_disk(model, adapter_dir)
        assert len(snap) == 2

        with snap:
            for p in model.parameters():
                assert torch.allclose(p, torch.zeros_like(p))
        # Restore returns to 7.0.
        for p in model.parameters():
            assert torch.allclose(p, torch.full_like(p, 7.0))

    def test_silently_skips_unmatched_file_keys(self, tmp_path: Path) -> None:
        # File has tensors that don't correspond to the live model.
        safetensors = pytest.importorskip("safetensors.torch")
        model = _make_tiny_model()
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        safetensors.save_file(
            {"unrelated.weight": torch.zeros(2, 2)},
            str(adapter_dir / "adapter_model.safetensors"),
        )

        snap = LoraReferenceSnapshot.from_disk(model, adapter_dir)
        # No live param matched any file key → empty snapshot, no crash.
        assert len(snap) == 0

    def test_adapter_name_suffix_transform(self, tmp_path: Path) -> None:
        # Build a model with a parameter name that mimics peft's naming:
        # base_model.layers.0.lora_A.default.weight → file key
        # base_model.layers.0.lora_A.weight (peft strips "<adapter_name>")
        safetensors = pytest.importorskip("safetensors.torch")

        class FakePeftModule(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                # Live name: <prefix>.default.weight ; file key: <prefix>.weight
                self.adapter_default_weight = nn.Parameter(torch.ones(3, 3))

            def named_parameters(  # type: ignore[override]
                self, *args, **kwargs
            ):
                # Yield it under a peft-style hierarchical name.
                yield ("base_model.layers.0.lora_A.default.weight",
                       self.adapter_default_weight)

        model = FakePeftModule()
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        # File contains the stripped name.
        safetensors.save_file(
            {"base_model.layers.0.lora_A.weight": torch.zeros(3, 3)},
            str(adapter_dir / "adapter_model.safetensors"),
        )
        snap = LoraReferenceSnapshot.from_disk(model, adapter_dir, adapter_name="default")
        assert len(snap) == 1
