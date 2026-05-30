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
# <div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif"><div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Orionfold · ai-field-notes</div><div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">Use SecurityLLM in your app</div><div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">App developer / model consumer</div><div style="color:#C2C9D4;margin-top:0.5rem">Call a cybersecurity model on real tasks — runs on Spark and a free cloud GPU.</div></div>

# %% tags=["parameters"]
# Parameters — overridable by papermill / Colab form.
runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"
hf_repo = 'Orionfold/SecurityLLM-GGUF'

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
# ## A cybersecurity model you can call in three lines — on the hardware you already have
#
# `SecurityLLM` is a Mistral-7B + Zephyr-DPO fine-tune for cybersecurity: it answers security
# multiple-choice and reasoning questions across cryptography, network security, identity, and
# governance. It runs **offline**, which is the point for a SOC or a security team that can't send
# incident detail or proprietary config to a hosted API. Built for security practitioners, threat
# analysts, and developers building security tooling on hardware they already own.
#
# This notebook proves three things from the consumer's seat:
#
# - **Desirability** — the model on real security tasks: domain MCQ, threat reasoning, and policy
#   evaluation.
# - **Viability** — `fieldkit` is the glue: one call to open the model, `fieldkit.rag` to ground
#   answers in CVE / advisory text, a `fieldkit.eval` scorer to gate MCQ answers.
# - **Feasibility** — the same code runs locally on a DGX Spark **and** on a free Colab/Kaggle GPU.
#   No rewrite, no API key, no incident detail leaving your control on the local path.
#
# It's a knowledge-and-triage assistant, not an autonomous defender — an analyst stays in the loop,
# and grounding answers in source advisories (below) keeps the output checkable.

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
# it through `llama-cpp-python` on the free GPU. **The chat format is non-negotiable here**:
# SecurityLLM is Zephyr-DPO, so we pass `chat_format="zephyr"` — Mistral's `[INST]` template would
# corrupt the responses. This is the FEASIBILITY axis — a single free GPU is enough.

# %%
client = open_model(hf_repo, chat_format="zephyr")  # variant auto-picked: Q4_K_M cloud, Q5_K_M Spark
client

# %% [markdown]
# ### Use case 1 — Security knowledge MCQ
#
# The model's core competency: domain multiple-choice across CyberMetric's nine areas. One practical
# note up front — Zephyr-DPO models are verbose by default, so the prompt explicitly demands a single
# letter. (The scorer below is `<think>`-free but prose-tolerant; it regex-extracts the letter even
# if the model adds a sentence.)

# %%
messages = [
    {'role': 'user', 'content': (
        "What is the primary purpose of a key-derivation function (KDF)?\n\n"
        "A) Generate public keys\n"
        "B) Authenticate digital signatures\n"
        "C) Encrypt data using a password\n"
        "D) Transform a secret into keys and initialization vectors\n\n"
        "Reply with only the single letter A, B, C, or D.")},
]
reply = client.chat(messages, max_tokens=256)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **The answer is D** — a KDF stretches a secret (a password or shared key) into one or more
# cryptographic keys and IVs; it doesn't encrypt or sign on its own. A correct, terse answer is the
# desirable behavior; if the model adds a justification sentence, the `mcq_letter` scorer below still
# reads the right letter out of it.

# %% [markdown]
# ### Use case 2 — Network-security MCQ
#
# A second domain to show breadth: the same MCQ shape over a network-security concept. This is the
# bulk shape for a security-knowledge app — a quiz engine, a certification trainer, a triage
# classifier.

# %%
messages = [
    {'role': 'user', 'content': (
        "Which attack does HSTS (HTTP Strict Transport Security) primarily mitigate?\n\n"
        "A) SQL injection\n"
        "B) SSL-stripping / protocol-downgrade man-in-the-middle\n"
        "C) Cross-site request forgery\n"
        "D) Buffer overflow\n\n"
        "Reply with only the single letter A, B, C, or D.")},
]
reply = client.chat(messages, max_tokens=256)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **The answer is B** — HSTS forces HTTPS so an attacker can't downgrade a connection to plaintext
# HTTP (the SSL-stripping MITM). The breadth across domains is what makes the model useful as a
# general security-knowledge surface rather than a single-topic tool.

# %% [markdown]
# ### Use case 3 — Threat reasoning from a log line
#
# Beyond MCQ, the model reasons over a security artifact. Hand it a suspicious log line and ask what
# it suggests — the free-form triage a SOC analyst does dozens of times a shift.

# %%
messages = [
    {'role': 'user', 'content': (
        "A web server access log shows hundreds of requests in seconds, all to paths like "
        "\"/?id=1' OR '1'='1\" and \"/?id=1 UNION SELECT\". In two sentences: what is this, and "
        "what is the immediate mitigation?")},
]
reply = client.chat(messages, max_tokens=384)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **A strong answer names it as an SQL-injection probe / automated scan and points to parameterized
# queries + a WAF rule as the immediate mitigation.** The value for an app is the first-pass triage:
# the model labels the pattern and suggests the control, and an analyst confirms — turning raw log
# noise into a starting hypothesis.

# %% [markdown]
# ### Use case 4 — Governance & compliance MCQ
#
# CyberMetric spans governance too. Policy and compliance questions are a realistic enterprise use —
# a control-mapping assistant, a policy quiz, an onboarding trainer.

# %%
messages = [
    {'role': 'user', 'content': (
        "Under the principle of least privilege, how should a new employee's access be provisioned?\n\n"
        "A) Grant broad access up front and revoke what's unused later\n"
        "B) Grant only the access required for their specific role, adding more on justified request\n"
        "C) Mirror the access of a peer in a different department\n"
        "D) Grant administrator access to avoid future tickets\n\n"
        "Reply with only the single letter A, B, C, or D.")},
]
reply = client.chat(messages, max_tokens=256)
display_reply(reply)   # reasoning box (if any) + answer as markdown

# %% [markdown]
# **The answer is B** — least privilege means provisioning the minimum for the role and expanding only
# on justified need. Governance MCQ like this is where a security model earns a place in compliance
# tooling: consistent, fast, and gradable against a policy answer key.

# %% [markdown]
# ### Ground the answers in real advisory text — `fieldkit.rag`
#
# For citable work you want answers anchored to source. `fieldkit.rag.Pipeline` ingests a domain
# corpus (a CVE feed, MITRE ATT&CK, NIST/RFC text, your own advisories), retrieves the relevant
# passages for a query, and feeds them to the model with a system prompt that forces citation. On the
# Spark this runs against a local embedder + pgvector; the result below is a recorded retrieval so the
# cell reads the same on a cloud runtime without that stack.

# %%
from fieldkit import rag
# On Spark: pipe = rag.Pipeline(embed_url=..., pgvector_dsn=..., generator=local_client)
#           pipe.ingest(advisory_docs); ctx = pipe.retrieve("HSTS downgrade mitigation")
ctx = {                              # recorded retrieval over a security-advisory corpus
    "query": "HSTS protocol downgrade mitigation",
    "top_passages": ["[RFC 6797 §2.2] ... HSTS enables web sites to declare that browsers should "
                     "only interact with them over secure HTTPS connections ...",
                     "[MITRE ATT&CK T1557] ... adversary-in-the-middle: SSL stripping downgrades "
                     "HTTPS to HTTP ..."],
    "answer_with_citation": "HSTS mitigates SSL-stripping downgrade MITM. Sources: [RFC 6797, ATT&CK T1557]",
}
ctx

# %% [markdown]
# **Grounding turns a recalled fact into a cited one.** Retrieval pulls the RFC and ATT&CK text, and
# the pipeline's system prompt makes the model say "the context does not contain the answer" rather
# than invent a CVE number — which, for security work, is the difference between an advisory you'd act
# on and one you'd verify. This is the VIABILITY axis: the glue is one class.

# %% [markdown]
# ### Gate quality — a `fieldkit.eval` scorer
#
# An app needs a quality gate, not a vibe. For the MCQ shape, `fieldkit.eval.mcq_letter` extracts the
# chosen letter from the reply — it's prose-tolerant, so a verbose Zephyr answer that buries the letter
# in a sentence still scores — and compares it to the gold letter. It's a plain function: pass the
# reply and the expected letter, get a 0/1 back, no infra. Here we score use case 1 (gold answer D).

# %%
from fieldkit import eval as fkeval
score = fkeval.mcq_letter(reply, expected="D")  # word-bounded letter extraction, prose-tolerant
print('CyberMetric-style letter score:', score)

# %% [markdown]
# **A passing score means the model picked the right option** — and because the scorer regex-extracts
# the letter, the model's habit of adding a justification sentence doesn't cost it the point. Wire this
# in as a gate: below threshold on a batch, route to an analyst or re-prompt. It's the same `mcq_letter`
# scorer the card used to grade the 50-question CyberMetric subset — deterministic, so the gate is
# reproducible. (This scorer debuted on the cyber card and was later reused by medical.)

# %% [markdown]
# ## Desirable, viable, feasible — what you just ran
#
# You called a security model on four real tasks (**desirability**); you grounded it in advisory text
# and gated an MCQ answer with two `fieldkit` classes (**viability**); and every line ran on a free GPU
# with no incident detail leaving your control on the local path (**feasibility**).
#
# - **Model card + variants:** <https://huggingface.co/Orionfold/SecurityLLM-GGUF>
# - **Want to reproduce the build?** The companion **builder notebook** walks the
#   feasibility → quantize → measure → publish journey as `fieldkit` calls — on one Spark.
