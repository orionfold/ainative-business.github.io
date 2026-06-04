# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""enqueue_rl.py — queue the astrodynamics ``rl_run`` for the Arena drain (C5).

The real-seam launch the C3 `smoke_rl.py` foreshadowed ("the fake seams swap for
`fieldkit.rl.gpu_seams(config, reward=…)` at C4"). Instead of driving `RLLoop`
standalone, this writes ONE ``queued`` ``rl_run`` job into the operator-private
arena.db so the **dispatcher** runs it — which means the run inherits the whole
rl-lane-autonomy stack the operator built it for: the lane arbiter (envelope
pre-flight + resident-brain teardown), the OOM `MemoryWatchdog`, the live
`/arena/reward/` cockpit progress feed, and the `jobs.result_json` + lineage
persistence. Drain it with::

    source $AROOT/fk-rl-env.sh
    /tmp/fk-rl/bin/fieldkit arena drain --db ~/.fieldkit/arena.db   # blocks for the run

The astro reward (`astro_numeric_match` — boxed + SI-unit-aware, kept local per
`feedback_keep_scorer_local_until_reuse`) rides the generic ``scorer_path``
payload hook added to `run_rl_loop`, so the dispatcher uses the *correct* verifier
instead of the built-in first-number `numeric_match` (which scores a correct astro
completion 0.0 — it grabs an intermediate from inside ``<think>``).

Knobs via env: ``FK_RL_BASE_MODEL`` (required — the merged SFT model served as
base), ``FK_RL_MAX_STEPS`` (default 34), ``ARENA_DB`` (default ~/.fieldkit/arena.db).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fieldkit.arena.jobs import enqueue_job
from fieldkit.arena.store import ArenaStore

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "evidence" / "astrodynamics"
BENCH_PATH = EVIDENCE / "astro-bench-v0.1.jsonl"  # 120-row pool (RV-10 ≥100 floor)
SCORER_PATH = REPO / "scripts" / "astro_bench" / "verifier.py"

LANE_ID = "astro-rlvr"
BENCH_ID = "astro-bench-v0.1"
VERTICAL = "astrodynamics"


def build_payload() -> dict:
    base = os.environ.get("FK_RL_BASE_MODEL")
    if not base:
        raise SystemExit(
            "FK_RL_BASE_MODEL is unset — source the run env first:\n"
            "    source /home/nvidia/data/astro-train-lora/p65-nemo/fk-rl-env.sh"
        )
    if not BENCH_PATH.exists():
        raise SystemExit(f"bench not found: {BENCH_PATH}")
    if not SCORER_PATH.exists():
        raise SystemExit(f"scorer not found: {SCORER_PATH}")
    max_steps = int(os.environ.get("FK_RL_MAX_STEPS", "34"))
    return {
        "base": base,
        "vertical": VERTICAL,
        "bench_path": str(BENCH_PATH),
        # the generic custom-scorer hook → the local boxed+SI astro verifier
        "scorer_path": f"{SCORER_PATH}:astro_numeric_match",
        "lane_id": LANE_ID,
        "bench_id": BENCH_ID,
        "config": {
            "max_steps": max_steps,
            "heldout_every": 10,   # hard held-out gate cadence (RV-4)
            "heldout_frac": 0.2,   # 24 held-out / 96 train off the 120-row pool
            "lora_rank": 16,       # matches init-lora-r16 (FK_RL_ADAPTER_INIT)
            "group_k": 4,
            "tasks_per_step": 8,
            "seed": 0,
        },
    }


def main() -> int:
    db = os.path.expanduser(os.environ.get("ARENA_DB", "~/.fieldkit/arena.db"))
    payload = build_payload()
    store = ArenaStore(db)
    store.initialize()
    try:
        job_id = enqueue_job(
            store, "rl_run", payload, trigger="manual",
            dedup_key=f"rl_run:{LANE_ID}:{BENCH_ID}",
        )
    finally:
        store.close()
    if job_id is None:
        print("coalesced — an in-flight rl_run already holds "
              f"rl_run:{LANE_ID}:{BENCH_ID} (nothing enqueued).")
        return 0
    print(f"queued rl_run {job_id}")
    print(f"  base        : {payload['base']}")
    print(f"  bench       : {payload['bench_path']}  (120 pool → 96 train / 24 held-out)")
    print(f"  scorer_path : {payload['scorer_path']}")
    print(f"  max_steps   : {payload['config']['max_steps']}  (held-out gate every 10)")
    print(f"  db          : {db}")
    print("\nNow drain it (blocks for the run; watch /arena/reward/):")
    print("    /tmp/fk-rl/bin/fieldkit arena drain --db ~/.fieldkit/arena.db")
    print("\npayload:")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
