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
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Build SecurityLLM on a Spark with fieldkit</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">AI researcher / engineer</div><div style="color:#C2C9D4;margin-top:0.5rem">Publish a five-variant cybersecurity model as fieldkit API calls — on a Spark.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/SecurityLLM-GGUF'
base_model = 'ZySec-AI/SecurityLLM'
vertical_slug = 'securityllm-gguf'

import os
if runtime != "auto":
    os.environ["FIELDKIT_RUNTIME"] = runtime
from fieldkit.notebook import detect_runtime
RUNTIME = detect_runtime()
print(f"runtime: {RUNTIME}")

# %% [markdown] tags=["badges"]
# **Build it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/cyber/builder.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/cyber/builder.ipynb)
#
# **Use it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/cyber/user.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/cyber/user.ipynb)
#
# **Model:** [![Hugging Face](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/Orionfold/SecurityLLM-GGUF)

# %% [markdown]
# ## You quantized a cybersecurity model on one desk. Here's the receipt.
#
# `Orionfold/SecurityLLM-GGUF` is five GGUF variants of
# [ZySec-AI/SecurityLLM](https://huggingface.co/ZySec-AI/SecurityLLM) — a Mistral-7B + Zephyr-DPO
# cybersecurity fine-tune — measured on a single DGX Spark and published with a four-axis card.
# It's the third vertical in the curator series and the one that introduced the `mcq_letter`
# scorer the medical card later reused.
#
# This notebook is the build, not the writeup. The release used to be a folder of shell scripts;
# here each step is a typed `fieldkit` call you can run. Three things it proves, in order:
#
# - **Speed** — "I picked a base model" to "live HF artifact + published card" is a handful of
#   `fieldkit` calls: an envelope check, a quantize sweep, the branded charts, and a publish.
# - **Feasibility** — a 7B model converts, quantizes to five variants, and serves entirely inside
#   the GB10's 128 GB unified-memory envelope — the working variant is a 4.8 GB file, and the whole
#   ladder runs fast (Q4_K_M tops 47 tok/s).
# - **Viability** — it shipped. The last cell links the live repo under the `Orionfold` handle and
#   the deep-dive that is this build's receipt.
#
# The full story lives in the field-notes cyber-curator article; this is the runnable spine of it.

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
# security model leaves space to run a retriever + a CVE / advisory corpus alongside it for an
# offline RAG loop. An air-gapped SOC can run this without a query leaving the network.

# %% [markdown]
# ### What kind of model is this — and what that does to the numbers
#
# SecurityLLM is a **chat-tune-only shape**: Mistral-7B finished with Zephyr-DPO (preference-tuned
# from preferred-vs-rejected pairs), a direct-answer model (no `<think>` reasoning block). That
# shape shows up twice in the measurement set. First, the **Q8 flip**: Q8_0 runs *faster* than F16
# (30.3 vs 17.5 tok/s, 1.7×) — the opposite of finance and legal, and the same direction as medical.
# After four verticals the pattern is clean: chat-tune-only shapes (cyber, medical) run Q8 fast on
# the GB10; domain-pretrained shapes (finance, legal) run it slow. Second, the **template gotcha**:
# Zephyr's `<|user|>` format is non-negotiable here, and the model is verbose by default — so the
# `mcq_letter` scorer (born on this card) regex-extracts the single letter and forgives the prose.

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

# report = quant.quantize_gguf(model='securityllm-f16.gguf', outdir='/data/quants/...') → QuantReport
manifest = load_manifest(vertical_slug)
variants = {v: manifest['perplexity'][v] for v in manifest['variants']}  # variant → wikitext-2 ppl
variants

# %% [markdown]
# **Five variants, Q4_K_M through F16**, clustered tightly around ~7.30–7.40 perplexity on
# wikitext-2 — Q8_0 (7.3068) sits within a hair of F16 (7.3009). Lossy quantization left
# general-language quality essentially intact; the axis you choose on is throughput, size, and the
# security bench, not perplexity. The next cell turns the full measurement set into the four-axis
# panel that decides which variant to ship.

# %% [markdown]
# ### The Spark-tested panel — the signature visual
#
# `viz.spark_quad` reads the manifest and renders perplexity, on-Spark throughput, CyberMetric
# accuracy, and the thermal envelope as one figure — the same quad the HF card leads with. It is
# the deterministic output of the measured run, branded and stack-colored, not a hand-drawn chart.

# %%
mf = SimpleNamespace(**manifest)
fig = viz.spark_quad(mf)
fig

# %% [markdown]
# **The throughput panel is the story: every quant runs fast, and Q8_0 (30.3 tok/s) beats F16
# (17.5).** That's the chat-tune Q8 flip — cyber and medical run Q8 fast where finance and legal run
# it slow. On accuracy, read the panel honestly: F16's 34% on CyberMetric is a modest-but-real lead
# over the 25% four-option chance floor, and the spread across variants (Q4_K_M tops at 40%) is well
# inside n=50 sampling noise. Q5_K_M is the recommended pick — 4.8 GB at 40 tok/s, F16-or-better
# behavior without the disk and load-time cost.

# %% [markdown]
# ### The hero table — the per-variant matrix
#
# `viz.variants_table` is the great_tables hero readers screenshot: every variant's size,
# perplexity, on-Spark throughput, and CyberMetric accuracy, recommended row highlighted, with a
# source-note crediting the article. The manifest tracks perplexity and tok/s but not on-disk
# bytes, so we hand it the measured GGUF sizes.

# %%
sizes = {"Q4_K_M": "4.1 GB", "Q5_K_M": "4.8 GB", "Q6_K": "5.5 GB",
         "Q8_0": "7.2 GB", "F16": "13.5 GB"}
viz.variants_table(mf, sizes=sizes)

# %% [markdown]
# **The highlighted Q5_K_M row is the recommended default** — 4.8 GB at 40 tok/s. Reach for
# **Q4_K_M** (4.1 GB, 47.7 tok/s) when throughput is everything and you're batching MCQ evals — it
# even tops the bench here; **Q6_K** for the lowest-perplexity work; **Q8_0** is the rare quant that's
# both near-lossless *and* fast on this shape (30.3 tok/s); **F16** is reference-only. The table hands
# a reader the whole decision, not just ours.

# %% [markdown]
# ### Publish — render the card, write the manifest, push
#
# 🖥️ **Spark-only step — this is the recorded shape of the publish that already ran.**
#
# `publish.publish_quant` is the last call: it renders the HF model card (positioning first, drift
# bounded and below-the-fold), writes the artifact manifest Mac's site reads, and pushes the five
# GGUFs + card to the `Orionfold` handle. The card snippets render `chat_format="zephyr"` — using
# Mistral's `[INST]` template instead would corrupt this model's responses. In the notebook we keep
# `dry_run=True`; the real push already shipped the repo below.

# %%
from fieldkit import publish
# result = publish.publish_quant(quant_report=report, base_model=base_model,
#     repo_name='SecurityLLM-GGUF', staging_dir='/tmp/stage',
#     chat_format='zephyr', recommended_variant='Q5_K_M', dry_run=True)
result = {                           # recorded — the live artifact this build shipped
    "gguf": "https://huggingface.co/Orionfold/SecurityLLM-GGUF",
    "variants": ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16"],
    "recommended": "Q5_K_M",
    "chat_format": "zephyr",
}
result

# %% [markdown]
# **The card leads with positioning, bounds the drift, and never front-loads a roadmap** —
# `publish_quant` enforces that shape so every Orionfold release reads as one brand. SecurityLLM was
# the third card through this surface and the one that grew the toolkit's reach: it introduced the
# `mcq_letter` scorer (later reused by medical) and the Zephyr chat-template branch — additions to the
# scripts around fieldkit, not to fieldkit itself.

# %% [markdown]
# ## It shipped — the through-line
#
# A folder of one-off scripts became a handful of typed `fieldkit` calls (**speed**); a 7B security
# model converted, quantized to five variants, and now serves at 40 tok/s in 4.8 GB on a single GB10
# (**feasibility**); and the artifact is live, with a published card and a deep-dive behind it
# (**viability**).
#
# - **Live model:** <https://huggingface.co/Orionfold/SecurityLLM-GGUF>
# - **The receipt:** [Becoming a cyber curator on Spark](https://ainative.business/field-notes/becoming-a-cyber-curator-on-spark/)
#
# Want to *use* the model instead of build it? The companion **user notebook** calls it on real
# security-MCQ tasks — and runs on a free Colab/Kaggle GPU as well as on the Spark.
