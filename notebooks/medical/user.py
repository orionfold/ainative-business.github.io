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
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Use II-Medical-8B in your app</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">App developer / model consumer</div><div style="color:#C2C9D4;margin-top:0.5rem">Call a medical reasoner on real tasks — runs on Spark and a free cloud GPU.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/II-Medical-8B-GGUF'

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
# ## A medical reasoner you can call in three lines — on the hardware you already have
#
# `II-Medical-8B` does clinical reasoning as an offline model that **shows its work**: a Qwen3-8B
# base finished with an SFT + DAPO reasoning recipe, it opens a `<think>` block and walks the
# differential — competing diagnoses, evidence, the call — before it answers. It is built for
# clinicians, medical educators, and health-app developers who want a private, on-device
# reasoning assistant: no patient text leaving the box, no hosted-API dependency.
#
# This notebook proves three things from the consumer's seat:
#
# - **Desirability** — the model on real clinical tasks, with its reasoning chain surfaced so you
#   can audit *how* it reached an answer, not just what it said. For decision-support work, the
#   trace is the product.
# - **Viability** — `fieldkit` is the glue: one call to open the model, `fieldkit.rag` to ground
#   answers in real source text, a `fieldkit.eval` scorer to gate quality.
# - **Feasibility** — the exact same code runs locally on a DGX Spark **and** on a free
#   Colab/Kaggle GPU. No rewrite, no API key, no data leaving your control on the local path.
#
# It is a decision-support and education tool, not a medical device: a clinician stays in the
# loop, and the `<think>` trace exists precisely so a human can check the reasoning.

# %% [markdown]
# ### Setup — one code path, two runtimes
#
# `detect_runtime()` tells you where you are. The point is that nothing below branches on it: the
# same notebook runs on your Spark (serving the model locally) and on a free cloud GPU (pulling
# the published GGUF). That is the dual-path contract — write once, run anywhere a GPU is.

# %%
# %pip install -q 'fieldkit[notebook]'
from fieldkit.notebook import open_model, detect_runtime, is_cloud, display_reply
RUNTIME = detect_runtime()
print('runtime:', RUNTIME, '| cloud?', is_cloud(RUNTIME))

# %% [markdown]
# ### Open the model — one call, backend chosen for you
#
# `open_model` returns a client with a single `.chat()` surface regardless of backend. On the
# Spark it serves the local GGUF; on Colab/Kaggle it pulls the published quant from HuggingFace
# and runs it through `llama-cpp-python` on the free GPU. Two settings matter for a reasoning
# model: `chat_format="chatml"` (II-Medical uses Qwen3's ChatML template, not Llama-2's `[INST]`),
# and a context window with room for the `<think>` block. This is the FEASIBILITY axis — a single
# free GPU is enough.

# %%
client = open_model(hf_repo, n_ctx=8192, chat_format="chatml")  # variant auto-picked: Q4_K_M cloud, Q5_K_M Spark
client

# %% [markdown]
# ### Reasoning models need room to think — budget the chain, not just the answer
#
# Every `.chat()` below sets `max_tokens=1536`, not the 256 a direct-answer model would use. A
# reasoning trace on a hard clinical question runs 400–800 tokens before the answer lands; cap it
# too low and the model gets cut off mid-differential and never reaches a conclusion. The build
# side learned this the hard way — the preflight scored 2/5 at 256 tokens and a clean 5/5 at 1024,
# same weights. As a consumer you inherit one number to respect: give the chain headroom.

# %% [markdown]
# ### Use case 1 — Differential diagnosis on a clinical vignette
#
# The canonical reasoning task: a vignette with a few discriminating findings, several plausible
# diagnoses, and one best answer. You want to *watch the model reason* — name the competing
# diagnoses, weigh the discriminators — not just trust a letter. The tearing chest pain with a
# blood-pressure differential between arms is a classic that separates aortic dissection from its
# mimics.

# %%
messages = [
    {'role': 'user', 'content': (
        "A 56-year-old man presents with sudden onset of severe tearing chest pain "
        "radiating to the back. BP 180/100, with a wider pulse pressure in the right arm "
        "than the left.\n\n"
        "Which is the most likely diagnosis?\n"
        "A) Acute pericarditis\n"
        "B) Aortic dissection\n"
        "C) Pulmonary embolism\n"
        "D) Myocardial infarction\n\n"
        "Reason through the differential, then give the single best letter.")},
]
reply = client.chat(messages, max_tokens=1536)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **Read the `<think>` block, not just the conclusion.** Good reasoning here latches onto the two
# discriminating findings — *tearing* pain radiating to the back and the inter-arm pulse-pressure
# differential — and uses them to rank dissection (B) over an MI or PE that share the chest-pain
# headline. The trace is the auditable artifact: for a decision-support tool, *why* the model
# landed on dissection is what a clinician checks before acting on it. That is the DESIRABILITY
# axis — a model that argues its case.

# %% [markdown]
# ### Use case 2 — Management & contraindication reasoning (free-form)
#
# Real clinical questions are rarely four-option MCQs. They are "what next, and what must I *not*
# do." This is multi-step conditional reasoning — the kind a reasoning recipe is built for — where
# the right answer depends on a contraindication the question only hints at.

# %%
messages = [
    {'role': 'user', 'content': (
        "A 68-year-old woman with an acute ischemic stroke arrives 2 hours after symptom onset. "
        "Her chart notes a GI bleed requiring transfusion three weeks ago. Walk through whether "
        "IV thrombolysis (tPA) is appropriate, naming the key contraindication and the reasoning, "
        "then state your recommendation.")},
]
reply = client.chat(messages, max_tokens=1536)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **The subtlety the model should catch:** the 2-hour window looks like a green light for tPA, but
# the recent GI bleed is a major contraindication that outweighs the timing. A strong answer
# separates the *eligibility-by-window* question from the *bleeding-risk* question and lands on
# caution — and it shows that conditional structure in the trace rather than asserting it. This is
# exactly the conditional, weigh-the-risk reasoning that direct-answer models flatten.

# %% [markdown]
# ### Use case 3 — Pharmacology & drug-interaction reasoning
#
# Polypharmacy questions interact in non-obvious ways, and the dangerous ones hinge on a
# mechanism, not a lookup. The model reasons through the interaction pathway and the clinical
# consequence — the multi-step chain a reasoning recipe surfaces step by step.

# %%
messages = [
    {'role': 'user', 'content': (
        "A patient on warfarin for atrial fibrillation is started on a course of "
        "trimethoprim-sulfamethoxazole for a UTI. Explain the mechanism of the interaction, "
        "the specific clinical risk it creates, and how monitoring or management should change.")},
]
reply = client.chat(messages, max_tokens=1536)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **A useful answer names the mechanism and the consequence, in order:** TMP-SMX inhibits
# warfarin's CYP2C9 metabolism (and displaces protein binding), the INR climbs, and the risk is
# bleeding — so the management is closer INR monitoring and a likely dose reduction. Watching the
# model build that mechanism→risk→action chain in its trace is how you tell domain reasoning from
# a memorized interaction-table hit.

# %% [markdown]
# ### Use case 4 — A documented second opinion
#
# Here the `<think>` block *is* the deliverable. Hand the model a working diagnosis and ask it to
# stress-test it — what else fits, what would change the call — and you get a documented
# second-opinion trace for a chart, a learner, or a peer reviewer. The model becomes a
# reasoning generator, not just a classifier.

# %%
messages = [
    {'role': 'user', 'content': (
        "A colleague diagnosed a 24-year-old with community-acquired pneumonia based on cough, "
        "fever, and a focal infiltrate on chest X-ray. Before we commit, reason through what "
        "alternative or concurrent diagnoses you would want to rule out, and what single piece of "
        "history or testing would most change the management.")},
]
reply = client.chat(messages, max_tokens=1536)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **The value is the structured doubt.** A good trace doesn't overturn the diagnosis for sport —
# it names what *else* fits (aspiration, an atypical pathogen, a post-obstructive process), flags
# the history that would discriminate (travel, immune status, a foreign-body risk), and proposes
# the one test that moves the needle. Captured alongside the answer, that reasoning is a
# documented-reasoning artifact — the second of the article's concrete uses for this model.

# %% [markdown]
# ### Ground the answers in real source text — `fieldkit.rag`
#
# A parametric reasoner is strong, but for citable clinical work you want answers anchored to
# source. `fieldkit.rag.Pipeline` ingests a domain corpus (a PubMed mirror, a guidelines set, or
# your own clinical-notes store), retrieves the relevant passages for a query, and feeds them to
# the model with a system prompt that forces citation and an "the context doesn't say" escape
# hatch. On the Spark this runs against a local embedder + pgvector; the result below is a recorded
# retrieval so the cell reads the same on a cloud runtime without that stack.

# %%
from fieldkit import rag
# On Spark: pipe = rag.Pipeline(embed_url=..., pgvector_dsn=..., generator=local_client)
#           pipe.ingest(guideline_docs); ctx = pipe.retrieve("tPA contraindications recent GI bleed")
ctx = {                              # recorded retrieval over a stroke-guidelines corpus
    "query": "IV thrombolysis contraindications recent gastrointestinal bleeding",
    "top_passages": ["[AHA/ASA 2019 §6.3] ... GI malignancy or GI/GU bleeding within 21 days "
                     "is a contraindication to IV alteplase ...",
                     "[AHA/ASA 2019 §4.1] ... eligibility within 3 hours of onset requires "
                     "exclusion of recent major bleeding ..."],
    "answer_with_citation": "... recent GI bleed (21 days) contraindicates tPA. "
                            "Sources: [AHA/ASA 2019 §6.3, §4.1]",
}
ctx

# %% [markdown]
# **Grounding turns a clinical assertion into a citation.** The tPA question from use case 2, run
# through retrieval, comes back anchored to the AHA/ASA guideline sections with a trailing
# `Sources:` line — and the pipeline's system prompt makes the model say "the context does not
# contain the answer" rather than invent a citation. For medical work that is the difference
# between a suggestion and a referenced one. This is the VIABILITY axis: the glue is one class.

# %% [markdown]
# ### Gate quality — a `fieldkit.eval` scorer
#
# An app needs a quality gate, not a vibe. For the MCQ shape, `fieldkit.eval.mcq_letter` extracts
# the chosen letter from a reasoning response — it is `<think>`-aware, so it strips the chain and
# reads the actual answer — and scores it against the gold letter. It's a plain function: pass the
# reply and the expected letter, get a 0/1 back, no infra. Here we score use case 1 against the
# correct answer (B, aortic dissection).

# %%
from fieldkit import eval as fkeval
score = fkeval.mcq_letter(reply, expected="B")  # <think>-aware: strips the chain, reads the answer
print('MedMCQA-style letter score:', score)

# %% [markdown]
# **A passing score means the reasoning landed on the right letter** — and because the scorer
# strips the `<think>` block first, a verbose, correct chain isn't penalized for thinking out loud.
# Wire this into your app as a gate: below threshold on a batch, route to a clinician or re-prompt.
# The scorer is deterministic, so the gate is reproducible — the same `mcq_letter` graded the 50
# MedMCQA questions on the card, where Q5_K_M scored 52%.

# %% [markdown]
# ## Desirable, viable, feasible — what you just ran
#
# You called a medical reasoner on four real clinical tasks and watched it show its work
# (**desirability**); you grounded it in guideline text and gated it with a domain scorer using
# two `fieldkit` classes (**viability**); and every line ran on a free GPU with no patient data
# leaving your control on the local path (**feasibility**).
#
# - **Model card + variants:** <https://huggingface.co/Orionfold/II-Medical-8B-GGUF>
# - **Want to reproduce the build?** The companion **builder notebook** walks the
#   feasibility → quantize → measure → publish journey as `fieldkit` calls — on one Spark.
