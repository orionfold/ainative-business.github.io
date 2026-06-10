#!/usr/bin/env bash
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
#
# Advisor 4B export-path smoke (plan step 2 of _IDEAS/advisor-4b-sft-lane-v1.md).
# Proves the round trip BEFORE any corpus investment:
#   HF BF16 -> mcore -> 10-step LoRA -> merge -> HF export -> GGUF Q8_0
# Lane launch + preflight stay Arena-side (guarded LaneTruth), not in here.
#
# Stages (comma-separated via STAGES env, default all batch stages):
#   container  ensure nemo-train exists + is running
#   convert    HF -> Megatron-Core base (p65_convert_hf_to_mcore.py, generic)
#   dataset    toy 50-row {input,output} jsonl via the base chat template
#   train      10-step LoRA smoke (sft_train_nemo_lora.py)
#   merge      LoRA -> dense Megatron (bridge examples/peft/merge_lora.py)
#   export     merged Megatron -> HF BF16 (bridge convert_checkpoints.py)
#   gguf       merged HF -> GGUF Q8_0 (local llama.cpp convert, gguf-py on PYTHONPATH)
#
# GPU note: tear down the serving lane (guarded LaneTruth) before `train`.
set -euo pipefail

: "${CONTAINER:=nemo-train}"
: "${IMAGE:=nvcr.io/nvidia/nemo:26.04.00}"
: "${HF_SNAPSHOT:=$(ls -d /home/nvidia/data/.hf-cache/hub/models--nvidia--NVIDIA-Nemotron-3-Nano-4B-BF16/snapshots/*/ 2>/dev/null | head -1)}"
: "${RUNS_ROOT:=/home/nvidia/data/aifn-train-lora/advisor-4b-smoke}"
: "${STAGES:=container,convert,dataset,train,merge,export,gguf}"
: "${SMOKE_ITERS:=10}"
: "${LLAMA_CPP:=/home/nvidia/llama.cpp}"

REPO=/home/nvidia/ainative-business.github.io
MCORE_BASE="$RUNS_ROOT/mcore-base"
DATASET_DIR="$RUNS_ROOT/dataset"
RUN_DIR="$RUNS_ROOT/runs-smoke"
MERGED_MCORE="$RUNS_ROOT/merged-mcore"
MERGED_HF="$RUNS_ROOT/merged-hf-bf16"
GGUF_OUT="$RUNS_ROOT/NVIDIA-Nemotron-3-Nano-4B-sftsmoke-Q8_0.gguf"
LOG_DIR="$RUNS_ROOT/logs"
mkdir -p "$LOG_DIR"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_DIR/orchestrator.log"; }
in_container() { docker exec -w /tmp "$CONTAINER" "$@"; }
has_stage() { [[ ",$STAGES," == *",$1,"* ]]; }

[[ -n "$HF_SNAPSHOT" ]] || { echo "[error] no 4B BF16 snapshot found in HF cache" >&2; exit 1; }
log "[plan] snapshot:  $HF_SNAPSHOT"
log "[plan] runs root: $RUNS_ROOT"

if has_stage container; then
    if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
        if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
            log "[container] starting existing $CONTAINER"
            docker start "$CONTAINER"
        else
            log "[container] creating $CONTAINER from $IMAGE"
            docker run -d --name "$CONTAINER" --gpus all --ipc=host \
                --ulimit memlock=-1 --ulimit stack=67108864 \
                -v /home/nvidia:/home/nvidia \
                -e HF_HOME=/home/nvidia/data/.hf-cache \
                -e HF_HUB_CACHE=/home/nvidia/data/.hf-cache/hub \
                "$IMAGE" sleep infinity
        fi
    fi
    log "[container] $CONTAINER up"
fi

if has_stage convert; then
    if [[ -d "$MCORE_BASE/iter_0000000" ]]; then
        log "[convert] skipping — $MCORE_BASE/iter_0000000 exists"
    else
        log "[convert] HF -> Megatron-Core ($MCORE_BASE)"
        in_container bash -lc "
          torchrun --nproc_per_node=1 $REPO/scripts/p65_convert_hf_to_mcore.py \
            --hf-model '$HF_SNAPSHOT' \
            --megatron-path '$MCORE_BASE' \
            --torch-dtype bfloat16 \
            --trust-remote-code
        " 2>&1 | tee -a "$LOG_DIR/convert.log"
    fi
fi

if has_stage dataset; then
    if [[ -f "$DATASET_DIR/training.jsonl" ]]; then
        log "[dataset] skipping — training.jsonl exists"
    else
        log "[dataset] toy 50-row build via base chat template"
        in_container bash -lc "
          python3 $REPO/scripts/orionfold_advisor/sft_smoke_dataset.py \
            --hf-model '$HF_SNAPSHOT' \
            --out-dir '$DATASET_DIR'
        " 2>&1 | tee -a "$LOG_DIR/dataset.log"
    fi
fi

if has_stage train; then
    log "[train] $SMOKE_ITERS-step LoRA smoke -> $RUN_DIR"
    in_container bash -lc "
      torchrun --nproc_per_node=1 $REPO/scripts/orionfold_advisor/sft_train_nemo_lora.py \
        --hf-model '$HF_SNAPSHOT' \
        --pretrained-mcore '$MCORE_BASE' \
        --dataset-root '$DATASET_DIR' \
        --run-dir '$RUN_DIR' \
        --smoke $SMOKE_ITERS
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
    log "[export] $MERGED_MCORE -> $MERGED_HF"
    rm -rf "$MERGED_HF"
    in_container bash -lc "
      python3 /opt/Megatron-Bridge/examples/conversion/convert_checkpoints.py export \
        --hf-model      '$HF_SNAPSHOT' \
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

log "[done] stages: $STAGES"
log "[next] launch via guarded LaneTruth (new recipe pointing at $GGUF_OUT) + 8-row preflight"
