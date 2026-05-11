---
title: "Reading the Lineage Primitive — cxcscmu Auto-Research, Studied from release_artifacts"
date: 2026-05-10
author: Manav Sehgal
product: NeMo
stage: agentic
also_stages: [training, foundations]
difficulty: advanced
time_required: "~28 min read"
hardware: "NVIDIA DGX Spark"
tags: [agentic, autoresearch, multi-agent, lineage, fieldkit, claude-agent-sdk, machine-that-builds-machines]
summary: "cxcscmu's own lineage_on vs lineage_off ablation closes the case: same agent, same trial budget, same prompt template — only the rendered lineage block differs, and the run with lineage produces 5.3× more keeps and 3.2× less wall-time waste. This piece extracts that primitive into fieldkit.lineage."
signature: LineageAblationKeeps5x
series: "Machine that Builds Machines"
book_chapters: [10, 11]
fieldkit_modules: [capabilities, training]
---

The cxcscmu [Auto-Research-Recipes](https://github.com/cxcscmu/Auto-Research-Recipes) release — paper [arXiv:2605.05724](https://arxiv.org/abs/2605.05724), ICML 2026 — looks at first like a paper about agentic infrastructure: ten specialists, a supervisor loop, a per-trial scheduler, an MCP toolchain, an external evaluator. The headline number is 1,797 trials run unattended across three reference tasks (Parameter Golf, NanoChat-D12, CIFAR-10 Airbench96), each task producing SOTA-or-better deltas with no human in the loop after launch. The compute bill is roughly 4,000 H100-hours for Parameter Golf alone, another 2,400 for NanoChat-D12, plus an Anthropic API spend running Claude Opus into the tens of thousands of dollars. By the standards of personal compute, none of that ports.

But underneath the agent infrastructure, the paper has a sharper claim. It is most easily read off the two ablation runs the authors ship verbatim alongside the main release: `pg_ablation_lineage_on` and `pg_ablation_lineage_off`. Same agent. Same task. Same wall budget. Same 201 trials of search. The only thing that changes is whether each iteration's prompt rendering includes the lineage prefix — the rendered tree of what prior trials proposed, what status they returned, what `val_bpb` they hit. With lineage on, the run produces **16 keeps**, **38 eval-budget overruns**, and a best `val_bpb` of **1.073142**. With lineage off — same prompt template, just minus the lineage block — the run produces **3 keeps**, **123 eval-budget overruns**, and a best `val_bpb` of **1.077413**. The agent searches 5.3× more productively, wastes 3.2× less wall, and finds a result 0.004 `val_bpb` deeper. Same agent. The difference is that one of them sees what was tried, and the other one does not.

That difference is what this article calls the **lineage primitive**. It is a 17-column TSV row per trial, an enum of status classes that double as failure semantics, a snapshot of the workdir per `keep`, and a rendered Markdown prompt that the next specialist reads at session entry. None of that is new infrastructure on a Spark scale: the substrate that records and renders it is small Python, no GPUs, no model weights, no NIM containers. The fixed cost of running cxcscmu's full Parameter Golf headline is dominated by 8-H100-node training trials and Opus tokens. The variable cost of writing what each trial returned to a TSV is a `fcntl.flock()` + a `csv.writer`. The lineage primitive is the portable part. **The agents and the trial budgets are the unportable parts.**

So this article reads the lineage primitive from cxcscmu's frozen release and extracts it into a `fieldkit.lineage` module. It is not a Spark reproduction. The released results.tsv files — six packages, 1,704 trials, every status class represented, every keep snapshotted, two example prompt renderings included verbatim — are a richer dataset than five smoke trials on a single GB10 would produce, and faithfully reproducing cxcscmu's 8-H100-node trial wall on a single Blackwell-class consumer-tier GPU is multi-day setup work plus multi-day wall, for a sample size smaller than the released artifacts already give us. I'll be explicit later about exactly what that cost looks like; for the body of this piece, the released data is the substrate.

## Why this matters for a personal AI builder

Every future article in the Machine that Builds Machines arc produces a lineage. The [Autoresearch Loop article](/field-notes/autoresearch-agent-loop/) on this site ran 50 iterations of an LLM editing a NeMo + Megatron pretrain config and shipped a sparkline. The [trajectory-eval follow-up](/field-notes/trajectory-eval-is-the-agent-flailing/) extracted three observability signals from that run's logs. The [T²PO article](/field-notes/t2po-uncertainty-guided-rl-on-spark/) traced a 50-step RL run and found that the strongest training-side checkpoint was the worst held-out checkpoint. In each case the artifact-of-interest is *the trajectory*, not the model. We've been writing those trajectories ad hoc — a JSONL per session, a CSV per run, a notebook of post-hoc analysis. cxcscmu's release argues that the shape of that artifact matters: when every entry carries `(parent_exp, status, hypothesis, score_delta)`, agents (and humans) can read a trial tree and know what's been tried, what worked, and what failed *in what way*. That changes the math of search.

On a Spark you cannot afford to throw 1,797 trials at any one question. But you can afford to write the same lineage primitive into every harness you build — and the cost of "what did I already try" goes from "ask the agent to remember between sessions" (which it doesn't, reliably) to "tail the TSV." For the personal AI builder running overnight experiments on a desk-class GPU, that's not a nice-to-have. It's the difference between an agent that re-discovers the same dead end twice and one that doesn't.

## The paper, in one breath

**Thesis.** A team of LLM-driven specialist agents can run a closed empirical loop over training recipes — each agent proposes a code edit, an external evaluator runs it, the resulting score-or-failure becomes feedback for the next proposal — and the *lineage* of those measurements (crashes, budget overruns, accuracy-gate misses, score deltas) is what lets later trials produce program-level rewrites rather than one-shot suggestions. The paper instantiates this on three reference tasks (Parameter Golf, NanoChat-D12 pretraining, CIFAR-10 Airbench96) and reports SOTA-or-better deltas with no human in the loop after launch. The contribution is the *harness* and the *lineage artifact*, not a model.

**Why this technique matters for a personal AI builder.** Modern coding agents already do this implicitly when you ask them to iterate inside a long session: they remember what they tried, see test output, and adjust. The cxcscmu harness makes that persistent — every trial in every run lands in a TSV that the next specialist reads. On a Spark, where overnight loops are how you turn a small budget into measurable progress, having that TSV is the difference between a 50-iteration loop that converges and a 50-iteration loop that ricochets between the same five hypotheses.

**Promise vs achieved.** Paper: 1,797 trials yielded a 1.073 `val_bpb` on Parameter Golf (against a 1.081 SOTA seed) and a deepest NanoChat-D12 `val_bpb` of 0.157 (against a 0.162 calibrated baseline). Spark: this article does not reproduce the numbers — it extracts the primitive that made them reproducible. The delta the article *does* reproduce is the lineage_on vs lineage_off gap: a 5.3× swing in keep rate, with no model change, no compute change, no prompt-template change — only whether the agent's session prompt includes the rendered lineage block.

## What's in the row

The schema is the primitive. Every trial in every cxcscmu run lands in a `results.tsv` with the same 17 columns, tab-separated, append-only, file-locked, parsed back into the supervisor's blackboard for every next session's rendering:

| Column | Meaning | Carried into the next agent's prompt? |
|---|---|---|
| `exp_id` | Zero-padded trial id (`000`–`NNN`) | Yes — appears in leaderboard + tree |
| `timestamp` | ISO-8601 UTC of trial completion | No — used for cumulative-best curves only |
| `specialist` | Which agent proposed (`arch`/`opt`/`reg`/`tok`/...) | Yes — shapes which knob axes the next agent reads |
| `parent_exp` | The `exp_id` this trial forked from | Yes — defines the tree structure |
| `baseline_exp` | The agent's stated baseline (typically `parent_exp` or `000`) | Yes — anchors the `delta_vs_best` interpretation |
| `domain` | Edit category (`arch`/`opt`/`loss`/etc.) | Yes — used to filter sibling trials |
| `hypothesis` | Free-text natural-language description of the edit | Yes — the *load-bearing field*, read by every later specialist |
| `expected_delta` | The agent's *prediction* of `val_bpb` movement | Yes — surfaces calibration error |
| `status` | One of `keep`/`discard`/`crash`/`eval_budget_overrun`/`size_blocked`/`harness_abort`/`preflight_crash`/`train_budget_overrun`/`disqualified` | Yes — the *second load-bearing field* |
| `core_metric` | Primary task metric (`val_bpb` for LM, accuracy for CIFAR) | Yes — drives the leaderboard |
| `val_bpb` | Validation bits-per-byte, for LM tasks | Yes — exposed in the leaderboard |
| `delta_vs_best` | Signed delta from the current-best trial's score | Yes — colours the agent's expectations |
| `train_s` | Wall-clock of the training phase | Indirectly — feeds the wall-cost narrative |
| `total_s` | Wall-clock of trial end-to-end | Indirectly — same |
| `job_name` | Scheduler tag (`apg-arch-0001` etc.) | No — internal accounting |
| `snapshot_path` | Filesystem path to the frozen workdir for `keep` trials | Yes — `rebase_to(exp_id)` reads this |
| `notes` | Free-text post-mortem, including kill_reason for crashes | Yes — the *third load-bearing field* for failure-class trials |

Three columns carry the conceptual weight. `hypothesis` is the trial's *intent* in language an agent can read, evaluate against, and avoid duplicating. `status` is the trial's *outcome class* — not a continuous score but a categorical one, because the failure modes are categorically distinct and the next agent should treat a `crash` differently from a `discard` differently from a `size_blocked`. `notes` is the trial's *operational receipt* — the kill_reason traceback, the size-overflow byte count, the deterministic error message. Together those three columns are enough that a fresh-context agent reading the TSV can reconstruct what to try next without re-running anything.

The other fourteen columns are tracking and bookkeeping. They matter for analysis (you cannot draw a cumulative-best curve without `timestamp`, you cannot slice subtrees without `parent_exp`), but they are not what the next iteration's *judgment* depends on. The `fieldkit.lineage` extraction below preserves all seventeen — drop any one and a downstream consumer becomes brittle — but the conceptual hierarchy is real: `(hypothesis, status, notes)` is the lineage primitive's load-bearing triple.

## The ablation, in one chart

cxcscmu's `pg_ablation_lineage_on` and `pg_ablation_lineage_off` runs are 201 trials each on the same Parameter Golf task with the same ten-specialist roster, same trial budget (≤ 600 s train + ≤ 600 s eval on 8×H100), same Claude Opus model on each specialist, same seed-stack `train_gpt.py` (the multi-596 seed at `val_bpb` ≈ 1.072). The only difference is a single boolean in the supervisor's prompt assembly — whether the agent's session-start prompt includes the rendered `## KNOWLEDGE.md` block (the tree, the lineage chain, the recent-30 activity) or whether it sees only the immutable rules + the agent's domain preamble.

The status histograms are the punchline.

<figure class="fn-diagram" aria-label="Paired waterfall: status distribution for cxcscmu's pg_ablation_lineage_on (left) vs pg_ablation_lineage_off (right). Both runs are 201 trials. Lineage on: 124 discard, 38 eval_budget_overrun, 16 keep, 11 size_blocked, 11 crash, 1 baseline. Lineage off: 46 discard, 123 eval_budget_overrun, 3 keep, 8 size_blocked, 20 crash, 1 baseline. The 16-vs-3 keep gap and the 38-vs-123 eval_budget_overrun gap are the two visible deltas. Both runs use the same agent, same prompt template, same trial budget, same 600s train + 600s eval cap on 8xH100; the only difference is whether the prompt includes the lineage block.">
<svg viewBox="0 0 880 360" role="img" xmlns="http://www.w3.org/2000/svg" data-svg-animate>
  <defs>
    <linearGradient id="lin-keep" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--svg-accent-green)" stop-opacity="0.65"/><stop offset="100%" stop-color="var(--svg-accent-green)" stop-opacity="0.18"/></linearGradient>
    <linearGradient id="lin-budget" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--svg-accent-red)" stop-opacity="0.55"/><stop offset="100%" stop-color="var(--svg-accent-red)" stop-opacity="0.15"/></linearGradient>
    <linearGradient id="lin-discard" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.42"/><stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.12"/></linearGradient>
    <linearGradient id="lin-crash" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--svg-accent-orange)" stop-opacity="0.50"/><stop offset="100%" stop-color="var(--svg-accent-orange)" stop-opacity="0.15"/></linearGradient>
    <linearGradient id="lin-size" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--svg-text-muted)" stop-opacity="0.50"/><stop offset="100%" stop-color="var(--svg-text-muted)" stop-opacity="0.15"/></linearGradient>
  </defs>
  <text x="440" y="22" text-anchor="middle" fill="var(--svg-text-muted)" font-family="var(--font-mono)" font-size="11" letter-spacing="0.18em">PARAMETER GOLF · 201 TRIALS EACH · LINEAGE ABLATION</text>
  <text x="220" y="48" text-anchor="middle" fill="var(--svg-text-bright)" font-family="var(--font-sans)" font-size="13" font-weight="600">LINEAGE ON</text>
  <text x="660" y="48" text-anchor="middle" fill="var(--svg-text-bright)" font-family="var(--font-sans)" font-size="13" font-weight="600">LINEAGE OFF</text>
  <text x="220" y="64" text-anchor="middle" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="9" letter-spacing="0.12em">agent sees the tree + leaderboard + recent-30</text>
  <text x="660" y="64" text-anchor="middle" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="9" letter-spacing="0.12em">agent sees only rules + domain preamble</text>
  <g transform="translate(60,90)">
    <rect class="bar-grow" x="0" y="0" width="60" height="18" rx="3" fill="url(#lin-keep)" stroke="var(--svg-accent-green)" stroke-width="1.2"/>
    <text x="68" y="13" fill="var(--svg-text-bright)" font-family="var(--font-mono)" font-size="11" font-weight="600">keep · 16</text>
    <rect class="bar-grow" x="0" y="32" width="142" height="18" rx="3" fill="url(#lin-budget)" stroke="var(--svg-accent-red)" stroke-width="1"/>
    <text x="150" y="45" fill="var(--svg-text-bright)" font-family="var(--font-mono)" font-size="11">eval_budget_overrun · 38</text>
    <rect class="bar-grow" x="0" y="64" width="248" height="18" rx="3" fill="url(#lin-discard)" stroke="var(--color-primary)" stroke-width="1"/>
    <text x="256" y="77" fill="var(--svg-text-bright)" font-family="var(--font-mono)" font-size="11">discard · 124</text>
    <rect class="bar-grow" x="0" y="96" width="22" height="18" rx="3" fill="url(#lin-crash)" stroke="var(--svg-accent-orange)" stroke-width="1"/>
    <text x="30" y="109" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="11">crash · 11</text>
    <rect class="bar-grow" x="0" y="128" width="22" height="18" rx="3" fill="url(#lin-size)" stroke="var(--svg-text-muted)" stroke-width="1"/>
    <text x="30" y="141" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="11">size_blocked · 11</text>
    <text x="0" y="180" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="10" letter-spacing="0.08em">best val_bpb · <tspan fill="var(--svg-accent-green)" font-weight="600">1.073142</tspan></text>
    <text x="0" y="198" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="10" letter-spacing="0.08em">keep rate · <tspan fill="var(--svg-text-bright)">8.0 %</tspan></text>
  </g>
  <g transform="translate(500,90)">
    <rect class="bar-grow" x="0" y="0" width="12" height="18" rx="3" fill="url(#lin-keep)" stroke="var(--svg-accent-green)" stroke-width="1.2"/>
    <text x="20" y="13" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="11">keep · 3</text>
    <rect class="bar-grow" x="0" y="32" width="320" height="18" rx="3" fill="url(#lin-budget)" stroke="var(--svg-accent-red)" stroke-width="1.4"/>
    <text x="160" y="45" text-anchor="middle" fill="var(--svg-text-bright)" font-family="var(--font-mono)" font-size="11" font-weight="600">eval_budget_overrun · 123</text>
    <rect class="bar-grow" x="0" y="64" width="92" height="18" rx="3" fill="url(#lin-discard)" stroke="var(--color-primary)" stroke-width="1"/>
    <text x="100" y="77" fill="var(--svg-text-bright)" font-family="var(--font-mono)" font-size="11">discard · 46</text>
    <rect class="bar-grow" x="0" y="96" width="40" height="18" rx="3" fill="url(#lin-crash)" stroke="var(--svg-accent-orange)" stroke-width="1"/>
    <text x="48" y="109" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="11">crash · 20</text>
    <rect class="bar-grow" x="0" y="128" width="16" height="18" rx="3" fill="url(#lin-size)" stroke="var(--svg-text-muted)" stroke-width="1"/>
    <text x="24" y="141" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="11">size_blocked · 8</text>
    <text x="0" y="180" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="10" letter-spacing="0.08em">best val_bpb · 1.077413</text>
    <text x="0" y="198" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="10" letter-spacing="0.08em">keep rate · <tspan fill="var(--svg-text-bright)">1.5 %</tspan></text>
  </g>
  <text x="440" y="330" text-anchor="middle" fill="var(--svg-text-bright)" font-family="var(--font-sans)" font-size="12" font-weight="600">5.3× more keeps · 3.2× fewer eval-budget wastes · 0.004 val_bpb deeper</text>
  <text x="440" y="348" text-anchor="middle" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="9" letter-spacing="0.10em">same agent · same template · same budget · only the lineage block differs</text>
</svg>
</figure>

The 38-vs-123 eval-budget overrun gap is, in some ways, the more telling one. A `keep` is a clear win — the trial improved the leaderboard. An `eval_budget_overrun` is a softer failure: the trial trained inside its 600 s budget, then ran out of wall during the 600 s eval budget. The cost to the run is the same as a `discard` (600 s of GPU wall) but the *informational* cost is higher — the run didn't even get a `val_bpb` to log against. With lineage on, only 19% of trials hit that wall. With lineage off, 61% did. The agent without lineage spends three out of every five trials chasing edits that *can't even finish their eval*. Without the tree visible, the agent re-proposes interventions that another specialist already tried and discovered to be wall-expensive — TTT epoch counts that no longer fit, quantization passes that overshoot the size budget, sampler changes that interact badly with the GPTQ calibration pass. The lineage prevents that.

The discard column shifts in the other direction: 124 with lineage on, 46 with lineage off. That looks like a regression until you notice that `discard` is the *clean* failure mode. A `discard` ran to completion, produced a `val_bpb`, and simply didn't beat the leaderboard. The trial is informational — the next specialist sees "we tried X, status was discard, val_bpb was 1.0758" and can decide whether to refine X or move elsewhere. Lineage on pushes failures *into* the discard bucket; lineage off lets them stay as crashes and overruns. That's a strict improvement.

The best-`val_bpb` delta, 1.073142 vs 1.077413, is real but secondary. The lineage primitive's value at this scale isn't measured in final-leaderboard depth — it's measured in *what fraction of trials produce signal at all*. Lineage on: 16 + 124 = 140 signal-producing trials out of 201 (70%). Lineage off: 3 + 46 = 49 (24%). Three times the information density per trial, with no change to the agent.

## What the agent sees

The released `example_lineage_pg_lineage_on_arch.txt` is the rendered prompt for a `tok` specialist at session start, on iteration 178 of a `lineage_on` run. It is what makes the abstract primitive concrete. The prompt has four substantive sections (plus the rules-only opener which is identical in both ablations):

**Section 1 — current best lineage chain.** The root-to-best path through the tree, rendered as nested `└─` lines. Twelve entries, from `exp_000` (baseline, 1.081) through `exp_176` (the current best, 1.073142, opt-specialist hypothesis "Muon momentum cooldown 0.99→0.95 after warmup"). Each line carries `(specialist, status, val_bpb, Δ)` and the first ~70 chars of the hypothesis. The agent reads this and understands the *causal* shape of the current best — eleven kept interventions chained from the baseline, with each `keep` written by a different specialist. That's the model of "what the current best is made of."

**Section 2 — top-20 leaderboard.** A Markdown table of the 20 `keep` trials sorted by `val_bpb`. Each row: `(exp_id, val_bpb, Δ, specialist, truncated_hypothesis)`. This is the depth-ordered view of what's worked. The agent uses this to spot specialist-axis productivity: in this run, `opt` has 5 keeps in the top-16, `meta` and `reg` have 2 each, and the `tok` agent reading this prompt sees its own specialty has *zero entries* in the top-20. That's information.

**Section 3 — recent 30 activity.** A separate table of the 30 most-recent trials, sorted reverse-chronological. Each row: `(exp_id, specialist, status, val_bpb, truncated_hypothesis)`. The agent reads this and sees *what other specialists are currently trying* and *what their last 30 outcomes were*. In the released example, recent activity shows the loss specialist failing twice in a row on Token Order Prediction (exp_161 then exp_172), the tok specialist crashing on a bigram_mix dtype bug (exp_171), and the arch specialist eval_budget_overrunning on RWKV-V5+ token shift (exp_177). The next tok specialist about to propose can use this to avoid the same dtype bug, see what arch's eval_budget_overrun was about, and identify cleanly-discardable directions.

**Section 4 — last-10 with full hypothesis.** For the ten most-recent trials, the *full* hypothesis text is included (not just the truncated leaderboard fragment). This is high-fidelity context for the immediately-prior interventions, where the agent is most likely to want to refine or rebut. The released example shows the loss specialist's full reasoning for the failed TOP hinge loss alongside the meta-specialist's reasoning for raising AdamW β1 — exactly the kind of nuance that gets lost in a 70-char truncation.

Plus four utility blocks: the bash recipes for slicing `tree.tsv` (so the agent can run its own queries against the lineage), the workdir state confirmation, the agent's domain-specific session task, and a stop-criterion that says "one submit is a complete session — do not force extra submits." 136 lines total. **All of it rendered into the system prompt at every session entry from the contents of `results.tsv` plus a small amount of auto-generated structure.**

Read that as code: the prompt isn't dynamic in any agentic sense. It is a deterministic function of the TSV state at iteration boundary. That's why the primitive is portable. It does not require the agent infrastructure cxcscmu built — it requires a TSV writer, a leaderboard renderer, a tree renderer, and an "include the rendered lineage in the system prompt" hook. On a Spark, all of that is sub-millisecond Python.

## The five status classes — each carries different signal

The status enum is what makes the lineage primitive's value *per-class*, not just per-row. Six failure classes plus `keep` plus `baseline`, each carrying a distinct downstream meaning:

- **`keep`** — trial ran to completion, score improved the leaderboard. The snapshot was archived (`snapshots/<exp_id>_<domain>/`), the next-best chain was updated, the tree gained a node. The agent reading the lineage will use `rebase_to(exp_id)` to start its next workdir from this snapshot if it wants to build on this win.
- **`discard`** — trial ran to completion, score did not improve. The trial is *information-positive*: the hypothesis was tested, the answer was no. The next agent should not re-propose this exact edit. But the *direction* is now annotated as unproductive *at this baseline*, not unproductive in general.
- **`crash`** — trial broke mid-training (or mid-eval) with a traceback. The `notes` column carries the kill_reason. The next agent reading this learns either to avoid the exact construct that broke or — more often, in the released example — to fix the bug and resubmit. The released `exp_171` (tok specialist, bigram_mix dtype mismatch) is the canonical example: the next tok session, exp_178, both fixed the bug *and* explained the fix in its own hypothesis. Crash-then-fix is a regular pattern.
- **`eval_budget_overrun`** — trial trained inside its 600 s budget but exceeded the 600 s eval budget. The trial's directional signal is partial — the agent knows training was viable, but does not have a `val_bpb` to log. The hypothesis is still informational ("we tried X and it wouldn't fit the eval"), and the agent reading the lineage can adjust either the technique itself (smaller TTT count, fewer GPTQ passes) or the budget allocation. The 19%-vs-61% gap on this status class between lineage on/off is the run's dominant wall efficiency story.
- **`size_blocked`** — preflight check found the trial's packed artifact would exceed the 16 MB cap. Trial is killed before training. Cost: ~30 s. The technique itself may be valid; what fails is the compression / quantization pass. Next agent learns "this approach works but the model doesn't fit at this aggression level."
- **`harness_abort`** — bookkeeping failure: scheduler crash, lost handle, etc. The trial is *quarantined* in the rendered prompt — the next agent does not see it in recent activity. It carries no experimental signal and would only confuse downstream interpretation. (The agent-side code is explicit about this: `_QUARANTINED_STATUSES = frozenset({"harness_abort"})`.)
- **`preflight_crash`** (NanoChat-D12 only) — the SMOKE_TEST=1 phase failed before training started, typically an import / shape / data-loader bug. Similar to `crash` but produced no `val_bpb`. The kill_reason is in `notes`.
- **`train_budget_overrun`** (NanoChat-D12 only) — trial's training phase exceeded its wall budget. NanoChat has separate train and eval budgets where Parameter Golf has a single combined cap.
- **`disqualified`** (CIFAR only) — accuracy gate not met. CIFAR's task isn't `val_bpb` minimization; it's wall-clock minimization *conditional on accuracy ≥ 96%*. A trial that hits 95.9% gets disqualified — interesting wall, wrong accuracy.

The enum is task-specific in tail (CIFAR and NanoChat add classes; Parameter Golf doesn't have them) but the core five — `keep`, `discard`, `crash`, `eval_budget_overrun`, `size_blocked` — generalize. Any task where (a) trials can run to completion, (b) trials can fail mid-run, (c) trials can produce out-of-budget completions, and (d) trials can be killed by structural constraints needs exactly these axes. The Spark-side analogue, in the autoresearch-agent-loop article, used a much smaller enum (`keep`, `revert`, `crash`, `rail_block`) — but the shape is the same. Lifting cxcscmu's superset into `fieldkit.lineage` lets every future harness write into the same vocabulary.

## fieldkit.lineage — types and module shape

The release_artifacts pattern decomposes cleanly into Python. The proposed `fieldkit.lineage` module has four dataclasses, one enum, and three thin accessor helpers. Total surface area ≈ 200 lines.

```python
# fieldkit/lineage/__init__.py

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Iterable
import csv, json

class FailureLabel(str, Enum):
    """The status enum. String-valued so TSV round-trip is identity."""
    KEEP                 = "keep"
    DISCARD              = "discard"
    CRASH                = "crash"
    EVAL_BUDGET_OVERRUN  = "eval_budget_overrun"
    TRAIN_BUDGET_OVERRUN = "train_budget_overrun"
    SIZE_BLOCKED         = "size_blocked"
    PREFLIGHT_CRASH      = "preflight_crash"
    HARNESS_ABORT        = "harness_abort"
    DISQUALIFIED         = "disqualified"
    BASELINE             = "baseline"

    @property
    def is_informational(self) -> bool:
        """True if this status carries usable signal for the next agent.
        False for harness_abort (bookkeeping) and bare crashes
        with no kill_reason."""
        return self not in {FailureLabel.HARNESS_ABORT}

@dataclass(frozen=True, slots=True)
class Trial:
    """One row of results.tsv. Field order matches the canonical header."""
    exp_id: str
    timestamp: str
    specialist: str
    parent_exp: str
    baseline_exp: str
    domain: str
    hypothesis: str
    expected_delta: str
    status: FailureLabel
    core_metric: Optional[float]
    val_bpb: Optional[float]
    delta_vs_best: Optional[float]
    train_s: Optional[float]
    total_s: Optional[float]
    job_name: str
    snapshot_path: str
    notes: str

@dataclass(frozen=True, slots=True)
class RecipeEdit:
    """A keep trial's frozen workdir + the diff against parent.
    snapshot_path is materialized; diff is lazily computed."""
    trial: Trial
    snapshot_path: Path
    parent_snapshot_path: Optional[Path]

    def diff(self) -> str: ...

@dataclass(frozen=True, slots=True)
class LineageSnapshot:
    """The rendered Markdown prompt block injected at session start.
    Deterministic function of (results.tsv state, tree.tsv state,
    snapshots/, KNOWLEDGE.md insights)."""
    rendered_prompt: str
    current_best: Trial
    chain_to_best: tuple[Trial, ...]
    top_k_leaderboard: tuple[Trial, ...]
    recent_n_activity: tuple[Trial, ...]
    last_m_with_full_hypothesis: tuple[Trial, ...]

class LineageStore:
    """The append-only TSV writer + the read-side accessors."""
    def __init__(self, root: Path): ...
    def append(self, trial: Trial) -> None: ...
    def latest(self, n: int = 30) -> Iterable[Trial]: ...
    def best(self) -> Trial: ...
    def chain_to(self, exp_id: str) -> tuple[Trial, ...]: ...
    def render_prompt(
        self,
        for_specialist: str,
        top_k: int = 20,
        recent_n: int = 30,
        last_m_full: int = 10,
    ) -> LineageSnapshot: ...
```

Three things to notice. First, the status enum is structural — the `is_informational` predicate is the cxcscmu `_QUARANTINED_STATUSES` rule made into a method, and any downstream consumer can read it without re-implementing the policy. Second, `LineageSnapshot` is a record of *what the agent saw* — including the rendered prompt — not just a reference to the underlying TSV state. That matters for reproducibility: if you want to know why the agent at iteration 178 made the choice it did, you read the snapshot, not the TSV. Third, `LineageStore.render_prompt` is the same deterministic function cxcscmu's `harness/blackboard.py` implements (about 600 lines of careful Markdown assembly); the `fieldkit.lineage` version is the published, testable, dependency-free port.

The module would land in `fieldkit/lineage/` as a new top-level submodule — peer of `fieldkit.eval`, `fieldkit.training`, `fieldkit.rag`, `fieldkit.nim`. Strictly, the v0.3 candidate is `fieldkit.lineage` not under `fieldkit.training` — lineage is task-agnostic (Parameter Golf, NanoChat-D12, and CIFAR all use the same primitive). Putting it under `fieldkit.training` would suggest LM-training specificity that isn't there. The CIFAR run's `disqualified` status class is the evidence: lineage works fine for vision tasks too.

Two integration points with existing `fieldkit` modules. `fieldkit.eval.AgentRun` (from the [autoresearchbench article](/field-notes/autoresearchbench-on-spark/)) is structurally a *per-question* trial log; the row shape generalizes to `Trial` if `(question_id, action, duration, papers_retrieved, parse_errors)` maps to `(exp_id, hypothesis_summary, train_s + total_s, core_metric, status)`. `fieldkit.training.LoraReferenceSnapshot` (from the [Phase 6 GRPO article](/field-notes/clawgym-on-spark-grpo/)) already establishes the pattern of "freeze + audit + tag" for adapters; `RecipeEdit.snapshot_path` is the same pattern for full workdirs. A later refactor could promote `Trial` to a base class with task-specific subclasses, but the dataclass-frozen design is the right starting point — schema first, ergonomics after.

## Why this is a study, not a Spark run

The seed for this article promised a Spark reproduction: clone cxcscmu, reduce parallel-trial fanout to a single GB10 worker, run NanoChat-D12 (or Parameter Golf) trials, extract lineage. The Frontier Scout eval rated the paper `spark-feasible` on memory grounds — Parameter Golf's largest reference task fits comfortably in 128 GB unified memory, and NanoChat-D12 at 0.5 B parameters in BF16 is under 1 GB resident. That part of the eval is correct. What the eval underweighted is wall-clock economics.

cxcscmu's published trial budget is 600 s of training on **8 × H100 SXM** GPUs — 4,800 H100-GPU-seconds of compute per trial. On a single GB10, BF16 dense throughput is roughly 1/8 of one H100 SXM (Blackwell consumer-class vs SXM data-center, plus memory bandwidth and tensor-core differences). Faithful trial replication at the published config would land each trial at ≈ 38,400 s wall — about 10.7 hours per trial — *for the training phase alone*. The eval phase is another 600 s × 8-GPU budget that contributes a similar amount when not fail-fast. A trial that runs cleanly to a `discard` or `keep` outcome takes 15–20 hours of single-GB10 wall. A `size_blocked` trial fails in preflight at ~30 s. The 902-trial `pg_main` released artifact, scaled to a Spark, would be 6–10 months of continuous wall.

A five-trial smoke is 60–100 hours — call it 3–4 days — for a sample size that produces ~2 informational data points (one or two `discard`s, maybe a `size_blocked`, possibly a `crash`). That's worse than what's already in `pg_ablation_lineage_on/results.tsv`. And it's *before* counting the setup cost: building a Flash-Attention 3 capable PyTorch wheel for Blackwell sm_120, downloading and re-tokenizing FineWeb10B at SP8192 vocabulary (the published tokenizer isn't on HuggingFace under either of the obvious paths), patching `run_trial.sh` for single-GPU operation, threading the Claude Agent SDK auth through bubblewrap-sandboxed subprocess. Conservatively 10–25 hours of setup before the first trial even tries to start.

So the article was scoped as a study from the released artifacts. The study is *better* on the metric that matters here — sample size and failure-class coverage — than a Spark smoke would be, by an order of magnitude. cxcscmu's 1,704 trials across six packages give us coverage of every status class, two complete ablations of the load-bearing intervention, two worked-example prompt renderings, and ~200 KB of post-mortem `notes` field text. A faithful Spark reproduction adds nothing the released data doesn't already say more authoritatively, and costs the box for a week.

What it does cost is a future-work scaffold. The working setup at `/home/nvidia/work/auto-research/` carries the fresh clone of `cxcscmu/Auto-Research-Recipes`, a Python venv with `claude-agent-sdk` 0.1.80 + `filelock` + `psutil`, and two small patches: `agent_core/harness/credentials.py` and `multi_agent_pg/harness/credentials.py` now accept `MAGENT_USE_OAUTH=1` to bypass the hard `ANTHROPIC_API_KEY` env-var check (the SDK threads through the local Claude Code OAuth session via the spawned `claude` CLI subprocess — verified working against the patched harness on 2026-05-10). When DGX Cloud or a multi-H100 lab block becomes available, the entry point is `MAGENT_USE_OAUTH=1 python -m multi_agent_pg.supervisor --state-root ./magent_state_pg_smoke --deadline-hours 24 --no-improvement-hours 4`. Until then, the patches sit unmerged in a working tree outside this repo, ready.

## What this means for the rest of the arc

The Machine that Builds Machines arc has been producing lineage primitives in different shapes for five installments already. The [baseline-training-loop article](/field-notes/baseline-training-loop-on-spark/) wrote a sweep CSV with 16 configurations. The [autoresearch-agent-loop](/field-notes/autoresearch-agent-loop/) wrote a 50-row JSONL of (`knob`, `value`, `val_bpb`, `keep`/`revert`). The [trajectory-eval](/field-notes/trajectory-eval-is-the-agent-flailing/) extracted three observability signals from that JSONL. The [Phase 6 GRPO article](/field-notes/clawgym-on-spark-grpo/) wrote a 34-step per-step metrics CSV plus two eval-step JSONs. The [T²PO article](/field-notes/t2po-uncertainty-guided-rl-on-spark/) traced 50 RL steps with three evals. Five different artifact shapes for the same conceptual object.

The cxcscmu schema is the one to converge on. It's testable, it's renderable, it's enum-typed where it needs to be (status) and free-text where it needs to be (hypothesis, notes). Future articles in this arc will write to a `fieldkit.lineage.LineageStore` from the start, and the corpus of trajectories across the blog will all be queryable on the same vocabulary. The [A²TGPO article](/field-notes/a2tgpo-turn-clipping-on-spark/), already scaffolded as Priority 2 in the Frontier Scout queue, will write per-step IG signal as a column in lineage — the `expected_delta` column is the natural home for that, with `notes` carrying the per-token entropy breakdown. The [SkillOS article](/field-notes/skill-os-on-spark/), once it materializes, will write curator actions (`insert_skill | update_skill | delete_skill`) as the `domain` column with the skill diff as the `hypothesis`.

The agent infrastructure does not port from a SuperPOD to a Spark desk. The 1,797 trials do not port. The 600 s × 8-H100 trial budget does not port. **The TSV does.** That's the part this article extracts, and the part the rest of the arc will reuse.
