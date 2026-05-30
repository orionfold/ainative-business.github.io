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
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Use patent-strategist in your app</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">App developer / model consumer</div><div style="color:#C2C9D4;margin-top:0.5rem">Call the model on real tasks — runs on Spark and a free cloud GPU.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/patent-strategist-v3-nemo-GGUF'
variant = 'Q5_K_M'  # the fast+accurate sweet spot on Spark — see the open-model cell

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
# ## A patent reasoner you can call in three lines — on the hardware you already have
#
# `patent-strategist-v3` does claim construction, MPEP-grounded office-action argument
# drafting, prior-art reasoning, and licensing analysis as an offline reasoning model — it
# shows its `<think>` work before it answers. It is built for patent attorneys, prosecution
# engineers, and IP-strategy teams who **cannot** ship privileged client text to a hosted
# frontier API.
#
# This notebook proves three things from the consumer's seat:
#
# - **Desirability** — the model on real patent tasks, with its reasoning chain surfaced so
#   you can audit *how* it got there, not just what it said.
# - **Viability** — `fieldkit` is the glue: one call to open the model, `fieldkit.rag` to
#   ground answers in real MPEP text, `fieldkit.eval` scorers to gate quality.
# - **Feasibility** — the exact same code runs locally on a DGX Spark **and** on a free
#   Colab/Kaggle GPU. No rewrite, no API key, no data leaving your control on the local path.

# %% [markdown]
# ### Setup — one code path, two runtimes
#
# `detect_runtime()` tells you where you are. The point is that nothing below branches on it:
# the same notebook runs on your Spark (serving the model locally) and on a free cloud GPU
# (pulling the published GGUF). That is the dual-path contract — write once, run anywhere a
# GPU is.

# %%
# %pip install -q 'fieldkit[notebook]'
from fieldkit.notebook import open_model, detect_runtime, is_cloud, display_reply
RUNTIME = detect_runtime()
print('runtime:', RUNTIME, '| cloud?', is_cloud(RUNTIME))

# %% [markdown]
# ### Open the model — one call, backend chosen for you
#
# `open_model` returns a client with a single `.chat()` surface regardless of backend. On the
# Spark it serves the local GGUF (or a NIM endpoint if one is up); on Colab/Kaggle it pulls
# the published quant from HuggingFace and runs it through `llama-cpp-python` on the free GPU.
# A reasoning model needs room to think, so we give it an 8K context window — the FEASIBILITY
# axis: a single free GPU is enough.
#
# We pin **Q5_K_M** — the fast+accurate sweet spot for local runs. Across the nemo GGUF sweep
# it holds 35 tok/s on a GB10 at 10.04 wikitext perplexity: within 0.8% of Q6_K's accuracy but
# 14% faster, and clearly sharper than Q4_K_M (10.24) on the legal-reasoning axis that matters.
# Heavier (Q6_K/Q8_0) or lighter (Q4_K_M) variants are one keyword away if your size/fidelity
# trade differs — the sibling GGUF card carries the full matrix.

# %%
client = open_model(hf_repo, variant=variant, n_ctx=8192)  # Q5_K_M — fast + accurate on Spark
client

# %% [markdown]
# ### Use case 1 — Claim construction (Markush groups & the doctrine of equivalents)
#
# Claim scope is the whole game in prosecution: a Markush group ("selected from the group
# consisting of…") is a closed list, and whether an unlisted member is captured under the
# doctrine of equivalents decides infringement. This is the kind of question where you want to
# *watch the model reason*, not just trust a one-line answer.

# %%
messages = [
    {'role': 'user', 'content': (
        "Claim 1 recites 'a halogen selected from the group consisting of fluorine, "
        "chlorine, and bromine.' The specification discloses only those three halogens. "
        "Construe the Markush limitation, then analyze whether iodine could be captured "
        "under the doctrine of equivalents. Show your reasoning.")},
]
reply = client.chat(messages, max_tokens=3000)
display_reply(reply)   # reasoning box (the <think> chain) + answer as markdown

# %% [markdown]
# **Read the `<think>` block, not just the conclusion.** Good reasoning here names the Markush
# group as a *closed* list, notes that the specification's silence on iodine cuts against
# equivalents, and reaches for the function-way-result test before committing. The reasoning
# trace is the auditable artifact — for privileged work, *why* the model concluded something is
# as important as the conclusion, and it's right there to check.

# %% [markdown]
# ### Use case 2 — MPEP-grounded office-action argument drafting
#
# The daily grind of prosecution is answering § 103 obviousness rejections. A good response
# does not just assert non-obviousness — it pins the argument to the examiner's burden under
# the MPEP (motivation to combine, the prima facie case) and to the specific gaps in the cited
# art.

# %%
messages = [
    {'role': 'user', 'content': (
        "An examiner rejected claim 1 under 35 U.S.C. § 103 as obvious over Smith in view "
        "of Jones. Smith teaches a pump with a steel housing; Jones teaches an aluminum "
        "housing for an unrelated audio device. Draft an argument that the examiner has not "
        "established a prima facie case of obviousness, grounding it in the MPEP's "
        "motivation-to-combine requirement.")},
]
reply = client.chat(messages, max_tokens=3000)
display_reply(reply)   # reasoning box (the <think> chain) + answer as markdown

# %% [markdown]
# **A strong draft attacks the motivation-to-combine link**, not just the elements: it argues
# a skilled artisan had no reason to look to an unrelated audio device for a pump housing, and
# it cites the examiner's burden to articulate a rationale. Watch whether the model's reasoning
# stays anchored to the MPEP framework — the next two cells show how to *force* that grounding
# and how to *score* it.

# %% [markdown]
# ### Use case 3 — Prior-art relevance & non-obviousness reasoning
#
# Before you argue a rejection you triage the art: which references actually bear on the claim,
# and in what order. The model reasons over the claim elements and the references to rank
# relevance for a § 103 analysis — the same triage a prosecution engineer does by hand.

# %%
messages = [
    {'role': 'user', 'content': (
        "Pending claim: a method with steps A, B, and C. Reference R1 teaches A and B; R2 "
        "teaches C but in a different technical field; R3 teaches only A. Rank R1, R2, R3 by "
        "relevance to a § 103 obviousness analysis of the claim, and explain whether a skilled "
        "artisan would have been motivated to combine them.")},
]
reply = client.chat(messages, max_tokens=3000)
display_reply(reply)   # reasoning box (the <think> chain) + answer as markdown

# %% [markdown]
# **The useful output is the ranking *plus* the rationale.** R1 (two of three elements) should
# top the list, R2's different-field teaching raises a motivation-to-combine question, and R3
# is weakest. A reasoning model earns its keep here by surfacing the combine-ability analysis
# explicitly — which is exactly what a `prior_art_relevance` scorer can grade.

# %% [markdown]
# ### Use case 4 — Licensing scenario analysis (most-favored-licensee & FTO)
#
# IP strategy is not only prosecution. Licensing terms interact in non-obvious ways — a
# most-favored-licensee clause can reach across deals — and freedom-to-operate questions gate
# product launches. The model reasons through the contract logic and the FTO risk.

# %%
messages = [
    {'role': 'user', 'content': (
        "Licensee A holds a non-exclusive license with a most-favored-licensee clause at a 4% "
        "royalty. We later grant Licensee B a 2.5% rate bundled with a cross-license. Does A's "
        "MFL clause entitle it to the 2.5% rate? Separately, summarize the freedom-to-operate "
        "risk if our product reads on a third party's unexpired claim.")},
]
reply = client.chat(messages, max_tokens=3000)
display_reply(reply)   # reasoning box (the <think> chain) + answer as markdown

# %% [markdown]
# **The subtlety the model should catch:** a bundled cross-license is not a clean royalty
# comparison, so whether the MFL clause triggers turns on how "more favorable terms" is
# defined — rarely a flat yes. On FTO, a strong answer separates the *infringement* question
# from the *validity/design-around* options. Reasoning models are well-suited to this because
# the analysis is multi-step and conditional.

# %% [markdown]
# ### Ground the answers in real MPEP text — `fieldkit.rag`
#
# A parametric reasoner is strong, but for citable work you want answers anchored to source.
# `fieldkit.rag.Pipeline` ingests a domain corpus (here, MPEP excerpts), retrieves the
# relevant passages for a query, and feeds them to the model with a system prompt that forces
# citation. On the Spark this runs against a local embedder + pgvector; the result below is a
# recorded retrieval so the cell reads the same on a cloud runtime without that stack.

# %%
from fieldkit import rag
# On Spark: pipe = rag.Pipeline(embed_url=..., pgvector_dsn=..., generator=nim_client)
#           pipe.ingest(mpep_docs); ctx = pipe.retrieve("motivation to combine under 103")
ctx = {                              # recorded retrieval over MPEP excerpts
    "query": "motivation to combine under 35 U.S.C. 103",
    "top_passages": ["[MPEP 2143.01] ... a suggestion or motivation to modify ...",
                     "[MPEP 2142] ... the examiner bears the burden of a prima facie case ..."],
    "answer_with_citation": "... Sources: [MPEP 2143.01, MPEP 2142]",
}
ctx

# %% [markdown]
# **Grounding turns an assertion into a citation.** The same office-action argument from use
# case 2, run through retrieval, comes back anchored to `MPEP 2143.01` and `MPEP 2142` with a
# trailing `Sources:` line — and the pipeline's system prompt makes the model say "the context
# does not contain the answer" rather than invent one. That is the difference between a draft
# you'd file and a draft you'd double-check. This is the VIABILITY axis: the glue is one class.

# %% [markdown]
# ### Gate quality — `fieldkit.eval` scorers
#
# An app needs a quality gate, not a vibe. `fieldkit.eval` ships domain scorers for exactly
# these shapes — `irac_structure`, `office_action_argument`, `patent_claim_validity`,
# `prior_art_relevance`. They're plain functions: pass the model's reply, get a score back, no
# infra required. Here we score the last reply for IRAC structure.

# %%
from fieldkit import eval as fkeval
score = fkeval.irac_structure(reply)   # 0..1 — does the answer carry Issue/Rule/Application/Conclusion?
print('IRAC structure score:', score)

# %% [markdown]
# **A passing IRAC score means the answer is shaped like legal analysis** — it states the
# issue, names the rule, applies it to the facts, and concludes — which is the structure a
# prosecution argument has to have to be useful. Wire this scorer into your app as a gate:
# below a threshold, route to a human or re-prompt. The scorer is deterministic, so the gate is
# reproducible.

# %% [markdown]
# ### Optional — watch it reason live (streaming)
#
# The cells above call `client.chat(...)` and render the finished reply, which keeps re-runs
# deterministic. For a live demo, `stream_reply` drives the same client token-by-token: the
# reasoning box fills as the model thinks, then the answer renders below. It returns the full
# reply string, so you can still score or store it. This is opt-in — leave the use-case cells
# on `display_reply` for clean snapshots.

# %%
from fieldkit.notebook import stream_reply
live = stream_reply(client, [
    {'role': 'user', 'content': (
        "In one paragraph: is 'consisting of' in a Markush claim open or closed, "
        "and why does that distinction matter for infringement? Reason briefly first.")},
], max_tokens=1200, temperature=0.6)

# %% [markdown]
# **Same model, same `.chat` surface — just streamed.** `stream_reply` is sugar over
# `client.chat_stream(...)`, which every `fieldkit` `ChatClient` implements (the OpenAI-compatible
# server path parses SSE; the in-process llama.cpp path streams the engine). Reach for it in an
# interactive session; keep `display_reply(client.chat(...))` for reproducible notebook output.

# %% [markdown]
# ## Desirable, viable, feasible — what you just ran
#
# You called a patent reasoner on four real tasks and watched it show its work
# (**desirability**); you grounded it in MPEP text and gated it with a domain scorer using two
# `fieldkit` classes (**viability**); and every line ran on a free GPU with no privileged data
# leaving your control on the local path (**feasibility**).
#
# - **Model card + variants:** <https://huggingface.co/Orionfold/patent-strategist-v3-nemo-GGUF>
# - **Want to reproduce the build?** The companion **builder notebook** walks the full
#   baseline → corpus → train → quantize → publish journey as `fieldkit` calls — on one Spark.
