# Card polish — the Orionfold engagement-pull recipe

> **Narrative rules live in [`/_GUIDES/narrative-contract.md`](../../../../_GUIDES/narrative-contract.md)** (repo root). That file is the surface-agnostic canonical rubric — section order, drift bounds, no forward-looking language, sibling cross-links, lane differentiation. This file covers **HF-surface specifics only**: frontmatter conventions, llms.txt, Spark-tested table format, and the engagement-pull moves (above-the-fold differentiator, cross-link templates, wire-back hooks) that the HF model-card surface needs but the destination site's templates handle differently.
>
> If the rules below conflict with anything in `_GUIDES/narrative-contract.md`, the contract wins.

This file codifies the **v5 §3.15.b engagement-pull recipe** — the set of model-card design moves that separates a card someone clones-and-forgets from a card someone *likes, follows, and recommends*. The reference exists because empirical evidence (Pulse #1, 2026-05-16) showed the four shipped Orionfold cards landed **472 DL / 0 likes** despite measurement quality being uniformly strong: the gap is a card-design problem, not a content problem.

The renderer in `fieldkit.publish.publish_quant` controls the bones of the card; this file owns the **above-the-fold differentiator block, the cross-link template, the wire-back hooks, and the metadata-completeness contract** that the renderer can't infer from kwargs alone. Read this every time you're about to push a new Orionfold artifact OR auditing an existing card via `card-audit` mode.

## §0 Canonical section order — positioning first, drift last

The v0.5.x section order, in this order, every time:

1. **YAML frontmatter** — `license`, `library_name`, `base_model`, `pipeline_tag`, `tags`, `model_creator`.
2. **# Title + one-line elevator.**
3. **## What this model does** — *positioning*. Customer problem → use cases → audience. Driven by `ModelCard.positioning`.
4. **## Spark-tested** — measurement quad/triple. The Orionfold moat.
5. **## Variants** — within-repo quant choice (Q4_K_M / Q5_K_M / …).
6. **## Choosing this lane** — *which-sibling-repo choice* for multi-stack bakeoffs (Unsloth vs NeMo, GGUF vs BF16). Driven by `ModelCard.stack_origin` + `ModelCard.lane_summary`.
7. **## How to run** — Ollama / Transformers / GGUF snippets.
8. **## Lineage** *(optional)* — trial log from `LineageStore`.
9. **## Methods** — link to the deep-dive article at `ainative.business/field-notes/<slug>/`.
10. **## Known drift** — bounded limitations. See §6.
11. **## Other Orionfold variants** — sibling cross-link table. Driven by `ModelCard.siblings`.
12. **Footer** — Orionfold attribution + orionfold.com.

**Why this order matters.** A HF visitor scrolls top-to-bottom. The first H2 sets the model's first impression. The 2026-05-22 patent-strategist publish landed cards with `## Known issues` as the first H2 — two MPEP fabrication bullets before any positioning — which read as "this model hallucinates." After repolish (2026-05-22), positioning leads, drift sits below Methods, bounded with counts. See [[hf-readme-positioning-first]] memory.

**Reject any reshape** that puts How-to-run, Known issues, Limitations, License, or Citation above the positioning + Spark-tested pair. If a contributor argues for "usability" (put How-to-run first) or "transparency" (put Limitations first), redirect: positioning IS the transparency — it's an honest statement of what the model is for. Bullets about what it gets wrong come AFTER bullets about what it does, never before.

## The five engagement-pull elements

Every Orionfold card lands with all five present. Missing any one is the signal that triggers a card-polish loop before push (or a `card-audit` retro-fix for already-pushed cards).

### 1. Spark-tested differentiator block — at the top, not buried

The `## Spark-tested` section is the Orionfold moat. **Position it above `## How to run`, immediately after the one-liner.** That's the order the renderer emits today; preserve it. If anyone reshapes the card to put "How to run" first ("for usability"), reject — `## Spark-tested` is what differentiates Orionfold from the 50 other GGUF re-uploads of the same base. A user who scrolls past it hasn't seen the value prop.

Inside the block, the contract is:
- One short paragraph that names the measurement quad/triple (perplexity, sustained tok/s, thermal envelope, +/- vertical-eval) and says "the actual run, not a wishlist"
- The measurement table — Variant | Size | Perplexity | tok/s | (optional vertical-eval) — populated with `as-measured` numbers per `[[project_q8_anomaly_model_specific]]` (never pre-correct Q8_0)
- A `**Recommended:** <variant>` line ABOVE or IN the table (not buried under), keyed off `recommended_variant` (default `Q5_K_M`)

`scripts/verify_stage.sh` Check 3 enforces the table shape; this reference enforces the placement + recommended-variant prominence.

### 2. Sibling Orionfold card cross-links — explicit, not buried

Every card includes a `## Other Orionfold vertical curators` block at the end (above `## License`). The block lists each sibling card with a one-line "what it is, who it's for" hook. This is the single largest amplification lever:
- A user who landed on `Orionfold/II-Medical-8B-GGUF` for the medical card sees, in 30 seconds, that there are 3 other verticals — finance, legal, cyber — and that they're built on the same Spark-tested differentiator
- Each visit to one card threads visits to the others; download counts compound

Template (the publish_quant caller should pass via `extra_yaml` / a custom markdown block; the renderer doesn't auto-generate this yet — Phase 2 of `fieldkit.publish` may codify it):

```markdown
## Other Orionfold vertical curators

Same Spark-tested recipe across the curator-on-Spark series:

- **[finance-chat-GGUF](https://huggingface.co/Orionfold/finance-chat-GGUF)** — AdaptLLM finance-chat (Llama-2-7B lineage) for FinanceBench-shaped queries
- **[Saul-7B-Instruct-v1-GGUF](https://huggingface.co/Orionfold/Saul-7B-Instruct-v1-GGUF)** — Equall Saul-7B legal-instruct for LegalBench-shaped queries
- **[zephyr-7b-cyber-GGUF](https://huggingface.co/Orionfold/zephyr-7b-cyber-GGUF)** — Mistral-7B + Zephyr DPO with cyber-eval gating
- **[II-Medical-8B-GGUF](https://huggingface.co/Orionfold/II-Medical-8B-GGUF)** — Qwen3-8B + DAPO reasoning for MedMCQA-shaped queries

Each card lists its own measurement quad; the headline numbers are recorded as the actual sweep ran, never pre-corrected.
```

**Maintenance rule:** every new vertical card edits this block on the previous N cards as part of the push session. Don't ship vertical #5 without back-editing finance/legal/cyber/medical card cross-links to include it. (This is the cross-link half of the engagement-pull lever — without backfill, only the newest card benefits.)

### 3. Wire-back to article + llms.txt

The `## Methods` section already links to the article at `https://ainative.business/field-notes/<slug>/`. **Two additional wire-backs strengthen the loop:**

- **`## Read the deep-dive` block** above the cross-links — explicit invitation to read the article, with one-line abstract pulled from the article's frontmatter
- **`llms.txt` entry** at `https://ainative.business/llms.txt` for this specific card → article slug pairing. When an LLM agent surfaces the model, the llms.txt entry tells it where the canonical methods writeup lives

Check 4 already validates the article exists locally; this reference adds the requirement that the wire-back is *explicit and visible*, not just a buried URL.

### 4. Launch-list call — the engagement endpoint

Engagement-pull without a conversion endpoint is a vanity metric. The Orionfold funnel is: HF card → article deep-dive → orionfold.com mailing list. **The endpoint is the launch list**, not a paid Sponsors page — Orionfold's commercial brand is still pre-launch, asking for sponsorship is premature. Every card includes a launch-list line in the footer:

```markdown
> Want to know when the next Orionfold vertical curator drops? [Join the launch list at orionfold.com](https://orionfold.com).
```

The placement matters: footer, after the publisher attribution line, single line, conversational. Not an ad-block; a "stay in the loop" credit-line that captures interested traffic into a real channel.

**When Sponsors becomes the right endpoint** (revisit per `[[project_orionfold_parent_brand]]`):
- Orionfold has shipped 6+ verticals (commercial credibility floor)
- A working `github.com/sponsors/manavsehgal` page exists (don't link before it exists — a 404 conversion endpoint is worse than nothing)
- The product launch on orionfold.com has happened (sponsorship asks land better post-launch)

Until those conditions hold, the launch list is the right call.

### 5. Frontmatter metadata completeness

The bones. Without these, HF's discoverability surfaces (model search, leaderboards, the `pipeline_tag` filter) won't surface the card regardless of card content:

- `pipeline_tag: text-generation` (or appropriate non-text-generation tag — verify against the model's actual output shape; default is correct for chat-tuned GGUFs)
- `library_name: gguf` (or `transformers` for non-GGUF formats)
- `tags:` — non-empty list of **at least 3** entries including:
  - `spark-tested` (Orionfold differentiator — required)
  - `gguf` (format)
  - `llama-cpp` (runtime hint)
  - `<vertical>` (finance / legal / cyber / medical / patent / …)
  - Optional: chat-format hint (`llama-2`, `chatml`, etc.), license-flavor tag (`apache-2.0`), or HF taxonomy tag (`text-generation-inference`)

`scripts/verify_stage.sh` Check 6 enforces this contract. The `$VERIFY_REQUIRED_TAGS` env var defaults to `spark-tested` and is comma-separated for additional required tags; `$VERIFY_MIN_TAGS` defaults to 3.

**How to populate from publish_quant:** thread a `tags=(...)` tuple kwarg into the call. The `g3_build_first_quant.sh` orchestrator should set this automatically per the resolved vertical; if it isn't doing so today, that's a fieldkit gap and the fix path is either patching the orchestrator or passing the kwarg explicitly in step 2 of the workflow.

### 6. Drift / Limitations section — bounded, below-the-fold, current-truth-only

The `## Known drift` block disclosed measured limitations honestly without making the model read as broken. Three rules, all required:

**Never above-the-fold.** Drift goes AFTER `## Methods`, never before `## Spark-tested`. If a contributor proposes moving it up "for transparency," redirect to §0 — positioning IS the transparency. Drift is a calibrated footnote, not the headline.

**Always bounded.** Every entry in `ModelCard.known_drift` must carry a `bound` field that quantifies the scope: a count ("2 of 200 bench questions"), a fraction ("<1% of probe answers"), or a comparison ("balance of bench cites real MPEP sections"). Unbounded narrative drift — "the model sometimes hallucinates legal citations" — is **not card-ready**. Send it back to measurement. If you can't put a number on it, you don't have a card-ready disclosure.

**No forward-looking roadmap.** The `known_drift` schema does NOT have a `fix_eta` field, and the renderer will not surface one. READMEs ship current truth only — promised fixes ("v4 will address this", "MPEP-grounded retrieval is on the roadmap") rot, over-promise, and shift the reader's attention from what works today to what might exist someday. If a fix has shipped, update the manifest and re-render the card; if it hasn't shipped, don't write a check the next release has to cash.

Drift block opens with one scope-framing sentence emitted by the renderer ("Bounded limitations observed during Spark-side measurement…"), then a tight bullet list. Each bullet: `- **<item>** — <bound>`. Done. Do not append "see also" links, mitigation tips, or "we're working on it" sentences.

### 7. Lane differentiation — for multi-stack bakeoff releases

When a release ships across multiple training stacks (Unsloth + NeMo) or multiple formats (GGUF + BF16) as sibling repos, every sibling card carries a `## Choosing this lane` block between `## Variants` and `## How to run`. Driven by `ModelCard.stack_origin` (enum: `unsloth` | `nemo` | `axolotl` | `verl` | `peft`) + `ModelCard.lane_summary` (free-form copy).

**Audience split** — every lane targets a different reader:

- **GGUF lanes** speak to inference-time users: tok/s, perplexity, llama.cpp / Ollama / LM Studio, low-VRAM. Frame as: "Pick this lane for offline / edge inference. For continued fine-tuning, see the BF16 sibling."
- **BF16 lanes** speak to research / fine-tune continuation users: continued training, transformers integration, NeMo PEFT, production Triton / TensorRT-LLM serving. Frame as: "Pick this lane for continued fine-tuning or transformers-format inference. For pure inference on Spark-class hardware, the GGUF sibling is faster."
- **Bakeoff-winning lane** gets the headline numbers lifted into the copy: "-X% perplexity, +Y% tok/s, +Z% reasoning depth vs the sibling." Don't bury the win.
- **Bakeoff-losing lane** acknowledges the loss honestly and names who should still pick it: lineage consistency, ecosystem preference, dev-velocity. Don't pretend the lanes are equivalent if they aren't.

**Default copy when only `stack_origin` is set** — the renderer emits a generic "GGUF-trained / BF16-trained" lane intro keyed off the stack name. Override via `lane_summary` whenever the bakeoff numbers warrant: the default is correct-but-thin, and the explicit copy is where the differentiation lives.

**Frontmatter tag** — when `stack_origin` is set, the renderer auto-appends `trained-with-<stack>` to the frontmatter tags. Do not duplicate it in the explicit `tags` kwarg; the renderer dedupes but cleaner to omit.

## The retro-fix playbook (already-pushed cards)

When `card-audit` mode flags an existing HF card as gap-ridden, the fix is straightforward but session-discipline matters:

1. Pull the current `README.md` from the HF repo to `/tmp/card-audit-<slug>/`.
2. Diff against the desired shape (this reference is the source of truth — start with §0 section order).
3. Patch in place. Common §0 violations:
   - **Drift block above the fold** (the 2026-05-22 patent-strategist class of bug): rebuild the card via `ModelCard(...).render()` with `positioning=`, `stack_origin=`, `known_drift=`, `siblings=` kwargs populated from the artifact manifest. The renderer enforces the section order; you don't have to.
   - **No `## What this model does` block**: populate `positioning` in the manifest YAML, re-render.
   - **No `## Choosing this lane` block on a multi-stack release**: populate `stack_origin` + `lane_summary`, re-render.
   - **Engagement-pull gaps** (cross-links / launch list / tags): edit the rendered output directly before push, or extend the renderer if the gap is systemic.
4. Use `huggingface_hub.upload_file` with a one-line scope-framing `commit_message` (e.g., "Card repolish — lead with positioning, bound the drift section, differentiate by lane") to push **just the README**. **Do not** re-run `publish_quant` — that re-stages and re-uploads all the weights.
   - The patent-strategist v3 repolish (2026-05-22) used `scripts/republish_patent_strategist_readmes.py` as the reference shape for this README-only path. Mirror that script when retro-fixing other multi-lane releases.
5. After push, back-edit the cross-link block on every other Orionfold card (since now there's one more card that should appear in everyone's sibling list).

Per `[[feedback_handoff_md_update_protocol]]`, log the retro-fix in HANDOFF.md as part of the session-close, and use a descriptive commit subject (`chore(field-notes): repolish <slug> card`) so Mac's `/sync-field-notes` skill sees the change in `git log`. The pre-2026-05-22 SYNC-HANDOFF.md rotation step is no longer required — see `[[sync-workflow-nfs-mount]]`.

## When to bend these rules

- **Q5_K_M not present in variants** — recommended_variant must be one of the actual variants. If the quant sweep ran a different mix (e.g., Q4_K_M / Q6_K / Q8_0 only), pick the closest quality-per-byte point and explain in `## Recommendations`.
- **Single-vertical cycles** — the "Other Orionfold vertical curators" block can be omitted on the *very first* card in a series (no siblings yet). From card #2 onward, it's required.
- **Non-GGUF artifacts (LoRA adapters)** — `library_name` becomes `transformers` or `peft`; `pipeline_tag` may shift to `text-classification` etc. depending on adapter intent. The five engagement-pull elements still apply.
- **Non-commercial license cards** — Sponsors line can stay; engagement-pull doesn't depend on commercialization. (Though per `[[project_orionfold_parent_brand]]`, Orionfold's commercial tier prefers permissive licenses; a non-permissive card is a deviation that should be flagged in the scout report.)

## Memory cross-references

- `[[hf-readme-positioning-first]]` — the §0 section order rule + §6 drift bounds + §7 lane differentiation. Read first on any card-audit or new push.
- `[[feedback_customer_link_audit]]` — voice-and-style audit (separate from this engagement-pull audit, but pairs with it at push time)
- `[[feedback_handoff_md_update_protocol]]` — the session-close log for retro-fixes
- `[[project_q8_anomaly_model_specific]]` — the "never pre-correct Q8_0" rule applies to the Spark-tested table
- `[[project_orionfold_parent_brand]]` — commercial-tier framing
- `[[feedback_refresh_stats_on_publish]]` — the post-fix HANDOFF + stats refresh tail

## What's intentionally NOT in this reference

- **Article voice + structure** — that's `tech-writer` skill's `references/voice-and-style.md` + `article-structure.md`. The customer-link audit at SKILL.md step 4 cross-references that.
- **Renderer logic** — that's `fieldkit/src/fieldkit/publish/__init__.py`. If the renderer needs to auto-emit cross-link blocks or Sponsors footers, that's a v0.4.x fieldkit change tracked through `fieldkit-curator`.
- **Discoverability A/B testing** — once 6+ verticals have shipped with this recipe and the engagement gap closes (or doesn't), this reference will get a "what moved the needle" pulse section. Until then, the recipe is hypothesis-driven from the 4-vertical pulse.
