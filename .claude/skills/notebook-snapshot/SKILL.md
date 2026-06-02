---
name: notebook-snapshot
description: Execute an Orionfold artifact notebook headless and capture it as marketing-grade images — the runnable notebook becomes a set of PNGs reused across the website, HF cards, and social. Trigger when the user says "snapshot the notebook", "capture the patent-strategist notebook", "run and screenshot the builder/user notebook", "export the notebook figures", "make marketing images from the notebook", invokes /notebook-snapshot, or right after `notebook-author` finishes a vertical's notebooks and the natural next step is producing the executed-cell images. Sibling to `notebook-author` (writes the notebooks) and `tech-writer` (prose) — this skill owns the *notebook-snapshot surface*. Bundled scripts/ do the deterministic parts (papermill/nbconvert execute with `--allow-errors`, nbconvert→HTML, headless high-DPI matplotlib hero export via `fieldkit.viz`); the session drives Playwright-MCP for the great_tables hero table + narrative-cell screenshots. Final PNGs land in `notebooks/<vertical>/exports/` (tracked); execution scratch goes to /tmp. Do NOT trigger for authoring/writing notebook cells (that's `notebook-author`), for article screenshots (that's `tech-writer`), or for general notebook-execution questions unrelated to Orionfold artifact notebooks.
---

# notebook-snapshot

Owns the **notebook-snapshot surface**: take an authored Orionfold notebook,
run it, and turn it into reusable marketing images. The notebooks are landing
pages; this skill harvests the rendered cells (charts, hero table, branded
banner, reasoning chains) as PNGs the website and HF cards reuse — so the asset
is the deterministic output of an actual executed run, not a mockup.

Governing spec: `_SPECS/notebooks-as-artifacts-v1.md` §9.2 + §7 (visual system).

## Output layout

```
notebooks/<vertical>/exports/        TRACKED — reused on site / cards / social
  builder/spark-quad.png
  builder/variants-table.png
  builder/cell-07-train-wall.png ...
  user/banner.png ...
  index.json                          cell/figure → image map for downstream reuse
```

Execution scratch (the executed `.ipynb`, the HTML) goes to `/tmp/aifn-nb-snapshot/`
per `feedback_browser_smoke_snapshots_tmp` — never the repo. Only the final
marketing PNGs are tracked.

## Two capture paths — pick per artifact

1. **Headless matplotlib heroes (deterministic, preferred for charts).** The
   `fieldkit.viz` matplotlib figures (`spark_quad`, `perplexity_sweep`,
   `throughput_bars`, `vertical_eval_bars`, `train_wall_compare`) export
   directly via `viz.save_figure` on the Agg backend — high-DPI, no browser, no
   chrome. `export_figures.py` does this from the manifest. These are the money
   shots; always export them.
2. **Playwright-MCP over rendered HTML (session-driven, for everything else).**
   The great_tables hero table renders to HTML but its `.save()` needs
   selenium+chromium, so capture it (and the branded banner + key reasoning
   cells) by screenshotting the nbconvert HTML with the in-session
   `mcp__playwright__*` tools. A bash script can't call MCP — *you* drive it.

## Workflow

```bash
FK=/tmp/fk/bin/python
SK=.claude/skills/notebook-snapshot/scripts
V=patent-strategist
NB=notebooks/$V
MANIFEST=src/content/artifacts/patent-strategist-v3-unsloth-gguf.yaml
```

### 1. Execute (deterministic; surfaces errors, doesn't hide them)

```bash
$FK $SK/execute_notebook.py --notebook $NB/user.ipynb --runtime spark
# → /tmp/aifn-nb-snapshot/<vertical>/user.executed.ipynb
```

`--allow-errors` is on by design (spec §13): a failing cell shows its traceback
in the output instead of aborting the run, so the snapshot tells the truth. On
Spark run builder with `--runtime spark`; the user notebook runs anywhere. The
cloud (`colab`/`kaggle`) path can't be exercised locally — capture it from a
real free runtime when validating that path, per spec §13.

### 2. Export the matplotlib heroes (deterministic)

```bash
$FK $SK/export_figures.py --manifest $MANIFEST --which builder --out $NB/exports/builder
$FK $SK/export_figures.py --manifest $MANIFEST --which user   --out $NB/exports/user
```

Writes `spark-quad.png` + the single-axis charts (and `train-wall.png` for the
builder when `--wall unsloth=NN,nemo=NN` is passed) at 2× DPI.

### 3. Convert to HTML for Playwright (deterministic)

```bash
$FK $SK/notebook_to_html.py --executed /tmp/aifn-nb-snapshot/$V/user.executed.ipynb \
  --out /tmp/aifn-nb-snapshot/$V/user.html
```

### 4. Screenshot banner + hero table + reasoning cells (you, via Playwright-MCP)

Open the HTML and capture the regions the matplotlib export can't:

- `mcp__playwright__browser_navigate` → `file:///tmp/aifn-nb-snapshot/<v>/user.html`
- `mcp__playwright__browser_snapshot` to get the accessibility tree + element refs
- `mcp__playwright__browser_take_screenshot` with an element `ref` for: the
  **branded banner** (top cell), the **great_tables variants table** (the hero
  table — find the `<table>` inside the great_tables wrapper), and any **`<think>`
  reasoning-chain** output worth showing. Save each into
  `notebooks/<vertical>/exports/<which>/<label>.png` (tracked).

Set a wide viewport first (`mcp__playwright__browser_resize` ~1400×900) so the
banner and table aren't cramped. These PNGs are marketing assets → they go in
`exports/`, not /tmp.

### 5. Build the index (deterministic)

```bash
$FK $SK/build_index.py --out $NB/exports
# → notebooks/<vertical>/exports/index.json  (label → relative image path)
```

### 6. Report + hand off

Report which images landed and vibe-check them (per `feedback_testing_cadence`,
eyeball — not a pixel diff). Hand off to `hf-publisher` to inject the badge row
into the model's HF README, and note the `exports/` PNGs are ready for the Mac
sync to pick up for the ainative card + site.

## Notes

- **`--allow-errors` surfaces, never hides.** If a cell errors, that traceback
  is part of the snapshot — fix the notebook (via `notebook-author`) and re-run,
  don't paper over it.
- **Heroes from the manifest, not the run.** `export_figures.py` reads the
  manifest so the charts are reproducible without a successful end-to-end
  execution — handy when a hardware-only builder step is recorded, not live.
- **Deterministic scripts never call a model.** This skill renders and captures;
  it does not author. Authoring is `notebook-author`.
