#!/usr/bin/env python3
"""G4 — full 5000-row distilabel run for patent corpus v2.

⚠️ DEMOTED 2026-05-20 — HISTORICAL / REPRO-AUDIT ONLY.
Superseded by the NeMo DataDesigner + Curator + NIM stack per the validation
pilot recorded in ``ideas/nemo-stack-validation-2026-05-20.md`` (Phase 4+5
results) and locked-in by ``ideas/uber-local-corpus-gen-decision.md`` (Phase 7,
"What unblocks immediately after this Phase 7 commit", §613). This file is
preserved for the G4 RCA trail (distilabel silent-None failure mode → 3308/5000
placeholder rows; see ``ideas/rca-g4-corpus-failure-2026-05-20.md``). DO NOT
run for new corpora — use the dd-pilot:0.1 image + DataDesigner pipeline
instead. distilabel is no longer a project dependency.

Identical pipeline to scripts/g4 G3 dry-run, scaled to the full queue and
restart-safe via distilabel's pipeline cache (`use_cache=True`).

Wall projection (measured from G3 dry-run-50): ~17 hours at c=8.
  - 50 rows in 10m32s wall = 285 rows/hr aggregate
  - HANDOFF's earlier 8.4h projection was extrapolated from raw NIM tok/s
    without orchestration overhead; the measured number is the realistic one.

To launch detached so it survives a CC session boundary:
  docker exec -d ps-train bash -c \
    'cd /tmp && python3 /home/nvidia/ainative-business.github.io/scripts/g4_distilabel_full_run.py \
     > /tmp/g4-run.log 2>&1'

Resume after an interruption: just re-run — distilabel will pick up from the
last cached step (use_cache=True).

Output:
  /home/nvidia/data/aifn-corpus-v2/full-5000/distiset/  (HF Distiset format)
  /home/nvidia/data/aifn-corpus-v2/full-5000/out.jsonl  (row_idx, family,
                                                         prompt, chain, answer)
"""
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "/home/nvidia/data/.hf-cache/hub")
os.environ.setdefault("OPENAI_API_KEY", "EMPTY")

import faiss
import pandas as pd

from distilabel.llms import OpenAILLM
from distilabel.pipeline import Pipeline
from distilabel.steps import KeepColumns, LoadDataFromDicts, Step, StepInput, StepOutput
from distilabel.steps.tasks import TextGeneration
from sentence_transformers import SentenceTransformer

# Reuse the proven G3 components — same SYSTEM_PROMPT, retriever, split_think,
# template — only the input queue + output path differ.
sys.path.insert(0, str(Path(__file__).parent))
from g3_distilabel_dry_run import (  # noqa: E402
    MPEPRetriever,
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    split_think,
)

QUEUE = Path("/home/nvidia/data/aifn-corpus-v2/queue.jsonl")
OUT_DIR = Path("/home/nvidia/data/aifn-corpus-v2/full-5000")
NIM_BASE_URL = "http://172.17.0.1:8000/v1"
MODEL = "nvidia/nemotron-nano-9b-v2"

# Skip rows already generated and salvaged from the prior c=8 attempt.
# Salvaged rows are at /home/nvidia/data/aifn-corpus-v2/salvaged-128/out.jsonl
# and will be concat'd with this run's output post-hoc.
SKIP_ROWS_BELOW = int(os.environ.get("G4_SKIP_ROWS_BELOW", "128"))


def load_full_queue() -> list[dict]:
    with QUEUE.open() as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if SKIP_ROWS_BELOW > 0:
        rows = [r for r in rows if r["row_idx"] >= SKIP_ROWS_BELOW]
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_full_queue()
    print(f"Loaded {len(rows)} rows from {QUEUE}", flush=True)
    family_counts = {fam: sum(1 for r in rows if r["family"] == fam)
                     for fam in ["A1", "A2", "A4", "E1", "E2"]}
    print(f"Family distribution: {family_counts}", flush=True)

    llm = OpenAILLM(
        model=MODEL,
        base_url=NIM_BASE_URL,
        api_key="EMPTY",
        generation_kwargs={
            "temperature": 0.6,
            "top_p": 0.95,
            "max_new_tokens": 3500,
        },
        max_retries=3,
    )

    # All step batch sizes aligned at 32 so batches flow through without
    # repacking. Memory headroom (28 GB free, vLLM KV-cache <1% used at
    # c=8) supports 32× concurrent NIM requests.
    with Pipeline(name="patent-corpus-v2-full-5000") as pipeline:
        loader = LoadDataFromDicts(name="loader", data=rows, batch_size=32)
        retriever = MPEPRetriever(name="retriever", input_batch_size=32)
        generator = TextGeneration(
            name="generator",
            llm=llm,
            system_prompt=SYSTEM_PROMPT,
            template=USER_TEMPLATE,
            columns=["mpep_context", "prompt"],
            input_batch_size=32,
            num_generations=1,
        )
        keeper = KeepColumns(
            name="keeper",
            columns=["row_idx", "family", "prompt", "mpep_context", "generation"],
            input_batch_size=32,
        )
        loader >> retriever >> generator >> keeper

    print("Running pipeline (use_cache=True for restart safety)...", flush=True)
    distiset = pipeline.run(use_cache=True)
    distiset.save_to_disk(str(OUT_DIR / "distiset"))
    print(f"Saved distiset to {OUT_DIR / 'distiset'}", flush=True)

    # Materialize JSONL with chain/answer split.
    out_jsonl = OUT_DIR / "out.jsonl"
    n_total = 0
    n_with_answer = 0
    with out_jsonl.open("w") as fout:
        for sub in distiset:
            for split_name in distiset[sub]:
                for row in distiset[sub][split_name]:
                    raw = row.get("generation") or ""
                    chain, answer = split_think(raw)
                    rec = {
                        "row_idx": row.get("row_idx"),
                        "family": row.get("family"),
                        "prompt": row.get("prompt"),
                        "mpep_context": row.get("mpep_context"),
                        "chain": chain,
                        "answer": answer,
                        "answer_chars": len(answer),
                        "chain_chars": len(chain),
                    }
                    fout.write(json.dumps(rec) + "\n")
                    n_total += 1
                    if answer.strip():
                        n_with_answer += 1
    print(f"\nWrote {n_total} rows → {out_jsonl}", flush=True)
    print(f"  with non-empty answer: {n_with_answer}/{n_total}", flush=True)


if __name__ == "__main__":
    main()
