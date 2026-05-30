# Sync workflow — Mac ↔ Spark (2026-05-22)

This note describes how this repo (`ai-field-notes`, authored on the NVIDIA DGX Spark) is synced with the public marketing website (`ainative-business.github.io`, deployed from the Mac). **It supersedes the older SYNC-HANDOFF.md-driven workflow.** Spark CC should memorize this so it knows what changed and what is/isn't expected of the source side anymore.

## What changed

Before: Mac kept a local clone of this repo at `/Users/manavsehgal/Developer/ai-field-notes/` and pulled from GitHub before each sync. The Mac-side `/sync-field-notes` skill read a curated release narrative from `SYNC-HANDOFF.md` and routed changes through a 7-bucket UX brainstorm. Spark would author the handoff at release time; Mac would PR a `STATUS: SHIPPED` flip back to source after sweeping.

After: Mac mounts this repo directly over NFS at `/Volumes/home/ai-field-notes/`. The mount IS the live source — no local clone, no `git pull` step on Mac. Mac now reads `git -C /Volumes/home/ai-field-notes log --since=<last-sync-date>` to know what changed. **The Mac-side skill no longer reads SYNC-HANDOFF.md.**

## What Spark should keep doing

- **Commit descriptively.** Mac uses your commit subjects as the "what changed" narrative. `feat(field-notes): add <slug>` and `chore(field-notes): refresh <slug>` are good; bare `update` is not.
- **Author articles in `articles/<slug>/`** with the existing frontmatter schema. Mac copies these 1:1.
- **Keep `mirrors/destination-overrides.md` up to date.** This is the source-of-truth for paths Mac owns (book, pricing, artifacts catalogs, skills, etc.) — Mac honors it as the "do not stomp" list.
- **Keep `evidence/` for raw research code and `screenshots/` for in-article imagery.** Mac copies image files from both but never copies non-image evidence (Python/notebooks stay here).

## What Spark can stop doing

- **Authoring SYNC-HANDOFF.md.** The Mac skill no longer reads it. You can keep writing it for your own records, or stop — Mac doesn't care either way. Setting `status: SHIPPED` and the prior-cycles receipt comments are no longer required.
- **Waiting for SHIPPED-flip PRs from Mac.** Mac no longer opens those PRs. If the handoff doc still exists on `main`, its status is now informational only.
- **Maintaining the SYNC-RENAMES.log destination-replay status.** Mac no longer reads it or PRs `status: destination-needs-replay` → `status: applied` flips back. You can keep the log as a historical record of renames or stop appending — either is fine.
- **Bundling release narratives.** A single feature/article ship doesn't need a paired SYNC-HANDOFF rewrite anymore. Just commit and push.

## What to expect FROM Mac

Mac now has write access to this repo via the NFS mount. When Mac's `/sync-field-notes` skill spots a source-side issue during review (missing catalog footer, frontmatter typo, image filename mismatch, broken link), Mac may:

1. Edit the file at `/Volumes/home/ai-field-notes/<path>` directly.
2. `git -C /Volumes/home/ai-field-notes pull --rebase --autostash origin main` to fast-forward.
3. `git -C /Volumes/home/ai-field-notes commit -m "<conventional message>"` — typically `chore(field-notes): restore catalog footer on <slug>` or `fix(field-notes): correct frontmatter typo in <slug>`. Each commit is co-authored by Claude Opus (`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`).
4. `git -C /Volumes/home/ai-field-notes push origin main`.

So Spark should expect occasional Mac-authored commits landing on `origin/main` — typically small fix-up commits attached to a sync run, not large source-side rewrites. They'll appear with the `Co-Authored-By: Claude Opus` trailer. If Spark has uncommitted local work when this happens, Mac's rebase step will surface the conflict and abort, leaving the push for the user to resolve.

## What Mac copies (full sync scope, unchanged)

| Content | Source path (on this repo) | Direction |
|---|---|---|
| Article markdown | `articles/<slug>/article.{md,mdx}` | source → Mac |
| Article seed (upcoming-only) | `articles/<slug>/seed.md` | source → Mac (renamed to `article.md`) |
| Screenshots | `articles/<slug>/screenshots/` | source → Mac |
| Evidence images only | `articles/<slug>/evidence/*.{png,jpg,jpeg,svg,gif,webp}` | source → Mac |
| Fieldkit module reference | `fieldkit/docs/api/*.md` | source → Mac |
| Fieldkit version pin | `fieldkit/src/fieldkit/_version.py` | source → Mac |
| Fieldkit landing sections | `src/pages/fieldkit/index.astro` (Install/Quickstart/CLI bodies only) | source → Mac |
| Signature SVG components | `src/components/svg/*.astro` | source → Mac |
| Project-stats KPIs | `src/data/project-stats.json` | source → Mac (with one hand-curated override re-applied) |
| Article-sequence order | derived from `git log` of `articles/*/article.md` | source → Mac |
| Source-side nit fixes | any path the Mac skill writes during a sync run | Mac → source |

Mac does not copy: `transcript.md`, non-image files under `evidence/`, the `_drafts/` folder, `ideas/`, `papers/`, `specs/`, `probes/`, `scripts/`, `dataset-cards/`, `share/`, `node_modules/`, `unsloth_compiled_cache/`, `dist/`.

## Tl;dr for Spark CC

- Mac reads this repo over NFS at `/Volumes/home/ai-field-notes/`. No clone, no `git pull` on Mac.
- Mac reads `git log` to know what's new. **No handoff document needed.**
- Mac may commit + push small fixes back to `origin/main` from inside its `/sync-field-notes` skill. These commits are co-authored by Claude Opus.
- Spark keeps authoring articles, evidence, signatures, and the fieldkit landing as before. Drop the SYNC-HANDOFF.md authoring and SHIPPED-flip ceremony — they're now no-ops.
- `mirrors/destination-overrides.md` is still the contract for "paths Mac owns, source must not stomp."

For the full destination-side workflow (what Mac actually does), see `.claude/skills/sync-field-notes/SKILL.md` in the destination repo at `ainative-business.github.io`.
