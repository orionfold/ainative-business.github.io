#!/usr/bin/env python3
"""hf-publisher — flip dry_run=False on an already-staged Orionfold push.

Generalized template (see /home/nvidia/ainative-business.github.io/scripts/g3_push_first_quant.py
for the inaugural-run version). Reuses the existing dry-run staging directory
so the live push doesn't re-copy GGUF bytes — the orchestrator's `shutil.copy2`
on a 32 GB folder is wasted I/O when the stage is already correct.

Required env:
  REPO_NAME    HuggingFace repo name without org prefix, e.g. `finance-chat-GGUF`.
               The push lands at `Orionfold/$REPO_NAME` (the org prefix comes
               from `fieldkit.publish.ORIONFOLD_HF_HANDLE`).
  STAGE_DIR    Absolute path to the dry-run-produced stage (e.g.
               `/tmp/orionfold-stage/finance-chat`). Must contain README.md.

Optional env:
  PRIVATE          `1` to push as private (default `0` = public).
  COMMIT_MESSAGE   Override the default initial-release commit message.
  HF_HOME          Defaults to `/home/nvidia/data/.hf-cache` (xet-safety).
  HF_HUB_DISABLE_XET   Defaults to `1` (Spark-side `~/.cache/huggingface/`
                       is root-owned; xet writes log files there and dies).

Reads HF_TOKEN from /home/nvidia/ainative-business.github.io/.env.local (chmod 600,
gitignored — same shape as PYPI_TOKEN per [[reference_fieldkit_pypi_auth]]).

Output: prints `hf_url:` and `public URL:` lines on success — both anchored
at line-start so the hf-publisher monitor's terminal-state grep catches them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Spark xet-safety — must precede any huggingface_hub import path. The system
# `~/.cache/huggingface/` is root-owned (legacy from a past sudo run); without
# these the Rust xet uploader dies with `Permission denied (os error 13)`
# inside `_upload_xet_files`. Same workaround as g3_build_first_quant.sh.
os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

ENV_LOCAL = Path("/home/nvidia/ainative-business.github.io/.env.local")


def _load_env_local() -> None:
    """Source HF_TOKEN from .env.local without requiring python-dotenv.

    Mirrors the pattern in g3_push_first_quant.py and fieldkit-curator's
    PyPI-token retrieval. Lines with `#` or no `=` are skipped; values may
    be optionally single- or double-quoted.
    """
    if not ENV_LOCAL.exists():
        return
    for raw in ENV_LOCAL.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def main() -> int:
    repo_name = os.environ.get("REPO_NAME")
    stage_dir_str = os.environ.get("STAGE_DIR")
    if not repo_name:
        print("ERROR: REPO_NAME env var required (e.g. `finance-chat-GGUF`)", file=sys.stderr)
        return 2
    if not stage_dir_str:
        print("ERROR: STAGE_DIR env var required (absolute path to dry-run stage)", file=sys.stderr)
        return 2
    stage_dir = Path(stage_dir_str)

    _load_env_local()
    if not os.environ.get("HF_TOKEN"):
        print(f"ERROR: HF_TOKEN not in env or {ENV_LOCAL}", file=sys.stderr)
        return 2
    if not stage_dir.exists():
        print(f"ERROR: STAGE_DIR does not exist: {stage_dir}", file=sys.stderr)
        return 2
    if not (stage_dir / "README.md").exists():
        print(
            f"ERROR: {stage_dir}/README.md missing — run dry-run via"
            " `scripts/g3_build_first_quant.sh publish-dryrun` first",
            file=sys.stderr,
        )
        return 2

    private = os.environ.get("PRIVATE", "0") in ("1", "true", "True")
    commit_message = os.environ.get(
        "COMMIT_MESSAGE",
        f"Initial Orionfold release — {repo_name} (Spark-tested measurement quad).",
    )

    # Lazy import so the env-var-validation errors above print fast.
    from fieldkit.publish import HFHubAdapter

    adapter = HFHubAdapter(staging_dir=stage_dir, dry_run=False)
    files = adapter._enumerate_staged()
    total_bytes = sum((stage_dir / f).stat().st_size for f in files)
    total_gb = total_bytes / (1024 ** 3)

    visibility = "PRIVATE" if private else "public"
    print(f"Pushing {stage_dir} → Orionfold/{repo_name} ({visibility})")
    print(f"Files staged: {len(files)} ({total_gb:.2f} GB total)")
    for f in files:
        size_gb = (stage_dir / f).stat().st_size / (1024 ** 3)
        print(f"  {f}  ({size_gb:.2f} GB)" if size_gb > 0.01 else f"  {f}")
    print()

    # ETA at the observed Spark home-network upstream (~5 MB/s aggregate).
    eta_minutes = max(1, int(total_bytes / (5 * 1024 * 1024) / 60))
    print(f"Starting upload — ETA ~{eta_minutes} min at observed ~5 MB/s aggregate.")
    print("(LFS uploads run in parallel; per-file progress will appear on stderr.)")
    print()

    result = adapter.push_folder(
        repo_name=repo_name,
        commit_message=commit_message,
        private=private,
        repo_type="model",
    )
    print()
    print("=== PUSH COMPLETE ===")
    print(f"hf_repo: {result.hf_repo}")
    print(f"hf_url:  {result.hf_url}")
    print(f"files uploaded: {len(result.files_uploaded)}")
    print(f"public URL: https://huggingface.co/{result.hf_repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
