# CODEX-CC.md

This file is the coexistence contract between Codex CLI and Claude Code for this repository. Codex-owned changes should be logged here so Claude-side sessions can see what was added without reverse-engineering `.codex/` and `.agents/`.

## Boundaries

- Claude Code remains owner of `.claude/`, including `.claude/settings*.json`, `.claude/hooks/`, and `.claude/skills/`.
- Codex owns `.codex/`, `.agents/skills/`, and root `AGENTS.md`.
- Shared project truth remains in existing repo docs: `CLAUDE.md`, `HANDOFF.md`, `_FLOWS/`, `_GUIDES/`, and `_SPECS/`.
- Codex bridge skills may read Claude skill instructions, but should not edit `.claude/` unless the operator explicitly asks for a Claude-side implementation change.
- New Codex configuration, skill, hook, or operator-experience changes should append an entry below.

## Change Log

### 2026-06-08 - Codex CLI coexistence layer

- Added root `AGENTS.md` with Codex project instructions, repo orientation, coexistence boundaries, verification commands, and session closeout expectations.
- Added `.codex/config.toml` with project-scoped Codex defaults: `workspace-write` sandbox, `on-request` approvals, cached web search, pragmatic personality, hook enablement, larger project-doc budget, and fallback instruction filenames for `CLAUDE.md`/`HANDOFF.md`.
- Added `.codex/hooks.json` plus Codex-owned hook scripts:
  - `.codex/hooks/secret_scan.sh` scans staged or working diffs for high-signal tokens and sensitive key assignments.
  - `.codex/hooks/pre_commit_guard.sh` blocks `git commit` only on likely staged secrets and emits advisory render-verifier nudges.
  - `.codex/hooks/post_publish.sh` emits publish-surface stats refresh nudges and best-effort fieldkit freshness checks.
- Added Codex repo skills under `.agents/skills/` for the high-value Claude workflows: `arena-lifecycle`, `status-beacon`, `spark-serve`, `vertical-route`, `tech-writer`, `product-writer`, `sync-field-notes`, `seo-monitor`, `dashboard`, `notebook-author`, `fieldkit-curator`, `notebook-snapshot`, `hf-model-scout`, `hf-publisher`, `nemoclaw-guru`, and `frontier-scout`.
- Implemented those skills as Codex bridge shims that read the authoritative `.claude/skills/<name>/SKILL.md` workflow at invocation time. This keeps the operator experience similar while avoiding a copied fork of the Claude implementation.
- Added a narrow `.gitignore` exception so `.agents/skills/**` is tracked for Codex while other `.agents/` state remains ignored.
- Left existing untracked `.claude/scheduled_tasks.lock` and `src/data/arena-mirror/` untouched.

## Operator Notes

- Start Codex from the repo root to load `AGENTS.md`, `.codex/config.toml`, `.codex/hooks.json`, and `.agents/skills/`.
- Project-local hooks require Codex hook trust review via `/hooks` before they run.
- If a bridge skill points to a missing Claude skill, stop and either restore the Claude skill or replace the bridge with a native Codex workflow.
