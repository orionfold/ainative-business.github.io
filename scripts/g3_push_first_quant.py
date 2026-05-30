#!/usr/bin/env python3
"""G3 v0 — flip dry_run=False and actually push the first Orionfold quant.

Reuses the staging dir produced by `scripts/g3_build_first_quant.sh publish-dryrun`
so we don't re-copy 32 GB of GGUF files. The README + manifest were already
rendered + verified by the dry-run; this is the single live HFHubAdapter call
that lifts the staged folder onto HuggingFace.

Defaults match the AdaptLLM/finance-chat → Orionfold/finance-chat-GGUF run.
Override via env vars (REPO_NAME, STAGE_DIR, COMMIT_MESSAGE) if needed.

Reads HF_TOKEN from /home/nvidia/ainative-business.github.io/.env.local (chmod 600,
gitignored). Per memory `reference_fieldkit_pypi_auth` shape.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Workaround for the Spark xet-permission landmine — the system
# `~/.cache/huggingface/` is root-owned (legacy from a past sudo run), so the
# Rust xet uploader explodes with `Permission denied (os error 13)` when it
# tries to write log + cache files. Disabling xet falls back to direct HTTP
# uploads, which work fine. Mirrors `scripts/g3_build_first_quant.sh`.
os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

REPO_NAME = os.environ.get("REPO_NAME", "finance-chat-GGUF")
STAGE_DIR = Path(os.environ.get("STAGE_DIR", "/tmp/orionfold-stage/finance-chat"))
COMMIT_MESSAGE = os.environ.get(
    "COMMIT_MESSAGE",
    "Initial Orionfold release — five GGUF variants of AdaptLLM/finance-chat"
    " with Spark-tested measurement quad (perplexity, tok/s, thermal envelope,"
    " FinanceBench (n=50, numeric_match)).",
)
ENV_LOCAL = Path("/home/nvidia/ainative-business.github.io/.env.local")


def _load_env_local() -> None:
    """Source HF_TOKEN from .env.local without requiring python-dotenv."""
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
    _load_env_local()
    if not os.environ.get("HF_TOKEN"):
        print(f"ERROR: HF_TOKEN not in env or {ENV_LOCAL}", file=sys.stderr)
        return 2
    if not STAGE_DIR.exists():
        print(
            f"ERROR: stage dir missing — run `scripts/g3_build_first_quant.sh"
            f" publish-dryrun` first to populate {STAGE_DIR}",
            file=sys.stderr,
        )
        return 2

    from fieldkit.publish import HFHubAdapter

    adapter = HFHubAdapter(staging_dir=STAGE_DIR, dry_run=False)
    print(f"Pushing {STAGE_DIR} → Orionfold/{REPO_NAME}")
    print(f"Files staged: {len(adapter._enumerate_staged())}")
    for f in adapter._enumerate_staged():
        size_gb = (STAGE_DIR / f).stat().st_size / (1024 ** 3)
        print(f"  {f}  ({size_gb:.2f} GB)" if size_gb > 0.01 else f"  {f}")
    print()
    print("Starting upload — five GGUFs ~32 GB total. Expect 30–90 min.")

    result = adapter.push_folder(
        repo_name=REPO_NAME,
        commit_message=COMMIT_MESSAGE,
        private=False,
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
