#!/usr/bin/env python3
"""G3 — 50-row distilabel dry-run for patent corpus v2.

⚠️ DEMOTED 2026-05-20 — HISTORICAL / REPRO-AUDIT ONLY.
Superseded by NeMo DataDesigner + NIM (see ``ideas/uber-local-corpus-gen-decision.md``
Phase 7 §613, "Delete / demote in the codebase"). The G3 dry-run flow is now
replaced by Phase 3+4 of the pilot — see ``/tmp/dd-pilot/phase3/scale_100row.py``
(to be moved into ``scripts/`` once v3 regen validates the recipe end-to-end).
The ``split_think()`` helper below is still canonical and re-used by the
DataDesigner driver as a post-process step; keep that import path stable.

Pipeline:
  LoadDataFromDicts (50 rows from queue.jsonl)
    → MPEPRetriever (custom Step, FAISS top-3)
    → TextGeneration (NIM Nemotron-Nano-9B-v2, OpenAI-compatible)
    → KeepColumns
  → post-process: split chain/answer using NIM's `<think>`-prefix convention
  → write JSONL at /home/nvidia/data/aifn-corpus-v2/dry-run-50/out.jsonl

Per HANDOFF G3.2 + G2 findings:
  - NIM prepends `<think>` to assistant prompt prefix; `split_think()` recovers
    the chain/answer split client-side.
  - max_tokens raised to 3500 (E1 family failed at 2500 by exhausting budget
    inside the reasoning block).
  - temperature 0.6, top_p 0.95 per Nemotron defaults.
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

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

QUEUE = Path("/home/nvidia/data/aifn-corpus-v2/queue.jsonl")
INDEX_DIR = Path("/home/nvidia/data/aifn-retrieval-index/mpep-bge-base")
OUT_DIR = Path("/home/nvidia/data/aifn-corpus-v2/dry-run-50")
NIM_BASE_URL = "http://172.17.0.1:8000/v1"
MODEL = "nvidia/nemotron-nano-9b-v2"

SYSTEM_PROMPT = (
    "You are a senior US patent practitioner with 15 years of prosecution experience. "
    "Use the MPEP excerpts provided as your sole source of MPEP authority — do not cite "
    "any MPEP section that does not appear in the excerpts. Reason step-by-step inside "
    "<think>…</think> tags. After </think>, give a concise practitioner answer that "
    "directly addresses the task. Always emit an answer after </think> — do not leave "
    "the post-think section empty. Cite MPEP sections by their exact titles as shown in "
    "the excerpts. No producer-meta-commentary, no row-index references, no diversification "
    "reasoning."
)

USER_TEMPLATE = """## MPEP EXCERPTS (top-3 retrieved)
{{ mpep_context }}

## TASK
{{ prompt }}
"""


class MPEPRetriever(Step):
    """Adds `mpep_context` to each row via FAISS top-3 retrieval over MPEP chunks."""

    @property
    def inputs(self) -> list[str]:
        return ["prompt"]

    @property
    def outputs(self) -> list[str]:
        return ["mpep_context"]

    def load(self) -> None:
        super().load()
        self._idx = faiss.read_index(str(INDEX_DIR / "index.faiss"))
        self._chunks = pd.read_parquet(INDEX_DIR / "chunks.parquet")
        self._embed = SentenceTransformer("BAAI/bge-base-en-v1.5", device="cpu")
        self._logger.info(
            f"MPEPRetriever loaded: {self._idx.ntotal:,} chunks, dim={self._idx.d}"
        )

    def _retrieve(self, query: str, k: int = 3) -> str:
        q = self._embed.encode([query], normalize_embeddings=True, convert_to_numpy=True)
        _, ids = self._idx.search(q, k)
        out = []
        for cid in ids[0].tolist():
            row = self._chunks.iloc[cid]
            meta = json.loads(row["metadata_json"])
            title = meta.get("title", "?").strip()
            out.append(f"### MPEP {title}\n{row['text'][:1200]}")
        return "\n\n".join(out)

    def process(self, inputs: StepInput) -> StepOutput:
        for row in inputs:
            row["mpep_context"] = self._retrieve(row["prompt"])
        yield inputs


def split_think(raw: str) -> tuple[str, str]:
    """Apply NIM's 'assistant prefix = <think>' convention.

    Prepend `<think>\n` to the response, take everything before the first
    `</think>` as chain, treat the rest as answer. Scrub the answer of any
    stray paired `<think>...</think>` blocks AND any orphan `<think>`/`</think>`
    tokens — in practice the model emits an unclosed `<think>` opener about
    84% of the time on this teacher, wrapping the actual answer text.
    """
    decorated = "<think>\n" + raw
    if "</think>" not in decorated:
        return "", decorated.strip()
    chain, rest = decorated.split("</think>", 1)
    chain = chain.removeprefix("<think>\n").strip()
    rest = re.sub(r"<think>.*?</think>", "", rest, flags=re.DOTALL)
    rest = re.sub(r"</?think>", "", rest)
    # Model emits `<>` and stray `…` as section dividers in ~14% of answers.
    rest = re.sub(r"…?\s*<>\s*", "\n\n", rest)
    rest = re.sub(r"\n{3,}", "\n\n", rest)
    return chain, rest.strip()


def load_50_rows(seed: int = 42, n: int = 50) -> list[dict]:
    """Pick 50 rows balanced across families."""
    import random as _r
    with QUEUE.open() as f:
        rows = [json.loads(line) for line in f]
    by_fam: dict[str, list[dict]] = {}
    for r in rows:
        by_fam.setdefault(r["family"], []).append(r)
    _r.seed(seed)
    # Sample proportional to queue distribution: A1=1500, A2=1250, A4=1000, E1=750, E2=500
    # For 50: A1=15, A2=12, A4=10, E1=8, E2=5
    quotas = {"A1": 15, "A2": 12, "A4": 10, "E1": 8, "E2": 5}
    out = []
    for fam, q in quotas.items():
        out.extend(_r.sample(by_fam[fam], q))
    _r.shuffle(out)
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_50_rows()
    print(f"Loaded {len(rows)} rows", flush=True)
    family_counts = {fam: sum(1 for r in rows if r["family"] == fam) for fam in ["A1","A2","A4","E1","E2"]}
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

    with Pipeline(name="patent-corpus-v2-dry-run-50") as pipeline:
        loader = LoadDataFromDicts(
            name="loader",
            data=rows,
            batch_size=8,
        )
        retriever = MPEPRetriever(name="retriever", input_batch_size=8)
        generator = TextGeneration(
            name="generator",
            llm=llm,
            system_prompt=SYSTEM_PROMPT,
            template=USER_TEMPLATE,
            columns=["mpep_context", "prompt"],
            input_batch_size=8,
            num_generations=1,
        )
        keeper = KeepColumns(
            name="keeper",
            columns=["row_idx", "family", "prompt", "mpep_context", "generation"],
            input_batch_size=8,
        )

        loader >> retriever >> generator >> keeper

    print("Running pipeline...", flush=True)
    distiset = pipeline.run(use_cache=True)
    distiset.save_to_disk(str(OUT_DIR / "distiset"))
    print(f"Saved distiset to {OUT_DIR / 'distiset'}", flush=True)

    # Materialize to plain JSONL with chain/answer split.
    # distiset structure: Distiset → {config: DatasetDict → {split: Dataset}}
    out_jsonl = OUT_DIR / "out.jsonl"
    n_with_answer = 0
    n_total = 0
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
