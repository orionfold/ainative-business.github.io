#!/usr/bin/env bash
# stop_feedback.sh — M11 (AH-2) the §6.5 Stop-hook feedback loop, finally wired.
#
# Wired as a Stop hook. Near-zero cost (the first action is a git status check;
# if nothing relevant changed it exits silently). When the working tree holds
# UNCOMMITTED changes under the Arena-artifact surfaces (src/content/artifacts/,
# articles/, products/, fieldkit/), it emits a one-line nudge so a session's work
# isn't silently left unstaged — the HANDOFF-amendment seam §6.5 described.
#
# Deterministic shell only — no LLM call (invariant #4). ALWAYS exits 0 so an
# Arena audit failure NEVER blocks a Stop (the `|| true` contract of §6.5).
set -uo pipefail

REPO="${CLAUDE_PROJECT_DIR:-/home/nvidia/ainative-business.github.io}"
cd "$REPO" 2>/dev/null || exit 0

dirty="$(git status --porcelain -- \
  src/content/artifacts/ articles/ products/ fieldkit/ arena-app/ 2>/dev/null \
  | grep -cE '.' || true)"

if [[ "${dirty:-0}" -gt 0 ]]; then
  printf '{"systemMessage":"M11 Stop hook: %s uncommitted change(s) under Arena-artifact surfaces (artifacts/articles/products/fieldkit/arena-app). Commit + refresh HANDOFF before ending the session, or stash deliberately."}\n' "$dirty"
fi
exit 0
