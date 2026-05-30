# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.3
#   kernelspec:
#     display_name: Python 3
#     name: python3
# ---

# %% [markdown] tags=["banner"]
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Build patent-strategist on a Spark with fieldkit</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">AI researcher / engineer</div><div style="color:#C2C9D4;margin-top:0.5rem">Walk the build journey as fieldkit API calls — on a Spark.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/patent-strategist-v3-nemo-GGUF'
base_model = 'deepseek-ai/DeepSeek-R1-0528-Qwen3-8B'
vertical_slug = 'patent-strategist-v3-nemo-gguf'

import os
if runtime != "auto":
    os.environ["FIELDKIT_RUNTIME"] = runtime
from fieldkit.notebook import detect_runtime
RUNTIME = detect_runtime()
print(f"runtime: {RUNTIME}")

# %% [markdown] tags=["badges"]
# **Build it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/patent-strategist/builder.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/patent-strategist/builder.ipynb)
#
# **Use it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/patent-strategist/user.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/patent-strategist/user.ipynb)
#
# **Model:** [![Hugging Face](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/Orionfold/patent-strategist-v3-nemo-GGUF)

# %% [markdown]
# ## You built a patent reasoner on one desk. Here's the receipt.
#
# `patent-strategist-v3` is a DeepSeek-R1 reasoning model distilled onto 5,000 rows of
# synthetic patent-prosecution chains so a single Spark-class box can do claim construction,
# MPEP-grounded office-action drafting, and prior-art reasoning **offline** — no privileged
# client text leaving the building. This notebook is the build, not the writeup. Every step
# below was a hand-rolled script in the original session; here each one is a typed
# `fieldkit` call you can run.
#
# Three things this notebook proves, in order:
#
# - **Speed** — the journey from "I have a JSONL" to "I have a live HF artifact + a published
#   card" collapses from a folder of one-off scripts into roughly a dozen `fieldkit` calls.
# - **Feasibility** — every heavy step is framed against the GB10's 128 GB unified-memory
#   envelope. An 8B reasoner trains, quantizes, and serves with room to spare.
# - **Viability** — it shipped. The last cell links the live NeMo-lane repos under the
#   `Orionfold` handle and the deep-dive that is this build's receipt.
#
# The full story lives in the field-notes bakeoff article; this is the runnable spine of it.

# %% [markdown]
# ### Setup
#
# One install pulls `fieldkit` plus its notebook extra (matplotlib, great_tables, jupytext,
# the inference glue). `capabilities` answers feasibility questions with arithmetic; `viz`
# turns the measured run into the same branded charts the HF card uses.

# %%
# %pip install -q 'fieldkit[notebook]'
import fieldkit
from fieldkit import capabilities, viz
print('fieldkit', fieldkit.__version__)

# %% [markdown]
# ### Does it even fit? — the feasibility question, answered first
#
# Before committing an overnight to a fine-tune, you want to know the model fits the box you
# have. `capabilities.practical_inference_envelope` is the rule-of-thumb lookup: for an 8B
# model in bf16 it returns the weights + KV-cache footprint and a measured throughput, keyed
# off the same memory-budget table the rest of fieldkit reasons about. This is the FEASIBILITY
# axis — everything downstream lives inside this envelope.

# %%
env = capabilities.practical_inference_envelope("8B params bf16")
env  # what fits on a single GB10

# %% [markdown]
# **~16 GB of weights + KV against a 128 GB unified-memory budget — "fits with room."** That
# headroom is the whole reason the build, the quantize sweep, and the live serving all happen
# on the same desk. The 8B reasoner never flirts with the
# [unified-memory OOM landmine](https://ainative.business/field-notes/derisk-cloud-pretraining-on-the-spark/)
# at ~110 GiB; the run below finishes with 92 GiB still free.

# %% [markdown]
# ### Baseline first — measure the gap before you close it
#
# 🖥️ **Spark-only step — showing the recorded run from this build's evaluation session.**
#
# You cannot claim a training gain you never baselined. Before any fine-tune, the base
# `DeepSeek-R1-0528-Qwen3-8B` was scored on the `patent-strategist` bench — 200 hand-anchored
# rows across seven question shapes — under three context modes (closed-book, retrieval,
# oracle) to bracket what the model already knew versus what retrieval could lift. The
# numbers below are the D-mcq accuracy from that bracket; in a fresh `fieldkit.eval` run
# they come from `VerticalBench.score(...)`.

# %%
from fieldkit import eval as fkeval
# Recorded baseline of the BASE model on the patent bench (pre-fine-tune),
# from the three-mode bracket in the v1 baseline article.
baseline = {
    "bench": "patent-strategist-v0.1 (200 rows, 7 shapes)",
    "d_mcq_closed_book": 0.625,   # pure parametric knowledge — the floor
    "d_mcq_retrieval": 0.85,      # + top-8 MPEP/BigPatent/PatentMatch chunks
    "d_mcq_oracle": 0.95,         # + the gold passage — the ceiling
}
baseline

# %% [markdown]
# **The closed-book floor is 0.625 and the oracle ceiling is 0.95** — the base model knows a
# fair amount of patent law but leaves a real gap, and the closed-to-retrieval lift (0.625 →
# 0.85) is 2.25× the retrieval-to-oracle gap. That gap on parametric reasoning — what the
# model can do with *no* context, the offline case that matters for privileged work — is what
# the fine-tune sets out to close.

# %% [markdown]
# ### The corpus — and the gates that kept it honest
#
# The training signal is 5,000 synthetic patent-reasoning rows, each an IRAC-shaped
# `<think>` chain over an anchored patent scenario. Synthetic corpora rot in specific,
# detectable ways, so the build runs them through deterministic gates before training: a
# leakage sweep that strips producer working-notes and `R<digits>` row-references out of the
# reasoning chain, a SPICE pigeon-hole check that catches prompt-template saturation, and a
# `split_think` completeness check so no row ships with an empty chain or a bare `<think>`
# opener. Those gates are the difference between a corpus that teaches reasoning and one that
# teaches a leak.

# %%
# The prepared corpus + the recorded shape after the synth gates ran.
corpus_path = '/home/nvidia/data/aifn-corpus-v3/patent-strategist-5000.jsonl'
corpus = {
    "rows": 5000,
    "shape": "IRAC <think>chain</think>answer over anchored patent scenarios",
    "gates_applied": ["meta-state strip", "R<digits> row-ref strip",
                      "SPICE pigeon-hole", "split_think completeness"],
}
corpus

# %% [markdown]
# **5,000 clean rows after the gates.** The gates are not decoration: an earlier corpus
# version leaked producer-state into 56% of chains and `R<digits>` references into another
# fraction before the regexes were tightened — caught at chunk-write time, never reaching the
# trainer. The full forensics live in the
# [data-prep article](https://ainative.business/field-notes/fine-tune-data-prep-decisions-on-spark/).

# %% [markdown]
# ### Which trainer? — let the decision tool answer
#
# Two LoRA lanes work on the Spark: Unsloth and NeMo Framework (Megatron-Bridge). Rather than
# relitigate the choice every session, the bakeoff's findings are encoded as a `decide` entry
# `fieldkit.training.decide.train_backend` reads. Ask it for a `(base_model_family,
# optimize_for)` cell and it returns the lane the measured evidence picked — with the evidence
# string attached.

# %%
from fieldkit import training
decision = training.decide.train_backend(
    base_model_family="qwen3-r1-distill", optimize_for="wall_clock")
decision

# %% [markdown]
# **For wall-clock, the tool picks NeMo** — 5h 38m vs Unsloth's 7h 34m on the identical 5k
# corpus. The same entry picks NeMo for chain length (+44%) and perplexity (~1 unit lower at
# every quant); Unsloth still wins dev velocity (~4× faster rebuild/smoke loop) and 4-bit QLoRA
# support, so it stays the lane for fast inner-loop iteration. But every axis that decides what
# *ships* — wall, perplexity, chain length — points to NeMo, so the **NeMo lane is the published
# flagship**. This notebook follows that lane end-to-end; the wall-compare chart below puts both
# on one axis so you can see why.

# %% [markdown]
# ### The training run — one call for the lane that was a shell script
#
# 🖥️ **Spark-only step — showing the recorded run from this build's training session.**
#
# The NeMo lane that used to be a Megatron-Bridge launch script + a recipe file + a babysitting
# loop is one `training.run(recipe)` call against a `TrainRecipe`. The recorded result below is
# the production overnight: a 625-step LoRA over the 5k corpus on a single GB10.

# %%
# recipe = training.TrainRecipe(base_model=base_model, corpus=corpus_path, lane="nemo", ...)
# run = training.run(recipe)        # ← the one call that replaces the launch-script lane
run = {                              # recorded production run (NeMo lane — the shipped flagship)
    "lane": "nemo",
    "steps": 625,
    "train_wall_sec": 20280,         # 5h 38m — 26% faster than the Unsloth lane's 7h 34m
    "per_step_sec": 32.4,            # 26% lower per-step on the identical recipe
}
run

# %% [markdown]
# **5h 38m, 32.4 s/step — 26% faster than the Unsloth lane on the identical recipe.**
# Megatron-Core's fused kernels run the matmul-heavy hot path faster, and the whole train stayed
# inside the GB10's thermal and unified-memory budget — the feasibility envelope from the second
# cell held all the way through. One caveat the build earned: a 10-iter smoke under-projected the
# wall by ~16% because checkpoint saves dominate at production scale and a smoke barely samples
# them. Pad smoke projections by ~1.16× before promising an overnight.

# %% [markdown]
# ### Did training actually improve the reasoning? — the probe
#
# 🖥️ **Spark-only step — showing the recorded run from this build's probe session.**
#
# Lower training loss is not the same as better patent reasoning. `training.ReasoningProbe`
# generates `<think>` chains on held-out patent prompts and measures chain quality — and it
# normalizes the token budget across lanes so the comparison is fair (this lane's probe ran at
# a 2,048-token budget; the Unsloth sibling was capped at 1,536). That budget-fix is the
# apples-to-apples the bakeoff needed.

# %%
# probe = training.ReasoningProbe(budget=2048).run(merged_ckpt)
probe = {                            # recorded probe (NeMo lane), budget-normalized
    "think_rate": 0.60,              # fraction of answers that emit a reasoning chain
    "closed_chains": 12,
    "chain_length_vs_unsloth": "+44% on patent-strategic at the same think rate",
    "drift_caught": ["\"metes-and-times\" terminology", "fabricated MPEP §2163.05(s)"],
    "real_mpep_citation_rate": 0.99, # ~99% of probe answers cite real MPEP sections
}
probe

# %% [markdown]
# **A 0.60 think-rate, ~99% of answers citing real MPEP sections, and chains 44% longer than the
# Unsloth lane's on the patent-strategic shape — at the same think rate.** The probe is also
# where the drift gets *measured* rather than guessed at — the `"metes-and-times"` artifact and
# the fabricated `§2163.05(s)` citation are corpus-generator residue, not a model-wide
# hallucination pattern, and they live in the shipped card's bounded-drift section rather than
# getting swept under the rug.

# %% [markdown]
# ### Quantize — one merged checkpoint, four GGUF variants
#
# 🖥️ **Spark-only step — showing the recorded quantize sweep.**
#
# The merged BF16 LoRA goes through `quant.quantize_gguf`, which emits the canonical GGUF
# ladder in one pass. Each variant trades file size and on-Spark throughput against perplexity;
# the table two cells down is the matrix readers screenshot. Here we surface the variants the
# sweep produced straight from the artifact manifest.

# %%
import yaml, urllib.request
from pathlib import Path
from fieldkit import quant

def load_manifest(slug):
    """Dual-path: repo-relative on Spark (any CWD), GitHub-raw fallback on Colab/Kaggle."""
    for d in [Path.cwd(), *Path.cwd().parents]:
        f = d / "src" / "content" / "artifacts" / f"{slug}.yaml"
        if f.exists():
            return yaml.safe_load(f.read_text())
    url = ("https://raw.githubusercontent.com/manavsehgal/ai-field-notes/"
           f"main/src/content/artifacts/{slug}.yaml")
    return yaml.safe_load(urllib.request.urlopen(url).read())

# report = quant.quantize_gguf(model='merged-hf-bf16/', outdir='/data/quants/...') → QuantReport
manifest = load_manifest(vertical_slug)
variants = {v: manifest['perplexity'][v] for v in manifest['variants']}  # variant → wikitext ppl
variants

# %% [markdown]
# **Four variants, Q4_K_M through Q8_0**, spanning ~10.24 down to ~9.93 perplexity on
# wikitext-2 — about a full unit sharper than the Unsloth lane at every step. Q4_K_M is the
# smallest footprint; Q8_0 is near-lossless for the fidelity-first case; Q5_K_M and Q6_K sit in
# between. The next cell turns the full measurement set into the four-axis panel that decides
# which one to recommend.

# %% [markdown]
# ### The Spark-tested panel — the signature visual
#
# `viz.spark_quad` reads the manifest and renders perplexity, throughput, vertical accuracy,
# and thermal envelope as one figure — the same quad the HF card leads with. It is the
# deterministic output of the measured run, branded and stack-colored (NVIDIA green = NeMo lane),
# not a hand-drawn chart.

# %%
from types import SimpleNamespace
mf = SimpleNamespace(**manifest)
fig = viz.spark_quad(mf)
fig

# %% [markdown]
# **Q5_K_M is the sweet spot.** It holds 35 tok/s on the GB10 — comfortably interactive for
# a reasoning model that thinks before it answers — while giving up only ~0.11 perplexity to
# the much heavier Q8_0. That tok/s, against the ~16 GB envelope from the feasibility cell, is
# the FEASIBILITY axis closed: a patent attorney gets real-time offline reasoning on one desk.
# (The accuracy panel is intentionally empty — this release publishes perplexity + throughput
# as its measured axes, not a single-number vertical score.)

# %% [markdown]
# ### The hero table — the per-variant matrix
#
# `viz.variants_table` is the great_tables hero readers screenshot: every variant's size,
# perplexity, and on-Spark throughput, with the recommended row highlighted and a source-note
# crediting the article. One call, publication-grade.

# %%
# Real on-disk GGUF sizes (the manifest tracks perplexity + tok/s, not bytes).
sizes = {"Q4_K_M": "5.0 GB", "Q5_K_M": "5.9 GB", "Q6_K": "6.7 GB", "Q8_0": "8.7 GB"}
viz.variants_table(mf, sizes=sizes)

# %% [markdown]
# **The highlighted Q5_K_M row is the recommended default**, and the trade it encodes reads
# straight off the columns: a few tenths of perplexity and a few GB of disk buy you a third
# more throughput than Q8_0. A reader can pick a different row for their own size/fidelity
# constraint — the table hands them the whole decision, not just our answer.

# %% [markdown]
# ### Unsloth vs NeMo — the bakeoff's headline chart
#
# Both lanes built the same model from the same recipe. `viz.train_wall_compare` puts their
# training wall-clock on one axis, colored from each lane's `stack_origin` and annotating the
# faster lane with its delta. This is the chart that picked NeMo as the lane to ship.

# %%
viz.train_wall_compare({'unsloth': 454.0, 'nemo': 338.0},  # minutes: 7h34m vs 5h38m
                       title='Training wall — Unsloth vs NeMo')

# %% [markdown]
# **NeMo finishes 26% faster — 5h 38m against 7h 34m.** Megatron-Core's fused kernels run the
# matmul-heavy hot path faster, and the margin is the *low end* of NeMo's return: every step up
# the hardware ladder (H100, H200, B200, a SuperPOD) amortizes its framework overhead across
# more iterations. Unsloth tops out at one GPU by design; NeMo is the path off the Spark when
# off-the-Spark becomes a real question. That scaling headroom, on top of the wall, perplexity,
# and chain-length wins, is why NeMo is the lane that shipped.

# %% [markdown]
# ### Publish — render the card, write the manifest, push
#
# 🖥️ **Spark-only step — this is the recorded shape of the publish that already ran.**
#
# `publish.publish_quant` is the last call: it renders the HF model card (positioning first,
# drift bounded and below-the-fold, per the narrative contract), writes the artifact manifest
# Mac's site reads, and pushes the GGUF + card to the `Orionfold` handle. In the notebook we
# keep `dry_run=True` so it stages without pushing; the real push already shipped the two
# NeMo-lane repos below.

# %%
from fieldkit import publish
# result = publish.publish_quant(quant_report=report, base_model=base_model,
#     repo_name='patent-strategist-v3-nemo-GGUF', staging_dir='/tmp/stage', dry_run=True)
result = {                           # recorded — the live NeMo-lane artifacts this build shipped
    "nemo_gguf": "https://huggingface.co/Orionfold/patent-strategist-v3-nemo-GGUF",
    "nemo_lora": "https://huggingface.co/Orionfold/patent-strategist-v3-nemo",
}
result

# %% [markdown]
# **The card leads with positioning, bounds the drift, and never front-loads a roadmap** —
# `publish_quant` enforces that shape so every Orionfold release reads as one brand. The
# dry-run set is exactly what the live push wrote, minus the upload.

# %% [markdown]
# ## It shipped — the through-line
#
# A folder of one-off scripts became roughly a dozen typed `fieldkit` calls (**speed**); an 8B
# reasoner trained, quantized, and now serves with 92 GiB to spare on a single GB10
# (**feasibility**); and the artifacts are live, with a published card and a deep-dive behind
# them (**viability**).
#
# - **Live model:** <https://huggingface.co/Orionfold/patent-strategist-v3-nemo-GGUF>
# - **The receipt:** [Unsloth vs NeMo Framework bakeoff](https://ainative.business/field-notes/patent-strategist-bakeoff-unsloth-vs-nemo-framework/)
#
# Want to *use* the model instead of build it? The companion **user notebook** calls it on
# real patent tasks — and runs on a free Colab/Kaggle GPU as well as on the Spark.
