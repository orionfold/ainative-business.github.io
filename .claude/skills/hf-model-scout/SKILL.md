---
name: hf-model-scout
description: Picks the next production base model to quantize + publish under the `Orionfold` user handle. Sibling to `hf-publisher` (publish surface) and `frontier-scout` (paper scouting) — this skill owns the *pick surface*. Trigger when the user says "find me a base model for <vertical>", "pick a base for the legal/cyber/medical card", "scout HF for a 7B finance model", "what should we quantize next", "/hf-model-scout <vertical>", or whenever a vertical-curator cycle needs a base-model decision before `g3_build_first_quant.sh download`. Codifies the four traps that cost real time on session 2 (instruction-pretrain models that have no chat_template; NC-license bases that block commercial Orionfold tier; unsupported llama.cpp architectures; oversized weights that won't fit the Spark's 128 GB unified-memory envelope). Outputs a top-3 ranked report at `/tmp/hf-scout/<run>/report.md`. Do NOT trigger for: paper scouting (`frontier-scout`), already-picked-model publishing (`hf-publisher`), general HF download questions, or fine-tuning a model the user has already chosen.
---

# hf-model-scout

Owns the *Orionfold base-model pick surface*. Codifies the gates we burned ~90 minutes discovering on `instruction-pretrain/finance-Llama3-8B` (continued-pretrain trap, 0/250 closed-book — feedback memory `[[feedback_chat_vs_continued_pretrain_trap]]` + `[[feedback_preflight_bench_before_quant]]`).

This skill is a **single-shot scout**, not a pipeline. It produces one markdown report; the user picks; downstream is `g3_build_first_quant.sh MODEL_ID=<picked>` then `g3_preflight_bench.py`. The skill does not write into `articles/`, `papers/`, or git-tracked dirs. All output lives at `/tmp/hf-scout/<YYYY-MM-DD>/<vertical>-<size>B/`.

## Where this slots in the cluster G pipeline

```
hf-model-scout         →  scripts/g3_build_first_quant.sh  →  fieldkit.publish          →  hf-publisher
(pick the base)           (download + convert + quantize)     (build the model card)       (push to HF live)
```

When the user says "ship the next finance/legal/cyber/medical card", the first thing they need is a base. This skill picks it.

## Mode router

| Mode          | Triggered by                                                        | Behavior                                                                              |
|---------------|---------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| `scout`       | default; "find/pick/scout … for <vertical>", `/hf-model-scout`      | Run the full 4-axis classification on 8–12 candidates, emit `report.md`, pause.       |
| `probe`       | "probe <repo>", "is <hf-repo> chat-tuned", "evaluate <repo> for spark" | Run the four classifiers on a single named repo. No search. Append to existing run if one exists today. |
| `lite`        | "quick scout", "lightning scout", "give me a one-line pick"         | Skip the full classifier — search + rank by trending_score + downloads + size, return top-3 names without per-model probing. Use only when the user needs a starting list and will probe themselves. |

Default to `scout`. Never auto-escalate to `lite` (it skips the trap detection that this skill exists to do).

## Every invocation — read these first

Three non-skippable preflights. If any fails, surface to the user and bail.

### 1. The HF CLI must resolve

```bash
HF=/tmp/fk-test/bin/hf  # canonical path on this Spark
test -x "$HF" || echo "MISSING — install via /tmp/fk-test venv first"
```

If missing, the user needs to `python3 -m pip install huggingface_hub` into a venv. This skill doesn't install dependencies.

### 2. Spark capability data must be readable

```bash
test -r /home/nvidia/ainative-business.github.io/scripts/lib/spark-capabilities.json || echo "MISSING"
```

Spark envelope math (memory fit, expected tok/s, quant-size estimates) all derive from this file via `fieldkit.capabilities`. Without it, the "Spark envelope" axis is blocked.

### 3. The run directory must be carvable

```bash
RUN_DIR="/tmp/hf-scout/$(date -u +%Y-%m-%d)/<vertical>-<size>B"
mkdir -p "$RUN_DIR"
```

If the same vertical+size was scouted earlier today, **append** the new candidates to the existing `report.md` under a "Re-scout at HH:MM UTC" subsection rather than overwriting. The user has read the prior report; preserve it for diff.

## Inputs

Gather via `AskUserQuestion` if the user's invocation didn't supply them:

| Field          | Examples                                  | Required | Resolution if missing                                                |
|----------------|-------------------------------------------|----------|----------------------------------------------------------------------|
| `vertical`     | finance, legal, cyber, medical, code, math | yes      | Ask single-select 4-option question                                  |
| `size_class`   | 7B, 8B, 13B, 14B                          | yes      | Ask single-select. Default 7B/8B for first cards.                    |
| `license_tier` | permissive (commercial-OK) / any          | no       | Default `permissive` — Orionfold is a commercial brand               |
| `eval_bench`   | FinanceBench, LegalBench, MedQA, …        | no       | Default per vertical; see `references/vertical-queries.md`           |
| `notes`        | any user-supplied constraint              | no       | Echo back into the report header                                     |

When the user invokes with a one-liner like `/hf-model-scout legal 8B`, parse the args; don't re-ask.

## Scout mode — full workflow

### Step 1. Build the search query

Pull the query stem for the requested `vertical` from `references/vertical-queries.md`. Each vertical has a primary query and a fallback. Example for `legal`:

```
primary:  legal OR law
fallback: contract OR statute
```

### Step 2. Search HF for candidates

```bash
HF=/tmp/fk-test/bin/hf
"$HF" models list \
  --search "<query>" \
  --filter "text-generation" \
  --num-parameters "min:6B,max:9B" \  # adjust per size_class
  --sort trending_score \
  --limit 25 \
  --expand downloads,likes,tags,gated,library_name,pipeline_tag
```

Save raw output to `$RUN_DIR/search-raw.txt`. From the 25 returned, filter:

- **Drop** gated/private repos — check `gated` field against **both** `True` (boolean) AND `"auto"` (string). The auto-gate is a soft-redistribution policy that still blocks clean re-publish under the Orionfold flow. On the 2026-05-16 medical scout, `ContactDoctor/Bio-Medical-Llama-3-8B` had `gated="auto"` and a naive boolean check let it through — caught on manual review only.
- **Drop** non-`text-generation` pipeline tags
- **Drop** any whose name reveals continued-pretrain pattern: `*-pretrain*`, `*-continued*`, `*-base` (unless paired with `*-instruct` or `*-chat` sibling — flag for the user)
- **Keep** top 8–12 by composite popularity. **Use `downloads + 50*likes` as the base ranker, but break ties / re-rank the top tier by `likes / max(downloads, 1)` ratio** — high-ratio entries are "fresh and climbing" candidates that raw downloads under-rank. On the 2026-05-16 medical scout, `Intelligent-Internet/II-Medical-8B`'s 3.6% like-rate flagged it as a stronger climbing signal than OpenBioLLM-8B's raw popularity would suggest; the ratio re-rank lifts these climbers into the candidate set.

### Step 3. Probe each candidate (the four axes)

For each surviving candidate, run `scripts/probe_model.sh <repo>`. The probe:

1. Downloads `tokenizer_config.json`, `README.md`, `config.json` to `$RUN_DIR/probes/<repo-slug>/`.
2. Detects **chat-format** by reading `chat_template` field — maps to one of `llama-2` / `llama-3` / `chatml` / `mistral` / `gemma` / `phi-3` / `zephyr` / `vicuna` / `openchat` / `qwen` per `[[reference]]` from hf-publisher's `references/chat-formats.md`. **The "MISSING" outcome is the trap** — surface in red.
3. Detects **license** by reading the README's `license:` frontmatter line + the README "License" section — maps to the hf-publisher license-tag set (`apache-2.0` / `llama2` / `llama3` / `gemma` / `cc-by-nc-4.0` / …).
4. Detects **training-type** by name + README signals — `*-Chat`, `*-Instruct`, `*-Hermes`, `*-Tulu`, `*-Zephyr`, `*-DPO`, `*-ORPO`, `*-SFT` are SFT-flavored; `*-pretrain*`, `*-continued*`, `*-base` are continued-pretrain (the trap).
5. Computes **Spark envelope** via `scripts/spark_envelope.py <repo>`. Reads `config.json` for `hidden_size` + `num_hidden_layers` + `vocab_size`, computes F16 weight bytes + Q4_K_M estimate, checks against `fieldkit.capabilities.practical_inference_envelope(...)`.
6. Checks **llama.cpp compatibility** by mapping `config.json:model_type` against the supported arch list in `references/arch-compat.md`. Llama-2, Llama-3, Mistral, Qwen2/3, Phi-3, Gemma-2/3 are supported; Skywork-MoE, MiniMax, Internlm3, others are NOT.

Each probe writes one JSON to `$RUN_DIR/probes/<repo-slug>/probe.json`:

```json
{
  "repo": "equall/Saul-7B-Instruct-v1",
  "chat_format": "llama-2",
  "license": "llama2",
  "training_type": "SFT",
  "spark_envelope": {"fits_fp16": true, "fits_q4km": true, "estimated_tg_tok_s": 32.0},
  "llama_cpp_compat": true,
  "downloads": 12345,
  "likes": 89,
  "score": 87,
  "verdict": "RECOMMEND",
  "warnings": []
}
```

`verdict` is one of:
- `RECOMMEND` — passes all four axes
- `RECOMMEND_WITH_NOTE` — passes but has a single non-fatal warning (e.g., low downloads, niche arch)
- `RULE_OUT` — fails at least one axis (continued-pretrain / NC-license / unsupported-arch / oversized)
- `MANUAL_REVIEW` — chat-template is MISSING but model name strongly suggests SFT — user judgment needed

`score` is 0–100; baseline = trending+downloads percentile + 10 per passing axis. Top 3 of the RECOMMEND-tier go into the report.

### Step 4. Gather the sample-balancing state

Before writing the report, read the current Orionfold shape distribution so the recommendation can pre-load the Q8_0 expectation per `references/quant-shape-signals.md`. Two paths:

- **Fast path** — read the snapshot table in `references/quant-shape-signals.md` ("Vertical N+1 sample-balancing — the discriminating-pick rule") and use the counts. Cheap; one read; drift risk if a vertical has shipped since the doc was edited.
- **Authoritative path** — survey shipped verticals via `git log --diff-filter=A --name-only -- 'articles/becoming-a-*-curator-on-spark/' | head -50`, then for each `becoming-a-<X>-curator-on-spark` resolve the base model's training shape (cross-check `articles/<slug>/index.mdx` or the HF card). Use this when you suspect the snapshot is stale (>1 week since last vertical ship date).

Record the resulting count (e.g., "current: 2 continued-pretrain / 2 chat-tune-only") in a one-line state variable; you'll inline it into the report header in step 5. Also pre-tag each candidate's training-shape so step 5 can emit the per-pick "Q8_0 expectation" line.

### Step 5. Write the report

Template at `references/report-template.md`. The shape:

```markdown
# HF Model Scout — <vertical> @ <size>B

> Run: <YYYY-MM-DD HH:MM:SS UTC> · <license_tier> · <eval_bench>
> <user-notes line if supplied>

## Sample-balancing gate

> Current Orionfold shape distribution: <N> continued-pretrain (<verticals>), <M> chat-tune-only (<verticals>).
> Strategy prescription this cycle: pick **<shape>** to promote the n=<count> pattern toward an n=<count+1> rule.
> Source: `references/quant-shape-signals.md` + `[[project_q8_anomaly_model_specific]]`.

(Use this block to frame the picks below. If all top-3 candidates fall on the prescribed side, no further action. If none do, flag in the "Why it wins" paragraph and recommend either re-running on different keywords or accepting an off-prescription sample.)

## Recommended picks

### 1. <repo> — score N/100 · <one-line verdict>
- **License**: <tag> — <commercial-OK or NC-blocker>
- **Chat format**: <llama-2/llama-3/chatml/…> — detection signal: `<tokenizer-template snippet>`
- **Training type**: <SFT/RLHF/DPO/continued-pretrain> — based on name + README
- **Q8_0 expectation**: <~25–35% slower / ~70–80% faster / UNKNOWN_SHAPE> — recommended-variant default = <Q5_K_M / Q4_K_M / Q8_0 / defer> per `references/quant-shape-signals.md`
- **Spark envelope**: F16=<X> GB, Q4_K_M=<Y> GB, est tg=<Z> tok/s — <fits / doesn't fit>
- **llama.cpp**: <arch> supported ✓
- **Why it wins**: <one paragraph — what makes this the right pick vs the others; if this is the prescribed shape, say so; if it isn't, note the trade-off vs the sample-balancing strategy>

### 2. <repo> — score N/100 …
### 3. <repo> — score N/100 …

## Picks ruled out

| Repo                          | Reason                                                                    |
|-------------------------------|---------------------------------------------------------------------------|
| <repo>                        | no chat_template — continued-pretrain trap                                |
| <repo>                        | cc-by-nc-4.0 — blocks commercial Orionfold tier                           |
| <repo>                        | Skywork-MoE — not supported by llama.cpp `convert_hf_to_gguf.py`          |
| <repo>                        | F16=28 GB — exceeds Spark practical envelope                              |

## Next steps

For the recommended pick:

```bash
MODEL_ID=<repo> ./scripts/g3_build_first_quant.sh download
MODEL_ID=<repo> ./scripts/g3_preflight_bench.py  # gate before quant cycle
# If preflight ≥1/5: MODEL_ID=<repo> ./scripts/g3_build_first_quant.sh convert quant publish-dryrun
```

> Generated by `hf-model-scout` — `/tmp/hf-scout/<YYYY-MM-DD>/<vertical>-<size>B/report.md`
```

Write `$RUN_DIR/report.md` + a `$RUN_DIR/candidates.json` sidecar with all probe.json's merged. Print only the path + the top-3 names + the one ruled-out trap-class summary to chat — the user reads the markdown.

## Probe mode — single-repo workflow

User says "probe `<repo>`" or "is `<repo>` chat-tuned". Skip step 1+2, run step 3 directly on the named repo, surface the four-axis verdict to chat. If a today-run already exists for the matching vertical+size, append the probe to that report's "Probed standalone" section. Otherwise emit a 30-line one-candidate report at `/tmp/hf-scout/<date>/standalone/<repo-slug>/report.md`.

## Lite mode — search-only

User says "quick scout" or "give me a one-liner". Skip step 3. Run step 1 + 2, sort by `trending_score × downloads`, return top-3 repo names + sizes + licenses to chat without per-model probing. **Warn** in chat that the four-axis traps aren't checked — the user might walk into the continued-pretrain trap.

## What NOT to do

- **Do not** download the actual weights — just `tokenizer_config.json` + `README.md` + `config.json` (collectively ≤200 KB). Weight download happens later in `g3_build_first_quant.sh`.
- **Do not** write to `papers/`, `articles/`, or any git-tracked dir. `/tmp/hf-scout/` only.
- **Do not** invoke `hf-publisher` or `g3_build_first_quant.sh` yourself — those are downstream of this skill's output, gated on user picking.
- **Do not** silently auto-pick if multiple candidates tie — surface the tie and ask. The user wants to see what was ruled out, not just the winner.
- **Do not** ignore the `MANUAL_REVIEW` verdict — surface it in the report as a fourth section between "Recommended picks" and "Picks ruled out". The continued-pretrain trap looks identical to a SFT model whose tokenizer_config.json is just missing the field; the model's README can save it (per the AdaptLLM/finance-chat example — chat-tuned, no chat_template field, README confirms `[INST]` usage).

## References this skill uses

- `references/vertical-queries.md` — search query stems per vertical (finance/legal/cyber/medical/code/math), with rationale for each keyword pick
- `references/training-signals.md` — name pattern + README signal table for SFT/RLHF/DPO vs continued-pretrain
- `references/quant-shape-signals.md` — downstream Q8_0 expectation per training shape (n=4 evidence) + the vertical N+1 sample-balancing rule
- `references/arch-compat.md` — `convert_hf_to_gguf.py` supported architectures, kept in sync with llama.cpp release tags
- (cross-skill) `~/.claude/skills/hf-publisher/references/chat-formats.md` — chat-template detection table
- (cross-skill) `~/.claude/skills/hf-publisher/references/license-tags.md` — license-tag decision tree
- (data) `/home/nvidia/ainative-business.github.io/scripts/lib/spark-capabilities.json` — Spark envelope math input

## Memory pointers

- `[[feedback_chat_vs_continued_pretrain_trap]]` — the load-bearing reason this skill exists
- `[[feedback_preflight_bench_before_quant]]` — the gate downstream of this skill
- `[[project_q8_anomaly_model_specific]]` — the 4-vertical Q8_0 split feeding the sample-balancing gate
- `[[project_orionfold_parent_brand]]` — the commercial-tier constraint on `license_tier=permissive` default
- `[[project_spark_unified_memory_oom]]` — the upper bound on Spark envelope checks

## Non-negotiables

- Never recommend a model with chat_template MISSING + no SFT-flavor signal in the name/README — that's the trap.
- Never recommend a non-commercial license when `license_tier=permissive`. If a non-permissive license is the only option in the vertical, return zero recommended picks and explain.
- Never run with `lite` mode silently when the user said "scout" or "find" without the explicit "quick" / "lite" / "one-liner" phrasing.
- Never write outside `/tmp/hf-scout/`. The skill's output is scratch; the user promotes a pick into the in-flight article's `evidence/` dir if they want a paper-trail.
