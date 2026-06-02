# Corpus recipe — claude-corpus-synth

Authoritative source for the production patent `<think>`-chain training corpus.

## Source of truth

`/home/nvidia/ainative-business.github.io/_SPECS/patent-strategist-v1.md`:

- **§4 Layer 2** — training-data structure mandate (`<think>chain</think>answer`, 100% of patent examples)
- **§5.3** — bench source allocation (Claude-seeded synthetic = Families A1-A4, E1-E2)
- **§6.1** — training-mix proportions (Claude-seeded synthetic = 10% of total, ~25k examples)

If those sections move or are renamed, update this file's pointers before re-running the skill.

## Family distribution (synthetic share)

| Family | Use case | Share | Approx rows @ 25k | Why synthetic (no public corpus) |
|---|---|---|---|---|
| **A1** | Claim drafting from invention disclosure | 30% | 7,500 | No public dataset of (disclosure → claim-1) pairs |
| **A2** | 112(b) indefiniteness analysis | 25% | 6,250 | USPTO 112 rejections exist but pairing them to original claims requires hand-curation |
| **A4** | Office-action traversal arguments | 20% | 5,000 | OARD has rejections but not the attorney response arguments in clean form |
| **E1** | Plain-English explanations of patent concepts | 15% | 3,750 | "Explain like I'm 7" content is rare in patent literature |
| **E2** | MCQ generation for paralegal training | 10% | 2,500 | Patent-MCQ datasets are exam-bank proprietary |

(`FAMILY_DIST` in `scripts/prepare_queue.py` mirrors these proportions.)

## Prompt template — spec §4 Layer 2

For EVERY queue row, Claude (in-CC-session) must emit exactly this structure:

```
<think>
[step-by-step reasoning: identify the claim element or legal issue, cite the
relevant MPEP section or statute, apply the rule, conclude]
</think>
[final answer in 1-3 sentences]
```

**The `<think>` block is mandatory.** Spec §4 Layer 2 forbids mixed-structure training (some `<think>`, some direct). The dry-run validation exists to catch any row that's emitting bare answers without the wrapper.

Other rules:
- Do not output anything before `<think>`.
- Do not output anything after the final answer (no closing remarks, no meta-commentary).
- The reasoning chain should be 200-2000 tokens depending on complexity.
- Cite specific MPEP sections (e.g. "MPEP 2173.05(b)") and statutes (e.g. "35 USC §112(b)") in A2/A4 rows — not vague references.
- The conclusion answers the question directly.

## Quality bar — what the dry-run should pass

The 5-row dry-run output should pass an eyeball check on:

1. **`<think>` block present** in every row.
2. **MPEP / statute citations** in A2/A4 chains (concrete section IDs, not vague).
3. **Conclusion answers the question** asked (1-3 sentences after `</think>`).
4. **No prompt-leakage** — the response shouldn't echo template substitutions verbatim.

If any of these fail, fix the prompt template (here, in this file) before going to preflight.

## Operational reality — 25k rows = many weeks of CC sessions

In-CC-session generation has a different cost shape than the API console route the original plan considered:

| Aspect | Number | Source |
|---|---|---|
| Avg output tokens/row | ~2000 | measured in earlier dry-run |
| Tool-call + cache-read overhead | ~800 tokens/row in-session | preflight_budget.py defaults |
| Total session tokens/row | ~2800 | sum |
| Rows per CC session before context fills | ~200 | empirical guideline (1M context / ~5K growing per-row footprint) |
| Sessions needed for 25k rows | ~125 | 25000 / 200 |
| Total Sonnet-equivalent hours | ~175 | 70M tokens / 400K tok/hr |
| % of one weekly Max 20x cap | 36–73% | 175 / (240..480) |
| Weekly cycles to complete | 2–4 | spread to stay under 50% per week |

**The user picks the scale** after seeing this math. Options:

- (a) Commit to a 2–4 week 25k corpus build — fully invest one or more weekly cycles.
- (b) Reduce N to 5k–10k — lower-risk LoRA train, lower-cap commitment.
- (c) Defer the production fine-tune to a later quarter — ship bench + RAG-only model first.
- (d) Ship patent-strategist v1.0 as RAG-only (Plan B documented in spec §4 fallback ladder) — no synthetic corpus needed.

## What this skill does NOT cover

- **Non-synthetic corpus rows** (MPEP, OARD, PatentMatch, BIGPATENT) — see `scripts/` in the main repo for the public-source ingestion pipeline. Those are 90% of the training mix; the Claude-seeded synthetic share is 10%.
- **Reasoning anchor mix-in** (spec §4 Layer 3: 10% AIME/MATH/GPQA) — those come from public benchmarks, not Claude. Separate ingestion path.
- **Bench Qs vs training rows** — the bench (`Orionfold/patent-strategist-bench-v0.1`) is hand-authored / Claude-seeded in an isolated session per R12 to prevent contamination. This skill is training-corpus only.

## Spice pool extension

The `SPICE` dict in `scripts/prepare_queue.py` is deliberately small (5 options per template variable). For a 25k row run that's fine — Claude's reasoning chain produces the diversity, not template combinatorics. To extend:

- Add invention domains to `A1.invention` (currently 5 — batteries, audio, CRISPR, photovoltaics, aircraft).
- Add poorly-drafted claims to `A2.draft_claim` (handcraft each to contain a recognizable 112(b) flaw).
- Add rejection / cited-reference / claim-subject triples to `A4` (the realism of the office-action traversal depends on triple coherence — don't randomly recombine).
- Add audience / concept pairs to `E1`.
- Add MPEP topics to `E2.mpep_topic`.

**Don't extend at scale.** 5×5×... combinations across 25k rows already produces ~600 unique prompt shells per family on the median; reasoning depth comes from Claude, not from the prompt corpus.
