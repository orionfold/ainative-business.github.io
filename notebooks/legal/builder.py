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
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Build Saul-7B-Instruct on a Spark with fieldkit</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">AI researcher / engineer</div><div style="color:#C2C9D4;margin-top:0.5rem">Publish a five-variant legal model as fieldkit API calls — on a Spark.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/Saul-7B-Instruct-v1-GGUF'
base_model = 'Equall/Saul-7B-Instruct-v1'
vertical_slug = 'saul-7b-instruct-v1-gguf'

import os
if runtime != "auto":
    os.environ["FIELDKIT_RUNTIME"] = runtime
from fieldkit.notebook import detect_runtime
RUNTIME = detect_runtime()
print(f"runtime: {RUNTIME}")

# %% [markdown] tags=["badges"]
# **Build it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/legal/builder.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/legal/builder.ipynb)
#
# **Use it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/legal/user.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/legal/user.ipynb)
#
# **Model:** [![Hugging Face](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/Orionfold/Saul-7B-Instruct-v1-GGUF)

# %% [markdown]
# ## You quantized a legal model on one desk. Here's the receipt.
#
# `Orionfold/Saul-7B-Instruct-v1-GGUF` is five GGUF variants of
# [Equall/Saul-7B-Instruct-v1](https://huggingface.co/Equall/Saul-7B-Instruct-v1) — a Mistral-7B
# instruction-tuned for law (the model from the Saul paper) — measured on a single DGX Spark and
# published with a four-axis card. It's the second vertical in the curator series, and the one
# where the publishing surface proved it generalized: a new bench, a new chat template, a new
# license, zero new library symbols.
#
# This notebook is the build, not the writeup. The release used to be a folder of shell scripts;
# here each step is a typed `fieldkit` call you can run. Three things it proves, in order:
#
# - **Speed** — "I picked a base model" to "live HF artifact + published card" is a handful of
#   `fieldkit` calls: an envelope check, a quantize sweep, the branded charts, and a publish.
# - **Feasibility** — a 7B model converts, quantizes to five variants, and serves entirely inside
#   the GB10's 128 GB unified-memory envelope — the working variant is a 4.8 GB file.
# - **Viability** — it shipped. The last cell links the live repo under the `Orionfold` handle and
#   the deep-dive that is this build's receipt.
#
# The full story lives in the field-notes legal-curator article; this is the runnable spine of it.

# %% [markdown]
# ### Setup
#
# One install pulls `fieldkit` plus its notebook extra (matplotlib, great_tables, the inference
# glue). `capabilities` answers feasibility questions with arithmetic; `viz` turns the measured
# run into the same branded charts the HF card carries.

# %%
# %pip install -q 'fieldkit[notebook]'
import fieldkit
from fieldkit import capabilities, viz
print('fieldkit', fieldkit.__version__)

# %% [markdown]
# ### Does it even fit? — the feasibility question, answered first
#
# `capabilities.practical_inference_envelope` is the rule-of-thumb lookup: for a 7B-class model in
# bf16 it returns the weights + KV-cache footprint against the GB10's memory budget. (The table is
# keyed by size band; a 7B sits comfortably inside the 8B-band envelope.) This is the FEASIBILITY
# axis — every step downstream lives inside it.

# %%
env = capabilities.practical_inference_envelope("8B params bf16")
env  # what fits on a single GB10

# %% [markdown]
# **~16 GB of weights + KV against a 128 GB unified-memory budget — "fits with room."** The F16
# GGUF is 13.5 GB; the working variant (Q5_K_M) is 4.8 GB. That headroom is why the convert, the
# five-variant quantize sweep, and live serving all happen on the same desk — and why a 4.8 GB
# legal model leaves space to run a retriever + a case-law/statute corpus alongside it for an
# offline RAG loop. Privileged legal text never has to leave the box.

# %% [markdown]
# ### What kind of model is this — and what that does to the numbers
#
# Saul is a **legal SFT on Mistral-7B**: a direct-answer model (no `<think>` reasoning block) tuned
# for legal classification and reasoning. Two things to read off the measurement set. First,
# **Q5_K_M tops the bench** — 72% on LegalBench, *above* F16's 68% (within n=50 sampling variance,
# but the direction says the lossy 4.8 GB variant lost no legal capability). Second, the **Q8
# anomaly**: Q8_0 measured *slower* than F16 (7.3 vs 10.9 tok/s). The legal article flags that as a
# likely thermal artifact — Q8_0 ran last in the sweep, into a half-spent throttle window — and
# across four verticals the slow-Q8 cases are the domain-trained shapes (finance, legal) while the
# chat-tune-only shapes (cyber, medical) run Q8 fast. The card carries the measurement as-recorded.

# %% [markdown]
# ### Quantize — one base checkpoint, five GGUF variants
#
# 🖥️ **Spark-only step — showing the recorded quantize sweep.**
#
# The F16 source converts to GGUF and through `quant.quantize_gguf`, which emits the canonical
# ladder in one pass: Q4_K_M, Q5_K_M, Q6_K, Q8_0, and the F16 reference. Here we surface the
# variants the sweep produced straight from the artifact manifest — loaded dual-path so this cell
# reads the same on a Spark (any working directory) and on a cloud runtime (GitHub-raw fallback).

# %%
import yaml, urllib.request
from pathlib import Path
from types import SimpleNamespace
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

# report = quant.quantize_gguf(model='saul-7b-f16.gguf', outdir='/data/quants/...') → QuantReport
manifest = load_manifest(vertical_slug)
variants = {v: manifest['perplexity'][v] for v in manifest['variants']}  # variant → wikitext-2 ppl
variants

# %% [markdown]
# **Five variants, Q4_K_M through F16**, clustered tightly around ~5.91–5.99 perplexity on
# wikitext-2 — Q8_0 (5.9138) even edges *below* F16 (5.9165). Lossy quantization left general-language
# quality essentially intact; the axis you choose on is throughput, size, and the legal bench, not
# perplexity. The next cell turns the full measurement set into the four-axis panel that decides
# which variant to ship.

# %% [markdown]
# ### The Spark-tested panel — the signature visual
#
# `viz.spark_quad` reads the manifest and renders perplexity, on-Spark throughput, LegalBench
# accuracy, and the thermal envelope as one figure — the same quad the HF card leads with. It is
# the deterministic output of the measured run, branded and stack-colored, not a hand-drawn chart.

# %%
mf = SimpleNamespace(**manifest)
fig = viz.spark_quad(mf)
fig

# %% [markdown]
# **Q5_K_M is the sweet spot, and it tops the accuracy panel** — 72% on LegalBench, the highest of
# the five and above F16's 68%, at 4.8 GB and 20.2 tok/s. The throughput panel shows the Q8 anomaly
# (7.3 tok/s, below F16's 10.9) — the domain-SFT signature, likely thermal in origin; if Q8 quality
# matters for your workload, prefer Q6_K (22.4 tok/s) or measure Q8 on your own box. For an
# interactive legal assistant, Q5_K_M is the row to download first.

# %% [markdown]
# ### The hero table — the per-variant matrix
#
# `viz.variants_table` is the great_tables hero readers screenshot: every variant's size,
# perplexity, on-Spark throughput, and LegalBench accuracy, recommended row highlighted, with a
# source-note crediting the article. The manifest tracks perplexity and tok/s but not on-disk
# bytes, so we hand it the measured GGUF sizes.

# %%
sizes = {"Q4_K_M": "4.1 GB", "Q5_K_M": "4.8 GB", "Q6_K": "5.5 GB",
         "Q8_0": "7.2 GB", "F16": "13.5 GB"}
viz.variants_table(mf, sizes=sizes)

# %% [markdown]
# **The highlighted Q5_K_M row is the recommended default** — 4.8 GB, 20.2 tok/s, 72% on LegalBench.
# Reach for **Q4_K_M** (4.1 GB, 29.4 tok/s) for high-volume legal-doc classification with a reviewer
# downstream — its 6-point bench dip vs Q5_K_M is recoverable in that loop; **Q6_K** for the
# lowest-perplexity work; **Q8_0** only after confirming throughput on your box; **F16** is
# reference-only. The table hands a reader the whole decision, not just ours.

# %% [markdown]
# ### Publish — render the card, write the manifest, push
#
# 🖥️ **Spark-only step — this is the recorded shape of the publish that already ran.**
#
# `publish.publish_quant` is the last call: it renders the HF model card (positioning first, drift
# bounded and below-the-fold), writes the artifact manifest Mac's site reads, and pushes the five
# GGUFs + card to the `Orionfold` handle. The card snippets render `chat_format="mistral-instruct"`
# because Saul inherits Mistral's `[INST]` template. In the notebook we keep `dry_run=True`; the
# real push already shipped the repo below.

# %%
from fieldkit import publish
# result = publish.publish_quant(quant_report=report, base_model=base_model,
#     repo_name='Saul-7B-Instruct-v1-GGUF', staging_dir='/tmp/stage',
#     chat_format='mistral-instruct', recommended_variant='Q5_K_M', dry_run=True)
result = {                           # recorded — the live artifact this build shipped
    "gguf": "https://huggingface.co/Orionfold/Saul-7B-Instruct-v1-GGUF",
    "variants": ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16"],
    "recommended": "Q5_K_M",
    "chat_format": "mistral-instruct",
}
result

# %% [markdown]
# **The card leads with positioning, bounds the drift, and never front-loads a roadmap** —
# `publish_quant` enforces that shape so every Orionfold release reads as one brand. Saul was the
# second card through this surface and the proof it generalized: swapping FinanceBench's
# `numeric_match` for LegalBench's `contains`, and Llama-2's template for Mistral's, needed no new
# library code at all.

# %% [markdown]
# ## It shipped — the through-line
#
# A folder of one-off scripts became a handful of typed `fieldkit` calls (**speed**); a 7B legal
# model converted, quantized to five variants, and now serves at 20.2 tok/s in 4.8 GB on a single
# GB10 (**feasibility**); and the artifact is live, with a published card and a deep-dive behind it
# (**viability**).
#
# - **Live model:** <https://huggingface.co/Orionfold/Saul-7B-Instruct-v1-GGUF>
# - **The receipt:** [Becoming a legal curator on Spark](https://ainative.business/field-notes/becoming-a-legal-curator-on-spark/)
#
# Want to *use* the model instead of build it? The companion **user notebook** calls it on real
# legal-classification tasks — and runs on a free Colab/Kaggle GPU as well as on the Spark.
