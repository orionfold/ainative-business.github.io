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
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Build II-Medical-8B on a Spark with fieldkit</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">AI researcher / engineer</div><div style="color:#C2C9D4;margin-top:0.5rem">Publish a five-variant medical reasoner as fieldkit API calls — on a Spark.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/II-Medical-8B-GGUF'
base_model = 'Intelligent-Internet/II-Medical-8B'
vertical_slug = 'ii-medical-8b-gguf'

import os
if runtime != "auto":
    os.environ["FIELDKIT_RUNTIME"] = runtime
from fieldkit.notebook import detect_runtime
RUNTIME = detect_runtime()
print(f"runtime: {RUNTIME}")

# %% [markdown] tags=["badges"]
# **Build it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/medical/builder.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/medical/builder.ipynb)
#
# **Use it:** [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/manavsehgal/ai-field-notes/blob/main/notebooks/medical/user.ipynb) [![Open in Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://kaggle.com/kernels/welcome?src=https://github.com/manavsehgal/ai-field-notes/blob/main/notebooks/medical/user.ipynb)
#
# **Model:** [![Hugging Face](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/Orionfold/II-Medical-8B-GGUF)

# %% [markdown]
# ## You quantized a medical reasoner on one desk. Here's the receipt.
#
# `Orionfold/II-Medical-8B-GGUF` is five GGUF variants of
# [Intelligent-Internet/II-Medical-8B](https://huggingface.co/Intelligent-Internet/II-Medical-8B) —
# a Qwen3-8B base finished with an SFT + DAPO reasoning recipe for clinical Q&A — measured on a
# single DGX Spark and published with a four-axis card. It is the fourth vertical in the curator
# series and the **first one that thinks before it answers**: every response opens a `<think>`
# block, and that single shift turned the generation budget into a load-bearing parameter the
# prior three cards never had to face.
#
# This notebook is the build, not the writeup. The release used to be a folder of shell scripts;
# here each step is a typed `fieldkit` call you can run. Three things it proves, in order:
#
# - **Speed** — the journey from "I picked a base model" to "I have a live HF artifact + a
#   published card" is a handful of `fieldkit` calls: an envelope check, a quantize sweep, the
#   branded measurement charts, and a publish.
# - **Feasibility** — an 8B reasoner converts, quantizes to five variants, and serves entirely
#   inside the GB10's 128 GB unified-memory envelope, with room left over to run a retriever
#   alongside it.
# - **Viability** — it shipped. The last cell links the live repo under the `Orionfold` handle
#   and the deep-dive that is this build's receipt.
#
# The full story — including the reasoning-budget gotcha below — lives in the field-notes
# medical-curator article; this is the runnable spine of it.

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
# Before committing a Spark to an overnight convert-and-measure sweep, you want to know the model
# fits the box. `capabilities.practical_inference_envelope` is the rule-of-thumb lookup: for an 8B
# model in bf16 it returns the weights + KV-cache footprint against the GB10's memory budget. This
# is the FEASIBILITY axis — every step downstream lives inside this envelope.

# %%
env = capabilities.practical_inference_envelope("8B params bf16")
env  # what fits on a single GB10

# %% [markdown]
# **~16 GB of weights + KV against a 128 GB unified-memory budget — "fits with room."** The F16
# source download is 15.3 GB and the heaviest GGUF (F16) is the same; the working variant
# (Q5_K_M) is 5.45 GB. That headroom is why the convert, the five-variant quantize sweep, and the
# live serving all happen on the same desk — and why a 5.45 GB medical model leaves space to run a
# retriever NIM and a pgvector store alongside it for a full offline RAG loop. The 8B reasoner
# never approaches the
# [unified-memory OOM landmine](https://ainative.business/field-notes/derisk-cloud-pretraining-on-the-spark/)
# at ~110 GiB.

# %% [markdown]
# ### One thing is different here — this model thinks
#
# The three prior verticals (finance, legal, cyber) shipped direct-answer models: ask, get a
# letter or a number. II-Medical-8B is a DAPO reasoning recipe — it emits an entire `<think>`
# block, typically 400–800 tokens of differential-diagnosis deliberation, *before* the answer
# letter lands. That changes one number you have to get right: the generation budget. At the
# pipeline's default `n_predict=256`, the F16 preflight scored **2/5** — not because the model
# didn't know the medicine, but because the budget ran out mid-thought before any answer token
# emerged. Bumped to `n_predict=1024`, the same weights swept a clean **5/5**. The quantize and
# measurement sweep below all ran at 1024, on numbers that reflect capability rather than a
# truncation artifact. Keep this in mind for every reasoning recipe: budget the chain, not just
# the answer.

# %% [markdown]
# ### Quantize — one base checkpoint, five GGUF variants
#
# 🖥️ **Spark-only step — showing the recorded quantize sweep.**
#
# The F16 source converts to GGUF and then through `quant.quantize_gguf`, which emits the
# canonical ladder in one pass: Q4_K_M, Q5_K_M, Q6_K, Q8_0, and the F16 reference. Each variant
# trades file size and on-Spark throughput against perplexity. Here we surface the variants the
# sweep produced straight from the artifact manifest — loaded dual-path so this cell reads the
# same on a Spark (any working directory) and on a cloud runtime (GitHub-raw fallback).

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

# report = quant.quantize_gguf(model='II-Medical-8B-f16.gguf', outdir='/data/quants/...') → QuantReport
manifest = load_manifest(vertical_slug)
variants = {v: manifest['perplexity'][v] for v in manifest['variants']}  # variant → wikitext-2 ppl
variants

# %% [markdown]
# **Five variants, Q4_K_M through F16**, all clustered tightly around ~16.0–16.6 perplexity on
# wikitext-2. The spread is striking: lossy quantization barely moved the general-language number,
# and Q6_K (16.01) and Q5_K_M (16.24) both sit *below* the F16 reference (16.27) — within
# wikitext-2 sampling noise, but a clean signal that the quantization did not damage this model.
# The next cell turns the full measurement set — perplexity, throughput, the medical bench, and
# thermal envelope — into the four-axis panel that decides which variant to recommend.

# %% [markdown]
# ### The Spark-tested panel — the signature visual
#
# `viz.spark_quad` reads the manifest and renders perplexity, on-Spark throughput, MedMCQA
# accuracy, and the thermal envelope as one figure — the same quad the HF card leads with. It is
# the deterministic output of the measured run, branded and stack-colored, not a hand-drawn chart.
# Unlike the prior reasoning model in this repo, the accuracy panel here is populated: medical
# ships a real per-variant vertical-bench score.

# %%
mf = SimpleNamespace(**manifest)
fig = viz.spark_quad(mf)
fig

# %% [markdown]
# **Q5_K_M is the sweet spot, and it lands above F16 on *both* axes that matter.** Its perplexity
# (16.24) edges under F16's 16.27, and its MedMCQA score (52%, 26/50) tops F16's 48% — two
# questions out of fifty, comfortably inside the n=50 binomial noise floor, but the direction is
# unambiguous. It holds **36.4 tok/s** on the GB10 at **5.45 GB**: interactive for a model that
# thinks for ~600 tokens before answering. There is also a quant story the prior cards inverted —
# Q8_0 here runs **1.78× faster than F16** (28.4 vs 15.9 tok/s), the opposite of finance and
# legal, where Q8_0 was *slower*. The cleanest hypothesis after four verticals: continued-pretrain
# shapes (finance, legal) produce Q8 weight distributions the GB10 handles less efficiently;
# chat-tune-only shapes (SecurityLLM's Zephyr-DPO, II-Medical's SFT+DAPO) don't. Medical is the
# fast half of that 2–2 split.

# %% [markdown]
# ### The hero table — the per-variant matrix
#
# `viz.variants_table` is the great_tables hero readers screenshot: every variant's size,
# perplexity, on-Spark throughput, and medical-bench accuracy, with the recommended row
# highlighted and a source-note crediting the article. The manifest tracks perplexity and tok/s
# but not on-disk bytes, so we hand it the measured GGUF sizes. One call, publication-grade.

# %%
sizes = {"Q4_K_M": "4.68 GB", "Q5_K_M": "5.45 GB", "Q6_K": "6.26 GB",
         "Q8_0": "8.11 GB", "F16": "15.3 GB"}
viz.variants_table(mf, sizes=sizes)

# %% [markdown]
# **The highlighted Q5_K_M row is the recommended default**, and the trade reads straight off the
# columns. Reach for **Q4_K_M** (4.68 GB, 43.6 tok/s) when you're scanning a corpus and a reviewer
# checks top hits — the ~10-point bench delta is recoverable downstream. **Q6_K** is the
# lowest-perplexity pick for minimum general-language drift; **Q8_0** is the lossless-feeling pick
# at F16 quality, 53% the size, and 1.78× the speed; **F16** is reference-only. The table hands a
# reader the whole decision, not just our answer.

# %% [markdown]
# ### Publish — render the card, write the manifest, push
#
# 🖥️ **Spark-only step — this is the recorded shape of the publish that already ran.**
#
# `publish.publish_quant` is the last call: it renders the HF model card (positioning first, drift
# bounded and below-the-fold, per the narrative contract), writes the artifact manifest Mac's site
# reads, and pushes the five GGUFs + card to the `Orionfold` handle. The card snippets render
# `chat_format="chatml"` because the manifest carries it — II-Medical-8B uses Qwen3's ChatML
# template (`<|im_start|>` / `<|im_end|>`), not Llama-2's `[INST]` or Zephyr's `<|user|>`. In the
# notebook we keep `dry_run=True` so it stages without pushing; the real push already shipped the
# repo below.

# %%
from fieldkit import publish
# result = publish.publish_quant(quant_report=report, base_model=base_model,
#     repo_name='II-Medical-8B-GGUF', staging_dir='/tmp/stage',
#     chat_format='chatml', recommended_variant='Q5_K_M', dry_run=True)
result = {                           # recorded — the live artifact this build shipped
    "gguf": "https://huggingface.co/Orionfold/II-Medical-8B-GGUF",
    "variants": ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16"],
    "recommended": "Q5_K_M",
    "chat_format": "chatml",
}
result

# %% [markdown]
# **The card leads with positioning, bounds the drift, and never front-loads a roadmap** —
# `publish_quant` enforces that shape so every Orionfold release reads as one brand. The headline
# the medical card earned is that `fieldkit` shipped *zero* new symbols to absorb a fourth vertical
# and a reasoning recipe: a new chat template, a new scorer, and a new license all flowed through
# the existing surface. The configuration changed; the library did not.

# %% [markdown]
# ## It shipped — the through-line
#
# A folder of one-off scripts became a handful of typed `fieldkit` calls (**speed**); an 8B
# reasoner converted, quantized to five variants, and now serves at 36.4 tok/s in 5.45 GB on a
# single GB10 (**feasibility**); and the artifact is live, with a published card and a deep-dive
# behind it (**viability**).
#
# - **Live model:** <https://huggingface.co/Orionfold/II-Medical-8B-GGUF>
# - **The receipt:** [Becoming a medical curator on Spark](https://ainative.business/field-notes/becoming-a-medical-curator-on-spark/)
#
# Want to *use* the model instead of build it? The companion **user notebook** calls it on real
# clinical-reasoning tasks — surfacing the `<think>` chain — and runs on a free Colab/Kaggle GPU
# as well as on the Spark.
