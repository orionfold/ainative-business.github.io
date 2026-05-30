#!/usr/bin/env bash
# G3 Track B end-to-end runner — produce first Orionfold GGUF on Spark.
#
# Owns: model download → quantize_gguf → measure perplexity + tok/s + thermal
# → dry-run publish_quant. Stops before the HF push so Track A (HF org / token)
# can be ungated independently — the final push is a one-liner once HF_TOKEN
# lands.
#
# Defaults target the revised front-runner from HANDOFF §2 (Track B1):
# nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16 — Bartowski gap as of
# 2026-05-12. Override via env vars.
#
# Usage:
#   ./scripts/g3_build_first_quant.sh
#   MODEL_ID=nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16 ./scripts/g3_build_first_quant.sh  # fallback
#   QUANT_VARIANTS=Q4_K_M,Q8_0 ./scripts/g3_build_first_quant.sh  # subset
#   SKIP_DOWNLOAD=1 ./scripts/g3_build_first_quant.sh  # reuse existing weights
#
# Prereqs:
#   - llama.cpp built on Spark (CUDA on, GGML_CUDA=ON). Default search path
#     /home/nvidia/llama.cpp; override LLAMA_CPP_DIR.
#   - huggingface_hub CLI in a venv. Default /tmp/fk-test; override HF_VENV.
#   - ~70 GB free disk for the source weights + ~150 GB for all five GGUF
#     variants. Total ~220 GB at peak. Spark home volume should have ≥ 250 GB.

set -euo pipefail

# --- Config (env-overridable) -----------------------------------------------

MODEL_ID="${MODEL_ID:-AdaptLLM/finance-chat}"
MODEL_SLUG="${MODEL_SLUG:-$(basename "$MODEL_ID")}"
BASE_MODEL_ARG="${BASE_MODEL_ARG:-$MODEL_ID}"
# Lineage dir isolates this run from prior model attempts (e.g. the archived
# finance-Llama3-8B audit trail at evidence/lineage/). The measure script
# honors LINEAGE_DIR; the dry-run step reads from the model-slug-specific
# quants path so each retry gets its own measurements.json + lineage.
LINEAGE_DIR_DEFAULT="/home/nvidia/ainative-business.github.io/articles/becoming-a-gguf-publisher-on-spark/evidence/lineage-${MODEL_SLUG}"
export LINEAGE_DIR="${LINEAGE_DIR:-$LINEAGE_DIR_DEFAULT}"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-/home/nvidia/llama.cpp}"
LLAMA_CPP_BIN="${LLAMA_CPP_BIN:-${LLAMA_CPP_DIR}/build/bin}"
LLAMA_CPP_CONVERT="${LLAMA_CPP_CONVERT:-${LLAMA_CPP_DIR}/convert_hf_to_gguf.py}"
HF_VENV="${HF_VENV:-/tmp/fk-test}"
MODELS_DIR="${MODELS_DIR:-/home/nvidia/data/models}"
QUANTS_DIR="${QUANTS_DIR:-/home/nvidia/data/quants}"
STAGE_DIR="${STAGE_DIR:-/tmp/orionfold-stage}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-/home/nvidia/ainative-business.github.io/src/content/artifacts}"
ARTICLE_SLUG="${ARTICLE_SLUG:-becoming-a-gguf-publisher-on-spark}"
QUANT_VARIANTS="${QUANT_VARIANTS:-Q4_K_M,Q5_K_M,Q6_K,Q8_0,F16}"
WIKITEXT_CORPUS="${WIKITEXT_CORPUS:-/home/nvidia/data/calibration/wikitext-2-raw-v1/wiki.test.raw}"
FINBENCH_JSONL="${FINBENCH_JSONL:-/home/nvidia/data/eval-benches/financebench/financebench_merged.jsonl}"
LEGALBENCH_JSONL="${LEGALBENCH_JSONL:-/home/nvidia/data/eval-benches/legalbench/legalbench_merged.jsonl}"
CYBERBENCH_JSONL="${CYBERBENCH_JSONL:-/home/nvidia/data/eval-benches/cybermetric/cybermetric_merged.jsonl}"
MEDMCQA_JSONL="${MEDMCQA_JSONL:-/home/nvidia/data/eval-benches/medmcqa/medmcqa_merged.jsonl}"
REPO_NAME="${REPO_NAME:-${MODEL_SLUG}-GGUF}"
# Upstream-model HF license tag — flows to README frontmatter `license:` and
# Astro manifest `license.model:`. Default `apache-2.0` matches most NVIDIA-blessed
# fine-tunes; AdaptLLM/finance-chat (Llama-2 derivative) overrides to `llama2`.
MODEL_LICENSE="${MODEL_LICENSE:-apache-2.0}"
# `llama_cpp.Llama(chat_format=...)` value threaded into the default
# llama-cpp-python snippet on the rendered card. Empty disables the kw arg.
CHAT_FORMAT="${CHAT_FORMAT:-}"
# Variant name to feature in the default How-to-run pull/serve snippets.
RECOMMENDED_VARIANT="${RECOMMENDED_VARIANT:-Q5_K_M}"
case "$MODEL_ID" in
  AdaptLLM/finance-chat)
    MODEL_LICENSE="${MODEL_LICENSE_OVERRIDE:-llama2}"
    CHAT_FORMAT="${CHAT_FORMAT_OVERRIDE:-llama-2}"
    ;;
  Equall/Saul-7B-Instruct-v1)
    MODEL_LICENSE="${MODEL_LICENSE_OVERRIDE:-mit}"
    CHAT_FORMAT="${CHAT_FORMAT_OVERRIDE:-mistral}"
    export VERTICAL_BENCH="${VERTICAL_BENCH:-legalbench}"
    ARTICLE_SLUG="${ARTICLE_SLUG_OVERRIDE:-becoming-a-legal-curator-on-spark}"
    ;;
  ZySec-AI/SecurityLLM)
    MODEL_LICENSE="${MODEL_LICENSE_OVERRIDE:-apache-2.0}"
    CHAT_FORMAT="${CHAT_FORMAT_OVERRIDE:-zephyr}"
    export VERTICAL_BENCH="${VERTICAL_BENCH:-cybermetric}"
    ARTICLE_SLUG="${ARTICLE_SLUG_OVERRIDE:-becoming-a-cyber-curator-on-spark}"
    ;;
  Intelligent-Internet/II-Medical-8B)
    MODEL_LICENSE="${MODEL_LICENSE_OVERRIDE:-apache-2.0}"
    CHAT_FORMAT="${CHAT_FORMAT_OVERRIDE:-chatml}"
    export VERTICAL_BENCH="${VERTICAL_BENCH:-medmcqa}"
    ARTICLE_SLUG="${ARTICLE_SLUG_OVERRIDE:-becoming-a-medical-curator-on-spark}"
    ;;
esac

# HF cache redirect — system /home/nvidia/.cache/huggingface is root-owned
# (legacy from a past sudo run), so xet and hub cache fall back to a writable
# location under /home/nvidia/data/. Disabling xet too — direct HTTP is more
# reliable when xet's log dir is unwritable and silently degrades to noise.
export HF_HOME="${HF_HOME:-/home/nvidia/data/.hf-cache}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"

# --- Logging helpers --------------------------------------------------------

log() { printf '\033[1;36m[g3]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[g3 FATAL]\033[0m %s\n' "$*" >&2; exit 1; }

# --- Step 1: preflight ------------------------------------------------------

step_preflight() {
  log "preflight — checking llama.cpp + huggingface_hub + disk"
  for bin in llama-quantize llama-perplexity llama-bench; do
    if [[ ! -x "${LLAMA_CPP_BIN}/${bin}" ]]; then
      die "llama.cpp binary not found: ${LLAMA_CPP_BIN}/${bin} — build llama.cpp first or set LLAMA_CPP_DIR"
    fi
  done
  if [[ ! -f "$LLAMA_CPP_CONVERT" ]]; then
    die "convert_hf_to_gguf.py not found at $LLAMA_CPP_CONVERT — set LLAMA_CPP_CONVERT"
  fi
  if [[ ! -x "${HF_VENV}/bin/hf" ]]; then
    log "installing huggingface_hub into ${HF_VENV}"
    if [[ ! -x "${HF_VENV}/bin/python" ]]; then
      die "venv ${HF_VENV} not found — create one with python3 -m venv ${HF_VENV}"
    fi
    "${HF_VENV}/bin/pip" install --quiet 'huggingface_hub>=1.14'
  fi
  local avail_gb
  avail_gb=$(df --output=avail -BG "$MODELS_DIR" 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)
  if [[ -z "$avail_gb" || "$avail_gb" -lt 250 ]]; then
    log "warn: <250 GB free at $MODELS_DIR; may run out of space at peak (~220 GB needed)"
  fi
  mkdir -p "$MODELS_DIR" "$QUANTS_DIR" "$STAGE_DIR" "$ARTIFACTS_DIR"
}

# --- Step 2: download source model -----------------------------------------

step_download() {
  local model_dir="${MODELS_DIR}/${MODEL_SLUG}"
  if [[ -n "${SKIP_DOWNLOAD:-}" ]]; then
    log "skip-download: reusing $model_dir"
    return
  fi
  if [[ -f "${model_dir}/config.json" ]]; then
    log "model already present at ${model_dir} — skipping download (set SKIP_DOWNLOAD=0 to force re-pull)"
    return
  fi
  log "downloading ${MODEL_ID} → ${model_dir} (this can take 30–120 min depending on bandwidth)"
  "${HF_VENV}/bin/hf" download "$MODEL_ID" \
    --local-dir "$model_dir"
}

# --- Step 2.5: preflight bench (V0 gate) -----------------------------------
# Score 5 FinanceBench questions on the FP source weights via transformers
# before sinking multi-hour quant+measure cycles. Per memory
# `feedback_preflight_bench_before_quant` + `feedback_chat_vs_continued_pretrain_trap`.

step_preflight_bench() {
  local _vbench="${VERTICAL_BENCH:-financebench}"
  log "preflight-bench — converting to F16 GGUF + scoring 5 ${_vbench} questions on GPU"
  MODELS_DIR="$MODELS_DIR" MODEL_SLUG="$MODEL_SLUG" QUANTS_DIR="$QUANTS_DIR" \
  VERTICAL_BENCH="$_vbench" \
  FINBENCH_JSONL="$FINBENCH_JSONL" \
  LEGALBENCH_JSONL="$LEGALBENCH_JSONL" \
  CYBERBENCH_JSONL="$CYBERBENCH_JSONL" \
  MEDMCQA_JSONL="$MEDMCQA_JSONL" \
  LLAMA_CPP_BIN="$LLAMA_CPP_BIN" LLAMA_CPP_CONVERT="$LLAMA_CPP_CONVERT" \
  BASE_MODEL_ARG="$BASE_MODEL_ARG" \
    "${HF_VENV}/bin/python" "$(dirname "$0")/g3_preflight_bench.py"
}

# --- Step 3: probe convert support (cheap — config.json only) --------------

step_probe_convert() {
  local model_dir="${MODELS_DIR}/${MODEL_SLUG}"
  log "probe — checking if convert_hf_to_gguf.py accepts this architecture"
  if "${HF_VENV}/bin/python" "$LLAMA_CPP_CONVERT" --help >/dev/null 2>&1; then
    log "convert script callable"
  else
    die "convert_hf_to_gguf.py not executable — check Python env has the requirements"
  fi
  # The actual architecture check happens at convert time. Documented as a
  # known risk in HANDOFF §2: omnimodal Nemotron may need a forked llama.cpp
  # branch or text-decoder-only extraction.
}

# --- Step 4: quantize via fieldkit.quant -----------------------------------

step_quantize() {
  local model_dir="${MODELS_DIR}/${MODEL_SLUG}"
  local out_dir="${QUANTS_DIR}/${MODEL_SLUG}"
  mkdir -p "$out_dir"
  log "quantizing ${MODEL_SLUG} → ${out_dir} (variants: ${QUANT_VARIANTS})"
  LLAMA_CPP_BIN="$LLAMA_CPP_BIN" LLAMA_CPP_CONVERT="$LLAMA_CPP_CONVERT" \
    "${HF_VENV}/bin/python" - <<PYEOF
import os
from pathlib import Path
from fieldkit.quant import quantize_gguf, LlamaCppPaths

paths = LlamaCppPaths().resolve()
variants = tuple("${QUANT_VARIANTS}".split(","))
report = quantize_gguf(
    model="${model_dir}",
    outdir="${out_dir}",
    variants=variants,
    paths=paths,
    base_model_id="${BASE_MODEL_ARG}",
)
print("variants written:", list(report.variant_files.keys()))
for v, info in report.variant_files.items():
    print(f"  {v}: {info.get('size','?')}")
PYEOF
}

# --- Step 5: measure perplexity + tok/s + thermal + FinanceBench ----------

step_measure() {
  if [[ ! -f "$WIKITEXT_CORPUS" ]]; then
    log "warn: wikitext corpus not found at $WIKITEXT_CORPUS — skipping perplexity pass"
    log "      download via: hf download Salesforce/wikitext --repo-type dataset --local-dir /home/nvidia/data/calibration --include 'wikitext-2-raw-v1/*'"
    return
  fi
  local _vbench="${VERTICAL_BENCH:-financebench}"
  if [[ "$_vbench" == "financebench" && ! -f "$FINBENCH_JSONL" ]]; then
    log "warn: FinanceBench corpus not at $FINBENCH_JSONL — vertical-eval will be skipped"
    log "      download via: hf download PatronusAI/financebench --repo-type dataset --local-dir /home/nvidia/data/eval-benches/financebench"
    export SKIP_VERTICAL=1
  fi
  if [[ "$_vbench" == "legalbench" && ! -f "$LEGALBENCH_JSONL" ]]; then
    log "warn: LegalBench merged JSONL not at $LEGALBENCH_JSONL — vertical-eval will be skipped"
    log "      build via: ./scripts/legalbench_merge.py (after hf download nguha/legalbench --repo-type=dataset)"
    export SKIP_VERTICAL=1
  fi
  if [[ "$_vbench" == "cybermetric" && ! -f "$CYBERBENCH_JSONL" ]]; then
    log "warn: CyberMetric merged JSONL not at $CYBERBENCH_JSONL — vertical-eval will be skipped"
    log "      build via: ./scripts/cyber_merge.py (after curl from tihanyin/CyberMetric on HF)"
    export SKIP_VERTICAL=1
  fi
  if [[ "$_vbench" == "medmcqa" && ! -f "$MEDMCQA_JSONL" ]]; then
    log "warn: MedMCQA merged JSONL not at $MEDMCQA_JSONL — vertical-eval will be skipped"
    log "      build via: ./scripts/medmcqa_merge.py (after hf download openlifescienceai/medmcqa --repo-type dataset)"
    export SKIP_VERTICAL=1
  fi
  log "measuring 4 axes per variant (perplexity / tok-s / thermal / ${_vbench})"
  MODEL_SLUG="$MODEL_SLUG" QUANTS_DIR="$QUANTS_DIR" QUANT_VARIANTS="$QUANT_VARIANTS" \
  WIKITEXT_CORPUS="$WIKITEXT_CORPUS" FINBENCH_JSONL="$FINBENCH_JSONL" \
  VERTICAL_BENCH="$_vbench" \
  LEGALBENCH_JSONL="$LEGALBENCH_JSONL" \
  CYBERBENCH_JSONL="$CYBERBENCH_JSONL" \
  MEDMCQA_JSONL="$MEDMCQA_JSONL" \
  LLAMA_CPP_BIN="$LLAMA_CPP_BIN" LINEAGE_DIR="$LINEAGE_DIR" \
  BASELINE_HF_REPO="$BASE_MODEL_ARG" \
    "${HF_VENV}/bin/python" "$(dirname "$0")/g3_measure_variants.py"
}

# --- Step 6: dry-run publish -----------------------------------------------

step_dry_run_publish() {
  local out_dir="${QUANTS_DIR}/${MODEL_SLUG}"
  log "dry-run publish_quant — staging at ${STAGE_DIR}/${MODEL_SLUG}"
  "${HF_VENV}/bin/python" - <<PYEOF
import json
from pathlib import Path
from types import SimpleNamespace
from fieldkit.publish import publish_quant

out_dir = Path("${out_dir}")
variants = "${QUANT_VARIANTS}".split(",")
measurements = json.loads((out_dir / "measurements.json").read_text()) if (out_dir / "measurements.json").exists() else {}

# Map gguf bytes to a "4.6 GB" / "16.0 GB" human size label.
def _human(n):
    if not n:
        return ""
    gb = n / (1024 ** 3)
    return f"{gb:.1f} GB"

variant_files = {}
gguf_bytes = measurements.get("gguf_bytes", {})
for v in variants:
    gguf = out_dir / f"model-{v}.gguf"
    if gguf.exists():
        variant_files[v] = {
            "path": str(gguf),
            "rel": gguf.name,
            "size": _human(gguf_bytes.get(v) or gguf.stat().st_size),
        }

# tokens_per_sec in measurements.json is {variant: {"tg": x, "pp": y}};
# publish_quant's card expects {variant: float} (tg only).
tps_raw = measurements.get("tokens_per_sec", {})
tokens_per_sec = {
    v: (tps_raw[v].get("tg") if isinstance(tps_raw.get(v), dict) else tps_raw.get(v))
    for v in variants
    if tps_raw.get(v) is not None
}

# Sustained load — take the minimum across variants as the honest worst-case
# disclosure (matches Q9 a "publish duty-cycle limits on every card").
sustained_per_var = measurements.get("sustained_load_minutes", {}) or {}
sustained_floats = [v for v in sustained_per_var.values() if isinstance(v, (int, float))]
sustained = min(sustained_floats) if sustained_floats else None

# Vertical eval — accuracy per variant; name encodes bench + n + scorer. The
# measure script writes `vertical_eval_name` directly into measurements.json
# (e.g. "FinanceBench (n=50, numeric_match)" or "LegalBench (n=50, contains)").
# Fall back to a derived FinanceBench label for older measurements.json shapes.
fb_acc = measurements.get("financebench_accuracy", {}) or {}
fb_n_per_var = measurements.get("financebench_n", {}) or {}
fb_n = next((n for n in fb_n_per_var.values() if isinstance(n, int) and n > 0), 0)
vertical_eval = {v: fb_acc[v] for v in variants if isinstance(fb_acc.get(v), (int, float))}
vertical_eval_name = measurements.get("vertical_eval_name") or (
    f"FinanceBench (n={fb_n}, numeric_match)" if vertical_eval else None
)

report = SimpleNamespace(
    format="gguf",
    variants=tuple(variants),
    variant_files=variant_files,
    perplexity=measurements.get("perplexity", {}),
    tokens_per_sec=tokens_per_sec,
    sustained_load_minutes=sustained,
)

model_license_arg = "${MODEL_LICENSE}".strip() or None
chat_format_arg = "${CHAT_FORMAT}".strip() or None
recommended_variant_arg = "${RECOMMENDED_VARIANT}".strip() or None

# Derive a short bench label for the article title.
_bench_short = (vertical_eval_name or "vertical mini-eval").split(" (")[0]
article_title_str = "Vertical-curator quants on Spark — ${REPO_NAME} + " + _bench_short + " mini-eval"

result = publish_quant(
    quant_report=report,
    base_model="${BASE_MODEL_ARG}",
    repo_name="${REPO_NAME}",
    staging_dir="${STAGE_DIR}/${MODEL_SLUG}",
    artifacts_dir="${ARTIFACTS_DIR}",
    article_slug="${ARTICLE_SLUG}",
    article_title=article_title_str,
    vertical_eval=vertical_eval,
    vertical_eval_name=vertical_eval_name,
    model_license=model_license_arg,
    chat_format=chat_format_arg,
    recommended_variant=recommended_variant_arg,
    dry_run=True,
)
print()
print("=== Dry-run result ===")
print("hf_repo:    ", result.hf_repo)
print("card_path:  ", result.card_path)
print("manifest:   ", result.manifest_path)
print("files staged:")
for f in result.files_uploaded:
    print(f"  {f}")
PYEOF
}

# --- Main -------------------------------------------------------------------

case "${1:-all}" in
  preflight)          step_preflight ;;
  download)           step_preflight && step_download ;;
  preflight-bench)    step_preflight && step_preflight_bench ;;
  probe)              step_preflight && step_probe_convert ;;
  quantize)           step_preflight && step_quantize ;;
  measure)            step_preflight && step_measure ;;
  publish-dryrun)     step_preflight && step_dry_run_publish ;;
  all)
    step_preflight
    step_download
    step_preflight_bench
    step_probe_convert
    step_quantize
    step_measure
    step_dry_run_publish
    log "done — review staged card at ${STAGE_DIR}/${MODEL_SLUG}/README.md"
    log "next: flip dry_run=False with HF_TOKEN set to actually push"
    ;;
  *)
    cat <<EOF
Usage: $0 <step>

Steps:
  preflight        — verify llama.cpp + venv + disk
  download         — pull source model from HF
  preflight-bench  — V0 gate: 5 FinanceBench questions on FP source via transformers
  probe            — check convert script accepts the architecture
  quantize         — produce GGUF variants via fieldkit.quant
  measure          — perplexity + tok/s per variant (needs wikitext)
  publish-dryrun   — stage card + manifest via fieldkit.publish (dry_run=True)
  all              — run every step in order (default)

Env overrides:
  MODEL_ID, MODEL_SLUG, LLAMA_CPP_DIR, MODELS_DIR, QUANTS_DIR, STAGE_DIR,
  ARTIFACTS_DIR, ARTICLE_SLUG, QUANT_VARIANTS, WIKITEXT_CORPUS, REPO_NAME,
  SKIP_DOWNLOAD
EOF
    exit 1
    ;;
esac
