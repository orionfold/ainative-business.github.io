#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Offline grounded-eval pack runner — the canonical receipt (grounded-eval-v1 §7).

For each pack row: build the packet LIVE through the Cortex stack
(``fieldkit.arena.cortex_chat.build_packet`` — pgvector + NIM embedder), chat
against the selected lane, score with the deterministic ``grounded_contract``
scorer (the same one the cockpit uses — one scorer path, report = reality),
and write per-run receipts. ``--mode both`` runs the ±Cortex ablation pair in
one harness pass and emits the grounding lift per row + per journey.

Deterministic transform only — no LLM calls beyond the lane under test
(`feedback_llm_skill_pattern`). Cortex down = hard abort, never a silently
ungrounded row scored as grounded.

Usage:
    /tmp/arena-venv/bin/python3 scripts/grounded_eval/run_pack.py \
        [--pack evidence/grounded-eval/cortex-grounded-v0.1.jsonl] \
        [--base-url http://127.0.0.1:8091/v1] [--model <auto from /v1/models>] \
        [--mode retrieval|no-retrieval|both] [--journey lookup] [--limit N] \
        [--max-tokens 1024] [--out evidence/grounded-eval/results/<run>/] [--root .]

Receipts land under ``evidence/grounded-eval/results/<run>/`` (tracked):
``results.jsonl`` (one row per task × mode, with the retrieval receipt) +
``summary.json`` (pass rate overall / per journey / per component / lift).
Interactive cockpit grades are a convenience; THESE files are the receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

_COMPONENT_RES = {
    "retrieval_hit": re.compile(r"retrieval hit (✓|✗|\?)"),
    "citation": re.compile(r"citation (✓|✗)"),
    "key_facts": re.compile(r"key facts \d+/\d+ (✓|✗)"),
    "refusal_wording": re.compile(r"refusal wording (✓|✗)"),
    "empty_citations": re.compile(r"empty citations (✓|✗)"),
    "no_private_state_risk": re.compile(r"no private-state risk (✓|✗)"),
    "no_thinking_leak": re.compile(r"no thinking leak (✓|✗)"),
}


def _normalize_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint += "/v1"
    return endpoint


def _http_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 300) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": "Bearer not-needed"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _detect_model(base_url: str) -> str:
    data = _http_json(f"{_normalize_endpoint(base_url)}/models")
    models = data.get("data") or []
    if not models:
        raise SystemExit(f"no models served at {base_url}")
    return str(models[0]["id"])


def _chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    chat_kwargs: dict[str, Any] | None,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    if chat_kwargs:
        payload.update(chat_kwargs)
    try:
        data = _http_json(
            f"{_normalize_endpoint(base_url)}/chat/completions", payload
        )
    except urllib.error.URLError as exc:
        raise SystemExit(f"lane call failed ({base_url}): {exc}") from exc
    message = data["choices"][0]["message"]
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or ""
    if reasoning and "<think>" not in content:
        content = f"<think>{reasoning}</think>{content}"
    return str(content)


def _components_from_why(why: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, rx in _COMPONENT_RES.items():
        m = rx.search(why)
        if m:
            out[name] = {"✓": "pass", "✗": "fail", "?": "unknown"}[m.group(1)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pack",
        default="evidence/grounded-eval/cortex-grounded-v0.1.jsonl",
        help="pack JSONL (rows must also resolve through the cortex-grounded bench loader)",
    )
    ap.add_argument("--base-url", default="http://127.0.0.1:8091/v1")
    ap.add_argument("--model", default=None, help="lane model id (default: first of /v1/models)")
    ap.add_argument(
        "--mode",
        choices=("retrieval", "no-retrieval", "both"),
        default="retrieval",
        help="grounded arm, ungrounded arm (same system contract, no context blocks), or the ±Cortex pair",
    )
    ap.add_argument("--journey", default=None, help="run only this journey tag")
    ap.add_argument("--limit", type=int, default=None, help="run only the first N (filtered) rows")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--root", default=str(REPO_ROOT), help="repo root (manifest + bodies resolve against it)")
    ap.add_argument("--out", default=None, help="receipt dir (default evidence/grounded-eval/results/<run>/)")
    ap.add_argument("--run-tag", default=None, help="override the run directory name tag")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    # The cortex-grounded bench loader resolves its files via these env vars
    # (BenchSpec root_env/root_fallback) — point them at --root when unset so
    # score_eval_prediction reads the same pack the runner is iterating.
    os.environ.setdefault("ARENA_REPO_ROOT", str(root))
    os.environ.setdefault("FK_ARENA_GROUNDED_DIR", str(root / "evidence/grounded-eval"))
    sys.path.insert(0, str(root / "fieldkit" / "src"))
    from fieldkit.arena import benches
    from fieldkit.arena.cortex_chat import CortexUnavailable, build_packet, _user_prompt

    pack_path = (root / args.pack) if not Path(args.pack).is_absolute() else Path(args.pack)
    if not pack_path.is_file():
        raise SystemExit(f"pack not found: {pack_path}")
    pack_bytes = pack_path.read_bytes()
    pack_sha12 = hashlib.sha256(pack_bytes).hexdigest()[:12]
    rows = [json.loads(ln) for ln in pack_bytes.decode("utf-8").splitlines() if ln.strip()]
    if args.journey:
        rows = [r for r in rows if r.get("journey") == args.journey]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("no rows after filtering")

    model = args.model or _detect_model(args.base_url)
    modes = ["retrieval", "no_retrieval"] if args.mode == "both" else [args.mode.replace("-", "_")]

    started = datetime.now(timezone.utc)
    tag = args.run_tag or f"{started.strftime('%Y-%m-%d-%H%M')}-{re.sub(r'[^a-z0-9]+', '-', model.lower())[:48]}-{args.mode}"
    out_dir = Path(args.out) if args.out else root / "evidence/grounded-eval/results" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"

    results: list[dict[str, Any]] = []
    with results_path.open("w", encoding="utf-8") as fh:
        for i, row in enumerate(rows, start=1):
            task_id = str(row["task_id"])
            question = str(row["question"])
            # Build the live packet ONCE per row; the no_retrieval arm replays
            # the same system contract with no context blocks, so the pair
            # differs only in grounding (grounded-eval-v1 §7).
            try:
                packet = build_packet(question, root=root)
            except CortexUnavailable as exc:
                raise SystemExit(
                    f"Cortex retrieval unavailable on row {task_id}: {exc} "
                    "(hard abort — an ungrounded run must not impersonate a grounded receipt)"
                ) from exc
            for mode in modes:
                grounded = mode == "retrieval"
                user_prompt = packet["user_prompt"] if grounded else _user_prompt(question, [])
                receipt = packet["retrieval"] if grounded else None
                t0 = time.time()
                output = _chat(
                    args.base_url,
                    model,
                    [
                        {"role": "system", "content": packet["system"]},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=args.max_tokens,
                    chat_kwargs=packet["chat_kwargs"],
                )
                wall_s = round(time.time() - t0, 2)
                score = benches.score_eval_prediction(
                    "cortex-grounded", task_id, output, retrieval=receipt
                )
                if not score.get("scored"):
                    raise SystemExit(
                        f"row {task_id} did not score ({score.get('reason')}) — is the pack "
                        "registered under the cortex-grounded bench (FK_ARENA_GROUNDED_DIR)?"
                    )
                rec = {
                    "task_id": task_id,
                    "journey": row.get("journey"),
                    "expected_behavior": row.get("expected_behavior"),
                    "in_sft_corpus": row.get("in_sft_corpus"),
                    "mode": mode,
                    "question": question,
                    "output": output,
                    "passed": bool(score.get("score")),
                    "why": score.get("why"),
                    "components": _components_from_why(score.get("why") or ""),
                    "wall_s": wall_s,
                    "retrieval": (
                        {
                            "table": receipt["table"],
                            "manifest_sha256_12": receipt["manifest_sha256_12"],
                            "top_k": receipt["top_k"],
                            "sources": receipt["sources"],
                        }
                        if receipt
                        else None
                    ),
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                results.append(rec)
                mark = "PASS" if rec["passed"] else "FAIL"
                print(f"[{i}/{len(rows)}] {task_id} ({mode}): {mark} · {wall_s}s", flush=True)

    # ---- summary ----
    def _rate(rs: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rs)
        p = sum(1 for r in rs if r["passed"])
        return {"n": n, "passed": p, "pass_rate": round(p / n, 4) if n else None}

    summary: dict[str, Any] = {
        "run": tag,
        "started_utc": started.isoformat(timespec="seconds"),
        "pack": str(pack_path.relative_to(root)) if pack_path.is_relative_to(root) else str(pack_path),
        "pack_sha256_12": pack_sha12,
        "base_url": args.base_url,
        "model": model,
        "mode": args.mode,
        "max_tokens": args.max_tokens,
        "corpus": results[0]["retrieval"] and {
            "table": results[0]["retrieval"]["table"],
            "manifest_sha256_12": results[0]["retrieval"]["manifest_sha256_12"],
        },
        "modes": {},
    }
    for mode in modes:
        rs = [r for r in results if r["mode"] == mode]
        per_journey = {
            j: _rate([r for r in rs if r["journey"] == j])
            for j in sorted({r["journey"] for r in rs})
        }
        comp: dict[str, dict[str, int]] = {}
        for r in rs:
            for name, verdict in r["components"].items():
                comp.setdefault(name, {"pass": 0, "fail": 0, "unknown": 0})[verdict] += 1
        summary["modes"][mode] = {
            "overall": _rate(rs),
            "per_journey": per_journey,
            "per_component": comp,
        }
    if len(modes) == 2:
        on = {r["task_id"]: r for r in results if r["mode"] == "retrieval"}
        off = {r["task_id"]: r for r in results if r["mode"] == "no_retrieval"}
        lifts = {
            tid: int(on[tid]["passed"]) - int(off[tid]["passed"])
            for tid in on
            if tid in off
        }
        answer_ids = {r["task_id"] for r in results if r["expected_behavior"] == "answer"}
        summary["grounding_lift"] = {
            "overall": round(sum(lifts.values()) / len(lifts), 4) if lifts else None,
            "answer_rows": (
                round(
                    sum(v for t, v in lifts.items() if t in answer_ids)
                    / max(1, len([t for t in lifts if t in answer_ids])),
                    4,
                )
            ),
            "per_row": lifts,
            "note": "lift = pass(retrieval) − pass(no_retrieval); refusal rows usually 0 (refusing is easier without context)",
        }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(f"\nreceipt → {out_dir}")
    for mode in modes:
        o = summary["modes"][mode]["overall"]
        print(f"  {mode}: {o['passed']}/{o['n']} ({o['pass_rate']})")
    if "grounding_lift" in summary:
        gl = summary["grounding_lift"]
        print(f"  grounding lift: overall {gl['overall']} · answer rows {gl['answer_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
