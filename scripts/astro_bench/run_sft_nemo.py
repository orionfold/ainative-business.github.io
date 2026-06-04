"""Drive the astrodynamics SFT-init via fieldkit.training (NeMo p65) — C2(b), AV-5.

The spec-faithful path: TrainRecipe(backend="nemo") -> run() -> merge_and_export().
Runs on the HOST (fieldkit.training orchestration is torch-free; it docker-execs
into the `nemo-train` container). Prereqs (handled outside this script):
  - container `nemo-train` UP (nvcr.io/nvidia/nemo:26.04.00, /home/nvidia mounted)
  - <output_dir>/mcore-base  (p65_convert_hf_to_mcore.py — done)
  - <output_dir>/dataset/{training,validation}.jsonl  (sft_to_nemo.py — done)

Modes:
  smoke  -> run(recipe, mode="smoke")  synchronous 10-iter sanity (blocks)
  full   -> run(recipe, mode="full")   synchronous full run (blocks; launch in bg)
  merge  -> merge_and_export(recipe)   -> <output_dir>/merged-hf-bf16 = FK_RL_ADAPTER_INIT

NB the NeMo p65 train script owns seq_length/lora/lr/batch knobs (the recipe
does not forward them for the nemo backend); the recipe drives base_model,
dataset, output_dir, max_steps (--train-iters) and smoke_steps (--smoke).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fieldkit" / "src"))

from fieldkit.training import TrainRecipe  # noqa: E402
from fieldkit.training.run import run, merge_and_export  # noqa: E402

BASE_SNAP = (
    "/home/nvidia/data/.hf-cache-astro/models--Qwen--Qwen3-8B/"
    "snapshots/b968826d9c46dd6066d109eabc6255188de91218"
)
OUTPUT_DIR = "/home/nvidia/data/astro-train-lora/p65-nemo"


def make_recipe() -> TrainRecipe:
    return TrainRecipe(
        base_model=BASE_SNAP,
        dataset_jsonl=f"{OUTPUT_DIR}/dataset/training.jsonl",
        output_dir=OUTPUT_DIR,
        backend="nemo",
        # 540 train rows / global_batch 16 ~= 34 iters/epoch.
        # 100 iters ~= 2.9 epochs — format-conditioning SFT, no overfit.
        max_steps=100,
        smoke_steps=10,
        save_interval=25,   # checkpoints at 25/50/75/100
        most_recent_k=-1,   # keep all so the held-out gate can pick best
        seed=42,
        notes="astrodynamics SFT-init (C2b, AV-5) — Qwen3-8B + 600-row CoT corpus",
    )


def _progress(latest: int, iters: list[int]) -> None:
    print(f"[poll] latest_iter={latest} iter_dirs={iters}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["smoke", "full", "merge"])
    args = ap.parse_args()

    recipe = make_recipe()
    recipe.validate()

    if args.mode == "merge":
        # Qwen3 tokenizer: remap NeMo's "TokenizersBackend" -> Qwen2Tokenizer
        # (the DeepSeek default would wrongly stamp LlamaTokenizer).
        res = merge_and_export(
            recipe,
            tokenizer_class_remap={"TokenizersBackend": "Qwen2Tokenizer"},
        )
        print(f"[merge] merged_hf_dir={res.merged_hf_dir}  (= FK_RL_ADAPTER_INIT)")
        print(f"[merge] source_iter={res.source_iter} standardize_applied={res.standardize_applied}")
        print(f"[merge] shard_renames={res.shard_renames} tokenizer_class_remapped={res.tokenizer_class_remapped}")
        return 0

    mode = "smoke" if args.mode == "smoke" else "full"
    result = run(recipe, mode=mode, poll_interval=30.0, on_progress=_progress)
    print(f"[{mode}] backend={result.backend} run_dir={result.run_dir}")
    print(f"[{mode}] final_iter={result.final_iter} wall_s={result.wall_seconds:.1f}")
    print(f"[{mode}] iter_dirs={result.iter_dirs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
