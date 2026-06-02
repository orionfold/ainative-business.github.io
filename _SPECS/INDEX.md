<!-- _SPECS index — project specs, plans, and historical design docs. Last updated: 2026-06-02 -->

# _SPECS — specs, plans & design docs

The single home for this repo's specifications. Consolidated 2026-06-02 from the
former `specs/`, `spec/`, `plans/`, and `docs/superpowers/` folders. Active specs
keep their original basenames (they are referenced as `_SPECS/<name>.md` across the
skills, `src/content.config.ts`, and the `fieldkit` package source).

## Active specs

| Spec | Status | Scope |
|---|---|---|
| [`patent-strategist-v1.md`](patent-strategist-v1.md) | ACTIVE | First fine-tuned vertical — hand-curated patent corpus + DeepSeek-R1-Qwen3-8B LoRA SFT + VerticalBench. §3.3 defines the `fieldkit.eval` scorers; §4 the corpus synth template (read by `claude-corpus-synth`). |
| [`notebooks-as-artifacts-v1.md`](notebooks-as-artifacts-v1.md) | ACTIVE (locked) | The 6th artifact kind — dual-path Spark/Colab builder + user notebooks per vertical. Governs `notebook-author` / `notebook-snapshot` + `fieldkit.notebook` / `fieldkit.viz`. |
| [`spark-arena-v1.md`](spark-arena-v1.md) | ACTIVE | The Orionfold Arena operator cockpit (M1–M7) — sidecar, chat, compare, leaderboard, leak-proof mirror. Governs `fieldkit.arena`. |
| [`hermes-harness-v1.md`](hermes-harness-v1.md) | ACTIVE | The Harnesses content line — install / serve / harden / route / eval an agent harness (Hermes first) on the Spark. Governs `fieldkit.harness`. |

### Rendering companions

| Spec | Status | Scope |
|---|---|---|
| [`hermes-harness-v1-mac.md`](hermes-harness-v1-mac.md) | ACTIVE | Section-by-section rendering-side companion to `hermes-harness-v1.md` ("what the site renders for the `harness`/`skill` artifact kinds"). |
| [`notebooks-as-artifacts-v1-mac.md`](notebooks-as-artifacts-v1-mac.md) | ACTIVE | Rendering-side companion to `notebooks-as-artifacts-v1.md`. Supersedes the archived model-playground design (see below). |

## Archive (superseded / historical — kept for the record)

| Doc | Retired | Why |
|---|---|---|
| [`archive/2026-05-22-model-playground-and-eval-surface-design.md`](archive/2026-05-22-model-playground-and-eval-surface-design.md) | 2026-05-23 | The HF-Space playground + Tier A/B/C eval approach; replaced by the notebooks-as-artifacts badge on-ramp. Marked do-not-implement. |
| [`archive/patent-strategist-v4-nemo.md`](archive/patent-strategist-v4-nemo.md) | 2026-05-24 | v4 retrain plan; the spaceless-`<think>` defect was diagnosed as Unsloth-lane-only and resolved by deleting the Unsloth artifacts instead. Kept as the S1 diagnostic record. |
| [`archive/superpowers/`](archive/superpowers/) (12 docs) | 2026-04 | Dated design + execution-plan pairs from the 2026-03/04 stagent.io → ainative.business pivot (landing-page, hero, tech-ticker, architecture-glance, the pivot itself, apply-product-release consolidation). The pivot shipped long ago. |

---

> **Note on `fieldkit/CHANGELOG.md`:** its historical entries still reference the
> old `specs/<name>.md` paths by design — a changelog is an immutable record of
> what was true at release time and is not rewritten. Likewise the `spec_ref`
> fields in `evidence/*.json` and one published article's external permalink to
> the archived `ai-field-notes` repo keep the old path. Live references (skills,
> content config, `fieldkit` source docstrings, `fieldkit/docs/api/`) point here.

Active guidance & practices live in [`../_GUIDES/`](../_GUIDES/INDEX.md).
