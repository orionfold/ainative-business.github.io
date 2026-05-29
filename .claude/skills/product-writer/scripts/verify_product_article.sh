#!/usr/bin/env bash
# Pre-publish gate for a product-launch article at products/<slug>/product.md.
#
# Checks the things that silently break a launch piece: missing required
# frontmatter, a metrics block that was never filled, screenshots referenced
# but absent, leftover template placeholders, and — most important, because the
# page is public and permanent — credential / PII patterns. This mirrors the
# tech-writer verify gate; the privacy scan is intentionally the same set of
# patterns (see ../../tech-writer/references/privacy-and-security.md).
set -uo pipefail

REPO="${REPO:-/home/nvidia/ainative-business.github.io}"
slug="${1:-}"
if [[ -z "$slug" ]]; then
  echo "usage: verify_product_article.sh <slug>" >&2
  exit 2
fi

dir="$REPO/products/$slug"
md="$dir/product.md"
fail=0
note() { echo "FAIL: $*"; fail=1; }
warn() { echo "WARN: $*"; }

[[ -f "$md" ]] || { echo "FAIL: $md not found"; exit 1; }

# --- required frontmatter keys -------------------------------------------------
for key in title date author product_name tagline summary status; do
  grep -qE "^${key}:" "$md" || note "missing frontmatter key: $key"
done

# summary length (the destination Zod schema caps it; catch it locally)
summ=$(awk -F': ' '/^summary:/{ $1=""; print; exit }' "$md" | sed 's/^ *//;s/^"//;s/"$//')
if [[ -n "$summ" && ${#summ} -gt 300 ]]; then
  note "summary is ${#summ} chars (max 300)"
fi

# --- build-metrics block present and filled -----------------------------------
if ! grep -qE "^build:" "$md"; then
  note "no build: metrics block — the infographic has no data source"
else
  for k in wall_clock_hours lines_of_code test_cases tokens_generated; do
    grep -qE "^\s+${k}:" "$md" || warn "build block missing field: $k"
  done
  # placeholder zeros usually mean the mine step was skipped
  if grep -qE "^\s+(lines_of_code|tokens_generated):\s*0\s*$" "$md"; then
    note "build metrics still zero — run mine_build_metrics.py and fill them"
  fi
fi

# --- feature tour: every referenced screenshot must exist ----------------------
missing=0
while IFS= read -r ref; do
  [[ -z "$ref" ]] && continue
  if [[ ! -f "$dir/$ref" ]]; then
    note "screenshot referenced but missing: $ref"
    missing=$((missing+1))
  fi
done < <(grep -oE 'screenshots/[A-Za-z0-9._-]+\.(png|jpg|jpeg|webp)' "$md" | sort -u)
shots=$(find "$dir/screenshots" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.webp' \) 2>/dev/null | grep -vc '/\._' || true)
if [[ "${shots:-0}" -eq 0 ]]; then
  warn "no screenshots present — a product launch piece needs a feature tour"
fi

# --- leftover template scaffolding --------------------------------------------
grep -qE "__SLUG__|TODO|FIXME|<placeholder>" "$md" && note "leftover placeholder/TODO markers in product.md"

# --- privacy scan (same patterns as tech-writer's verify) ----------------------
scan() { grep -REIn "$1" "$dir" --include='*.md' --include='*.json' 2>/dev/null | grep -vE '\.(png|jpg|webp)' ; }
declare -A pats=(
  ["NGC/nvapi key"]='nvapi-[A-Za-z0-9_-]{20,}'
  ["OpenAI key"]='sk-[A-Za-z0-9]{20,}'
  ["Anthropic key"]='sk-ant-[A-Za-z0-9_-]{20,}'
  ["AWS access key"]='AKIA[0-9A-Z]{16}'
  ["Bearer token"]='[Bb]earer [A-Za-z0-9._-]{20,}'
  ["GitHub token"]='gh[pousr]_[A-Za-z0-9]{30,}'
  ["private key block"]='BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY'
)
for label in "${!pats[@]}"; do
  if scan "${pats[$label]}" >/dev/null; then
    note "possible secret ($label) — scrub before publishing:"
    scan "${pats[$label]}" | sed 's/^/      /'
  fi
done

echo ""
if [[ $fail -eq 0 ]]; then
  echo "PASS: $slug ready (review WARNs above)"
else
  echo "PASS/FAIL: FAIL — fix the items above before committing"
fi
exit $fail
