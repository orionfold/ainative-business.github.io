#!/usr/bin/env bash
# Codex PostToolUse(Bash) hook.
# Advisory only: after publish-surface commits, nudge the operator to refresh stats.
set -uo pipefail

REPO="/home/nvidia/ainative-business.github.io"
payload="$(cat || true)"
cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // .tool_input.cmd // .command // empty' 2>/dev/null || true)"

printf '%s' "$cmd" | grep -qE '\bgit[[:space:]]+commit\b' || exit 0
cd "$REPO" 2>/dev/null || exit 0

touched="$(git show --name-only --pretty=format: HEAD 2>/dev/null | grep -E '^(articles|products)/' || true)"
[[ -z "$touched" ]] && exit 0

db="$HOME/.fieldkit/arena.db"
if [[ -f "$db" ]] && command -v fieldkit >/dev/null 2>&1; then
  fieldkit arena check-regressions >/dev/null 2>&1 || true
fi

n="$(printf '%s\n' "$touched" | grep -c . || true)"
printf '{"systemMessage":"Codex post-publish: HEAD touched %s publish file(s) under articles/products. Refresh project-stats before pushing; a freshness eval_rerun was queued when fieldkit was available."}\n' "$n"
exit 0
