# Producer subagent prompt template

Reference for the **fan-out mode** of `claude-corpus-synth` (added session 34, 2026-05-18, validated at chunk_100_149 stage-1 — 50/50 rows clean).

The orchestrator (you, the CC session model) spawns N parallel `general-purpose` subagents via the Agent tool, each owning a disjoint queue slice. Subagents write to chunk-specific files; orchestrator runs the deterministic verifier (`scripts/verify_chunk.py`) on each completed chunk and merges into `out.jsonl` in row-order.

## Token economics (session-34 measurement)

| Approach | Input ctx / subagent | Output / subagent | Total for 250 rows | Wall time |
|---|---|---|---|---|
| Sequential single-session | ~5k once | ~110k once | ~115k | ~25 min |
| Parallel 5-subagent fan-out | ~10k × 5 = ~50k | ~22k × 5 = ~110k | ~165k | ~6 min |

Parallel costs ~32% more tokens for ~4× wall-time speedup. Cap headroom is fine — 250 rows ≈ 3-4% of weekly Max 20x either way.

## Subagent prompt template

When invoking `Agent(subagent_type="general-purpose", ...)`, use the template below. Substitute `{LO}`, `{HI}`, and `{OUTPUT_PATH}` (typically `/tmp/aifn-corpus-synth/chunk_<LO>_<HI>.jsonl`).

```
You are a producer subagent in a parallel-fan-out patent-corpus generation pipeline. You generate training-corpus rows for a patent-strategist LoRA fine-tune. This is in-CC-session work — no SDK, no API, no subprocess to anthropic/claude.

## Your assigned slice

Read `/tmp/aifn-corpus-synth/queue.jsonl`. Generate responses for rows with `row_idx` {LO} through {HI} inclusive ({HI-LO+1} rows). Write output to `{OUTPUT_PATH}`.

Use Python with `json.dumps(..., ensure_ascii=False)` for output writing. Compose all responses as inline Python triple-quoted strings in a single helper script you write to `/tmp/aifn-corpus-synth/producer_{LO}_{HI}.py`, then run it via Bash. This pattern mirrors the orchestrator's prior helpers at `/tmp/aifn-corpus-synth/append_batch_*.py`.

## Mandatory output structure (spec §4 Layer 2 — patent-strategist-v1.md)

Every response MUST follow this exact structure:

    <think>
    [step-by-step reasoning: identify the claim element or legal issue, cite the relevant MPEP section or statute, apply the rule, conclude]
    </think>
    [final answer in 1-3 sentences, OR the format the prompt demands]

- `<think>` block mandatory on EVERY row. No bare answers.
- Nothing before `<think>`. Nothing after the final answer.
- `<think>` chain length: 200-500 tokens typical; A4 traversals may run longer.
- Cite specific MPEP sections and statutes for A2/A4 rows.

## ⚠️ Producer working-notes MUST NOT leak into `<think>`

The `<think>` block is **in-character reasoning a patent practitioner would write**. It is NOT a place for your pipeline metadata. The s40 patent-strategist v2 failure — documented in `articles/fine-tune-data-prep-decisions-on-spark/` — was caused by 56% of training rows leaking the producer's working notes into `<think>`. The trainer faithfully learned the leak.

Before writing each row, **strip ALL of the following from the `<think>` body** (the verifier will reject the chunk if any survive):

1. **Family designators as a prefix.** Never let `<think>` begin with `A1`, `A2`, `A4`, `E1`, `E2`, optionally followed by a space, colon, period, or the words `duplicate` / `spice`. The family is your assignment, not the patent practitioner's first thought.
2. **`duplicate of N` annotations.** If the prompt is a duplicate in your slice, handle the de-duplication framing internally — never write the phrase `duplicate of <number>` into `<think>`.
3. **`diversify by …` instructions.** Diversification angles are your routing logic. The output reads as if a single practitioner thought through the problem. No meta-instruction phrasing.
4. **Anything that reads like producer state** — spice-combinator notes, queue-position references, sibling-row callouts, "this is the second framing of …", etc.
5. **`R<digits>` row references AND `For R<digits>` framings.** Never write `"R105 hit the MBA-audience framing"` or `"For R120 the paralegal audience can handle …"` or `"R5, R29, R47 have already covered …"`. The integer-suffixed `R`-tag is producer routing telemetry — the patent practitioner has no R-numbers in their head. The verifier rejects any `\bR\d{2,4}\b` token in the `<think>` body.

If your draft `<think>` begins with `"A2 duplicate of 1287. Diversify by emphasizing the §103 angle. The claim recites …"` — rewrite it as `"The claim recites a problematic term: …"` before serialization. The substance moves; the meta vanishes.

Self-check before writing each row: would a working patent attorney recognize this `<think>` as their own scratch reasoning? If no, rewrite.

## Anti-hallucination whitelist

**MPEP sections — only cite real ones.** Known-real (non-exhaustive): 201.08, 608.01(m), 608.01(n), 608.01(p), 609, 706, 706.07(f), 715, 715.07, 803, 1207, 1207.02, 1207.03, 1209, 2106, 2106.04(a), 2112, 2131, 2141, 2141.01(a), 2164, 2173.02 (and (II)/(III)), 2173.05 and subsections (b), (c), (d), (g), (h), (o), 2173.06(II), 2181. **Do NOT invent subsection letters** (e.g., 2173.05(q) does not exist). If unsure, shift the framing.

**Cases — only cite real ones.** Anchor list (use freely): Nautilus v. Biosig (2014); Williamson v. Citrix (Fed. Cir. 2015 en banc); Aristocrat Tech v. IGT (Fed. Cir. 2008); In re Donaldson (Fed. Cir. 1994 en banc); Halliburton v. M-I (Fed. Cir. 2008); Phillips v. AWH (Fed. Cir. 2005 en banc); Festo (2002); Graver Tank v. Linde (1950); KSR v. Teleflex (2007); Alice v. CLS Bank (2014); Mayo v. Prometheus (2012); Bilski v. Kappos (2010); In re Klein (Fed. Cir. 2011); In re Robertson (Fed. Cir. 1999); Datamize v. Plumtree (Fed. Cir. 2005); Solomon v. Kimberly-Clark (Fed. Cir. 2000); Interval Licensing v. AOL (Fed. Cir. 2014); Pall Corp v. Micron Separations (Fed. Cir. 1995); Continental Can v. Monsanto (Fed. Cir. 1991); Therasense v. Becton Dickinson (Fed. Cir. 2011); In re Swinehart (CCPA 1971); Seattle Box v. Industrial Crating (Fed. Cir. 1984); Welker Bearing v. PHD (Fed. Cir. 2008); Verve v. Crane Cams (Fed. Cir. 2002); Allen Engineering v. Bartell Industries (Fed. Cir. 2002); In re Dossel (Fed. Cir. 1997); Personalized Media v. ITC (Fed. Cir. 1998); W.L. Gore v. Garlock (Fed. Cir. 1983); Energizer Holdings v. ITC (Fed. Cir. 2006); Idenix Pharms v. Gilead (Fed. Cir. 2019); Electric Power Group v. Alstom (Fed. Cir. 2016); Graham v. John Deere (1966); Eiselstein v. Frank (Fed. Cir. 1995); In re Comiskey (Fed. Cir. 2009). Other well-known cases OK — never invent a name or citation.

**Statutes**: 35 USC §§101, 102 (a/b), 103, 112 (a/b/f), 121, 282; 37 CFR 1.56, 1.97, 1.98, 1.114, 1.116, 1.131, 1.132, 1.143, 1.144, 1.181, 1.321(c), 41.31, 41.37, 41.39.

## Duplicate prompts

The queue contains intentional duplicate prompts. When a duplicate appears in your slice, produce a meaningfully distinct framing — different headline case, different MPEP subsection emphasis, or a different practical angle (Markman construction, amendment strategy, examiner-applicant ping-pong, prosecution-history estoppel). The corpus already has 100+ rows of prior framings — diversity is essential. If a prompt appears more than once within YOUR slice, the two framings must be distinct.

## Family-specific guidance

- **A1 (claim drafting)**: numbered claim with "comprising" + 3-5 elements. Honor the constraint flavor (system-vs-method, structural-only, non-obvious narrowing, §101 Alice step 2, §112(f) avoidance).
- **A2 (§112(b) indefiniteness)**: identify problematic phrases, cite MPEP + caselaw, explain scope-uncertainty. 1-3 sentence answer.
- **A4 (office-action traversal)**: 2 paragraphs. ¶1 attacks the rejection (anticipation under MPEP 2131 / In re Robertson; obviousness under KSR / Graham). ¶2 preempts alternative grounds (non-analogous art under MPEP 2141.01(a) / In re Klein; inherent anticipation under MPEP 2112 / Continental Can v. Monsanto). **Spice combinators**: some A4 prompts have mismatched fact patterns — traverse via procedural-error attack + non-analogous-art fallback.
- **E1 (plain explanation)**: 2-4 short sentences as prompt specifies. No case citations except for "paralegal" audience.
- **E2 (MCQ)**: 4 options + answer key + one-sentence rationale.

## Self-verification (MANDATORY before reporting done)

After writing your chunk file, run:

    python3 -c "
    import json, re
    with open('{OUTPUT_PATH}') as f:
        rows = [json.loads(l) for l in f]
    assert len(rows) == {HI-LO+1}, f'row count {len(rows)}'
    assert [r['row_idx'] for r in rows] == list(range({LO}, {HI+1})), 'row_idx order'
    assert all('<think>' in r['response'] and '</think>' in r['response'] for r in rows), 'think tag'
    chars = [len(r['response']) for r in rows]
    assert min(chars) > 400, f'short row: {min(chars)} chars'
    print('PASS')
    "

## Final report format

    DONE chunk_{LO}_{HI}
    - Output: {OUTPUT_PATH}
    - Lines: {HI-LO+1}
    - <think> rate: 100%
    - Mean chars: <N>
    - MPEP cites: <N> total
    - Case cites: <N> total
    - Notable: <1-2 sentence — duplicate-prompt diversity moves, spice traversals, anything unusual>

If blocked:

    BLOCKED chunk_{LO}_{HI}
    <one-paragraph description>

DO NOT modify `/tmp/aifn-corpus-synth/out.jsonl` or `cursor.txt` — the orchestrator handles those.
```

## Orchestrator-side responsibilities

After spawning N subagents in parallel (use Agent in one assistant message with N tool calls):

1. **Receive each subagent's DONE/BLOCKED report.**
2. **Run `scripts/verify_chunk.py <chunk_path>`** on each chunk file.
3. **Semantic eyeball**: read 1-2 random rows per chunk; check for hallucinated MPEP subsection letters or invented case names.
4. **Merge in row-order**: `cat chunk_LO_HI.jsonl >> /tmp/aifn-corpus-synth/out.jsonl` for each chunk, sorted by LO.
5. **Advance cursor**: `echo NEW_HI+1 > /tmp/aifn-corpus-synth/cursor.txt`.
6. **Rename merged chunk files**: `mv chunk_LO_HI.jsonl chunk_LO_HI.merged.jsonl` so reruns don't double-count.

## Failure-mode handling

| Failure | Recovery |
|---|---|
| Subagent returns BLOCKED | Re-spawn with a revised prompt explaining the block. Do not merge partial output. |
| `verify_chunk.py` reports < 100% `<think>` | Re-spawn the subagent with explicit failure detail. Do not merge until clean. |
| `verify_chunk.py` reports short rows | Re-spawn with note: "rows N, M had only X chars — chains too brief, extend reasoning to 200+ tokens." |
| Semantic eyeball catches fake MPEP/case | Re-spawn with explicit anti-hallucination reinforcement, and add the fabricated cite to a "previously hallucinated, avoid" list. |
| Two consecutive failures on same chunk | Pause that chunk, surface to user with the failing output for inspection. |

## When NOT to fan out

- **Initial 50-100 rows of a new corpus**: do these in single-session so the orchestrator can hand-tune the prompt template + verify quality before parallel execution amplifies any defect.
- **Final 50-100 rows of a corpus**: lower-stakes, smaller speedup gain — sequential is fine.
- **When weekly cap is > 70%**: fan-out's ~32% overhead becomes risky; revert to sequential.

## Integration with `/goal` (CC v2.1.139+)

For autonomous multi-turn corpus build: combine fan-out with `/goal`:

    /goal Generate the full 5000-row patent corpus by spawning parallel-subagent fan-out (100 rows per turn, 4 subagents × 25 rows each) until queue exhausted. Condition: wc -l /tmp/aifn-corpus-synth/out.jsonl == 5000 AND no row missing <think>...</think> per `scripts/verify_chunk.py /tmp/aifn-corpus-synth/out.jsonl`. Stop and surface to user if any chunk fails verify twice in a row.

The judge model (Haiku by default) checks the condition between turns; CC continues across many turns until the condition is met.
