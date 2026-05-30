#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Run a NIM (OpenAI-compatible) endpoint against the routing bench queue.

Reads queue.jsonl, POSTs each prompt to /v1/chat/completions, appends one
JSONL row per response. Same output schema as bench_local_vs_cc_ollama.py
so the renderer can join them by row_idx.

Default base-url targets the standard NIM port (8000). Override with
--base-url for a different container. The script fails loudly if the
endpoint isn't reachable.

Usage:
  python bench_local_vs_cc_nim.py --model nvidia/nemotron-nano-9b-v2
  python bench_local_vs_cc_nim.py --model meta/llama-3.1-8b-instruct \\
      --base-url http://localhost:8000/v1 \\
      --queue /tmp/aifn-bench-local-vs-cc/queue.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

THINK_RE = re.compile(r"<think>(.*?)</think>(.*)", re.DOTALL)


def parse_think(text: str) -> tuple[str, str, bool]:
    m = THINK_RE.search(text)
    if m:
        return m.group(1).strip(), m.group(2).strip(), True
    return "", text.strip(), False


def call_nim(
    base_url: str,
    model: str,
    prompt: str,
    system: str | None,
    max_tokens: int,
    timeout: int,
    api_key: str | None,
) -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode(),
        headers=headers,
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read())
    wall = time.monotonic() - t0
    choice = payload.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content", "")
    usage = payload.get("usage", {})
    return {
        "content": content,
        "wall_s": round(wall, 2),
        "prompt_tok": usage.get("prompt_tokens"),
        "output_tok": usage.get("completion_tokens"),
        "finish_reason": choice.get("finish_reason"),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model",
        required=True,
        help="NIM model name, e.g. nvidia/nemotron-nano-9b-v2",
    )
    p.add_argument("--base-url", default="http://localhost:8000/v1")
    p.add_argument(
        "--queue", default="/tmp/aifn-bench-local-vs-cc/queue.jsonl"
    )
    p.add_argument(
        "--output",
        default=None,
        help="Default: /tmp/.../out-nim-<model-slug>.jsonl",
    )
    p.add_argument(
        "--system",
        default=None,
        help="Optional system prompt (e.g. '/think' for Nemotron toggle)",
    )
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument(
        "--api-key",
        default=None,
        help="Optional bearer token (local NIM usually unauthenticated)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    queue_path = Path(args.queue)
    if not queue_path.exists():
        print(f"ERROR: queue not found at {queue_path}", file=sys.stderr)
        print("Run bench_local_vs_cc_prepare.py first.", file=sys.stderr)
        return 2

    if args.output is None:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", args.model).strip("-").lower()
        out_path = queue_path.parent / f"out-nim-{slug}.jsonl"
    else:
        out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [json.loads(line) for line in queue_path.read_text().splitlines() if line]
    print(f"queue={queue_path} rows={len(rows)} model={args.model}")
    print(f"base_url={args.base_url} output={out_path}")

    with open(out_path, "w") as fh:
        for row in rows:
            try:
                resp = call_nim(
                    args.base_url,
                    args.model,
                    row["prompt"],
                    args.system,
                    args.max_tokens,
                    args.timeout,
                    args.api_key,
                )
            except urllib.error.URLError as e:
                print(
                    f"ERROR row {row['row_idx']}: {e} — is the NIM container "
                    f"running at {args.base_url}?",
                    file=sys.stderr,
                )
                return 3
            think, answer, has_think = parse_think(resp["content"])
            out = {
                "row_idx": row["row_idx"],
                "family": row["family"],
                "backend": "nim",
                "model": args.model,
                "think": think,
                "answer": answer,
                "has_think": has_think,
                "wall_s": resp["wall_s"],
                "prompt_tok": resp["prompt_tok"],
                "output_tok": resp["output_tok"],
                "finish_reason": resp["finish_reason"],
            }
            fh.write(json.dumps(out) + "\n")
            fh.flush()
            mark = "OK" if has_think else "NO-THINK"
            print(
                f"  [{row['row_idx']:>2}] {row['family']} "
                f"{mark} wall={resp['wall_s']}s tok={resp['output_tok']}"
            )

    n_think = sum(1 for line in out_path.read_text().splitlines() if json.loads(line)["has_think"])
    print(f"DONE: {n_think}/{len(rows)} rows with <think> block")
    return 0


if __name__ == "__main__":
    sys.exit(main())
