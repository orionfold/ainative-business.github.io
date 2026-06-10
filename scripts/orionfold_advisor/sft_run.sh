#!/usr/bin/env bash
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
#
# Advisor 4B real SFT run (plan step 4 of _IDEAS/advisor-4b-sft-lane-v1.md).
# Reuses the step-2 PROVEN export path and its artifacts:
#   - mcore base conversion:  advisor-4b-smoke/mcore-base (same base snapshot)
#   - shadow HF base dir:     advisor-4b-smoke/hf-base-fixed (GenerationConfig
#     strict-save fix; used for merge/export/gguf --hf-model)
#
# Stages (comma-separated via STAGES env, default all):
#   bake     777-row corpus -> {input,output} jsonl via the base chat template
#            (enable_thinking=False; stratified val split, default 64 rows)
#   train    LoRA SFT (sft_train_nemo_lora.py; eval_iters sized to the val split)
#   merge    LoRA -> dense Megatron (bridge examples/peft/merge_lora.py)
#   export   merged Megatron -> HF BF16 (shadow base dir as --hf-model)
#   gguf     merged HF -> GGUF Q8_0 (local llama.cpp convert)
#
# GPU note: tear down the 30B serving lane (guarded LaneTruth) before `train`.
set -euo pipefail

: "${CONTAINER:=nemo-train}"
: "${HF_SNAPSHOT:=$(ls -d /home/nvidia/data/.hf-cache/hub/models--nvidia--NVIDIA-Nemotron-3-Nano-4B-BF16/snapshots/*/ 2>/dev/null | head -1)}"
: "${SMOKE_ROOT:=/home/nvidia/data/aifn-train-lora/advisor-4b-smoke}"
: "${RUNS_ROOT:=/home/nvidia/data/aifn-train-lora/advisor-4b-sft}"
: "${CORPUS_VERSION:=v0.2}"
: "${STAGES:=bake,train,merge,export,gguf}"
: "${TRAIN_ITERS:=270}"
: "${EVAL_ITERS:=8}"
: "${VAL_ROWS:=64}"
: "${GLOBAL_BATCH:=8}"
: "${LLAMA_CPP:=/home/nvidia/llama.cpp}"

REPO=/home/nvidia/ainative-business.github.io
CORPUS="$RUNS_ROOT/corpus/advisor-sft-corpus-${CORPUS_VERSION}.jsonl"
MCORE_BASE="$SMOKE_ROOT/mcore-base"
SHADOW_HF="$SMOKE_ROOT/hf-base-fixed"
if [[ "$CORPUS_VERSION" == "v0.1" ]]; then
    # v0.1 artifacts predate version-suffixed dirs; keep their original paths.
    DATASET_DIR="$RUNS_ROOT/dataset"
    RUN_DIR="$RUNS_ROOT/runs-sft"
    MERGED_MCORE="$RUNS_ROOT/merged-mcore"
    MERGED_HF="$RUNS_ROOT/merged-hf-bf16"
else
    DATASET_DIR="$RUNS_ROOT/dataset-${CORPUS_VERSION}"
    RUN_DIR="$RUNS_ROOT/runs-sft-${CORPUS_VERSION}"
    MERGED_MCORE="$RUNS_ROOT/merged-mcore-${CORPUS_VERSION}"
    MERGED_HF="$RUNS_ROOT/merged-hf-bf16-${CORPUS_VERSION}"
fi
GGUF_OUT="$RUNS_ROOT/NVIDIA-Nemotron-3-Nano-4B-advisor-sft-${CORPUS_VERSION}-Q8_0.gguf"
LOG_DIR="$RUNS_ROOT/logs"
mkdir -p "$LOG_DIR"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_DIR/orchestrator.log"; }
in_container() { docker exec -w /tmp "$CONTAINER" "$@"; }
has_stage() { [[ ",$STAGES," == *",$1,"* ]]; }

[[ -n "$HF_SNAPSHOT" ]] || { echo "[error] no 4B BF16 snapshot found in HF cache" >&2; exit 1; }
[[ -f "$CORPUS" ]] || { echo "[error] SFT corpus missing at $CORPUS (plan step 3)" >&2; exit 1; }
[[ -d "$MCORE_BASE/iter_0000000" ]] || { echo "[error] proven mcore base missing at $MCORE_BASE" >&2; exit 1; }
[[ -d "$SHADOW_HF" ]] || { echo "[error] shadow HF base dir missing at $SHADOW_HF" >&2; exit 1; }
(( VAL_ROWS >= EVAL_ITERS * GLOBAL_BATCH )) || { echo "[error] VAL_ROWS < EVAL_ITERS*GLOBAL_BATCH (validation would wedge)" >&2; exit 1; }
log "[plan] snapshot:  $HF_SNAPSHOT"
log "[plan] corpus:    $CORPUS"
log "[plan] runs root: $RUNS_ROOT  iters=$TRAIN_ITERS eval_iters=$EVAL_ITERS val_rows=$VAL_ROWS"

if has_stage bake; then
    if [[ -f "$DATASET_DIR/training.jsonl" ]]; then
        log "[bake] skipping — training.jsonl exists"
    else
        log "[bake] corpus -> chat-template {input,output} ($DATASET_DIR)"
        in_container bash -lc "
          cd $REPO/scripts/orionfold_advisor && python3 sft_corpus.py --bake \
            --hf-model '$HF_SNAPSHOT' \
            --out '$CORPUS' \
            --bake-out '$DATASET_DIR' \
            --val-rows $VAL_ROWS
        " 2>&1 | tee -a "$LOG_DIR/bake.log"
    fi
fi

if has_stage train; then
    log "[train] $TRAIN_ITERS-iter LoRA SFT -> $RUN_DIR"
    in_container bash -lc "
      torchrun --nproc_per_node=1 $REPO/scripts/orionfold_advisor/sft_train_nemo_lora.py \
        --hf-model '$HF_SNAPSHOT' \
        --pretrained-mcore '$MCORE_BASE' \
        --dataset-root '$DATASET_DIR' \
        --run-dir '$RUN_DIR' \
        --train-iters $TRAIN_ITERS \
        --eval-iters $EVAL_ITERS \
        --global-batch $GLOBAL_BATCH
    " 2>&1 | tee -a "$LOG_DIR/train.log"
fi

if has_stage merge; then
    ITER_FILE="$RUN_DIR/latest_checkpointed_iteration.txt"
    [[ -f "$ITER_FILE" ]] || { echo "[error] no checkpoint iteration file at $ITER_FILE" >&2; exit 1; }
    ITER=$(cat "$ITER_FILE")
    LORA_CKPT=$(printf '%s/iter_%07d' "$RUN_DIR" "$ITER")
    log "[merge] $LORA_CKPT -> $MERGED_MCORE"
    rm -rf "$MERGED_MCORE"
    in_container bash -lc "
      torchrun --nproc_per_node=1 /opt/Megatron-Bridge/examples/peft/merge_lora.py \
        --lora-checkpoint '$LORA_CKPT' \
        --hf-model-path   '$HF_SNAPSHOT' \
        --output          '$MERGED_MCORE'
    " 2>&1 | tee -a "$LOG_DIR/merge.log"
fi

if has_stage export; then
    [[ -d "$MERGED_MCORE" ]] || { echo "[error] $MERGED_MCORE missing" >&2; exit 1; }
    log "[export] $MERGED_MCORE -> $MERGED_HF (shadow base: $SHADOW_HF)"
    rm -rf "$MERGED_HF"
    in_container bash -lc "
      python3 /opt/Megatron-Bridge/examples/conversion/convert_checkpoints.py export \
        --hf-model      '$SHADOW_HF' \
        --megatron-path '$MERGED_MCORE' \
        --hf-path       '$MERGED_HF'
    " 2>&1 | tee -a "$LOG_DIR/export.log"
fi

if has_stage gguf; then
    [[ -d "$MERGED_HF" ]] || { echo "[error] $MERGED_HF missing" >&2; exit 1; }
    log "[gguf] $MERGED_HF -> $GGUF_OUT (Q8_0)"
    in_container bash -lc "
      PYTHONPATH=$LLAMA_CPP/gguf-py python3 $LLAMA_CPP/convert_hf_to_gguf.py \
        '$MERGED_HF' --outfile '$GGUF_OUT' --outtype q8_0
    " 2>&1 | tee -a "$LOG_DIR/gguf.log"
    log "[gguf] $(du -h "$GGUF_OUT" | cut -f1) written"
fi

log "[done] stages: $STAGES (corpus $CORPUS_VERSION)"
log "[next] launch via guarded LaneTruth (lane recipe pointing at $GGUF_OUT) + post-SFT receipts"
