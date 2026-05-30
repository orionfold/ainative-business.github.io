"""Publish Orionfold/hermes-brain-bench-v0.1 to HuggingFace.

Modeled on `scripts/publish_patent_bench.py`. Default mode is `--dry-run`:
rebuilds the staging dir (via `build_hf_hermes_brain_bench.py`), validates the
staged tree, prints exactly what WOULD be uploaded, and stops. Use `--push` to
actually upload.

The bench is small (~150 KB total: README, prompts, scratch, 3 scorecards) —
no LFS, no retries needed — so this script uses `HfApi.upload_folder` rather
than the `upload_large_folder` pattern reserved for multi-GB model pushes.

HF auth: reads `HF_TOKEN` from `/home/nvidia/ainative-business.github.io/.env.local`.

Usage:
  # Dry run (default — recommended first call):
  python scripts/publish_hermes_brain_bench.py

  # Actual push:
  python scripts/publish_hermes_brain_bench.py --push

  # Personal-namespace smoke test before Orionfold:
  python scripts/publish_hermes_brain_bench.py --push \
      --repo-id YOUR_USER/hermes-brain-bench-v0.1-test
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

STAGE_DIR = Path("/tmp/hf-stage/hermes-brain-bench-v0.1")
DEFAULT_REPO_ID = "Orionfold/hermes-brain-bench-v0.1"
ENV_LOCAL = Path("/home/nvidia/ainative-business.github.io/.env.local")
BUILD_SCRIPT = Path(__file__).parent / "build_hf_hermes_brain_bench.py"


def load_hf_token() -> str | None:
    if "HF_TOKEN" in os.environ:
        return os.environ["HF_TOKEN"]
    if not ENV_LOCAL.exists():
        return None
    for line in ENV_LOCAL.read_text().splitlines():
        line = line.strip()
        if line.startswith("HF_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def show_plan(repo_id: str, args) -> None:
    print(f"Plan: upload `{STAGE_DIR}` → `{repo_id}` (repo_type=dataset)")
    print()
    print(f"Files to push:")
    total_bytes = 0
    file_count = 0
    for path in sorted(STAGE_DIR.rglob("*")):
        if path.is_file():
            rel = path.relative_to(STAGE_DIR)
            size = path.stat().st_size
            total_bytes += size
            file_count += 1
            print(f"  {rel}  ({size:,} bytes)")
    print()
    print(f"  Total: {file_count} files, {total_bytes:,} bytes ({total_bytes / 1024:.1f} KB)")
    print()
    if args.push:
        print("Mode: --push (will upload)")
    else:
        print("Mode: dry-run — no upload. Re-run with --push to publish.")


def push(repo_id: str, token: str, args) -> int:
    from huggingface_hub import HfApi, create_repo

    api = HfApi(token=token)

    # create_repo with exist_ok=True is idempotent
    print(f"\nEnsuring repo `{repo_id}` exists (creating if needed)...")
    info = create_repo(
        repo_id=repo_id,
        token=token,
        repo_type="dataset",
        exist_ok=True,
        private=args.private,
    )
    print(f"  repo URL: {info.url}")

    print(f"\nUploading staging dir → `{repo_id}` ...")
    commit_info = api.upload_folder(
        folder_path=str(STAGE_DIR),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=args.commit_message,
        token=token,
    )
    print(f"\nDONE.")
    print(f"  commit: {commit_info.commit_url}")
    print(f"  HF dataset: https://huggingface.co/datasets/{repo_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--push", action="store_true", help="Actually upload (default: dry-run)"
    )
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_REPO_ID,
        help=f"Target HF repo id (default: {DEFAULT_REPO_ID})",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Create the repo private (default: public)",
    )
    parser.add_argument(
        "--commit-message",
        default=(
            "v0.1 — initial release: 10-prompt graded-rubric agent-brain "
            "eval + 3 reference-lane scorecards (N=5) for Spark"
        ),
        help="Commit message for the upload",
    )
    parser.add_argument(
        "--skip-rebuild",
        action="store_true",
        help="Trust the existing /tmp/hf-stage tree; don't re-run the build",
    )
    args = parser.parse_args()

    if not args.skip_rebuild:
        print(f"Rebuilding staging dir via {BUILD_SCRIPT.name}...")
        env = os.environ.copy()
        # Per reference_hf_cache_path_on_spark, ~/.cache/huggingface is
        # root-owned; redirect the cache before the build's `datasets`
        # validation call hits it.
        env.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
        env.setdefault("HF_HUB_CACHE", "/home/nvidia/data/.hf-cache/hub")
        env.setdefault("HF_DATASETS_CACHE", "/home/nvidia/data/.hf-cache/datasets")
        rc = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)], check=False, env=env
        ).returncode
        if rc != 0:
            print(f"ERROR: build script failed with rc={rc}", file=sys.stderr)
            return rc
        print()

    if not STAGE_DIR.exists():
        print(
            f"ERROR: staging dir {STAGE_DIR} missing — run build_hf_hermes_brain_bench.py first",
            file=sys.stderr,
        )
        return 2

    show_plan(args.repo_id, args)

    if not args.push:
        return 0

    token = load_hf_token()
    if not token:
        print(
            "\nERROR: HF_TOKEN not found in env or .env.local — cannot push",
            file=sys.stderr,
        )
        print(
            "  Add `HF_TOKEN=hf_xxx` to /home/nvidia/ainative-business.github.io/.env.local",
            file=sys.stderr,
        )
        return 3

    return push(args.repo_id, token, args)


if __name__ == "__main__":
    sys.exit(main())
