# AGENTS.md

## Repository Orientation

This repo is the Spark-owned `ainative-business.github.io` monorepo: the build workspace and the public `ainative.business` website.

Read these files before substantial work:

- `HANDOFF.md` for the live session-transfer state, open items, and recent decisions. This is the per-session continuity contract: read it at session start, update it at session end when state changes, and prune stale completed context periodically.
- `CLAUDE.md` for the existing Claude Code navigation map and load-bearing project invariants.
- `CODEX-CC.md` for the Codex/Claude coexistence contract and Codex-specific configuration log.
- `_FLOWS/the-machine-that-builds-machines.md` when a request touches roadmap, artifact flow, or publishing process.
- `_GUIDES/index.md` and `_SPECS/index.md` when a request asks for active guidance, specs, or design decisions.

## Coexistence Boundary

- Do not edit `.claude/` to improve Codex behavior unless the user explicitly asks for a Claude-side change.
- Put Codex project settings under `.codex/`.
- Put Codex repo skills under `.agents/skills/`; Codex scans that location, while Claude's existing skills remain under `.claude/skills/`.
- Log any new Codex/Claude interoperability change in `CODEX-CC.md`.
- Treat `.claude/scheduled_tasks.lock` and unrelated untracked files as operator/Claude state unless the task specifically targets them.

## Operating Rules

- This is a solo-blog, direct-to-main workflow; human review is the gate.
- Privacy-gated publish is mandatory. Run `.codex/hooks/secret_scan.sh --cached` before committing and keep secrets in `.env.local`.
- Use deterministic scripts for mechanical transforms. Do not call `anthropic` or `claude-agent-sdk` from repo automation.
- Keep one local serving lane resident at a time on the 128 GB DGX Spark memory envelope.
- For website verification, prefer `node node_modules/astro/astro.js build`, then `node scripts/verify_artifact_rendering.mjs` and `node scripts/verify_field_notes_rendering.mjs`.
- `npm run build` is documented as broken on this checkout; use the direct Astro command above unless the state has changed and you verify it.

## Session Closeout

For substantial repo sessions, update `HANDOFF.md` and `_STATUS.json` if the work changes live state, public artifacts, release posture, or the operator cockpit beacon. Keep `_STATUS.json` short and factual; do not bump external metrics dates without a real check.
