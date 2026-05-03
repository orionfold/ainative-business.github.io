---
title: "What the Agent Actually Built — Five Articles in Plain English, and Why You Probably Don't Want to Train From Scratch"
date: 2026-04-25
author: Manav Sehgal
product: Foundation
stage: foundations
difficulty: beginner
time_required: "~15 minute read · no GPU required"
hardware: "NVIDIA DGX Spark"
tags: [foundations, training, layman, autoresearch, dgx-spark, roadmap, lora, fine-tuning, pretrain]
summary: "Five technical articles in one day built an unattended AI research loop on a desk for $0.02 of electricity. The plain-English readout: what the agent built (not a usable model), what it changes for one person, and a four-tier roadmap from LoRA in minutes to from-scratch in weeks."
signature: FourKindsOfTraining
also_stages: [training, agentic]
series: Looking Beyond Spark
---

A reader who walked in cold today and read the five technical articles I shipped — `nemo-framework-on-spark`, `baseline-training-loop-on-spark`, `nemo-curator-training-data-prep`, `guardrails-for-code-generation`, and `autoresearch-agent-loop` — could be forgiven for coming away with the impression that I trained a custom language model on my desk. That impression is *almost* right and importantly wrong, in a way that most "personal AI" content doesn't bother to disambiguate. This article is the reset.

Two factual sentences first, in plain English: **For 73 minutes this afternoon, an LLM running on my desk decided what 50 different training experiments to try and ran them all by itself, without my involvement, while drawing about as much electricity as a desk lamp.** No model that the agent produced is useful for anything yet — every experiment was a 60-second taste-test, not a finished dish. That's the whole article in one paragraph; the rest is what those two sentences mean for someone who is curious about doing this themselves.

## What we actually did vs. what "training a model" usually means

The phrase **"I want to train a language model"** is one of the most-overloaded sentences in the AI vocabulary. Four very different things hide behind it, with costs that span four orders of magnitude. Most people who say "train" mean one of the cheaper rows in the table below. The agent loop in the [autoresearch-loop article](/articles/autoresearch-agent-loop/) is infrastructure for the *most* expensive row — but most readers' actual goal is served by a cheaper one.

| what people usually say | the canonical name | what it actually does | cost on a Spark | typical result |
|---|---|---|---:|---|
| "train a model" | **LoRA** / adapter | adds a few % of trainable weights on top of a frozen pre-trained model | minutes · ~$0.01 | model behaves slightly differently on your task |
| "train on my data" | **fine-tune** | updates all weights of a pre-trained model on a small dataset | hours · ~$0.30 | model takes on the style or knowledge of your data |
| "train my own model" | **continued pre-training** | extends the pre-training of an existing model with more general data | days · ~$5 | model gets a stronger base; mostly the same flavor |
| "train from scratch" | **pre-training** | random weights → useful model, learning the language from zero | weeks · ~$50 | a model that didn't exist before; usually *worse* than fine-tuning a comparable pre-trained one |

(The cost column is electricity only, on a Spark drawing 56 W. The hardware itself is a one-time purchase. Cloud equivalents are 50–500× higher.)

The five technical articles I published today were almost entirely about **the bottom row** — pre-training from scratch. The same agent loop ran 50 experiments where the model started from random weights every iteration and trained for one minute. That isn't a *training* run; it's a *recipe-tasting* run. A bread baker who's testing 50 different flour mixtures doesn't bake 50 loaves — they mix the dough for a minute and feel its texture, and they decide which mixtures are worth committing the oven time to. The agent did the equivalent. We never baked a loaf.

So no, **we don't have a custom-trained language model that you can ask questions to.** What we have is the *experimental kitchen*: an LLM driver that proposes recipes, safety rails that block bad recipes from touching the oven, an evaluator that measures how a recipe behaves in 60 seconds, and a logbook of what the agent tried. That kitchen is a useful artifact. It's not the same artifact as a finished model.

## What the Spark genuinely changes for one person

Even the recipe-tasting kitchen is something that, two years ago, you could not run on your desk. The five technical articles add up to a thesis worth saying plainly:

**For about $50 of equipment-amortization plus the price of running a desk lamp, a single person can now run an LLM-driven AI research loop overnight, on their own hardware, with no cloud account, no API keys, no rate limits, and no per-token bills.** Every part of that sentence used to require a vendor.

Three concrete things this changes, that the technical articles touch on but don't shout about:

- **Privacy actually flips.** When the model lives on your desk, the conversation never leaves your house. For personal data — your notes, your medical records, your code, your kids' photos — this is the difference between "trust a vendor's privacy policy" and "trust your own router."
- **Iteration speed becomes the constraint.** A cloud LLM round-trip is 200ms-2.5s. A local one is milliseconds-to-seconds. When you iterate on a prompt 100 times in an afternoon, that latency multiplied is the difference between flow and meeting-your-cloud-bill.
- **Failure becomes free.** This article's agent loop ran 50 experiments. **42 of them failed** (the model got worse, not better). On the cloud, every failed experiment costs real money and you'd start being conservative. On the Spark, every failed experiment costs a fraction of a cent of electricity, and you let the agent take chances.

The "personal AI power user" framing this blog has been pushing isn't hype. It's the literal arithmetic: $0.02 of electricity for 50 unattended AI experiments. The Spark earns its line on the spec sheet by making that cost real.

## What we didn't do — the gap between this experiment and a real trained model

To get from what we built today to a model you could actually use, you have to commit a lot more compute. The agent loop trained each candidate model for 60 steps. A model worth using needs roughly **6,000 to 60,000 times more training**. Concretely:

- **Each agent iteration trained on ~1 million tokens of text.** A real Chinchilla-optimal pretrain of a 354M-parameter model needs **~7 billion tokens** — about 7,000× more.
- **Each iteration's final loss number (val_bpb 10.85) is essentially noise.** A properly trained GPT-2-small on Wikipedia data sits at val_bpb ≈ 4 (a perplexity of about 16). Ours at 10.85 means perplexity ~1,850 — the model is barely above random for natural English.
- **We never saved any model's weights.** Each iteration's model was discarded after the val_bpb measurement. The agent's *decisions* are the artifact, not the models.
- **The agent worked with a tiny menu.** It could twist 13 specific knobs (model size, learning rate, etc.). It can't add a new layer type, change the optimizer, or alter the data pipeline. Those are the kinds of changes a human researcher makes; the agent operates inside the boundaries we drew.

Whether this matters depends on what you wanted out of the experiment. If you wanted a *trained model* — no, we don't have one. If you wanted a *measured methodology for finding good training recipes cheaply* — yes, we have that, and the trajectory log from that loop is the data you'd use to bootstrap a serious training run.

## Three roadmaps at architecture-glance

<figure class="fn-diagram" aria-label="Three parallel roadmaps from a starting line on the left to a 'your trained model' destination on the right. Top track: LoRA, minutes long, about one cent in electricity, suitable for matching brand voice or domain jargon. Middle track: fine-tune, hours long, about thirty cents, suitable for medical or legal specializations or teaching the model your private knowledge. Bottom track (highlighted as the path the article's technical pieces built infrastructure for): from-scratch pre-training, weeks long, about fifty dollars, suitable for niche domains, privacy-critical training, or learning by doing. The pivot text below the diagram notes that for most readers, the top or middle path is what they actually want — from-scratch on a small personal corpus usually loses to fine-tuning a comparable pre-trained model.">
  <svg viewBox="0 0 900 460" role="img" aria-label="Three roadmaps from start to a trained model: LoRA in minutes, fine-tune in hours, from-scratch in weeks. The from-scratch path is the most expensive AND usually the worst result for a small personal corpus." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="wab-accent-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.04"/>
      </linearGradient>
    </defs>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" d="M 200 80 L 320 80" />
      <path class="fn-diagram__edge" d="M 540 80 L 660 80" />
      <path class="fn-diagram__edge" d="M 200 200 L 320 200" />
      <path class="fn-diagram__edge" d="M 540 200 L 660 200" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" d="M 200 320 L 320 320" />
      <path class="fn-diagram__edge fn-diagram__edge--accent" d="M 540 320 L 660 320" />
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="40" y="180" width="160" height="80" rx="8" />
      <rect class="fn-diagram__node" x="320" y="40" width="220" height="80" rx="8" />
      <rect class="fn-diagram__node" x="320" y="160" width="220" height="80" rx="8" />
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="320" y="280" width="220" height="80" rx="10" style="fill: url(#wab-accent-grad)" />
      <rect class="fn-diagram__node" x="660" y="180" width="200" height="80" rx="8" />
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--muted" x="55" y="204" text-anchor="start">START</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="55" y="226" text-anchor="start">your goal</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="55" y="246" text-anchor="start">"train a model"</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="335" y="64" text-anchor="start">PATH 1 · LoRA</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="335" y="86" text-anchor="start">minutes · ~$0.01</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="335" y="106" text-anchor="start">brand voice · domain jargon</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="335" y="184" text-anchor="start">PATH 2 · fine-tune</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="335" y="206" text-anchor="start">hours · ~$0.30</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="335" y="226" text-anchor="start">specialization · private knowledge</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="335" y="304" text-anchor="start">PATH 3 · from-scratch</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="335" y="326" text-anchor="start">weeks · ~$50</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="335" y="346" text-anchor="start">niche · privacy-critical · learning</text>
      <text class="fn-diagram__label fn-diagram__label--muted" x="675" y="204" text-anchor="start">YOUR MODEL</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="675" y="226" text-anchor="start">a working LLM</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="675" y="246" text-anchor="start">on your hardware · your data</text>
    </g>
  </svg>
  <figcaption>Same destination, three different paths. The bottom (accented) path is what the technical articles built infrastructure for — and it's the most expensive. For most readers the top or middle path is what you actually want; from-scratch on a small personal corpus usually loses to fine-tuning a comparable pre-trained model. The honest pivot below explains when each path is the right choice.</figcaption>
</figure>

## Three paths in detail — and an honest pivot

If you read the technical arc and got excited about "training your own model," there are three real paths you could walk. They differ by orders of magnitude in cost and time. Most people who say "I want to train a model" want the **shortest** path; the longest path is genuinely interesting but it's almost never the right tool unless you have a specific reason.

**Path 1 — LoRA in an evening (~$0.01)**

Take an existing pre-trained model (Llama 3.1 8B, Qwen 2.5 7B, etc.) and add a small "adapter" layer that learns your specific task. The base model's weights stay frozen; only the adapter changes. After ~30 minutes of training on your laptop or 5 minutes on a Spark, you have a model that responds in your voice, follows your formatting conventions, or knows your domain's vocabulary.

**Best for:** matching a brand voice, learning a domain's jargon, classifying support tickets, summarizing in a specific style. **Already articled** at [`lora-on-your-own-qa-pairs`](../lora-on-your-own-qa-pairs/) (article S2).

**Path 2 — Fine-tuning in a Saturday afternoon (~$0.30)**

Same as LoRA, but you update *all* of the model's weights, not just an adapter. Result is more powerful (the model can really learn new knowledge, not just new style) but takes longer and uses more memory. On a Spark, a 3-billion-parameter base model fine-tuned on a few hundred MB of your own text takes about 2-3 hours.

**Best for:** medical / legal / scientific specializations where the base model lacks vocabulary; learning a non-English language the base barely knows; teaching the model your private knowledge.

**Path 3 — Pre-training from scratch in 6 days (~$2.50)**

Start with random weights. Show the model billions of tokens. Watch it learn language from nothing.

This is the path the five technical articles built infrastructure for. On a Spark, training a 354M-parameter model to "Chinchilla-optimal" (the standard recipe for "as good as the model can get given its size") takes about 6 days of continuous training, drawing 56 W, costing roughly $2.50 in US residential electricity. End result: a small but real model that you trained from nothing, on your data.

**The honest pivot:** for almost everyone, **Path 1 or Path 2 is what you actually want.** A from-scratch 354M model trained on your personal corpus will be *worse* than a pre-trained 8B model fine-tuned on the same corpus, because the 8B started life having read a meaningful fraction of the internet and your model started life knowing nothing. The narrow case where Path 3 wins:

- **You're learning by doing.** Knowing what training-from-scratch feels like teaches you things the higher-abstraction paths don't.
- **You have a privacy-critical reason** to never let your training data touch any pre-trained model — even one you downloaded and ran locally.
- **You're in a niche domain** (proprietary code in a rare language, scientific texts in a specific subfield) where pre-trained models genuinely have nothing useful to inherit from.
- **You want to extend or change the model architecture itself**, not just its weights.

Outside those cases, picking Path 3 is like building your own car engine because you wanted to drive somewhere. Possible, educational, and almost never the most direct route.

## If you really do want to train from scratch — a concrete plan

For the readers who land in one of the four narrow cases above, here's the week-by-week plan that the five technical articles set up:

| week | what you do | which articles to follow | rough wall time |
|---|---|---|---:|
| 1 | Set up the box. Pull NIM, run an inference, install Docker images. | [F1 — `nim-first-inference-dgx-spark`](../nim-first-inference-dgx-spark/), [`nemoclaw-vs-openclaw-dgx-spark`](../nemoclaw-vs-openclaw-dgx-spark/) | 2-3 hours of attended setup |
| 2 | Prepare your corpus. NeMo Curator pipeline, tokenize, pack. | [A3 — `nemo-curator-training-data-prep`](../nemo-curator-training-data-prep/) | 2 hours of work + 5-30 min of pipeline depending on corpus size |
| 3 | Find the training recipe. Run the agent loop overnight to cull architectures. | [A4 — `autoresearch-agent-loop`](../autoresearch-agent-loop/) gated by [A5 — `guardrails-for-code-generation`](../guardrails-for-code-generation/) | 1-8 hours unattended depending on iteration count |
| 4-5 | Commit to the winning recipe. Run actual pre-training for 6 days. | [A1 — `nemo-framework-on-spark`](../nemo-framework-on-spark/) for the framework setup; the harness from A2 with the recipe from A4 | 6 days continuous wall time |
| 6 | Evaluate. Compare your model to off-the-shelf alternatives. | (article TBD — would compare your custom model to fine-tuned Llama on the same task) | 4-6 hours |

Total: roughly one calendar month, of which one week is active work and the rest is unattended Spark time. Total electricity bill: under $5. Total cloud bill: $0.

## Where you can start tomorrow

Three concrete moves anchored to articles already published, in increasing commitment:

**Tomorrow morning, 30 minutes.** Read [`nim-first-inference-dgx-spark`](../nim-first-inference-dgx-spark/), pull the NIM container, run one query against the Llama 3.1 8B endpoint. You will have a fully local LLM responding to you in milliseconds. That is the floor of personal AI.

**This weekend, 4 hours.** Walk the Second Brain arc — [`nim-first-inference`](../nim-first-inference-dgx-spark/) → [`nemo-retriever-embeddings-local`](../nemo-retriever-embeddings-local/) → [`pgvector-on-spark`](../pgvector-on-spark/) → [`naive-rag-on-spark`](../naive-rag-on-spark/) → [`mcp-second-brain-in-claude-code`](../mcp-second-brain-in-claude-code/). End state: a private RAG over your own documents, callable from any Claude Code session anywhere on your network. This is the "what does it feel like to have personal AI" experience.

**Next month, 6 days unattended.** If by then you still want to walk Path 3, the table above is your week-by-week plan. Boot the agent loop on a Friday evening, check it on Saturday morning, run the winning recipe Saturday through Friday. End the next Friday with weights for a model that has never existed in the world before, that nobody else has the data to replicate.

That's the plain-English version of what the Spark earned today. Five articles, 50 unattended experiments, $0.02 of electricity, no cloud account, no API key, no rate limit. We didn't train a usable model — we built the kitchen that lets you train one this month. The hardware made it possible; the next move is yours.
