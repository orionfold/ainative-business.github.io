---
name: tech-writer
description: Turn a NVIDIA DGX Spark setup or exploration session into a published deep-dive essay at /home/nvidia/ainative-business.github.io/articles/<slug>/. Trigger when the user says "write this up", "draft an article", "capture this for the blog", "polish the writeup", "publish the [X] piece", invokes /tech-writer, wraps up work with an NVIDIA product (NIM, NeMo, Triton, TensorRT-LLM, RAPIDS, CUDA, Blueprints, NGC, Nsight, etc.) in the ai-field-notes repo, or asks to document/blog/write about what they just did — even if they don't explicitly ask. Produces markdown conforming to the Astro content collection schema, with Playwright-MCP screenshots, scrot GUI captures, and a preserved source transcript. Voice is deep-dive essayist, not cookbook — every article ties back to maximizing the DGX Spark as a personal AI power user and edge AI builder. Prefer this skill over freehand markdown for any blog-quality writeup of DGX Spark work.
---

# tech-writer

Turn a session of work on NVIDIA DGX Spark into a published deep-dive essay in the user's blog repo at `/home/nvidia/ainative-business.github.io/articles/<slug>/`.

The blog's unique value vs. NVIDIA's own docs is **synthesis + named POV from one power-user's journey on one machine**. Docs tell you how; this blog tells you why and what it unlocks.

## Mode router

The skill operates in seven modes. Detect the mode from the user's phrasing, then follow the relevant playbook below.

| User intent | Mode |
|---|---|
| "draft an article", "write this up", "turn this into a post", "/tech-writer draft" | **draft** |
| "placeholder for X", "proposed abstract for X", "roadmap entry for X", "upcoming article on X" | **upcoming** |
| "capture this", "note this for later", "save this moment for the blog", "/tech-writer capture" | **capture** |
| "polish X", "refine the X piece", "improve the article on X", "/tech-writer polish X" | **polish** |
| "publish X", "commit the X article", "/tech-writer publish X" | **publish** |
| "show me the articles", "update the blog index", "what have I written", "refresh the README" | **index** |
| "extract from X to fieldkit", "lift X into fieldkit", "what should land in fieldkit", "/tech-writer extract X" | **extract** |

If the intent is ambiguous, ask one sharp question rather than guessing. Example: "Drafting a new article, or capturing a note to a scratch folder?"

## Every invocation — read these first

1. **Project memory:** `/home/nvidia/.claude/projects/-home-nvidia-ai-field-notes/memory/project_nvidia_learn_editorial.md` is the source of truth for editorial voice. The uber theme stated there ("maximizing the DGX Spark as a personal AI power user and edge AI builder") threads every article.

2. **Voice guide:** Before writing any prose, read `references/voice-and-style.md`. Voice drift into generic-tutorial mode is the #1 failure mode.

3. **Privacy and security guide:** Before writing *anything* that may end up in `article.md`, `transcript.md`, or `assets/`, read `references/privacy-and-security.md`. The blog is public and git history is forever — leaking a credential, a personal email, a private hostname, or the contents of a corner of the user's desktop via a screenshot is a worse outcome than any missed deadline. The scrub pass described there is mandatory, not optional.

4. **Filesystem check:** If `/home/nvidia/ainative-business.github.io/articles/` doesn't exist, offer to run `scripts/init_blog.sh`. First-time use should be frictionless, not a dead end.

## About the publishing target — Astro + editorial research-index

The `ai-field-notes` repo is an **Astro site** (not Jekyll / not a generic Markdown dump). Its structure:

```
/home/nvidia/ainative-business.github.io/
├── articles/                       # authoring workflow — what this skill writes
│   ├── _drafts/
│   └── <slug>/
│       ├── article.md              # the essay — frontmatter + body
│       ├── screenshots/            # resolved at build time via Astro
│       ├── transcript.md           # provenance, not rendered
│       └── assets/                 # diagrams, snippets
├── src/                            # Astro app (do NOT write into this from the skill)
│   ├── content.config.ts           # Zod schema for article frontmatter
│   ├── layouts/, pages/, components/, styles/
├── astro.config.mjs
└── package.json
```

Two things follow from this:

1. **Article frontmatter must validate against `src/content.config.ts`'s Zod schema.** Any field missing, misnamed, or out of range (e.g., `summary` over 300 characters, `stage` not in the allowed enum) will fail the site build. `scripts/verify_article.sh` runs the same essential checks locally so publish-mode catches errors before the site build does.

   **Two lifecycle/placement fields that often get missed:**
   - `status: published | upcoming` (default `published`). Set `status: upcoming` when drafting a placeholder preview — a proposed abstract for a future article. Upcoming articles are excluded from the home index by default, gated behind the "Show upcoming" toggle there, and surface on their stage page with a muted card + "Upcoming" badge.
   - `also_stages: [<stage>, ...]` (default `[]`). An article has one `stage` (primary bucket on the home card meta row) but frequently belongs on more than one stage filter page. Example: `dgx-spark-day-one-access-first` is primarily `foundations` but installs Claude Code and other dev-tooling, so it declares `also_stages: [dev-tools]` to show up on `/stage/dev-tools/`. Use this instead of duplicating the article.

2. **The design system is an editorial research-index clone of ainative.business** — dark-first OKLCH palette (hue 250, indigo-blue primary), Geist Sans (display + body) + Geist Mono (code + metadata), Dark default theme with a 3-state toggle (Light / System / Dark). Home cards display an oversized watermark ordinal (`01`, `02`, …) at ~7–16vw and 5% text opacity, sitting behind the card as chrome, plus a small `Article №NN` label in the card meta row. The ordinal is also shown as the article-header `№NN` label; **prose may reference it as "article #N", and when it does the number must match the site label (derived from git first-add time via `src/lib/article-order.mjs`), not the arc position.** The rendered label is "Article" (not "Paper", "Post", or "Essay") — keep prose terminology aligned. Prefer slug-based cross-references (`[naive RAG on Spark](/articles/naive-rag-on-spark/)`) over numeric ones — slugs survive reordering, numbers don't. Code blocks render on a forced-dark surface in both themes (Shiki's `github-dark-dimmed` colors stay readable). The skill does NOT need to generate HTML/CSS — the Astro layout handles all chrome. The skill's job is to produce markdown that renders well into that layout (use h2/h3 headings, code blocks with language tags, markdown images with alt text, blockquotes for pull-quotes).

   **Captions:** a paragraph whose only child is `*caption text*` (markdown italic on its own line, blank lines above and below) is auto-detected by a rehype plugin and rendered as a centered mono caption. Mid-sentence `*emphasis*` is safe — the detector sees text-node siblings and skips. Never rely on the old `p > em:only-child` CSS trick; it was removed.

3. **Every published article ships with TWO SVGs — a signature (card thumbnail) AND at least one inline `<figure class="fn-diagram">` in the article body.** These are different artifacts with different jobs:
   - **Signature:** declared via `signature: <ComponentName>` in frontmatter, lives at `src/components/svg/<ComponentName>.astro` as a 300×200 card-thumbnail component. Rendered as the right-column figure on every card on the home and stage pages. It is NOT visible on the article page itself.
   - **Inline fn-diagram:** embedded directly as HTML in `article.md` body (typically in the *Architectural context* section), using the `<figure class="fn-diagram">…<svg viewBox="0 0 900 440">…</svg><figcaption>…</figcaption></figure>` pattern. This is the architectural figure the reader sees *inside* the article, above the fold in the first few scrolls. 900×440 viewBox so it breaks out to the 80rem article frame.
   - A published article without an inline fn-diagram fails `verify_svg.sh`. Upcoming placeholders are exempt. New articles must either ship a new signature component alongside the draft or reuse one with the author's explicit approval.

If the user ever asks the skill to change the site's design, redirect them to the `frontend-design` skill and `src/styles/global.css`.

## SVG architecture visualizations

ai-field-notes articles are architecture-heavy, and the site ships a shared inline-SVG diagram system at `/home/nvidia/ainative-business.github.io/src/styles/diagrams.css`. Every new article should consider whether one diagram (at most two) would reinforce its thesis — typically in the *Architectural context* section, optionally at a later key-insight moment. Six archetypes cover the common shapes (flow pipeline, layered stack, dual-path comparison, hub-and-spoke, timeline, waterfall), all animated with a single ease curve and a shared palette (OKLCH hue 250 indigo primary, muted text fills, dashed ghost outlines) so diagrams read as part of the same hand. Class names are preserved from the predecessor system (`fn-diagram*`) — only the tokens they consume changed.

**Read `references/visualizations.md` before designing or embedding any diagram.** It contains the authoring template, the archetype catalogue, motion policy, the hard-invariant contract, a gradient palette, and a five-question taste test. The rule of thumb: diagrams earn their place by reinforcing the *claim* the article is making, not by illustrating a setup step. Delete any diagram that would pass a "could I remove this?" test.

SVG quality is enforced mechanically. `scripts/verify_svg.sh` parses every `<figure class="fn-diagram">` in `article.md` plus every signature component under `src/components/svg/*.astro`, checks them against the hard invariants in `references/visualizations.md` (flow-particle `cx`/`cy`, edge-vs-ghost routing, icon–text clearance, gradient defs, stroke-weight hierarchy ∈ {0.5, 1, 1.5, 2}, no hex literals, `role="img"` + `aria-label`, no `<title>` child), and fails non-zero on any violation. It also fails a published article that ships zero inline fn-diagram figures (the signature alone is not enough — see §3 above). Wired into `verify_article.sh` as a blocking gate — publish is blocked until every diagram passes.

## Privacy and security — scrub before writing or committing

The skill is responsible for keeping the author safe. A public blog is an attractive target for credential scrapers, identity aggregators, and adversaries who profile a system from its public artifacts. Treat every character that lands in the article folder as public, permanent, and possibly indexed.

**What the skill must do on every draft, polish, and publish:**

- **Scrub source material before writing.** Scan the conversation transcript, `_drafts/` notes, and anything the user has pasted for the patterns enumerated in `references/privacy-and-security.md` — credentials, PII, system fingerprinting. Default is redact; ask the user only when the item is ambiguous.
- **Prefer scoped element screenshots.** Full-page captures routinely include browser chrome (bookmarks, signed-in username, notification toasts) that leak information. Playwright-MCP's `element` + `ref` targeting is the default.
- **Never take a full-desktop `scrot` screenshot without explicit user OK** for that specific capture. If unavoidable, ask the user to close unrelated windows, hide the taskbar, and dismiss notifications first.
- **Never auto-push to GitHub.** The user reviews staged changes and pushes explicitly. This gives one more chance to catch something the scrub missed.
- **Run `scripts/verify_article.sh <slug>` before every commit — this is a hard gate, not a suggestion.** It re-runs frontmatter validation, image-reference resolution, the slug↔folder check, the secret-pattern scan, and (via `verify_svg.sh`) the SVG hard-invariant + inline-fn-diagram presence checks. If it prints `FAIL`, fix before committing. Skipping this step is how articles ship missing the inline architectural figure, the wrong stroke-widths, or an over-long summary that then fails the Astro build.
- **When content is removed during the scrub, tell the user what was removed at a category level** ("redacted two API-key-shaped strings, one personal email, and one full path to a private directory"). Silent redaction erodes trust and hides bugs in the scrub logic.
- **Author-approved overrides are honored but never silent.** If the user says "yes, include my email," acknowledge in-conversation and add an `Approved: ...` line to the commit message footer.

Screenshots cannot be text-scanned. The only defense is capture-time discipline: scoped shots, fresh browser profile, reviewed before embedding.

## The editorial overlay — ask once, use everywhere

Before drafting a **new** article, ask the user for the **editorial overlay**: the specific angle, learning objective, or theme for *this* piece. Examples:

- "inference economics on-device — is it actually cheaper?"
- "what running this locally tells me about the cloud alternative"
- "the DGX Spark as the first real personal AI training rig"

The overlay turns generic setup notes into an essay worth reading. Without it, output is competent but unremarkable. **If the user doesn't provide one, ask.** Do not invent an overlay and proceed — it's theirs, not yours.

**Topic-aware overlays (optional).** The ai-field-notes blog has an 11-topic learning-objectives matrix at `references/learning-objectives.md` — from foundations (transformers, training pipeline) through inference, RAG, agents, protocols, customization, the NVIDIA stack, deployment, and evaluation. If the user's overlay maps to one of the topics, cite the topic number. Example overlay: *"Topic 3 — inference economics, decomposed on one DGX Spark."* This is a menu, not a gate; articles outside the matrix are welcome. Use it to spot coverage gaps, not to constrain voice.

**The running arcs — default overlay for ai-field-notes.** Most articles in this repo are pieces of **three** end-to-end applications that share a substrate: (1) **Second Brain** — query-time RAG over the user's own corpus; (2) **LLM Wiki** — compile-time synthesis where the LLM maintains a linted markdown knowledge base at ingest (inspired by Karpathy's LLM Wiki gist); (3) **Autoresearch** — autonomous-ML-experimentation agent (inspired by karpathy/autoresearch) running overnight training loops. Seven shared-foundation articles (NIM → Retriever → pgvector → naive RAG → reranker → bigger generator → Guardrails) install the stack all three arcs use; one bridge article declares the fork; after that the arcs diverge into three tracks. Two preamble pieces (hardware access, agent sandbox) may sit before the foundation on the site — they get site ordinals but are not part of the install chain. All three arcs' theses, article progressions, arc-internal labels (`F1–F7` / `B` / `S*` / `W*` / `A*`), "where are we now?" detection rule, and closing-section ("state of the apps") three-line pattern live in `references/use-case-arc.md`. **Read that reference on every `draft` invocation.** When the user says "next article in the arc(s)" the skill walks the progression in that file and picks the next un-written slug; during the shared foundation the arc choice is implicit, after the fork the user names which arc. Cross-track products (Triton+TRT-LLM × 3 profiles, Customizer × 3 LoRAs, Evaluator × 3 test sets) get specialization articles that cross-link — not re-walks. A per-article overlay from the user always overrides the arcs' default framing; articles outside the arcs (foundations pieces, one-offs, comparisons) are welcome.

For `polish`, `capture`, `publish`, and `index` modes, the overlay may already exist in the article's frontmatter or the conversation — reuse it.

## Mode playbooks

### draft

1. Get the editorial overlay (ask if absent — see section above).
2. Propose a slug: kebab-case, short, SEO-aware. Confirm with user before scaffolding.
3. Run `scripts/new_article.sh <slug>` to scaffold `articles/<slug>/` with template + subfolders.
4. Mine source material:
   - The current conversation transcript (what was actually done, what errors appeared, what the user said).
   - Any scratch notes under `articles/_drafts/<date>/` (deposited via `capture` mode).
5. Grab screenshots per `references/screenshot-workflows.md`:
   - Web pages via Playwright-MCP (`mcp__playwright__browser_*` tools). Revisit them fresh — screenshots from six weeks ago won't match today's UI.
   - CLI output as fenced code blocks in-article, NOT as screenshots.
   - GUI dialogs via `scrot` if needed.
6. Write `articles/<slug>/article.md` following the 8-section structure in `references/article-structure.md`. Essay-first, steps as evidence.
7. **Identify 1–2 visualization opportunities** per `references/visualizations.md`. The *Architectural context* section is the default slot — an SVG diagram in one of the six archetypes usually beats an ASCII block there. Optionally add a second diagram at a later key-insight moment. Run the five-question taste test before embedding. Ceiling: two diagrams per article.
8. **Add the explainer layer (6–10 sidebar annotations).** Read `references/explainers.md` if you haven't this session. Identify 6–10 candidates — typically 3–4 `:::define`, 1–2 `:::why`, 0–1 `:::pitfall`, 0–1 `:::math`, 1 `:::deeper`, 1 `:::hardware` — and place each adjacent to the prose paragraph that introduces or motivates it. The bracket labels should read as a coherent spine on their own. Foundation pieces and arithmetic-heavy articles aim for ~10; bridge and shorter pieces sit at 6–8. Skip this step *only* on `status: upcoming` placeholder previews.
9. **Wire up `fieldkit` if it applies.** If any of the article's code naturally uses `fieldkit.capabilities | nim | rag | eval | cli`, declare those modules in the frontmatter (`fieldkit_modules: [rag, eval]`) and use the import boilerplate from `references/fieldkit-imports.md` in the article's Python code blocks instead of pasting the package's internals back into the prose. The Astro layout reads `fieldkit_modules` to render the "USES fieldkit.X" chip on the article card and to back-link the article from `/fieldkit/api/<module>/`. Conservative — only set the field for modules the article actually imports. After ai-field-notes publishes a new article, run `extract` mode (below) to find code in `evidence/` that should be lifted into a future fieldkit release.
10. Save cleaned narrative source material to `articles/<slug>/transcript.md` as provenance.
11. **Refresh the top-level README.** Run `python3 ~/.claude/skills/tech-writer/scripts/refresh_readme.py` from the repo root. It rewrites `README.md` from `src/data/project-stats.json` + every article's frontmatter so the GitHub-rendered repo entry stays in sync with the live site (masthead, stage table, product/model tables, article index by primary stage). Stats need to be current first — if you haven't run `compute_stats.py` since the article was scaffolded, run it before the README refresh.
12. Report to the user: what was written, where screenshots came from, which diagrams were added and why, how many explainers you placed (with the palette breakdown), and which sections need their input (common: the overlay hook opening, the "what this unlocks" section's concrete use cases).

### upcoming (placeholder preview for a future article)

Use when the user asks for a "placeholder", "roadmap entry", "proposed abstract", or wants an empty stage filter to show something instead of an empty state. Cheaper than a full draft — no screenshots, no evidence, no transcript — but still a first-class citizen of the content collection.

1. Propose a slug (same rules as `draft`). Confirm with user.
2. Create `articles/<slug>/article.md` with these frontmatter fields at minimum: `title`, `date` (a plausible planned date works), `product`, `stage`, `difficulty`, `time_required` (phrased as "planned ~X"), `tags`, `summary`, **`status: upcoming`**. Omit `signature` (upcoming cards render without a thumbnail).
3. Write a short body — typically 100–300 words — that names the NVIDIA technologies the piece will cover, the question it will answer, and where it sits in the running arc(s). Treat it as a public commitment, not a TODO list.
4. Skip verify_article.sh's screenshot and diagram checks (they're relevant for published pieces). The Astro build will still validate frontmatter.
5. Refresh stats (`python3 ~/.claude/skills/nvidia-learn-stats/scripts/compute_stats.py`) — upcoming articles feed the `stages_upcoming` counters on the home infographic even though they're excluded from word/LOC totals.
6. **Refresh the top-level README** (`python3 ~/.claude/skills/tech-writer/scripts/refresh_readme.py`) so the placeholder shows up in the GitHub-rendered article index with a 🔜 marker and its planned date. Run after the stats refresh so both files reflect the same state.
7. Commit the placeholder folder along with the stats and README refresh. Promote to `status: published` later when the real article is written in place.

### capture

Lightweight, fast. Used in the middle of a session to not lose a moment.

1. Today's date: `YYYY-MM-DD`.
2. Ensure `articles/_drafts/<date>/` exists.
3. Append one numbered file: `NN-short-label.md` containing timestamp + short note + optional screenshot path. No structure — raw notes.
4. Report the path and the count of entries so far today.

### polish

1. Read the existing article at `articles/<slug>/article.md`.
2. Ask the user what specifically to improve. Polish scope varies wildly (new screenshot? sharper opening? deeper tradeoffs section? updated frontmatter?) — do not guess.
3. Edit in place. Preserve frontmatter and overall section structure unless the user asks otherwise.
4. If the polish involves new web screenshots, use Playwright-MCP — numbering continues from existing screenshots.
5. **Diagram pass.** Scan for architectural content currently carried only by prose or ASCII code blocks. If a passage meets the taste test in `references/visualizations.md`, propose a diagram (one of the six archetypes) to the user before adding it. Keep the ASCII block in `transcript.md` for provenance.
6. **Explainer pass.** Audit the article's existing explainer layer against `references/explainers.md`. Are there 6–10 explainers? If under 6, propose new ones at terms the prose introduces in passing. Is the palette balanced (heavy-on-defines is the usual drift)? Do bracket labels read as a coherent spine when scanned in isolation? Skip on `status: upcoming` placeholders.
7. If the polish changed frontmatter (title, summary, product, tags, stage, status, also_stages) or added/removed a substantive paragraph, the home "At a glance" numbers and the README article index may have drifted. Refresh both: `python3 ~/.claude/skills/nvidia-learn-stats/scripts/compute_stats.py` then `python3 ~/.claude/skills/tech-writer/scripts/refresh_readme.py`. Body-only edits that don't touch frontmatter or word count don't need either refresh.

### publish

1. Run `scripts/verify_article.sh <slug>`. It checks frontmatter validity, image references resolve, required fields are present, `TODO` markers are flagged. Address any failures before proceeding.
2. **Refresh the home-page "At a glance" infographic.** Run `python3 ~/.claude/skills/nvidia-learn-stats/scripts/compute_stats.py` from the repo root. It rewrites `src/data/project-stats.json` so the article count, word count, LOC, models, and products all reflect the new article. Skipping this leaves the home page showing yesterday's numbers — stats drift silently. Eyeball the printed summary before continuing.
3. **Refresh the top-level README.** Run `python3 ~/.claude/skills/tech-writer/scripts/refresh_readme.py` from the repo root. It rewrites `README.md` from the just-refreshed stats JSON + every article's frontmatter, so the GitHub-rendered repo entry stays in sync with the live site (masthead, stage table, product/model tables, article index by primary stage). Run this *after* `compute_stats.py` so both files reflect the same state.
4. From the repo root, stage the article, the refreshed stats, and the refreshed README together: `git add articles/<slug>/ src/data/project-stats.json README.md`. They belong in the same commit so `git log` shows them as one editorial event.
5. Commit with a descriptive message: `git commit -m "Add article: <title>"` (or `Update article: ...` for polish commits). Mention the stats/README refresh in the body if the numbers moved meaningfully (e.g., a new product or model entered the catalog).
6. **Do not push.** Report the commit hash and remind the user to push when they're ready.

### index

Regenerate the top-level `README.md` to mirror the live home page — masthead, "At a glance" stats, stage / product / model tables, and the article index grouped by primary stage. This is the same operation that runs as a step inside `draft`, `upcoming`, `polish`, and `publish` — `index` mode is the standalone trigger when the user asks for a README refresh without other authoring work.

1. Run `python3 ~/.claude/skills/nvidia-learn-stats/scripts/compute_stats.py` first if stats may be stale (e.g., the user just hand-edited an article's frontmatter outside this skill).
2. Run `python3 ~/.claude/skills/tech-writer/scripts/refresh_readme.py`. It reads `src/data/project-stats.json` + each `articles/<slug>/article.md` frontmatter and writes `README.md`.
3. Show the user a diff (`git diff README.md`) so they can spot anything unexpected before committing.
4. Do not commit unless the user asks. README-only refreshes typically ride along with the next article commit.

### extract

Run **after** an article publishes. Goal: identify code in the article's `evidence/` that should land in `fieldkit/` so the package keeps absorbing the recurring patterns. Outputs are *proposals* — never edits the article, never bumps the package version. The `fieldkit-curator` skill's `release` mode picks them up later.

1. Resolve the article: prefer the slug the user named; otherwise default to the most recently committed article (`git log --diff-filter=A --name-only --pretty=format: -- 'articles/*/article.md' | head -3`).

2. **Read the frontmatter and `evidence/` of the article.** Build a list of every Python (and shell, if relevant) file under `articles/<slug>/evidence/`. For each, note its public-looking shape — top-level functions, classes, CLI entrypoints — and the patterns it implements (NIM client wrapper? KV-cache math? RAG ingest loop? Eval harness? LLM-as-judge? Trajectory analysis? Telemetry collector?).

3. **Map each candidate against fieldkit's surface.** Cross-check using `references/fieldkit-imports.md` (current `__all__` + canonical imports) and the package source at `/home/nvidia/ai-field-notes/fieldkit/src/fieldkit/`. For each candidate, decide one of:
   - **Already-in-fieldkit** — the article should switch to the import. Note this in the report; do not edit the article (that's a follow-up `polish` if the user wants it).
   - **Extends an existing module** — propose a patch under `fieldkit/src/fieldkit/<module>/` adding the new symbol. Include a one-line diff sketch (function signature + one-paragraph behavior note), not a full implementation.
   - **Proposes a new module** — name the module, sketch its v0.x scope, suggest the version it should land in (default v0.2 unless the user is mid-cut). Use the deferred-modules table in `ideas/fieldkit.md` first; only invent a brand-new module name if no existing slot fits.
   - **Article-specific glue** — keep in `evidence/`. Not every snippet earns extraction. Articles that ship without a `# TODO(fieldkit): ...` comment don't need one fabricated.

4. **Write the report** to `fieldkit/CHANGELOG.md` under `## [Unreleased]` — one Markdown bullet per accepted candidate, formatted exactly:
   ```markdown
   - **`fieldkit.<module>.<Symbol>`** — one-sentence behavior. Source: `articles/<slug>/evidence/<file>.py`. ([extract from #<slug>])
   ```
   New modules get an `### Added — proposed module` sub-heading first. Reference labels (`[extract from #<slug>]`) collect at the bottom of `[Unreleased]`. Keep the section append-only — don't reorder existing bullets.

5. **Open a single staged change.** Show the user `git diff fieldkit/CHANGELOG.md`. Never commit. Never auto-push. The user reviews, then runs `fieldkit-curator release` (mode 8.5) when enough candidates accumulate to justify a version bump.

6. **Report briefly.** One sentence per category (already-in-fieldkit count, extends-existing count, proposes-new count, article-specific count) plus a pointer to the diff. Don't paste the report body in chat — the diff is the artifact.

**Non-negotiables for `extract`:**
- Never edit `article.md` or `evidence/`. The article is the historical record; only future articles use the lifted API.
- Never write to `fieldkit/src/fieldkit/`. Patch sketches live in the CHANGELOG entry until `fieldkit-curator` picks them up.
- Never bump `fieldkit/src/fieldkit/_version.py`. Versioning is `release` mode's job.
- If `fieldkit-curator` exists locally and the user asks "extract and release in one go," still run extract first, then hand off — surface a single CHANGELOG diff before any tagging.

## Screenshot quick reference

| Source | Tool | Notes |
|---|---|---|
| Web UI (NGC, build.nvidia.com, docs.nvidia.com, NIM playground) | Playwright-MCP (`mcp__playwright__browser_*`) | Full-page or scoped. Save to `articles/<slug>/screenshots/NN-description.png`. |
| CLI / terminal output | Fenced markdown code block | Accessible, searchable, copyable. **Not a screenshot.** |
| GUI installer / desktop dialog | `scrot` on `DISPLAY=:1` | Install with `sudo apt install scrot` if missing. |
| Animated multi-step CLI flow | `asciinema` (optional) | Only if rhythm matters; otherwise, a code block suffices. |

Full decision logic + exact commands: `references/screenshot-workflows.md`.

## Article folder contract

```
articles/<slug>/
├── article.md       # The essay: frontmatter + 8 sections + embedded refs
├── screenshots/     # NN-description.png (numbered for flow order)
├── transcript.md    # Cleaned source material from session + _drafts notes
└── assets/          # Diagrams (mermaid/ascii), config snippets, referenced files
```

Slug rules: kebab-case, lowercase, hyphens only. Good: `nim-first-inference-dgx-spark`. Bad: `My_NIM_Post`, `2026-04-21-nim`.

`articles/_drafts/<date>/` holds scratch notes from `capture` mode. **Never delete them** — when material is promoted to an article, move it to `<slug>/transcript.md`.

## Non-negotiables

- **Never publish secrets, PII, or system fingerprinting.** The scrub pass in `references/privacy-and-security.md` is mandatory before any content lands in `article.md`, `transcript.md`, or `assets/`. `scripts/verify_article.sh` re-runs the scan and blocks commits on any match. Author-approved overrides are honored but never silent.
- **Never auto-push to GitHub.** Stage + commit locally only. Publishing to remote is the user's call.
- **Never write voice-drift prose.** If a draft is starting to read like "Today we install X. First, run…", stop and re-anchor in the editorial overlay. See `references/voice-and-style.md` for drift signals and re-anchoring patterns.
- **Always ask for the editorial overlay** on a new draft. Do not proceed without it.
- **Always tie back to the uber theme** in the opening hook and the closing. The personal-power-user / edge-builder frame is why this blog exists next to nvidia.com.
- **Preserve `_drafts/` notes** — move them, don't delete, when material is promoted.

## When things go sideways

- **No articles/ tree yet?** Run `scripts/init_blog.sh`.
- **Playwright-MCP tools missing?** Confirm with `claude mcp list`. If tools named `mcp__playwright__browser_*` still aren't loaded, the session predates the install — ask the user to restart Claude Code. On aarch64 (DGX Spark), the default `chrome` channel fails (no Google Chrome arm64 build); register with `--executable-path` pointing at Playwright's bundled chromium — see `references/screenshot-workflows.md` ("aarch64 / DGX Spark note") for the exact command. If MCP still can't be used (reconfig doesn't reload mid-session), fall back to `scripts/playwright-screenshot.js`.
- **User wants to publish but hasn't pushed in a while?** Show `git status` and `git log --oneline -5` from the repo so they know what's staged before committing.
- **Slug collision?** `new_article.sh` errors out. Propose a disambiguating suffix (`-v2`, `-revisited`, or a subtopic).

## Where to look for deeper guidance

- **Privacy and security — what must never be published:** `references/privacy-and-security.md`
- **Voice + style + drift detection:** `references/voice-and-style.md`
- **Article structure + frontmatter schema:** `references/article-structure.md`
- **SVG architecture visualizations — archetypes, authoring template, motion policy:** `references/visualizations.md`
- **Explainer layer — six directive types, per-article budget, placement rules:** `references/explainers.md`
- **Screenshot commands + decision tree:** `references/screenshot-workflows.md`
- **Command/intent routing logic:** `references/commands.md`
- **Learning-objectives matrix for ai-field-notes:** `references/learning-objectives.md`
- **Running use-case arc (Second Brain) — default overlay + "next article" rule:** `references/use-case-arc.md`
- **`fieldkit` import lookup — what to import for each module declared in `fieldkit_modules`:** `references/fieldkit-imports.md`
- **Template to copy for a new article:** `assets/article-template.md`
