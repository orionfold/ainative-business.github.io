#!/usr/bin/env python3
"""One-off assembly of the arena demo simulated-stub overlay.

Sanitizes the real endpoint dumps (same scrubber `fieldkit arena record` uses)
and merges the hand-authored showcase enrichments. Output is the checked-in
overlay consumed by `fieldkit arena record --stubs-overlay`.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/nvidia/ainative-business.github.io/fieldkit/src")
from fieldkit.arena.fixtures import _sanitize  # noqa: E402

SHAPES = Path("/tmp/arena-stub-shapes")
OUT = Path("/home/nvidia/ainative-business.github.io/arena-app/arena-demo-sim/stubs.json")

real_jobs = _sanitize(json.loads((SHAPES / "jobs.json").read_text()))["jobs"]
real_standup = _sanitize(json.loads((SHAPES / "standup.json").read_text()))
real_knowledge = _sanitize(json.loads((SHAPES / "knowledge.json").read_text()))

# ---- hand-authored queued/running jobs (the board's empty columns) ----------
queued_eval = {
    "id": "c41f7a02d9e84b6f8a3d5e0b117f24a9",
    "kind": "eval_rerun",
    "status": "queued",
    "trigger": "leaderboard_regression",
    "priority": 5,
    "dedup_key": "eval_rerun:saul-7b-instruct-v1-gguf::Q4_K_M:legal-bench-v0.1",
    "error": None,
    "attempt": 0,
    "enqueued_at": "2026-06-07T07:58:12Z",
    "dispatched_at": None,
    "finished_at": None,
    "arq_job_id": None,
    "payload": {"lane_id": "saul-7b-instruct-v1-gguf::Q4_K_M", "bench_id": "legal-bench-v0.1", "n": 25},
    "result": None,
    "result_json": None,
}
queued_launch = {
    "id": "9b8e2f6c413d47d2b0a6c9d8e5f1a370",
    "kind": "lane_launch",
    "status": "queued",
    "trigger": "manual",
    "priority": 0,
    "dedup_key": "lane_launch:patent-v3-q5km",
    "error": None,
    "attempt": 0,
    "enqueued_at": "2026-06-07T08:02:47Z",
    "dispatched_at": None,
    "finished_at": None,
    "arq_job_id": None,
    "payload": {"recipe": "patent-v3-q5km", "anchor_on_warm": True},
    "result": None,
    "result_json": None,
}
running_rag = {
    "id": "5d20c7b9ef364c01a4f8b2d6c3e91854",
    "kind": "rag_eval",
    "status": "running",
    "trigger": "manual",
    "priority": 0,
    "dedup_key": "rag_eval:qa-eval.jsonl",
    "error": None,
    "attempt": 0,
    "enqueued_at": "2026-06-07T08:04:21Z",
    "dispatched_at": "2026-06-07T08:04:30Z",
    "finished_at": None,
    "arq_job_id": None,
    "payload": {"qa_set": "qa-eval.jsonl", "rerank": False, "top_k": 5},
    "result": None,
    "result_json": None,
}
jobs = [queued_eval, queued_launch, running_rag] + real_jobs

# ---- standup: reflect the queued work --------------------------------------
standup = dict(real_standup)
standup["queued"] = [
    {k: j[k] for k in ("id", "kind", "status", "trigger", "enqueued_at")}
    for j in (queued_eval, queued_launch)
]
counts = dict(standup.get("counts") or {})
counts["queued"] = len(standup["queued"])
standup["counts"] = counts

# ---- lane recipes (models pane launch form) ---------------------------------
lane_recipes = {
    "recipes": [
        {"name": "kepler-q8", "valid": True, "kind": "llama-server",
         "model_file": "kepler-q8.gguf", "port": 8091, "n_ctx": 32768, "gguf_present": True},
        {"name": "patent-v3-q5km", "valid": True, "kind": "llama-server",
         "model_file": "patent-strategist-v3-nemo-Q5_K_M.gguf", "port": 8092, "n_ctx": 16384, "gguf_present": True},
        {"name": "medical-q4km", "valid": True, "kind": "llama-server",
         "model_file": "II-Medical-8B-Q4_K_M.gguf", "port": 8093, "n_ctx": 16384, "gguf_present": True},
    ],
    "path": "lane-recipes.json",
}

# ---- active lane: the Kepler serving lane discovered on :8091 ----------------
# (:8091 is already public — the `discovered:8091` lane id ships in the mirror
# leaderboard and the launch articles; the sidecar/Hermes ports stay redacted.)
active_lane = {
    "active": {
        "id": "discovered:8091", "kind": "LlamaServerLane", "model": "kepler-q8.gguf",
        "port": 8091, "provider": "custom", "context_length": 32768,
        "max_tokens": 8192, "source": "discovery", "drift": None,
    },
    "discovered": [
        {"port": 8091, "model": "kepler-q8.gguf", "context_length": 32768,
         "kind": "LlamaServerLane", "warm_seconds": 412},
    ],
    "registry": None,
    "source": "discovery",
    "drift": None,
}

# ---- Cortex knowledge fixture: before → after + canned queries ---------------
after = dict(real_knowledge)
before = json.loads(json.dumps(after))  # deep copy
cov = before["coverage"]
cov["indexed"] = 46
cov["missing"] = [
    "t2po-uncertainty-guided-rl-on-spark",
    "test-time-distilling-for-exploration",
    "trajectory-eval-is-the-agent-flailing",
]
cov["missing_n"] = 3
cov["coverage_pct"] = 93.9
for slug in cov["missing"]:
    cov["chunk_counts"].pop(slug, None)
before["provenance_backfilled"] = {"with_provenance": 188, "total": 295}
before["rag_eval_runs"] = []
before["reindex_runs"] = before["reindex_runs"][-1:]
before["index_note"] = "3 articles published since the last re-index — rebuild to fold them in."

queries = [
    {
        "query": "Why did the Hermes brain bakeoff pick a 30B MoE over NIM?",
        "hits": [
            {"slug": "picking-the-hermes-brain-on-spark", "chunk_idx": 2, "source": "article", "dist": 0.312,
             "text": "The bakeoff pinned the Hermes brain to Qwen3-30B-A3B MoE at Q4_K_M on llama.cpp: 8/8 harness tasks against 6/8 for the NIM lane, at roughly 3.5x the tokens per second."},
            {"slug": "hermes-serving-lane-on-spark", "chunk_idx": 1, "source": "article", "dist": 0.389,
             "text": "One serving lane at a time inside the 128 GB unified envelope — the harness points at whichever lane is resident, and the cockpit's discovery probe reports what is actually serving."},
            {"slug": "hermes-cost-routing-local-and-openrouter", "chunk_idx": 3, "source": "article", "dist": 0.421,
             "text": "Routing sends local-shaped work to the resident lane and escalates to OpenRouter frontier models only when local confidence drops below the threshold."},
        ],
    },
    {
        "query": "What recall did naive RAG get on the Second Brain eval?",
        "hits": [
            {"slug": "naive-rag-on-spark", "chunk_idx": 4, "source": "article", "dist": 0.298,
             "text": "Naive top-k retrieval over the 313-chunk pgvector index lands recall@k 0.409 on the QA eval set — the floor the rerank and fusion experiments are measured against."},
            {"slug": "rag-eval-ragas-and-nemo-evaluator", "chunk_idx": 2, "source": "eval", "dist": 0.355,
             "text": "The QA eval harness scores recall@k and slug-recall@k per run and persists each run, so the trend over re-indexes is inspectable instead of anecdotal."},
            {"slug": "rerank-fusion-retrieval-on-spark", "chunk_idx": 5, "source": "article", "dist": 0.401,
             "text": "Fusing dense retrieval with a reranking pass lifts slug-recall toward 0.73 — the biggest single jump in the retrieval-path series."},
        ],
    },
    {
        "query": "How much GPU memory does a LoRA fine-tune need on the Spark?",
        "hits": [
            {"slug": "gpu-sizing-math-for-fine-tuning", "chunk_idx": 1, "source": "article", "dist": 0.276,
             "text": "Rule-of-thumb arithmetic: weights + optimizer states + activations, then check it against the 128 GB unified envelope — a rank-16 LoRA on an 8B model fits with tens of gigabytes to spare."},
            {"slug": "lora-on-your-own-qa-pairs", "chunk_idx": 3, "source": "article", "dist": 0.342,
             "text": "A 600-row QA LoRA on the Spark trains in minutes, not hours — the bottleneck is corpus quality, not compute."},
            {"slug": "fine-tune-data-prep-decisions-on-spark", "chunk_idx": 2, "source": "article", "dist": 0.398,
             "text": "Data-prep decisions (dedup, format, BOS/EOS) move the eval more than hyperparameters do; the gates are cheap to run before any multi-hour train."},
        ],
    },
]

overlay = {
    "note": (
        "Demo bundle: chat & compare replay real recorded DGX Spark runs "
        "(real answers, measured TTFT/throughput). The jobs board, standup, "
        "lane and knowledge panes show simulated data drawn from past real "
        "runs to demonstrate the features — see the DEMO ribbon."
    ),
    "stubs": {
        "/api/jobs": {"jobs": jobs},
        "/api/standup": standup,
        "/api/lane-recipes": lane_recipes,
        "/api/active-lane": active_lane,
    },
    "knowledge": {"before": before, "after": after, "queries": queries},
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(overlay, indent=1) + "\n", encoding="utf-8")
flat = OUT.read_text()
for bad in ("/home/", "/Users/", ".hermes", ":7866", ":8080", "config_mtime", "config_path"):
    assert bad not in flat, f"LEAK: {bad}"
print(f"wrote {OUT} ({OUT.stat().st_size} bytes), leak scan clean")
