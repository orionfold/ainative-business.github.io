---
name: frontier-scout
description: Scouts fresh AI research papers across HuggingFace, arxiv, and Papers-with-Code, classifies them against the ai-field-notes taxonomy, runs DGX Spark feasibility evaluations, and hands winners off to the tech-writer skill as article scaffolds. Trigger when the user mentions finding/scouting/refreshing papers, asks "what's new in AI research", asks whether a specific arxiv paper would run on the Spark, says "evaluate this for spark feasibility", "promote this to an article", or invokes /frontier-scout — even if they don't say "skill". Also trigger when the user shares a fresh paper URL and asks whether it's worth turning into the next deep-dive. Operates on /home/nvidia/ainative-business.github.io/, writes papers/ markdown reports + papers.json sidecar, and scaffolds articles/<slug>/ for the tech-writer handoff. Do NOT trigger for general code review, non-paper article work, or general research questions — those belong to tech-writer or general assistance.
---

# Frontier Scout

The upstream of the ai-field-notes publication pipeline. Every existing series in the blog (Foundations, Second Brain, LLM Wiki, Machine that Builds Machines, Looking Beyond Spark) is *downstream* — execute, measure, write. Frontier Scout is what *finds* the next thing worth writing about, by reading the global stream of new AI papers and asking "can this run on the Spark?"

The blog already publishes Frontier Scout as the sixth series. The user invokes this skill from inside Claude Code on the Spark; the skill uses Claude Code's native tools (Bash, WebFetch, Read, Write, Edit) — there is no separate Agent SDK or auth flow.

## Workflow shape

Frontier Scout is a **three-gate human-confirmed pipeline**, with markdown as the deliverable at every gate:

1. **Refresh gate** — `/frontier-scout` finds + classifies papers, writes `papers/README.md` calling out top picks. *User reads the markdown, picks dive-deep candidates.*
2. **Dive-deep gate** — `/frontier-scout eval <id>` writes `papers/<id>/eval.md`, a deep feasibility report. *User reads, picks one paper to promote.*
3. **Handoff gate** — `/frontier-scout promote <id>` scaffolds `articles/<slug>/seed.md` and explicitly hands off to `/tech-writer`.

Chat output stays brief — a pointer to the markdown. The markdown is the artifact; chat is the breadcrumb.

## Repo layout this skill writes into

- `/home/nvidia/ainative-business.github.io/` — the blog repo
- `papers/README.md` — derived human-readable index; leads with **Recommended dive-deep candidates**, then full listing, run history, stats. Regenerated each refresh.
- `papers/papers.json` — canonical machine-readable triage store (preserves carry-over `classify`, `deep_eval`, `promoted_to` fields across runs)
- `papers/<arxiv-id>/paper.md` — per-paper card; light YAML frontmatter + abstract + rationale + repos + links. Regenerated each refresh.
- `papers/<arxiv-id>/eval.md` — deep feasibility eval. Created by `eval` mode, **immutable** thereafter.
- `papers/<arxiv-id>/retrospective.md` — optional, created by `annotate` mode.
- `papers/runs/index.md` — append-only log; one line per refresh (timestamp, new/dropped counts, top picks).
- `papers/runs/<YYYY-MM-DD>/refresh-summary.md` — per-day refresh summary; overwritten on same-day re-runs.
- `articles/<slug>/` — the article scaffold this skill creates on promotion (`seed.md`, `transcript.md`, `evidence/`)
- `HANDOFF.md` — the session-transfer doc; this skill appends an "In-flight from Frontier Scout" stanza on promote
- `scripts/lib/spark-capabilities.json` — the **grounding floor**; the skill must consult it before forming any feasibility verdict. The same JSON is mirrored into the `fieldkit` package at `fieldkit/src/fieldkit/capabilities/data/spark-capabilities.json` and exposed as a typed Python API via `from fieldkit.capabilities import Capabilities, kv_cache_bytes, weight_bytes, practical_inference_envelope`. Use the API when doing memory math; read the JSON directly only for verbatim signal/hint lookup. The two copies are kept in sync by `fieldkit/scripts/sync_capabilities.py` (pre-commit-enforced).
- `scripts/lib/sources/{arxiv,huggingface,paperswithcode,github,semantic-scholar}.mjs` — pure I/O Node modules; the skill shells out to them via `node -e` one-liners (do NOT reimplement)

**Authority rules** (also in `references/data-schema.md`):
- `papers.json` is canonical for triage data. `paper.md` frontmatter is a human-readable mirror, not source of truth.
- `paper.md`, `README.md`, `runs/<date>/refresh-summary.md` regenerate on every refresh — do not hand-edit.
- `eval.md` and `retrospective.md` are immutable once written.

## Mode router

Detect the mode from the user's phrasing, then follow the corresponding playbook below.

| User intent | Mode |
|---|---|
| "find papers", "scout papers", "what's new", "refresh papers", "/frontier-scout refresh", or no specific paper named | **refresh** |
| "evaluate <id>", "is <paper-url> spark-feasible", "deep-eval", "/frontier-scout eval <id>" | **eval** |
| "promote <id> to article", "turn this into the next deep-dive", "/frontier-scout promote <id>" | **promote** |
| "the eval was wrong about X", "annotate <id>", "retrospective on <id>", "fieldkit fit for <id>" | **annotate** |

If ambiguous, ask which mode in one short sentence.

## Mode: refresh

Goal: pull fresh papers, score popularity, classify each against the ai-field-notes taxonomy, drop the off-topic ones, write the full markdown report set + `papers/papers.json`. Preserves prior classifications + deep-eval pointers + promotion pointers across re-runs.

0. **Auto-migrate from the legacy Astro path if needed** (one-shot, idempotent). At the very top of refresh, before any fetch:

   ```
   if exists src/data/papers.json AND not exists papers/papers.json:
     read src/data/papers.json
     for each paper p:
       mkdir -p papers/<p.arxiv_id>/
       write papers/<p.arxiv_id>/paper.md          (regenerated from p, see paper.md template in references/data-schema.md)
       if p.deep_eval and exists src/data/paper-evals/<p.arxiv_id>.md:
         mv src/data/paper-evals/<p.arxiv_id>.md → papers/<p.arxiv_id>/eval.md
         rewrite p.deep_eval.path → "papers/<p.arxiv_id>/eval.md"
     write papers/papers.json (with rewritten deep_eval paths)
     rmdir src/data/paper-evals/   (empty after the moves)
     rm    src/data/papers.json
   ```

   The existence check makes this a no-op on subsequent runs. Order is recoverable: new files written first, source-of-truth `src/data/papers.json` removed last.

1. **Read the existing `papers/papers.json`** if present so you can carry forward prior `classify`, `deep_eval`, and `promoted_to` fields. Re-classifying papers that haven't changed is wasted work.

2. **Load the Spark capability map** once, into context. This is the grounding floor for every classification — what the Spark can actually do today, the in/out-envelope signals, the stage and series routing hints. Two equivalent paths:
   - **Preferred (typed):** `python3 -c "from fieldkit.capabilities import Capabilities; import json; print(json.dumps(Capabilities.load().raw, indent=2))"` — also gives you `Capabilities.load().in_envelope_signals`, `.out_of_envelope_signals`, `.stack`, etc., as Python objects.
   - **Fallback (raw):** read `scripts/lib/spark-capabilities.json` directly when `fieldkit` isn't importable on the host.

3. **Fetch fresh candidates in parallel** by shelling to the Node sources:

   ```bash
   cd /home/nvidia/ainative-business.github.io
   node -e "import('./scripts/lib/sources/huggingface.mjs').then(m => m.fetchHuggingFaceDailyPapers({days: 30}).then(r => console.log(JSON.stringify(r))))" > /tmp/fs-hf.json
   node -e "import('./scripts/lib/sources/arxiv.mjs').then(m => m.fetchRecentArxiv({maxResults: 60}).then(r => console.log(JSON.stringify(r))))" > /tmp/fs-arxiv.json
   ```

   Read both JSON files. Dedupe by `arxiv_id`, preferring entries that have `hf_upvotes` (HF is the strongest leading signal of community interest).

4. **Cap the candidate set** at ~30 papers (sort by `hf_upvotes` desc, take top N). Classifying everything is expensive and most of HF's top is the relevant set anyway. Adjust the cap based on user intent ("just check today's top 5" vs "wide sweep this week").

5. **Enrich with code links + GitHub metadata + citations** for each candidate:

   ```bash
   node -e "import('./scripts/lib/sources/paperswithcode.mjs').then(m => m.fetchPapersWithCodeRepos('2604.26904').then(r => console.log(JSON.stringify(r))))"
   node -e "import('./scripts/lib/sources/github.mjs').then(m => m.fetchGitHubRepoMeta('https://github.com/owner/repo').then(r => console.log(JSON.stringify(r))))"
   node -e "import('./scripts/lib/sources/semantic-scholar.mjs').then(m => m.fetchSemanticScholarCitations('2604.26904').then(r => console.log(JSON.stringify(r))))"
   ```

   Sleep ~150 ms between PWC calls and ~200 ms between Semantic Scholar calls (their rate limits are tight). For each paper, take the top ≤3 repos to keep the JSON bounded.

6. **Compute popularity_score** per paper: composite of HF upvotes + max repo stars + citations, with a 90-day exponential decay on `published`. Formula in `references/data-schema.md`.

7. **Classify each candidate** that doesn't already have a `classify` block. Use `references/classifier-prompt.md` as the structured-output prompt; emit a JSON block per paper. Drop any paper with `relevance_score < 0.5` — keeping the listing focused on what could realistically become an ai-field-notes article matters more than total volume.

8. **Write `papers/papers.json`** with the new + carried-over papers, sorted by `popularity_score` desc. Schema in `references/data-schema.md`.

9. **Write per-paper `papers/<arxiv-id>/paper.md`** for every paper in the listing. Use the template in `references/data-schema.md`. Regenerate on every refresh — frontmatter/body track classification changes.

10. **Write `papers/runs/<YYYY-MM-DD>/refresh-summary.md`** for this run — what was new, what was dropped (with reasons), top picks, verdict + series distributions. Template in `references/data-schema.md`. Overwrites if re-run on the same day.

11. **Append one line to `papers/runs/index.md`** — `<iso-timestamp> · added=N dropped=K total=M · top: <id1>, <id2>, <id3>`. Append-only audit trail across all runs.

12. **Regenerate `papers/README.md`** with this structure:
    1. **Recommended dive-deep candidates** (top 3–5 by combined relevance × popularity × verdict-weight; each entry: title link → `<id>/paper.md`, one-line rationale, fast verdict pill).
    2. **What's new this run** (link to `runs/<date>/refresh-summary.md`).
    3. **Full listing** grouped by series → verdict → popularity. Each entry: title, id, popularity, fast verdict, link to `<id>/paper.md`, link to `eval.md` if present, link to `articles/<slug>/` if promoted.
    4. **Stats panel**: total count, classified-this-run, dropped-this-run, verdict + series + stage breakdowns.
    5. **Run history** — link to `runs/index.md`.

13. **Report briefly** to the user. One sentence pointing to `papers/README.md`, plus the top picks called out by id + verdict. Don't reproduce the markdown in chat.

14. **Don't auto-trigger a build or commit.** The user opens `papers/README.md` to review; that's their decision point.

## Mode: eval

Goal: produce a structured feasibility verdict for one paper, save it as `papers/<arxiv-id>/eval.md`, and patch `papers/papers.json` with a `deep_eval` pointer.

1. **Resolve the arxiv id** from whatever the user gave (URL, raw id, or "the ClawGym paper"). If they named a paper without an id, find it in `papers/papers.json` first; if it isn't there, run a refresh first or ask permission to fetch it ad-hoc.

2. **Read the paper entry from `papers/papers.json`** for context (title, abstract, repos, fast classify).

3. **Load the Spark capability map in full** — every claim in the eval must be defensible against this map. Prefer `from fieldkit.capabilities import Capabilities` for the typed view (and use `kv_cache_bytes` / `weight_bytes` / `practical_inference_envelope` for the memory math instead of redoing the arithmetic by hand); fall back to reading `scripts/lib/spark-capabilities.json` directly if `fieldkit` isn't installed in the active environment.

4. **Read the actual paper body**, not just the abstract. Try in order:
   - `WebFetch` `https://ar5iv.labs.arxiv.org/html/<id>` (clean HTML render)
   - `WebFetch` `https://arxiv.org/abs/<id>` (fallback)

5. **Survey the linked repos** if any. Use `gh api /repos/<owner>/<repo>/readme -q '.content' | base64 -d` for the README, `gh api /repos/<owner>/<repo>/contents/` for the file tree, and `gh api /repos/<owner>/<repo>/languages` for the language stats. Skim `requirements.txt` / `pyproject.toml` if present so you can name actual dependencies in the recipe.

6. **Run the memory budget arithmetic** if the paper involves a specific model size. Use the formulas from `references/feasibility-prompt.md` — params × bytes-per-param + KV cache (2 × hidden × bytes × n_layers × ctx × batch). Compare against the 128 GB envelope.

7. **Write the eval markdown** to `papers/<arxiv-id>/eval.md` following the template in `references/feasibility-prompt.md`. The template's section ordering is load-bearing — `papers-promote` extracts sections by name. **Refuse to overwrite an existing `eval.md`** — evals are immutable once written; if the user wants to revise the verdict use `annotate` mode.

8. **Patch `papers/papers.json`**: add a `deep_eval` block to the paper entry:
   ```json
   "deep_eval": { "path": "papers/<id>/eval.md", "evaluated_at": "<iso-now>", "verdict": "<spark-feasible|borderline|out-of-envelope>" }
   ```

9. **Regenerate `papers/<arxiv-id>/paper.md`** so the frontmatter `has_deep_eval: true` and the body links to `eval.md`.

10. **Report the verdict + recipe summary** in chat (1–3 sentences) and offer the next move ("want me to promote this to an article scaffold? — `/frontier-scout promote <id>`").

## Mode: promote

Goal: turn an evaluated paper into an article scaffold ready for `/tech-writer`. Bridges Frontier Scout output into the existing per-article authoring layout (`article.md`, `transcript.md`, `evidence/`) used by all 25 published articles.

Full playbook in `references/handoff-protocol.md`. Summary:

1. Require an existing eval at `papers/<id>/eval.md`. If missing, do `eval` first.
2. Choose a slug — prefer the eval's "Suggested slug" line; fallback is a kebab-case from the title.
3. Create `articles/<slug>/` with `seed.md` (frontmatter + sectioned outline), `transcript.md` (provenance), and `evidence/{paper.pdf, paper-meta.json, repo-snapshot/, feasibility-eval.md, spark-recipe.md}`.
4. Download the paper PDF (`curl -L <pdf_url>`); shallow-clone the top-starred repo (`git clone --depth 1`); fail soft if either is unavailable.
5. Patch `papers/papers.json` with `promoted_to: { article_slug, status: "upcoming" }` and regenerate `papers/<id>/paper.md` so the frontmatter reflects it.
6. Append an "In-flight from Frontier Scout" stanza to `HANDOFF.md` (per the existing single-source-of-truth protocol; don't create a new handoff file).
7. Report and hand off explicitly: *"Promoted → `articles/<slug>/`. Open `seed.md` and run `/tech-writer` to continue."*

## Mode: annotate

Reverse-handoff. Two flavors, both inline-prepend on `papers/<arxiv-id>/eval.md` (convention preserved for continuity — eval bodies stay immutable; annotations are appended-style notes that ride above the original):

**Verdict revision** — when an experiment proves the original eval was wrong (too optimistic or too pessimistic):

1. Prepend `> **RETROSPECTIVE (<date>):** Verdict revised to **<new-verdict>**. <one-paragraph why>` to the existing eval.
2. Update `papers/papers.json`'s `deep_eval.verdict` to the new value and add `deep_eval.retrospective_at: <iso-now>`.
3. Regenerate `papers/<arxiv-id>/paper.md` so the frontmatter verdict reflects the revision. The next refresh rewrites `papers/README.md`; run `/frontier-scout refresh` if the user wants it updated immediately.

**Fieldkit-fit annotation** — when an eval predates the `## Fieldkit fit` template (added with `fieldkit v0.1.0`) or the package surface has changed since the eval was written. Forward-looking, doesn't revise the verdict:

1. Prepend `> **FIELDKIT FIT (<date>):** ` followed by the same sub-bullets the template's "Fieldkit fit" section would have used (Would import / Would extend / Would propose for v0.x). Keep it ≤6 lines.
2. Patch `papers/papers.json`'s `deep_eval` block: add `fieldkit_fit_annotated_at: <iso-now>` and `fieldkit_modules: [<modules>]` (mirror the v0.1 module enum: `capabilities | nim | rag | eval | cli`; leave empty for evals whose fit is only deferred-version modules).
3. Regenerate `papers/<arxiv-id>/paper.md` so its frontmatter mirrors the new modules. (The `paper.md` template doesn't currently render the modules field — that's fine; the JSON is the source of truth and the eval body carries the human-readable annotation.)
4. **Don't touch `Verdict`, `deep_eval.verdict`, or any other section of the eval body.** Fieldkit-fit annotation is purely additive metadata; verdict revision is a separate flavor of `annotate` (above) and shouldn't be conflated.

## Conventions and gotchas

- **Always run from the repo root** `/home/nvidia/ainative-business.github.io/`. The Node fetchers use relative imports.
- **Never re-implement the fetchers** in chat — shell to the existing modules. They handle pagination, retries (arxiv 429), and the entity-decoding quirks.
- **Preserve existing `classify`, `deep_eval`, `promoted_to` fields** on every refresh. Losing the deep-eval pointer means losing minutes-to-hours of agent work.
- **Markdown is the deliverable.** Keep it clean — readable on GitHub directly, no raw HTML, no MDX, no Astro components.
- **Don't auto-commit.** The user reviews diffs, then commits + pushes per the project's solo-blog-direct-to-main workflow (memory note `project_nvidia_learn_git_workflow`).
- **Refresh `nvidia-learn-stats`** *only* when an article is published, not when the paper triage changes. Triage doesn't affect `project-stats.json`.
- **Memory + OOM landmine:** running this skill while NIM 8B is up is fine (the skill is light), but per memory `project_spark_unified_memory_oom`, don't ALSO start a parallel Ollama or NeMo training run — keep the Spark for one heavy thing at a time.

## Suggested follow-ups by mode

| Just finished | Likely next | Skill to use |
|---|---|---|
| `refresh` | open `papers/README.md`, pick a candidate from "Recommended dive-deep candidates" | (none — manual) |
| `eval` returning `spark-feasible` | promote to article | `/frontier-scout promote <id>` |
| `promote` | start the experiment + write | `/tech-writer` |
| `tech-writer` ships an article | refresh project stats | `/nvidia-learn-stats` |

## References

- `references/data-schema.md` — exact shapes for papers.json, paper.md, eval.md, refresh-summary.md, runs/index.md, README.md
- `references/classifier-prompt.md` — the structured-output prompt used in `refresh`
- `references/feasibility-prompt.md` — the deep eval markdown template + memory math
- `references/handoff-protocol.md` — the `promote` playbook in detail
