#!/usr/bin/env python3
"""Score a GGUF variant served by llama-server on the astro held-out set.

Quant-fidelity gate (dogfood AF-13): hits an OpenAI-compatible llama-server
lane, extracts the `\\boxed{}` answer, and scores it with the local
`astro_numeric_match` reward — the same verifier the corpus/RLVR used. Writes a
per-variant fidelity report next to the GGUFs.

Usage: score_gguf_lane.py --variant Q6_K --url http://127.0.0.1:8088 \
         --heldout evidence/astrodynamics/astro-bench-v0.1.heldout.jsonl \
         --out /home/nvidia/data/quants/Kepler/q6-fidelity-heldout.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verifier import astro_numeric_match, extract_boxed  # noqa: E402


def ask(
    url: str,
    prompt: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> tuple[str, str, int]:
    payload: dict = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 2048,
    }
    if model:  # local llama-server ignores model; OpenRouter requires it
        payload["model"] = model
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers=headers,
    )
    d = json.load(urllib.request.urlopen(req, timeout=300))
    c = d["choices"][0]
    return (
        c["message"]["content"] or "",
        c.get("finish_reason", ""),
        d.get("usage", {}).get("completion_tokens", 0),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, help="label for the lane (e.g. Q8_0, qwen3-8b-stock)")
    ap.add_argument("--url", default="http://127.0.0.1:8088")
    ap.add_argument("--model", default=None, help="model id (required for OpenRouter)")
    ap.add_argument("--api-key-env", default=None, help="env var holding the bearer key")
    ap.add_argument("--heldout", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--baseline", type=float, default=0.8636)
    args = ap.parse_args()
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    if args.api_key_env and not api_key:
        sys.exit(f"env {args.api_key_env} is unset")

    rows = [json.loads(line) for line in open(args.heldout)]
    n = len(rows)
    boxed = reward = trunc = 0
    toks: list[int] = []
    misses: list[str] = []
    for i, r in enumerate(rows):
        comp, fin, t = ask(args.url, r["prompt"], model=args.model, api_key=api_key)
        toks.append(t)
        has_box = extract_boxed(comp) is not None
        sc = astro_numeric_match(comp, r["answer"], rel_tolerance=r.get("rel_tol", 0.02))
        boxed += has_box
        reward += sc == 1.0
        trunc += fin == "length"
        if sc != 1.0:
            misses.append(r["subtopic"])
        print(f"{i + 1:2d}/{n} {r['subtopic']:28s} box={'Y' if has_box else 'n'} rew={int(sc)} tok={t}")

    report = {
        "variant": args.variant,
        "n": n,
        "boxed_rate": boxed / n,
        "reward_rate": reward / n,
        "truncation_rate": trunc / n,
        "mean_tokens": sum(toks) / n,
        "hf_bf16_baseline": args.baseline,
        "misses": misses,
    }
    json.dump(report, open(args.out, "w"), indent=2)
    print(f"\n===== KEPLER {args.variant} GGUF — {n}-row held-out =====")
    print(f"boxed : {boxed}/{n} = {100 * boxed / n:.2f}%")
    print(f"reward: {reward}/{n} = {100 * reward / n:.2f}%   (HF bf16 = {100 * args.baseline:.2f}%)")
    print(f"trunc : {trunc}/{n}   mean tok {sum(toks) / n:.0f}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
