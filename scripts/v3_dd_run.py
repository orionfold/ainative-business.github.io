"""v3 DataDesigner driver — runs Stage 2 (chain+answer LLM gen) over the
pre-built v3 seed dataset.

Inputs:
  /home/nvidia/data/aifn-corpus-v3/seed.parquet   (cols: row_idx, family, prompt, mpep_context)
  http://127.0.0.1:8000/v1                        (hardened NIM Nano-9B-v2)

Outputs (under ARTIFACT_PATH=/work/artifacts/<DATASET_NAME>/):
  - DD's parquet + metadata.json (resume checkpoint store)
  - On full completion: /work/<DATASET_NAME>.jsonl  (post-processed via split_think)

Env knobs (also via CLI flags for the c=8 probe vs overnight run):
  N_ROWS            : how many rows of the seed to generate (default 5000)
  ARTIFACT_PATH     : DD artifact root (default /work/artifacts)
  DATASET_NAME      : dataset folder name under ARTIFACT_PATH (default v3_full_5000)
  MAX_PAR           : LLM max_parallel_requests (default 4; probe 8)
  MAX_TOKENS        : LLM max_tokens (default 3500 per G3 finding for E1)

Run pattern (host invokes container with mounted /work):
  docker run --rm -d --name v3-run --network host \\
    -v /home/nvidia/data/aifn-corpus-v3:/work \\
    -e N_ROWS=5000 -e MAX_PAR=4 -e DATASET_NAME=v3_full_5000 \\
    dd-pilot:0.1 python /work/v3_dd_run.py

resume=IF_POSSIBLE means a re-run from the same artifact path will pick up
where it left off — survives NIM transients per pilot Phase 4 Part B evidence.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import data_designer.config as dd
from data_designer.config import LocalFileSeedSource
from data_designer.interface import DataDesigner, ResumeMode


SYSTEM_PROMPT = (
    "You are a senior US patent practitioner with 15 years of prosecution experience. "
    "Use the MPEP excerpts provided as your sole source of MPEP authority — do not cite "
    "any MPEP section that does not appear in the excerpts. Reason step-by-step inside "
    "<think>...</think> tags. After </think>, give a concise practitioner answer that "
    "directly addresses the task. Always emit an answer after </think> — do not leave "
    "the post-think section empty. Cite MPEP sections by their exact titles as shown in "
    "the excerpts. No producer-meta-commentary, no row-index references, no diversification "
    "reasoning."
)

USER_PROMPT_TEMPLATE = """## MPEP EXCERPTS (top-3 retrieved)
{{ mpep_context }}

## TASK
{{ prompt }}"""


def build_config(model_alias: str, max_par: int, max_tokens: int):
    b = dd.DataDesignerConfigBuilder(
        model_configs=[
            dd.ModelConfig(
                alias=model_alias,
                model="nvidia/nemotron-nano-9b-v2",
                provider="local-nim",
                inference_parameters=dd.ChatCompletionInferenceParams(
                    temperature=0.6,
                    top_p=0.95,
                    max_tokens=max_tokens,
                    timeout=300,
                    max_parallel_requests=max_par,
                ),
            ),
        ],
    )
    b.with_seed_dataset(LocalFileSeedSource(path="/work/seed.parquet"))
    b.add_column(dd.LLMTextColumnConfig(
        name="raw_generation",
        model_alias=model_alias,
        system_prompt=SYSTEM_PROMPT,
        prompt=USER_PROMPT_TEMPLATE,
    ))
    return b


def split_think(raw: str) -> tuple[str, str]:
    """NIM-prefix convention: assistant prompt starts with `<think>\n`, so the
    LLM response begins with reasoning text and emits `</think>` then the
    answer. Same helper as scripts/g3_distilabel_dry_run.py (canonical).
    """
    if not raw:
        return "", ""
    decorated = "<think>\n" + raw
    if "</think>" not in decorated:
        return "", decorated.strip()
    chain, rest = decorated.split("</think>", 1)
    chain = chain.removeprefix("<think>\n").strip()
    rest = re.sub(r"<think>.*?</think>", "", rest, flags=re.DOTALL)
    rest = re.sub(r"</?think>", "", rest)
    rest = re.sub(r"…?\s*<>\s*", "\n\n", rest)
    rest = re.sub(r"\n{3,}", "\n\n", rest)
    return chain, rest.strip()


def main():
    n_rows = int(os.environ.get("N_ROWS", "5000"))
    artifact_path = os.environ.get("ARTIFACT_PATH", "/work/artifacts")
    dataset_name = os.environ.get("DATASET_NAME", "v3_full_5000")
    max_par = int(os.environ.get("MAX_PAR", "4"))
    max_tokens = int(os.environ.get("MAX_TOKENS", "3500"))
    nim_endpoint = os.environ.get("NIM_ENDPOINT", "http://127.0.0.1:8000/v1")

    print(f"=== v3 DD driver ===", flush=True)
    print(f"  rows           : {n_rows}", flush=True)
    print(f"  artifact_path  : {artifact_path}", flush=True)
    print(f"  dataset_name   : {dataset_name}", flush=True)
    print(f"  max_parallel   : {max_par}", flush=True)
    print(f"  max_tokens     : {max_tokens}", flush=True)
    print(f"  nim_endpoint   : {nim_endpoint}", flush=True)

    t0 = time.time()
    b = build_config("nemotron-nano", max_par, max_tokens)
    dd_iface = DataDesigner(
        artifact_path=artifact_path,
        model_providers=[
            dd.ModelProvider(
                name="local-nim",
                endpoint=nim_endpoint,
                provider_type="openai",
                api_key="not_needed",
            ),
        ],
    )

    print("calling .create()...", flush=True)
    t1 = time.time()
    res = dd_iface.create(
        config_builder=b,
        num_records=n_rows,
        dataset_name=dataset_name,
        resume=ResumeMode.IF_POSSIBLE,
    )
    wall = time.time() - t1
    print(f"create returned in {wall:.1f}s ({n_rows/wall:.2f} rows/s)", flush=True)

    df = res.load_dataset()
    if df is None or not hasattr(df, "shape"):
        print("WARN: load_dataset returned nothing; cannot post-process to JSONL.", flush=True)
        return 1

    print(f"df.shape: {df.shape}, cols: {list(df.columns)}", flush=True)

    # Write two output shapes:
    #  (a) /work/<dataset_name>.jsonl — single file, full schema
    #      (row_idx, family, prompt, mpep_context, chain, answer, response, *_chars)
    #  (b) /work/<dataset_name>/chunks/chunk_<lo>_<hi>.jsonl — 1000-row chunks
    #      with the verifier's expected legacy schema (row_idx, family, prompt, response).
    #      Lets `.claude/skills/claude-corpus-synth/scripts/verify_chunk.py` run as-is.
    chunk_size = int(os.environ.get("CHUNK_SIZE", "1000"))
    chunk_dir = Path(f"/work/{dataset_name}/chunks")
    chunk_dir.mkdir(parents=True, exist_ok=True)

    out_jsonl = Path(f"/work/{dataset_name}.jsonl")
    n_total = 0
    n_with_answer = 0
    n_with_chain = 0
    by_family: dict[str, int] = {}
    chunk_buf: list[dict] = []
    chunk_idx = 0

    def flush_chunk(buf, idx):
        if not buf:
            return
        lo = idx * chunk_size
        hi = lo + len(buf) - 1
        chunk_path = chunk_dir / f"chunk_{lo}_{hi}.jsonl"
        with chunk_path.open("w") as cf:
            for rec in buf:
                cf.write(json.dumps({
                    "row_idx": rec["row_idx"],
                    "family": rec["family"],
                    "prompt": rec["prompt"],
                    "response": rec["response"],
                }) + "\n")
        print(f"  wrote {chunk_path} ({len(buf)} rows)", flush=True)

    df_sorted = df.sort_values("row_idx").reset_index(drop=True)
    with out_jsonl.open("w") as fout:
        for chunk_pos, (_, row) in enumerate(df_sorted.iterrows()):
            raw = row.get("raw_generation") or ""
            chain, answer = split_think(raw)
            response = f"<think>{chain}</think>{answer}" if chain or answer else ""
            rec = {
                "row_idx": int(row["row_idx"]),
                "family": row["family"],
                "prompt": row["prompt"],
                "mpep_context": row["mpep_context"],
                "chain": chain,
                "answer": answer,
                "response": response,
                "chain_chars": len(chain),
                "answer_chars": len(answer),
            }
            fout.write(json.dumps(rec) + "\n")
            chunk_buf.append(rec)
            n_total += 1
            if answer.strip() and not answer.startswith("<think>"):
                n_with_answer += 1
            if chain.strip():
                n_with_chain += 1
            by_family[row["family"]] = by_family.get(row["family"], 0) + 1

            if len(chunk_buf) >= chunk_size:
                flush_chunk(chunk_buf, chunk_idx)
                chunk_idx += 1
                chunk_buf = []
        flush_chunk(chunk_buf, chunk_idx)

    print(f"\nWrote {n_total} rows → {out_jsonl}", flush=True)
    print(f"  with non-empty chain  : {n_with_chain}/{n_total}", flush=True)
    print(f"  with non-empty answer : {n_with_answer}/{n_total}", flush=True)
    print(f"  by family             : {by_family}", flush=True)
    print(f"  chunks under          : {chunk_dir}", flush=True)
    print(f"=== total wall: {time.time()-t0:.1f}s ===", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
