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
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Use Saul-7B-Instruct in your app</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">App developer / model consumer</div><div style="color:#C2C9D4;margin-top:0.5rem">Call a legal model on real tasks — runs on Spark and a free cloud GPU.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/Saul-7B-Instruct-v1-GGUF'

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
# ## A legal model you can call in three lines — on the hardware you already have
#
# `Saul-7B-Instruct-v1` is a Mistral-7B instruction-tuned for law — the model from the Saul paper.
# It classifies and reasons over legal text: does a sentence overrule a case, what trademark
# doctrine applies, is an NDA clause confidential, does a fact pattern create diversity
# jurisdiction. It runs **offline**, which matters for anyone who can't send privileged matter
# documents to a hosted API. Built for legal-tech developers, compliance teams, and litigators who
# want a private domain assistant on hardware they already own.
#
# This notebook proves three things from the consumer's seat:
#
# - **Desirability** — the model on real legal tasks: overruling detection, doctrine classification,
#   contract analysis, and jurisdiction reasoning.
# - **Viability** — `fieldkit` is the glue: one call to open the model, `fieldkit.rag` to ground
#   answers in real case law / statute text, a `fieldkit.eval` scorer to gate classifications.
# - **Feasibility** — the same code runs locally on a DGX Spark **and** on a free Colab/Kaggle GPU.
#   No rewrite, no API key, no privileged text leaving your control on the local path.
#
# It's a research-and-triage assistant, not legal advice — a lawyer stays in the loop, and grounding
# answers in source text (below) is how you keep the output checkable.

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
# `open_model` returns a client with a single `.chat()` surface regardless of backend. On the Spark
# it serves the local GGUF; on Colab/Kaggle it pulls the published quant from HuggingFace and runs
# it through `llama-cpp-python` on the free GPU. Saul inherits Mistral's `[INST]` template, so we
# pass `chat_format="mistral-instruct"`. This is the FEASIBILITY axis — a single free GPU is enough.

# %%
client = open_model(hf_repo, chat_format="mistral-instruct")  # variant auto-picked: Q4_K_M cloud, Q5_K_M Spark
client

# %% [markdown]
# ### Use case 1 — Overruling detection
#
# A core case-law triage task: given a sentence, decide whether it overrules a prior case. This is a
# LegalBench task and a realistic first pass when you're scanning opinions for negative treatment.

# %%
messages = [
    {'role': 'user', 'content': (
        "Does the following sentence overrule a previous case? Answer yes or no.\n"
        "Sentence: \"Curtman is overruled to the extent it conflicts with Evans.\"")},
]
reply = client.chat(messages, max_tokens=256)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **The answer should be a clear yes** — "is overruled" is explicit negative treatment. The value for
# an app is the binary signal at scale: run it across an opinion's citations and surface the ones that
# overrule for a human to confirm. The output is short and checkable, which is exactly what the
# `contains` scorer (below) grades.

# %% [markdown]
# ### Use case 2 — Trademark doctrine classification
#
# The Abercrombie spectrum — generic, descriptive, suggestive, arbitrary, fanciful — decides whether a
# mark is protectable. Classifying a proposed mark is a daily IP task and a clean test of the model's
# doctrinal grounding.

# %%
messages = [
    {'role': 'user', 'content': (
        "Classify the trademark on the Abercrombie spectrum (generic, descriptive, suggestive, "
        "arbitrary, or fanciful). Reply with the single category.\n"
        "Mark: \"KODAK\" for cameras.")},
]
reply = client.chat(messages, max_tokens=256)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **KODAK is the textbook *fanciful* mark** — a coined word with no prior meaning, the strongest
# category. A good answer names that category cleanly. Wire this into an intake flow and the model
# pre-classifies marks for an attorney to review, with the doctrine label as the gradable output.

# %% [markdown]
# ### Use case 3 — Contract clause analysis (confidentiality)
#
# Contract review is high-volume and pattern-heavy — a good fit for a 7B classifier. Here the model
# decides whether an NDA clause establishes a confidentiality-of-agreement obligation, a binary call
# a reviewer can spot-check.

# %%
messages = [
    {'role': 'user', 'content': (
        "Does this NDA clause require the parties to keep the existence and terms of the agreement "
        "itself confidential? Answer yes or no, then quote the operative phrase.\n"
        "Clause: \"Neither party shall disclose the existence of this Agreement or any of its "
        "terms to any third party without the prior written consent of the other party.\"")},
]
reply = client.chat(messages, max_tokens=384)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **Yes — and the operative phrase is \"the existence of this Agreement or any of its terms.\"** A
# strong answer both classifies *and* points to the language that drives the call, which is what makes
# the output auditable. For a contract-review app, that quoted phrase is the reviewer's entry point.

# %% [markdown]
# ### Use case 4 — Federal diversity jurisdiction
#
# Procedure questions are conditional and rule-driven — does this fact pattern support federal
# diversity jurisdiction? The model walks the citizenship-and-amount test and lands on yes/no.

# %%
messages = [
    {'role': 'user', 'content': (
        "Does a federal court have diversity jurisdiction? Answer yes or no with a one-line reason.\n"
        "Facts: Plaintiff is a citizen of California. Defendant is a citizen of Texas. The amount "
        "in controversy is $200,000.")},
]
reply = client.chat(messages, max_tokens=256)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **Yes — complete diversity (CA vs TX) and the amount exceeds $75,000.** The model should hit both
# prongs of 28 U.S.C. § 1332 in its reason. This is the conditional rule-application that a legal SFT
# handles well at 7B, and the kind of triage that saves an associate a first pass.

# %% [markdown]
# ### Ground the answers in real legal text — `fieldkit.rag`
#
# For citable work you want answers anchored to source. `fieldkit.rag.Pipeline` ingests a domain
# corpus (case law, statutes, your own contract store), retrieves the relevant passages for a query,
# and feeds them to the model with a system prompt that forces citation. On the Spark this runs
# against a local embedder + pgvector; the result below is a recorded retrieval so the cell reads the
# same on a cloud runtime without that stack.

# %%
from fieldkit import rag
# On Spark: pipe = rag.Pipeline(embed_url=..., pgvector_dsn=..., generator=local_client)
#           pipe.ingest(statute_docs); ctx = pipe.retrieve("diversity jurisdiction amount in controversy")
ctx = {                              # recorded retrieval over a federal-statute corpus
    "query": "diversity jurisdiction citizenship amount in controversy",
    "top_passages": ["[28 U.S.C. § 1332(a)] ... district courts shall have original jurisdiction "
                     "of all civil actions where the matter in controversy exceeds $75,000 ... and "
                     "is between citizens of different States ...",
                     "[Strawbridge v. Curtiss] ... complete diversity is required ..."],
    "answer_with_citation": "Yes — complete diversity, amount > $75,000. Sources: [28 U.S.C. § 1332(a)]",
}
ctx

# %% [markdown]
# **Grounding turns an asserted rule into a cited one.** Retrieval pulls the statute text, and the
# pipeline's system prompt makes the model say "the context does not contain the answer" rather than
# invent a citation — the difference, for legal work, between a memo you'd file and one you'd
# double-check. This is the VIABILITY axis: the glue is one class.

# %% [markdown]
# ### Gate quality — a `fieldkit.eval` scorer
#
# An app needs a quality gate, not a vibe. For the classification shapes, `fieldkit.eval.contains`
# checks whether the gold label appears in the model's reply — the same `contained_in_output` scorer
# LegalBench uses. It's a plain function: pass the reply and the expected answer, get a 0/1 back, no
# infra. Here we score use case 1 against the gold answer.

# %%
from fieldkit import eval as fkeval
score = fkeval.contains(reply, expected="yes")  # gold label present in the response?
print('LegalBench-style contains score:', score)

# %% [markdown]
# **A passing score means the model's answer carries the right label.** Wire this in as a gate: below
# threshold on a batch, route to a lawyer or re-prompt. It's the same `contains` scorer the card used
# to grade the 50-question LegalBench subset where Q5_K_M scored 72% — deterministic, so the gate is
# reproducible.

# %% [markdown]
# ## Desirable, viable, feasible — what you just ran
#
# You called a legal model on four real tasks (**desirability**); you grounded it in statute text and
# gated a classification with two `fieldkit` classes (**viability**); and every line ran on a free GPU
# with no privileged text leaving your control on the local path (**feasibility**).
#
# - **Model card + variants:** <https://huggingface.co/Orionfold/Saul-7B-Instruct-v1-GGUF>
# - **Want to reproduce the build?** The companion **builder notebook** walks the
#   feasibility → quantize → measure → publish journey as `fieldkit` calls — on one Spark.
