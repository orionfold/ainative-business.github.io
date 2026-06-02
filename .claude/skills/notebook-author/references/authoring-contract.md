# Authoring contract — voice + the visual / narrative rules

A notebook is a **marketing landing page that happens to run**. The reader
should feel the value before they hit a single line of setup, and never meet a
chart or output without a sentence telling them what it means. These are the
rules the prose you write must honor.

## Voice

Inherit the blog's deep-dive-essayist voice — the same one `tech-writer` uses.
Read `.claude/skills/tech-writer/references/voice-and-style.md` if you need to
recalibrate. In short:

- **Named POV, not cookbook.** "Here's what I found running this on one Spark"
  beats "Step 3: run the command." The blog's value over NVIDIA's docs is
  synthesis from one power-user's journey.
- **Earn each sentence.** Every markdown cell should change what the reader
  knows or can do next. Cut throat-clearing.
- **Tie back to the uber-theme** — DGX Spark as personal AI power user / edge AI
  builder. The notebook is the most direct expression of it: you don't read the
  journey, you run it.
- **Customer-POV on the user notebook.** It's linked from the model's HF card,
  so it's customer-facing: no strategy leak, no competitor punches, no
  failure-narrative front-loading (`feedback_customer_link_audit`). The builder
  notebook is more internal/method-facing but still ships current truth only.

## The narrative contract still applies

The notebook surfaces the same artifact as the card and the article, so
`/_GUIDES/NARRATIVE-CONTRACT.md` governs it too:

- **Positioning leads.** The intro cell is positioning — problem, who it's for,
  the value. Measurements come after. (The badge row is the one thing above
  positioning, because it's a runnable link, not a claim — Rule 8.)
- **Drift is bounded and never above-the-fold.** If you mention a model's known
  drift in the user notebook, quote the bound from the manifest's `known_drift`
  (e.g. "~99% of probe answers cite real MPEP sections") and put it late, not
  in the hero.
- **No forward-looking roadmap.** No "v4 will fix," no "coming soon." Ship what
  runs today.
- **Wire back to Methods.** Link the field-notes article (the manifest's
  `article:`) — the artifact is the deliverable, the article is the receipt.

## Visual system

Charts and tables come from `fieldkit.viz` (read `fieldkit/docs/api/viz.md`),
fed the artifact manifest so they're the deterministic output of the measured
run, branded, and stack-colored:

- `viz.spark_quad(manifest)` — the four-axis Spark-tested panel (perplexity,
  throughput, vertical accuracy, thermal). The signature figure.
- `viz.variants_table(manifest)` — the great_tables hero table readers
  screenshot. Recommended row highlighted, nano-plot inline bars.
- `viz.perplexity_sweep` / `throughput_bars` / `vertical_eval_bars` — single
  panels when you want one axis at a time.
- `viz.train_wall_compare({...})` — builder-only, the bakeoff lane comparison.

Don't hand-roll matplotlib or paste stock images. Data-driven visuals are the
moat (NARRATIVE-CONTRACT Rule 7) — anyone can clone the README; only Orionfold
has the per-artifact Spark-measured data the figure is built from.

## Dual-path runtime

The notebook must run on Spark **and** a free Colab/Kaggle GPU
(`_SPECS/notebooks-as-artifacts-v1.md` §6). `fieldkit.notebook.detect_runtime()`
+ `open_model(hf_repo)` handle the inference split for you. For builder cells
that genuinely need Spark hardware (training, thermal probe), do NOT let them
error on cloud — show the recorded output behind a banner:

> **🖥️ Spark-only step — showing a recorded run.** Training ran on a DGX Spark
> (GB10, 128 GB unified memory). On Colab/Kaggle this cell loads the published
> result instead of re-running.

Write that banner as the explainer markdown above the cell, and have the code
branch on `is_cloud(RUNTIME)` to load a recorded artifact rather than execute.
