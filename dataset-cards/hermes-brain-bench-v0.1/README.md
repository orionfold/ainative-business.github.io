---
license: cc-by-4.0
task_categories:
- text-generation
- question-answering
language:
- en
size_categories:
- n<1K
tags:
- agent
- agent-evaluation
- tool-calling
- benchmark
- local-llm
- dgx-spark
- hermes
- methodology
pretty_name: Hermes Brain Bench v0.1
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.jsonl
---

# Hermes Brain Bench v0.1

A small, diverse, graded-rubric benchmark for picking the **agent brain** behind
a local-only Spark deployment of an OpenAI-compatible tool-using assistant
(developed against [Hermes Agent](https://github.com/NousResearch/hermes), but
the suite is harness-agnostic — any OpenAI-tool-format runner works).

The bench answers a question that single-stream throughput benchmarks can't:
**which local serving lane actually produces the more correct agent — under the
same rubric, run-to-run?**

Companion artifacts (Field Notes):

- [`fieldkit.eval` graded-rubric primitives](https://ainative.business/field-notes/fieldkit/api/eval/) — `GradedPromptSuite`, `CheckSpec`, `Rubric`, `score_answer`. Loads this suite.
- [`fieldkit.harness` brain evaluator](https://ainative.business/field-notes/fieldkit/api/harness/) — `evaluate_brain`, `BrainScorecard`, `bucket_hermes_sessions`, `Telemetry`, `measure_throughput`. Runs this suite. Both shipped in [`fieldkit==0.11.0`](https://pypi.org/project/fieldkit/0.11.0/).

## What it measures

Ten prompts, eight `core: true` (cross-lane comparable), two `core: false`
(conditional on MCP / RAG being wired). Each prompt carries an explicit
deterministic check (substring / `json_keys` / regex / honesty hedge / numeric)
plus expected tools. Categories:

| Prompt | Category | Discriminator role |
|---|---|---|
| `p1_read_grounding` | single tool call + grounding | floor — every brain should pass |
| `p2_multistep_chain` | multi-step tool chain (list → pick → extract) | **brain-capacity wall** in our N=5 bakeoff |
| `p3_tool_plus_compute` | tool + arithmetic reasoning | medium-band variance |
| `p4_honesty` | refusal of an unknowable private fact | **hedge-vs-confabulate gate** (honesty must pass to rank at all) |
| `p5_strict_json_format` | strict output-format constraint | format-discipline gate |
| `p6_code_microtask` | code micro-task (one-liner) | medium-band variance |
| `p7_mcp_envelope` | drive a read-only MCP tool (`spark_inference_envelope`) | conditional — skipped if MCP off |
| `p8_rag_secondbrain` | RAG via second-brain | conditional — skipped if RAG off |
| `p9_multifile_join` | join two files + per-row multiply + sum | hard discriminator |
| `p10_disambiguation_trap` | pick the right key among distractors + unit transform | hard discriminator |

The seven seeded fixtures under `scratch/` (`facts.txt`, `notes/budget-q3.txt`,
`numbers.csv`, `inventory.csv`, `prices.csv`, `service.conf`, plus two
distractor notes) are **bytes-deterministic** so every lane sees exactly the
same world.

## How to score

The runner exports the agent's [Hermes session
JSONL](https://github.com/NousResearch/hermes), buckets tool calls + final
answers per prompt with a mutually-exclusive last-slot rule (replaces a buggy
±2s pad-window that double-counted back-to-back attempts), and scores against
the per-prompt `check.kind`:

- `substring` — `answer` contains any of `check.any`
- `json_keys` — `answer` parses to JSON with exactly `check.keys`
- `regex` — `answer` matches all of `check.all`
- `honesty` — `answer` contains any of `HEDGE_PHRASES` (declines to guess)
- `numeric` — numeric tolerance check (unused in v0.1)

`{{placeholder}}` tokens in `check.any` (e.g., `{{codename}}`,
`{{grand_total_comma}}`) are resolved from `ground_truth.json` so the suite and
the seeded scratch files can never drift apart.

Each prompt runs **N=5** by default and aggregates to:

- `pass_rate` — fraction of attempts whose check passed
- `agreement` — majority-answer consistency across attempts
- `correct_tool_rate` — fraction that called any tool in `expect_tool_any`
- `runaway_rate` — fraction that hit the per-attempt timeout (default 360 s)
- `wall_mean/min/max` — per-attempt wall-clock seconds

…which roll up to a per-lane `BrainScorecard` with `core_pass_rate`,
`consistency`, `runaway_rate`, `honesty_pass_rate`, `json_format_pass_rate`,
plus a throughput probe (`tokens_per_sec`, median of 3) and GPU/unified-memory
telemetry sampled every 2 s during the run.

**Rank key:** honesty-as-a-gate → mean core `pass_rate` → consistency → fewer
runaways → `tokens_per_sec` as tiebreaker.

## Reference scores — three lanes, N=5, DGX Spark GB10 (128 GB unified)

Full per-lane scorecards live in `results/`. The cross-lane summary:

| Rank | Lane | core_pass | pass_rate | consistency | runaway | tok/s | peak unified |
|---:|---|:---:|---:|---:|---:|---:|---:|
| 1 | `qwen3-30b-moe-llamacpp-q4km` (Qwen3-30B-A3B MoE, llama.cpp Q4_K_M) | 8/8 | 90% | 90% | 5% | 83.5 | 31.8 GB |
| 2 | `qwen3-30b-moe-vllm-fp8` (Qwen3-30B-A3B MoE, vLLM FP8) | 8/8 | 88% | 88% | 0% | 55.0 | 97.8 GB |
| 3 | `nim-incumbent` (NVIDIA Nemotron-Nano-9B-v2 NIM, DGX-Spark) | 6/8 | 78% | 82% | 2% | 23.9 | 92.9 GB |

All three lanes scored **100% honesty / 100% JSON-format / 100% clean-run** (no
format errors over the run, no malformed tool calls). The discriminator was
`p2_multistep_chain` — the 9B-class lane completed it on 2/5 attempts, the
30B-A3B MoE lanes on 4–5/5. The 4-bit lane's 5% runaway rate is the cost of
going 4-bit (1× `p6_code_microtask` hit the 360 s timeout); the FP8 lane had no
runaways but used 3× the unified memory.

These are **reference scores, not a leaderboard.** A new lane that scores `7/8
(85%)` is comparable to the lanes above only if it's run with the same N=5,
same scratch dir, same rubric, same runner version. The runner pins the
prompt-suite version + `fieldkit` version in the scorecard for that reason.

## What this bench is NOT for

- Not a general-purpose LLM benchmark. Ten prompts can't generalize beyond the
  agent-brain question on a local serving lane.
- Not a serving-lane benchmark for throughput / latency / sustained-load. See
  [`Orionfold/spark-hermes-profile`](https://huggingface.co/Orionfold/spark-hermes-profile)
  (the H2 serving-lane bakeoff) for that.
- Not a model-capability benchmark. Tool-using-agent capability is one slice of
  what a model can do.
- Not a calibrated leaderboard. Different harnesses, different system prompts,
  and different stub tools will all shift absolute pass rates by tens of
  points. Comparable-with-self only.

## Schema

```
data/train.jsonl                  # one prompt per line
  id                str           # p1_read_grounding, p2_multistep_chain, …
  category          str           # human-readable category
  core              bool          # true → counts toward core_pass_rate
  conditional       str | null    # mcp_fieldkit etc. — gate the prompt on capability
  prompt            str           # the prompt sent verbatim to Hermes
  expect_tool_any   List[str]     # tool-name substrings — empty means no tool expected
  check             object        # {kind: substring|json_keys|regex|honesty|numeric, …}
  vibe              bool          # heuristic check — eyeball the answer too
  note              str           # optional design note (kept for context)

ground_truth.json                 # {{placeholder}} → resolved value
  codename          str           # ORION-7
  budget            str           # 42,000
  csv_sum           str           # 10250
  grand_total       str           # 16950
  read_ms           str           # 37000
  …

scratch/                          # bytes-deterministic seeded fixtures
  facts.txt
  notes/budget-q3.txt
  notes/roadmap.txt
  notes/standup-2026-05-20.txt
  numbers.csv
  inventory.csv
  prices.csv
  service.conf

results/<lane>.json               # full BrainScorecard, including per-prompt attempts + telemetry
results/summary.md                # human-readable cross-lane rank + flaky-prompt notes
```

## How to run it on your own Spark

### 1. Install `fieldkit==0.11.0` with the harness extra

```bash
pip install 'fieldkit[harness]==0.11.0'
```

### 2. Stand up a local serving lane

Anything that speaks OpenAI tool-format will do — `llama-server`, `vllm
serve`, an NVIDIA NIM container, ollama. For the lanes scored in `results/`:

- **`qwen3-30b-moe-llamacpp-q4km`** — `llama-server -m
  Qwen3-30B-A3B-Q4_K_M.gguf --host 127.0.0.1 --port 8080 -ngl 99 -c 64000
  --jinja`
- **`qwen3-30b-moe-vllm-fp8`** — `vllm serve Qwen/Qwen3-30B-A3B-FP8
  --enable-auto-tool-choice --tool-call-parser hermes --port 8000
  --max-model-len 64000`
- **`nim-incumbent`** — the cached `nemotron-nano-9b-v2-dgx-spark` NIM on
  `:8000` (NIM ships the correct tool-call parser by default)

### 3. Point Hermes at it + run the suite

```python
from pathlib import Path
import json
from fieldkit.eval import GradedPromptSuite
from fieldkit.harness import evaluate_brain, point_hermes_at_endpoint

bench = Path("hermes-brain-bench-v0.1")
ground_truth = json.loads((bench / "ground_truth.json").read_text())

# light-touch Hermes config swap (saves old config, restored on exit):
point_hermes_at_endpoint(
    "http://127.0.0.1:8080/v1",
    "Qwen3-30B-A3B-Q4_K_M",
    context_length=64000,
)

suite = GradedPromptSuite.load(
    bench / "data" / "train.jsonl",
    substitutions=ground_truth,
)

scorecard = evaluate_brain(
    suite,
    label="my-lane",
    scratch_dir=bench / "scratch",
    runs=5,
    core_only=True,
    enable_telemetry=True,
)

print(f"{scorecard.label}: {scorecard.core_pass}/{scorecard.core_n} "
      f"(pass_rate={scorecard.core_pass_rate:.0%}, "
      f"consistency={scorecard.consistency:.0%}, "
      f"{scorecard.tokens_per_sec:.1f} tok/s, "
      f"runaways={scorecard.runaway_rate:.0%})")
```

The article driver at
[`articles/picking-the-hermes-brain-on-spark/evidence/hermes_brain_eval.py`](https://github.com/manavsehgal/ai-field-notes/blob/main/articles/picking-the-hermes-brain-on-spark/evidence/hermes_brain_eval.py)
is a thin layer on `fieldkit.harness.evaluate_brain` and produces the
`results/<lane>.json` shape this bench publishes — use it verbatim and drop
your new lane's JSON next to ours for an apples-to-apples comparison.

## Companion article

📝 [Picking the Hermes Brain on a DGX Spark](https://ainative.business/field-notes/picking-the-hermes-brain-on-spark/)
— the deep-dive that produced this bench. Walks the suite design, the three
mid-run fixes, the consistency-not-difficulty finding, the telemetry pass,
and the three-lane verdict. Pairs with the prior
[Hermes Serving Lane on a DGX Spark](https://ainative.business/field-notes/hermes-serving-lane-on-spark/)
(the throughput bakeoff this bench extends).

## Versioning

- **v0.1** — initial release. 10 prompts (8 core + 2 conditional), 7 seeded
  fixtures, 3 reference-lane scorecards (N=5 each), `fieldkit==0.11.0`.

## License

`CC-BY-4.0`. The seed fixtures are synthetic test data; the prompts are
original; the reference scorecards are measurement output. Attribution
appreciated.
