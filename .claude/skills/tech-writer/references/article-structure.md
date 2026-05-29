# Article Structure

Each article is a folder. The folder is the unit of publishing; the markdown file is only the entry point.

## Folder contract

```
articles/<slug>/
├── article.md       # The essay
├── screenshots/     # NN-description.png, numbered by article flow
├── transcript.md    # Cleaned source material (provenance)
└── assets/          # Diagrams, config snippets, referenced files
```

### Slug rules

Kebab-case, lowercase, hyphens only. Short, descriptive, SEO-aware.

- **Good:** `nim-first-inference-dgx-spark`, `nemo-finetune-llama-on-spark`, `agentic-stack-without-cloud`
- **Bad:** `my-nim-article`, `2026-04-21-setup`, `Getting_Started`, `final-v2`

The slug is permanent — it's the URL. Choose it once, carefully.

## Frontmatter — Astro content collection schema

The shape below must match the Zod schema in `/home/nvidia/ainative-business.github.io/src/content.config.ts`. Astro validates at build time, so any missing field, typo in a field name, or out-of-range value (summary > 300 chars, stage not in the enum) will fail `astro build`. `scripts/verify_article.sh` runs the same core checks locally so errors surface in publish mode, not only at site build.

```yaml
---
title: "A concrete, insight-forward title"
date: 2026-04-21
author: Manav Sehgal
product: NIM
stage: inference
difficulty: intermediate
time_required: "~2 hours"
hardware: "NVIDIA DGX Spark"
tags: [nim, inference, on-device, first-contact]
summary: "One-paragraph TL;DR under 300 chars. Stands alone — a reader who reads only this should know what they'll get from the full article."
signature: NimPipeline   # component name under src/components/svg/, renders as the home-card thumbnail
---
```

### Field meanings

| Field | Guidance |
|---|---|
| `title` | Lead with the insight or outcome. **"Your First NIM Inference on DGX Spark — and What It Says About On-Device Deployment"** beats "Installing NIM on DGX Spark". |
| `date` | ISO format `YYYY-MM-DD`. The day the article was finalized, not the day the work was done. |
| `author` | `Manav Sehgal` unless overridden. |
| `product` | **One primary value.** Multi-product pieces pick the one a reader would search for. Valid: `NIM`, `NeMo`, `Triton`, `TensorRT-LLM`, `RAPIDS`, `CUDA`, `Blueprints`, `Base Command`, `DGX OS`, `NGC`, `Nsight`, `Foundation` (general DGX-Spark / environment pieces). |
| `stage` | **One primary value.** Valid: `foundations`, `training`, `fine-tuning`, `inference`, `deployment`, `agentic`, `observability`, `dev-tools`. |
| `difficulty` | `beginner` \| `intermediate` \| `advanced`. Be honest. Reader self-selects. |
| `time_required` | Realistic hands-on time including waits. If you hit a 45-minute Docker pull, say so. |
| `hardware` | `"NVIDIA DGX Spark"` for anything Spark-specific. Extend if the article references external hardware. |
| `tags` | 4-8 kebab-case tags. Reuse across articles — repeated tags make the index browsable. |
| `summary` | **Under 300 characters, stands alone.** Enforced hard by the Astro schema (`z.string().max(300)`) — over-length summaries fail the build. The verify script catches this in publish mode so you don't hit it at build time. |

## The 8-section body

Write in this order. Each section has a specific purpose — don't skip without a reason.

### 1. Opening hook (1-3 paragraphs)

Lead with the **insight, concept, or question** the piece is really about. Not "today we install X." Something like:

> On a cluster, you pick the model that fits your GPUs. On a DGX Spark, 128GB of unified memory inverts the question — now the model picks the hardware almost never, and that changes what you can reasonably attempt on your own.

The hook must contain the **specific claim** this article will back up with evidence. If the reader stops after the hook, they should still know what the article is about.

### 2. Why this matters for the personal AI power user / edge builder (1-2 paragraphs)

**Explicit tie to the uber theme.** What does this piece teach a reader about what this one machine lets one person do? If you can't write this paragraph, the article isn't ready.

Connect to concrete reader concerns: cost of cloud inference, data gravity, latency, independence, prototyping speed, privacy. Name at least one of these.

### 3. Architectural context (2-4 paragraphs, typically a diagram)

Where does this product sit in the larger LLM / inference / agentic stack? What does it replace, enable, or complement? Readers arriving at NIM have often also heard of Triton, vLLM, Ollama, TensorRT-LLM — help them place this one on the map.

**This is the default slot for the article's architecture visualization.** An inline SVG diagram in one of the six archetypes (flow pipeline, layered stack, dual-path comparison, hub-and-spoke, timeline, waterfall) almost always reinforces the thesis better than prose or ASCII. Read `references/visualizations.md` for archetypes, the authoring template, motion policy, and the taste test. Keep ASCII for quick sketching during `capture` mode — but convert to SVG before publishing.

If a diagram isn't warranted (rare), a short prose placement beats a cluttered ASCII block:

> Llama 3.1 8B bundled as a NIM container (TensorRT-LLM + OpenAI-compatible API) on a DGX Spark's 128 GB unified memory, fronting your agent or app directly.

### 4. The journey (bulk of the article)

The actual setup + exploration, woven with commentary. Each step should answer three things:

1. **What did I run?** (command or action)
2. **What happened?** (output, screenshot, observation)
3. **What does it mean?** (interpretation, connection to the thesis)

Steps are evidence; commentary is the backbone. Rough ratio: **two paragraphs of prose per code block**. Embed screenshots from `screenshots/` with descriptive alt text and captions.

### 5. Verification — what success looks like on DGX Spark (1-3 paragraphs)

Not "run the health check" — what *does success feel like on this machine*? Concrete:

- Inference latency you can compare to cloud (or to a laptop).
- A model fitting in memory that you didn't expect to fit.
- A GPU utilization pattern visible in `nvidia-smi`.
- Cold-start time numbers.

Hardware-aware verification is what makes this section different from the vendor's checklist.

### 6. Tradeoffs, gotchas, surprises (honest, 2-4 paragraphs)

**The piece of official docs doesn't write.** What didn't work on the first try? What did naming confuse you about? What version mismatch cost you an hour? What tradeoffs are you making that the marketing copy glosses over?

This section is the second-biggest differentiator after the uber-theme tie-in. Readers remember the honest friction.

### 7. What this unlocks (2-3 paragraphs)

Concrete use cases the reader can now pursue. Not "the possibilities are endless" — **three named things** the reader could build this week with what they just learned.

Example (bad): "Now you can deploy any model you want."
Example (good): "Now you can stand up a local voice-transcription API that doesn't depend on OpenAI, feed it from a Whisper NIM container, and wire it to your meeting recorder in an afternoon. The second thing you can do: …"

**For product-card-linked articles** (frontmatter has `customer_linked: true`, or a Hugging Face / Civitai / app-store listing points at this article): the named use cases are for the reader *downloading the artifact*, not for the publisher's roadmap. Cut roadmap-shaped framings ("the next vertical we tackle", "the second cycle sleeper") and lean into reader-facing concreteness ("a local chatbot fronting your notes corpus", "an agent that drafts variance commentary against a structured tables source").

### 8. Closing (1-2 paragraphs)

Tie back **explicitly to the uber theme**. Name the next article in the series if applicable:

> Next up: serving three concurrent NIM endpoints on one Spark without OOMing — the memory math gets interesting.

Leave the reader wanting Monday.

**For product-card-linked articles**: the closing is reader-facing — "what to do Monday morning with this artifact" — not roadmap-facing. Skip HANDOFF Q-references, internal planning-doc section numbers, and named-next-release detail. A brief "watch the org page for the next release" pointer is fine; a "next up is the cybersec sleeper from §4 Q14(c)" pointer is not.

## Image references in markdown

```markdown
![The NGC catalog showing the "Optimized for DGX Spark" filter toggled on, with four model tiles visible below.](screenshots/03-ngc-catalog-nim-filter.png)

*The filter narrows thousands of containers to a few dozen that have been Spark-optimized. Note the "Runnable on 1x GPU" badge — that's the flag that matters here.*
```

- **Alt text** is for accessibility AND SEO. Describe what's *in* the image, not just label it.
- **Caption** tells the reader what to *notice*. It's interpretation, not description.
- Both belong on every meaningful screenshot.

## Length guidance

- **Under 800 words** → it's a blog note, not an article. Consider merging with a sibling or publishing as a shorter format.
- **1,500-3,500 words** → the sweet spot for a deep-dive on an infra topic.
- **Over 4,000 words** → split into a series. Link explicitly in frontmatter or in a prominent "This is Part N of M" block.

## Provenance: transcript.md

Every article's folder includes a `transcript.md` that preserves the cleaned source material — the conversation snippets, command logs, and screenshots that became evidence in the article. This is:

- A reproducibility aid — if a reader asks "how did you actually do this?", the transcript is the answer.
- A foundation for future articles — material that didn't make this cut might be the seed for the next one.
- A guard against over-polish — if the article strays from what actually happened, the transcript is the record.

Do not delete `_drafts/` notes after promoting them — move them into `transcript.md`.
