---
name: grounded-eval-synth
description: Authors grounded-eval pack rows (operator-journey QA over a Cortex corpus pack) IN the Claude Code session itself — no API calls, no subprocess, no `anthropic` / `claude-agent-sdk` imports. Claude (the session model) curates deterministic miner candidates into journey-tagged eval rows via Edit-append, gated per batch by `scripts/grounded_eval/verify_pack.py`. Trigger when the user says "author grounded eval rows", "extend the cortex-grounded pack", "build the grounded eval pack", "add journey evals", "/grounded-eval-synth", or when grounded-eval-v1 Phase 1/4 needs more pack rows before freeze. Spec: `_SPECS/grounded-eval-v1.md` (journeys §2, row schema §4, generation pipeline §6). Do NOT trigger for the frozen advisor curveball benches (those are `scripts/orionfold_advisor/` territory), for retrieval-recall QA sets (`rag_eval_index`), or for SFT training corpora (`claude-corpus-synth`).
---

# grounded-eval-synth

Owns the *authoring surface* for grounded eval packs (`_SPECS/grounded-eval-v1.md` §6b). Sibling of `claude-corpus-synth` (training corpora) — same architecture rule, much smaller scale (a pack is ~60 rows, not 25k).

## Architecture rule — read first

**Claude authors rows IN this CC session via Edit-append. No subprocess. No SDK. No API.** Scripts are deterministic helpers only:

- `scripts/grounded_eval/mine_candidates.py` — journey-tagged candidate seeds from the corpus manifest (no LLM)
- `scripts/grounded_eval/verify_pack.py` — mechanical row gates + freeze stamp (no LLM)

If you catch yourself wanting to import `anthropic` / `claude_agent_sdk` or shell out to an external `claude` — stop. See `[[feedback_llm_skill_pattern]]`.

## Files

| File | Role |
|---|---|
| `evidence/grounded-eval/cortex-grounded-v0.1.draft.jsonl` | the draft pack (Edit-append target) |
| `evidence/grounded-eval/cortex-grounded-ext.jsonl` | living extension set (post-freeze rows land here) |
| `/tmp/grounded-eval/candidates.jsonl` | miner output (re-runnable scratch, untracked) |
| `evidence/orionfold-advisor/public-corpus-manifest.jsonl` | the corpus pack manifest (gold ids must exist here) |

v0.1 journey quotas (spec §3): `lookup` 15 · `howto` 12 · `synthesis` 12 · `troubleshoot` 12 · `refusal` 9 = 60.

## Mode router

| Mode | Triggered by | Behavior |
|---|---|---|
| `mine` | "refresh candidates", first invocation with no candidates file | Run the miner; report per-journey candidate counts. |
| `batch` (default) | "author N rows", "next batch" | The authoring loop below, default 10–15 rows/batch, balancing journey quotas. |
| `status` | "pack status" | Run `verify_pack.py` on the draft; report counts vs quotas + failures. |
| `freeze` | "freeze the pack" — **operator-gated, never autonomous** | Confirm operator review happened → `--apply-sft-tags` → rename `*.draft.jsonl` → `cortex-grounded-v0.1.jsonl` → `verify_pack.py --freeze`. After freeze, new rows go ONLY to `cortex-grounded-ext.jsonl`. |

## `batch` mode — the authoring loop

1. **Pick candidates** from `/tmp/grounded-eval/candidates.jsonl`, weighted toward the journey furthest below quota. Candidates are *seeds, not rows* — miner noise is expected (generic "what changes…" sentences, weak "no longer" superseded matches): skip freely, quality over yield.
2. **Read the gold source section** (the manifest row's `path_or_url`) around each candidate before writing — `key_facts` must be verbatim-verifiable in the gold body, and the `expected_answer` must be faithful to what the source actually says, not what you remember.
3. **Write rows via Edit-append** to the draft pack, one JSON line per row, schema per spec §4. Authoring bar:
   - **Operator voice, production-shaped.** Phrase as a real Spark operator would ask mid-work. NEVER echo the source title, never "according to…", never name the source. `troubleshoot` rows lead with the *symptom* ("I pkilled vLLM and 108 GB is still held"), not the topic.
   - **`key_facts` are the gate** — pick 1–3 facts that distinguish a grounded answer from a plausible hallucination (exact numbers, exact flags, the load-bearing noun). Add `alt` spellings for unicode variants (`8.5×`/`8.5x`).
   - **`synthesis` rows** name ≥2 `gold_source_ids` and set `require_all_citations` only when both sources are genuinely needed.
   - **`refusal` rows** split between out-of-corpus topics and superseded-content probes (record which in `notes`); empty gold ids, empty key_facts.
   - **`notes`** records provenance: the candidate `cid` + which section of the source the facts came from.
   - `task_id` = `cg-<journey>-NNNN`, zero-padded, next free ordinal per journey; `in_sft_corpus: null` (the validator computes it).
4. **Gate the batch**: `python3 scripts/grounded_eval/verify_pack.py <draft>` — fix or drop every FAIL in the same batch; never leave the draft failing.
5. **Report**: rows added per journey, quota progress, validator verdict.

## Freeze discipline (spec §9)

- Freeze **before** any Advisor v0.3 training (pre-registration; `[[feedback_preregister_next_ood_gate]]`).
- The pack must never be ingested into a retrieval corpus; the spec basename joins `EXCLUDED_SPEC_BASENAMES` at the next corpus build.
- Frozen rows are never edited — errata go to the next version (curveball 0082-erratum precedent).
- Human review is the gate: the operator reads the draft before `freeze` mode runs.
