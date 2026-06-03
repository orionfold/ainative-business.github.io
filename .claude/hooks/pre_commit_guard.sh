#!/usr/bin/env bash
# pre_commit_guard.sh — M11 (AH-2) the pre-commit hook of the battery.
#
# Wired as a PreToolUse(Bash) hook. Reads the harness hook JSON on stdin, acts
# ONLY when the Bash command is a `git commit` (every other Bash call passes
# through untouched and instantly). On a commit it runs two checks:
#
#   1. secret-scan (HARD BLOCK)   — invariant #3; a real secret aborts the commit.
#   2. render verifiers (ADVISORY) — verify_artifact_rendering + field_notes;
#      run only if dist/ exists, never block (R25 — a flaky/slow verifier must
#      not stall a legitimate direct-to-main commit). Failures surface as a
#      systemMessage the operator reads, not an abort.
#
# Deterministic shell only — no LLM call (invariant #4). To block, exit 2 with a
# reason on stderr (the harness denies the tool call and feeds stderr back).
set -uo pipefail

REPO="/home/nvidia/ainative-business.github.io"
HOOKS="$REPO/.claude/hooks"

# Pull the Bash command out of the hook payload without a hard jq dependency.
payload="$(cat || true)"
cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"

# Not a git commit → no-op, fast path.
printf '%s' "$cmd" | grep -qE '\bgit[[:space:]]+commit\b' || exit 0

cd "$REPO" 2>/dev/null || exit 0

# 1. Secret scan — HARD BLOCK on a real secret.
if ! bash "$HOOKS/secret_scan.sh" --cached 2>/tmp/.m11-secret-scan.err; then
  reason="$(cat /tmp/.m11-secret-scan.err 2>/dev/null)"
  echo "${reason:-secret-scan blocked the commit}" >&2
  exit 2  # deny the git commit (privacy gate, invariant #3)
fi

# 2. Render verifiers — ADVISORY only (never block; R25).
warn=""
if [[ -d "$REPO/dist" ]]; then
  for v in verify_artifact_rendering.mjs verify_field_notes_rendering.mjs; do
    if [[ -f "$REPO/scripts/$v" ]]; then
      if ! node "$REPO/scripts/$v" >/dev/null 2>&1; then
        warn="${warn}${warn:+; }$v reported an issue"
      fi
    fi
  done
fi

if [[ -n "$warn" ]]; then
  # Non-blocking nudge — emit a systemMessage, allow the commit.
  printf '{"systemMessage":"M11 pre-commit (advisory): %s. dist/ may be stale — rebuild before pushing."}\n' "$warn"
fi
exit 0
