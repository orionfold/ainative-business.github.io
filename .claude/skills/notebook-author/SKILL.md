---
name: notebook-author
description: Author the builder + user Jupyter notebooks for an Orionfold vertical — the runnable on-ramp that turns an artifact card + article into a one-click Open-in-Colab / Open-in-Kaggle experience. Trigger when the user says "author the notebooks for <vertical>", "build the patent-strategist notebooks", "write the builder/user notebook", "make the runnable notebook for the finance model", "scaffold the colab notebook", invokes /notebook-author, or whenever a vertical model release (a `kind: quant`/`lora` manifest under src/content/artifacts/) needs its companion `notebooks/<vertical>/{builder,user}.ipynb`. Sibling to `tech-writer` (prose articles) and `notebook-snapshot` (execute → marketing images) — this skill owns the *notebook-authoring surface*. The session model writes the prose/markdown cells via Edit into a jupytext `.py` percent file; bundled scripts/ do ONLY deterministic transforms (NotebookBuilder scaffold, jupytext sync, badge inject, explainer→code→interpretation cadence validation). Per `feedback_llm_skill_pattern` it NEVER imports `anthropic` or `claude-agent-sdk` and never shells out to an external `claude`. Do NOT trigger for prose article writing (that's `tech-writer`), for executing/snapshotting an already-authored notebook (that's `notebook-snapshot`), or for general Jupyter questions unrelated to Orionfold artifact notebooks.
---

# notebook-author

Owns the **notebook-authoring surface** for Orionfold artifact verticals. A vertical's loop is `artifact → card → article`; this skill closes it with the missing **runnable on-ramp**: two notebooks per vertical that a reader runs instead of reads.

- **builder notebook** — for the AI researcher/engineer. Walks the build journey as `fieldkit` API calls. Takeaway: **speed** of development with fieldkit, **feasibility** (does it fit the 128 GB Spark envelope?), **viability** (it shipped — live HF artifact + card).
- **user notebook** — for the model consumer / app developer. Walks realistic domain use cases. Takeaway: **desirability** (the model on real tasks, reasoning chains surfaced), **viability** (fieldkit glue makes app-building tractable), **feasibility** (runs on Spark *and* a free Colab/Kaggle GPU).

The governing spec is `_SPECS/notebooks-as-artifacts-v1.md` — read §4 (anatomy), §6 (dual-path runtime), §7 (visual system) before authoring a new vertical.

## Architecture rule — read first

**You (the session model) write the prose. Scripts do deterministic transforms only.**

The markdown explainer + interpretation cells are *writing* — voice, synthesis, a named POV. That is the part a language model is uniquely good at, and the reason this is a skill and not a code generator. The bundled scripts never call a model:

- `scripts/scaffold_notebook.py` — reads the manifest, lays the **structural skeleton** via `fieldkit.notebook.NotebookBuilder` (banner, parameters cell, badge row, code cells with real fieldkit calls, and `TODO(notebook-author)` markers where prose goes). No LLM.
- `scripts/inject_badges.py` — computes the Colab/Kaggle URLs and writes/refreshes the badge row cell. No LLM.
- `scripts/sync_notebook.py` — `jupytext` sync between the `.py` percent (source of truth) and the committed `.ipynb`. No LLM.
- `scripts/validate_cadence.py` — checks every code cell is preceded by an explainer and followed by an interpretation (spec §4.3). No LLM.

If you catch yourself reaching for `anthropic`, `claude_agent_sdk`, or a subprocess to an external `claude` binary — **stop**. The user has banned that path; see `[[feedback_llm_skill_pattern]]`. You generate cells by editing the `.py` file directly in this session.

## Where this slots

```
tech-writer (article)  ─┐
fieldkit.publish (card)─┼─►  notebook-author  ─►  notebook-snapshot  ─►  hf-publisher
artifact manifest      ─┘    (this skill:           (execute → PNGs       (badge row into
                              author .py + .ipynb)    for marketing)        the 4 HF READMEs)
```

## Inputs (resolve these first)

| Input | Where | Notes |
|---|---|---|
| vertical slug | user, e.g. `patent-strategist` | the `notebooks/<vertical>/` directory name |
| artifact manifest | `src/content/artifacts/<model-slug>.yaml` | the **sibling model** manifest (a `quant`/`lora`), NOT a notebook manifest. Source of measurements, positioning, drift, article link. For multi-sibling verticals (Unsloth+NeMo) pick the recommended/lead sibling; cross-link the others. |
| article(s) | `articles/<slug>/article.md` | from the manifest's `article:` field. The prose spine — reuse its framing, don't re-derive. |
| fieldkit docs | `fieldkit/docs/api/{viz,notebook,quant,training,eval,rag}.md` | the API surface the code cells call. |

## Workflow

Default mode authors **both** notebooks. Accept `builder` / `user` to do one.

### 1. Scaffold the skeleton (deterministic)

```bash
FK=/tmp/fk/bin/python   # or any python with fieldkit installed editable
$FK .claude/skills/notebook-author/scripts/scaffold_notebook.py \
  --vertical patent-strategist \
  --manifest src/content/artifacts/patent-strategist-v3-unsloth-gguf.yaml \
  --which both \
  --out notebooks/patent-strategist
```

This writes `notebooks/<vertical>/{builder,user}.py` (jupytext percent) with the locked section structure from `references/cell-template.md`, real fieldkit code cells templated against the manifest, and `# TODO(notebook-author): <what to write>` markers in every prose slot. The script toggles the builder spine by the manifest's `kind`: a `quant`-only vertical (finance/legal/cyber/medical — no training run) gets the quant/publish path; a vertical with a training article (patent-strategist) gets the full baseline→corpus→decide→train→probe→quant→publish spine.

### 2. Write the prose cells (you, in this session)

Open the `.py` file and replace each `TODO(notebook-author)` marker with real prose via Edit. Follow `references/cell-template.md` for what each cell must accomplish and `references/authoring-contract.md` for voice + the visual/narrative contract. The non-negotiable rhythm (spec §4.3): **every code cell is preceded by a markdown cell explaining *why* and followed by one interpreting the *result*.** Treat the notebook as a marketing landing page — lead with the value, show the data, never leave a chart uninterpreted.

Do NOT hand-edit the `.ipynb` — it is generated. Edit the `.py`.

### 3. Inject badges + sync (deterministic)

```bash
$FK .claude/skills/notebook-author/scripts/inject_badges.py --vertical patent-strategist --out notebooks/patent-strategist
$FK .claude/skills/notebook-author/scripts/sync_notebook.py --out notebooks/patent-strategist --which both
```

`inject_badges.py` writes the Colab/Kaggle badge row (each notebook links to itself + cross-links its sibling). `sync_notebook.py` runs `jupytext --sync` so the committed `.ipynb` matches the `.py`. Commit **both** files — Colab opens the `.ipynb` from `main`.

### 4. Validate the cadence (deterministic, blocking)

```bash
$FK .claude/skills/notebook-author/scripts/validate_cadence.py --out notebooks/patent-strategist --which both
```

Fails (non-zero) if any code cell lacks a preceding explainer or following interpretation, or if any `TODO(notebook-author)` marker survives. Fix the `.py`, re-sync, re-validate. Green here is the gate before handoff.

### 5. Hand off to `notebook-snapshot`

Tell the user the notebooks are authored and point them at `notebook-snapshot` to execute + capture marketing images, then `hf-publisher` to inject the badge row into the model's HF README (the manifest's `notebooks` field carries the URLs).

## Templatize across verticals

After the patent-strategist pilot, the cell skeleton in `references/cell-template.md` IS the template. Rolling finance/legal/cyber/medical is steps 1–5 again with their manifest — the scaffold toggles the builder spine by `kind`, so GGUF-only verticals skip the train/probe cells automatically. Keep per-vertical specifics (use cases, drift, domain RAG corpus) sourced from the manifest + article, not hard-coded.

## Reference files

- `references/cell-template.md` — the locked builder + user cell skeletons (what each cell accomplishes). Read before authoring.
- `references/authoring-contract.md` — voice, the marketing-landing-page mandate, and the visual/narrative contract pointers (`_GUIDES/NARRATIVE-CONTRACT.md`, `fieldkit.viz` figures, dual-path runtime banners).
