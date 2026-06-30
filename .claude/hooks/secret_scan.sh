#!/usr/bin/env bash
# secret_scan.sh — M11 (AH-2) the privacy-gated-publish guard (invariant #3).
#
# Scans the STAGED diff (or, with --working, the unstaged working tree) for
# high-signal secrets before a commit can land. Deterministic shell only — no
# LLM call (invariant #4). Exits 0 when clean, 1 when a secret is found (the
# caller — pre_commit_guard.sh — turns a nonzero exit into a hard block).
#
# High-signal only, to avoid false-positives on the many docs that NAME these
# vars: it matches ADDED lines (^+) carrying an assignment-with-real-value
# (KEY=<non-placeholder>) or a known live-token prefix. A bare mention of
# "PYPI_TOKEN" in prose does NOT trip it; "PYPI_TOKEN=pypi-AgEI…" does.
set -euo pipefail

mode="--cached"
if [[ "${1:-}" == "--working" ]]; then mode=""; fi

# Only the added side of the diff.
added="$(git diff $mode --no-color 2>/dev/null | grep -E '^\+' | grep -vE '^\+\+\+' || true)"
[[ -z "$added" ]] && exit 0

# 1. Live-token prefixes (these formats are never legitimately committed).
token_re='(pypi-AgEI[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|sk-or-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN[A-Z ]*PRIVATE KEY-----)'

# 2. Our own env-var names assigned a real (non-empty, non-placeholder) value.
#    Placeholders we tolerate: <...>, your-..., xxx, changeme, "", '', not-needed.
assign_re='(PYPI_TOKEN|HF_TOKEN|OPENROUTER_API_KEY|ANTHROPIC_API_KEY|NGC_API_KEY)[[:space:]]*=[[:space:]]*["'\'']?[A-Za-z0-9_./+-]{12,}'

hits="$(printf '%s\n' "$added" | grep -nEi "$token_re" || true)"
hits2="$(printf '%s\n' "$added" | grep -nE "$assign_re" \
  | grep -vEi '=[[:space:]]*["'\'']?(<|your-|xxx|changeme|not-needed|placeholder|\$)' || true)"

if [[ -n "$hits" || -n "$hits2" ]]; then
  echo "SECRET-SCAN: a likely secret was found in the staged diff — commit blocked." >&2
  echo "Move it to .env.local (gitignored, chmod 600) and unstage the file." >&2
  [[ -n "$hits"  ]] && echo "  token-format match(es): $(printf '%s\n' "$hits"  | grep -c .)" >&2
  [[ -n "$hits2" ]] && echo "  key=value match(es):    $(printf '%s\n' "$hits2" | grep -c .)" >&2
  exit 1
fi
exit 0
