# Sub-Skill Contracts

This file documents the Plan/Execute contract every sub-skill must honor so the `apply-product-release` orchestrator can chain them reliably.

## Required SKILL.md structure

Every sub-skill's `SKILL.md` must contain these section headers in order:

```
## Workflow
(introductory note explaining the two-phase structure)

## Plan Phase
(detection, diffing, cache reads — no file writes, no prompts)

## Plan Output Format
(canonical markdown block the sub-skill emits at the end of Plan Phase)

## Execute Phase
(file writes, copies, rebuilds, audits)
```

All 5 sub-skills follow this structure:

| Sub-skill | Plan Phase steps | Execute Phase steps |
|---|---|---|
| `apply-screengrabs` | 1-5 (detect mode, hash-diff, build rename map, scan references, alt-text drift check) | 6-12 (rename pass, orphan resolution, copy, alt-text sync, cache, build, report) |
| `apply-product-docs` | 1-6 (load mapping, detect mode, page status, product-only classification, image-rewrite scan, marker placement detection) | 7-12 (apply markers, sync bodies, handle product-only decisions, cache, build, report) |
| `apply-api-docs` | 1-4 (inventory, validators, types, incremental check) | 5-9 (generate pages, update index, navigation, manifest, verify) |
| `apply-book-update` | 1-2 (detect sync mode, compare files) | 3-7 (copy chapters, images, code files, build, audits, report) |
| `ainative-stats` | 1-7b (verify tools, LOC, tests, git velocity, feature status, infra counts, quality, business primitives) | 8-10 + website propagation (write report, trend comparison, save snapshot, update website, verify) |

## Plan Output Format — canonical block shape

Every sub-skill ends Plan Phase by emitting a block matching this minimum shape. Sub-skills may add additional fields (clearly labeled) that are specific to their domain:

```markdown
### <skill-name>
- **Status**: changed | no-changes | error
- **Summary**: <one-line description>
- **Changes**:
  | Type | Item | Reason |
  |------|------|--------|
  | create | foo.mdx | new domain |
  | update | bar.md | content diff |
  | delete | baz.png | stale |
- **Risks**: (optional) drift warnings, forbidden patterns, etc.
```

### Per-skill additional fields (seen in current SKILL.md files)

- `apply-screengrabs`: `**Mode**`, `**Renames**` (table), `**Orphans for user decision**` (table), `**Alt-text drift**` (table)
- `apply-product-docs`: `**Mode**`, `**Page status**` (table), `**Marker placement**` (table), `**Product-only docs**` (table)
- `apply-api-docs`: (base shape, no additions)
- `apply-book-update`: `**Mode**`
- `ainative-stats`: `**Deltas**` (table), `**Website targets affected**` (list)

The orchestrator concatenates whatever each sub-skill emits verbatim and presents the full aggregate.

## Invocation pattern

The orchestrator invokes each sub-skill via the `Skill` tool. Skills do not accept parameters, so "run Plan Phase only" is communicated via prose instruction:

> "Invoke Skill(apply-book-update). Tell it to run only the content under its `## Plan Phase` header, emit the block under `## Plan Output Format`, and return control without writing any files or prompting for confirmation."

Each sub-skill's `## Plan Phase` explicitly states this contract in its intro paragraph. When the sub-skill is being run standalone (user invoked it directly, not via orchestrator), it proceeds automatically into Execute Phase after firing its own single gate at the Plan→Execute boundary.

## Sub-skill execution order

For Execute Phase, sub-skills MUST run in this order:

1. **`apply-screengrabs`** — images first, because docs/book/research reference them. A stale reference would break the next step's build verification.
2. **`apply-product-docs`** — docs may reference newly-renamed screenshots. Must run after screengrabs or the sync will reintroduce pre-rebrand references.
3. **`apply-api-docs`** — independent of docs/screengrabs; generates its own `/docs/api/` subsite.
4. **`apply-book-update`** — independent; book owns its own `/book/images/` subdirectory (not `/screenshots/`).
5. **`ainative-stats`** — LAST. It propagates counts into `Proof.astro`, `timeline.ts`, `research.mdx`, and 4 SVG files. These files may have been touched by earlier steps (e.g., research.mdx drift audit from apply-book-update). Running stats last ensures the final state is authoritative.

## In-skill confirmation gates — removed

Prior to the Plan/Execute refactor, `apply-api-docs` had a Step 5 "User Confirmation Gate". This has been deleted. The orchestrator now owns all gating. When a sub-skill runs standalone, it prompts once at the Plan→Execute boundary with a single universal gate.

## Partial approval

The orchestrator supports partial approval in its Stage 3 Approval Gate. The user may respond with:

- `proceed` — approve all sub-skills
- `abort` — cancel the run, no Execute Phase runs
- `skip <name>` — proceed with all EXCEPT the named sub-skill(s) (may be repeated)
- `only <name>` — proceed with ONLY the named sub-skill(s)

The orchestrator records the approval decision per sub-skill. Skipped sub-skills report "skipped by user" in the final summary.

## Error handling

If any sub-skill reports Status: error in its Plan Output, the orchestrator stops before Stage 3 (approval gate) and surfaces the error. The user fixes it and re-invokes.

If any sub-skill reports an error DURING Execute Phase, the orchestrator stops before Stage 5 (build) and reports. Sub-skills that already completed their Execute Phase have already committed their changes (each sub-skill may update the working tree but the orchestrator does NOT auto-commit — so the user can `git stash` / `git checkout -- <file>` selectively to recover).

## Idempotence

Every sub-skill must be idempotent: running it twice in a row should produce the same result. The second run's Plan Phase should report `Status: no-changes` (or near-zero changes if only cache metadata drifted). This property is what makes Stage 4 safe to re-run if the build or smoke fails partway through.
