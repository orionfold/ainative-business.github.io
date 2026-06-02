---
project: notebooks-as-artifacts
version: v1.0
status: locked
created: 2026-05-23
authoritative: Spark
---

# Notebooks as a first-class artifact — v1.0 Specification

## 1. Context

### Why this project

We publish vertical model artifacts (GGUF quants, LoRA adapters, benches) under the
`Orionfold` HF handle, render them as cards on ainative.business, and write each up as a
deep-dive article. The artifact → card → article loop sells the *outcome* but offers no
**runnable on-ramp**. A researcher who wants to reproduce the build, or an app developer who
wants to call the model, has to reconstruct the journey from prose.

This project adds a sixth artifact kind — **`notebook`** — and, for every vertical model
release, **two Jupyter notebooks**:

- a **builder** notebook for the AI researcher / engineer, walking the build journey as
  `fieldkit` API calls so the takeaway is **speed of development with fieldkit, feasibility,
  and viability of building on Spark**; and
- a **user** notebook for the model consumer / app developer, walking realistic use cases so
  the takeaway is **desirability of building on Orionfold models, viability of building with
  fieldkit, and feasibility of Spark as the inference device**.

Both are distributed as ainative.business artifact cards **and** as one-click **Open in
Colab / Open in Kaggle** experiences, with prominent top-of-page badges in the artifact card
detail and the HF README — the way top GitHub repos lead with badges.

Editorial uber-theme alignment: the notebook is the most direct expression yet of "DGX Spark
as personal AI power user / edge AI builder" — you don't read about the journey, you run it.

### Design mandate (from the planning session)

Notebooks are treated as **marketing landing pages**: heavy on appropriate visualizations,
charts, and well-formatted tables, polished both as docs-plus-code and as executed cells. A
companion `notebook-snapshot` skill captures fully-run notebooks as images for reuse across
the website and marketing channels.

Throughout, we **watch for opportunities to generalize** — wherever notebook creation, use-
case demo construction, or model-pipeline automation repeats, we extract a `fieldkit` API
rather than hand-coding it again (§8).

## 2. Decisions locked

| # | Decision | Choice |
|---|----------|--------|
| 1 | Colab/Kaggle runtime | **Dual-path, runtime-detected.** Spark = full local fieldkit path; Colab/Kaggle = cloud fallback (pull published GGUF from HF, run via `llama-cpp-python` on the free GPU). Hardware-only builder steps render pre-run outputs behind a banner. |
| 2 | Visual stack | **matplotlib + branded `fieldkit.viz`** static charts + **great_tables** hero tables + pandas `Styler` fallback. |
| 3 | Authoring | **`notebook-author` skill** (sibling to `tech-writer`) **plus** a separate **`notebook-snapshot`** skill. |
| 4 | Scope | **Pilot patent-strategist end-to-end, then templatize** across finance / legal / cyber / medical. |

## 3. Artifact-kind change — add `"notebook"` (the 6th kind)

Same three-file mirror touched by the 8→5 narrowing (commit `95d6aa4`):

- `fieldkit/src/fieldkit/publish/__init__.py` — add `"notebook"` to `ARTIFACT_KINDS`
  (now `quant, lora, adapter, dataset, bench, notebook`).
- `src/content.config.ts` — add `"notebook"` to the const array feeding the artifacts zod enum.
- `fieldkit/tests/test_publish.py` — extend the kind assertion (`_canonical_five` → `_canonical_six`).

**Manifest granularity:** **one notebook manifest per vertical**, with
`variants: [builder, user]` — the two notebooks are facets of one offering, like quant
variants. `class: ipynb`. It reuses existing manifest fields:

- `positioning` (problem / use_cases / audience / headline) — required, per NARRATIVE-CONTRACT.
- `known_drift` — bounded (e.g. *"Colab path runs Q4_K_M; reasoning quality bounded vs the
  BF16 LoRA — see sibling card"*). Every entry carries a `bound`.
- `article` — wire-back to the source deep-dive(s).
- `stack_origin` — optional, inherited from the sibling model.
- `hf_repo` — the sibling model repo the notebooks target (not a separate notebook repo).

Notebook manifests carry **no** `perplexity`/`spark_tokens_per_sec`/`vertical_eval` of their
own — chart data is sourced from the sibling **model** manifest by slug. **New field**
`notebooks` (§8.3) carries the Colab/Kaggle URLs the card renders as badges.

## 4. Notebook anatomy

### 4.1 Builder notebook — "Build `<vertical>` on a Spark with fieldkit"

Audience: AI researcher / engineer. Spine: the vertical's article journey, with each step
expressed as a `fieldkit` API call that replaces a prior ad-hoc script. Takeaway contract:

- **Speed** — visibly collapse N hand-rolled scripts into a handful of typed API calls.
- **Feasibility** — frame every heavy step with `fieldkit.capabilities` arithmetic (does it
  fit the 128 GB unified-memory envelope?).
- **Viability** — it shipped: end on the live HF artifact + the published card.

### 4.2 User notebook — "Use `<vertical>` in your app"

Audience: model consumer / app developer. Spine: realistic, domain-specific use cases.
Takeaway contract:

- **Desirability** — model capabilities shown on real tasks, reasoning chains surfaced.
- **Viability** — `fieldkit` glue (RAG grounding, eval scoring) makes app-building tractable.
- **Feasibility** — runs locally on Spark *and* on a free Colab/Kaggle GPU (dual-path).

### 4.3 Narrative cadence (both)

Every code cell is **preceded** by a markdown cell that explains the *why* (reusing article
prose + fieldkit doc text) and **followed** by an interpreted result. This is a validated
contract the `notebook-author` skill enforces (§9.1).

## 5. Repo layout

```
notebooks/
  <vertical>/                      e.g. patent-strategist/
    builder.py                     jupytext py:percent — SOURCE OF TRUTH (reviewable diff)
    builder.ipynb                  generated, committed (Colab/Kaggle open this)
    user.py
    user.ipynb
    exports/                       snapshot PNGs (tracked, for marketing reuse)
      builder/cell-03-spark-quad.png ...
    requirements.txt               cloud-runtime deps (fieldkit[notebook], llama-cpp-python, ...)
```

Source-of-truth is the `.py` **percent** file (jupytext) for reviewable diffs; the `.ipynb`
is generated and **committed** because Colab opens
`colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/<vertical>/<nb>.ipynb`
directly. A jupytext pre-commit/CI sync keeps the pair consistent. The repo is public, so
GitHub-import works against `main`.

## 6. Dual-path runtime contract

A first **parameterized cell** (papermill `parameters` tag) plus
`fieldkit.notebook.detect_runtime()`:

- `"spark"` → local path: NIM at `127.0.0.1:8000` or `llama-server` / `llama-cpp-python` on a
  local GGUF; full builder steps (quantize, train, thermal probe) run live.
- `"colab"` / `"kaggle"` → cloud fallback: `huggingface_hub` pulls the published GGUF →
  `llama-cpp-python` on the free GPU. Builder cells that need Spark hardware (training,
  thermal probe) render **pre-executed outputs behind a "Spark-only — showing recorded run"
  banner** instead of erroring.

The unified helper `fieldkit.notebook.open_model(hf_repo, variant=...)` returns an object
with a single `.chat(messages)` surface regardless of backend, so the use-case cells are
backend-agnostic.

## 7. Visual system + tooling

Marketing-landing-page quality. Research-backed stack:

| Concern | Choice | Why |
|---|---|---|
| Authoring format | **jupytext** `py:percent` paired notebooks | Reviewable git diffs; commit both `.py` (source) + `.ipynb` (Colab) |
| Charts | **matplotlib** + packaged `orionfold.mplstyle` (composes `dark_background` + brand rcParams); seaborn optional | Static PNGs are snapshot-clean and run on Colab; pixel control |
| Hero tables | **great_tables** ≥0.3.1 (spanner labels, title/subtitle/source-note, **nano-plots** inline bars, `.save()` to PNG) | Publication-grade tables that export directly to image |
| Incidental tables | pandas **Styler** | Lightweight, no extra dep weight |
| Execution | **papermill** / `nbconvert --execute --allow-errors` (nbclient engine) | Parameterized runs; surfaces errors instead of hiding them |
| Snapshot | nbconvert → HTML → **Playwright-MCP** screenshots; great_tables `.save()` / matplotlib `savefig` for direct figure export | webpdf already drives Playwright Chromium; MCP is already in-repo |
| Badges | `colab-badge.svg` + `open-in-kaggle.svg` | Standard, recognizable one-click affordance |

**Branded header banner** at top of each notebook: an HTML/CSS markdown cell using the
ainative dark/OKLCH palette (Geist-ish web-font, sans fallback) carrying title, audience tag,
and the Colab/Kaggle/HF badge row.

**Standard figures** (from `fieldkit.viz`, §8.1): `perplexity_sweep`, `throughput_bars`,
`spark_quad` (the four-axis Spark-tested panel mirroring the HF card), `vertical_eval_bars`,
and a builder-only `train_wall_compare` (e.g. unsloth vs nemo). **Hero table:**
`variants_table` (spanner labels, recommended-variant row highlight, nano-plot inline bars,
source-note crediting the article).

## 8. New fieldkit surface (extractions)

Specified now, **built under the keep-local-until-2nd-reuse discipline**
(`feedback_keep_scorer_local_until_reuse`, `feedback_llm_skill_pattern`). The pilot builds the
genuinely-shared pieces into `fieldkit`; speculative helpers stay in a skill's `scripts/`
until a 2nd vertical reuses them.

### 8.1 `fieldkit.viz` *(build in pilot)*
New module + `fieldkit/docs/api/viz.md`. Branded chart/table builders that consume an
`ArtifactManifest` (or its measurement dicts) and return a matplotlib `Figure` or a
great_tables `GT`. Functions: the standard figures in §7, `variants_table`, and
`save_figure(fig, path, *, scale)`. Ships `fieldkit/assets/orionfold.mplstyle`. Reused by
every vertical, by article figures, and potentially the home-page infographic — clears the
reuse bar on day one.

### 8.2 `fieldkit.notebook` *(build in pilot)*
New module + `fieldkit/docs/api/notebook.md`:
- `detect_runtime() -> "spark" | "colab" | "kaggle" | "local"`
- `open_model(hf_repo, variant=None) -> ChatClient` — unified `.chat()`; local NIM/llama.cpp
  vs cloud `llama-cpp-python`.
- `colab_url(...)` / `kaggle_url(...)` / `badge_markdown(...)` — URL + badge builders.
- `NotebookBuilder` — assemble a `.py` percent **scaffold** from a manifest + article +
  template (deterministic skeleton; prose cells are filled by the session model per §9.1).

### 8.3 `ModelCard.notebooks` + `ArtifactManifest.notebooks` field *(build in pilot)*
`{colab: <url>, kaggle: <url>}`. Rendered as a **badge row directly under the one-liner** in
the HF README (new block in `_render_model_card`), and surfaced in the manifest for Mac to
render badges on artifact cards. **Update `_GUIDES/narrative-contract.md`** to slot the badge row
above-the-fold (after elevator, before/with positioning — it is a navigation aid, not a
claim, so it does not violate "positioning leads").

### 8.4 `fieldkit[notebook]` optional-dependency extra *(build in pilot)*
In `fieldkit/pyproject.toml`: jupytext, papermill, matplotlib, great-tables, jupyterlab,
llama-cpp-python, huggingface_hub.

### 8.5 Promotion-gated (NOT built in pilot — listed so we don't re-derive them)
- **`fieldkit.infer`** — a generic backend abstraction; promote `open_model` here when a
  **2nd non-notebook consumer** needs unified inference.
- **`VerticalCurator`** — a higher-level eval driver over `VerticalBench`; extract when a 2nd
  caller reuses the per-variant matrix loop.
- **`fieldkit.capabilities.sync()`** — promote `scripts/sync_capabilities.py` when an external
  reader needs to keep its copy current.

## 9. Two skills (built via `skill-creator`)

### 9.1 `notebook-author` — sibling to `tech-writer`
SKILL.md instructs Claude (the **session model**) to assemble both notebooks for a vertical
from its manifest + article(s) + fieldkit docs, following a locked cell template and the
visual/narrative contract. Per `feedback_llm_skill_pattern`: **prose/markdown cells are
generated by the session model via Edit-append into the `.py` percent file**; `scripts/` do
**only deterministic transforms** — jupytext convert/sync, badge injection, manifest read,
`NotebookBuilder` scaffold, and validation that every code cell has a preceding explainer +
following interpretation. **Banned:** any `anthropic.Anthropic(api_key=...)` or
`claude-agent-sdk` subprocess.

### 9.2 `notebook-snapshot`
Execute a notebook headless and snapshot it to marketing images. `scripts/` do:
(a) `papermill` / `nbconvert --execute --allow-errors` against a chosen `runtime` param;
(b) `nbconvert --to html`;
(c) drive **Playwright-MCP** to screenshot per-cell + hero regions;
(d) prefer great_tables `.save()` / matplotlib `savefig` for direct high-DPI figure export.
Final PNGs land in `notebooks/<vertical>/exports/` (**tracked** — reused on site/marketing);
execution scratch goes to `/tmp` per `feedback_browser_smoke_snapshots_tmp`. Emits an index
mapping cell → image for downstream reuse.

## 10. Pilot — patent-strategist

Richest vertical: lora + gguf + bench + 4 articles + reasoning chains.

**`builder.ipynb`** — spine = the four articles. Each step is an API call replacing a prior
script: baseline bench (`eval.VerticalBench` + patent rubrics) → corpus prep + gates (the
synth lessons) → backend `training.decide` → `training.run` → reasoning `training.probe` →
`quant.quantize_gguf` → measure (perplexity / tok-s / thermal) → `publish.publish_quant`.
Charts: `train_wall_compare` (unsloth vs nemo), `perplexity_sweep`, `throughput_bars`,
`spark_quad`; great_tables bakeoff measurement table. Feasibility framed with `capabilities`.

**`user.ipynb`** — realistic use cases: claim construction, MPEP-grounded office-action
response, prior-art relevance reasoning, licensing-scenario analysis. Runtime-detected
inference; surface the `<think>` reasoning chains; ground answers with `fieldkit.rag` over
MPEP excerpts; score outputs with `eval` scorers.

## 11. Templatization rule

After the pilot, lock the **vertical template** — the cell skeleton both notebooks follow.
The `notebook-author` skill rolls finance / legal / cyber / medical from it. Those are
GGUF-only verticals, so their builder notebooks use the **quant/publish path only** (no
train/probe) — the template toggles sections by the sibling manifest's `kind`.

## 12. Distribution

- **HF README** — badge row under the one-liner (§8.3), rendered by `ModelCard`. Extend
  `scripts/republish_patent_strategist_readmes.py` for the pilot retro-fit.
- **ainative artifact card** — Mac renders Colab/Kaggle badges from the manifest `notebooks`
  field on the card detail page (destination's `site-rendering-rubric.md` slot mapping).
- **Colab/Kaggle** — badges point at the committed `.ipynb` on `main`.

## 13. Verification

- `fieldkit` tests green incl. new kind + `viz` + `notebook` modules; `fieldkit-curator
  audit-docs` clean for the new modules (manually eyeball kwargs per
  `feedback_audit_docs_kwarg_blind_spot`).
- Astro dev build accepts a `kind: notebook` manifest (no zod error) — load
  `http://localhost:4321/`, vibe-check the card.
- `builder.ipynb` executes clean on Spark via the snapshot skill (`--allow-errors` **surfaces**
  failures, doesn't hide them); `user.ipynb` executes end-to-end on a real Colab/Kaggle free
  runtime.
- Colab/Kaggle badge links resolve to the committed `.ipynb` on `main`.
- Snapshot PNGs land in `notebooks/patent-strategist/exports/` and look marketing-grade
  (vibe-test per `feedback_testing_cadence`, not a formal eval).
- HF READMEs show the badge row above-the-fold; `_GUIDES/narrative-contract.md` updated + consistent.

## 14. Deferred / open

- Kaggle one-click is import-from-GitHub-URL; if we want native Kaggle kernels we later push
  via the `kaggle` CLI and point the badge at the kernel slug. Pilot uses the import URL.
- Whether `fieldkit.viz` should also back the home-page infographic (currently
  `nvidia-learn-stats` → `project-stats.json`) — revisit on 2nd reuse.

## 15. Research sources

- Charts: [matplotlib style sheets & rcParams](https://matplotlib.org/stable/users/explain/customizing.html), [Matplotlib vs Seaborn for scientific plots](https://plotivy.app/blog/matplotlib-vs-seaborn-for-scientific-plots)
- Tables: [great_tables (posit-dev)](https://posit-dev.github.io/great-tables/get-started/), [Level up with Great Tables](https://posit.co/blog/level-up-great-tables), [pandas Styler](https://pandas.pydata.org/docs/user_guide/style.html), [itables](https://github.com/mwouts/itables)
- Execution/snapshot: [papermill](https://github.com/nteract/papermill), [nbconvert usage (webpdf/Playwright)](https://nbconvert.readthedocs.io/en/latest/usage.html)
- Versioning: [jupytext](https://github.com/mwouts/jupytext)
- Badges: [colab-badge-action](https://github.com/trsvchn/colab-badge-action), [OpeninColab-Kaggle](https://github.com/EswarDivi/OpeninColab-Kaggle)
