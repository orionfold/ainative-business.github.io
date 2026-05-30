#!/usr/bin/env bash
# Phase 6.5 — merge LoRA adapter → HF-export → 20-q reasoning probe.
#
# Runs after scripts/p65_train_nemo_lora.sh STAGES=train finishes. Mirrors
# the Unsloth v3 sequence (train → merge → probe) so the resulting probe
# JSON is apples-to-apples comparable with
# probes/patent-strategist-v3-2026-05-21.json.
#
# Stages:
#   1. merge   — merge LoRA adapter into base via Megatron-Bridge
#                examples/peft/merge_lora.py  (output: merged-mcore/)
#   2. export  — round-trip merged Megatron → HF BF16
#                examples/conversion/convert_checkpoints.py export
#                (output: merged-hf-bf16/)
#   3. probe   — scripts/probe_reasoning.py with --max-new-tokens 2048
#                (output: probes/patent-strategist-v3-nemo-<date>.json)
#
# Env overrides:
#   STAGES           comma-separated subset (default "merge,export,probe")
#   CONTAINER_TRAIN  nemo container name   (default nemo-train)
#   CONTAINER_PROBE  HF container name     (default ps-train)
#   RUNS_ROOT        run-dir root          (default /home/nvidia/data/aifn-train-lora/p65-nemo)
#   ITER             LoRA iter to merge    (default: read latest_checkpointed_iteration.txt)
#   EXPECT_ITER      sanity-check value    (default 625; pass 0 to skip)
#   HF_MODEL         HF base model path    (default DeepSeek-R1-0528-Qwen3-8B snapshot on disk)
#   PROBE_OUT        output probe JSON     (default probes/patent-strategist-v3-nemo-<YYYY-MM-DD>.json)
#   MAX_NEW_TOKENS   probe gen budget      (default 2048 per HANDOFF length-clip fix)
set -euo pipefail

: "${CONTAINER_TRAIN:=nemo-train}"
: "${CONTAINER_PROBE:=ps-train}"
: "${RUNS_ROOT:=/home/nvidia/data/aifn-train-lora/p65-nemo}"
: "${HF_MODEL:=/home/nvidia/data/.hf-cache/hub/models--deepseek-ai--DeepSeek-R1-0528-Qwen3-8B/snapshots/6e8885a6ff5c1dc5201574c8fd700323f23c25fa}"
: "${STAGES:=merge,export,probe}"
: "${MAX_NEW_TOKENS:=2048}"
: "${EXPECT_ITER:=625}"

TRAIN_RUN_DIR="$RUNS_ROOT/runs-full"
MERGED_MCORE="$RUNS_ROOT/merged-mcore"
MERGED_HF="$RUNS_ROOT/merged-hf-bf16"
LOG_DIR="$RUNS_ROOT/logs"
mkdir -p "$LOG_DIR"

date_stamp="$(date +%F)"
: "${PROBE_OUT:=probes/patent-strategist-v3-nemo-${date_stamp}.json}"

# Resolve ITER from latest_checkpointed_iteration.txt if not set.
if [[ -z "${ITER:-}" ]]; then
    LATEST_FILE="$TRAIN_RUN_DIR/latest_checkpointed_iteration.txt"
    if [[ ! -f "$LATEST_FILE" ]]; then
        echo "[error] $LATEST_FILE missing — train didn't finish (or run-dir is wrong)" >&2
        exit 1
    fi
    ITER=$(cat "$LATEST_FILE" | tr -d '[:space:]')
fi
ITER_PADDED=$(printf "iter_%07d" "$ITER")
LORA_CKPT="$TRAIN_RUN_DIR/$ITER_PADDED"

if [[ "$EXPECT_ITER" -gt 0 && "$ITER" -ne "$EXPECT_ITER" ]]; then
    echo "[error] resolved ITER=$ITER ≠ EXPECT_ITER=$EXPECT_ITER — train may have stopped early." >&2
    echo "        Pass EXPECT_ITER=0 to override, or ITER=<n> to merge a specific checkpoint." >&2
    exit 1
fi

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_DIR/merge-probe.log"; }
has_stage() { [[ ",$STAGES," == *",$1,"* ]]; }

log "[plan] LoRA ckpt: $LORA_CKPT"
log "[plan] merged mcore: $MERGED_MCORE"
log "[plan] merged HF:    $MERGED_HF"
log "[plan] probe out:    $PROBE_OUT  (max-new-tokens=$MAX_NEW_TOKENS)"

# ─── Stage 1: merge (Megatron-Bridge LoRA → dense Megatron) ─────────────────
if has_stage merge; then
    if [[ ! -d "$LORA_CKPT" ]]; then
        echo "[error] LoRA checkpoint not found: $LORA_CKPT" >&2
        exit 1
    fi
    log "[merge] $LORA_CKPT -> $MERGED_MCORE"
    rm -rf "$MERGED_MCORE"
    docker exec -w /tmp "$CONTAINER_TRAIN" bash -lc "
      torchrun --nproc_per_node=1 /opt/Megatron-Bridge/examples/peft/merge_lora.py \
        --lora-checkpoint '$LORA_CKPT' \
        --hf-model-path   '$HF_MODEL' \
        --output          '$MERGED_MCORE'
    " 2>&1 | tee -a "$LOG_DIR/merge.log"
fi

# ─── Stage 2: export (Megatron → HF BF16) ───────────────────────────────────
if has_stage export; then
    if [[ ! -d "$MERGED_MCORE" ]]; then
        echo "[error] merged Megatron checkpoint not found: $MERGED_MCORE" >&2
        exit 1
    fi
    log "[export] $MERGED_MCORE -> $MERGED_HF"
    rm -rf "$MERGED_HF"
    docker exec -w /tmp "$CONTAINER_TRAIN" bash -lc "
      python3 /opt/Megatron-Bridge/examples/conversion/convert_checkpoints.py export \
        --hf-model      '$HF_MODEL' \
        --megatron-path '$MERGED_MCORE' \
        --hf-path       '$MERGED_HF'
    " 2>&1 | tee -a "$LOG_DIR/export.log"
fi

# ─── Stage 3: probe (HF transformers, 20-q reasoning preservation) ──────────
if has_stage probe; then
    if [[ ! -d "$MERGED_HF" ]]; then
        echo "[error] merged HF model not found: $MERGED_HF" >&2
        exit 1
    fi
    log "[probe] 20-q reasoning probe on merged HF model"
    docker exec -w /home/nvidia/ainative-business.github.io "$CONTAINER_PROBE" bash -lc "
      python3 scripts/probe_reasoning.py \
        --model '$MERGED_HF' \
        --probe-set probes/reasoning-preservation-20q.jsonl \
        --output  '$PROBE_OUT' \
        --max-new-tokens $MAX_NEW_TOKENS
    " 2>&1 | tee -a "$LOG_DIR/probe.log"
    log "[probe] wrote $PROBE_OUT"
fi

log "[done] merge+export+probe complete"
log "[next] compare $PROBE_OUT vs probes/patent-strategist-v3-2026-05-21.json (Unsloth baseline)"
log "[next] update ideas/uber-local-corpus-gen-decision.md Q4 with train-layer pick"
