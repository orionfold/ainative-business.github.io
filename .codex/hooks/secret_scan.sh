#!/usr/bin/env bash
# Codex-scoped privacy-gated publish guard.
# Mirrors the Claude secret scan behavior without depending on .claude hooks.
set -euo pipefail

mode="--cached"
if [[ "${1:-}" == "--working" ]]; then
  mode=""
fi

added="$(git diff $mode --no-color 2>/dev/null | grep -E '^\+' | grep -vE '^\+\+\+' || true)"
[[ -z "$added" ]] && exit 0

token_re='(pypi-AgEI[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|sk-or-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN[A-Z ]*PRIVATE KEY-----)'
assign_re='(PYPI_TOKEN|HF_TOKEN|OPENROUTER_API_KEY|ANTHROPIC_API_KEY|NGC_API_KEY)[[:space:]]*=[[:space:]]*["'\'']?[A-Za-z0-9_./+-]{12,}'

hits="$(printf '%s\n' "$added" | grep -nEi "$token_re" || true)"
hits2="$(printf '%s\n' "$added" | grep -nE "$assign_re" | grep -vEi '=[[:space:]]*["'\'']?(<|your-|xxx|changeme|not-needed|placeholder|\$)' || true)"

if [[ -n "$hits" || -n "$hits2" ]]; then
  echo "SECRET-SCAN: a likely secret was found in the staged diff - commit blocked." >&2
  echo "Move it to .env.local (gitignored, chmod 600) and unstage the file." >&2
  [[ -n "$hits" ]] && echo "  token-format match(es): $(printf '%s\n' "$hits" | grep -c .)" >&2
  [[ -n "$hits2" ]] && echo "  key=value match(es):    $(printf '%s\n' "$hits2" | grep -c .)" >&2
  exit 1
fi

exit 0
