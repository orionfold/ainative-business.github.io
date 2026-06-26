---
title: "Orionfold Advisor: a governed local AI advisor for your enterprise corpus"
date: 2026-06-10
author: Manav Sehgal
product_name: "Orionfold Advisor"
tagline: "A governed local AI advisor over your corpus: exact citations, trusted refusals, and a receipt for every claim."
summary: "Bring a corpus to a DGX Spark and get a governed advisor over it: a NVIDIA-native 4B lane fine-tuned for exact source-id citations and adversarial-proof refusals, a recall-gated retriever, deterministic frontier routing, and an Arena cockpit where every gate is a visible receipt."
hardware: NVIDIA DGX Spark
status: published
series: Cockpit
tags: [advisor, rag, grounded-citation, refusal, routing, nemotron, nemo, sft, arena, cortex, cockpit, local-llm, dgx-spark, fieldkit, agentic-coding]
download_url: "https://huggingface.co/Orionfold/Advisor-GGUF"
fieldkit_modules: [arena, eval, memory, cost, training, quant, publish]
build:
  window: "two days (~30 hours) from proof-spec to promoted serving lane"
  wall_clock_hours: 29.9
  sessions: 10
  assistant_turns: 871
  tokens_processed: 118874155
  tokens_generated: 645475
  cache_read_tokens: 115831600
  lines_of_code: 4307
  test_cases: 54
  feature_count: 7
  models: ["Claude Fable 5"]
  daily_driver: "Claude Fable 5"
  harness: "Claude Code"
features:
  - name: "A one-click generator gate"
    benefit: "The Cortex preflight card runs the 8-packet citation/refusal gate against whatever lane is serving and shows pass/fail per row — the same button that caught two base models failing before a single training hour was spent."
    screenshot: "screenshots/01-advisor-preflight.png"
  - name: "The corpus pack as a visible unit"
    benefit: "182 sources, the manifest hash, both recall gates (BM25 and the live pgvector lane), and the corpus-swap proof on one card — when the corpus changes, the gates re-run and the card says so."
    screenshot: "screenshots/02-corpus-pack.png"
  - name: "Governed escalation with a visible bill"
    benefit: "Every hosted escalation carries its tier, provider, model, cost, and verdict — 28/28 at $0 local-only, 28/28 at $0.0033 with the frontier in the loop, and private-state queries never leave the box."
    screenshot: "screenshots/03-routing-cost.png"
  - name: "A publish verdict you can re-verify"
    benefit: "The §14 receipt card shows the promoted lane, all nine gate chips, and why six candidate lanes were promoted or rejected — assembled by a script that fails if the evidence stops supporting a claim."
    screenshot: "screenshots/04-publish-receipt.png"
  - name: "Guarded lane swaps"
    benefit: "One model resident at a time in 128 GB unified memory: teardown-first confirmation, envelope preflight, and an anchor on warm — the promoted 4B comes up in ~2 seconds at ~12 GB."
    screenshot: "screenshots/05-lanetruth-promoted.png"
  - name: "Every measured bench row, pickable in chat"
    benefit: "The eval drawer holds all 89 measured Advisor rows — frozen held-out and both curveballs — with family filters; pick one and the chat replays the exact packet the receipts were scored on."
    screenshot: "screenshots/06-eval-drawer.png"
  - name: "Refusals scored live at the wire"
    benefit: "Ask the serving lane a private-state question and watch it refuse with empty citations — scored 100% against the deterministic contract the moment the turn lands, no judge model in the loop."
    screenshot: "screenshots/07-chat-eval-refusal-scored.png"
---

## An advisor that knows where its answers come from

**Orionfold Advisor** is a governed local AI advisor for your enterprise corpus. It runs on one NVIDIA DGX Spark and it is not a model — it is an appliance: a fine-tuned NVIDIA-native model lane, a recall-gated retriever, a deterministic frontier router with a spend cap, a corpus pack you can swap, and the [Orionfold Arena](/products/orionfold-arena/) cockpit as its operating surface. Ask it a question and it answers from retrieved sources, citing the **exact source id** every claim came from. Ask it something the corpus doesn't contain — or something about private operator state — and it **refuses**, with empty citations, even when the question arrives dressed as an urgent exception, a roleplay, a false premise, or an instruction to miscite.

It is for the operator who needs corpus answers they can audit, and for the builder who wants the receipts: every gate the Advisor passed on its way to serving — retrieval recall, generator preflight, frozen out-of-distribution benches, routing accuracy, the publish verdict itself — is a tracked artifact you can re-run, rendered on cards in the cockpit.

## What it unlocks

The hard part of a corpus assistant was never fluent answers — it's *trustable* ones. A grounded answer with a paraphrased citation is unauditable; a confident answer to a question the corpus can't support is worse. The Advisor makes both failure modes measurable, then trains them away: citation discipline means the cited id is drawn from the retrieved set (an alias like `Source 2` is a strict failure), and the refusal floor is measured against adversarial pretexts that were frozen *before* training, so the number can't flatter itself.

That discipline turned out to be trainable where prompting wasn't. The most important measurement of the build: on the frozen curveball bench, the **30B model with a carefully engineered prompt contract scored 8/21 — and fabricated private-looking state on 3 rows**. The 4B model *fine-tuned* for the behavior scored **18/21 with refusals 9/9 and zero private-state risk**. The trained lane, not the prompt, carries the refusal floor. That's a result you can only get cheaply when training, serving, and evaluation all live on the same box — the whole SFT run was **~21 minutes** on the Spark, and the candidate was behind the same eval surface minutes later.

And because the corpus pack is a swappable unit — manifest, trust tiers, gold eval seed, refusal cases, rebuild gates — the same harness that advises over Orionfold's public corpus today can take a customer's corpus tomorrow. That swap was proven, not promised: a synthetic three-source fixture pack went through the unchanged recall scorer and passed its gate at 1.0@5.

## The build story: gates first, training second

The Advisor went from proof spec to promoted serving lane in **two days (~30 wall-clock hours, 31 commits)**. The infographic above is the honest receipt of those two days: **10 Claude Code sessions, 871 assistant turns, 118.9M tokens processed — 97.4% of them served from prompt cache — and 645k tokens actually generated**, all on **Claude Fable 5**. The 4,307 lines are the authored Advisor harness (corpus generation, recall scorers, the preflight gate, the route bakeoff, the SFT pipeline, the receipt assembler); the cockpit cards and eval drawer ride the existing Arena codebase, with **54 advisor-specific test cases** alongside.

The order of operations is the story. Before any training: a 182-source public corpus manifest with a frozen 28-row held-out bench; retrieval recall gates on two lanes (BM25 proxy 0.9885@5, live pgvector + NIM embedder 0.977@5, 1.0 on held-out answerable); then a raw-floor preflight of candidate bases through the visible cockpit. Two NVIDIA bases failed that floor honestly (one leaked its reasoning chain on 7 of 8 rows) before the 30B and the 4B cleared it. Only then came SFT — a teacher-verified corpus generated by the 30B on-box, trained into the 4B with NeMo LoRA in ~21 minutes, quantized to Q8_0, and launched behind the same gates.

Twice, the gates caught what would have silently shipped. A corpus rebuild pulled the Advisor's own proof spec into its retrieval index — the bench's erratum text started surfacing in eval context, and the full gate re-run flagged it before promotion (proof-control documents are now excluded at generation time). And the first SFT pass fixed citation discipline but *regressed* the refusal floor under novel pretexts, 14/15 → 9/15 — caught by the frozen curveball, fixed in v0.2 by training three new hint-free refusal families, and verified at 15/15 on the class that regressed. A pre-registered bench you can't touch is the only reason either failure has a number attached.

The promotion itself is a script, not a sentiment: the receipt assembler reads every tracked receipt and fails if the evidence stops supporting a gate claim. It assembled nine green gates and a verdict — **PROMOTED: the 4B-SFT-v0.2 lane** — with the 30B retained as teacher and comparison lane, and four other candidates recorded as rejected, with reasons.

## The feature tour

### A one-click generator gate

![The Advisor preflight card — 8 packets, reasoning off, all rows passing, scored receipt below](screenshots/01-advisor-preflight.png)

*The citation/refusal gate as a button: 8 packets against the active lane, pass/fail per row.*

The Cortex pane's preflight card runs the 8-packet citation/refusal gate against the active lane — one button for the default run, one for reasoning-off — and renders pass/fail per row with the receipt underneath. Every base model the Advisor considered went through this card in the visible cockpit; the screenshot shows the promoted lane's 8/8.

### The corpus pack as a visible unit

![The corpus pack card — 182 sources, manifest hash, both recall gates green, swap fixture, SFT handoffs](screenshots/02-corpus-pack.png)

*The corpus with a hash and gates, not a folder of files.*

The Advisor's knowledge boundary is a governed unit: its card shows the manifest (182 sources, `6b1e832d099c`), both recall gates, the corpus-swap fixture proof, and the SFT corpus handoffs that were generated from it — the chain from "what the Advisor knows" to "what the model was trained on" on one card.

### Governed escalation with a visible bill

![The routing & cost card — three configs at 28/28, $0 to $0.0033, zero private-state escapes](screenshots/03-routing-cost.png)

*Every hosted call has a tier, a provider, a cost, and a verdict — and a policy that keeps private state home.*

The router is deterministic and observables-only: it escalates on detectable failure signals (a citation outside the retrieved set, a rank-sanity anomaly), never on vibes. The card shows each measured config with its score and bill, the per-escalation ledger, and the governance line: hosted models are an allow-list with a dollar cap, and private-state queries are blocked from egress by policy.

### A publish verdict you can re-verify

![The publish receipt card — PROMOTED, nine gate chips, the why-promoted drawer open](screenshots/04-publish-receipt.png)

*Promotion as evidence, not announcement: nine gates, each chip backed by a named receipt.*

The §14 receipt card renders the promotion: the lane, nine gate chips each backed by a named evidence file, and the drawer explaining why this lane won and what happened to the other lanes considered. Re-running the assembler re-verifies every claim against the receipts on disk.

### Guarded lane swaps

![LaneTruth — the promoted 4B lane ACTIVE on :8091, guarded launch form below](screenshots/05-lanetruth-promoted.png)

*One resident model is the law of unified memory; LaneTruth makes it visible and safe.*

One model resident at a time is the law of 128 GB unified memory, and LaneTruth enforces it visibly: teardown-first confirmation, a guarded pre-flight on every launch, and an anchor on warm. The Advisor's promotion was executed here — the 30B (~40 GB, 14 s warm) torn down, the trained 4B (~12 GB, 2 s warm) anchored in its place.

### Every measured bench row, pickable in chat

![The eval drawer — Orionfold Advisor bench selected, 89 rows with family filters](screenshots/06-eval-drawer.png)

*The receipts' exact packets, replayable from the chat composer.*

All 89 measured Advisor rows — the frozen held-out and both curveballs — are pickable in the chat and compare eval drawer, replaying the exact packets the published receipts were scored on, system contract included. The bench rider even replays the measured reasoning control, so what you see in chat is what the receipts measured.

### Refusals scored live at the wire

![A live private-state refusal — empty citations, scored 100% against the deterministic contract](screenshots/07-chat-eval-refusal-scored.png)

*A refusal you can score the moment it lands — no judge model, no rubric drift.*

The deterministic contract scorer runs on every eval turn as it lands: this row asks about live operator state, the serving lane refuses with empty citations, and the turn scores 100% instantly — refusal wording, empty citations, no private-state echo, no thinking leak, each a visible check.

## Built on the substrate

The Advisor is the thinnest possible new layer over what the Spark stack already proved. Retrieval rides **Orionfold Cortex** (pgvector + the NIM embedder, with the recall-gate discipline from the [Cortex launch](/products/orionfold-cortex/)). The operating surface is **Orionfold Arena** — LaneTruth, the jobs board, the eval drawer, telemetry — extended with four read-only Advisor cards. Training is the NeMo LoRA lane; quantization and publishing ride `fieldkit.quant` and `fieldkit.publish`, and the model card's measurement-first shape is the same one every Orionfold artifact ships with. The newly authored code is the harness itself: packet construction, deterministic scorers, the route bakeoff, the receipt assembler.

The published artifacts close the loop: the model is [`Orionfold/Advisor-GGUF`](https://huggingface.co/Orionfold/Advisor-GGUF), the benches and corpus manifest are [`Orionfold/Advisor-bench`](https://huggingface.co/datasets/Orionfold/Advisor-bench), and every receipt quoted on this page is tracked in the public repo under [`evidence/orionfold-advisor/`](https://github.com/orionfold/ainative-business.github.io/tree/main/evidence/orionfold-advisor).

## The workflow, generalized

The pattern under the product is reusable for any vertical: freeze a bench before you train; gate retrieval before you gate generation; preflight the raw base before you spend a training hour; let a deterministic router — not hope — decide when the frontier gets consulted; and make promotion a script that reads receipts. The corpus pack makes the whole loop portable — same harness, same gates, different corpus. One Spark ran every step: corpus generation by a local teacher, training, quantization, serving, evaluation, and the decision.

## Get it

- **Run the model:** [`Orionfold/Advisor-GGUF`](https://huggingface.co/Orionfold/Advisor-GGUF) — Q8_0, ~12 GB resident, with the packet contract and reasoning-off serving notes on the card.
- **Score your own lane:** [`Orionfold/Advisor-bench`](https://huggingface.co/datasets/Orionfold/Advisor-bench) — the pool, the frozen held-out, both curveballs, and the corpus manifest they resolve against.
- **Read the receipts:** [`evidence/orionfold-advisor/`](https://github.com/orionfold/ainative-business.github.io/tree/main/evidence/orionfold-advisor) — every number on this page, re-runnable.

The cockpit it runs in is the same Orionfold Arena that ships with [fieldkit on PyPI](https://pypi.org/project/fieldkit/).
