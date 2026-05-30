#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Run an Ollama model against the local-vs-CC routing bench queue.

Reads queue.jsonl (built by bench_local_vs_cc_prepare.py), POSTs each prompt
to Ollama's /api/chat, appends one JSONL row per response. Tracks wall time
and token counts; parses out the <think> block for downstream scoring.

The Ollama model must already be pulled (`ollama pull qwen3.5:9b` etc.).
The script fails loudly if the daemon isn't reachable — no silent retries.

Usage:
  python bench_local_vs_cc_ollama.py --model qwen3.5:9b
  python bench_local_vs_cc_ollama.py --model deepseek-r1:14b \\
      --base-url http://localhost:11434 \\
      --queue /tmp/aifn-bench-local-vs-cc/queue.jsonl \\
      --output /tmp/aifn-bench-local-vs-cc/out-ollama-deepseek-r1-14b.jsonl
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


def call_ollama(
    base_url: str,
    model: str,
    prompt: str,
    system: str | None,
    num_predict: int,
    timeout: int,
    think: bool,
) -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": think,
        "options": {"num_predict": num_predict},
    }
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read())
    wall = time.monotonic() - t0
    msg = payload.get("message", {})
    return {
        "content": msg.get("content", ""),
        "thinking": msg.get("thinking", ""),
        "wall_s": round(wall, 2),
        "prompt_tok": payload.get("prompt_eval_count"),
        "output_tok": payload.get("eval_count"),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="Ollama tag, e.g. qwen3.5:9b")
    p.add_argument("--base-url", default="http://localhost:11434")
    p.add_argument(
        "--queue", default="/tmp/aifn-bench-local-vs-cc/queue.jsonl"
    )
    p.add_argument(
        "--output",
        default=None,
        help="Default: /tmp/.../out-ollama-<model-slug>.jsonl",
    )
    p.add_argument(
        "--system",
        default=None,
        help="Optional system prompt (e.g. '/think' for Nemotron-style toggle)",
    )
    p.add_argument("--num-predict", type=int, default=2048)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument(
        "--no-think",
        action="store_true",
        help="Disable Ollama's think:true flag (for non-reasoning models)",
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
        out_path = queue_path.parent / f"out-ollama-{slug}.jsonl"
    else:
        out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [json.loads(line) for line in queue_path.read_text().splitlines() if line]
    print(f"queue={queue_path} rows={len(rows)} model={args.model}")
    print(f"output={out_path}")

    with open(out_path, "w") as fh:
        for row in rows:
            try:
                resp = call_ollama(
                    args.base_url,
                    args.model,
                    row["prompt"],
                    args.system,
                    args.num_predict,
                    args.timeout,
                    think=not args.no_think,
                )
            except urllib.error.URLError as e:
                print(
                    f"ERROR row {row['row_idx']}: {e} — is `ollama serve` "
                    f"running at {args.base_url}?",
                    file=sys.stderr,
                )
                return 3
            if resp["thinking"]:
                think, answer = resp["thinking"], resp["content"]
                has_think = True
            else:
                think, answer, has_think = parse_think(resp["content"])
            out = {
                "row_idx": row["row_idx"],
                "family": row["family"],
                "backend": "ollama",
                "model": args.model,
                "think": think,
                "answer": answer,
                "has_think": has_think,
                "wall_s": resp["wall_s"],
                "prompt_tok": resp["prompt_tok"],
                "output_tok": resp["output_tok"],
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
