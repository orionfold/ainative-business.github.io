---
title: "The Hermes Vertical Router on a DGX Spark — One Brain Always Warm, Five Specialists Summoned on Demand"
date: 2026-05-28
author: Manav Sehgal
product: Foundation
stage: agentic
difficulty: intermediate
time_required: "~3 hours including bakeoff + harness publish"
hardware: "NVIDIA DGX Spark"
tags: [hermes, agentic, routing, multi-domain, llama-cpp, qwen3, orionfold, dgx-spark]
summary: "Five published Orionfold verticals plus the pinned MoE brain become a router on one Spark — not by parallel inference (the unified-memory envelope forbids that), but by a deterministic keyword classifier that dispatches the prompt and serves the right specialist one-at-a-time."
signature: HermesVerticalRouter
series: Harnesses
also_stages: [inference]
fieldkit_modules: [harness]
customer_linked: true
---

The public-docs pattern for *agent routing* — Hermes, OpenClaw, AutoGen, OpenRouter all carry a version of it — assumes you have many GPUs and want to spread cheap prompts to a cheap lane while reserving the expensive lane for hard ones. The economics are the pitch: don't pay GPT-4 prices for prompts Haiku could handle. On a personal DGX Spark, that framing inverts. There is one box, one unified-memory envelope, and one model warm at a time. *Tier routing for parallel cost arbitrage* is the wrong shape entirely. *Vertical routing for cold-start dispatch* is what the hardware actually wants.

This article is the sixth installment in the [Harnesses series](/series/harnesses/) and the one where the inventory finally pays a dividend. Five verticals are already published — [patent-strategist](https://huggingface.co/Orionfold/patent-strategist-v3-nemo-GGUF), [Saul-7B-Instruct](https://huggingface.co/Orionfold/Saul-7B-Instruct-v1-GGUF), [finance-chat](https://huggingface.co/Orionfold/finance-chat-GGUF), [SecurityLLM](https://huggingface.co/Orionfold/SecurityLLM-GGUF), [II-Medical-8B](https://huggingface.co/Orionfold/II-Medical-8B-GGUF), all Q5_K_M, 4.5–5.5 GB on disk — and the [previous article in this series](/field-notes/picking-the-hermes-brain-on-spark/) pinned the Qwen3-30B-A3B MoE Q4_K_M as the always-on resident brain. The router is the thin shim that ties them together: a deterministic keyword classifier decides which specialist owns the prompt, [`fieldkit.harness.serve_lane`](/fieldkit/api/harness/) brings that specialist up one-at-a-time, and the brain catches everything no vertical claims. The headline finding earned the [`Orionfold/spark-hermes-vertical-router`](https://huggingface.co/Orionfold/spark-hermes-vertical-router) harness artifact this article documents: **router accuracy 30/30 = 100%, overall per-vertical answer quality 27/30 = 90%**, with all three failures auditable to measurement artifacts, not model failures.

## Why this matters for a personal AI builder

A vertical specialist on a personal Spark is a different kind of asset than a vertical specialist in a cloud fleet. In the cloud, you'd run them all concurrently behind a load balancer; the operational cost is autoscaling, not memory. On the Spark you can hold one strong model warm at a time, and the choice of *which* model is the entire feel of the agent for the next few minutes. A router lets you publish five domain specialists without ever having to pick *the one* — the prompt picks it on entry, the lane warms in five seconds, and the answer comes back from a model that was trained on exactly the kind of content the prompt asks about.

What makes that pay on a Spark is the absence of a marginal call to make. Every published specialist is leverage you already own. You don't lease them by the hour; you don't pay per token. The router's job is to *connect inventory to demand* — and the inventory is already on disk. That's why H5 was the [HANDOFF's higher-value local win](https://github.com/manavsehgal/ai-field-notes): the alternative cost zero new training and produced a measurable lift on the kind of in-domain prompt a generalist 9B couldn't reliably finish.

:::why[Routing on one box is dispatch, not load balancing]
The public-docs router pattern (cheap-lane / expensive-lane) is *concurrent* — it assumes both lanes can be warm at once and decides which gets the next request based on cost or model size. On a single DGX Spark, only one strong model fits warm at a time, so a router is **serial** — it decides which lane to *cold-start next*. That changes everything: warm-time-to-first-token replaces tok/s as the system metric, dispatch accuracy matters more than load distribution, and the default lane is *the brain that stays warm*, not a fallback.
:::

## Where this sits in the Harnesses arc

The series so far has built outward from the install: [H1 the cockpit](/field-notes/the-hermes-harness-on-spark/), [H2 the serving lane](/field-notes/hermes-serving-lane-on-spark/), [H3 the hardening](/field-notes/hardening-the-hermes-harness-on-spark/), [H4 the keystone](/field-notes/hermes-drives-the-spark-via-fieldkit-mcp/) where Hermes drives `fieldkit` via MCP, and [the brain bakeoff](/field-notes/picking-the-hermes-brain-on-spark/) that pinned which model goes in the always-on slot. This article — H5 — uses the pinned brain as the dispatch-class default and adds a *deterministic* classifier above it that swaps in a vertical specialist when the prompt is in-domain. H6 will keep the same `RouterConfig` shape but add cost-tier predicates for an OpenRouter overflow lane; the measured shape is supposed to be a *failure-mode curve* (where does local stop being enough?), not a generic cost-savings pitch.

The thing the diagram below makes visible is the inversion. The brain — the always-on lane — has *zero* warm cost; the five verticals each cost 4 to 6 seconds of cold-start. On the quality axis, finance, cyber, and medical clear 5/5 cleanly; patent, legal, and the brain itself sit at 4/5, with the single miss on each lane traceable to either a `max_tokens` budget or a rubric framework mismatch (the next section walks each).

<figure class="fn-diagram" aria-label="Six Hermes lanes on a DGX Spark scored on two axes: per-vertical pass-rate across five domain prompts, and warm-time to first token. The default brain — the always-warm Qwen3 30B-A3B MoE at Q4_K_M on port 8080 — is the accent: zero warm cost. The five verticals (patent, legal, finance, cyber, medical, all served on port 8090 via llama-server) cold-start in 4 to 6 seconds. Finance, cyber, and medical pass 5 of 5; patent, legal, and brain pass 4 of 5.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Six Hermes lanes on a DGX Spark scored on two axes: per-vertical pass-rate across five domain prompts, and warm-time to first token. The default brain — the always-warm Qwen3 30B-A3B MoE at Q4_K_M on port 8080 — is the accent: zero warm cost. The five verticals (patent, legal, finance, cyber, medical, all served on port 8090 via llama-server) cold-start in 4 to 6 seconds. Finance, cyber, and medical pass 5 of 5; patent, legal, and brain pass 4 of 5." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d06-quality-band-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d06-warm-band-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d06-accent-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.16"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d06-accent-fill-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="40" y="48" width="820" height="160" rx="10" fill="url(#d06-quality-band-grad)" stroke="none"/>
    <rect x="40" y="240" width="820" height="140" rx="10" fill="url(#d06-warm-band-grad)" stroke="none"/>
    <rect x="740" y="60" width="120" height="320" rx="10" fill="url(#d06-accent-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 40 188 L 860 188"/>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="100" width="100" height="88" rx="8"/>
      <rect class="fn-diagram__node" x="200" y="100" width="100" height="88" rx="8"/>
      <rect class="fn-diagram__node" x="340" y="80" width="100" height="108" rx="8"/>
      <rect class="fn-diagram__node" x="480" y="80" width="100" height="108" rx="8"/>
      <rect class="fn-diagram__node" x="620" y="80" width="100" height="108" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="760" y="100" width="100" height="88" rx="8" style="fill: url(#d06-accent-fill-grad)"/>
      <rect class="fn-diagram__node" x="60" y="305" width="100" height="62" rx="6"/>
      <rect class="fn-diagram__node" x="200" y="290" width="100" height="77" rx="6"/>
      <rect class="fn-diagram__node" x="340" y="290" width="100" height="77" rx="6"/>
      <rect class="fn-diagram__node" x="480" y="290" width="100" height="77" rx="6"/>
      <rect class="fn-diagram__node" x="620" y="290" width="100" height="77" rx="6"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="760" y="260" width="100" height="107" rx="6" style="fill: url(#d06-accent-fill-grad)"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="60" y="38" text-anchor="start">Vertical answer quality (5 prompts each)</text>
      <text class="fn-diagram__label" x="60" y="230" text-anchor="start">Warm headroom (inverted: tall = already warm)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="110" y="408" text-anchor="middle">patent</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="250" y="408" text-anchor="middle">legal</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="390" y="408" text-anchor="middle">finance</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="530" y="408" text-anchor="middle">cyber</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="670" y="408" text-anchor="middle">medical</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="810" y="408" text-anchor="middle">brain</text>
      <text class="fn-diagram__label" x="110" y="135" text-anchor="middle" font-size="20" font-weight="600">4/5</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="110" y="158" text-anchor="middle">80%</text>
      <text class="fn-diagram__label" x="250" y="135" text-anchor="middle" font-size="20" font-weight="600">4/5</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="250" y="158" text-anchor="middle">80%</text>
      <text class="fn-diagram__label" x="390" y="115" text-anchor="middle" font-size="20" font-weight="600">5/5</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="390" y="138" text-anchor="middle">100%</text>
      <text class="fn-diagram__label" x="530" y="115" text-anchor="middle" font-size="20" font-weight="600">5/5</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="530" y="138" text-anchor="middle">100%</text>
      <text class="fn-diagram__label" x="670" y="115" text-anchor="middle" font-size="20" font-weight="600">5/5</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="670" y="138" text-anchor="middle">100%</text>
      <text class="fn-diagram__label" x="810" y="135" text-anchor="middle" font-size="20" font-weight="600">4/5</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="810" y="158" text-anchor="middle">80%</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="110" y="325" text-anchor="middle" font-size="13">6.1s</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="250" y="310" text-anchor="middle" font-size="13">4.0s</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="390" y="310" text-anchor="middle" font-size="13">4.0s</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="530" y="310" text-anchor="middle" font-size="13">4.0s</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="670" y="310" text-anchor="middle" font-size="13">4.0s</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="810" y="280" text-anchor="middle" font-size="13">warm</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="110" y="200" text-anchor="middle">max_tokens</text>
      <text class="fn-diagram__annotation" x="250" y="200" text-anchor="middle">rubric mismatch</text>
      <text class="fn-diagram__annotation" x="810" y="200" text-anchor="middle">think-block budget</text>
    </g>
  </svg>
  <figcaption>The brain sits warm at zero cold-start; each vertical pays 4 to 6 seconds for its first token. Quality lands above 80% across every lane; the three misses each have a named, bounded cause.</figcaption>
</figure>

The shape the diagram makes visible is *whose* time the router spends. The brain's warm-time bar is full because it's already up — every prompt that doesn't fire a vertical keyword goes there with no warm cost. The verticals' bars are partial because they cold-start: 6.1 seconds for patent (it's slightly larger), 4.0 seconds for the four 7B–8B siblings. That cold-start is the ceiling on a vertical's responsiveness, and the deterministic classifier is what keeps it from happening for the wrong prompt.

:::define[Vertical, in this article]
A *vertical* is a domain-tuned model published as a single artifact — one HF repo with one recommended GGUF variant — that the router can swap in for prompts whose keywords fall in its domain. The five verticals here are the published Orionfold quants for patent, legal, finance, cybersecurity, and medical reasoning; each was trained or domain-tuned independently and ships with its own bench numbers.
:::

## Why a deterministic keyword classifier, not a model

The first question every architecture review asks at this point is: *should the router itself be a small LLM?* The temptation is real — a 1.5B chat model can classify domain in milliseconds, generalizes to paraphrases, and feels modern. The H5 spec (§4.6) ruled it out for three concrete reasons, and the bakeoff results bear out all three.

The first is the **envelope**. The pinned brain is 31.8 GB resident; the largest vertical (patent, an 8B at Q5_K_M) is 5.5 GB. A 1.5B Q4 classifier would add about 1 GB of always-warm weight to the 128 GB box. That's not the cost worth measuring; the cost is what the classifier *displaces* in the working set. Every gigabyte spent on a classifier is a gigabyte not available for vertical headroom or system services, and the failure mode of running out is silent until something OOMs. A deterministic predicate over a keyword set adds zero bytes to the working set.

The second is **auditability**. A keyword-classifier misroute is a one-line diff: `"breach"` should have hit `legal`, but the prompt phrased it as `"contract breakage"` and missed. You read the keyword list, see why, add the missing keyword, re-test. A small-model classifier's misroute is an embedding artifact you don't see. On the *one* prompt you have eyes on, you can probe both; across a corpus of hundreds, only one of these is debuggable in a Saturday afternoon.

The third is **exactness on in-domain prompts**. The five verticals here have very distinct surface vocabulary — `MPEP §2164` and `prior art` and `provisional` for patent, `CVE-2024-9999` and `OWASP` and `LPE` for cyber, `ICD-10` and `D-dimer` and `mg/kg` for medical. A keyword set written from the bench prompts already covers the vocabulary the customer actually uses; a model classifier learns it from less, and decides probabilistically about cases the keyword set decides exactly about. The deterministic predicate is *less general* but *more precise* on the domains it was designed for, which is the trade you want for an in-house dispatch layer.

:::pitfall[The router that misroutes is auditable; the classifier that misroutes is a black box]
A naive instinct is to "let the model figure it out" because a 1.5B classifier feels smarter than a keyword list. But on a single Spark, you'll be debugging routing decisions yourself, not delegating to ops. A `route_for(prompt)` you can trace by reading the keyword list (and patch in 30 seconds) is operationally cheaper than a classifier whose decisions you can only A/B-test. The H6 cost router will keep the same shape — predicates over the prompt text, not a runtime LLM in the routing path.
:::

H6 will extend the same `RouterConfig` shape with `RouteTier` and `build_cost_router` — three tiers (local Spark $0 → OpenRouter cheap → frontier) selected by predicates over the prompt (keyword sets, token-budget thresholds), not by a runtime LLM. The shape carries because the discipline is the same.

## The router config — config and serving, separated

`fieldkit.harness` v0.12.0 ships the Route group as five symbols. `VerticalRoute` describes one lane; `RouterConfig` holds the tuple of routes plus the default brain; `build_vertical_router` is the factory that validates the routes (unique names, non-empty keywords, default not in routes); `lane_spec_for_vertical` builds the `LlamaServerLane`-bound `LaneSpec` per vertical; `RoutingError` is the refusal type. The router is config; the *serving* is `serve_lane`'s problem.

```python
from fieldkit.harness import VerticalRoute, build_vertical_router

routes = [
    VerticalRoute("patent", "Orionfold/patent-strategist-v3-nemo-GGUF", "Q5_K_M",
                  keywords=("patent", "claim", "prior art", "uspto", "mpep")),
    VerticalRoute("legal", "Orionfold/Saul-7B-Instruct-v1-GGUF", "Q5_K_M",
                  keywords=("lawsuit", "contract", "tort", "statute", "breach")),
    # finance / cyber / medical similarly
]
default = VerticalRoute("brain", "Qwen/Qwen3-30B-A3B-Q4_K_M", "Q4_K_M",
                        keywords=("__default__",), params_b=30.0)
router = build_vertical_router(routes, default=default)
```

The classifier itself is twelve lines: lowercase the prompt, count keyword hits per route, multiply by the route's `weight` (default 1.0 — bump it to bias toward a specific vertical when keyword sets overlap), pick the highest score, break ties by listed-first index, fall through to `default` on zero hits. `router.classify("draft a patent claim for X")` returns the patent route; `router.classify("what's the weather today?")` returns `brain`. The function is pure, has no I/O, and can be tested without anything resembling a GPU.

The OOM-safe convenience is `RouterConfig.serve_for(prompt)` — a context manager that classifies first, then wraps `serve_lane(LlamaServerLane(...), guard=True)` for the picked vertical. The guard reuses `fieldkit.capabilities.weight_bytes` to refuse a lane that would tip the 128 GB envelope. The contextmanager's teardown is the structural guarantee against stacking — exit the `with` block and the vertical is torn down before the next one warms.

:::define[Default route, in `RouterConfig`]
The `default` field of a `RouterConfig` is **not** a competitor for keyword hits — it's the fallback served when no vertical's keyword score is positive. `build_vertical_router` refuses to construct a router where the default's name also appears in `routes`. In this article's setup the default is the always-warm Qwen3-30B-A3B MoE on port 8080; the five verticals live on port 8090 and only one of them is warm at a time.
:::

## The 30-prompt suite

The suite that scores the router is small on purpose. Five prompts per vertical (twenty-five vertical prompts total) plus five default-brain prompts (intentionally vertical-neutral — a haiku, a Tokyo trip plan, a backpropagation explainer, a leftover-vegetable recipe, a polite-decline email) — thirty prompts that take about fifteen minutes of wall time to run end-to-end. Each prompt drives *two* measurements: router accuracy (does `RouterConfig.classify()` pick the right vertical?) and answer quality (does the picked vertical's lane actually produce a passable answer?).

```json
{
  "id": "patent_3_prior_art_search",
  "vertical": "patent",
  "prompt": "What is a prior-art search and when in patent prosecution should you do one?",
  "check": {"kind": "substring", "all": ["prior art"],
            "any": ["search", "before filing", "examination", "fil"]}
}
```

The scoring is deterministic by design — substring matches, regex patterns, and the same `CheckSpec` primitives from `fieldkit.eval` that the brain-bakeoff used. No LLM judge. Two of the thirty prompts are flagged `vibe: true` (the haiku, the leftover-veggies recipe) because they're open-ended enough that any deterministic check is a heuristic — those get an eyeball pass in the report, not a number. The other twenty-eight are scored to PASS or FAIL with a one-line `why` string that names the specific keyword or pattern that hit (or didn't).

The check column uses the `all` / `any` shape because *partial* coverage of the right vocabulary is the right bar for a 5-prompt sample. A patent-prosecution answer that mentions "prior art" but not "USPTO" still earned the rubric; one that mentions neither did not. Tightening to `all: ["prior art", "USPTO"]` would have produced more failures of the rubric, not more failures of the model.

## Router accuracy is the easy axis

The router classifies all thirty prompts in under a millisecond — it's a pure function. The number that comes out is **30/30 = 100%**. That's the cleanest possible result, and it deserves a caveat in the same paragraph: the suite was author-built to be classifiable, and the keyword sets were tuned during bench iteration. A 100% on a suite that was designed against the keyword sets is necessary, not sufficient.

The honest version of the question is sharper: *does the deterministic predicate hold up when the prompt's surface vocabulary is the kind a real customer would use?* The five vertical prompts per domain were written to vary surface form — direct domain terms in some (`"draft three independent patent claims"`), incidental references in others (`"a 65-year-old presents with sudden chest pain"`), implicit framings in still others (`"calculate amoxicillin dose for a 25 kg child"`). The router caught all of them by *one or more* keywords per prompt, never by exact-string match alone. The 100% is what you'd want; it doesn't say the router will hold up against an adversarial input distribution.

The honesty next to the headline is that the *router* doing 100% on the suite is half the bakeoff. The other half is what happens when the picked vertical actually has to *answer* the prompt — and that's where the interesting failures live.

## Per-vertical quality — 27/30 = 90%, with three named failures

```
[patent]   4/5  warm 6.1s
[legal]    4/5  warm 4.0s
[finance]  5/5  warm 4.0s
[cyber]    5/5  warm 4.0s
[medical]  5/5  warm 4.0s
[brain]    4/5  (always-warm)
```

Finance, cyber, and medical scored 5/5 cleanly — every prompt's expected vocabulary was present, every answer was within the rubric's tolerance, no max_tokens trouble. Patent, legal, and the brain each missed one, and each miss has a named, bounded cause. The article doesn't earn its 90% by being lucky; it earns it by being able to *explain the 3/30 failures one at a time*.

**`patent_1_claims`** — the model was asked to draft three independent patent claims. It opened with a confident MPEP-anchored preamble ("MPEP 2172.01 allows claims to stand independently...") and rolled into claim 1 — but then ran out of `max_tokens=1024` partway through. The rubric checked for a "3." line at the start of a multiline pattern and didn't find one, because there *was no claim 3 yet*. That's not a model failure; it's a budget failure. The model knew the structure and was generating it correctly; an answer of three substantial claims plus a domain-aware preamble doesn't fit in 1024 tokens. The fix is `max_tokens=2048` for patent-claim drafting and an acceptance that the bench rubric uses the same budget across all verticals for fairness.

**`legal_1_contract_elements`** — the prompt asked what four elements a plaintiff must prove for breach of contract. The rubric expected `offer / acceptance / consideration`. Saul instead gave the **cause-of-action framework**: existence of a valid contract, breach, damages, causation. Saul is correct. The four elements of a *breach* claim (what a plaintiff sues over) are not the four elements of contract *formation* (what makes a contract exist in the first place). My rubric was looking for the formation framework when the prompt was asking about the lawsuit framework. The rubric was wrong; Saul was right. The fix is the rubric, not the model — and the failure mode (deterministic check disagrees with domain-specialist answer) is exactly what `vibe: true` was supposed to catch but the prompt wasn't flagged.

**`default_1_haiku`** — the brain (Qwen3-30B-A3B at Q4_K_M) was asked to write a single haiku about a misty morning over a river. The rubric expected three lines. The brain's reply consumed most of its 1024 tokens in a long `<think>...</think>` block (Qwen3 served with `--reasoning-format none` keeps the reasoning chain in the OpenAI `content` field), and after the [`fieldkit.notebook.split_think`](/fieldkit/api/notebook/) strip, only two truncated lines of the haiku remained: *"Misty veil descends, / River's mirror blurs with"*. The fix is, again, `max_tokens=2048` — the reasoning budget needs to leave room for the answer. Reasoning models with `<think>` blocks need a *bigger* per-prompt budget than non-reasoning models for the same answer length.

:::define[`<think>` block, in a reasoning-model reply]
Reasoning models (R1, Qwen3-Thinking, Nemotron-Reasoning) emit a `<think>...</think>` reasoning trace before the answer. When the server is configured with `--reasoning-format none`, the trace stays in the OpenAI `content` field as raw text rather than being split into a separate `reasoning_content`. `fieldkit.notebook.split_think(reply)` returns `(reasoning, answer)`; the answer is what the rubric scores against. A 1024-token budget that includes 700 tokens of thinking leaves only 324 tokens for the answer.
:::

Two of the three failures are the same root cause — `max_tokens=1024` is too short when the answer is structured or the model is a reasoner. The third is a rubric framework mismatch. Zero of the three are a model getting domain content wrong, which is the only failure that would actually invalidate the router's premise.

## Envelope discipline — one specialist warm at a time

The bakeoff serves each vertical on port 8090 via `llama-server` directly from `/home/nvidia/data/quants/<vertical>/model-Q5_K_M.gguf`, runs that vertical's 5 prompts, then tears it down before the next vertical warms. The default brain stays warm on port 8080 throughout, at ~31.8 GB resident. The peak concurrent footprint is `brain (31.8 GB) + one vertical (4.5–5.5 GB) + system services (~10 GB)` ≈ 47 GB — well inside the 128 GB envelope. Stacking two verticals at once would still fit, but the [unified-memory OOM landmine](/field-notes/dgx-spark-day-one-access-first/) costs an entire box when it misses, and the `serve_lane` contextmanager's teardown-on-exit is the structural guarantee that prevents it.

```python
# fieldkit.harness.RouterConfig.serve_for — the OOM-safe convenience
@contextmanager
def serve_for(self, prompt, *, guard=True, headroom_gb=8.0, ...):
    picked = self.classify(prompt)             # pure predicate, no I/O
    spec = lane_spec_for_vertical(picked, ...)
    with serve_lane(spec, guard=guard,         # weight_bytes + headroom check
                    headroom_gb=headroom_gb,
                    params_b=picked.params_b,
                    dtype=picked.dtype) as lane:
        yield picked, lane                     # vertical live on lane.base_url
    # __exit__ tears the vertical down before the next one warms
```

The cold-start tax is measurable: 6.1 seconds for patent (the largest, an R1-distilled 8B at Q5_K_M), 4.0 seconds for the four 7B–8B siblings. On the time-to-first-token axis, the brain is the only lane the customer would *not* wait for. That's the dispatch logic: ambiguous prompts default to the always-warm brain because the brain's latency is dominated by decode, not warm-up; in-domain prompts pay the 4 to 6 second tax because the specialist's answer is what justifies it. A naive router that warmed a vertical for every prompt would have a p50 latency floor of 5 seconds — unacceptable for the kind of agent turn the cockpit handles dozens of times an hour.

:::math[Routing budget on a 128 GB Spark]
brain `31.8 GB` + system services `~10 GB` + headroom `~8 GB` = `~50 GB`. That leaves `~78 GB` for at most one vertical (at most `~5.5 GB`) plus working memory for the vertical's KV cache, agent terminal sandbox, and whatever else is running. The router lives well below the envelope. Two verticals warm at once (e.g., a pipeline that needs cyber → medical handoff) would still fit at `~55 GB` total — but the simpler discipline is "one specialist at a time, brain catches everything else."
:::

## What this unlocks

Three things slot in immediately. The first is the **multi-domain agent loop**. A Hermes session can now drive any of five specialists without the operator deciding which to warm — the prompt's surface vocabulary picks. A first-turn prompt about a CVE warms cyber; the next turn about an ICD-10 code tears cyber down and warms medical. The H4 keystone wired `fieldkit` as MCP tools; H5 wires the model side of the loop the same way — `fieldkit.harness` is now both the *cockpit* the operator drives and the *dispatcher* the agent dispatches through.

The second is **measurable router swaps**. The 30-prompt suite + the `RouterConfig` config file + the `build_router_profile.py` publisher are the same shape as the brain-bakeoff's measurement surface — drop a new vertical's manifest into [`router_config.json`](https://huggingface.co/Orionfold/spark-hermes-vertical-router/blob/main/router.yaml), add its 5 prompts to the suite, re-run the bakeoff, and the published harness card updates itself. The cost of adding a sixth vertical is a few hours of bench writing, not a re-design. The [published harness artifact](https://huggingface.co/Orionfold/spark-hermes-vertical-router) ships the keyword sets, the prompt suite, and the per-vertical scorecards — readers can clone the shape into their own router without re-deriving any of the discipline.

The third is the **path to H6**. H5's `RouterConfig` is the same shape H6's `build_cost_router` will extend with `RouteTier` and 3-tier predicates — local Spark $0 first, then OpenRouter cheap, then frontier. The HANDOFF reframes H6 as a *measured failure-mode curve* — "when does the local stack stop being enough?" — not a generic cost-savings pitch, because the cost-savings pitch barely applies on a $0 local lane. The interesting question is which prompts genuinely overflow the brain's capacity, and that's a curve you can only draw if you have a router to attribute the overflows to.

```python
# From a Hermes-driven script — pick the vertical, serve it, ask it
from fieldkit.harness import build_vertical_router, VerticalRoute
import httpx

routes = [...]  # 5 VerticalRoute entries
default = VerticalRoute("brain", ..., keywords=("__default__",))
router = build_vertical_router(routes, default=default)

prompt = "What three differential diagnoses must we rule out for chest pain?"
with router.serve_for(prompt) as (picked, lane):
    print(f"Routed to {picked.name} on {lane.base_url}")  # → "medical"
    r = httpx.post(f"{lane.base_url}/chat/completions", json={
        "model": picked.name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    }, timeout=60).json()
    print(r["choices"][0]["message"]["content"])
```

## Tradeoffs and gotchas

The biggest tradeoff is the **cold-start latency floor**. A vertical's first token is 4–6 seconds away even on a hot box, and that's the *best* case (the GGUF is already in the page cache from a prior warm). On a fresh boot the first-ever warm of a vertical adds a couple of seconds for disk read. The dispatch logic mitigates this — only in-domain prompts pay the tax — but the operator hits it directly when testing a new vertical. The two scripts in [`evidence/`](https://huggingface.co/Orionfold/spark-hermes-vertical-router/tree/main) are the same `start-` / `stop-` pattern as the brain bakeoff; pre-warming a vertical before a session that's going to use it is a documented escape hatch.

The second is the **keyword-set drift**. Keywords were tuned against the bench prompts, which means they cover the surface vocabulary the bench uses well and the surface vocabulary the customer might use *adjacently* — a customer who phrases a CVE triage as "I'm seeing CVE-2025-99999, what's our exposure" will hit cyber; one who writes "we got hit, what's the patch story" might not (no keyword fires). The router refuses to do fuzzy matching by design. The mitigation is operator-side — observe the routing decisions for a week, add the missing keywords as they surface. The [`router.yaml`](https://huggingface.co/Orionfold/spark-hermes-vertical-router/blob/main/router.yaml) on the HF card is the canonical config; edit it, rebuild the harness profile, re-publish.

The third is the **brain-default may sometimes outperform the routed specialist**. The brain is a 30B-A3B MoE that is, on most prompts, better than any 7B–8B vertical. The router's value isn't "the picked vertical always beats the brain" — it's "the picked vertical answers from the right *training corpus*." For domain-specific terminology, citation patterns, or framework names, the specialist wins reliably. For raw general reasoning, the brain wins. The 90% vs 80% per-vertical band reflects this: finance, cyber, and medical have very *distinct* surface vocabularies their specialists know cold; patent and legal sit a bit closer to general legal-reasoning territory and the brain often does fine on those too. The router doesn't *win every prompt*; it ensures the right model gets the prompt.

:::hardware[The router shape scales; the model class doesn't]
On a Spark, the 5 verticals are 7B–8B Q5_K_M (~5 GB each) and the brain is a 30B-A3B MoE Q4 (~32 GB). On an H100 (80 GB HBM3), the same router could hold all 5 verticals + a 70B brain warm at once and *parallelize* dispatch — H100's headroom converts the serial `serve_lane` pattern into the parallel load-balancer pattern from the public docs. The router *config* (keyword classifier + RouterConfig) carries unchanged; the *serving discipline* changes from "one specialist at a time, brain always warm" to "all specialists warm, dispatch on demand." The H5 article walks the Spark shape; the H6 cost router will name the inflection.
:::

:::deeper
- [`fieldkit.harness.Route` group](/fieldkit/api/harness/) — `VerticalRoute` / `RouterConfig` / `build_vertical_router` / `lane_spec_for_vertical` / `RoutingError` (v0.12.0)
- [`Orionfold/spark-hermes-vertical-router`](https://huggingface.co/Orionfold/spark-hermes-vertical-router) — the published harness artifact with the canonical `router.yaml`
- [`Orionfold/spark-hermes-profile`](https://huggingface.co/Orionfold/spark-hermes-profile) — the H2 serving-lane profile this router builds on
- [Picking the Hermes Brain on a DGX Spark](/field-notes/picking-the-hermes-brain-on-spark/) — the brain bakeoff that pinned the default-route MoE
- [spec/hermes-harness-v1.md §4.5–4.6](https://github.com/manavsehgal/ai-field-notes/blob/main/specs/hermes-harness-v1.md) — H5/H6 design, the deterministic-predicate discipline
:::

## Closing — and the cleared path to H6

The router is live as of today: [`fieldkit.harness.build_vertical_router`](/fieldkit/api/harness/) in v0.12.0 on [PyPI](https://pypi.org/project/fieldkit/0.12.0/), the [`Orionfold/spark-hermes-vertical-router`](https://huggingface.co/Orionfold/spark-hermes-vertical-router) harness artifact on HuggingFace with the canonical [`router.yaml`](https://huggingface.co/Orionfold/spark-hermes-vertical-router/blob/main/router.yaml) embedded, and the 30-prompt bakeoff suite committed under this article's `evidence/` so anyone can re-run the measurement on their own Spark. The five Orionfold verticals were already published; H5 added 251 lines of `fieldkit.harness` code, 24 tests, one new signature component, and an honest 27/30. No new training, no new weights — pure leverage on inventory already on disk.

The pin from this article is the *dispatch contract*, not a model. The cockpit (H1), the serving lane (H2), the hardening (H3), the fieldkit-as-MCP keystone (H4), the brain (the pin), and the router (this article) compose into an agent harness where every layer is measurable and every decision is auditable. The remaining piece — H6's cost router and the failure-mode curve to OpenRouter — measures where the *local* stack stops being enough. With the router in place, that's a question we can answer concretely rather than philosophically. The Spark holds its end of the deal; H6 measures the rest.

---

**Catalog page:** [`/artifacts/harnesses/spark-hermes-vertical-router/`](/artifacts/harnesses/spark-hermes-vertical-router/) — positioning, lane variants with measured throughput, the recommended lane, and bounded drift — the full Spark-agent harness profile.
