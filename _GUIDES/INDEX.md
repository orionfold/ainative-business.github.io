<!-- _GUIDES index — active guidance & practices for this repo. Last updated: 2026-06-02 -->

# _GUIDES — active guidance & practices

The single home for this repo's **active** guidance docs: publishing contracts,
distribution handoffs, and operator reference. Each file carries a
`<!-- Title — Last updated: YYYY-MM-DD -->` header. When guidance changes, update
the doc *and* its line below.

> **Root-tier living docs stay in the root** (not here): `WORKFLOWS.md` (the
> canonical origin-instruction → artifact map + roadmap) and `HANDOFF.md` (the
> living session-transfer doc). Skill-generated reports also stay in the root:
> `ainative-stats.md` (written by `ainative-stats`) and `seo-progress.md`
> (written by `seo-monitor`).

## Publishing contracts

| Guide | Last updated | What it governs |
|---|---|---|
| [`NARRATIVE-CONTRACT.md`](NARRATIVE-CONTRACT.md) | 2026-05-23 | The 11-rule publish rubric for every Orionfold artifact across HF cards + site detail pages (positioning-first, bounded drift, no roadmap language, sibling cross-links, Methods wire-back, data-driven visuals, notebooks-after-positioning). Enforced by `hf-publisher` + `scripts/verify_artifact_rendering.mjs`. Filename is a code/test identifier — kept verbatim. |
| [`PRODUCT-ARTICLES.md`](PRODUCT-ARTICLES.md) | 2026-05-29 | The `products/<slug>/product.md` launch-article genre — schema (build-metrics block + feature tour) and the rendering it requires. Authored by `product-writer`. Filename is a code identifier — kept verbatim. |

## Arena distribution

| Guide | Last updated | What it governs |
|---|---|---|
| [`arena-distribution.md`](arena-distribution.md) | 2026-05-28 | How the Orionfold Arena cockpit is built (`fieldkit arena build`) and published — the PyPI `fieldkit[arena]` wheel + the leak-proof static `/arena/` web preview + the static-vs-live contract. (Was `APP-SYNC.md`.) |
| [`arena-storefront-marketing.md`](arena-storefront-marketing.md) | 2026-05-28 | Storefront positioning + card/detail layout for orionfold.com (the separate light-themed MARKETER repo) — local-runnable CTA, not SaaS. (Was `APP-MARKETING.md`.) |

## Operator reference

| Guide | Last updated | What it governs |
|---|---|---|
| [`local-ai-stack-commands.md`](local-ai-stack-commands.md) | 2026-04-21 | Repeat commands for the local AI stack on the DGX Spark — Ollama, NemoClaw (`clawnav`), OpenClaw TUI, OpenShell gateway, plus troubleshooting + state-file map. (Was `COMMANDS.md`.) |

---

Specs, plans, and historical design docs live in [`../_SPECS/`](../_SPECS/INDEX.md).
