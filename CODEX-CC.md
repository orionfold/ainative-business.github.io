# CODEX-CC.md

This file is the coexistence contract between Codex CLI and Claude Code for this repository. Codex-owned changes should be logged here so Claude-side sessions can see what was added without reverse-engineering `.codex/` and `.agents/`.

## Boundaries

- Claude Code remains owner of `.claude/`, including `.claude/settings*.json`, `.claude/hooks/`, and `.claude/skills/`.
- Codex owns `.codex/`, `.agents/skills/`, and root `AGENTS.md`.
- Shared project truth remains in existing repo docs: `CLAUDE.md`, `HANDOFF.md`, `_GUIDES/`, and `_SPECS/` (the `_FLOWS/` stream was retired 2026-06-12 — its machine map moved into `_GUIDES/`; `_GUIDES/`/`_SPECS/`/`_IDEAS/` are now private gitignored symlinks into the `orionfold/strategy` clone).
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


### 2026-06-09 - HANDOFF pruning discipline

- Added persistent Codex guidance in `AGENTS.md` to keep `HANDOFF.md` aggressively pruned between long sessions. The handoff should carry continuity-critical current state, live runtime, build/verify rules, open items, and a short recent-decision log only; completed historical detail remains recoverable via `git log -p HANDOFF.md`.

### 2026-06-09 - Codex Arena browser-use sandbox notes

- Updated the Codex-owned `arena-lifecycle` bridge skill with sandbox-specific browser-use workarounds.
- Localhost CDP/cockpit checks can fail inside Codex's sandbox (`EPERM` or false down status); rerun read-only CDP/status checks with escalation before concluding Arena is down.
- Keep screenshot captures attached with `defaultViewport: null` and use the operator-resized real browser window, avoiding fixed viewport overrides that can box the visible Chromium session.

### 2026-06-09 - Arena pipeline browser-use discipline

- Added a root `AGENTS.md` operating rule that Arena/fieldkit/model-pipeline work must be driven through the visible Arena cockpit in browser-use mode first.
- Headless browser scripts, hidden endpoint batch scoring, and terminal-only API calls are not acceptable substitutes for Arena validation. If Arena lacks the needed surface, perform only minimal deterministic terminal work and record the gap as an `AD-AE-*` or `AD-FK-*` dogfood finding.
- Updated `HANDOFF.md` with the same pinned rule so cross-session continuation starts from Arena as the system of record.

## Operator Notes

- Start Codex from the repo root to load `AGENTS.md`, `.codex/config.toml`, `.codex/hooks.json`, and `.agents/skills/`.
- Project-local hooks require Codex hook trust review via `/hooks` before they run.
- If a bridge skill points to a missing Claude skill, stop and either restore the Claude skill or replace the bridge with a native Codex workflow.
