# Explainers — the learning-aid layer for ai-field-notes articles

Every published article ships an **explainer layer** — sidebar annotations that float in the gutter on desktop, collapse to inline blocks on mobile, and surface in `/glossary/` automatically. This reference is the source of truth for authoring them.

The explainer system exists because the blog has two audiences in one prose:

1. **The advanced reader** (DGX Spark owner, AI engineer) who wants the deep-dive essay voice and would resent inline definitions interrupting the flow.
2. **The aspiring AI researcher / engineer cross-learning the domain** (deep Go expertise, new to LLMs; data scientist learning the inference stack; junior ML engineer extending into systems) who needs *just-in-time* definitions, *why-this-matters* framings, and *go-deeper* pointers without leaving the page.

Inline definitions hurt the first reader. Footnotes hurt the second. Sidebar explainers serve both — the advanced reader's eye skips them, the cross-learning reader's eye lands on the relevant one and continues.

## The six directive types

All explainers are remark-directive container blocks: triple colons, type name, optional bracket label, body, triple-colon close. The remark plugin at `src/lib/remark-explainers.mjs` rewrites these to `<aside class="explain explain--<kind>">` nodes; CSS in `src/styles/global.css` injects the eyebrow label and the per-kind accent.

```markdown
:::define[KV cache]
Per-token attention state cached during decode...
:::
```

| Type | Eyebrow label | Accent | When to use |
|---|---|---|---|
| `:::define[term]` | `DEFINE` | cyan | First mention of a domain-specific term whose definition is non-obvious to a cross-learning reader. ~3 sentences. Auto-collected to `/glossary/`. |
| `:::why[bold-headline]` | `WHY THIS MATTERS` | amber | A non-obvious framing or motivation that the prose hints at but doesn't restate. Lead with a *headline* in brackets that's punchy and specific. |
| `:::deeper` | `GO DEEPER` | violet | Bullet list of links — papers, sibling articles, vendor docs. No bracket label. Place near the topic the reader might want to dig into. |
| `:::pitfall[bold-headline]` | `PITFALL` | rose | A common misconception, a config default that surprises, a bug that survives smoke tests. Bracket headline names the trap concisely. |
| `:::math[bold-headline]` | `IN PLAIN WORDS` | emerald | An isolated arithmetic or back-of-envelope calculation that benefits from sidebar treatment so the prose stays narrative. Bracket headline frames the math in human terms. |
| `:::hardware[bold-headline]` | `BEYOND SPARK` | gold | Frontier-hardware extrapolation — *"on Spark X tok/s, on H100 Y, on H200 Z."* Anchors the article's measurement to the broader hardware ladder. Bracket headline summarizes the through-line. |

## Per-article budget — 6–10 explainers, balanced palette

Pilots and the 2026-05-06 foundation rollout converged on **6–10 explainers per published article** (the bridge / shorter pieces sit at 6–8; foundation pieces at 10). More than 10 starts feeling decorated, less than 6 misses opportunities.

A balanced palette typically lands at:

- 3–4 `:::define` (term anchoring)
- 1–2 `:::why` (motivation reframes)
- 0–1 `:::pitfall` (often 1; sometimes 2 in articles with strong gotcha content)
- 0–1 `:::math` (usually 1, especially for arithmetic-heavy or sizing pieces)
- 1 `:::deeper` (papers + sibling articles)
- 1 `:::hardware` (frontier extrapolation — usually at the closing)

Skewing slightly more `pitfall` is fine in articles whose hero finding is a counterintuitive result. Skewing more `math` is fine for sizing / arithmetic pieces. Don't skew more `define` — over-defining is the most common failure mode.

## Where they sit in the prose

Explainers are **block-level**, placed between paragraphs, with blank lines on both sides. They do *not* go inside `<figure>` HTML blocks (markdown breaks out on blank lines and the figure renders as code). Place them adjacent to the prose that introduces or motivates the term — not at the top of the section, not at the bottom.

```markdown
prose paragraph that introduces the term...

:::define[term]
definition
:::

next prose paragraph continues the discussion...
```

The CSS alternates left/right gutter placement automatically (using `:nth-of-type(odd)`-style rules). You don't pick which side.

## Authoring rules

**1. The bracket label is the hook.** A reader who only reads the eyebrow + bracket label of every explainer should still pick up the article's main argument. Examples that work:

- `:::why[The OpenAI dialect is the lingua franca of local inference]`
- `:::pitfall[`temperature=0` is not a correctness lever]`
- `:::hardware[Same 8 GB FP8 weights, frontier coefficients]`

Examples that don't:

- `:::why[Why this matters]` — generic; doesn't earn the sidebar
- `:::pitfall[Be careful]` — doesn't say what to be careful of
- `:::define[Important term]` — define the term, not the importance

**2. `:::define` opens with a one-line concept gloss, then 2–3 sentences of context.** The reader should be able to stop after sentence one and continue reading without missing the article. Sentences 2–3 add the relevant nuance for *this article's use of the term*.

**3. `:::why` and `:::pitfall` headlines are ≤ 12 words.** They render in the article gutter at small size; a long headline wraps awkwardly.

**4. `:::math` is for short, freestanding arithmetic.** If the math runs longer than ~4 lines or needs a table, keep it in the body and skip the sidebar. The sidebar serves single-step calculations — *"24.8 tok/s × 0.75 words/token = 18.6 words/s ≈ 3.7× human reading speed"*.

**5. `:::deeper` is a bullet list, not prose.** Each bullet is one link + one short clause explaining what the reader gets from clicking. Three to five bullets max.

**6. `:::hardware` always anchors back to the article's measurement.** It's not "here's what an H200 can do" in the abstract — it's "the same equation the article walked, with frontier coefficients."

## What NOT to write as an explainer

- **Generic restatement of the prose.** If the explainer paraphrases the paragraph it sits next to, delete it.
- **Definitions for terms the cross-learning reader already knows.** "Python", "GPU", "API endpoint" don't earn explainers.
- **Definitions for terms the article is actually *about*.** If the article's title is "KV-cache arithmetic at inference," do define KV cache (the cross-learning reader needs the anchor) — but don't define every adjacent term recursively (`page`, `block`, `decode step` would be too much).
- **Why-explainers that are sales pitches.** "Why local inference is amazing" is bad. "Why local-vs-cloud changes the cost shape, not just the cost" is good.
- **Pitfalls that are obvious.** "Don't commit secrets" is documentation chrome; "the planner ignores your shiny new index by default" is a pitfall.
- **Decorative deeper blocks.** A `:::deeper` with one link and no context is just an inline link in disguise; promote it back to the prose.

## False-positive directives (text/leaf, not container)

The remark plugin at `src/lib/remark-explainers.mjs` neutralizes stray text/leaf directives so prose with colons doesn't break:

- `:59 UTC` (timestamps)
- `:8001` (port numbers)
- `3:2` (ratios)

These are rebuilt to plain text before HTML rendering. You don't need to escape them. Container directives (`:::name`) are only matched when the type is one of the six known kinds (`define`, `why`, `deeper`, `pitfall`, `math`, `hardware`) — unrecognized container names are also passed through as text.

## Verification

The `:::define[term]` directives are auto-collected to `/glossary/` at build time (the remark plugin populates `file.data.glossaryEntries`). Two consequences:

- **Each `:::define[term]` should have a unique `term`** within the article. The plugin slugifies the term for the anchor; duplicate slugs collide.
- **The `term` should be the noun phrase you'd file it under** in a glossary. Use `KV cache`, not `What is KV cache`.

`scripts/verify_article.sh` does NOT yet check explainer count — it's a soft target, not a hard gate. The build (`npm run build`) will fail on malformed directives (broken close tags, unclosed brackets), so always run a build before committing an article with new explainers.

## Worked examples — the pilots and the foundation

The seven foundation articles + bridge (F1–F7 + B) plus the two pilots (`kv-cache-arithmetic-at-inference`, `gpu-sizing-math-for-fine-tuning`) are the canonical examples. Read one when uncertain about placement or balance:

- **Arithmetic-heavy:** `kv-cache-arithmetic-at-inference` (10 explainers — see how `:::math` and `:::hardware` ground the per-token formula).
- **Foundation-style:** `nim-first-inference-dgx-spark` (10 explainers — see how `:::define[NIM]` opens after the lede and `:::hardware` closes the piece).
- **Bridge / shorter article:** `one-substrate-three-apps` (8 explainers — fewer because the article itself is shorter; the palette is still balanced).
- **Counterintuitive finding:** `bigger-generator-grounding-on-spark` (10 explainers — note the heavy `:::pitfall` use; the article's main result is a debunked assumption, so the pitfall density earns its place).

## Workflow integration

When drafting a new article (`tech-writer draft` mode, step 7-ish in the playbook), allocate an explainer pass:

1. Identify 6–10 candidates (one per non-trivial domain term + a few framings + 1–2 pitfalls + 1 deeper + 1 hardware).
2. Draft each as a 2–4 line block.
3. Place adjacent to the prose anchor — adjacent paragraph, not at the section header.
4. Check the bracket labels read like an article spine on their own.
5. Run `npm run build` before committing — broken directives fail loud.

When polishing an existing article (`polish` mode), audit:

- Are there 6–10 explainers? If under 6, propose new ones at terms the prose introduces in passing.
- Is the palette balanced? Heavy on defines is the usual drift.
- Do the bracket labels carry the article's argument when read in isolation?

When extracting to fieldkit (`extract` mode), no explainer interaction — explainers live in the article, not in the package.
