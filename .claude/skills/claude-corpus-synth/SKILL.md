---
name: claude-corpus-synth
description: Generates patent `<think>chain</think>answer` training-corpus rows IN the Claude Code CLI session itself — no API calls, no subprocess, no `anthropic` / `claude-agent-sdk` imports. Claude (the session model) writes rows directly via Edit-append using the spec §4 Layer 2 prompt template. Trigger when the user says "build the production corpus", "synth the 25k patent corpus", "generate the W3 training data", "spec §4 Layer 2 corpus", `/claude-corpus-synth`, or whenever the patent-strategist W3 production fine-tune unblocks (current state: blocked-on-corpus per HANDOFF). ALWAYS gate live runs with paste-`/usage` pre-flight showing projected % of weekly Max 20x cap consumed AND estimated number of CC sessions needed. Three modes — `dry` (5 rows in one assistant turn, validates prompt + measures tokens-per-row), `preflight` (computes weekly-cap delta + session-count from dry-run measurement), `live` (cursor-driven batch loop across multiple CC sessions). Do NOT trigger for non-patent corpora without re-reading _SPECS/patent-strategist-v1.md §4. Do NOT use this skill to invoke Claude via any subprocess / SDK / API key.
---

# claude-corpus-synth

Owns the *Claude-routed artifact-generation surface* for the patent-strategist project. The canonical example of in-CC-session orchestration: the skill itself drives Claude (the session model) to generate rows directly via Edit-append; no Python script ever calls Claude.

## Architecture rule — read first

**Claude generates rows IN this CC session. No subprocess. No SDK. No API.** Scripts in this skill are deterministic helpers only:

- `scripts/prepare_queue.py` — builds the prompt queue (no LLM call)
- `scripts/preflight_budget.py` — estimates this session's token cost (no LLM call)
- `scripts/merge_outputs.py` — validates + consolidates outputs (no LLM call)
- `scripts/verify_chunk.py` — validates a single producer chunk (no LLM call)

If you (Claude) catch yourself wanting to import `anthropic`, `claude_agent_sdk`, or shell out to `python … -c 'client.messages.create(…)'` — stop. The user has explicitly banned that path. See memory `[[feedback_llm_skill_pattern]]` for the canonical pattern.

**Subagent fan-out IS in-session orchestration** (validated session 34, 2026-05-18). Spawning `general-purpose` subagents via the Agent tool runs inside the CC harness — not via SDK, not via subprocess to an external `claude` binary. The orchestrator (you, the CC session model) remains the source of truth for cursor + out.jsonl; subagents only write to disjoint chunk files. See `references/producer-subagent-prompt.md` and "Fan-out mode" below.

## Where this slots in the patent-strategist W3 pipeline

```
claude-corpus-synth  →  g3_train_first_lora.sh (EPOCHS=2)  →  compare_probes (vs baseline-4096)  →  hf-publisher (paired drop)
(synth the patent     (run production overnight LoRA)         (PASS/FAIL gate)                       (push model + bench together)
 corpus in-session)
```

## Mode router

| Mode        | Triggered by                                                                   | Behavior |
|-------------|---------------------------------------------------------------------------------|----------|
| `dry`       | default first invocation; "dry-run", "5-row preview", "validate the prompt"     | Run `prepare_queue.py --rows 5`. Then Claude generates all 5 rows in one assistant turn via Edit-append. Report `<think>` presence rate + measured per-row output tokens. |
| `preflight` | "what's the budget impact", "show the pre-flight", "estimate the cost"           | Run `preflight_budget.py --rows N --avg-output-tok <from-dry>`. Optionally pipe in pasted `/usage`. Blocks for user confirm. |
| `live`      | "go ahead", "kick off the production corpus", "ship the patent training data"   | Run `prepare_queue.py --rows N` (idempotent on `--seed`). Then enter cursor-driven batch loop (below). Span multiple CC sessions to complete large N. Default 25-50 rows/batch sequential. |
| `fanout`    | "parallelize the corpus build", "fan out producers", "speed up the corpus", "use subagents" | Spawn N parallel `general-purpose` subagents (Agent tool, one assistant message with N tool calls) per the `references/producer-subagent-prompt.md` template. Each owns a disjoint queue slice → writes to its own `chunk_<lo>_<hi>.jsonl`. Orchestrator runs `verify_chunk.py` on each, semantic-eyeballs 1-2 rows/chunk, merges in row-order. ~32% token overhead, ~4× wall-time speedup. See "Fan-out mode" section below. |
| `goal`      | user explicitly invokes CC v2.1.139+ `/goal` for autonomous multi-turn corpus build | Provide the `/goal` template that wraps `fanout` and gates completion on `wc -l out.jsonl == N AND verify_chunk.py PASS`. See "Integration with /goal" in `references/producer-subagent-prompt.md`. |

**Never run `live` without a fresh `dry` + `preflight` in this same session.** The pre-flight is the safety belt — without measured tokens-per-row, the cap projection is guesswork.

## Every invocation — read these first

Two non-skippable preflights. If either fails, surface to the user and bail.

### 1. Patent-strategist spec must exist

```bash
test -r /home/nvidia/ainative-business.github.io/_SPECS/patent-strategist-v1.md || echo MISSING
```

The prompt template + family distribution come from spec §4 Layer 2 + §5.3 + §6.1. Do not run if the spec has moved without updating `references/corpus-recipe.md`.

### 2. Working directory must be carvable

```bash
RUN_DIR="/tmp/aifn-corpus-synth"
mkdir -p "$RUN_DIR"
```

If a prior run's queue / out / cursor files exist there, surface them — do not silently clobber. Either continue (live mode resume) or move the prior run aside.

## Inputs

Gather via `AskUserQuestion` if the user's invocation didn't supply:

| Field      | Examples                                            | Required        | Default                                              |
|------------|-----------------------------------------------------|-----------------|------------------------------------------------------|
| `rows`     | 5 / 50 / 1000 / 25000                                | yes             | 5 for dry, ask for live                              |
| `seed`     | 42                                                   | no              | 42 (idempotent → same queue across resumes)          |
| `output`   | `/home/nvidia/data/corpus/patent-prod-<date>.jsonl`  | yes for live    | `/home/nvidia/data/corpus/patent-prod-$(date -u +%Y-%m-%d).jsonl` |
| `cap_tier` | max5x / max20x / pro                                 | no              | `max20x` (per session memory)                        |

When the user invokes with `/claude-corpus-synth dry` or `/claude-corpus-synth live --rows 25000`, parse args — don't re-ask.

## `dry` mode — full workflow

1. Build the 5-row queue:

   ```bash
   python3 .claude/skills/claude-corpus-synth/scripts/prepare_queue.py \
     --rows 5 --seed 42 --output /tmp/aifn-corpus-synth/queue.jsonl
   ```

2. Read `/tmp/aifn-corpus-synth/queue.jsonl` (5 lines). For each row:
   - Read `references/corpus-recipe.md` once to confirm the prompt template / structure mandate.
   - In a single assistant turn, generate the response for that row obeying spec §4 Layer 2:
     ```
     <think>
     [step-by-step reasoning: identify the claim element or legal issue, cite the relevant
     MPEP section or statute, apply the rule, conclude]
     </think>
     [final answer in 1-3 sentences]
     ```
   - Append a JSONL line to `/tmp/aifn-corpus-synth/out.jsonl` via Edit (append-only):
     ```json
     {"row_idx": 0, "response": "<think>…</think>…"}
     ```

3. Report a 4-bullet summary to the user:
   - `<think>` presence rate (target: 1.0)
   - Avg response length in chars (use `len(response) // 4` as a token approximation if you don't have actual usage data)
   - Per-row preview (first 200 chars of each response)
   - Recommended `--avg-output-tok` for the pre-flight: round measured avg up to nearest 100

If `<think>` rate < 1.0, iterate on the prompt template in `references/corpus-recipe.md` before going to preflight.

## `preflight` mode — full workflow

```bash
python3 .claude/skills/claude-corpus-synth/scripts/preflight_budget.py \
  --rows <N> \
  --avg-output-tok <from-dry-run> \
  --cap-tier max20x
```

Optionally pipe pasted `/usage`:

```bash
cat <<'EOF' | python3 .../preflight_budget.py --rows 25000 --avg-output-tok 2000 --paste-usage -
Current week (resets Tuesday): 23%
EOF
```

The script prints projected session-tokens + Sonnet-hour equivalent + % of weekly cap + estimated session count + weekly cycles needed. **Then blocks for user confirmation** (interactive prompt; pass `--yes` to skip).

If the worst-case projection > 95% of one week's cap, the script refuses to auto-approve. The user can still override with `--yes` after understanding the consequence.

## `live` mode — cursor-driven batch loop

The 25k production target requires ~125 CC sessions of ~200 rows each. The skill state is just three files in `/tmp/aifn-corpus-synth/`:

- `queue.jsonl` — all N prompts (built once by `prepare_queue.py`)
- `out.jsonl` — one line per generated row, appended via Edit
- `cursor.txt` — single integer "next row_idx to process"

### Per-session workflow (each CC invocation)

1. **Build / verify the queue** (idempotent on seed):

   ```bash
   python3 .claude/skills/claude-corpus-synth/scripts/prepare_queue.py \
     --rows <N> --seed 42 --output /tmp/aifn-corpus-synth/queue.jsonl
   ```

   If queue.jsonl already exists with matching `--rows` + `--seed`, re-running is a no-op (identical bytes).

2. **Read the cursor:**

   ```bash
   cat /tmp/aifn-corpus-synth/cursor.txt 2>/dev/null || echo 0
   ```

3. **Pick this session's batch size B.** Default 200. Reduce to 50 if rows are unusually long (E2 MCQ rows can run small; A2 indefiniteness rows can balloon). Reduce further if the user's `/usage` is already > 70%.

4. **Read queue rows [cursor, cursor+B)** from queue.jsonl. For each row:
   - Generate the response per spec §4 Layer 2 (same template as dry mode).
   - Append `{"row_idx": idx, "response": "<think>…</think>…"}` to `out.jsonl` via Edit.
   - Track running progress; report every 25 rows.

5. **Advance the cursor:**

   ```bash
   echo $((CURSOR + B)) > /tmp/aifn-corpus-synth/cursor.txt
   ```

6. **Decide whether to continue this session:**
   - If context window is > 70% full → stop, advise user to `/clear` and re-invoke the skill in a fresh session.
   - If `cursor >= N` (queue exhausted) → run `merge_outputs.py` and emit the final corpus file.
   - Otherwise → user can ask for another batch in the same session.

## `fanout` mode — parallel producer subagents (validated session 34)

Use when the user asks to "parallelize", "speed up the corpus", "use subagents", or when the sequential path is too slow for a long-running build. **Empirical**: stage 1 (50-row chunk, 1 subagent) on 2026-05-18 produced clean output (50/50 `<think>`, 110 MPEP + 100 case cites, 2097 mean chars) in ~11 minutes — ~2× the per-row content density of single-session-orchestrator runs.

### Per-session workflow

1. **Verify state** (cursor + out.jsonl + queue) per `live` mode step 1-2.

2. **Pick chunk count N and chunk size S.** Each subagent should own 25-50 rows. For a 200-row session: 4-5 subagents × 50 rows. Reduce N if cap headroom < 50%.

3. **Plan slices.** For cursor=C, generate (LO, HI) tuples: (C, C+S-1), (C+S, C+2S-1), …, ending at C+N*S-1. Total rows banked this session = N*S.

4. **Spawn subagents in parallel.** In ONE assistant message, make N Agent tool calls. Each prompt is built from `references/producer-subagent-prompt.md` with `{LO}`/`{HI}`/`{OUTPUT_PATH}` substituted. The `OUTPUT_PATH` MUST be `/tmp/aifn-corpus-synth/chunk_<LO>_<HI>.jsonl`.

5. **As each subagent returns DONE**, run `verify_chunk.py`:

   ```bash
   python3 .claude/skills/claude-corpus-synth/scripts/verify_chunk.py \
     /tmp/aifn-corpus-synth/chunk_<LO>_<HI>.jsonl
   ```

   PASS → proceed to step 6. FAIL → re-spawn that subagent with explicit failure detail.

6. **Semantic eyeball.** Read 1-2 random rows per chunk; check for hallucinated MPEP subsection letters or invented case names. If a subsection is outside the verifier's whitelist (WARN), confirm it's real before merging.

7. **Merge in row-order**:

   ```bash
   for lo_hi in 100_149 150_199 200_249 250_299 300_324; do
     cat /tmp/aifn-corpus-synth/chunk_$lo_hi.jsonl >> /tmp/aifn-corpus-synth/out.jsonl
     mv /tmp/aifn-corpus-synth/chunk_$lo_hi.jsonl /tmp/aifn-corpus-synth/chunk_$lo_hi.merged.jsonl
   done
   echo NEW_HI+1 > /tmp/aifn-corpus-synth/cursor.txt
   ```

   Rename to `.merged.jsonl` so reruns don't double-count.

8. **Update HANDOFF** with banked row count + per-chunk stats.

### When NOT to fan out

- **First 50-100 rows of a fresh corpus** — orchestrator should hand-tune the template before parallel execution amplifies any defect.
- **Final 50-100 rows** — small speedup gain, sequential is fine.
- **Weekly cap > 70%** — ~32% fan-out overhead becomes risky; revert to sequential.

### Integration with `/goal` (CC v2.1.139+)

For autonomous multi-turn corpus build, combine fan-out with `/goal`:

```
/goal Generate the full <N>-row patent corpus by spawning parallel-subagent fan-out per the `claude-corpus-synth` skill's fanout mode (4 subagents × 25 rows per turn). Condition: `wc -l /tmp/aifn-corpus-synth/out.jsonl` equals <N> AND every line contains both `<think>` and `</think>` per a final pass of `verify_chunk.py` over the merged out.jsonl. Stop and surface to the user if any chunk fails `verify_chunk.py` twice in a row or if the user's weekly cap exceeds 80%.
```

Requires the workspace trust dialog to have been accepted (one-time pop-up on first workspace open — there is no `/trust` slash command). To confirm: run `/goal` with no argument; if it shows status, trust is accepted; if it errors with a hooks message, that's the gate. The judge model (Haiku by default) checks the condition between turns.

## Final consolidation (run once after queue exhausted)

```bash
python3 .claude/skills/claude-corpus-synth/scripts/merge_outputs.py \
  --queue /tmp/aifn-corpus-synth/queue.jsonl \
  --out   /tmp/aifn-corpus-synth/out.jsonl \
  --final /home/nvidia/data/corpus/patent-prod-$(date -u +%Y-%m-%d).jsonl
```

The merge script validates `<think>` presence per row, drops failures, reports per-family yield, writes the final consolidated JSONL.

## Output schema (final corpus, one row per JSONL line)

```json
{"row_idx": 0, "family": "A1", "prompt": "Draft a single independent claim …", "response": "<think>\\n…\\n</think>\\n…", "has_think": true}
```

Downstream `g3_train_first_lora.sh` reads only rows where `has_think == true` — the merge step already filters.

## DO NOT

- Do NOT import `anthropic`, `claude_agent_sdk`, or any other SDK that calls Claude programmatically. The user's policy is explicit: in-CC-session orchestration only. See `[[feedback_llm_skill_pattern]]`.
- Do NOT shell out to `python -c 'client.messages.create(…)'` or any equivalent escape hatch.
- Do NOT bypass the pre-flight gate. The 25k corpus is many weeks of cap consumption — the user must see the math before committing.
- Do NOT extend this skill to non-patent corpora without re-reading `_SPECS/patent-strategist-v1.md` §4. The prompt template + family templates are domain-specific. A new domain wants a sibling skill, not a flag.
- Do NOT skip the dry-run before preflight. Without measured tokens-per-row, the cap projection is guesswork.
- Do NOT continue generating in a session whose context is > 70% full. Stop, advise `/clear`, resume in a fresh session.

## Operational reality the user needs to see

At measured ~2000 output tok/row + overhead, 25k rows consumes ~36–73% of one weekly Max 20x cap. Realistic completion: 2–4 weekly cycles, ~125 separate CC sessions. The skill makes this visible upfront so the user can pick a sustainable scale: full 25k stretched over 4 weeks / reduce to 5k–10k / defer entirely / ship patent-strategist v1.0 as RAG-only (spec's documented Plan B).
