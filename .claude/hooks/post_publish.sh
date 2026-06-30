#!/usr/bin/env bash
# post_publish.sh — M11 (AH-2) the post-publish hook of the battery.
#
# Wired as a PostToolUse(Bash) hook. Reads the harness hook JSON on stdin, acts
# ONLY when the just-run Bash command was a `git commit` whose last commit
# touched articles/ or products/ (a publish). ALWAYS advisory (exit 0, R25):
#
#   1. enqueue an eval_rerun freshness trigger into arena.db (if the db + the
#      fieldkit CLI exist) — the freshness-monitor seam (AH-6); a no-op otherwise.
#   2. nudge the operator to refresh project-stats (the home "At a glance" reads
#      a JSON that drifts silently on publish — feedback_refresh_stats_on_publish).
#
# Deterministic shell only — no LLM call (invariant #4). Never blocks.
set -uo pipefail

REPO="${CLAUDE_PROJECT_DIR:-/home/nvidia/ainative-business.github.io}"
payload="$(cat || true)"
cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"

printf '%s' "$cmd" | grep -qE '\bgit[[:space:]]+commit\b' || exit 0
cd "$REPO" 2>/dev/null || exit 0

# Did the HEAD commit touch a publish surface?
touched="$(git show --name-only --pretty=format: HEAD 2>/dev/null | grep -E '^(articles|products)/' || true)"
[[ -z "$touched" ]] && exit 0

# 1. Freshness trigger — enqueue an index-staleness re-eval sweep (best-effort).
#    The cron's run_drain_cycle picks it up overnight (AH-6). Silent if arena
#    isn't installed / the db is absent — never fail the hook.
db="$HOME/.fieldkit/arena.db"
if [[ -f "$db" ]] && command -v fieldkit >/dev/null 2>&1; then
  fieldkit arena check-regressions >/dev/null 2>&1 || true
fi

# 2. Stats-refresh nudge (advisory systemMessage).
n="$(printf '%s\n' "$touched" | grep -c . || true)"
printf '{"systemMessage":"M11 post-publish: HEAD touched %s publish file(s) under articles/products. Refresh project-stats before pushing (feedback_refresh_stats_on_publish); a freshness eval_rerun was queued for the overnight drain."}\n' "$n"
exit 0
