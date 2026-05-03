---
title: "Derisking the Cloud Pretrain — How a $5K Spark Saves $50K on H100 Rentals"
date: 2026-04-30
author: Manav Sehgal
product: Foundation
stage: training
also_stages: [foundations, agentic]
difficulty: advanced
time_required: "~30 minute read · math + economics, no GPU required"
hardware: "NVIDIA DGX Spark"
tags: [training, pretrain, cloud, h100, h200, beyond-spark, autoresearch, dgx-spark, economics]
summary: "The Spark is too small for a serious pretrain — but it's the right size for the recipe-search that precedes one. Cull 100 candidate architectures down to 3 on one Spark for ~$1 of electricity, then book the cloud node knowing what to train. The expected savings per campaign run into the thousands."
signature: SparkSandboxToCloud
series: Looking Beyond Spark
---

You cannot pretrain a 7-billion-parameter Llama-class model on a DGX Spark from scratch. A Chinchilla-optimal 7B run needs around 140 billion training tokens — six times the parameter count, ten times if you intend to overtrain — and the FLOP budget that comes with it. On one GB10 the wall clock is months; on a single H100 it is weeks; on a properly-spec'd 8-GPU cloud node it is days. The cloud is the right tool for that workload. The Spark is not.

The argument of this article is that this fact about the Spark is *not* its weakness. It is the precondition for the Spark's most undersold use case — the **recipe lab** that decides what the cloud node should actually run when you finally book it. A pretraining campaign is not one job; it is a hundred candidate jobs collapsing to one. The cloud is the right tool for the *one*. The Spark is the right tool for the *hundred*.

The arithmetic that follows is the case for treating your DGX Spark as a wind tunnel before any aircraft is built. A hundred-iteration architectural sweep on one Spark costs about a dollar of marginal electricity and a couple of hours of wall time. The same sweep at meaningful scale on cloud — single-H100 spot, sustained — runs ~$5 to ~$70 depending on how target-faithful you make it. The much larger number is what you save on the *back end*: the wrong-architecture cloud campaign you didn't book because the Spark already told you it would not work. At a 50% wrong-pick rate without prior signal — conservative for blind architectural search — a $1 Spark sweep gates ~$1,679 in expected loss against a small ($3K) cloud campaign and ~$7K against a medium ($14K) one. Scaled to a 70B Llama-class run on 1024 H100s for 21 days, the same Spark dollar gates more than a million.

## Why this matters for a personal AI builder

The audience for this article is the engineer at a startup, the research lead at a small lab, or the independent builder who has cloud credits or budget — between $5K and $500K — earmarked for *one* serious pretraining run, and exactly one chance to spend it well. That decision is downstream of an architectural search the cloud is a poor place to perform. Doing it on the cloud means paying $50 to $5,000 *per candidate* to discover that your candidate doesn't work. Doing it on the Spark means paying ~$0.01 per candidate to discover the same thing. The architectural search isn't where the money is — but it's where the *information* is, and information is what compounds.

The Spark's uber move for a personal AI power user has, until this article, been about prototyping at a scale your desk can afford ([fine-tuning a 100B Nemotron, sized](/articles/gpu-sizing-math-for-fine-tuning/) being the prior chapter). Derisking a cloud pretrain is the same idea applied one level up: the Spark on your desk is the rig that lets you walk into the cloud-vendor billing portal with a recipe, a measured trajectory, and a defensible architectural argument — instead of a prayer.

## Where the cloud cost actually lives

The cloud bill for a serious pretrain decomposes into three pieces, and only one of them is what most people think it is.

1. **The final-training run itself.** The headline number — `8× H100 × 168 hr × $2.50/hr ≈ $3.4K` for a 7B-class spot run, several × that on-demand or for larger models. This is what gets quoted when someone says "we trained X for $Y."
2. **The architectural search that preceded it.** Usually buried in the same line item. If you ran 30 candidate architectures at any meaningful scale before settling, that's another `30 × $30 to 30 × $300` depending on how target-faithful the search was. People don't quote this number because they wish they hadn't spent it.
3. **The expected loss from picking wrong.** The hidden one. If the architectural search wasn't informative — or didn't happen at all — the wrong-pick rate is well above zero, and the cost is the *next* final-training run after the first one didn't converge. At a 50% wrong-pick rate, the expected loss is half of one final-training run per campaign. Anyone who has watched a colleague restart a $30K cloud booking three weeks in knows this number is not abstract.

The Spark eliminates the second of those three line items entirely (replaces $50–$5K of cloud sweep with ~$1 of Spark electricity) and reduces the *expected value* of the third by an integer factor (cuts the wrong-pick rate from "blind" to "informed"). The first line item it does not touch — you still pay the cloud bill for the final-training run. But you pay it once, on the right architecture, with measured early-loss curves to back the decision.

<figure class="fn-diagram" aria-label="A three-phase timeline showing how a cloud pretraining campaign decomposes when the Spark is part of the toolchain. Phase 1 — Spark recipe lab — runs 100 candidate architectures via the A4 agent loop, 88 seconds per iteration, 2.4 hours total wall, costing about one dollar of marginal electricity, culling to 10 promising candidates. Phase 2 — Spark stress test — runs the top 3 candidates for 1000 steps each, 22 hours wall, costing 40 cents, culling to 3 finalists. Phase 3 — cloud commit — books an 8×H100 node for one week to train the chosen architecture to Chinchilla optimal, costing 3,360 dollars at spot rates. A reject path under Phase 1 and Phase 2 shows that candidates that died on the Spark never see the cloud.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Three-phase pretraining campaign timeline: Phase 1 Spark recipe lab cuts 100 candidates to 10 for ~$1; Phase 2 Spark stress test cuts 10 to 3 for $0.40; Phase 3 Cloud commit trains 1 model on 8×H100 for ~$3,360." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d-derisk-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.03"/>
        <stop offset="50%"  stop-color="var(--color-primary)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.03"/>
      </linearGradient>
      <linearGradient id="d-derisk-cloud-band" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.04"/>
        <stop offset="50%"  stop-color="var(--svg-accent-orange)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.04"/>
      </linearGradient>
      <linearGradient id="d-derisk-p1-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <linearGradient id="d-derisk-p2-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.08"/>
      </linearGradient>
      <linearGradient id="d-derisk-p3-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-orange)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.10"/>
      </linearGradient>
    </defs>
    <rect x="20" y="60" width="560" height="220" rx="10" fill="url(#d-derisk-band)" stroke="none"/>
    <rect x="600" y="60" width="280" height="220" rx="10" fill="url(#d-derisk-cloud-band)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 220 170 L 300 170"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 500 170 L 580 170"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 760 170 L 780 170"/>
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 160 230 L 160 310 L 720 310 L 720 230"/>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node fn-diagram__node--accent" x="60" y="120" width="160" height="100" rx="10" style="fill: url(#d-derisk-p1-grad)"/>
      <rect class="fn-diagram__node" x="300" y="120" width="200" height="100" rx="10" fill="url(#d-derisk-p2-grad)" stroke="var(--color-text-muted)" stroke-width="1"/>
      <rect class="fn-diagram__node" x="580" y="120" width="180" height="100" rx="10" fill="url(#d-derisk-p3-grad)" stroke="var(--color-text-muted)" stroke-width="1"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="780" y="138" width="80" height="64" rx="8"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--display" x="140" y="148" text-anchor="middle">PHASE 1</text>
      <text class="fn-diagram__label" x="140" y="170" text-anchor="middle">Spark recipe lab</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="140" y="187" text-anchor="middle">100 → 10 candidates</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="140" y="203" text-anchor="middle">100 iters · 2.4 hr · ~$1</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="400" y="148" text-anchor="middle">PHASE 2</text>
      <text class="fn-diagram__label" x="400" y="170" text-anchor="middle">Spark stress test</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="400" y="187" text-anchor="middle">10 → 3 finalists</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="400" y="203" text-anchor="middle">3 × 1k steps · 22 hr · $0.40</text>
      <text class="fn-diagram__label fn-diagram__label--display" x="670" y="148" text-anchor="middle">PHASE 3</text>
      <text class="fn-diagram__label" x="670" y="170" text-anchor="middle">Cloud commit</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="670" y="187" text-anchor="middle">3 → 1 trained model</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="670" y="203" text-anchor="middle">8× H100 · 168 hr · ~$3.4K</text>
      <text class="fn-diagram__label" x="820" y="170" text-anchor="middle">7B</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="820" y="190" text-anchor="middle">trained</text>
      <text class="fn-diagram__label fn-diagram__label--accent" x="30" y="40" text-anchor="start">PRETRAINING CAMPAIGN, DERISKED</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="30" y="58" text-anchor="start">three phases · two on the Spark · one on the cloud</text>
      <text class="fn-diagram__label fn-diagram__label--mono fn-diagram__label--muted" x="160" y="335" text-anchor="middle">candidates that died on the Spark never see the cloud</text>
    </g>
    <g class="fn-diagram__symbols">
      <g class="fn-diagram__icon" transform="translate(128 92)"><path d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0V12a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 12V5.25"/></g>
      <g class="fn-diagram__icon" transform="translate(388 92)"><path d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></g>
      <g class="fn-diagram__icon" transform="translate(658 92)"><path d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z"/></g>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__label fn-diagram__label--accent" x="30" y="380" text-anchor="start">EXPECTED VALUE — WHY THIS MATH WORKS</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="30" y="403" text-anchor="start">blind cloud booking, 50% wrong-pick rate → expected loss ≈ $1,680/campaign</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="30" y="421" text-anchor="start">spark filter, $1 of electricity → ratio 1,670× per campaign run</text>
    </g>
  </svg>
  <figcaption>Two phases on the Spark gate one phase on the cloud — and the cloud phase is the only one that costs more than coffee. The dashed reject-path is where the savings actually come from: candidates the Spark culled never see an H100.</figcaption>
</figure>

## Phase 1 — the Spark recipe lab (~$1, ~2 hours)

Phase 1 is the [autoresearch agent loop](/articles/autoresearch-agent-loop/) pointed at a 7B-shaped target architecture instead of an open exploration. The agent proposes a candidate config, the trainer runs it for 60 steps on a proxy model — small enough that one iteration completes in roughly 88 seconds on a Spark — and the loop records `val_bpb` against the trajectory. After 100 iterations, the trajectory log holds 100 (candidate, val_bpb) pairs. Sort, take the top 10, save the rest.

What makes Phase 1 cheap is not just the Spark's electricity cost. It is the **proxy substitution** that the agent loop already encodes: the search runs on a 200M-class model whose head dimension, FFN ratio, and activation function all match the 7B target, but whose total parameter count is two orders of magnitude smaller. The shape of the architectural search (which knob settings dominate, where the loss surface is convex, which combinations interact) transfers up to the target. The absolute numbers do not need to. This is the same trick that makes it possible to run scaling-law experiments at 50M and project to 70B — it is what every serious pretrain campaign already does on the cloud, just done on a desk for 1/300th the cost.

The cost arithmetic for Phase 1 lives in [`evidence/cost_arithmetic.py`](evidence/cost_arithmetic.py) and runs from environment variables so it stays current as cloud spot prices move. The defaults — H100 at $2.50/hr per GPU, Spark at 240 W sustained training draw, $0.13/kWh, 1.5-year amortization horizon — produce the table below. The column the article is selling is the Spark column. The rightmost column is the alternative the Spark replaces.

```text
$ python3 evidence/cost_arithmetic.py | jq .campaign_100_iters_usd
{
  "spark_electricity_only":      0.08,
  "spark_total_cost_of_use":     1.01,
  "h100_single_proxy":           6.11,
  "h100_8gpu_node_proxy":       48.89,
  "h100_8gpu_node_target_scale": 2933.33
}
```

The Spark electricity-only line ($0.08 for 100 iterations) is the marginal cost — the Spark is on your desk anyway. The total cost-of-use line ($1.01) includes amortized hardware over a 1.5-year horizon and is the more honest "what did this run actually cost." The cloud lines escalate: $6 to do the same 100-iter sweep on a single rented H100 at proxy scale, $49 if you parallelize across an 8-GPU node for speed, $2,933 if you run the same sweep at *target* scale on the cloud (60× longer per iter because the model is 60× larger). The savings ratio depends on which alternative you score against; either way, the Spark column is where you start.

## Phase 2 — the Spark stress test (~$0.40, ~22 hours)

Phase 1's 60-step taste test catches gross failures and ranks survivors by early-loss slope. It does not catch issues that only emerge at 1,000+ steps — late-onset divergence, optimizer instabilities, gradient norm blowups under longer schedules. Phase 2 is the unattended stress test: run each of the top 3 candidates for 1,000 steps on the Spark and watch for the failure modes that take time to show up.

22 hours of Spark wall clock is one overnight. At the same total cost-of-use rate as Phase 1, that is roughly $0.40 — call it forty cents to confirm the recipe is stable past the kernel-timing window. If two of the three candidates survive, you have a primary plus a fallback for the cloud booking. If all three survive, you ship the highest-ranked one and keep the others as restart candidates. If only one survives, you have learned something genuinely useful before booking a cloud node: that the architectural envelope is narrow and the next sweep should explore tighter neighborhoods.

The reason Phase 2 belongs on the Spark and not on the cloud is the same reason as Phase 1, just at a longer time horizon. A 1,000-step run on a single cloud H100 costs ~$0.30 per candidate at proxy scale (close to break-even with the Spark) and ~$18 at target scale on an 8-GPU node. The cloud is competitive on cost for Phase 2 only if you don't have a Spark. Once you do, the math says: spend the watt-hours, not the dollars.

## Phase 3 — the cloud commit (~$3,360, ~1 week)

Phase 3 is the only piece that the Spark cannot do — and it is the only piece you should pay full cloud price for. Book the 8× H100 node, run the surviving best candidate to Chinchilla-optimal (or whatever schedule you've decided on), and watch the loss curve land where the Spark stress test predicted. At spot rates ($2.50/hr per GPU, $20/hr for the node, 168 hours for a one-week run), the bill is around $3,360. At on-demand rates and a 3-week schedule for a slightly larger target, it climbs into the low five figures. At a 70B Llama-class campaign on 1,024 H100s for 21 days, the bill is in the millions. The dollar amount scales with the campaign's ambition; the *Spark recipe-lab cost stays at $1*.

What changes between the small and the large case is the **expected savings**, not the absolute Spark cost. At a 50% wrong-pick rate without prior signal — conservative for blind architectural search — the Spark filter prevents one wrong final-training booking per two campaigns in expectation. For the small case, that is $1,680 of expected savings per Spark dollar spent. For the medium case, $7,055. For the 70B Llama-class case, the savings cross seven figures. The ratio of expected savings to Spark cost is `~1670×` for the small campaign and `~7000×` for the medium one.

```text
$ python3 evidence/cost_arithmetic.py | jq .expected_value_argument
{
  "wrong_pick_rate": 0.50,
  "expected_loss_from_blind_booking_usd": 1680.00,
  "spark_recipe_search_cost_usd":            1.01,
  "expected_savings_per_campaign_usd":    1678.99,
  "ratio_savings_to_spark_cost":          1670
}
```

There is no scenario inside this arithmetic where buying a Spark and using it as a recipe lab loses money against the alternative of going to the cloud blind. The break-even is reached after the very first prevented wrong-pick.

## Verification — what success looks like on the Spark for a cloud-bound workload

Success in Phase 1 is a 100-row `trajectory.jsonl` file under `articles/autoresearch-agent-loop/evidence/` with `val_bpb` deltas large enough to rank the candidates. Success in Phase 2 is three loss curves drawn over 1,000 steps each with no late-onset divergence. Both artifacts are plain text. Both are reproducible. Both are what you bring to the cloud-vendor billing portal as the justification for booking the node.

What success specifically does *not* look like on the Spark is convergence. You are not training the model on the Spark — you are searching for the architecture you will train on the cloud. The Spark's job is to give you a defensible reason to skip 90 candidates and pay attention to the other 10. The cloud's job is to take your three finalists and produce one trained model. Neither machine is being asked to do the other's job.

Hardware-aware verification: for Phase 1, watch GPU utilization during a representative iteration with `nvidia-smi -lms 500` and confirm the Spark is doing real work (steady ~95% utilization, ~80 GB of unified memory engaged). For Phase 2, log loss every 50 steps and plot the three candidates side-by-side; any candidate that goes flat or diverges before step 800 has just told you something the cloud would have charged $300 to learn. For Phase 3, the loss curve in the first 24 hours of cloud training should land within ~5% of the Spark stress-test extrapolation. If it doesn't, your proxy substitution is broken — investigate before letting the cloud node burn through the rest of the week.

## Tradeoffs and gotchas

The argument here has four important caveats. None of them break it; all of them affect how you run a real campaign.

**FP8 numerics differ between GB10 and H100.** Hopper FP8 (E4M3 and E5M2 with their specific calibration scheme) is not bit-exact to Blackwell FP8 — and the Spark's Blackwell GPU is not bit-exact to either Hopper FP8 or to the next-gen B200. In practice the throughput delta is under 2% and the accuracy delta is essentially zero on most architectures, but a recipe that depends on a specific FP8 calibration choice should be validated with one Phase 2 run on the cloud target before committing the full Phase 3 budget. The fix is to budget for an extra cloud-side day at the front of Phase 3 — call it the "FP8 sanity check" — and treat it as a tax against the Spark filter's savings.

**Single-GPU sweep does not exercise multi-GPU parallelism at all.** If your final cloud training uses tensor parallelism (TP=2, TP=4) or pipeline parallelism (PP=2, PP=4), the Spark is not validating those code paths. Plan a cloud-side "TP=4 / PP=2 sanity check" for one day before opening the rest of Phase 3 — this is not optional, it is how you avoid discovering on day three of a week-long run that your tensor-parallel attention is wrong.

**Memory-bound workloads behave differently with PCIe between GPUs.** The Spark has 128 GB of unified memory and zero PCIe between CPU and GPU; a cloud H100 has 80 GB per GPU with PCIe 5 between them. KV cache-heavy or very-long-sequence workloads can hit memory-traffic patterns the Spark cannot reproduce. The defense is the same as for FP8: budget one cloud-side day to confirm that the Spark-measured throughput shape transfers under the cloud's memory topology.

**The agent loop's 60-step filter is not exhaustive.** Even with Phase 2's 1,000-step stress test, the longest a candidate runs before the cloud commit is roughly 1/100th of its eventual cloud schedule. Some failure modes — gradient instabilities from particular LR-schedule + batch-size interactions, late-onset loss spikes from data ordering — only manifest at scale. The Spark filter cuts the wrong-pick rate; it does not eliminate it. The expected-savings math in the arithmetic table assumes a 50% post-filter wrong-pick rate, which is conservative; in practice with both Phase 1 and Phase 2 running cleanly you can expect closer to 10–20%. That makes the savings math even more lopsided.

## What this unlocks

Three concrete things the reader can do this week with what's in this article.

**Run a real recipe-lab session for a cloud booking you've been postponing.** If you have a planned pretrain on the calendar but haven't decided what architecture to commit to, copy [`evidence/recipe_lab_template.py`](evidence/recipe_lab_template.py) into the [autoresearch agent loop's evidence directory](/articles/autoresearch-agent-loop/), point its `ProxyMenu` at your target shape, and let it run overnight. The next morning you have a `trajectory.jsonl` to take to the cloud-vendor billing portal — and a defensible story about why this architecture is the one to fund.

**Compute your own break-even number for the Spark as a recipe lab.** Re-run [`cost_arithmetic.py`](evidence/cost_arithmetic.py) with your actual cloud rates, your actual planned campaign size, and your honest estimate of your wrong-pick rate without the filter. The ratio of expected savings to Spark cost is rarely below 100× and often over 1,000×. Once you have that number for your specific situation, the Spark stops being "the small machine on the desk" and starts being "the line item in the AI infrastructure budget that pays for itself in one campaign."

**Treat the trajectory log as a portable artifact across campaigns.** A `trajectory.jsonl` from one campaign — even a campaign you never ran on the cloud — is calibration data for the *next* one. The agent loop in [autoresearch](/articles/autoresearch-agent-loop/) reads its own history when proposing candidates; over multiple campaigns the proposer learns which knobs predict which gains. The first recipe-lab session you run is the most expensive (it has to discover everything from scratch). The fifth is essentially free (the proposer already knows what to try). This is the per-Spark, per-builder version of what the Llama-class scaling-laws papers did at company scale — and it is exactly the kind of thing the [guardrails for code generation](/articles/guardrails-for-code-generation/) exist to keep honest as the trajectory grows across many sessions.

## State of the apps — as of this article

The **Looking Beyond Spark** thread is now three articles long: [the 100B Nemotron sizing piece](/articles/gpu-sizing-math-for-fine-tuning/) (the first in the series), [the layman recap of the autoresearch loop and its 4-tier training roadmap](/articles/what-the-agent-actually-built/), and this one. All three follow the same pattern — work the cloud-side arithmetic on the Spark, present the math as the artifact, and treat the cloud spend as a downstream consequence of an upstream decision. The other three arcs are unchanged: Second Brain has [its four pieces](/articles/mcp-second-brain-in-claude-code/), the LLM Wiki arc remains unstarted, and the Autoresearch arc sits at five published pieces ([NeMo Framework](/articles/nemo-framework-on-spark/), [the baseline training loop](/articles/baseline-training-loop-on-spark/), [the Curator data-prep envelope](/articles/nemo-curator-training-data-prep/), [the agent loop](/articles/autoresearch-agent-loop/), [the guardrails](/articles/guardrails-for-code-generation/), and the [layman recap](/articles/what-the-agent-actually-built/)) with four to go.

The Spark is now wearing a third hat in this blog. First it was an inference rig. Then it was a training rig. With this article it is also a recipe lab — the small machine on the desk that decides what the big machines in the cloud get to do. That is, it turns out, the most expensive role you can possibly assign to a $5,000 box, because the cost being measured is not the box's electricity but the cloud booking it gates. The Spark on the desk pays for itself on the *first* prevented wrong-pick. After that, every Spark dollar is making the cloud bill smaller.
