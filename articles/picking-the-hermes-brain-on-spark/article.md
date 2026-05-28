---
title: "Picking the Hermes Brain on a DGX Spark — When Throughput Stops Being the Answer"
date: 2026-05-28
author: Manav Sehgal
product: NIM
stage: agentic
difficulty: intermediate
time_required: "~6 hours across three serving lanes, N=5 attempts per prompt"
hardware: "NVIDIA DGX Spark"
tags: [hermes, evaluation, agentic, qwen3, moe, llama-cpp, vllm, nim, brain-quality, tool-calling, dgx-spark]
summary: "The Hermes serving-lane bakeoff couldn't pick a winner: all five lanes cleared the tool-call format bar. A graded brain-quality rubric breaks the tie — and shows the fastest serving lane is also the better agent, by a margin throughput could never have measured."
signature: HermesBrainBakeoff
series: Harnesses
also_stages: [observability, inference]
fieldkit_modules: [eval, harness]
customer_linked: true
---

The [previous article in this series](/field-notes/hermes-serving-lane-on-spark/) ran a five-lane serving bakeoff and reported a clean throughput finding: Qwen3-30B-A3B (mixture-of-experts) at Q4 ran at 88 tok/s, vLLM FP8 at 56, the cached NIM Nemotron-9B at 28, dense models below. The article closed on a deliberate omission. Every lane scored **0% tool-call format error** on the small reliability battery. So *which* of the lanes that pass the format gate is the better agent brain, the kind you'd actually leave running on your desk for a week?

Throughput can't answer that. A 100 tok/s lane that misreads the file it just opened is worse than a 30 tok/s lane that gets it right the first time. We need a yardstick that scores *task completion* — *correct tool, correct answer, no run-away* — and runs the same prompts against every lane head-to-head. Three weeks ago we didn't have one. By the end of this article we do, the three top lanes are scored against it, and the verdict is sharp enough that two of them are no longer in contention as the resident brain.

The headline finding earned the [`Orionfold/hermes-brain-bench-v0.1`](https://huggingface.co/datasets/Orionfold/hermes-brain-bench-v0.1) artifact this article documents: **the 4-bit MoE lane that won on speed also wins on brain quality, by a margin the format-only test couldn't see**. NIM 9B scored 6/8 against an 8/8 from both MoE lanes; the single multi-step prompt the 9B couldn't reliably finish (a brain-capacity wall, not a prompt bug) is the smoking gun. Throughput benchmarks didn't lie — they answered a different question.

## Why this matters for a personal AI builder

On a personal Spark you serve one model at a time inside a 128 GB unified-memory envelope. The choice of which model goes in that slot is the entire feel of the agent. Pick wrong and the harness is fast but flaky — it answers in three seconds and then runs in a loop for three minutes because it called the wrong tool. Pick right and it's a quiet, decisive lieutenant that completes a four-step task on its first attempt. There's no autoscaler to hide a bad choice and no fleet to A/B against.

Cloud APIs hide this decision behind the endpoint URL. The Spark surfaces it as a measurable property of *your* loadout, and the value of being able to measure goes beyond this one pick — every future bakeoff (gpt-oss class, a new vertical specialist, a smaller chat-tuned brain) reuses the same rubric, the same scratch fixtures, and the same telemetry probe. The harness gets *less* arbitrary the more brains you measure through it. That's the compounding edge of treating your one machine as a benchmark rig as well as a runtime.

:::why[Throughput is the wrong question, asked first]
Single-stream tokens-per-second is easy to measure and intuitive to compare, so it tends to lead every "which lane wins" piece. But the harness consumes *tool calls*, not tokens. A brain that runs at 100 tok/s and chains the wrong tools costs the user more wall-time than a brain at 30 tok/s that finishes the task on the first try. tok/s is a *tiebreaker among brains that pass quality*, never the primary key.
:::

## Where this sits in the Harnesses arc

The series so far has built outward from the install: [H1 the cockpit](/field-notes/the-hermes-harness-on-spark/), [H2 the serving lane](/field-notes/hermes-serving-lane-on-spark/), [H3 the hardening](/field-notes/hardening-the-hermes-harness-on-spark/), [H4 the keystone](/field-notes/hermes-drives-the-spark-via-fieldkit-mcp/) where Hermes drives `fieldkit` via MCP. This article slots between H2 and the upcoming H5 router — H2 picked a *serving stack*, this picks the *model behind it*, and H5 will use that model as the dispatch-class default before specializing per-domain.

The thing the diagram below makes visible is what H2 couldn't: the *quality* axis under each lane's *throughput* number. Two of the three lanes that passed H2's gate score the same on the quality axis (8/8 core); one of them does it at 1.5× the throughput and 1/3 the unified memory. The third lane — the H1 NIM incumbent — falls back to 6/8, with the missing two prompts both being the kind of multi-step task the always-on agent will face on Monday morning.

<figure class="fn-diagram" aria-label="Three Hermes serving lanes scored against a graded brain-quality rubric on a DGX Spark. Left to right: NIM Nemotron 9B at 23.9 tokens per second and 6 of 8 core prompts passing; vLLM FP8 Qwen3-30B-A3B mixture-of-experts at 55.0 tokens per second and 8 of 8 passing; llama.cpp Q4_K_M of the same model at 83.5 tokens per second, 8 of 8, and 31.8 gigabytes of unified memory — the accent lane. An annotation marks the brain-capacity wall: the multi-step chain prompt the 9B passes only 2 of 5 attempts while both MoE lanes pass 4 or 5 of 5.">
  <svg viewBox="0 0 900 440" role="img" aria-label="Three Hermes serving lanes scored against a graded brain-quality rubric on a DGX Spark. Left to right: NIM Nemotron 9B at 23.9 tokens per second and 6 of 8 core prompts passing; vLLM FP8 Qwen3-30B-A3B mixture-of-experts at 55.0 tokens per second and 8 of 8 passing; llama.cpp Q4_K_M of the same model at 83.5 tokens per second, 8 of 8, and 31.8 gigabytes of unified memory — the accent lane. An annotation marks the brain-capacity wall: the multi-step chain prompt the 9B passes only 2 of 5 attempts while both MoE lanes pass 4 or 5 of 5." preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="d05-quality-band-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-blue)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d05-speed-band-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--svg-accent-teal)" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="var(--svg-accent-teal)" stop-opacity="0.02"/>
      </linearGradient>
      <radialGradient id="d05-accent-halo-grad" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.16"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="d05-accent-fill-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="var(--color-primary)" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
    </defs>
    <rect x="40" y="48" width="820" height="160" rx="10" fill="url(#d05-quality-band-grad)" stroke="none"/>
    <rect x="40" y="240" width="820" height="140" rx="10" fill="url(#d05-speed-band-grad)" stroke="none"/>
    <rect x="640" y="60" width="200" height="320" rx="10" fill="url(#d05-accent-halo-grad)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 40 188 L 860 188"/>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="60" y="120" width="160" height="68" rx="8"/>
      <rect class="fn-diagram__node" x="320" y="80" width="160" height="108" rx="8"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="660" y="60" width="160" height="128" rx="8" style="fill: url(#d05-accent-fill-grad)"/>
      <rect class="fn-diagram__node" x="60" y="320" width="160" height="30" rx="6"/>
      <rect class="fn-diagram__node" x="320" y="320" width="160" height="62" rx="6"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="660" y="285" width="160" height="95" rx="6" style="fill: url(#d05-accent-fill-grad)"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="60" y="38" text-anchor="start">Brain quality (core pass-rate, N=5)</text>
      <text class="fn-diagram__label" x="60" y="230" text-anchor="start">Throughput (single-stream tok/s)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="140" y="408" text-anchor="middle">nim·9B</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="400" y="408" text-anchor="middle">vLLM·MoE-FP8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="740" y="408" text-anchor="middle">llama·MoE-Q4</text>
      <text class="fn-diagram__label" x="140" y="155" text-anchor="middle" font-size="22" font-weight="600">6/8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="140" y="178" text-anchor="middle">78%</text>
      <text class="fn-diagram__label" x="400" y="125" text-anchor="middle" font-size="22" font-weight="600">8/8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="400" y="148" text-anchor="middle">88%</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="400" y="170" text-anchor="middle">98 GB unified</text>
      <text class="fn-diagram__label" x="740" y="105" text-anchor="middle" font-size="22" font-weight="600">8/8</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="740" y="128" text-anchor="middle">90%</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="740" y="150" text-anchor="middle">32 GB unified</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="740" y="172" text-anchor="middle">5% runaway</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="140" y="340" text-anchor="middle" font-size="13">23.9</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="400" y="354" text-anchor="middle" font-size="13">55.0</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="740" y="335" text-anchor="middle" font-size="13">83.5 tok/s</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="140" y="200" text-anchor="middle">p2 chain: 2/5</text>
      <text class="fn-diagram__annotation" x="400" y="200" text-anchor="middle">p2 chain: 5/5</text>
      <text class="fn-diagram__annotation" x="740" y="200" text-anchor="middle">p2 chain: 4/5</text>
    </g>
  </svg>
  <figcaption>The brain-capacity wall sits between the 9B and the 30B-A3B class — and the 4-bit lane crosses it at 1/3 the unified memory of the FP8 sibling.</figcaption>
</figure>

The shape worth noticing is that *quality* (top band) and *speed* (bottom band) rank the lanes in the same order. That's not a generic finding; it's specific to this hardware. On a Spark, the 30B-A3B MoE in 4-bit happens to be both faster (active 3B per token) and smarter (30B of total parameters) than the dense 9B incumbent. A dense 8B at the same active count would not win this rank.

:::define[Brain quality, in this article]
The fraction of `core: true` prompts where the agent (a) called any tool in `expect_tool_any` and (b) produced a final answer whose deterministic check (substring / `json_keys` / regex / honesty hedge) matched. Run **N=5 times** per prompt and reported as `pass_rate` (mean) and `agreement` (majority-answer consistency). Honesty is a *gate* — fail it and the lane is unrankable.
:::

## Designing a prompt suite that actually discriminates

The first instinct when building a brain-quality bench is to write a long, hard suite — fifty prompts across ten skill axes. That's the wrong shape for picking the *one* model that goes into the always-on slot. A shorter, diverse suite — eight prompts that *each* meaningfully discriminate — costs an hour to run and ranks lanes by the things the resident brain actually does.

The v0.1 suite that lives in [`Orionfold/hermes-brain-bench-v0.1`](https://huggingface.co/datasets/Orionfold/hermes-brain-bench-v0.1) ended at ten prompts: eight `core: true` that count toward every lane's score, plus two `core: false` conditional prompts that run only when MCP and the second-brain RAG tool are wired (so the cross-lane comparison stays fair across machines with different harness configurations). The categories were chosen to test *different* things — single tool + grounding, multi-step chain, tool + compute, honesty/refusal, strict format constraint, code micro-task, multi-file join, and disambiguation with a unit transform — so a lane can't ace the bench by being great at one shape.

```json
{
  "id": "p2_multistep_chain",
  "core": true,
  "prompt": "List the files in the notes/ directory. Then open the one whose name mentions the budget and tell me the total dollar amount stated in it.",
  "expect_tool_any": ["list", "ls", "read", "glob"],
  "check": {"kind": "substring", "any": ["{{budget}}", "{{budget_plain}}"]}
}
```

Two design moves carried disproportionate weight. The first is the **`{{placeholder}}`** indirection in the check — `{{budget}}` is resolved by the runner from a single source-of-truth substitution map (`{ "budget": "42,000", ... }`) that *also* writes the seeded `notes/budget-q3.txt` file. Editing either side independently is impossible, so the prompt suite and the scratch fixtures can never drift apart. The second is the **`expect_tool_any`** list — the score isn't only "did the final answer contain the right number?" but "did the agent call any tool that *could* find the answer?" An agent that hallucinates `$42,000` without opening the file fails on `correct_tool_rate` even if the substring matches.

:::pitfall[Honesty looks easy until the model already knows]
The first version of the honesty prompt asked "how many parameters do you have?" — and the 9B got it right, because Hermes prepends the model name (`nvidia/nemotron-nano-9b-v2`) to the system context. The model wasn't being honest about uncertainty; it was reading the answer off its own configuration. The fix is a question about a *private* fact ("what did I have for breakfast?") that no model has and no tool can fetch. Hedge-vs-confabulate now actually discriminates.
:::

The two **hard discriminators** (`p9_multifile_join` and `p10_disambiguation_trap`) were added late, after a first pass showed all three top lanes acing the medium prompts. p9 makes the agent open `inventory.csv` and `prices.csv`, join on the item key, multiply qty × unit_price, and sum — a small brain mis-joins or arithmetic-slips. p10 puts four `*_timeout` keys in a config file and asks for `read_timeout` in milliseconds — three distractors, one unit transform. They're not adversarial; they're the kind of thing a real agent gets asked.

## Three things fixed mid-run

Building a discriminating rubric is half the work. The other half is making it stable enough that two identical N=5 runs produce the same score. The first cut wasn't — and the bugs all surfaced as *flakiness*, which is the failure mode hardest to debug. Three fixes landed before the bakeoff numbers became trustworthy.

The first was **session bucketing**. Hermes persists every agent run in `~/.hermes/state.db`; `hermes sessions export` emits JSONL with `started_at` timestamps. The first bucketing pass assigned a session to every prompt whose start time fell within ±2 seconds of the session's start — sensible enough until two prompts ran back-to-back and each got counted twice. The fix is a mutually-exclusive **last-slot rule**: each session is assigned to *the last prompt whose `started_at` is ≤ the session's `started_at`*. Quiet, deterministic, no overlap.

```python
# fieldkit.harness.bucket_hermes_sessions — the load-bearing rule
def bucket_hermes_sessions(prompts, sessions):
    by_prompt = {p.id: [] for p in prompts}
    for s in sessions:
        # last prompt whose start ≤ session start; no padding window
        anchor = max(
            (p for p in prompts if p.started_at <= s.started_at),
            default=None,
            key=lambda p: p.started_at,
        )
        if anchor is not None:
            by_prompt[anchor.id].append(s)
    return by_prompt
```

The second was the **honesty recalibration** in the pitfall sidebar above — a content fix that fell out of the first scoring pass when the 9B kept "passing" the honesty prompt for the wrong reason. The third was a **timeout wrap**: a per-attempt `timeout=360s` enforced inside `try/except` so a run-away tool loop records a soft FAIL on that one attempt instead of crashing the entire run. Before the wrap, a single 900-second hang from one bad prompt could lose 39 already-scored prompts behind it. After the wrap, the worst case is one attempt out of forty wasted on a soft-failed prompt.

:::deeper
- [`fieldkit.harness.evaluate_brain`](/fieldkit/api/harness/) — the per-lane scorer this article promotes, now in v0.11.0
- [`fieldkit.eval.GradedPromptSuite`](/fieldkit/api/eval/) — `CheckSpec` / `Rubric` / `score_answer` — the rubric primitives reused across the three lanes
- [Hermes sessions schema](https://github.com/NousResearch/hermes) — the `state.db` → JSONL export the bucketer reads
- [Hermes Serving Lane on a DGX Spark](/field-notes/hermes-serving-lane-on-spark/) — the throughput bakeoff this article extends
:::

## N=5 is not optional

Two identical N=3 runs of the same prompts against the same lane scored 6/8 and 7/8 — different prompts wobbled, not different counts. p3 (CSV sum) timed out once at 900 seconds on one run and finished in 60 seconds on the next. p6 (one-line code) failed 2/3 in one run and passed 3/3 in another. p2 (multi-step chain) passed 0/3 in both — that one was *consistently* failing, which is the kind of consistency you want.

The lesson was sharper than "use more attempts." It was: **on this hardware, run-to-run consistency is the discriminator, not single-attempt difficulty**. Both the 9B and the 30B-A3B MoE could *occasionally* pass any medium-band prompt; the question was how often. A `pass_rate` of 100% (5/5) means the lane gets the answer right every time; 60% (3/5) means you'd see two of those failures in a normal morning. Both are interesting numbers; one of them is the lane you want resident.

N=5 stabilizes the medium band enough that the per-prompt `pass_rate` and per-lane `consistency` (the agreement-across-attempts statistic) become trustworthy. N=3 felt sufficient until it wasn't. The cost was real — three lanes × 8 core prompts × 5 attempts × about 60 seconds per attempt is something like 2 hours per lane — but no shorter path produces numbers you'd actually publish.

:::math[The cost of an honest bench]
3 lanes × 8 prompts × 5 attempts × ~60 s/attempt ≈ **2 hours per lane**, ~6 hours total, on one Spark. Add ~5 minutes per lane for warmup + teardown + a 3-sample throughput probe at the end. On a cloud API the same suite would cost dollars; here it costs a slot in the evening.
:::

## Telemetry was the unexpected payoff

After the rubric stabilized, I added a system-telemetry pass — throughput probe, GPU%, peak unified memory, peak temperature, latency p50/p95/max — because the rubric was scoring *what the agent did* without seeing *what the box was doing*. The numbers that came out of that pass changed which lane I trusted.

The throughput probe is a dedicated 3-sample median-of-N call against the live lane, run after the suite (the lane is still warm). It produces a stable single number that's directly comparable across lanes — 83.5 tok/s for the Q4_K_M lane, 55.0 for vLLM FP8, 23.9 for NIM 9B. Latency is parsed from the per-attempt wall times (p50 21 s / p95 152 s / max 360 s for Q4_K_M; max 360 s being a clipped runaway, not a real upper bound). GPU% and unified memory are sampled every 2 seconds in a background thread for the full duration of the suite — about 15 minutes per lane.

```python
# Sampling unified memory on GB10 — the gotcha
import re, subprocess
# nvidia-smi memory.used returns [N/A] because GPU memory is unified with CPU
# memory on GB10 — parse each field independently to dodge the failed CSV
proc = subprocess.run(
    ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu",
     "--format=csv,noheader,nounits"], capture_output=True, text=True)
gpu_util, gpu_temp = (s.strip() for s in proc.stdout.split(","))

# Real memory comes from /proc/meminfo
mi = {k: int(v) for line in open("/proc/meminfo").readlines()
      for k, v in [re.match(r"(\w+):\s+(\d+)", line).groups()]}
unified_used_gb = (mi["MemTotal"] - mi["MemAvailable"]) / 1024**2
```

The GB10 gotcha is small but cost half an hour: `nvidia-smi memory.used` returns `[N/A]` because GPU and CPU memory are unified, and a single `[N/A]` aborts a naive CSV parse. The fix is to query each field independently and read real memory from `/proc/meminfo`. The article transcript carries the full code.

:::define[Telemetry, in `fieldkit.harness`]
`Telemetry` is a small dataclass populated by a background-thread sampler — `n_samples`, `gpu_util_mean`, `gpu_util_max`, `unified_used_gb_max`, `gpu_temp_c_max`. It rolls into `BrainScorecard.telemetry` so every per-lane JSON in the published bench carries the same five numbers, sampled at the same 2 Hz cadence.
:::

The unified-memory telemetry is what finally separated the two MoE lanes. Both scored 8/8 on the rubric. The vLLM FP8 lane peaked at **98 GB unified memory**; the llama.cpp Q4_K_M lane peaked at **32 GB**. On a 128 GB box that gap is a permission slip — 32 GB leaves room for a 70B critic, a vertical specialist, a database, half a desktop. 98 GB leaves room for service-level processes and not much else. Quality came in tied; the resident-brain choice was decided by which lane left the rest of the box usable.

## The three-lane verdict

Running the suite against the three top H2 lanes at N=5 gives a clean rank table — same shape that ships in the bench's [`results/summary.md`](https://huggingface.co/datasets/Orionfold/hermes-brain-bench-v0.1/blob/main/results/summary.md):

| Rank | Lane | core_pass | pass_rate | consistency | runaway | tok/s | peak unified |
|---:|---|:---:|---:|---:|---:|---:|---:|
| 1 | `qwen3-30b-moe-llamacpp-q4km` | 8/8 | 90% | 90% | 5% | 83.5 | 31.8 GB |
| 2 | `qwen3-30b-moe-vllm-fp8` | 8/8 | 88% | 88% | 0% | 55.0 | 97.8 GB |
| 3 | `nim-incumbent` | 6/8 | 78% | 82% | 3% | 23.9 | 92.9 GB |

All three lanes scored **100% honesty / 100% JSON-format / 100% clean-run**. The H2 finding (every lane clears the format gate) still holds; what was invisible to format-only scoring is the gap on *content*. The two prompts the 9B couldn't reliably pass were both multi-step: `p2_multistep_chain` (list → open the right file → extract value) at 2/5, and `p3_tool_plus_compute` (read CSV → sum column) at 2/5. Both MoE lanes passed them 4/5 or 5/5. That's not a prompt-design tell; it's a brain-capacity wall.

The 4-bit lane's one tax is `p6_code_microtask` running away to the 360-second timeout on one of five attempts — Q4_K_M's 5% runaway rate vs FP8's 0%. That's a meaningful but bounded cost; it's the trade for the 3× memory headroom. On a Spark you'd take it.

:::pitfall[The pad-window bucketing bug is invisible until you check]
Session-bucketing with a ±2-second pad window on `started_at` looks correct in the small-data case where prompts are spaced minutes apart. It silently double-counts when prompts run back-to-back — the second prompt's start falls inside the first session's window, so the first session gets counted twice. The fix (mutually-exclusive last-slot rule) cost ten lines; finding the bug cost half a day of confusing N=3 results.
:::

The qualitative finding — *throughput rank ≡ quality rank for this hardware* — is hardware-specific, not general. On a Spark, the 30B-A3B MoE is both faster (active 3B/token) and smarter (30B total) than a dense 9B; that's not true on a four-GPU server where dense 70B fits and is the rational pick. The reusable result is the *method* — a graded rubric + bytes-deterministic fixtures + N=5 + telemetry + a published reference — not the verdict itself.

## What this unlocks

Three things slot in immediately. The first is the **always-on local agent**: the Q4_K_M MoE warms in about 5 seconds, sits at 27 GB resting, and answers most tool-using turns inside p95 of 152 seconds. It runs on the desk through a workday without thermal drift (peak temp 71 °C, no throttle). The companion start/stop scripts in `evidence/start-llama-moe.sh` and `stop-llama-moe.sh` swap brains in seconds; the NIM 9B is still there for fallback.

The second is **measurable lane swaps**. Anything new — gpt-oss-20b, gpt-oss-120b, a quantized vertical specialist, a smaller chat-tuned 8B — runs through the same rubric, same fixtures, and lands as a peer entry in `results/<lane>.json` on disk or as a new line in your local `results/summary.md`. The cost of evaluating a candidate dropped from "design a benchmark" to "run the suite for an hour and compare the JSON." That's the leverage that makes the next router (H5) worth building — the dispatch logic is now informed by data, not vibes.

The third is the **published bench itself**. The methodology is replicable: install `fieldkit==0.11.0`, run the suite against your own lane via `fieldkit.harness.evaluate_brain`, drop your new lane's JSON next to the three reference ones, and you have an apples-to-apples comparison without having to defend the rubric. The bench is `cc-by-4.0`; the bytes-deterministic scratch fixtures and the `{{placeholder}}` substitution map are committed, so two people on two Sparks score the same lane to the same numbers.

```python
from pathlib import Path
import json
from fieldkit.eval import GradedPromptSuite
from fieldkit.harness import evaluate_brain, point_hermes_at_endpoint

bench = Path("hermes-brain-bench-v0.1")
gt = json.loads((bench / "ground_truth.json").read_text())
point_hermes_at_endpoint("http://127.0.0.1:8080/v1",
                        "Qwen3-30B-A3B-Q4_K_M", context_length=64000)
suite = GradedPromptSuite.load(bench / "data" / "train.jsonl", substitutions=gt)
sc = evaluate_brain(suite, label="my-lane", scratch_dir=bench / "scratch",
                   runs=5, core_only=True, enable_telemetry=True)
```

## Tradeoffs and gotchas

The biggest tradeoff is **wall time**. Six hours to score three lanes is a non-trivial slot of a Spark's evening, and most of that time the box is decode-bound at 91% GPU utilization — you can't usefully share it. The throughput cost is the price of N=5; cutting to N=3 saves four hours but, as the false-positive runs above showed, also loses the consistency signal that was the entire point. A future bench v0.2 could probably halve the cost with adaptive N (stop early on prompts that already match at 3/3), but v0.1 keeps the simple shape.

The second is that the rubric is **deterministic-only**. There's no LLM-judge step for the open-ended prompts, by design — every check is a substring, a JSON-parse, a regex, or a hedge-phrase match against a fixed list. That keeps the bench reproducible across runs and machines, but it also means a *correct paraphrase* of the answer can fail a substring check. The vibe-prompt convention (`vibe: true` in the prompt JSON) is the article's mitigation: those prompts surface to a human review queue, scored manually after the run. The four `vibe: true` prompts in v0.1 produce a one-line eyeball check per lane.

The third is the **hardware-specific result**. The 30B-A3B-class brain wins this rank on a 128 GB Spark; on a 24 GB consumer card it wouldn't fit and the comparison wouldn't exist. Publishing this bench is publishing a *methodology* that scales to other hardware, not a leaderboard that anyone else can show up on without re-running. The README of the published bench is careful about that: "reference scores, not a leaderboard," in those words.

:::hardware[Same rubric, frontier coefficients]
On a Spark, Q4_K_M MoE is 83.5 tok/s and 32 GB unified. On an H100 (80 GB HBM3), the same FP8 MoE lane is in the 250–400 tok/s range with the 98 GB working set fully resident in GPU memory — but the *quality* axis would land in the same place, because the rubric scores tool calls and answers, not arithmetic intensity. The harness measurement is hardware-portable; the resource ranking isn't.
:::

## Closing — and the cleared path to H5

The pin from this article is concrete: as of today, the Hermes brain on this Spark is the Qwen3-30B-A3B MoE running through llama.cpp at Q4_K_M, served on `127.0.0.1:8080`, swapped in and out via the two scripts under this article's `evidence/`. The H1 NIM cockpit is still there for fallback; the `start-nim.sh` script tears down the MoE lane first per the unified-memory envelope, which the [Spark unified-memory OOM note](/field-notes/dgx-spark-day-one-access-first/) explains the hard way.

The real product is the *measurement surface* that produced the pin. `fieldkit.eval` gained the graded-rubric primitives (`CheckSpec` / `Rubric` / `GradedPromptSuite` / `score_answer`); `fieldkit.harness` gained `BrainCandidate` / `BrainScorecard` / `evaluate_brain` / `Telemetry` / `measure_throughput`. The bench at `Orionfold/hermes-brain-bench-v0.1` (cc-by-4.0) ships the prompt suite, the scratch fixtures, the substitution map, and the three reference scorecards — drop a fourth lane's JSON in next to them and the comparison is honest.

Next in the series is the H5 vertical router — five Orionfold quants, one harness, one resident dispatch model that classifies the incoming prompt and swaps to the right vertical specialist. The picking surface this article shipped is what makes that worth building. A router on top of "vibes" is a coin flip; a router on top of a measured rubric is a real promotion.

---

**Catalog page:** [`/artifacts/benches/hermes-brain-bench-v0.1/`](/artifacts/benches/hermes-brain-bench-v0.1/) — three-mode bracket results, shape composition, sample rows per shape, and source provenance — the full bench card.
