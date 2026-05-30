#!/usr/bin/env python3
"""hf-publisher — resilient sequential push for already-staged Orionfold artifacts.

Replaces hf_push.py's `upload_folder()` call with `upload_large_folder()`. The
upstream API:

  - splits the push into many small per-file tasks (hash → LFS pre-upload → commit)
  - persists task state in `<stage>/.cache/.huggingface/` so re-runs resume cleanly
  - retries each task indefinitely on transient errors (httpx.RemoteProtocolError,
    ConnectionError, server 5xx, etc.) — the kind of error that crashed the
    Saul-7B push on 2026-05-14 mid-F16 chunk
  - takes `num_workers`, which on slower connections HF explicitly recommends
    setting low: "partially uploaded files will have to be completely re-uploaded
    if the process is interrupted." Spark measured upstream ≈ 38 Mbit/s (4.77 MB/s)
    via speedtest-cli — the Spark IS the slower-connection case.

Behavior delta vs hf_push.py:

  - num_workers=1 by default — strictly one file at a time, full bandwidth per file
  - emits the same `=== PUSH COMPLETE` / `hf_url:` / `public URL:` sentinels so
    the existing hf-publisher monitor terminal-state grep keeps working
  - on partial failures, prints a `=== PUSH PARTIAL` line and exits non-zero so
    a re-run is the obvious next step (resume picks up from .cache/.huggingface/)

Required env (same as hf_push.py):
  REPO_NAME    HuggingFace repo name without org prefix
  STAGE_DIR    Absolute path to the dry-run-produced stage

Optional env:
  NUM_WORKERS      Default 1 (strict sequential). Raise to 2-4 to trade
                   resumability for throughput on stable networks.
  PRINT_EVERY      Progress-report cadence in seconds (default 30).
  PRIVATE          `1` for private repo (default `0` = public).
  COMMIT_MESSAGE   Used as the prefix; upload_large_folder may produce many
                   commits, each suffixed automatically by the SDK.
  HF_HOME          Defaults to `/home/nvidia/data/.hf-cache` (xet-safety).
  HF_HUB_DISABLE_XET   Defaults to `1` — same reason as hf_push.py.

Reads HF_TOKEN from /home/nvidia/ainative-business.github.io/.env.local.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

ENV_LOCAL = Path("/home/nvidia/ainative-business.github.io/.env.local")


def _load_env_local() -> None:
    if not ENV_LOCAL.exists():
        return
    for raw in ENV_LOCAL.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    repo_name = os.environ.get("REPO_NAME")
    stage_dir_str = os.environ.get("STAGE_DIR")
    if not repo_name:
        print("ERROR: REPO_NAME env var required", file=sys.stderr)
        return 2
    if not stage_dir_str:
        print("ERROR: STAGE_DIR env var required", file=sys.stderr)
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
        print(f"ERROR: {stage_dir}/README.md missing — run dry-run first", file=sys.stderr)
        return 2

    num_workers = int(os.environ.get("NUM_WORKERS", "1"))
    print_every = int(os.environ.get("PRINT_EVERY", "30"))
    private = os.environ.get("PRIVATE", "0") in ("1", "true", "True")
    commit_message = os.environ.get(
        "COMMIT_MESSAGE",
        f"Initial Orionfold release — {repo_name} (Spark-tested measurement quad).",
    )

    from huggingface_hub import HfApi
    from huggingface_hub.utils import HfHubHTTPError

    repo_id = f"Orionfold/{repo_name}"
    token = os.environ["HF_TOKEN"]
    api = HfApi(token=token)

    files = sorted(
        str(p.relative_to(stage_dir))
        for p in stage_dir.rglob("*")
        if p.is_file() and not p.is_relative_to(stage_dir / ".cache")
    )
    total_bytes = sum((stage_dir / f).stat().st_size for f in files)
    total_gb = total_bytes / (1024 ** 3)

    # Resume signal — if .cache/.huggingface/ exists with prior task state,
    # this run will pick up where the last one left off.
    cache_dir = stage_dir / ".cache" / ".huggingface"
    resuming = cache_dir.exists() and any(cache_dir.iterdir())

    visibility = "PRIVATE" if private else "public"
    print(f"Pushing {stage_dir} → {repo_id} ({visibility})")
    print(f"Files staged: {len(files)} ({total_gb:.2f} GB total)")
    print(f"Workers: {num_workers}  ·  Progress every: {print_every}s")
    print(f"Resume cache: {'YES (picking up prior progress)' if resuming else 'fresh push'}")
    for f in files:
        size_gb = (stage_dir / f).stat().st_size / (1024 ** 3)
        if size_gb > 0.01:
            print(f"  {f}  ({size_gb:.2f} GB)")
        else:
            print(f"  {f}")
    print()

    # Spark measured upstream is ~4.77 MB/s; ETA = bytes / rate / 60.
    eta_minutes = max(1, int(total_bytes / (4.77 * 1024 * 1024) / 60))
    print(f"ETA ~{eta_minutes} min at observed ~4.77 MB/s upstream.")
    print()

    # Ensure repo exists. upload_large_folder doesn't auto-create; failures
    # here are auth or quota issues, not transient.
    try:
        api.create_repo(repo_id=repo_id, repo_type="model", private=private, exist_ok=True)
    except HfHubHTTPError as exc:
        print(f"ERROR creating repo {repo_id}: {exc}", file=sys.stderr)
        return 3

    try:
        api.upload_large_folder(
            repo_id=repo_id,
            folder_path=str(stage_dir),
            repo_type="model",
            num_workers=num_workers,
            print_report=True,
            print_report_every=print_every,
            ignore_patterns=[".cache/**"],
        )
    except KeyboardInterrupt:
        print("\n=== PUSH INTERRUPTED ===")
        print(f"Cache preserved at {cache_dir} — re-run this script to resume.")
        return 4
    except Exception as exc:  # noqa: BLE001
        print(f"\n=== PUSH PARTIAL ===")
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Cache preserved at {cache_dir} — re-run this script to resume.")
        return 5

    url = f"https://huggingface.co/{repo_id}"
    print()
    print("=== PUSH COMPLETE ===")
    print(f"hf_repo: {repo_id}")
    print(f"hf_url:  {url}")
    print(f"public URL: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
