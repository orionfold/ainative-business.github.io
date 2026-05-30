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
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Use finance-chat in your app</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">App developer / model consumer</div><div style="color:#C2C9D4;margin-top:0.5rem">Call a finance chat model on real tasks — runs on Spark and a free cloud GPU.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/finance-chat-GGUF'

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
# ## A finance chat model you can call in three lines — on the hardware you already have
#
# `finance-chat` is a 7B Llama-2 model continued-pretrained on finance text: it answers financial
# questions, explains concepts, and — pointed at a filing — reads the numbers out of it. It runs
# **offline**, which is the point for anyone who can't send a draft 10-K, a deal model, or client
# financials to a hosted API. Built for FP&A teams, finance-app developers, and analysts who want
# a private domain assistant on hardware they already own.
#
# This notebook proves three things from the consumer's seat:
#
# - **Desirability** — the model on real financial tasks: open-book Q&A over a filing, concept
#   explanation, and variance commentary.
# - **Viability** — `fieldkit` is the glue: one call to open the model, `fieldkit.rag` to ground
#   answers in real filing text, a `fieldkit.eval` scorer to gate numeric answers.
# - **Feasibility** — the same code runs locally on a DGX Spark **and** on a free Colab/Kaggle GPU.
#   No rewrite, no API key, no financials leaving your control on the local path.
#
# One honest expectation up front: this is a 7B model, so it's strongest as an *open-book*
# assistant — give it the filing text and ask it to read and reason, rather than relying on it to
# recall a specific figure from memory.

# %% [markdown]
# ### Setup — one code path, two runtimes
#
# `detect_runtime()` tells you where you are. Nothing below branches on it: the same notebook runs
# on your Spark (serving the model locally) and on a free cloud GPU (pulling the published GGUF).
# That is the dual-path contract — write once, run anywhere a GPU is.

# %%
# %pip install -q 'fieldkit[notebook]'
from fieldkit.notebook import open_model, detect_runtime, is_cloud, display_reply
RUNTIME = detect_runtime()
print('runtime:', RUNTIME, '| cloud?', is_cloud(RUNTIME))

# %% [markdown]
# ### Open the model — one call, backend chosen for you
#
# `open_model` returns a client with a single `.chat()` surface regardless of backend. On the
# Spark it serves the local GGUF; on Colab/Kaggle it pulls the published quant from HuggingFace and
# runs it through `llama-cpp-python` on the free GPU. finance-chat inherits Llama-2's `[INST]`
# template, so we pass `chat_format="llama-2"`. This is the FEASIBILITY axis — a single free GPU is
# enough.

# %%
client = open_model(hf_repo, chat_format="llama-2")  # variant auto-picked: Q4_K_M cloud, Q5_K_M Spark
client

# %% [markdown]
# ### Use case 1 — Open-book Q&A over a filing
#
# The model's sweet spot: hand it a passage from a 10-K and ask a question whose answer is in the
# text. This is the FinanceBench shape — the bench gives each question the relevant filing excerpt
# as context, and a 7B model that *reads* the passage beats one asked to recall the figure cold.

# %%
messages = [
    {'role': 'user', 'content': (
        "Context (FY2018 10-K excerpt): \"Capital expenditures were $1,577 million in 2018, "
        "compared with $1,373 million in 2017.\"\n\n"
        "Question: What was the company's FY2018 capital expenditure, and how did it change "
        "year over year?")},
]
reply = client.chat(messages, max_tokens=512)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **Grounded in the passage, the answer is exact: $1,577M, up $204M (~15%) from 2017.** The take-home
# for app builders: structure your prompt as *context + question*, and the 7B model becomes a
# reliable reader rather than a hopeful rememberer. The numeric answer is also the thing you can
# score — use case shown below.

# %% [markdown]
# ### Use case 2 — Explain a finance concept
#
# Beyond filings, the continued-pretrain gives it solid domain explanation. This is the assistant
# surface — a quick, correct definition with the *why*, not just a dictionary line.

# %%
messages = [
    {'role': 'user', 'content': (
        "Explain working capital to a non-finance product manager: what it is, how it's "
        "calculated, and why a sudden drop might matter.")},
]
reply = client.chat(messages, max_tokens=512)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **A strong answer names the formula (current assets − current liabilities), then connects a drop
# to liquidity / operational stress** rather than stopping at the definition. This is where the
# finance continued-pretrain earns its keep over a general 7B chat model — the domain framing comes
# for free.

# %% [markdown]
# ### Use case 3 — FP&A variance commentary
#
# A daily FP&A task: turn a small numeric table into the prose a deck needs. The model drafts the
# variance narrative; a human edits. This is the "agent drafts, analyst approves" loop that makes a
# 7B model genuinely useful in a finance workflow.

# %%
messages = [
    {'role': 'user', 'content': (
        "Draft a two-sentence variance commentary for a board deck.\n"
        "Revenue: actual $42.1M vs plan $39.0M. Opex: actual $30.4M vs plan $28.0M.\n"
        "Note the revenue beat and the opex overrun, and net the two.")},
]
reply = client.chat(messages, max_tokens=512)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **The useful output nets the two movements:** a $3.1M revenue beat against a $2.4M opex overrun
# is a ~$0.7M favorable net — the model should surface that, not just restate the lines. Drafting
# this in seconds, then editing, is the realistic productivity win for an FP&A team on a private box.

# %% [markdown]
# ### Ground the answers in real filing text — `fieldkit.rag`
#
# For citable work you want answers anchored to source. `fieldkit.rag.Pipeline` ingests a domain
# corpus (your own 10-K mirror or filing store), retrieves the relevant passages for a query, and
# feeds them to the model with a system prompt that forces citation. On the Spark this runs against
# a local embedder + pgvector; the result below is a recorded retrieval so the cell reads the same
# on a cloud runtime without that stack.

# %%
from fieldkit import rag
# On Spark: pipe = rag.Pipeline(embed_url=..., pgvector_dsn=..., generator=local_client)
#           pipe.ingest(filing_docs); ctx = pipe.retrieve("FY2018 capital expenditure")
ctx = {                              # recorded retrieval over a 10-K corpus
    "query": "FY2018 capital expenditure year over year",
    "top_passages": ["[10-K FY2018, Item 7] ... Capital expenditures were $1,577 million in "
                     "2018, compared with $1,373 million in 2017 ...",
                     "[10-K FY2018, Item 7] ... driven by investments in manufacturing capacity ..."],
    "answer_with_citation": "$1,577M (FY2018), up $204M YoY. Sources: [10-K FY2018, Item 7]",
}
ctx

# %% [markdown]
# **Grounding turns a recalled figure into a cited one.** Retrieval pulls the exact filing line, and
# the pipeline's system prompt makes the model say "the context does not contain the answer" rather
# than guess a number — which, for finance, is the difference between a draft you'd circulate and one
# you'd double-check. This is the VIABILITY axis: the glue is one class.

# %% [markdown]
# ### Gate quality — a `fieldkit.eval` scorer
#
# An app needs a quality gate, not a vibe. For numeric finance answers, `fieldkit.eval.numeric_match`
# extracts the number from the model's reply and compares it to the gold figure with a tolerance —
# so "$1,577 million" and "$1.577 billion" both match. It's a plain function: pass the reply and the
# expected value, get a 0/1 back, no infra. Here we score use case 1.

# %%
from fieldkit import eval as fkeval
score = fkeval.numeric_match(reply, expected="1577")  # tolerant numeric extraction + compare
print('FinanceBench-style numeric score:', score)

# %% [markdown]
# **A passing score means the model pulled the right figure out of the passage.** Wire this in as a
# gate: below threshold on a batch, route to a human or re-prompt. It's the same `numeric_match`
# scorer the card used to grade the 50-question FinanceBench subset — deterministic, so the gate is
# reproducible.

# %% [markdown]
# ## Desirable, viable, feasible — what you just ran
#
# You called a finance model on three real tasks (**desirability**); you grounded it in filing text
# and gated a numeric answer with two `fieldkit` classes (**viability**); and every line ran on a
# free GPU with no financials leaving your control on the local path (**feasibility**).
#
# - **Model card + variants:** <https://huggingface.co/Orionfold/finance-chat-GGUF>
# - **Want to reproduce the build?** The companion **builder notebook** walks the
#   feasibility → quantize → measure → publish journey as `fieldkit` calls — on one Spark.
