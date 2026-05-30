#!/usr/bin/env bash
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
#
# probe_model.sh — single-repo four-axis classifier for hf-model-scout
#
# Usage:
#   probe_model.sh <repo-id> <run-dir>
#
# Examples:
#   probe_model.sh equall/Saul-7B-Instruct-v1 /tmp/hf-scout/2026-05-14/legal-7B
#
# Downloads tokenizer_config.json + README.md + config.json (collectively ≤200 KB),
# classifies along four axes (chat_format, license, training_type, llama_cpp_compat),
# emits one JSON per probe at <run-dir>/probes/<repo-slug>/probe.json.
#
# Exits 0 always; failures land in probe.json's `warnings` array. The skill's
# downstream ranker decides what to do with them.

set -u  # -e off — we want to keep going past per-file fetch failures

REPO="${1:?repo-id required (e.g. equall/Saul-7B-Instruct-v1)}"
RUN_DIR="${2:?run-dir required (e.g. /tmp/hf-scout/2026-05-14/legal-7B)}"

HF="${HF_CLI:-/tmp/fk-test/bin/hf}"
test -x "$HF" || { echo "FATAL: hf CLI not at $HF" >&2; exit 2; }

REPO_SLUG="${REPO//\//__}"
PROBE_DIR="$RUN_DIR/probes/$REPO_SLUG"
mkdir -p "$PROBE_DIR"

WARNINGS=()
warn() { WARNINGS+=("$1"); }

# --- 1. Fetch the three metadata files -----------------------------------------

fetch_one() {
  local filename="$1"
  if ! "$HF" download "$REPO" "$filename" --local-dir "$PROBE_DIR" >/dev/null 2>&1; then
    warn "missing-$filename"
    return 1
  fi
}

fetch_one tokenizer_config.json
fetch_one README.md
fetch_one config.json

# --- 2. Classify chat_format ---------------------------------------------------

CHAT_FORMAT="UNKNOWN"
CHAT_DETECT_SIGNAL=""

if [[ -r "$PROBE_DIR/tokenizer_config.json" ]]; then
  TPL=$(python3 -c "
import json, sys
try:
    d = json.load(open('$PROBE_DIR/tokenizer_config.json'))
    print(d.get('chat_template') or '')
except Exception:
    print('')
")
  if [[ -z "$TPL" ]]; then
    CHAT_FORMAT="MISSING"
    CHAT_DETECT_SIGNAL="no chat_template field in tokenizer_config.json"
  else
    # Pattern-match against the chat-formats table.
    # Order matters: more-specific patterns first.
    if   [[ "$TPL" == *"<<SYS>>"* && "$TPL" == *"[INST]"* ]]; then CHAT_FORMAT="llama-2"; CHAT_DETECT_SIGNAL="[INST] + <<SYS>>"
    elif [[ "$TPL" == *"<|start_header_id|>"* ]];               then CHAT_FORMAT="llama-3"; CHAT_DETECT_SIGNAL="<|start_header_id|>"
    elif [[ "$TPL" == *"<|im_start|>"* ]];                      then CHAT_FORMAT="chatml"; CHAT_DETECT_SIGNAL="<|im_start|>"
    elif [[ "$TPL" == *"<start_of_turn>"* ]];                   then CHAT_FORMAT="gemma"; CHAT_DETECT_SIGNAL="<start_of_turn>"
    elif [[ "$TPL" == *"<|user|>"* && "$TPL" == *"<|end|>"* ]]; then CHAT_FORMAT="phi-3"; CHAT_DETECT_SIGNAL="<|user|> + <|end|>"
    elif [[ "$TPL" == *"<|user|>"* ]];                          then CHAT_FORMAT="zephyr"; CHAT_DETECT_SIGNAL="<|user|>"
    elif [[ "$TPL" == *"GPT4 Correct User:"* ]];                then CHAT_FORMAT="openchat"; CHAT_DETECT_SIGNAL="GPT4 Correct User:"
    elif [[ "$TPL" == *"USER:"* && "$TPL" == *"ASSISTANT:"* ]]; then CHAT_FORMAT="vicuna"; CHAT_DETECT_SIGNAL="USER:/ASSISTANT:"
    elif [[ "$TPL" == *"[INST]"* ]];                            then CHAT_FORMAT="mistral"; CHAT_DETECT_SIGNAL="[INST] without <<SYS>>"
    else                                                              CHAT_FORMAT="OTHER"; CHAT_DETECT_SIGNAL="custom template"
    fi
  fi
else
  CHAT_FORMAT="MISSING"
  CHAT_DETECT_SIGNAL="tokenizer_config.json not fetched"
fi

# README fallback when chat_format is MISSING — look for [INST] in code blocks
if [[ "$CHAT_FORMAT" == "MISSING" && -r "$PROBE_DIR/README.md" ]]; then
  if grep -qE '\[INST\]|<<SYS>>|<\|im_start\|>|<\|user\|>' "$PROBE_DIR/README.md"; then
    warn "chat_template missing but README shows chat usage — MANUAL_REVIEW"
  fi
fi

# --- 3. Classify license -------------------------------------------------------

LICENSE_TAG="unknown"
if [[ -r "$PROBE_DIR/README.md" ]]; then
  # First, frontmatter `license:` line
  FM_LICENSE=$(awk '/^---$/{c++; next} c==1 && /^license:/ {sub(/^license:[[:space:]]*/, ""); gsub(/^"|"$|^'\''|'\''$/, ""); print; exit}' "$PROBE_DIR/README.md")
  if [[ -n "$FM_LICENSE" ]]; then
    LICENSE_TAG="$FM_LICENSE"
  else
    # README body search for canonical phrases
    BODY=$(tr '[:upper:]' '[:lower:]' < "$PROBE_DIR/README.md")
    if   [[ "$BODY" == *"apache 2"* || "$BODY" == *"apache license"* ]]; then LICENSE_TAG="apache-2.0"
    elif [[ "$BODY" == *"llama 3.2 community"* ]];                            then LICENSE_TAG="llama3.2"
    elif [[ "$BODY" == *"llama 3.1 community"* ]];                            then LICENSE_TAG="llama3.1"
    elif [[ "$BODY" == *"llama 3 community"* || "$BODY" == *"meta llama 3"* ]]; then LICENSE_TAG="llama3"
    elif [[ "$BODY" == *"llama 2 community"* || "$BODY" == *"meta llama 2"* ]]; then LICENSE_TAG="llama2"
    elif [[ "$BODY" == *"gemma terms"* ]];                                    then LICENSE_TAG="gemma"
    elif [[ "$BODY" == *"cc by-nc"* || "$BODY" == *"non-commercial"* ]];      then LICENSE_TAG="cc-by-nc-4.0"
    elif [[ "$BODY" == *"mit license"* ]];                                    then LICENSE_TAG="mit"
    elif [[ "$BODY" == *"tongyi qianwen"* ]];                                 then LICENSE_TAG="qwen"
    elif [[ "$BODY" == *"openrail"* ]];                                       then LICENSE_TAG="openrail"
    fi
  fi
else
  warn "no README — license unknown"
fi

# Commercial-OK flag (the Orionfold gate)
case "$LICENSE_TAG" in
  apache-2.0|mit|llama2|llama3|llama3.1|llama3.2|gemma|cc-by-4.0|openrail) COMMERCIAL_OK="true" ;;
  cc-by-nc-4.0|cc-by-nc-sa-4.0|qwen-research|mistral-ai)                   COMMERCIAL_OK="false" ;;
  *)                                                                       COMMERCIAL_OK="unknown" ;;
esac

# --- 4. Classify training_type -------------------------------------------------

# Heuristic: name patterns + README signals.
NAME_LC=$(echo "$REPO" | tr '[:upper:]' '[:lower:]')
TRAINING_TYPE="UNKNOWN"

if   [[ "$NAME_LC" == *"-pretrain"* || "$NAME_LC" == *"continued"* ]]; then
  TRAINING_TYPE="continued-pretrain"
elif [[ "$NAME_LC" == *"-base"* && "$NAME_LC" != *"-base-"* ]]; then
  # bare "-base" suffix only; "-base-something" might be a SFT
  TRAINING_TYPE="base"
elif [[ "$NAME_LC" == *"-instruct"* || "$NAME_LC" == *"-chat"* ]]; then
  TRAINING_TYPE="SFT"
elif [[ "$NAME_LC" == *"-dpo"* || "$NAME_LC" == *"-orpo"* ]]; then
  TRAINING_TYPE="DPO/RLHF"
elif [[ "$NAME_LC" == *"-hermes"* || "$NAME_LC" == *"-tulu"* || "$NAME_LC" == *"-zephyr"* ]]; then
  TRAINING_TYPE="SFT-flavored"
elif [[ "$NAME_LC" == *"-sft"* ]]; then
  TRAINING_TYPE="SFT"
fi

# If still UNKNOWN, peek at README for tell-tale signals
if [[ "$TRAINING_TYPE" == "UNKNOWN" && -r "$PROBE_DIR/README.md" ]]; then
  RBODY=$(tr '[:upper:]' '[:lower:]' < "$PROBE_DIR/README.md")
  if   [[ "$RBODY" == *"continued pre-training"* || "$RBODY" == *"continued pretraining"* ]]; then TRAINING_TYPE="continued-pretrain"
  elif [[ "$RBODY" == *"supervised fine-tuning"* || "$RBODY" == *"sft"* ]];                     then TRAINING_TYPE="SFT"
  elif [[ "$RBODY" == *"instruction tuning"* || "$RBODY" == *"instruction-tuned"* ]];           then TRAINING_TYPE="SFT"
  elif [[ "$RBODY" == *"rlhf"* || "$RBODY" == *"dpo"* ]];                                       then TRAINING_TYPE="DPO/RLHF"
  fi
fi

# --- 5. Spark envelope ---------------------------------------------------------
# Delegated to spark_envelope.py for the actual fieldkit.capabilities math.

SPARK_JSON="{\"fits_fp16\":null,\"fits_q4km\":null,\"f16_gb\":null,\"q4km_gb\":null,\"estimated_tg_tok_s\":null}"
if [[ -r "$PROBE_DIR/config.json" ]]; then
  SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
  SE_OUT=$(python3 "$SCRIPT_DIR/spark_envelope.py" "$PROBE_DIR/config.json" 2>&1) || warn "spark_envelope.py: $SE_OUT"
  if [[ -n "$SE_OUT" && "$SE_OUT" == "{"* ]]; then
    SPARK_JSON="$SE_OUT"
  fi
else
  warn "no config.json — spark envelope blocked"
fi

# --- 6. llama.cpp arch compat --------------------------------------------------

LLAMA_CPP_COMPAT="unknown"
ARCH_NAME="unknown"
if [[ -r "$PROBE_DIR/config.json" ]]; then
  ARCH_NAME=$(python3 -c "
import json
d = json.load(open('$PROBE_DIR/config.json'))
print(d.get('model_type') or (d.get('architectures') or ['unknown'])[0])
")
  # Whitelist of llama.cpp-supported model_type / architecture values.
  # Conservative: anything not in this list is flagged "unknown" — the user can override.
  case "$ARCH_NAME" in
    llama|LlamaForCausalLM|MistralForCausalLM|mistral) LLAMA_CPP_COMPAT="true" ;;
    Qwen2ForCausalLM|qwen2|Qwen3ForCausalLM|qwen3)     LLAMA_CPP_COMPAT="true" ;;
    GemmaForCausalLM|gemma|Gemma2ForCausalLM|gemma2|Gemma3ForCausalLM|gemma3) LLAMA_CPP_COMPAT="true" ;;
    Phi3ForCausalLM|phi3|PhiForCausalLM|phi)           LLAMA_CPP_COMPAT="true" ;;
    FalconForCausalLM|falcon)                          LLAMA_CPP_COMPAT="true" ;;
    StableLmForCausalLM|stablelm)                      LLAMA_CPP_COMPAT="true" ;;
    DeepseekV2ForCausalLM|DeepseekV3ForCausalLM|deepseek_v2|deepseek_v3) LLAMA_CPP_COMPAT="true" ;;
    *) LLAMA_CPP_COMPAT="unknown" ;;
  esac
fi

# --- 7. Emit probe.json --------------------------------------------------------

WARNINGS_JSON=$(printf '%s\n' "${WARNINGS[@]:-}" | jq -R . | jq -s -c .)

python3 <<PYEOF >"$PROBE_DIR/probe.json"
import json, sys

probe = {
    "repo": "$REPO",
    "repo_slug": "$REPO_SLUG",
    "chat_format": "$CHAT_FORMAT",
    "chat_detect_signal": "$CHAT_DETECT_SIGNAL",
    "license": "$LICENSE_TAG",
    "commercial_ok": "$COMMERCIAL_OK",
    "training_type": "$TRAINING_TYPE",
    "spark_envelope": json.loads('''$SPARK_JSON'''),
    "llama_cpp_compat": "$LLAMA_CPP_COMPAT",
    "arch_name": "$ARCH_NAME",
    "warnings": json.loads('''$WARNINGS_JSON'''),
}
print(json.dumps(probe, indent=2))
PYEOF

echo "wrote $PROBE_DIR/probe.json"
