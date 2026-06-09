#!/usr/bin/env bash
# Codex PreToolUse(Bash) hook.
# Blocks `git commit` only when the staged diff contains a likely secret.
# Render verifiers remain advisory so a stale dist/ cannot prevent local work.
set -uo pipefail

REPO="/home/nvidia/ainative-business.github.io"
HOOKS="$REPO/.codex/hooks"

payload="$(cat || true)"
cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // .tool_input.cmd // .command // empty' 2>/dev/null || true)"

printf '%s' "$cmd" | grep -qE '\bgit[[:space:]]+commit\b' || exit 0

cd "$REPO" 2>/dev/null || exit 0

if ! bash "$HOOKS/secret_scan.sh" --cached 2>/tmp/.codex-secret-scan.err; then
  reason="$(cat /tmp/.codex-secret-scan.err 2>/dev/null)"
  echo "${reason:-secret-scan blocked the commit}" >&2
  exit 2
fi

warn=""
if [[ -d "$REPO/dist" ]]; then
  for verifier in verify_artifact_rendering.mjs verify_field_notes_rendering.mjs; do
    if [[ -f "$REPO/scripts/$verifier" ]]; then
      if ! node "$REPO/scripts/$verifier" >/dev/null 2>&1; then
        warn="${warn}${warn:+; }$verifier reported an issue"
      fi
    fi
  done
fi

if [[ -n "$warn" ]]; then
  printf '{"systemMessage":"Codex pre-commit advisory: %s. dist/ may be stale - rebuild before pushing."}\n' "$warn"
fi

exit 0
