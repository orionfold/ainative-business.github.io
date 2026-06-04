#!/usr/bin/env bash
# C4 runtime env for the astrodynamics RLVR run — source before `fieldkit arena autonomy on`.
# The vLLM lane runs in the pinned aarch64+CUDA-13 image `vllm-node:latest` (no host vllm binary),
# so FK_RL_SERVE_CMD wraps the launch in `docker run` and FK_RL_STOP_CMD is the container teardown
# (the default host `pkill` can't reach a process inside a container).
#
# Single-tree trick: base model, init-LoRA, AND the per-step work_dir all live under
# $AROOT, bind-mounted at its own host path → every {adapter} (a host abs path the loop
# substitutes) resolves identically inside the container.
#
#   mkdir -p /home/nvidia/data/astro-train-lora/p65-nemo/rl-work   # work_dir (run as nvidia, not root)
#   source /home/nvidia/data/astro-train-lora/p65-nemo/fk-rl-env.sh
#   # bring up fieldkit[rl] in a host torch venv, then: fieldkit arena autonomy on

AROOT=/home/nvidia/data/astro-train-lora/p65-nemo

export FK_RL_VLLM_URL=http://localhost:8000/v1
export FK_RL_BASE_MODEL=$AROOT/merged-hf-bf16          # the merged SFT model = the served base
export FK_RL_ADAPTER_INIT=$AROOT/init-lora-r16         # zero-init policy LoRA (step-0 == SFT)
export FK_RL_WORK_DIR=$AROOT/rl-work                   # per-step adapters land here (same mounted tree)
export FK_RL_LORA_NAME=policy                          # the served LoRA id == the chat `model`
export FK_RL_MAX_TOKENS=2048                           # AV-R1: keep the <think>+\boxed{} budget generous
export FK_RL_GPU_UTIL=0.5                              # one-lane envelope (RV-10 / unified-memory OOM)
export FK_RL_MAX_MODEL_LEN=4096                        # ~70-tok prompt + 2048 completion, headroom
export FK_RL_HELDOUT_TEMP=0.2

# --- serve: one `docker run` (Popen argv, NOT a shell — no chaining). {adapter}/{port}/{name} substituted. ---
export FK_RL_SERVE_CMD="docker run --rm --name vllm-rl --gpus all --network host -e HF_HUB_OFFLINE=1 -v $AROOT:$AROOT --entrypoint vllm vllm-node:latest serve $AROOT/merged-hf-bf16 --port {port} --max-model-len 4096 --gpu-memory-utilization 0.5 --enable-lora --lora-modules {name}={adapter} --max-lora-rank 32"

# --- stop: container teardown (runs via shell=True; the built-in 3s settle follows). ---
export FK_RL_STOP_CMD="docker rm -f vllm-rl"
