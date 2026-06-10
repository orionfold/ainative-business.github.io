#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Run the Orionfold Advisor §13.F routing probe (route bakeoff).

Spec: ``_SPECS/orionfold-advisor-nvidia-native-v1.md`` §11 (governed routing)
and §13.F (routing probe). The publishable claim is not "frontier available";
it is "frontier is governed, measured, capped, and used only when the local
stack needs help."

Design (deterministic, auditable — Hermes-router lineage):

- T1 is the local Advisor candidate lane (Nemotron-3-Nano-30B-A3B Q8_0 on
  ``:8091``) with the tracked exemplar-format system prompt and reasoning off —
  the exact configuration behind the documented 7/8 pre-SFT floor receipt.
- The bakeoff slice is the FULL frozen 28-row held-out (not the 8-row preflight
  subset): 16 refusal/private-state boundary rows, 11 answer rows, 1 route row.
  This doubles as the "wider slice" check on the 0082 over-refusal class.
- The router sees only observables — the question text, retrieval state, and
  the T1 output. It never sees expected labels.

Router predicates, in order:

1. ``private_state_query`` — the question targets private/operator/live state
   (regex below). Hosted egress is FORBIDDEN for these rows regardless of the
   T1 verdict; a local refusal stays the routed answer (data-policy gate).
2. ``t1_error`` — the local lane errored/timed out → escalate.
3. ``format_failure`` — no ``Citations:`` line, or ``<think`` leaked into the
   content channel → escalate.
4. ``non_private_refusal`` — T1 refused (empty citations + refusal wording) a
   question that is NOT a private-state query. Over the product's own public
   corpus a refusal of a public question is suspect (the 0082 class) →
   escalate.
5. ``citation_outside_retrieved`` — T1 cited a source id that is not in the
   retrieved set (hallucinated citation) → escalate.
6. ``citation_rank_sanity`` — the 0040 wrong-citation class, made partially
   detectable without labels: anchor = the highest-ranked retrieved source not
   titled "index" (pure index pages dominate BM25 on doc-name queries but are
   rarely the citable evidence); escalate when the answer cites only sources
   scoring well below an uncited anchor —
   ``(anchor_score - best_cited_score) / anchor_score >= 0.15``. Threshold
   calibrated on the v0.1 ledger: catches 0040 (rel margin 0.22) with zero
   false escalations on the 11 correct answer rows (closest passing margins:
   0.013 cited-sibling row 0034; 0.12 below-index row 0003, whose anchor after
   the index skip IS the cited source).
7. Otherwise keep the T1 answer (zero marginal cost, full privacy).

Remaining router limitation (recorded, not hidden): a wrong citation whose
retrieval score sits within 15% of the anchor — or that outranks the correct
source — is still undetectable without labels; router recall is bounded by
detectable failure classes.

Configs:

- ``t1-only``     — escalation disabled (baseline).
- ``t1+t2``       — SKIPPED on this box: the T1 30B-A3B lane is already the
                    largest local lane on disk; no larger/specialist local
                    GGUF exists for the Advisor domain (recorded honestly).
- ``t1+t3``       — escalate to the hosted NVIDIA teacher
                    ``nvidia/nemotron-3-ultra-550b-a55b`` (integrate.api.nvidia.com,
                    ``NGC_API_KEY``). Tokens recorded; list price $0 (NGC dev
                    endpoint) — cost honesty is the token ledger, not a fake $.
- ``t1+t4``       — escalate to OpenRouter with an explicit allowed-model list
                    (``anthropic/claude-haiku-4.5``) under ``--cap-usd``
                    (default 1.00). Actual cost read from the response usage.

Hosted scoring fairness: hosted models report reasoning on a separate
``reasoning_content`` channel; only ``<think`` in the *content* channel counts
as leakage (the local-lane folding in ``preflight._chat`` is deliberate for
local leak detection and is not applied to hosted calls).

Usage:

    python3 scripts/orionfold_advisor/route_bakeoff.py \
        --t1-endpoint http://127.0.0.1:8091 --t1-model nemotron3-nano-30b-q8
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from preflight import (  # type: ignore  # noqa: E402
    EVIDENCE_DIR,
    _chat,
    _score_output,
    build_packets,
)
from score_recall import HELDOUT_PATH, REPO_ROOT, _read_jsonl  # type: ignore  # noqa: E402

VERSION = "v0.1"
LEDGER_PATH = EVIDENCE_DIR / f"advisor-route-bakeoff-{VERSION}.ledger.jsonl"
REPORT_PATH = EVIDENCE_DIR / f"advisor-route-bakeoff-{VERSION}.json"

# Data-policy gate: questions targeting private/operator/live state. Calibrated
# against the held-out boundary rows' *shape* (private-state markers), not
# their ids — separates 16/16 refuse rows from 0/12 answerable rows.
PRIVATE_STATE_RE = re.compile(
    r"(?i)(\.env\.local|_STATUS\.json|CLAUDE\.md|currently resident|right now"
    r"|live runtime|\b(credentials?|secrets?|handoff|scheduled_tasks|private"
    r"|unpublished|CODEX-CC|arena.mirror|CDP|root-owned|tonight)\b)"
)

REFUSAL_WORDS = (
    "not support",
    "does not support",
    "does not provide",
    "do not have",
    "cannot answer",
    "can't answer",
    "insufficient",
)

T3_ENDPOINT = "https://integrate.api.nvidia.com/v1"
T3_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
T4_ENDPOINT = "https://openrouter.ai/api/v1"
T4_ALLOWED_MODELS = ("anthropic/claude-haiku-4.5",)


def _hosted_chat(
    endpoint: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict[str, Any]]:
    """One hosted chat call → (content-channel text, usage dict).

    ``reasoning_content`` stays on its own channel — it is NOT folded into the
    scored text (see module docstring on hosted scoring fairness)."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        f"{endpoint.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    message = data["choices"][0]["message"]
    return str(message.get("content") or ""), dict(data.get("usage") or {})


def _is_refusal(output: str) -> bool:
    """Observable refusal: an empty Citations line + refusal wording."""
    matches = list(re.finditer(r"(?im)\bCitations:\s*\[(.*?)\]\s*\.?", output))
    if not matches:
        return False
    cited = re.findall(r"[a-z][a-z0-9_]+", matches[-1].group(1))
    return not cited and any(w in output.lower() for w in REFUSAL_WORDS)


RANK_SANITY_REL_MARGIN = 0.15


def _cited_ids(output: str) -> list[str]:
    """Source ids on the LAST Citations line of the output (observable)."""
    matches = list(re.finditer(r"(?im)\bCitations:\s*\[(.*?)\]\s*\.?", output))
    if not matches:
        return []
    return re.findall(r"[a-z][a-z0-9_]+", matches[-1].group(1))


def _citation_sanity_trigger(packet: dict[str, Any], output: str) -> str | None:
    """Label-free wrong-citation detection (router predicates 5 and 6)."""
    cited = _cited_ids(output)
    if not cited:
        return None
    retrieved = packet["retrieved_sources"] or []
    scores = {s["source_id"]: float(s["score"]) for s in retrieved}
    if any(source_id not in scores for source_id in cited):
        return "citation_outside_retrieved"
    anchor = next(
        (s for s in retrieved if str(s.get("title", "")).strip().lower() != "index"),
        None,
    )
    if anchor is None or anchor["source_id"] in cited:
        return None
    best_cited = max(scores[source_id] for source_id in cited)
    anchor_score = float(anchor["score"])
    if anchor_score <= 0:
        return None
    if (anchor_score - best_cited) / anchor_score >= RANK_SANITY_REL_MARGIN:
        return "citation_rank_sanity"
    return None


def _route_decision(packet: dict[str, Any], t1_output: str | None) -> dict[str, Any]:
    """The deterministic router verdict for one row (observables only)."""
    private_state = bool(PRIVATE_STATE_RE.search(str(packet["question"])))
    if t1_output is None:
        trigger = "t1_error"
    elif "<think" in t1_output.lower():
        trigger = "format_failure_think_leak"
    elif not re.search(r"(?im)\bCitations:\s*\[", t1_output):
        trigger = "format_failure_no_citation_line"
    elif _is_refusal(t1_output) and not private_state:
        trigger = "non_private_refusal"
    else:
        trigger = _citation_sanity_trigger(packet, t1_output)
    escalate = trigger is not None and not private_state
    return {
        "private_state_query": private_state,
        "trigger": trigger,
        "escalate": escalate,
        "hosted_egress_blocked": trigger is not None and private_state,
    }


def _summarize(
    rows: list[dict[str, Any]], key: str
) -> dict[str, Any]:
    """Pass/refusal/citation metrics over the ledger for verdict column ``key``."""
    refuse = [r for r in rows if r["expected_behavior"] == "refuse"]
    answer = [r for r in rows if r["expected_behavior"] != "refuse"]
    n = len(rows)
    passed = sum(1 for r in rows if r[key]["passed"])
    return {
        "pass": passed,
        "pass_rate": round(passed / n, 4) if n else None,
        "refusal_correct": sum(1 for r in refuse if r[key]["refusal_ok"] and r[key]["citation_ok"]),
        "refusal_rows": len(refuse),
        "citation_correct": sum(1 for r in answer if r[key]["citation_ok"]),
        "answer_rows": len(answer),
        "thinking_leaks": sum(1 for r in rows if r[key]["thinking_leak"]),
        "private_state_risks": sum(1 for r in rows if r[key]["private_state_risk"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--t1-endpoint", default="http://127.0.0.1:8091")
    parser.add_argument("--t1-model", default="nemotron3-nano-30b-q8")
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--cap-usd", type=float, default=1.00)
    parser.add_argument("--skip-hosted", action="store_true", help="T1 run + router decisions only")
    args = parser.parse_args()

    ngc_key = os.environ.get("NGC_API_KEY", "")
    or_key = os.environ.get("OPENROUTER_API_KEY", "")

    all_ids = [row["task_id"] for row in _read_jsonl(HELDOUT_PATH)]
    # T1 packets carry the reasoning-off control (the 7/8 receipt config);
    # hosted packets carry the same prompt contract without the local
    # reasoning-mode controls (inert-but-noisy for hosted templates).
    t1_packets = build_packets(task_ids=all_ids, top_k=5, max_sources=5, excerpt_chars=900, reasoning_mode="off")
    hosted_packets = {
        p["task_id"]: p
        for p in build_packets(task_ids=all_ids, top_k=5, max_sources=5, excerpt_chars=900, reasoning_mode="default")
    }

    print(f"T1 run: {len(t1_packets)} held-out rows via {args.t1_endpoint} ({args.t1_model})")
    ledger: list[dict[str, Any]] = []
    for i, packet in enumerate(t1_packets, 1):
        try:
            output: str | None = _chat(
                args.t1_endpoint,
                args.t1_model,
                packet["messages"],
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                reasoning_mode="off",
            )
        except RuntimeError as exc:
            print(f"  [{i}/{len(t1_packets)}] {packet['task_id']} T1 ERROR: {exc}")
            output = None
        score = _score_output(packet, output or "")
        decision = _route_decision(packet, output)
        top1 = (packet["retrieved_sources"] or [{}])[0]
        ledger.append(
            {
                "task_id": packet["task_id"],
                "family": packet["family"],
                "expected_behavior": packet["expected_behavior"],
                "retrieval_top1_source": top1.get("source_id"),
                "retrieval_top1_score": top1.get("score"),
                "t1_output": output,
                "t1": score,
                "route": decision,
                "escalations": {},
            }
        )
        mark = "PASS" if score["passed"] else "fail"
        esc = f" -> escalate({decision['trigger']})" if decision["escalate"] else ""
        blocked = " [hosted egress blocked: private-state]" if decision["hosted_egress_blocked"] else ""
        print(f"  [{i}/{len(t1_packets)}] {packet['task_id']} {mark}{esc}{blocked}")

    escalated = [r for r in ledger if r["route"]["escalate"]]
    print(f"router: {len(escalated)} rows escalate, "
          f"{sum(1 for r in ledger if r['route']['hosted_egress_blocked'])} blocked as private-state")

    hosted_cost_usd = {"t1+t3": 0.0, "t1+t4": 0.0}
    hosted_tokens = {"t1+t3": {"prompt": 0, "completion": 0}, "t1+t4": {"prompt": 0, "completion": 0}}
    tiers = []
    if not args.skip_hosted:
        tiers = [
            ("t1+t3", "T3", T3_ENDPOINT, ngc_key, T3_MODEL),
            ("t1+t4", "T4", T4_ENDPOINT, or_key, T4_ALLOWED_MODELS[0]),
        ]
    for config, tier, endpoint, key, model in tiers:
        if not key:
            print(f"{config}: SKIPPED — missing API key in env")
            continue
        for row in escalated:
            if hosted_cost_usd[config] >= args.cap_usd:
                row["escalations"][config] = {"status": "cap_exceeded"}
                print(f"  {config} {row['task_id']}: CAP {args.cap_usd} USD reached — not sent")
                continue
            packet = hosted_packets[row["task_id"]]
            try:
                text, usage = _hosted_chat(
                    endpoint, key, model, packet["messages"],
                    # the teacher thinks on the same completion budget — give it room
                    max_tokens=4096 if tier == "T3" else args.max_tokens,
                    temperature=args.temperature,
                )
            except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
                row["escalations"][config] = {"status": "error", "error": str(exc)[:300], "model": model}
                print(f"  {config} {row['task_id']}: ERROR {exc}")
                continue
            score = _score_output(packet, text)
            cost = float(usage.get("cost") or 0.0)
            hosted_cost_usd[config] += cost
            hosted_tokens[config]["prompt"] += int(usage.get("prompt_tokens") or 0)
            hosted_tokens[config]["completion"] += int(usage.get("completion_tokens") or 0)
            row["escalations"][config] = {
                "status": "ok",
                "tier": tier,
                "model": model,
                "output": text,
                "score": score,
                "usage": {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "cost")},
            }
            print(f"  {config} {row['task_id']}: {'PASS' if score['passed'] else 'fail'} (${cost:.6f})")

    # Routed verdicts per config: escalated rows take the hosted verdict when
    # the call succeeded, else keep T1.
    configs: dict[str, Any] = {}
    config_names = ["t1-only"] + [c for c, *_ in tiers]
    for config in config_names:
        for row in ledger:
            esc = row["escalations"].get(config) if config != "t1-only" else None
            row[f"routed_{config}"] = esc["score"] if esc and esc.get("status") == "ok" else row["t1"]
        # Route accuracy (post-hoc, labels allowed here): correct = escalated
        # exactly the rows T1 failed. The data-policy block is part of the
        # policy, so a blocked private-state row counts via its keep decision.
        correct = sum(
            1 for row in ledger
            if (row["route"]["escalate"] and config != "t1-only") == (not row["t1"]["passed"])
        ) if config != "t1-only" else None
        summary = _summarize(ledger, f"routed_{config}")
        t1_summary = _summarize(ledger, "t1")
        delta_points = round((summary["pass_rate"] - t1_summary["pass_rate"]) * 100, 2)
        cost = round(hosted_cost_usd.get(config, 0.0), 6)
        configs[config] = {
            **summary,
            "escalated_rows": len(escalated) if config != "t1-only" else 0,
            "route_accuracy": round(correct / len(ledger), 4) if correct is not None else None,
            "hosted_cost_usd": cost if config != "t1-only" else 0.0,
            "hosted_tokens": hosted_tokens.get(config) if config != "t1-only" else None,
            "quality_delta_points": delta_points if config != "t1-only" else 0.0,
            "usd_per_quality_point": (
                round(cost / delta_points, 6) if config != "t1-only" and delta_points > 0 else None
            ),
        }

    report = {
        "generated": date.today().isoformat(),
        "version": VERSION,
        "spec": "_SPECS/orionfold-advisor-nvidia-native-v1.md §13.F",
        "slice": {
            "rows": len(ledger),
            "source": HELDOUT_PATH.relative_to(REPO_ROOT).as_posix(),
            "note": "full frozen held-out, not the 8-row preflight subset",
        },
        "t1": {
            "endpoint": args.t1_endpoint,
            "model": args.t1_model,
            "config": "exemplar-format system prompt + reasoning off (the 7/8 receipt config)",
            **_summarize(ledger, "t1"),
        },
        "router": {
            "policy": (
                "deterministic observables-only: private-state data-policy gate; escalate on "
                "t1_error / format failure / non-private refusal / citation outside retrieved set / "
                "citation rank sanity (uncited non-index anchor outscores best cited source by "
                f">={RANK_SANITY_REL_MARGIN} relative margin)"
            ),
            "revision": 2,
            "rank_sanity_rel_margin": RANK_SANITY_REL_MARGIN,
            "rank_sanity_calibration": (
                "threshold calibrated on the v0.1 router-revision-1 ledger: catches 0040 "
                "(rel margin 0.22), zero false escalations on the 11 correct answer rows "
                "(closest passing margins 0.013 and 0.12-below-index)"
            ),
            "escalated": len(escalated),
            "private_state_blocked": sum(1 for r in ledger if r["route"]["hosted_egress_blocked"]),
            "known_limitation": (
                "a wrong citation within the rank-sanity margin of the anchor, or one that "
                "outranks the correct source, is still undetectable without labels"
            ),
        },
        "configs": configs,
        "t2_status": (
            "skipped — no larger/specialist local lane on disk; the T1 30B-A3B "
            "lane is already the largest local model for the Advisor domain"
        ),
        "t4_governance": {
            "allowed_models": list(T4_ALLOWED_MODELS),
            "cap_usd": args.cap_usd,
            "data_policy": "public-corpus packets only; private-state queries never leave the box",
        },
        "ledger_path": LEDGER_PATH.relative_to(REPO_ROOT).as_posix(),
    }
    with LEDGER_PATH.open("w", encoding="utf-8") as fh:
        for row in ledger:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote route-bakeoff ledger -> {LEDGER_PATH}")
    print(f"wrote route-bakeoff report -> {REPORT_PATH}")
    for config, c in configs.items():
        print(
            f"{config}: pass {c['pass']}/{len(ledger)}"
            + (f" · route_acc {c['route_accuracy']}" if c["route_accuracy"] is not None else "")
            + (f" · ${c['hosted_cost_usd']}" if config != "t1-only" else "")
        )


if __name__ == "__main__":
    main()
