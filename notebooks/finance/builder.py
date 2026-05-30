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
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Build finance-chat on a Spark with fieldkit</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">AI researcher / engineer</div><div style="color:#C2C9D4;margin-top:0.5rem">Publish a five-variant finance chat model as fieldkit API calls — on a Spark.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/finance-chat-GGUF'
base_model = 'AdaptLLM/finance-chat'
vertical_slug = 'finance-chat-gguf'

import os
if runtime != "auto":
    os.environ["FIELDKIT_RUNTIME"] = runtime
from fieldkit.notebook import detect_runtime
RUNTIME = detect_runtime()
print(f"runtime: {RUNTIME}")

# %% [markdown] tags=["badges"]
# **Build it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/finance/builder.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/finance/builder.ipynb)
#
# **Use it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/finance/user.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/finance/user.ipynb)
#
# **Model:** [![Hugging Face](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/Orionfold/finance-chat-GGUF)

# %% [markdown]
# ## You quantized a finance chat model on one desk. Here's the receipt.
#
# `Orionfold/finance-chat-GGUF` is five GGUF variants of
# [AdaptLLM/finance-chat](https://huggingface.co/AdaptLLM/finance-chat) — a Llama-2-7B base given
# a finance continued-pretrain so it answers financial questions offline — measured on a single
# DGX Spark and published with a four-axis card. It was the **first** vertical in the curator
# series: the release that set the publishing surface every later card reuses.
#
# This notebook is the build, not the writeup. The release used to be a folder of shell scripts;
# here each step is a typed `fieldkit` call you can run. Three things it proves, in order:
#
# - **Speed** — "I picked a base model" to "live HF artifact + published card" is a handful of
#   `fieldkit` calls: an envelope check, a quantize sweep, the branded charts, and a publish.
# - **Feasibility** — a 7B model converts, quantizes to five variants, and serves entirely inside
#   the GB10's 128 GB unified-memory envelope — the working variant is a 4.5 GB file.
# - **Viability** — it shipped. The last cell links the live repo under the `Orionfold` handle and
#   the deep-dive that is this build's receipt.
#
# The full story — including the Q8 throughput anomaly this card first surfaced — lives in the
# field-notes gguf-publisher article; this is the runnable spine of it.

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
# GGUF is 12.6 GB; the working variant (Q5_K_M) is 4.5 GB. That headroom is why the convert, the
# five-variant quantize sweep, and live serving all happen on the same desk — and why a 4.5 GB
# finance model leaves space to run a retriever + a 10-K corpus alongside it for an offline RAG
# loop. A 7B finance assistant runs on hardware a single analyst already has.

# %% [markdown]
# ### What kind of model is this — and what that does to the numbers
#
# finance-chat is a **continued-pretrain** shape: Llama-2-7B-chat further trained on a finance
# corpus, a direct-answer model (no `<think>` reasoning block). Two honest consequences the card
# carries rather than smooths over. First, the **accuracy floor**: FinanceBench lands at 14–18%
# across variants — that is 7B *capacity*, not quantization damage, and quantization can't recover
# what the base never had. Second, the **Q8 anomaly**: on this model Q8_0 runs *slower* than F16
# (8.9 vs 11.5 tok/s). It first read as a thermal-scheduling artifact; after four verticals it
# correlates with model shape — continued-pretrain shapes (finance, legal) run Q8 slow on the
# GB10, chat-tune-only shapes (cyber, medical) run it fast. finance is the slow half of that split.

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

# report = quant.quantize_gguf(model='finance-chat-f16.gguf', outdir='/data/quants/...') → QuantReport
manifest = load_manifest(vertical_slug)
variants = {v: manifest['perplexity'][v] for v in manifest['variants']}  # variant → wikitext-2 ppl
variants

# %% [markdown]
# **Five variants, Q4_K_M through F16**, clustered tightly around ~6.14–6.22 perplexity on
# wikitext-2 — Q8_0's perplexity matches F16 to four decimals (6.1373). Lossy quantization left
# general-language quality essentially intact; the axis you actually choose on is throughput and
# size, not perplexity. The next cell turns the full measurement set — perplexity, throughput, the
# finance bench, and thermal envelope — into the four-axis panel that decides which variant to ship.

# %% [markdown]
# ### The Spark-tested panel — the signature visual
#
# `viz.spark_quad` reads the manifest and renders perplexity, on-Spark throughput, FinanceBench
# accuracy, and the thermal envelope as one figure — the same quad the HF card leads with. It is
# the deterministic output of the measured run, branded and stack-colored, not a hand-drawn chart.

# %%
mf = SimpleNamespace(**manifest)
fig = viz.spark_quad(mf)
fig

# %% [markdown]
# **Q5_K_M is the recommended pick — but read the throughput panel carefully.** Q5_K_M holds
# 26.9 tok/s at 4.5 GB; the smaller Q4_K_M is faster still (31.1 tok/s). The eye-catcher is Q8_0
# at just 8.9 tok/s — *below* F16's 11.5 — the continued-pretrain Q8 anomaly made visual. The
# practical lesson it earns: if you're choosing between Q6_K and Q8_0 for a throughput-sensitive
# finance workload, **measure on your own hardware before committing to Q8_0**. The accuracy panel
# is honest about the 7B floor (14–18% on FinanceBench); for higher quantitative accuracy the path
# is a larger base, not a heavier quant.

# %% [markdown]
# ### The hero table — the per-variant matrix
#
# `viz.variants_table` is the great_tables hero readers screenshot: every variant's size,
# perplexity, on-Spark throughput, and FinanceBench accuracy, recommended row highlighted, with a
# source-note crediting the article. The manifest tracks perplexity and tok/s but not on-disk
# bytes, so we hand it the measured GGUF sizes.

# %%
sizes = {"Q4_K_M": "3.8 GB", "Q5_K_M": "4.5 GB", "Q6_K": "5.1 GB",
         "Q8_0": "6.7 GB", "F16": "12.6 GB"}
viz.variants_table(mf, sizes=sizes)

# %% [markdown]
# **The highlighted Q5_K_M row is the recommended default** — 4.5 GB at 26.9 tok/s, the
# speed/quality balance for an interactive finance assistant. Reach for **Q4_K_M** (3.8 GB,
# 31.1 tok/s) when you're scanning a filing corpus and a reviewer checks the hits; **Q6_K** for
# the lowest-perplexity general-language work; **Q8_0** only after you've confirmed its throughput
# on your box; **F16** is reference-only. The table hands a reader the whole decision, not just ours.

# %% [markdown]
# ### Publish — render the card, write the manifest, push
#
# 🖥️ **Spark-only step — this is the recorded shape of the publish that already ran.**
#
# `publish.publish_quant` is the last call: it renders the HF model card (positioning first, drift
# bounded and below-the-fold), writes the artifact manifest Mac's site reads, and pushes the five
# GGUFs + card to the `Orionfold` handle. The card snippets render `chat_format="llama-2"` because
# finance-chat inherits Llama-2's `[INST]` template (no modern `chat_template` field on the base,
# so consumer surfaces wrap it for you). In the notebook we keep `dry_run=True`; the real push
# already shipped the repo below.

# %%
from fieldkit import publish
# result = publish.publish_quant(quant_report=report, base_model=base_model,
#     repo_name='finance-chat-GGUF', staging_dir='/tmp/stage',
#     chat_format='llama-2', recommended_variant='Q5_K_M', dry_run=True)
result = {                           # recorded — the live artifact this build shipped
    "gguf": "https://huggingface.co/Orionfold/finance-chat-GGUF",
    "variants": ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16"],
    "recommended": "Q5_K_M",
    "chat_format": "llama-2",
}
result

# %% [markdown]
# **The card leads with positioning, bounds the drift, and never front-loads a roadmap** —
# `publish_quant` enforces that shape so every Orionfold release reads as one brand. finance-chat
# was the first card through this surface; the three verticals after it (legal, cyber, medical)
# reused it with zero new library symbols — only a different scorer, chat template, and license.

# %% [markdown]
# ## It shipped — the through-line
#
# A folder of one-off scripts became a handful of typed `fieldkit` calls (**speed**); a 7B finance
# model converted, quantized to five variants, and now serves at 26.9 tok/s in 4.5 GB on a single
# GB10 (**feasibility**); and the artifact is live, with a published card and a deep-dive behind it
# (**viability**).
#
# - **Live model:** <https://huggingface.co/Orionfold/finance-chat-GGUF>
# - **The receipt:** [Becoming a GGUF publisher on Spark](https://ainative.business/field-notes/becoming-a-gguf-publisher-on-spark/)
#
# Want to *use* the model instead of build it? The companion **user notebook** calls it on real
# financial-Q&A tasks — and runs on a free Colab/Kaggle GPU as well as on the Spark.
