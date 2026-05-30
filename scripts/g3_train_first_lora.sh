#!/usr/bin/env bash
# Patent-Strategist W3 LoRA training orchestrator.
#
# Mirrors scripts/g3_build_first_quant.sh patterns (env-overridable; staged).
# Stages:
#   1. prepare  — sanity-check inputs, ensure container & deps, log env
#   2. train    — run scripts/g3_train_first_lora.py (TRL SFTTrainer)
#   3. merge    — peft merge_and_unload → BF16 safetensors via g3_merge_adapter.py
#   4. handoff  — print path that g3_build_first_quant.sh can pick up as MODEL_DIR
#
# All env vars accepted by the trainer are forwarded; this script just
# wires defaults, container exec, and run-dir layout.
#
# Usage:
#   # Smoke (50-row Day-1, ~20min wall):
#   DATASET=/home/nvidia/data/corpus/patent-smoke-50.jsonl \
#   RUN_NAME=smoke-2026-05-17 \
#   LORA_R=8 LORA_ALPHA=16 LR=3e-5 MAX_STEPS=200 CHECKPOINT_EVERY=50 \
#   ./scripts/g3_train_first_lora.sh
#
#   # Production (~25k row overnight):
#   DATASET=/home/nvidia/data/corpus/patent-train-25k.jsonl \
#   RUN_NAME=patent-strategist-v1-2026-05-19 \
#   EPOCHS=2 CHECKPOINT_EVERY=200 ./scripts/g3_train_first_lora.sh
#
#   # Stage skip:
#   STAGES=train,merge ./scripts/g3_train_first_lora.sh
set -euo pipefail

# ─── Inputs ──────────────────────────────────────────────────────────────────
: "${DATASET:?DATASET env var required (jsonl with {'text': ...})}"
: "${RUN_NAME:=lora-$(date +%Y%m%d-%H%M%S)}"
: "${MODEL_ID:=deepseek-ai/DeepSeek-R1-0528-Qwen3-8B}"
: "${CONTAINER:=ps-train}"
: "${STAGES:=prepare,train,merge,handoff}"

# Resolve run-dir layout.
# Default to a bind-mounted host path so the trainer's outputs survive container exit
# — the in-container /tmp is NOT shared with the host on ps-train, and using it
# stranded the entire smoke run on 2026-05-17 (recovered via `docker exec mv`).
: "${RUNS_ROOT:=/home/nvidia/data/aifn-train-lora}"
RUN_DIR="$RUNS_ROOT/$RUN_NAME"
ADAPTER_DIR="$RUN_DIR/adapter"
MERGED_DIR="$RUN_DIR/merged-bf16"
LOG_FILE="$RUN_DIR/train.log"
mkdir -p "$RUN_DIR" "$ADAPTER_DIR" "$MERGED_DIR"

# ─── Helpers ─────────────────────────────────────────────────────────────────
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE" ; }
in_container() { docker exec -i "$CONTAINER" "$@" ; }
has_stage() { [[ ",$STAGES," == *",$1,"* ]] ; }

# ─── Stage 1: prepare ────────────────────────────────────────────────────────
if has_stage prepare ; then
  log "=== prepare ==="
  log "RUN_DIR=$RUN_DIR"
  log "MODEL_ID=$MODEL_ID"
  log "DATASET=$DATASET"
  log "CONTAINER=$CONTAINER"

  if ! docker ps --filter "name=^${CONTAINER}\$" --format '{{.Names}}' | grep -q "^${CONTAINER}\$" ; then
    log "ERROR: container '$CONTAINER' is not running. Start it with:"
    log "  docker start $CONTAINER  # or run from pytorch:25.11-py3"
    exit 1
  fi

  if [[ ! -f "$DATASET" ]] ; then
    log "ERROR: DATASET=$DATASET does not exist"
    exit 1
  fi

  # Sanity: <think>...</think> structure (spec §4 Layer 2)
  N_ROWS=$(wc -l < "$DATASET")
  N_THINK=$(grep -c '<think>' "$DATASET" || true)
  log "dataset rows=$N_ROWS  <think>-bearing=$N_THINK"
  if [[ "$N_THINK" -lt "$N_ROWS" ]] ; then
    log "WARNING: $((N_ROWS - N_THINK)) rows missing <think> markers"
  fi

  # Capture env snapshot
  env | grep -E '^(MODEL_ID|DATASET|RUN_NAME|LORA_|LR|EPOCHS|MAX_STEPS|BATCH_SIZE|GRAD_ACCUM|CHECKPOINT_EVERY|PROBE_EVERY|WARMUP_RATIO|SEED|MAX_SEQ_LENGTH|STAGES)=' \
    | sort > "$RUN_DIR/env.snapshot" || true
  log "env snapshot -> $RUN_DIR/env.snapshot"
fi

# ─── Stage 2: train ──────────────────────────────────────────────────────────
if has_stage train ; then
  log "=== train ==="
  # Forward all relevant env vars into the container
  in_container env \
    MODEL_ID="$MODEL_ID" \
    DATASET="$DATASET" \
    OUTPUT_DIR="$ADAPTER_DIR" \
    RUNS_DIR="$RUN_DIR/runs" \
    LORA_TARGETS="${LORA_TARGETS:-q_proj,k_proj,v_proj,o_proj}" \
    LORA_R="${LORA_R:-16}" \
    LORA_ALPHA="${LORA_ALPHA:-32}" \
    LORA_DROPOUT="${LORA_DROPOUT:-0.05}" \
    LR="${LR:-1e-4}" \
    EPOCHS="${EPOCHS:-2}" \
    MAX_STEPS="${MAX_STEPS:-0}" \
    BATCH_SIZE="${BATCH_SIZE:-2}" \
    GRAD_ACCUM="${GRAD_ACCUM:-8}" \
    CHECKPOINT_EVERY="${CHECKPOINT_EVERY:-200}" \
    PROBE_EVERY="${PROBE_EVERY:-0}" \
    WARMUP_RATIO="${WARMUP_RATIO:-0.05}" \
    SEED="${SEED:-42}" \
    MAX_SEQ_LENGTH="${MAX_SEQ_LENGTH:-2048}" \
    python /home/nvidia/ainative-business.github.io/scripts/g3_train_first_lora.py 2>&1 | tee -a "$LOG_FILE"

  log "train stage done"
  log "  adapter: $ADAPTER_DIR"
  log "  runs:    $RUN_DIR/runs"
fi

# ─── Stage 3: merge ──────────────────────────────────────────────────────────
if has_stage merge ; then
  log "=== merge ==="
  if [[ ! -f "$ADAPTER_DIR/adapter_config.json" ]] ; then
    log "ERROR: $ADAPTER_DIR/adapter_config.json missing — train stage didn't write an adapter"
    exit 1
  fi
  in_container env \
    MODEL_ID="$MODEL_ID" \
    ADAPTER_DIR="$ADAPTER_DIR" \
    MERGED_DIR="$MERGED_DIR" \
    python /home/nvidia/ainative-business.github.io/scripts/g3_merge_adapter.py 2>&1 | tee -a "$LOG_FILE"

  log "merge stage done"
  log "  merged BF16: $MERGED_DIR"
fi

# ─── Stage 4: handoff ────────────────────────────────────────────────────────
if has_stage handoff ; then
  log "=== handoff ==="
  log "Ready for g3_build_first_quant.sh:"
  log "  MODEL_DIR=$MERGED_DIR  SLUG=patent-strategist-qwen3-8b-v1"
  log ""
  log "Or attach adapter directly to base for evaluation:"
  log "  MODEL_ID=$MODEL_ID  ADAPTER=$ADAPTER_DIR"
fi

log "DONE."
