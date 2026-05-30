#!/usr/bin/env bash
# hf-publisher — automated stage verification before live HF push.
#
# Catches the same five rendering bugs that bit `Orionfold/finance-chat-GGUF`:
# wrong license-frontmatter default, empty `## How to run` body, mis-shaped
# Spark-tested table, broken Methods link, GGUF files in stage that the
# Variants table doesn't list. Each is a reason a customer-facing card would
# render wrong on HuggingFace and we'd find out only after the push.
#
# Usage:  bash verify_stage.sh /tmp/orionfold-stage/<slug>
# Exit code = number of failed checks. 0 = ready to push.

set -uo pipefail

STAGE_DIR="${1:-}"
if [[ -z "$STAGE_DIR" ]]; then
  echo "Usage: $0 <stage-dir>" >&2
  exit 99
fi
if [[ ! -d "$STAGE_DIR" ]]; then
  echo "ERROR: stage dir does not exist: $STAGE_DIR" >&2
  exit 99
fi
README="$STAGE_DIR/README.md"
if [[ ! -f "$README" ]]; then
  echo "ERROR: $README missing — run dry-run first" >&2
  exit 99
fi

# Articles dir is canonical at this path. Override via ARTICLES_DIR if needed.
ARTICLES_DIR="${ARTICLES_DIR:-/home/nvidia/ainative-business.github.io/articles}"

PASS=0
FAIL=0

pass() { printf "[\033[1;32mPASS\033[0m] %s\n" "$*"; PASS=$((PASS+1)); }
fail() { printf "[\033[1;31mFAIL\033[0m] %s\n" "$*"; FAIL=$((FAIL+1)); }

# --- Check 1: license frontmatter ----------------------------------------
# The bug we shipped on finance-chat: license defaulted to apache-2.0 but the
# model is Llama-2 lineage. Allow apache-2.0 ONLY if the source repo's README
# explicitly says Apache (caller verified) — flagged via APACHE_VERIFIED=1.
license_line=$(awk '/^---$/{f=!f; next} f && /^license:/' "$README" | head -1)
license_value=$(echo "$license_line" | sed 's/^license:[[:space:]]*//' | tr -d '"' | tr -d "'")
if [[ -z "$license_value" ]]; then
  fail "license frontmatter is missing entirely"
elif [[ "$license_value" == "apache-2.0" ]]; then
  if [[ "${APACHE_VERIFIED:-0}" == "1" ]]; then
    pass "license frontmatter is apache-2.0 (caller-verified upstream is Apache)"
  else
    fail "license: apache-2.0 — verify upstream isn't Llama/Gemma/Qwen/CC-BY-NC; pass APACHE_VERIFIED=1 if confirmed"
  fi
else
  pass "license frontmatter is non-default (got: $license_value)"
fi

# --- Check 2: ## How to run body is non-empty ----------------------------
# The bug we shipped on finance-chat: section header rendered with no body
# because ollama_pull_handle + transformers_snippet were both None and the
# old renderer had no GGUF default. Threshold: ≥ 8 non-empty content lines
# between the header and the next ## heading (covers minimal pull + serve
# snippet pair).
howto_body=$(awk '
  /^## How to run/ { in_section=1; next }
  in_section && /^## / { exit }
  in_section { print }
' "$README" | grep -cE '\S')
if (( howto_body >= 8 )); then
  pass "## How to run body is non-empty ($howto_body content lines)"
else
  fail "## How to run body has only $howto_body content lines (need ≥ 8) — likely the empty-section bug"
fi

# --- Check 3: ## Spark-tested table shape --------------------------------
# Columns are *metrics* (Variant / Size / Perplexity / tok-s / optional
# vertical-eval), not derived from variants count. Valid shapes:
#   - 4 cols (no vertical eval): Variant | Size | Perplexity | tok/s
#   - 5 cols (with vertical eval): Variant | Size | Perplexity | tok/s | <eval>
# Each VARIANT-ROW (excluding header + separator) must match the header
# column count — that's the real shape invariant.
sparktable_header=$(awk '
  /^## Spark-tested/ { in_section=1; next }
  in_section && /^## / { exit }
  in_section && /^\| Variant \|/ { print; exit }
' "$README")
if [[ -z "$sparktable_header" ]]; then
  fail "## Spark-tested table is missing"
else
  header_pipes=$(echo "$sparktable_header" | tr -cd '|' | wc -c)
  header_cells=$((header_pipes - 1))
  # Pull all data rows (rows after the |---| separator inside Spark-tested)
  rows_with_wrong_cell_count=$(awk -v hcells="$header_cells" '
    /^## Spark-tested/ { in_section=1; next }
    in_section && /^## / { exit }
    in_section && /^\| / && !/^\| Variant \|/ && !/^\|---/ {
      pipes = gsub(/\|/, "|")
      cells = pipes - 1
      if (cells != hcells) { bad++ }
    }
    END { print bad+0 }
  ' "$README")
  if (( header_cells != 4 && header_cells != 5 )); then
    fail "Spark-tested header has $header_cells cells; expected 4 (no vertical-eval) or 5 (with vertical-eval)"
  elif (( rows_with_wrong_cell_count > 0 )); then
    fail "Spark-tested table has $rows_with_wrong_cell_count data row(s) whose cell count != header ($header_cells)"
  else
    pass "Spark-tested table shape is correct ($header_cells cols, all rows match)"
  fi
fi

# --- Check 4: ## Methods link points at existing article -----------------
methods_url=$(awk '
  /^## Methods/ { in_section=1; next }
  in_section && /^## / { exit }
  in_section { print }
' "$README" | grep -oE 'ainative\.business/field-notes/[a-z0-9-]+/?' | head -1)
if [[ -z "$methods_url" ]]; then
  fail "## Methods link is missing or malformed"
else
  slug=$(echo "$methods_url" | sed -E 's|.*/field-notes/([a-z0-9-]+)/?|\1|')
  if [[ -d "$ARTICLES_DIR/$slug" ]]; then
    pass "Methods link points at existing article ($slug)"
  else
    fail "Methods link slug '$slug' has no $ARTICLES_DIR/$slug directory"
  fi
fi

# --- Check 5: Variants table covers every model-*.gguf in stage ----------
table_variants=$(awk '
  /^## Variants/ { in_section=1; next }
  in_section && /^## / { exit }
  in_section && /^\| / && !/^\| Variant \|/ && !/^\|---/ { print $2 }
' "$README" | tr -d ' ')
stage_variants=$(ls "$STAGE_DIR" | grep -oE '^model-[A-Za-z0-9_]+\.gguf$' | sed -E 's/^model-(.+)\.gguf$/\1/')
if [[ -z "$stage_variants" ]]; then
  fail "no model-*.gguf files in stage — nothing to publish"
else
  missing=()
  while IFS= read -r v; do
    [[ -z "$v" ]] && continue
    if ! grep -qx "$v" <<< "$table_variants"; then
      missing+=("$v")
    fi
  done <<< "$stage_variants"
  if (( ${#missing[@]} == 0 )); then
    n=$(echo "$stage_variants" | wc -l)
    pass "Variants table covers all $n GGUF files in stage"
  else
    fail "Variants table missing rows for: ${missing[*]}"
  fi
fi

# --- Check 6: frontmatter engagement-pull metadata -----------------------
# v5 §3.15.b: cards missing pipeline_tag / library_name / tags get ranked
# poorly in HF's discoverability surfaces. Confirmed empirically on
# Orionfold/II-Medical-8B-GGUF (472 DL / 0 likes). The renderer in
# fieldkit.publish supplies pipeline_tag + library_name defaults, but
# `tags` is rendered from a tuple that's empty unless the publish_quant
# caller passes a non-empty `tags=(...)` kwarg.
#
# Required tags include `spark-tested` — the Orionfold engagement-pull
# differentiator. Configurable via VERIFY_REQUIRED_TAGS (comma-separated);
# overall tag count via VERIFY_MIN_TAGS (default 3).
VERIFY_REQUIRED_TAGS="${VERIFY_REQUIRED_TAGS:-spark-tested}"
VERIFY_MIN_TAGS="${VERIFY_MIN_TAGS:-3}"

# Extract frontmatter into a temp buffer so all four sub-checks read from
# the same delimited block (between the first two `---` lines).
fm_block=$(awk '/^---$/{c++; if(c==2)exit; next} c==1' "$README")

pipeline_tag_value=$(echo "$fm_block" | awk '/^pipeline_tag:/' | sed 's/^pipeline_tag:[[:space:]]*//' | tr -d '"' | tr -d "'")
library_name_value=$(echo "$fm_block" | awk '/^library_name:/' | sed 's/^library_name:[[:space:]]*//' | tr -d '"' | tr -d "'")

if [[ -z "$pipeline_tag_value" ]]; then
  fail "pipeline_tag frontmatter is missing — publish_quant should default to 'text-generation' (and supply explicitly for non-GGUF formats)"
else
  pass "pipeline_tag frontmatter present (got: $pipeline_tag_value)"
fi

if [[ -z "$library_name_value" ]]; then
  fail "library_name frontmatter is missing — publish_quant should default to 'gguf' (or 'transformers' for non-GGUF formats)"
else
  pass "library_name frontmatter present (got: $library_name_value)"
fi

# tags is a YAML list — either inline `tags: [a, b, c]` or block list
# (`tags:\n- a\n- b`). Normalise to a flat space-separated token list.
tags_inline=$(echo "$fm_block" | awk '/^tags:[[:space:]]*\[/' | sed -E 's/^tags:[[:space:]]*\[//; s/\][[:space:]]*$//' | tr ',' ' ' | tr -d '"' | tr -d "'")
tags_block=$(echo "$fm_block" | awk '
  /^tags:[[:space:]]*$/ { in_block=1; next }
  in_block && /^[[:space:]]*-[[:space:]]/ { sub(/^[[:space:]]*-[[:space:]]*/, ""); print; next }
  in_block && /^[^[:space:]-]/ { exit }
' | tr -d '"' | tr -d "'" | tr '\n' ' ')
tags_all="$tags_inline $tags_block"
tags_count=$(echo "$tags_all" | tr -s '[:space:]' '\n' | grep -cE '\S' || true)

if (( tags_count == 0 )); then
  fail "tags frontmatter is empty — at minimum needs: $VERIFY_REQUIRED_TAGS plus N≥$VERIFY_MIN_TAGS engagement-pull tags (e.g., gguf, llama-cpp, spark-tested, $vertical-tag)"
elif (( tags_count < VERIFY_MIN_TAGS )); then
  fail "tags frontmatter has only $tags_count entries (need ≥$VERIFY_MIN_TAGS) — current: $tags_all"
else
  missing_required=()
  IFS=',' read -ra required_arr <<< "$VERIFY_REQUIRED_TAGS"
  for req in "${required_arr[@]}"; do
    req_trimmed=$(echo "$req" | xargs)
    [[ -z "$req_trimmed" ]] && continue
    if ! grep -qw "$req_trimmed" <<< "$tags_all"; then
      missing_required+=("$req_trimmed")
    fi
  done
  if (( ${#missing_required[@]} > 0 )); then
    fail "tags frontmatter is missing required engagement-pull tags: ${missing_required[*]} (have: $(echo "$tags_all" | xargs))"
  else
    pass "tags frontmatter is complete ($tags_count entries including: ${VERIFY_REQUIRED_TAGS//,/ })"
  fi
fi

# --- Summary --------------------------------------------------------------
TOTAL=$((PASS + FAIL))
if (( FAIL == 0 )); then
  printf "\n\033[1;32m%d/%d PASSED\033[0m — stage is ready for live push\n" "$PASS" "$TOTAL"
else
  printf "\n\033[1;31m%d/%d FAILED\033[0m — fix before pushing\n" "$FAIL" "$TOTAL"
fi
exit "$FAIL"
