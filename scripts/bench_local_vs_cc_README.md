# Local-vs-CC routing bench (20 rows)

A one-shot 3-way head-to-head deciding **Track B routing** for the
patent-strategist W3 production corpus (see HANDOFF.md). Asks:
*can a local SLM author production-quality patent `<think>` chains,
or do we need CC-in-session for some / all of the work?*

## What it tests

Same 20 prompts → three generators → side-by-side `<think>chain</think>answer`
output for vibe-test scoring. Prompts are drawn from the same
`FAMILY_TEMPLATES` + `SPICE` the production `claude-corpus-synth` skill
uses, so the bench measures the actual surface, not a toy proxy.

20 rows = 5 each across **A1** (claim drafting), **A2** (indefiniteness),
**A4** (office-action traversal), **E1** (plain-English explanation).
E2 (MCQ generation) is dropped — it's the least patent-prose-shaped
family and doesn't discriminate generators on legal-coherence.

## Top candidates from the SOTA scout (2026-05-18)

| Generator | Model | Backend | Why |
|---|---|---|---|
| Ollama #1 | `qwen3.5:9b` | Ollama | Apache-2.0, Mar 2026 SOTA, native `<think>` on by default |
| NIM #1 | `nvidia/nemotron-nano-9b-v2` | NIM container (Spark-tagged) | Native `<think>` + `/think` toggle, ~3× speed of baseline Llama-3.1-8B NIM |
| CC reference | — | CC-in-session (claude-corpus-synth pattern) | Quality ceiling we're trying to match locally |

Full reports: `/tmp/sml-research/{ollama,hf,nvidia}-sota.md`.

## Flow

```
1. prepare    →  queue.jsonl              (20 prompts, balanced, seed=42)
2. run each generator independently:
     ollama   →  out-ollama-<slug>.jsonl
     nim      →  out-nim-<slug>.jsonl
     cc       →  out-cc.jsonl             (Claude appends in-session)
3. render     →  comparison.md + summary.json
4. eyeball    →  fill in "Your score" column in comparison.md
```

All artifacts live in `/tmp/aifn-bench-local-vs-cc/` (autoclean per the
browser-smoke memory convention).

## Step 1 — build the queue

```bash
cd /home/nvidia/ainative-business.github.io
python3 scripts/bench_local_vs_cc_prepare.py
# Wrote /tmp/aifn-bench-local-vs-cc/queue.jsonl (20 rows, seed=42)
#   A1: 5
#   A2: 5
#   A4: 5
#   E1: 5
```

## Step 2a — Ollama run

Pre-req: `ollama pull qwen3.5:9b` (5.5 GB), `ollama serve` reachable on
`localhost:11434`. Qwen3.5 has `<think>` default-on, no system prompt needed.

```bash
python3 scripts/bench_local_vs_cc_ollama.py --model qwen3.5:9b
```

For DeepSeek-R1-Distill (the Ollama-ecosystem #2 pick):

```bash
python3 scripts/bench_local_vs_cc_ollama.py --model deepseek-r1:14b
```

## Step 2b — NIM run

Pre-req: the Nemotron-Nano-9B-v2 NIM container running on `localhost:8000`.
Pass `--system "/think"` to force thinking-on (Nemotron toggle).

```bash
python3 scripts/bench_local_vs_cc_nim.py \
  --model nvidia/nemotron-nano-9b-v2 \
  --system "/think"
```

For the existing Llama-3.1-8B-Instruct NIM baseline (no native think — will
likely score 0/20 on `<think>` presence; useful as a *negative* anchor):

```bash
python3 scripts/bench_local_vs_cc_nim.py \
  --model meta/llama-3.1-8b-instruct
```

## Step 2c — CC-in-session run

Same pattern as the `claude-corpus-synth` skill: Claude (this session)
reads `/tmp/aifn-bench-local-vs-cc/queue.jsonl` and appends one row per
prompt to `/tmp/aifn-bench-local-vs-cc/out-cc.jsonl` via the Edit tool.
One row schema (mirrors the HTTP generators):

```json
{"row_idx": 0, "family": "A1", "backend": "cc", "model": "claude-opus-4-7",
 "think": "...", "answer": "...", "has_think": true,
 "wall_s": null, "prompt_tok": null, "output_tok": null}
```

In an `/clear`'d CC session, point Claude at this README + queue.jsonl and
ask "generate the cc-in-session leg of the routing bench." No script needed.

## Step 3 — render the comparison

```bash
python3 scripts/bench_local_vs_cc_render.py
# Wrote /tmp/aifn-bench-local-vs-cc/comparison.md
# Wrote /tmp/aifn-bench-local-vs-cc/summary.json
```

The renderer discovers all `out-*.jsonl` files in the dir automatically —
so you can run any subset of generators and re-render incrementally.

## Step 4 — eyeball pass

Open `comparison.md`. Each row has:

- The prompt
- Per-generator `<think>` block + answer (collapsed `<details>`)
- A blank score column for 1–5 legal coherence

Bar to set:

- **5** — production-quality. Cites concrete MPEP / 35 USC sections, applies the
  rule correctly, conclusion answers the question in 1–3 sentences.
- **3** — directionally right but vague citations or shallow chain.
- **1** — wrong, hallucinated citation, or no usable `<think>` structure.

## Decision rule

After the eyeball pass, count rows ≥4/5 per generator:

| Local-best score | Routing decision |
|---|---|
| **≥ 16/20** (≥80%) | Pure local — Track B option (a). Skip CC for corpus gen entirely. |
| **10–15/20** | Hybrid — local generates 3 candidates per row, CC-in-session picks best. Track B option 1. ~67% CC cap savings. |
| **< 10/20** | CC-in-session only — Track A. Local quality is a filter cost, not a generator. |

Time budget: 5 min to build queue, ~30 min wall per generator at 20 rows
(plus model pull time on first Ollama run), ~30 min eyeball — total ~2h
if all three runs go clean.
