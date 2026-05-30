# Handoff protocol — Frontier Scout → tech-writer

The bridge that turns a deep-evaluated paper into an article scaffold. After this runs, the user opens `articles/<slug>/seed.md`, runs `/tech-writer`, and the flow is identical to every other ai-field-notes article.

## promote — full playbook

Inputs: `<arxiv-id>` (required), optional explicit `<slug>`.

### 1. Pre-conditions

- `papers/papers.json` exists and contains the paper.
- `papers/<arxiv-id>/eval.md` exists. If not, refuse to proceed and tell the user to run `/frontier-scout eval <id>` first.
- The paper has at least a fast `classify` (else how was it triaged into the listing?).

### 2. Choose the slug

Priority order:

1. The CLI argument if the user supplied one (`/frontier-scout promote 2604.26904 my-clawgym-rematch`).
2. The eval's "Suggested slug" line, found by regex `Suggested slug:\*\*\s*([a-z0-9-]+)`.
3. Fallback: kebab-case of the title's first 6 words.

Confirm the slug doesn't already exist as a directory under `articles/`. If it does, ask the user whether to overwrite, choose a new slug, or abort.

### 3. Create the article scaffold

```
articles/<slug>/
├── seed.md
├── transcript.md
└── evidence/
    ├── paper.pdf                ← downloaded from paper.pdf_url
    ├── paper-meta.json          ← copy of the papers.json entry for this paper
    ├── repo-snapshot/           ← shallow clone of the top-starred repo
    ├── feasibility-eval.md      ← copy of papers/<id>/eval.md
    └── spark-recipe.md          ← extracted "## Proposed Spark recipe" section as standalone runbook
```

### 4. Write `seed.md`

The frontmatter must match the schema in `src/content.config.ts` (validated by Astro at build time):

```yaml
---
title: '{Paper title} — Spark reproduction notes'
date: <today YYYY-MM-DD>
author: 'Manav Sehgal'
product: '<first nvidia_stack item from classify>'
stage: <classify.suggested_stage or eval suggestion>
difficulty: 'intermediate'
time_required: '~30 min read'
hardware: 'NVIDIA DGX Spark'
tags: [<from classify.topic_tags>]
summary: '<eval Suggested summary, ≤300 chars>'
status: upcoming
series: '<eval Suggested series>'
# Optional, MTBM only — the /book/ chapter(s) this article grounds.
# Inherit from classify.chapter_alignment when present, else default to [10]
# when series is "Machine that Builds Machines"; omit otherwise.
book_chapters: [<integers 1–14, e.g. 10>]
---
```

Body sections (these are the starting outline `/tech-writer` will polish). **The first section, `## The paper, in one breath`, is load-bearing**: it is the article-opening hook the published deep-dive must include — thesis, why-the-technique-matters, and promise-vs-achieved. Articles that omit it bury the paper's claim under the Spark-substrate framing (this template was added 2026-05-03 after a review of the first three Frontier Scout articles surfaced exactly that gap).

```markdown
## The paper, in one breath (ARTICLE OPENING — required at publish)

> tech-writer: this becomes a `## The paper, in one breath` section in
> the published article, placed immediately after the lede and before
> any "Why this matters for a personal AI builder" substrate framing.
> Pull thesis material from the eval's `## Hypothesis`; fill in the
> achieved beat after the experiment runs.

**Thesis.** <paraphrase the eval's "## Hypothesis" in 2–3 sentences,
plain language, one concrete mechanism — distinguish from the obvious
baseline the technique replaces>

**Why this technique matters for a personal AI builder.** <2 sentences
on what the technique unlocks for the reader — Pass@k efficiency,
literature-retrieval evaluation, runtime-as-frontier patching, etc. —
distinct from the Spark-substrate framing in the "Why this matters for
a personal AI builder" section that follows>

**Promise vs achieved.** Paper: <headline number on reference
hardware, e.g. "0.9878× tok/s on RTX 4090 with CUDA graphs">. Spark:
<measured number, e.g. "0.974× on patched Qwen 2.5 7B"; fill in after
the experiment>. Delta: <e.g. "1.4 percentage points"; one sentence on
why the gap is what it is>.

## Source paper
- arXiv: [<id>](<abs_url>) — {title}
- Repo: [<url>](<url>) (<stars>★, last commit <date>)
- Popularity: <popularity_score> · <hf_upvotes> HF upvotes · <citations> citations

## Frontier Scout verdict
<copy the eval's "## Verdict" section>

## Proposed Spark recipe
<copy the eval's "## Proposed Spark recipe" section>

## Open questions for the experiment
<copy the eval's "## Blockers" section — these are the things the experiment needs to resolve>

## Suggested article shape
<copy the eval's "## Article suggestion" section>
```

### 5. Write `transcript.md`

Provenance, not the article. Future tech-writer sessions read this to understand where the article came from.

```markdown
# Provenance: <slug>

Promoted from Frontier Scout on <today>.

- arXiv: <id>
- Repo: <url or "(none)">
- Fast verdict: <classify.fast_verdict>
- Deep verdict: <deep_eval.verdict>

The full agent eval is at `evidence/feasibility-eval.md`. The proposed Spark recipe is at `evidence/spark-recipe.md`. Use these as the starting outline; replace with measured numbers as the experiment progresses.
```

### 6. Populate `evidence/`

- `cp papers/<id>/eval.md evidence/feasibility-eval.md`
- Extract the "## Proposed Spark recipe" section into `evidence/spark-recipe.md` (with a `# Proposed Spark recipe` H1 prepended)
- Write `evidence/paper-meta.json` as the JSON entry from `papers/papers.json` (pretty-printed)
- Download the PDF: `curl -sL <pdf_url> -o evidence/paper.pdf`. If the curl fails (404, redirect issues), don't block — note it in the transcript and move on
- Snapshot the top-starred repo: `git clone --depth 1 <repo_url> evidence/repo-snapshot`. If clone fails, write `evidence/repo-snapshot/README.txt` with `(clone failed: <reason>)` and move on

### 7. Patch papers.json + per-paper card

Add to the paper entry in `papers/papers.json`:

```json
"promoted_to": {
  "article_slug": "<slug>",
  "status": "upcoming"
}
```

Then regenerate `papers/<arxiv-id>/paper.md` so the frontmatter `promoted_to: <slug>` is set and the body renders the "Promoted" section pointing at `articles/<slug>/`. (Template in `references/data-schema.md`.)

### 8. Append to HANDOFF.md

Per the existing protocol (the single root-level HANDOFF.md is the session-transfer truth — don't create a new file). Append at the end:

```markdown

## In-flight from Frontier Scout
- **Slug:** `<slug>` · **Series:** <series> · **Stage:** <stage>
- **Source:** arXiv <id>{ + <repo_url> if present}
- **Status:** promoted <today>; experiment not started
- **Next:** read `articles/<slug>/seed.md`, decide on minimum viable repro, then run via `/tech-writer`
```

If a stanza for this exact slug already exists, don't duplicate — update in place instead.

### 9. Hand off explicitly

End with one line in chat: `Promoted → articles/<slug>/. Open seed.md and run /tech-writer to continue.`

## annotate — reverse handoff

Inputs: `<arxiv-id>`, `<new-verdict>`, `"<note>"`.

1. Validate `new-verdict` ∈ `spark-feasible | borderline | out-of-envelope`.
2. Read `papers/<arxiv-id>/eval.md`. If it already starts with `> **RETROSPECTIVE`, replace that block instead of stacking — keep one retrospective at the top.
3. Prepend:

   ```markdown
   > **RETROSPECTIVE (<today>):** Verdict revised to **<new-verdict>**.
   >
   > <note (line breaks become "> " continuations)>

   ```

   (Note: `eval.md` is otherwise immutable; this prepend is the one sanctioned exception, applied only by `annotate` mode. As an alternative, `papers/<arxiv-id>/retrospective.md` can be written as a sibling — pick one convention and stick to it; current convention is the inline prepend.)
4. Patch `papers/papers.json`: set `deep_eval.verdict = <new-verdict>` and `deep_eval.retrospective_at = <iso-now>`.
5. Regenerate `papers/<arxiv-id>/paper.md` so its frontmatter `deep_verdict` reflects the revised value.
6. Report the change in chat. The next refresh will rewrite `papers/README.md` to surface the new verdict; if the user wants the README updated immediately, run `/frontier-scout refresh`.

## Why a single HANDOFF.md, not per-session files

The user's existing protocol (memory `feedback_handoff_md_update_protocol`): one root-level `HANDOFF.md` rewritten/amended on every significant task. The previous "handoff/<date>.md per-session folder" pattern was removed 2026-04-30. Frontier Scout follows the same protocol — append a stanza to the same file, replace stale stanzas, don't fork the convention.
