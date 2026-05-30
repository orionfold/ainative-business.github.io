# Locked cell template — builder + user notebooks

The skeleton `scaffold_notebook.py` lays down and you fill. Each entry says
what the cell must *accomplish*; the script supplies real fieldkit code and a
`TODO(notebook-author):` marker in every prose slot. The rhythm is invariant:
**markdown explainer → code → markdown interpretation** (spec §4.3). Never
ship a code cell without the bracketing prose; `validate_cadence.py` enforces it.

## Contents
- [Shared top matter](#shared-top-matter)
- [Builder notebook spine](#builder-notebook-spine)
- [User notebook spine](#user-notebook-spine)
- [Per-`kind` toggle](#per-kind-toggle)

## Shared top matter

1. **Banner** (markdown, branded HTML) — title + audience tag. From
   `NotebookBuilder.header_banner`. No blank lines inside the HTML block
   (markdown breaks out of HTML on a blank line — `feedback_fn_diagram_no_blank_lines`).
2. **Parameters cell** (code, `parameters` tag) — `runtime`, `hf_repo`, etc.
   papermill overrides these; Colab shows them as a form.
3. **Badge row** (markdown, `badges` tag) — Open-in-Colab / Open-in-Kaggle for
   both notebooks + the HF model. Written by `inject_badges.py`, not by hand.
4. **Intro** (markdown) — the thesis + the three takeaway axes (below). This is
   the landing-page hero: lead with the value, not the setup.

## Builder notebook spine

Audience: **AI researcher / engineer.** Three axes to land:
**SPEED** (N scripts → a handful of typed calls), **FEASIBILITY** (fits the
128 GB Spark envelope — frame with `capabilities`), **VIABILITY** (it shipped).

| Step | Code does | Prose must |
|---|---|---|
| Setup | install `fieldkit[notebook]`, imports | say what we're standing up |
| Feasibility | `capabilities.practical_inference_envelope(base)` | interpret the envelope (FEASIBILITY) |
| Baseline bench *(full spine)* | `eval.VerticalBench` scores the base | name the gap training closes |
| Corpus + gates *(full)* | point at the prepared corpus | shape, family mix, what gates caught |
| Backend decide *(full)* | `training.decide.train_backend` | which lane won + the trade-off |
| Train *(full)* | `training.run(recipe)` | wall, peak mem, where it landed (SPEED) |
| Probe *(full)* | `training.ReasoningProbe` (budget-normalized) | chain quality, drift, vs baseline |
| Quantize | `quant.quantize_gguf` → `QuantReport` | the variants + what each is for |
| Measure | `viz.spark_quad(manifest)` | the sweet-spot variant + why (FEASIBILITY) |
| Hero table | `viz.variants_table(manifest)` | the recommended row + the trade |
| Wall compare *(full)* | `viz.train_wall_compare({...})` | which lane was faster, by how much |
| Publish | `publish.publish_quant(..., dry_run=True)` | the card/manifest shape, the dry-run set |
| Close | — | VIABILITY: live HF artifact + published card links |

## User notebook spine

Audience: **app developer / model consumer.** Three axes:
**DESIRABILITY** (the model on real tasks, reasoning chains surfaced),
**VIABILITY** (fieldkit glue makes app-building tractable), **FEASIBILITY**
(runs on Spark *and* a free Colab/Kaggle GPU).

| Step | Code does | Prose must |
|---|---|---|
| Setup | install + `detect_runtime()` | the dual-path note (same code, two runtimes) |
| Open model | `open_model(hf_repo)` (variant auto-picked) | one call, backend by runtime (FEASIBILITY) |
| Use case 1..N | `client.chat(messages)` per `positioning.use_cases` | the realistic task + surface the `<think>` chain (DESIRABILITY) |
| RAG grounding | `fieldkit.rag` over a domain corpus | how grounding changed the answer (VIABILITY) |
| Eval scoring | a `fieldkit.eval` scorer | what passing means for the app |
| Close | — | restate the three axes; link card + builder notebook |

Use cases come from the manifest's `positioning.use_cases` — one `step()` each.
For patent-strategist that's claim construction, MPEP-grounded office-action
drafting, prior-art relevance reasoning, licensing-scenario analysis.

## Per-`kind` toggle

`scaffold_notebook.py --builder-spine`:

- **`full`** (trained verticals, e.g. patent-strategist) — the whole
  baseline→corpus→decide→train→probe→quant→publish spine + the wall-compare chart.
- **`quant`** (GGUF-only verticals — finance / legal / cyber / medical, built
  from instruction-pretrain bases with no training run) — the quant/publish
  path only. The train/probe/wall cells are omitted.

Default: `full` for `kind: lora`, `quant` otherwise. patent-strategist's lead
sibling is a `quant` manifest that *was* trained, so pass `--builder-spine full`.
