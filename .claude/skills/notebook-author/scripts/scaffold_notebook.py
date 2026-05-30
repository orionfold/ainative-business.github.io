#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Scaffold the builder/user notebook skeleton for an Orionfold vertical.

DETERMINISTIC ONLY — no LLM call. Reads the sibling-model artifact manifest,
lays the locked cell structure via `fieldkit.notebook.NotebookBuilder` (banner,
parameters cell, badge placeholder, real fieldkit code cells, and
`TODO(notebook-author): ...` markers in every prose slot), and writes the
jupytext `.py` percent files. The session model fills the prose; the
`notebook-author` skill never generates cells from a script.

Usage:
    scaffold_notebook.py --vertical patent-strategist \
        --manifest src/content/artifacts/patent-strategist-v3-unsloth-gguf.yaml \
        --which both --out notebooks/patent-strategist [--builder-spine full|quant]

`--builder-spine` defaults to `full` for `kind: lora` manifests and `quant`
otherwise; pass it explicitly when a `quant` manifest was nonetheless trained
(e.g. patent-strategist's lead GGUF sibling → `--builder-spine full`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# Make fieldkit importable when run from the repo without an install.
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "fieldkit" / "src"))
from fieldkit.notebook import NotebookBuilder  # noqa: E402

TODO = "TODO(notebook-author):"


def load_manifest(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"manifest {path} did not parse to a mapping")
    return data


def _todo(what: str) -> str:
    return f"{TODO} {what}"


# --- builder notebook ------------------------------------------------------


def build_builder(m: dict, vertical: str, spine: str) -> NotebookBuilder:
    hf_repo = m.get("hf_repo", f"Orionfold/{vertical}")
    base = m.get("base_model", "<base-model>")
    slug = m.get("slug", vertical)
    eval_name = m.get("vertical_eval_name") or f"{vertical} bench"
    b = NotebookBuilder(
        vertical=vertical, audience="AI researcher / engineer",
        title=f"Build {vertical} on a Spark with fieldkit",
    )
    b.parameters_cell({"hf_repo": hf_repo, "base_model": base, "vertical_slug": slug})
    b.markdown(_todo(
        "Intro. The thesis: this build used to be N hand-rolled scripts; "
        "fieldkit collapses them into a handful of typed API calls. Frame the "
        "three takeaways — SPEED (fewer calls), FEASIBILITY (fits 128 GB), "
        "VIABILITY (it shipped). Reuse the article's framing; don't re-derive."))
    b.markdown(_todo("Explain the setup cell: install fieldkit[notebook] + imports."))
    b.code(
        "%pip install -q 'fieldkit[notebook]'\n"
        "import fieldkit\n"
        "from fieldkit import capabilities, viz\n"
        "print('fieldkit', fieldkit.__version__)")
    b.markdown(_todo(
        "Feasibility framing. Use capabilities to answer: does this model + "
        "training fit the Spark's 128 GB unified-memory envelope? Interpret the "
        "number — this is the FEASIBILITY axis."))
    b.code(
        "env = capabilities.practical_inference_envelope(base_model)\n"
        "env  # what fits on a single GB10")

    if spine == "full":
        b.step(
            _todo("Explain the baseline bench — score the BASE model on the "
                  "vertical rubric before any training, so the gain is measured."),
            "from fieldkit import eval as fkeval\n"
            f"# bench = fkeval.VerticalBench.load('{slug}')\n"
            "# baseline = bench.score(base_model)\n"
            f"# {TODO} wire to the real VerticalBench for this vertical\n"
            "baseline = None  # replace with bench.score(...)",
            _todo("Interpret the baseline — where does the base model fall short "
                  "on this vertical? This is the gap training closes."))
        b.step(
            _todo("Explain corpus prep + the synth gates (reuse the data-prep "
                  "article's lessons — leakage gates, pigeon-hole check)."),
            f"# {TODO} corpus prep: point at the prepared training corpus / "
            "claude-corpus-synth output for this vertical\n"
            "corpus_path = '<path-to-corpus.jsonl>'",
            _todo("Interpret the corpus shape — row count, family distribution, "
                  "what the gates caught."))
        b.step(
            _todo("Explain the backend decision — training.decide picks Unsloth "
                  "vs NeMo for this shape. Name WHY the recommended lane won."),
            "from fieldkit import training\n"
            "decision = training.decide.train_backend(base_model)\n"
            "decision",
            _todo("Interpret the decision — which lane, and the trade-off it "
                  "encodes (dev velocity vs chain quality vs wall)."))
        b.step(
            _todo("Explain the training run — one fieldkit call replaces the "
                  "shell-script lane. This is the SPEED axis made concrete."),
            f"# {TODO} training.run(recipe) — show the recipe construction + run\n"
            "# recipe = training.TrainRecipe(...)\n"
            "# run = training.run(recipe)\n"
            "run = None  # replace with the real run",
            _todo("Interpret the run — wall-clock, peak memory, where it landed."))
        b.step(
            _todo("Explain the reasoning probe — budget-normalized so the "
                  "comparison is apples-to-apples (the bakeoff's key fix)."),
            f"# {TODO} training.probe the merged checkpoint\n"
            "# probe = training.ReasoningProbe(...).run(merged_ckpt)\n"
            "probe = None",
            _todo("Interpret the probe — chain quality, drift caught, vs baseline."))

    # Quant + measure + publish — every vertical (the quant-only spine starts here).
    b.step(
        _todo("Explain the quantize step — one call emits every GGUF variant "
              "from the merged/base checkpoint."),
        "from fieldkit import quant\n"
        f"# {TODO} quant.quantize_gguf(model=..., outdir=...) → QuantReport\n"
        "# report = quant.quantize_gguf(model='<merged-or-base>', outdir='/data/quants/...')\n"
        "report = None  # replace with the real QuantReport",
        _todo("Interpret the variants — sizes produced, what each is for."))
    b.step(
        _todo("Explain the measurement — perplexity / tok-s / thermal on Spark. "
              "Then render the four-axis Spark-tested panel from the manifest."),
        "import yaml\n"
        f"manifest = yaml.safe_load(open('src/content/artifacts/{slug}.yaml'))\n"
        "from types import SimpleNamespace\n"
        "mf = SimpleNamespace(**manifest)\n"
        "fig = viz.spark_quad(mf)\n"
        "fig",
        _todo(f"Interpret the quad — the sweet-spot variant "
              f"({m.get('recommended_variant', '<recommended>')}) and why; "
              f"tie tok/s back to FEASIBILITY."))
    b.step(
        _todo("Explain the hero table — the per-variant matrix readers screenshot."),
        "viz.variants_table(mf)",
        _todo("Interpret the table — recommended row, the trade it represents."))
    if spine == "full":
        b.step(
            _todo("Explain the train-wall comparison (Unsloth vs NeMo) — the "
                  "bakeoff's headline chart."),
            f"# {TODO} fill measured wall-clock per lane\n"
            "viz.train_wall_compare({'unsloth': 0.0, 'nemo': 0.0}, "
            "title='Training wall — Unsloth vs NeMo')",
            _todo("Interpret — which lane was faster and by how much."))
    b.step(
        _todo("Explain the publish step — publish_quant renders the card + "
              "manifest + pushes. Keep dry_run=True in the notebook."),
        "from fieldkit import publish\n"
        f"# {TODO} publish.publish_quant(quant_report=report, base_model=base_model,\n"
        f"#   repo_name='{hf_repo.split('/')[-1]}', staging_dir='/tmp/stage', dry_run=True)\n"
        "result = None",
        _todo("Interpret — the card shape, the manifest written, the dry-run set."))
    b.markdown(_todo(
        f"VIABILITY close. It shipped: link the live artifact "
        f"(https://huggingface.co/{hf_repo}) and the published card "
        f"(https://ainative.business/field-notes/{(m.get('article') or '').strip('/').split('/')[-1]}/). "
        "End on the speed/feasibility/viability through-line."))
    # Banner is inserted as the first cell — it is the markdown that precedes
    # (and so satisfies the cadence for) the parameters cell.
    b.header_banner(subtitle="Walk the build journey as fieldkit API calls — on a Spark.")
    return b


# --- user notebook ---------------------------------------------------------


def build_user(m: dict, vertical: str) -> NotebookBuilder:
    hf_repo = m.get("hf_repo", f"Orionfold/{vertical}")
    pos = m.get("positioning", {}) or {}
    use_cases = pos.get("use_cases", []) or [_todo("define a realistic use case")]
    b = NotebookBuilder(
        vertical=vertical, audience="App developer / model consumer",
        title=f"Use {vertical} in your app",
    )
    b.parameters_cell({"hf_repo": hf_repo})
    b.markdown(_todo(
        "Intro. Frame the three takeaways — DESIRABILITY (the model on real "
        "tasks), VIABILITY (fieldkit glue makes app-building tractable), "
        "FEASIBILITY (runs on Spark AND a free Colab/Kaggle GPU). Pull the "
        "audience + problem from the manifest positioning."))
    b.markdown(_todo("Explain setup + the dual-path note: same code runs locally "
                     "on Spark and on a free cloud GPU."))
    b.code(
        "%pip install -q 'fieldkit[notebook]'\n"
        "from fieldkit.notebook import open_model, detect_runtime, is_cloud\n"
        "RUNTIME = detect_runtime()\n"
        "print('runtime:', RUNTIME)")
    b.markdown(_todo(
        "Explain open_model — one call, backend chosen by runtime. On Spark it "
        "serves locally; on Colab/Kaggle it pulls the published GGUF. This is "
        "the FEASIBILITY axis."))
    b.code(
        "client = open_model(hf_repo)   # variant auto-picked: Q4_K_M on cloud, Q5_K_M on Spark\n"
        "client")
    for i, uc in enumerate(use_cases, start=1):
        b.step(
            _todo(f"Use case {i}: '{uc}'. Explain the realistic task + why it "
                  "matters to the audience. Show a concrete domain prompt."),
            "messages = [\n"
            f"    {{'role': 'user', 'content': {_short(uc)!r}}},  # {TODO} real domain prompt\n"
            "]\n"
            "reply = client.chat(messages, max_tokens=2048)\n"
            "print(reply)",
            _todo("Interpret the answer. If the model is a reasoner, surface the "
                  "<think> chain and explain what good reasoning looks like here. "
                  "This is the DESIRABILITY axis."))
    b.step(
        _todo("Explain RAG grounding — fieldkit.rag over a domain corpus so "
              "answers cite real sources. This is the VIABILITY axis (glue)."),
        "from fieldkit import rag\n"
        f"# {TODO} ground answers over a small domain corpus (e.g. MPEP excerpts)\n"
        "# store = rag.ingest([...]); ctx = store.retrieve(query)\n"
        "ctx = None",
        _todo("Interpret — how grounding changed the answer; the citation."))
    b.step(
        _todo("Explain eval scoring — score the output with a fieldkit.eval "
              "scorer so the app has a quality gate."),
        "from fieldkit import eval as fkeval\n"
        f"# {TODO} score the reply with the right scorer for this vertical\n"
        "score = None",
        _todo("Interpret the score — what passing means for the app."))
    b.markdown(_todo(
        "Close. Restate desirability/viability/feasibility. Link the model card "
        f"(https://huggingface.co/{hf_repo}) and the builder notebook for "
        "readers who want to reproduce the build."))
    b.header_banner(subtitle="Call the model on real tasks — runs on Spark and a free cloud GPU.")
    return b


def _short(text: str, n: int = 90) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[: n - 1] + "…"


# --- driver ----------------------------------------------------------------


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vertical", required=True)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--which", choices=["builder", "user", "both"], default="both")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--builder-spine", choices=["full", "quant"], default=None)
    args = ap.parse_args(argv)

    m = load_manifest(args.manifest)
    spine = args.builder_spine or ("full" if m.get("kind") == "lora" else "quant")
    args.out.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    if args.which in ("builder", "both"):
        p = build_builder(m, args.vertical, spine).write_py(args.out / "builder.py")
        written.append(f"{p}  (spine={spine})")
    if args.which in ("user", "both"):
        p = build_user(m, args.vertical).write_py(args.out / "user.py")
        written.append(str(p))

    print("scaffolded:")
    for w in written:
        print("  -", w)
    print(f"\nNext: fill every '{TODO}' marker via Edit, then inject_badges.py + "
          "sync_notebook.py + validate_cadence.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
