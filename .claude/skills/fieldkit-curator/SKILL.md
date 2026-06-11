---
name: fieldkit-curator
description: Cut releases of the `fieldkit` Python package at `/home/nvidia/ainative-business.github.io/fieldkit/`. Trigger when the user says "cut a fieldkit release", "release fieldkit v0.X.Y", "tag fieldkit", "ship fieldkit", "publish fieldkit", "distribute fieldkit to pypi", "audit fieldkit docs", "check fieldkit docs drift", invokes `/fieldkit-curator`, or asks about bumping the package version, regenerating CHANGELOG, tagging, verifying a fresh-venv install, or whether the `fieldkit/docs/api/` pages match the modules' `__all__` exports. **Two modes:** *interactive* (default — confirms bump kind and `--spark` decision) and *full-auto* ("publish/ship/distribute fieldkit to pypi" — auto-resolves bump kind from `[Unreleased]`, runs end-to-end, stops only on hard errors). Implemented: **release** (CHANGELOG → audit-docs → tests → bump → tag → push → install verify → PyPI build/upload → install verify → stats → HANDOFF), **audit-docs** (standalone pre-flight: diffs each module's `__all__` against `fieldkit/docs/api/<module>.md`, flags missing pages + undocumented symbols). **audit**, **samples**, **docs**, **extract-help** are stubs. Don't trigger for general fieldkit usage, article writing, or non-release maintenance — those belong to the docs site or `tech-writer`.
---

# fieldkit-curator

Cut releases of the `fieldkit` Python package that lives in the Spark-owned monorepo (build workspace + `ainative.business` website) at `/home/nvidia/ainative-business.github.io/fieldkit/`. The package's release cadence is *editorial* — every 3–4 articles cuts a minor version (~2/quarter), per the maintenance budget decision in `ideas/fieldkit.md`.

The fieldkit package itself is the second deliverable of the publication pipeline (the blog is the first). It's a standalone product with its own version, CHANGELOG, and tags — distinct from the blog's article-publication events. This skill keeps the release process sharp without making it ceremonial.

## Mode router

The skill operates in six modes — `release` and `audit-docs` ship; the others are stubbed for future work and the body intentionally errors out so they don't run half-baked. Detect the mode from phrasing, then follow the playbook below.

| User intent | Mode | Status |
|---|---|---|
| "cut a release", "release v0.X.Y", "tag fieldkit", "ship fieldkit", "/fieldkit-curator release" | **release** (interactive) | Implemented |
| "distribute fieldkit to pypi", "publish fieldkit", "publish fieldkit to pypi", "ship fieldkit to pypi" | **release** (full-auto) | Implemented |
| "audit fieldkit docs", "check fieldkit docs drift", "are the API docs in sync", "/fieldkit-curator audit-docs" | **audit-docs** | Implemented |
| "audit fieldkit landing", "check fieldkit landing-page drift", "is the fieldkit page in sync", "/fieldkit-curator audit-landing" | **audit-landing** | Implemented |
| "audit fieldkit drift", "is the article still in sync", "/fieldkit-curator audit" | **audit** (articles vs package) | Stub — refuse and explain |
| "regenerate samples", "/fieldkit-curator samples" | **samples** | Stub — refuse and explain |
| "regenerate fieldkit docs", "rebuild API reference from docstrings", "/fieldkit-curator docs" | **docs** (auto-extract from docstrings) | Stub — refuse and explain |
| (called internally by `tech-writer extract`) | **extract-help** | Stub — refuse and explain |

For unimplemented modes, tell the user the mode isn't built yet, point them at `ideas/fieldkit.md` Phase 8.5 (the spec slot they live in), and ask whether they want to run `release` instead. Don't make up behavior.

## Every invocation — read these first

1. **Spec:** `/home/nvidia/ainative-business.github.io/ideas/fieldkit.md` — decisions A–M (especially **D** Distribution: git-based until v1.0; **L** Maintenance budget: ~2 hrs/week; **M** Versioning: semver, breaking changes allowed in v0.x). The release process section near the bottom is the canonical workflow this skill executes.
2. **State:** `/home/nvidia/ainative-business.github.io/HANDOFF.md` — see what's "in-flight from Frontier Scout" and which articles have landed `fieldkit_modules` frontmatter since the last release. Everything in `[Unreleased]` of `CHANGELOG.md` came from `tech-writer extract` runs; the release entry is what the user has chosen to ship.
3. **Memory pointers worth re-reading:**
   - `project_nvidia_learn_git_workflow` — solo blog, push to `main` directly, no PRs, harness denies main-push by default so a permission prompt is expected on first push per session.
   - `feedback_terminal_bang_unavailable` — for any sudo/TTY/interactive bit (e.g., GPG passphrase) hand the user a copy-pasteable block; do not assume `!command` works.
4. **Current version:** read `fieldkit/src/fieldkit/_version.py` (single source of truth — `pyproject.toml`'s `[tool.hatch.version]` reads from it). The latest tag is `git tag -l 'fieldkit/v*' | sort -V | tail -1`.

## Mode: release

Goal: turn the `[Unreleased]` section of `fieldkit/CHANGELOG.md` into a versioned, git-tagged, install-verified release. Pushed to `origin/main` and PyPI. Stats and HANDOFF refreshed so the home-page infographic and the next session both show the new state.

This is the workflow this skill's ancestors (the v0.1.0 phases) executed by hand. It runs ~2× per quarter; codifying it keeps each one ~30 minutes instead of an hour of remembering.

### Invocation modes — interactive vs full-auto

Two ways to launch this mode:

- **Interactive** (default — phrases like "cut a release", "release v0.X.Y", "tag fieldkit", "ship fieldkit Y", "/fieldkit-curator release"): walk through the Inputs section below, *confirm bump kind and the `--spark` decision with the user*, then execute steps 1–12.
- **Full-auto** (phrases like "distribute fieldkit to pypi", "publish fieldkit", "publish fieldkit to pypi", "ship fieldkit to pypi"): **skip all input confirmation**. Auto-resolve everything from repo state, then execute steps 1–12 unattended. The skill only stops on hard errors (empty `[Unreleased]`, failing tests, install-verify failure, twine-check failure). The user expects the next time they hit Enter, fieldkit is on PyPI.

Auto-resolution rules in full-auto mode:
- **Bump kind:** if `[Unreleased]` adds a new top-level module / submodule / public class → `minor`. If it only changes docstrings, samples, fixtures, or internal helpers → `patch`. If it removes or breaks a public symbol → `minor` (v0.x allows breakage per Decision M; never auto-pick `major`, that's reserved for v1.0+ and requires a human decision).
- **`--spark` decision:** if any `[Unreleased]` bullet mentions `fieldkit.nim`, `fieldkit.rag`, `fieldkit.eval`, NIM, embed, pgvector, or `--spark` itself → run `pytest --spark` (and warm the chat NIM then the embed NIM beforehand, in that order — see step 3 + the OOM landmine memory). Otherwise run offline `pytest` only.
- **Commit message:** generate from the CHANGELOG section being finalized — first bullet of **Added** (or **Changed**, if no Added) becomes the one-line summary; commit body lists the article slugs from `git log <last-tag>..HEAD -- articles/`.
- **Hard stops** (skill halts and reports back to the user even in full-auto):
  - `[Unreleased]` is empty → refuse, tell user to add entries via `tech-writer extract` first.
  - `audit-docs` returns non-zero (any module ships without an API doc page or with undocumented `__all__` symbols) → refuse, point the user at the missing pages. New modules in `[Unreleased]` are the common case; fix the docs before re-running.
  - `audit-landing` returns non-zero (the fieldkit landing page hardcodes a module count, the wrong "N imports" headline, a hardcoded version literal, missing tagline, or doc-page `order:` collision) → refuse, point the user at the offending file. New modules in `[Unreleased]` always shift the canonical `order:` and the displayed count; fix the landing page before re-running.
  - Tests fail → refuse, do not tag, do not push, do not upload.
  - `twine check` fails → refuse, do not upload, suggest the metadata fix.
  - Git install verify (step 7) or PyPI install verify (step 9) fails → refuse to mark release complete, surface the error.

### Inputs

Read these into context before executing steps. In **interactive** mode, confirm each with the user. In **full-auto** mode, resolve each per the auto-resolution rules above and proceed without prompting (just log what was resolved, in the final report).

1. **Bump kind.** `patch | minor | major`. v0.x permits breaking changes between minors per Decision M, so the choice is *editorial*: did the API surface widen (minor) or did the recipe details get tightened (patch)? Interactive: if the user says "cut a release" without specifying, propose a default based on `[Unreleased]` content and ask them to confirm. Full-auto: apply the auto-resolution rule above without asking.
2. **CHANGELOG draft.** Read `fieldkit/CHANGELOG.md`'s `[Unreleased]` section. If it's empty, refuse in both modes — releases need at least one user-visible change. If it's stale (last entry's date significantly older than today), interactive mode asks whether anything from recent articles should land first; full-auto mode proceeds with what's there and notes it in the final report.
3. **Articles since last release.** `git log --oneline <last-tag>..HEAD -- articles/` shows which articles landed in this window. Their frontmatter `fieldkit_modules` lists are the editorial-side acknowledgement that this release is the one those articles assume.

### Steps

Once the inputs are confirmed:

1. **Bump the version.** Edit `fieldkit/src/fieldkit/_version.py` to the new version. Don't touch `pyproject.toml` — its `[tool.hatch.version]` already reads from `_version.py`. Run `python3 -c "from fieldkit import __version__; print(__version__)"` from `fieldkit/` to verify the bump took.

2. **Finalize the CHANGELOG.** Move everything from `## [Unreleased]` to a new `## [0.X.Y] — YYYY-MM-DD` section. Leave a fresh empty `## [Unreleased]` heading at the top. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/): subsections in the order **Added · Changed · Deprecated · Removed · Fixed · Security**. v0.x entries are usually **Added** + **Changed**.
   - Cross-link reference labels (`[#capabilities]: …`) at the bottom — match the pattern from the v0.1.0 entry.
   - Add a **Verified on Spark** sub-section if any module was live-tested against NIM / pgvector / NemoClaw during the cycle (mirror v0.1.0's structure).
   - Add a **Test suite** sub-section with the test count: `cd fieldkit && pytest` for offline; `pytest --spark` against warm NIMs for the live count.
   - Add a **Articles in this release** sub-section listing the articles whose `fieldkit_modules` frontmatter assumes this version — pulled from `git log <last-tag>..HEAD -- articles/`.

2b. **Audit docs drift (new gate).** Run the bundled audit before tests so missing API pages stop the release before the heavier work runs:
   ```bash
   python3 /home/nvidia/ainative-business.github.io/.claude/skills/fieldkit-curator/scripts/audit_docs.py
   ```
   Hard-stops on any FAIL — most commonly, a `[Unreleased]` entry added a module (e.g. `fieldkit.publish`) without a corresponding `fieldkit/docs/api/publish.md`, or a new public class in an existing module's `__all__` that the docs page doesn't mention. SKIP rows (module has no explicit `__all__`, like `fieldkit.cli`) don't fail. Fix by writing or extending the markdown page (model the shape after `fieldkit/docs/api/lineage.md`), then re-run. See **Mode: audit-docs** below for the standalone flow and what the script checks.

   **Kwarg drift (v0.4.1 catch-up — soft WARN by default).** The audit now also flags keyword-only args on public functions / methods that aren't mentioned in the corresponding docs page. As of 2026-05-14 there are 26 pre-existing kwarg-drift items across `rag` / `eval` / `quant` / `publish` (added before the check existed); they surface as `WARN` lines under each module's PASS line and don't block release. **For any release whose `[Unreleased]` block mentions kwargs / params / defaults on existing public methods**, add `--strict-kwargs` to elevate kwarg drift to FAIL:
   ```bash
   python3 /home/nvidia/ainative-business.github.io/.claude/skills/fieldkit-curator/scripts/audit_docs.py --strict-kwargs
   ```
   This catches the v0.4.1-class drift where `VerticalBench.from_jsonl` gained `open_book` + `subset` kwargs and shipped undocumented. Once the existing 26 items are documented across passes, flip the default to `--strict-kwargs` for every release.

2c. **Audit landing-page drift (new gate).** The `audit-docs` gate proves `__all__` symbols are documented; this one proves the marketing surface — `src/pages/fieldkit/index.astro` and `src/components/sections/fieldkit/*.astro` — didn't drift. Stale module counts ("7 / seven"), missing taglines for new modules, hardcoded version literals, and `docs/api/<module>.md` `order:` collisions all silently survive `astro build` because nothing in TypeScript or Zod enforces "in sync with `_version.py` and `FIELDKIT_MODULES`".
   ```bash
   python3 /home/nvidia/ainative-business.github.io/.claude/skills/fieldkit-curator/scripts/audit_landing.py
   ```
   Hard-stops on any FAIL. The six checks are documented under **Mode: audit-landing** below. Common fixes: thread a new module's tagline into BOTH `FieldkitModules.astro` copies (main + arena-app), bump a doc page's `order:` to its 1-based `FIELDKIT_MODULES` index, swap a hardcoded `0.X.Y` literal for the `version` prop, trim a new module's doc `summary:` to the 60–260-char reader-facing band. Re-run after each fix; aim for 6/6 PASS before tagging.

3. **Run the test suite.** From `fieldkit/`:
   ```bash
   /tmp/fk/bin/pytest tests/                  # → expect N passed, M skipped
   ```
   If `--spark` integration tests are part of the release-readiness bar (typically yes for modules that touch NIM / pgvector), the user must have warmed the chat NIM first then the embed NIM (sequence per `project_spark_unified_memory_oom`). Run:
   ```bash
   docker start nim-llama31-8b && sleep 120 && docker start nim-embed-nemotron
   /tmp/fk/bin/pytest tests/ --spark          # → expect K passed
   ```
   Don't tag if anything fails. Investigate root cause; never `--no-verify` past it.

4. **Stage + commit on `main`.** Solo-blog workflow per `project_nvidia_learn_git_workflow`: branch is `main`, commit is direct.
   ```bash
   git add fieldkit/src/fieldkit/_version.py fieldkit/CHANGELOG.md
   git commit -m "fieldkit v0.X.Y: <one-line summary>"
   ```
   The commit message body should reference the articles whose `fieldkit_modules` assume this version.

5. **Tag the release.** Annotated tag, prefixed (Decision Q1). Signed if the host has GPG configured; unsigned if not — v0.1.0 was unsigned for this reason and the convention stays for continuity until GPG is set up.
   ```bash
   git tag -a fieldkit/v0.X.Y -m "fieldkit v0.X.Y"
   # Or, if GPG is configured: git tag -s fieldkit/v0.X.Y -m "fieldkit v0.X.Y"
   ```

6. **Push commit + tag.** First main-push of the session triggers a permission prompt — that's expected. Don't suggest `--no-verify` or other ways around it.
   ```bash
   git push origin main
   git push origin fieldkit/v0.X.Y
   ```

7. **Verify install in a fresh venv (git source).** This is the gate that catches packaging mistakes (missing `MANIFEST.in` entries, wrong import paths, etc.) before a reader hits them. Use a temp directory each time so caches don't mask issues.
   ```bash
   python3 -m venv /tmp/fk0XY && /tmp/fk0XY/bin/pip install -q \
     "git+https://github.com/manavsehgal/ainative-business.github.io.git@fieldkit/v0.X.Y#subdirectory=fieldkit"
   /tmp/fk0XY/bin/fieldkit version          # → 0.X.Y
   /tmp/fk0XY/bin/fieldkit envelope "70B params fp8"
   /tmp/fk0XY/bin/fieldkit feasibility llama-3.1-70b --ctx 4096 --batch 32 --dtype fp8
   ```
   If the install fails, revert the tag (`git tag -d fieldkit/v0.X.Y && git push origin :refs/tags/fieldkit/v0.X.Y`), fix, re-tag, re-push. **Tag-revert is the one destructive operation in this flow** — confirm with the user before pulling the tag down from origin.

8. **Build PyPI artifacts and upload.** Auth is a project-scoped PyPI token stored as `PYPI_TOKEN` in `/home/nvidia/ainative-business.github.io/.env.local` (gitignored, chmod 600 — set up during the v0.1.0 bootstrap, see `Distribution` section of v0.1.0 CHANGELOG). From `fieldkit/`:
   ```bash
   rm -rf dist/ build/ src/fieldkit.egg-info/
   /tmp/fk/bin/python -m build              # → dist/fieldkit-0.X.Y-py3-none-any.whl + .tar.gz
   /tmp/fk/bin/twine check dist/*           # → PASSED for both
   set -a && . /home/nvidia/ainative-business.github.io/.env.local && set +a
   TWINE_USERNAME=__token__ TWINE_PASSWORD="$PYPI_TOKEN" TWINE_NON_INTERACTIVE=1 \
     /tmp/fk/bin/twine upload dist/*        # → View at: https://pypi.org/project/fieldkit/0.X.Y/
   ```
   If `twine check` fails, fix metadata and rebuild *before* uploading — PyPI rejects re-uploads of the same version, and recovery requires a `0.X.Y.post1` post-release bump (not a minor). If `/tmp/fk` doesn't exist, recreate: `python3 -m venv /tmp/fk && /tmp/fk/bin/pip install -e "/home/nvidia/ainative-business.github.io/fieldkit/[dev]"`.

9. **Verify install from PyPI in a fresh venv.** Mirrors step 7 but pulls from PyPI instead of git, catching any sdist/wheel-only packaging bugs (e.g., missing data files, broken entry points):
   ```bash
   rm -rf /tmp/fk-pypi
   python3 -m venv /tmp/fk-pypi && /tmp/fk-pypi/bin/pip install --no-cache-dir fieldkit==0.X.Y
   /tmp/fk-pypi/bin/fieldkit version          # → 0.X.Y
   rm -rf /tmp/fk-pypi
   ```
   PyPI propagation is usually instant on `pip install <name>==<exact>` since pip checks the simple index directly. If pip can't find the version, wait 60s and retry — the CDN occasionally lags.

10. **Refresh project-stats.** The home-page "At a glance" infographic reads `src/data/field-notes/project-stats.json`; the LOC count includes `fieldkit/src/` and `fieldkit/tests/` (excluding the gitignored `_webui/` baked bundle), so any release that adds modules / tests will move the number. Per `feedback_refresh_stats_on_publish`:
   ```bash
   python3 /home/nvidia/ainative-business.github.io/.claude/skills/nvidia-learn-stats/scripts/compute_stats.py
   ```
   Stage + commit:
   ```bash
   git add src/data/field-notes/project-stats.json
   git commit -m "Refresh stats post-fieldkit-v0.X.Y"
   git push origin main
   ```

11. **Update `HANDOFF.md`.** Per `feedback_handoff_md_update_protocol`, rewrite or amend the living session-transfer doc so the next session opens to the new state. At minimum: bump the **Last updated** line, the **Latest tag** field, the **TL;DR** version line, and the **fieldkit state** entry (include both the git tag and the PyPI URL). Add or trim the next-priority section.

   `HANDOFF.md` is **tracked** (since 2026-06-02) — commit it along with the stats refresh. The user reviews it; that's the contract.

12. **Report.** One short message in chat covering: new version, tag pushed, PyPI URL, stats refresh commit, both install-verifies ✅, anything that moved in `HANDOFF.md`. Don't paste the CHANGELOG or test output — those are the artifact.

### Non-negotiables for `release`

- **Never push without a passing test suite.** `pytest --spark` for any release that touches modules with live integration tests; offline-only is acceptable for changes that genuinely don't touch the live paths.
- **Never amend or force-push a published tag.** If the git install verify fails, the recovery is a *new* tag (e.g., v0.X.Y → v0.X.Y+1). Never modify an already-pushed tag.
- **Never re-upload the same PyPI version.** PyPI permanently rejects it. If a metadata bug ships, recover with a `0.X.Y.post1` post-release (same code, fixed metadata) — never delete-and-reupload, never bump minor for metadata-only fixes.
- **Never put the PyPI token in the repo or in chat.** The token lives in `/home/nvidia/ainative-business.github.io/.env.local` (chmod 600, gitignored) as `PYPI_TOKEN`. Source it into env vars at upload time; do not echo, paste, or hardcode. If it leaks, rotate at <https://pypi.org/manage/account/token/> immediately and update `.env.local`.
- **Never bypass the main-push prompt** with `--no-verify`, GPG-skip, or any other shortcut. The harness's prompt is the user's checkpoint.
- **Never skip either install verify.** Step 7 (git source) and step 9 (PyPI) catch different packaging classes — the git path validates source-tree completeness; the PyPI path validates the wheel/sdist actually built and published correctly. v0.1.0 caught issues both ways.
- **Never silently skip the stats / HANDOFF refresh.** They are part of the release, not optional after-care.
- **Never bypass `audit-docs` to tag.** If new modules are in `[Unreleased]` without doc pages, the customer-facing `/fieldkit/api/<module>/` route 404s after deploy. The audit costs ~50ms; suppressing it to skip the editorial work that a release should include is the wrong tradeoff.
- **Never bypass `audit-landing` to tag.** The fieldkit landing page reads the module count, version, and module list at build time; drift here is silent (no test, no Zod check) and ships straight to readers as the wrong "in N imports" headline or a stale `v0.2.0` in the CLI demo. The audit costs ~30ms.

## Mode: audit-docs

Goal: cheap, fast pre-flight that the `fieldkit/docs/api/<module>.md` pages haven't drifted from the package's actual `__all__` exports. Catches the v0.4 trap that motivated this script — shipping `fieldkit.publish` + `fieldkit.quant` modules without `publish.md` / `quant.md` would 404 the `/fieldkit/api/publish/` and `/fieldkit/api/quant/` Astro routes on the destination site, even though the modules are live in the package.

The bundled script (`scripts/audit_docs.py`) parses each module's `__all__` via Python AST (robust against import side-effects) and checks every exported symbol against a word-boundary regex match on the docs file. The audit is intentionally substring-flexible — it doesn't enforce *how* a symbol is documented, only *that* it's mentioned somewhere. This keeps the editorial voice of the docs free while still catching drift.

### Invocation

```bash
# Human-readable (default)
python3 /home/nvidia/ainative-business.github.io/.claude/skills/fieldkit-curator/scripts/audit_docs.py

# Machine-readable — used by `release` flow + any CI hook
python3 /home/nvidia/ainative-business.github.io/.claude/skills/fieldkit-curator/scripts/audit_docs.py --json

# Strict kwarg-drift mode — elevates kwarg WARN lines to FAIL (use for releases
# that add kwargs / params / defaults on existing public methods)
python3 /home/nvidia/ainative-business.github.io/.claude/skills/fieldkit-curator/scripts/audit_docs.py --strict-kwargs
```

Exit code = number of FAIL verdicts (symbol coverage; also kwarg drift when `--strict-kwargs`). 0 = ready to release; ≥1 = drift, fix before tagging. Standalone invocation is read-only — never edits files.

### What it checks

For each module in `FIELDKIT_MODULES` (`capabilities`, `nim`, `rag`, `eval`, `training`, `lineage`, `quant`, `publish`, `cli`):

1. **Source resolution** — finds `fieldkit/src/fieldkit/<module>/__init__.py` (packages) or `fieldkit/src/fieldkit/<module>.py` (flat). Modules that don't exist on disk emit `SKIP`.
2. **`__all__` extraction** — parses the AST; pulls the string literals from the top-level `__all__ = [...]` (or tuple) assignment. Modules without an explicit `__all__` (or with a computed one) emit `SKIP` — they're considered out of scope for the audit.
3. **Docs file presence** — `fieldkit/docs/api/<module>.md` must exist; missing pages emit `FAIL` with the full list of symbols that would need coverage.
4. **Symbol coverage** — each `__all__` entry must appear in the docs text via a word-boundary regex (`\bSymbol\b`). `Capability` won't false-match `Capabilities`, but `Bench(...)`, `Bench,`, or `Bench\n` all match `Bench`. Partial coverage emits `FAIL` with the list of missing symbols.
5. **Kwarg coverage** — for every top-level public function in `__all__` and every public method of every class in `__all__`, AST-walks the sources (init + any package sub-modules like `eval/vertical.py`) and extracts the keyword-only args (after `*` in the signature). Each kwarg name must appear in the docs text via word-boundary regex. Coverage gap emits a `WARN` line under the module's verdict (visibility-only by default; `--strict-kwargs` elevates to FAIL). This is the v0.4.1 trap — `VerticalBench.from_jsonl` gained `open_book` + `subset` kwargs without docs catch-up; the symbol-coverage check passes because `VerticalBench` itself is mentioned but the new kwargs slipped through.

### What it does NOT check

By design — these belong in other modes or in human review:

- **Whether the *prose* describing each symbol is accurate.** Drift in semantics (a class field was renamed) is the `audit` mode's territory (still stubbed), not this one. Catching it would require source-truth comparison far beyond `__all__`.
- **Whether code examples in the docs actually run.** Snippet rot is real but not free to test; `samples/` regeneration (stubbed `samples` mode) is the right home.
- **Whether the docs file's frontmatter (`module`, `title`, `summary`, `order`) is valid.** Astro's Zod schema (`src/content.config.ts`) does that at build time; this script doesn't duplicate the check.
- **Removed-symbol references** ("orphan" mentions in the docs). Prose may legitimately reference a removed API in a transition paragraph; flagging it would produce false positives.

### Modeling docs after the canonical shape

When the audit flags a new symbol that needs coverage, model the new entry after `fieldkit/docs/api/lineage.md` (medium-density, public-API-focused) or `eval.md` (higher density, multi-version). The five-section shape:

```
## What it is             — motivation + concrete use case (1–2 paragraphs)
## Public API             — `from fieldkit.<mod> import (...)` block + per-symbol code-block examples
## Why this surface       — design rationale (why duck-typed, why frozen, why this name)
## Samples                — script paths + anchor article link
```

Every public symbol from `__all__` should appear somewhere in `## Public API`. The script's coverage check is the lower bound; the editorial bar is higher.

## Mode: audit-landing

Goal: cheap, fast pre-flight that the fieldkit *landing page* — `src/pages/fieldkit/index.astro` and its sibling components under `src/components/sections/fieldkit/` — hasn't drifted from the package's actual surface area. `audit-docs` proves the API reference is in sync with `__all__`; `audit-landing` proves the marketing surface above the fold is in sync with `FIELDKIT_MODULES` + `_version.py` + the doc-page `order:` schema. This is the v0.4-era drift that motivated the script: the page kept saying "7 / seven imports" and listed only `{capabilities,nim,rag,eval,training,lineage,cli}` long after `quant` and `publish` shipped, because nothing in `astro build` or `pytest` fails when a number is wrong, only when a *type* is wrong.

The bundled script (`scripts/audit_landing.py`) reads `FIELDKIT_MODULES` directly out of `src/content.config.ts` (regex against the array literal — robust against re-arrangement) and `__version__` out of `fieldkit/src/fieldkit/_version.py`. No build is invoked.

### Invocation

```bash
# Human-readable (default)
python3 /home/nvidia/ainative-business.github.io/.claude/skills/fieldkit-curator/scripts/audit_landing.py

# Machine-readable — used by `release` flow + any CI hook
python3 /home/nvidia/ainative-business.github.io/.claude/skills/fieldkit-curator/scripts/audit_landing.py --json
```

Exit code = number of FAIL verdicts. 0 = clean; ≥1 = drift, fix before tagging. Standalone invocation is read-only.

### What it checks

Six checks against the six kinds of silent drift in landing-page copy:

1. **`module_count_dynamic`** — `FieldkitProblem.astro` must import + use `FIELDKIT_MODULES` for the "modules, one import each" stat (not a hardcoded `'7'` string). `FieldkitModules.astro` must derive its "fieldkit in N imports" headline from `docs.length` / `moduleCount` / `moduleCountWord`, not from a static English word or integer literal. Catches the v0.4 drift directly.

2. **`no_hardcoded_versions`** — no `*.astro` file under `src/components/sections/fieldkit/` may contain a `0.X.Y`-shaped literal. `FieldkitHero`, `FieldkitCli`, and `FieldkitCTAFooter` all accept a `version` prop wired from the landing page's `_version.py` read; any new section that displays the version must follow that pattern, not paste `0.4.0` inline. Catches the v0.4 case where `FieldkitCli.astro` still showed `$ fieldkit version → 0.2.0` long after v0.3 / v0.4.

3. **`module_taglines`** — every module in `FIELDKIT_MODULES` must have a ≤56-char entry in the `taglines` map inside BOTH copies of `FieldkitModules.astro` — the main-site one AND `arena-app/src/components/sections/fieldkit/FieldkitModules.astro` (the arena-app copy is the easy miss; it froze at 13 taglines while 18 modules shipped, caught 2026-06-10). Without one, the card falls back to the doc summary and visually misaligns with its siblings; over-length taglines wrap and break the card grid's anchor line. Also flags taglines for modules that have been *removed* from `FIELDKIT_MODULES`.

4. **`docs_order_matches_modules`** — every `fieldkit/docs/api/<module>.md` `order:` frontmatter must equal that module's 1-based index in `FIELDKIT_MODULES`. `FieldkitModules.astro` sorts cards by `order`, so collisions silently swap card positions on the page (the v0.4 trap: `cli.md order: 7` collided with the new `quant.md order: 7`, leaving `cli` mid-grid until detected). Astro's Zod schema only validates that `order:` is an integer — it can't enforce the cross-file uniqueness or canonical ordering, so this script does.

5. **`landing_version_source`** — `src/pages/fieldkit/index.astro` must read the version from the package's canonical `fieldkit/src/fieldkit/_version.py` (the hatch single source of truth that the release flow bumps), and the retired two-repo-era mirror `fieldkit/_version.py` must not exist. Catches the post-cutover drift where the live page rendered **v0.13.0 for 18 releases** (until 2026-06-10): releases bumped only the canonical file while the page read the orphaned mirror the retired `sync-field-notes` skill used to maintain.

6. **`doc_summary_balance`** — each `fieldkit/docs/api/<module>.md` `summary:` renders verbatim as that module's landing-card body, so it must stay reader-facing and balanced across the grid: 60–260 chars, and no internal milestone codenames (`M6` / `H3` / `W3` / `Bet 5` / `Phase 2` / `_SPECS/` paths — they mean nothing to a visitor). Ship-log detail belongs in the doc body below the frontmatter, not in the card. Catches the pre-v0.31 state where `training`'s summary ran ~780 chars beside `cli`'s 96, and `arena`/`harness` read like milestone changelogs. **When a new module ships, write its `summary:` to this contract from day one.**

### What it does NOT check

By design — these belong elsewhere or in human review:

- **Visual layout regressions** (text overflow, container bleed, font-size collisions). Those need a Playwright smoke test or human eyes; this script is text-only.
- **Whether the headline copy is *good*.** "fieldkit in nine imports" is mechanically correct at 9 modules; whether nine is the right number of modules to highlight in the headline is an editorial call.
- **Whether non-fieldkit pages drift.** The home-page infographic is owned by `nvidia-learn-stats`; the per-stage filter pages have their own ordering logic. This script is narrowly scoped to the fieldkit landing surface.

### Updating the script when the page evolves

When `src/components/sections/fieldkit/` gains a new section, decide whether it carries any of the six drift classes:
- If it displays a module count → the script's regex for the headline / stat needs an additional match.
- If it displays a version → either thread the `version` prop in (preferred) or extend the script's allowlist.
- If it lists modules by name → add it to the module-list check.

The script is the schema. Keeping it lean is more important than catching every conceivable drift; we can always add a check after a class of drift has shown up once.

These are listed in `ideas/fieldkit.md`'s skill-modifications section. When a user asks for one, refuse + redirect to the spec; don't half-implement.

### audit (articles vs package)
Distinct from the implemented `audit-docs` mode: this would find drift between *articles*' `fieldkit_modules` frontmatter + code snippets and the package's actual public surface. Flags articles whose example code references a symbol that has since changed signature or moved modules. Cadence: ad-hoc, before each release. `audit-docs` covers `__all__` vs docs; this one would cover `__all__` vs every article's `evidence/` snippets — a fundamentally bigger lift requiring snippet extraction + per-snippet import resolution.

### samples
Regenerate `fieldkit/samples/<arc>/` from article `evidence/` so samples don't go stale. The four current samples (`feasibility-math.py`, `hello-nim.py`, `naive-rag.py`, `bench-rag.py`) are hand-curated — that's fine for v0.1; this mode would automate it once a fifth or sixth lands.

### docs
Regenerate the Astro `/fieldkit/api/<module>/` reference pages from each module's docstrings. Currently the docs are hand-written markdown under `fieldkit/docs/api/`; this mode would extract from the package source and rewrite them. Belongs in the build pipeline, not the editorial workflow.

### extract-help
Helper for `tech-writer extract` mode. When that skill identifies code in an article's `evidence/` that should land in fieldkit, this mode formats the proposal as a CHANGELOG bullet under `[Unreleased]`. Not user-invokable directly.

## Where to look for deeper guidance

- **Spec:** `/home/nvidia/ainative-business.github.io/ideas/fieldkit.md` — Decisions, Architecture, Module-by-module spec, Implementation plan (Phases 0–11+), Release process section.
- **CHANGELOG conventions:** [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
- **Sibling skills:**
  - `tech-writer` `extract` mode — produces the `[Unreleased]` entries this skill consolidates at release time.
  - `frontier-scout` `eval` mode — its `## Fieldkit fit` section feeds the editorial roadmap that determines when a module slot graduates from deferred to shipped.
  - `nvidia-learn-stats` — owns `compute_stats.py`, called from step 10.
- **Memory pointers used in `release` flow:** `project_nvidia_learn_git_workflow` (push to main), `feedback_handoff_md_update_protocol` (HANDOFF rewrite), `feedback_refresh_stats_on_publish` (stats refresh ordering), `feedback_terminal_bang_unavailable` (interactive command etiquette), `project_spark_unified_memory_oom` (NIM warmup ordering for `--spark` tests).
