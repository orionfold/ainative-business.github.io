---
title: "Cost-Routing the Hermes Harness — When Local Stops Being Enough on a DGX Spark"
date: 2026-05-28
author: Manav Sehgal
product: Foundation
stage: agentic
difficulty: intermediate
time_required: "~4 hours including the OpenRouter bakeoff + harness publish"
hardware: "NVIDIA DGX Spark + OpenRouter API (~$5 budget)"
tags: [hermes, agentic, routing, cost, openrouter, frontier, dgx-spark, qwen3, claude-opus]
summary: "The local 30B-MoE on a Spark is at $0 marginal cost — until it isn't. H6 measures the failure-mode curve: where does local stop being enough, and what does the dollar curve look like when you escalate to OpenRouter only when you have to?"
signature: HermesCostRouter
series: Harnesses
also_stages: [inference, deployment]
fieldkit_modules: [harness, eval]
customer_linked: true
---

The public-docs framing of an *agent cost router* — local-vs-frontier, save 60–80% — is one of the oldest pitches in the AI-tooling literature. It assumes the expensive lane is a tax you pay because the cheap lane isn't strong enough. On a DGX Spark with the [Step-2 pinned Qwen3-30B-A3B MoE brain](/field-notes/picking-the-hermes-brain-on-spark/) at $0 marginal cost, that pitch barely applies. The interesting question on this box isn't "how do I save money on the easy prompts" — it's *when does the local MoE actually fail and I need to call OpenRouter?* This article measures that.

H6 is the sixth and final installment of the [Harnesses series](/series/harnesses/). The first five built the agent harness outward from the install — [the cockpit](/field-notes/the-hermes-harness-on-spark/), [the serving lane](/field-notes/hermes-serving-lane-on-spark/), [the hardening](/field-notes/hardening-the-hermes-harness-on-spark/), [the keystone where Hermes drives `fieldkit` via MCP](/field-notes/hermes-drives-the-spark-via-fieldkit-mcp/), and [the vertical router that picks among the five Orionfold specialists](/field-notes/hermes-vertical-router-on-spark/). H6 closes the loop with a *cost-tier* router that sits next to the vertical router in the same `fieldkit.harness` Route group: the vertical router decides *which expert* answers; this one decides *which tier* answers. Local Spark for the cases it can handle, OpenRouter for the cases it can't.

## Why this matters for a personal AI builder

A personal AI builder running a Spark has, for the first time, two different fundamental cost regimes inside the same agent. The local lane is electricity-only — every prompt the local brain answers is a marginal cost of approximately zero. The frontier lane is per-token billed at frontier-model prices: at the snapshot prices this article measures, Claude Opus 4.1 is $15 per million input tokens and $75 per million output tokens. Between them is a value tier — OpenRouter's `gpt-4o-mini` at $0.15 input / $0.60 output, *100× cheaper* than Opus on input.

The arithmetic of that price gap is what makes a cost router worth building. If the local lane handles even half your agent's traffic, you've cut the frontier spend in half before any of the standard-tier optimizations kick in. But the more interesting question — the one this article tries to answer — is *what fraction does the local lane actually handle?* The reframed-per-[HANDOFF](https://github.com/manavsehgal/ai-field-notes) headline metric is the **leak rate**: the percentage of prompts where local *failed* the rubric but the frontier model *passed*. That's the genuine "where local stops being enough" number, measured with no editorial finger on the scale.

:::why[Cost routing on a Spark is failure-mode measurement, not savings]
The public-docs cost-router pattern assumes both lanes cost real money. On a Spark, only the frontier lane does — the local lane is amortized hardware plus electricity. So the pitch *flips*: you're not optimizing the cost curve, you're measuring the failure curve. "How often does local need help?" is the editorially honest version of "how much does the cost router save?"
:::

## Where this sits in the Harnesses arc

The series so far has built outward from the install: H1 the cockpit, H2 the serving lane, H3 the hardening, H4 the keystone where Hermes drives `fieldkit` via MCP, the [brain bakeoff](/field-notes/picking-the-hermes-brain-on-spark/) that pinned which model goes in the always-on slot, and [H5](/field-notes/hermes-vertical-router-on-spark/) — the vertical router that ties the five published Orionfold quants together. H6 is the cost-tier router: same deterministic-predicate discipline, different routing dimension. Both routers ship as `fieldkit.harness.RouterConfig` siblings now — `build_vertical_router` and `build_cost_router` — and the new H6 surface adds three symbols (`RouteTier`, `CostRouterConfig`, `build_cost_router`) plus the `LaneMetricColumns` machinery the published harness card uses to render a $/M-per-tier table instead of the H2-style tool-call-reliability table.

The thing the signature figure makes visible is the three-way split: a per-strategy pass-rate band on top (how many of the 12 prompts each strategy got right at majority vote across N=3 attempts), and a $/100-tasks band on the bottom (the dollar cost normalized to a hundred-task workload, with $0 shown as the tallest bar so cheaper-is-better reads visually). The cost-routed strategy is the accent — it landed at 11/12 against the frontier ceiling's 12/12 while spending **$2.19 per 100 tasks** vs the frontier's **$2.94**. The leak set has a specific shape that the rest of this article walks: two prompts that are genuine capacity walls for the 30B-MoE class (a KV-cache derivation and a multi-step planning question), and two prompts that are deterministic-rubric format misses (a Python-expression translation that needed the exact word *count*, and a quantization-trade-off summary that needed the exact string *Q5_K_M*).

:::define[Cost tier, in this article]
A *cost tier* is one rung in the cost-router's escalation ladder — an OpenAI-compatible endpoint plus the model id served at that endpoint, the predicates that gate routing to it (a keyword set OR a token-budget threshold), and a snapshot of its per-million-token prices. This article's reference config is three tiers: a local Spark lane on `:8080` ($0), an OpenRouter value lane on `openai/gpt-4o-mini` ($0.15/$0.60 per M), and an OpenRouter frontier lane on `anthropic/claude-opus-4.1` ($15/$75 per M). The router picks the *highest* tier whose predicate fires; otherwise the floor.
:::

:::define[Leak rate]
The fraction of prompts where the *local* strategy failed the deterministic rubric but the *frontier-only* strategy passed it. The reframed-per-HANDOFF headline metric of H6 — it answers "where does local stop being enough?" directly, without any cost-savings rhetoric on top. A leak rate of zero means the local 30B-MoE never needed help; a leak rate of 25% means a quarter of the workload genuinely demands a frontier model.
:::

:::define[Strategy, in this article]
One of three dispatch policies: `local-only` sends every prompt to the Spark lane (the no-router baseline + the $0 floor); `cost-routed` runs `CostRouterConfig.classify()` and dispatches to the picked tier; `frontier-only` sends every prompt to the frontier model (the no-router ceiling + the $ ceiling). The cost-routed strategy is the production proposal; the other two are the bounds the article measures it against.
:::

## The 12-prompt suite, sized for the failure-mode curve

The brain bakeoff used eight agent-typical prompts to discriminate among three lanes that all sat in the 30B-MoE class — the discrimination axis was *quality at fixed brain size*. H6 measures something different: the discrimination axis is *brain capacity ceiling*, so the suite needs deliberate spread across the difficulty range. Twelve prompts split four/four/four across three tiers:

- **4 simple prompts** — short factual lookups, format-strict JSON output, a Python-expression translation, and a list-format instruction-following test. None of them have escalation keywords; all are well under the 600-token standard threshold. Expected to stay on local.
- **4 standard prompts** — a `summarize` of the Q4/Q5 trade-off, a `compare` of unified vs discrete VRAM, an `analyze` of a five-row CSV with a deterministic numeric answer, and a long `compare` of LoRA vs full-parameter fine-tuning. The keywords are the trigger; gpt-4o-mini at $0.15/$0.60 per M is the value-tier cost target.
- **4 complex prompts** — a structured *proof by induction* with both a geometric intuition and a formal step-by-step argument, a *derivation* of the KV-cache footprint of Qwen3-30B-A3B at 64K context, a *multi-step* planning question that requires picking one model from a fixed inventory under three constraints, and a long-context paste — about 3,800 tokens of the H1 spec — with five specific facts to extract. The first three are keyword-triggered (`prove`, `derive`, `multi-step`); the fourth triggers the complex tier via the `min_input_tokens=3000` threshold without needing a keyword.

The router accuracy axis is the cheapest measurement in the whole article: the deterministic classifier doesn't touch a GPU and doesn't make an API call, so it costs nothing and runs in milliseconds. The expected-tier ground truth is encoded directly in the prompt JSON. As shipped, the router classifies **12/12** correctly — every prompt routes to the tier the author intended.

:::deeper[Why the router has no LLM classifier]
You could in principle stand up a small 1.5B model as a "router brain" — read the prompt, decide the tier, dispatch. On a Spark you almost certainly shouldn't. Three reasons. First, a 1.5B classifier eats unified memory that the 30B brain needs (the Spark holds one strong model warm at a time per the [H1 cockpit math](/field-notes/the-hermes-harness-on-spark/)). Second, an LLM classifier is opaque — when it misroutes a prompt, you can't read the decision; with a keyword set, you can. Third, the router's job is to be wrong cheap and right cheap; an LLM classifier is wrong-and-right *expensively*. The deterministic predicate is the OOM-correct, audit-correct, and latency-correct choice — even if its discrimination is coarser.
:::

## The bakeoff: three strategies, N=3 each

Three strategies, twelve prompts each, three attempts per prompt — 108 calls total. The local strategy hits the always-warm Qwen3-30B-A3B Q4_K_M lane on `:8080` and pays nothing; the routed strategy lets `CostRouterConfig.classify()` decide; the frontier strategy sends everything to `anthropic/claude-opus-4.1` and is the failure-mode ceiling. Every call records prompt-token and completion-token counts from the API response, computes the dollar cost from the snapshot prices in `evidence/openrouter_prices.json`, scores the answer against the prompt's rubric via `fieldkit.eval.score_answer`, and emits one row in `evidence/cost_router_results.json`.

A `--cap-usd 5.00` hard-stop guards against runaway frontier spend — the driver aborts mid-strategy if the cumulative OpenRouter total would exceed it. The cap didn't trip; total spend was **$1.85** for the full 108-call run, well under budget.

:::pitfall[The substring scorer bug that surfaced on prompt t07]
The H6 t07 prompt asks the model to compute the mean of a five-row CSV and put the number on its own last line. The check spec was `{"kind": "substring", "all": ["31.60"]}` — pass iff the literal string `31.60` is in the answer. The first smoke run reported FAIL even when the answer was literally `31.60`, because the `score_answer` substring path was reading only `any` and silently dropping `all` — a latent bug since the graded primitives landed in v0.11.0. The H5 vertical-router prompts dodged it by always combining `all + any` with discriminating `any` terms; the H6 numeric-answer prompt didn't, so the bug surfaced. The fix retired the silent-pass shape in v0.13.0 — `all` is now the AND-clause, `any` is the OR-clause, both empty is an explicit config-error failure. The four regression tests live in `test_eval_graded.py` so this can't drift back.
:::

## What the results actually say

The headline numbers from the bakeoff (the full record is in `evidence/cost_router_results.json`):

| Strategy | Majority pass-rate | Total $ for 36 calls | $ per 100 tasks |
|---|---|---|---|
| local-only | **8/12 (66.7%)** | $0.00 | $0.00 |
| cost-routed | 11/12 (91.7%) | $0.79 | $2.19 |
| frontier-only | 12/12 (100.0%) | $1.06 | $2.94 |

The local-only floor is two-thirds of the workload — meaning a third of the prompts in the suite were *not* reliably answered by the always-warm 30B-MoE at N=3 majority vote. That set has a specific shape that the article won't sandbag: the local lane consistently failed `s03` (a Python-expression translation where the rubric required the word "count"), `t05` (a 3-sentence summarize-the-Q4/Q5-trade-off where the rubric required mentioning Q5_K_M specifically), `c10` (the multi-step KV-cache derivation — 3/3 fail), and `c11` (the constrained model-picking plan from a fixed inventory — 3/3 fail). Two of those four are clean *capacity* fails — `c10` and `c11` are exactly the kind of structured-quantitative multi-step reasoning that the [brain bakeoff's p2 prompt](/field-notes/picking-the-hermes-brain-on-spark/) flagged as the 30B-MoE class's known wall. The other two are *format* fails — the model answered correctly but missed the rubric's specific required phrase, which is the cost of running a deterministic grader without an LLM-judge fallback.

The leak rate — the headline H6 metric — is **4/12 (33.3%)** of the workload: prompts where local failed but the frontier model passed at majority vote. Below that, the frontier model didn't help; above it, the frontier earned its price.

## The dollar curve, honestly

The cost-routed strategy lands at **$2.19** per hundred tasks against **$2.94** for frontier-only — a **25% spend reduction** while staying within **8.3 percentage points** of the frontier quality. That's the cost-savings story, and it's *secondary* to the leak-rate story: the cost savings are a function of how many prompts the local lane can handle, which is itself the failure-mode curve in disguise. If the leak rate were zero, the router would save 100% of the spend and the article would write itself; if the leak rate were 100%, the router would save nothing and the article would also write itself. The interesting territory is the middle — *measured* — and the H6 suite landed it at 33.3% leak / 25% savings / 8.3-point quality gap.

The local-only strategy is free but leaks 4/12 (33.3%) of the workload. The frontier-only strategy is at the cost ceiling but pays for prompts the local lane could have handled for free. The routed strategy is the production proposal *if* its quality lands within an acceptable margin of frontier; the result the bakeoff produced is reproducible from the snapshot prices and the prompt suite in `evidence/`. The two prompts where the cost-routed strategy diverged from the frontier ceiling were both in the simple tier — `s03` (Python translate) consistently failed local while never being escalated, because no complexity keyword fires on a 100-token literal-translation prompt and no token-budget threshold is met. That's an *escalation gap*, not a router failure: the keyword set was tuned around domain-typical signals (summarize, analyze, prove, derive) which don't appear in a one-shot instruction-following task. A reader running this measurement on a workload heavy on instruction-strict prompts would extend the keyword set; the router lets them.

:::pitfall[The frontier tier is NOT free for the prompts you don't send to it]
A reader's first instinct on seeing the dollar curve is to widen the complex-tier predicates — "if frontier is 100× more accurate on the hard prompts, let it answer more of them." The math doesn't work. Even at the article's measured leak rate, the *correct* routing decision sends the cheap prompts to local — not because the cheap prompts are easy for the frontier (they are), but because the frontier *costs* exactly the same per token regardless of the prompt's difficulty. Sending an easy prompt to Claude Opus pays the frontier price for a question the local lane would have answered correctly for $0. The cost router's editorial value is *not letting* the frontier model answer cheap prompts, not *getting it* to answer them.
:::

:::hardware[The cost router's hardware footprint is zero]
Unlike the H5 vertical router, the H6 cost router doesn't summon any new local lanes — it dispatches over HTTP to either the already-warm Qwen3-30B brain on `:8080` or to OpenRouter over the wire. No memory cost beyond the brain that was already warm; no cold-start penalty on the local path; no second GPU process to teardown. The router itself is pure Python — `CostRouterConfig.classify()` is a substring scan and a token-length comparison. The expensive component of the system is the *frontier model itself*, billed by OpenRouter at the snapshot prices in the published `router.yaml`.
:::

:::deeper[Token estimation without a tokenizer]
The router's complex-tier predicate has a token-budget arm — `min_input_tokens=3000` — so long-context prompts route to the frontier even when no complexity keyword fires. The naive way to compute "is this prompt over 3000 tokens" is to invoke the served model's tokenizer; for a router that wants to be a microsecond-class predicate, that's too much. `fieldkit.harness.estimate_tokens` instead uses the venerable 4-chars-per-token heuristic: `max(1, len(text) // 4)`. The constant is the GPT-family rule of thumb; for modern BPE tokenizers it's within ±15% on English text, which is plenty for a routing decision. A 5% over- or undercount doesn't flip the tier — the threshold is meant to be coarse, not surgical. The trade is: zero dependencies, microsecond latency, no surprises when a tokenizer's vocabulary updates underneath the router. The router stays pure Python.
:::

## Publishing the router as a `harness` artifact

The router is now [`Orionfold/spark-hermes-cost-router`](https://huggingface.co/Orionfold/spark-hermes-cost-router), the second `kind: harness` artifact in this series and the sibling of H5's `spark-hermes-vertical-router`. The card embeds the live `cost-router.yaml` (with snapshot prices), a `hermes.yaml` block that points Hermes at the local brain by default, a `.env.example` showing where `OPENROUTER_API_KEY` lives, and a `Methods` backlink to this article. The per-tier lane rows use the new `LaneMetricColumns` machinery in v0.13.0 to swap the H2-style tool-call columns for `$/M input` and `$/M output` — the more honest framing of what a cost router actually costs.

The published card also carries `known_drift` bullets with explicit fractions, because the snapshot prices, the OpenRouter model availability, and the threshold tuning could all drift between this measurement and a reader's reproduction:

- The OpenRouter prices were snapshotted at the time-of-measurement (UTC timestamp in `evidence/openrouter_prices.json`). Prices change; the card carries the snapshot date.
- The complex-tier `min_input_tokens=3000` threshold was tuned to the H6 suite's distribution. A workload with different long-context-to-short-prompt ratios should re-tune.
- The leak rate is measured over 12 prompts × N=3 attempts. It's a point measurement on a synthetic suite; production workloads will exhibit their own leak rates, which is the whole point of having the router instrumented.

## Closing the Harnesses arc

H6 closes the spec. H1 through H4 was the must-have spine — the install, the serving lane, the hardening, the keystone — and the brain bakeoff plus H5 and H6 were the leverage-multiplier follow-ons that turned the harness from a single-lane cockpit into a multi-tier dispatch surface. The whole arc shares one pattern: every routing decision the Spark makes is a *deterministic predicate*. The vertical router is a keyword scan; the cost router is a keyword scan plus a token-length comparison. Both are auditable, both are zero-marginal-memory, both are wrong-cheap and right-cheap. The frontier-LLM-as-router pitch never enters the picture, and that's the whole editorial position of the Harnesses arc — a Spark + Hermes + `fieldkit` agent harness is configured with predicates, not with another model.

The next moves from here are queued in the [HANDOFF](https://github.com/manavsehgal/ai-field-notes): the gpt-oss brain-class bakeoff (does a 120B-class MoE clear the multi-step planning wall?), the patent-strategist corpus MPEP-hallucination fix, the spark-playground spec, and a v0.12.1/v0.13.1 fieldkit polish cycle. The Harnesses arc itself is done.

---

**Catalog page:** [`/artifacts/harnesses/spark-hermes-cost-router/`](/artifacts/harnesses/spark-hermes-cost-router/) — positioning, lane variants with measured throughput, the recommended lane, and bounded drift — the full Spark-agent harness profile.
