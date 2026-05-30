#!/usr/bin/env bash
# Phase 6.5 — NeMo Framework LoRA SFT orchestrator.
#
# Mirrors scripts/g3_train_first_lora.sh stage layout, but inside the
# nemo:26.04.00 container with Megatron-Bridge as the trainer.
#
# Stages:
#   1. convert   — HF → Megatron-Core checkpoint (one-shot, idempotent if dir exists)
#   2. dataset   — reshape v3 corpus into {input, output} JSONL
#   3. smoke     — 10-iter train run (sanity: recipe wires up, gradients flow)
#   4. train     — full production train (default 625 iters = 5000 rows × 2 epochs)
#   5. handoff   — print paths the next step (merge / probe) can pick up
#
# Env overrides:
#   STAGES        comma-separated subset (default "convert,dataset,smoke")
#   CONTAINER     docker container name (default nemo-train)
#   HF_MODEL      HF model path (default DeepSeek-R1-0528-Qwen3-8B on disk)
#   RUNS_ROOT     run-dir root (default /home/nvidia/data/aifn-train-lora/p65-nemo)
#   TRAIN_ITERS   iters for the full train stage (default 625)
#   SMOKE_ITERS   iters for the smoke stage (default 10)
set -euo pipefail

: "${CONTAINER:=nemo-train}"
: "${HF_MODEL:=/home/nvidia/data/.hf-cache/hub/models--deepseek-ai--DeepSeek-R1-0528-Qwen3-8B/snapshots/6e8885a6ff5c1dc5201574c8fd700323f23c25fa}"
: "${RUNS_ROOT:=/home/nvidia/data/aifn-train-lora/p65-nemo}"
: "${STAGES:=convert,dataset,smoke}"
: "${TRAIN_ITERS:=625}"
: "${SMOKE_ITERS:=10}"

MCORE_BASE="$RUNS_ROOT/mcore-base"
DATASET_DIR="$RUNS_ROOT/dataset"
SMOKE_RUN_DIR="$RUNS_ROOT/runs-smoke"
TRAIN_RUN_DIR="$RUNS_ROOT/runs-full"
LOG_DIR="$RUNS_ROOT/logs"
mkdir -p "$LOG_DIR"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_DIR/orchestrator.log"; }
in_container() { docker exec -w /tmp "$CONTAINER" "$@"; }

has_stage() {
    [[ ",$STAGES," == *",$1,"* ]]
}

# ─── Stage 1: convert ───────────────────────────────────────────────────────
if has_stage convert; then
    if [[ -d "$MCORE_BASE/iter_0000000" ]]; then
        log "[convert] skipping — $MCORE_BASE/iter_0000000 already exists"
    else
        log "[convert] HF -> Megatron-Core (this writes ~16 GB to $MCORE_BASE)"
        in_container bash -lc "
          torchrun --nproc_per_node=1 /home/nvidia/ainative-business.github.io/scripts/p65_convert_hf_to_mcore.py \
            --hf-model '$HF_MODEL' \
            --megatron-path '$MCORE_BASE' \
            --torch-dtype bfloat16
        " 2>&1 | tee -a "$LOG_DIR/convert.log"
    fi
fi

# ─── Stage 2: dataset ───────────────────────────────────────────────────────
if has_stage dataset; then
    if [[ -f "$DATASET_DIR/training.jsonl" && -f "$DATASET_DIR/validation.jsonl" ]]; then
        log "[dataset] skipping — training.jsonl + validation.jsonl already exist"
    else
        log "[dataset] reshape v3 corpus into NeMo {input,output} schema"
        # Runs on host (pure-python, no GPU); doesn't need the container.
        python3 /home/nvidia/ainative-business.github.io/scripts/p65_v3_to_nemo_jsonl.py 2>&1 | tee -a "$LOG_DIR/dataset.log"
    fi
fi

# ─── Stage 3: smoke ─────────────────────────────────────────────────────────
if has_stage smoke; then
    log "[smoke] 10-iter sanity train (recipe wires up, gradients flow)"
    rm -rf "$SMOKE_RUN_DIR"
    mkdir -p "$SMOKE_RUN_DIR"
    in_container bash -lc "
      cd /tmp
      torchrun --nproc_per_node=1 /home/nvidia/ainative-business.github.io/scripts/p65_train_nemo_lora.py \
        --hf-model '$HF_MODEL' \
        --pretrained-mcore '$MCORE_BASE' \
        --dataset-root '$DATASET_DIR' \
        --run-dir '$SMOKE_RUN_DIR' \
        --smoke $SMOKE_ITERS
    " 2>&1 | tee -a "$LOG_DIR/smoke.log"
fi

# ─── Stage 4: train ─────────────────────────────────────────────────────────
if has_stage train; then
    log "[train] full production train ($TRAIN_ITERS iters)"
    mkdir -p "$TRAIN_RUN_DIR"
    in_container bash -lc "
      cd /tmp
      torchrun --nproc_per_node=1 /home/nvidia/ainative-business.github.io/scripts/p65_train_nemo_lora.py \
        --hf-model '$HF_MODEL' \
        --pretrained-mcore '$MCORE_BASE' \
        --dataset-root '$DATASET_DIR' \
        --run-dir '$TRAIN_RUN_DIR' \
        --train-iters $TRAIN_ITERS
    " 2>&1 | tee -a "$LOG_DIR/train.log"
fi

# ─── Stage 5: handoff ───────────────────────────────────────────────────────
if has_stage handoff; then
    log "[handoff] paths for next step:"
    log "   mcore base:   $MCORE_BASE"
    log "   dataset:      $DATASET_DIR"
    log "   smoke run:    $SMOKE_RUN_DIR"
    log "   train run:    $TRAIN_RUN_DIR"
    log "   logs:         $LOG_DIR/"
fi
