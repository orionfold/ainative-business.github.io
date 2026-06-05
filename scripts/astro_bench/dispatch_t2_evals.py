#!/usr/bin/env python3
"""Dispatch the T2 head-to-head as Arena `eval_rerun` jobs (AF-15/AF-8/AF-7).

Routes Kepler-Q8_0 (local llama-server lane) + the OpenRouter baselines through
the SAME cockpit dispatch + the SAME custom `astro_numeric_match` verifier (the
AF-15 `scorer_path` hook), writing real `eval_runs`/`eval_scores` rows into the
live `~/.fieldkit/arena.db` so the browser shows the runs with correct scores.

Run with the edited source on the path:
  PYTHONPATH=fieldkit/src OPENROUTER_API_KEY=... \
    /tmp/fk/bin/python scripts/astro_bench/dispatch_t2_evals.py --only kepler
  ... --only baselines   (the slow OpenRouter lanes)
  ... --all
"""
from __future__ import annotations

import argparse
import os
import sys

from fieldkit.arena import jobs
from fieldkit.arena.store import ArenaStore

DB = os.path.expanduser("~/.fieldkit/arena.db")
BENCH_ID = "kepler-astro"

# id -> (kind, model, base_url, api_key_env) — the eval lane definitions (AF-7).
LANES = {
    "kepler-q8-gguf": ("LlamaServerLane", "kepler-Q8_0", "http://127.0.0.1:8088", None),
    "qwen3-8b-stock": ("OpenRouterLane", "qwen/qwen3-8b", "https://openrouter.ai/api", "OPENROUTER_API_KEY"),
    "deepseek-r1": ("OpenRouterLane", "deepseek/deepseek-r1", "https://openrouter.ai/api", "OPENROUTER_API_KEY"),
}


def register_lanes(store: ArenaStore, lane_ids: list[str]) -> None:
    for i, lid in enumerate(lane_ids):
        kind, model, base_url, _ = LANES[lid]
        store.upsert_lane(
            {
                "id": lid,
                "kind": kind,
                "model": model,
                "port": 8088 if lid == "kepler-q8-gguf" else 0,
                "base_url": base_url,
                "recommended": 1 if lid == "kepler-q8-gguf" else 0,
            }
        )
        print(f"  registered lane {lid} ({model})")


def enqueue(store: ArenaStore, lane_ids: list[str]) -> list[str]:
    ids = []
    for lid in lane_ids:
        _, model, base_url, api_key_env = LANES[lid]
        payload = {
            "lane_id": lid,
            "bench_id": BENCH_ID,
            "base_url": base_url,
            "model": model,
            # scorer_path is resolved from the bench meta sidecar (AF-15); no key
            # in the payload, only its env-var name.
            "api_key_env": api_key_env,
        }
        jid = jobs.enqueue_job(store, jobs.JobKind.EVAL_RERUN, payload, trigger="operator")
        ids.append(jid)
        print(f"  enqueued eval_rerun {jid[:12]} → {lid}")
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["kepler", "baselines"], default=None)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.only == "kepler":
        lane_ids = ["kepler-q8-gguf"]
    elif args.only == "baselines":
        lane_ids = ["qwen3-8b-stock", "deepseek-r1"]
    else:
        lane_ids = list(LANES)

    store = ArenaStore(DB)
    store.initialize()
    print(f"DB: {DB}  lanes: {lane_ids}")
    register_lanes(store, lane_ids)
    enqueue(store, lane_ids)
    print("draining (sequential, one lane at a time)…")
    done = jobs.drain_jobs(store)
    for row in done:
        import json as _json

        res = _json.loads(row.get("result_json") or "{}")
        print(
            f"  {row['kind']} {row['id'][:12]} status={row['status']} "
            f"lane={res.get('lane_id')} n_scored={res.get('n_scored')} "
            f"mean={res.get('mean_normalized')}"
        )
    store.close()


if __name__ == "__main__":
    main()
