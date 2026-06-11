# Grounded Eval v1 — operator-journey evals for Cortex-grounded Advisor chat

- **Status:** ACTIVE (2026-06-11)
- **Owner surface:** `fieldkit.arena` (benches + chat/compare eval mode) + `scripts/grounded_eval/` + `.claude/skills/grounded-eval-synth/`
- **Decided with operator (2026-06-11):** hybrid generation (deterministic mining + session-model authoring + Arena re-validation); single-turn v1 with multi-turn deferred to v1.1; deterministic gate with judge advisory; frozen pack + living extension set; same-lane ±Cortex ablation duel as a v1 feature; reuse `eval_scores` + bench files — **no arena.db schema change**.

## 1. Why this layer exists (and what it is NOT)

Three eval layers already exist; none measures the live grounded loop:

| Layer | What it measures | What it can't see |
|---|---|---|
| Advisor benches (heldout/curveballs) | model behavior on **frozen packet replays** (`packet_files`) | retrieval drift, embedder regressions, corpus-pack changes |
| `rag_eval_runs` / `rag_eval_index` | **retrieval-only** recall@k against the index | the generated answer, citations, refusals |
| Interactive `eval_scores` / compare rubrics | per-turn grades on the above | n/a (consumes the above) |

**Grounded Eval is the missing middle**: live query → pgvector (`advisor_corpus_v01`) → `cortex_chat.build_packet()` → answer → citations, scored as one unit and organized around operator journeys. A grounded score moves when *any* of {model, corpus pack, embedder, chunking, packet contract} moves — that is the point. It never replaces the frozen packet benches (model-only gates) and never conflates with them.

## 2. Operator journeys (the unit of coverage)

Journeys are corpus-agnostic archetypes; each row carries a `journey` tag. v1 ships J1–J4 + J6 (single-turn); J5 is v1.1.

| Tag | Journey | Exercises | Failure mode it catches |
|---|---|---|---|
| `lookup` (J1) | Single-fact lookup ("what tok/s did Q8_0 get on the legal curator?") | exact retrieval + precise extraction | wrong source, fact paraphrased wrong, number drift |
| `howto` (J2) | Runbook how-to ("how do I bring up NIM locally?") | single-source procedure fidelity | step invention, wrong flags, merged procedures |
| `synthesis` (J3) | Cross-article synthesis ("NeMo vs Unsloth — which, when?") | multi-source retrieval + reconciliation | one-sided answers, citing one of two needed sources |
| `troubleshoot` (J4) | Symptom→fix ("I pkilled vLLM and 108 GB is still held") | retrieval by symptom, not topic words | retrieval miss when query vocabulary ≠ article vocabulary |
| `research` (J5, **v1.1**) | Multi-turn drill-down scripts | per-turn retrieval under conversation carry | context bleed, stale retrieval on follow-ups |
| `refusal` (J6) | Out-of-corpus / superseded-content honesty | corpus-boundary refusal (`Citations: []`) | fabrication beyond corpus; answering from superseded sources |

J6 extends the refusal floor from private-state pretexts (curveball territory) to **corpus-boundary** honesty — a distinct refusal class; rows must not duplicate curveball families.

## 3. Pack artifacts & naming

Everything lives in `evidence/grounded-eval/` (tracked; root resolution mirrors the advisor bench: `root_env="FK_ARENA_GROUNDED_DIR"`, `root_fallback="evidence/grounded-eval"`).

- **`cortex-grounded-v0.1.jsonl`** — the **frozen gate**. Once frozen: sha12 recorded here and in the validator receipt; rows never edited (errata via a successor version, per the 0082-erratum precedent).
- **`cortex-grounded-ext.jsonl`** — the **living extension set**. New rows land here as articles ship; periodically graduates (operator-reviewed) into the next frozen version (v0.2, …). Extension scores are advisory, never gate.
- **`cortex-grounded-v0.1.receipt.json`** — validator output: sha12, per-journey counts, in-SFT overlap stats, validation timestamp.
- Draft stage: `cortex-grounded-v0.1.draft.jsonl` until operator review promotes it (rename = freeze, sha12 stamped).

**v0.1 target:** 60 rows — `lookup` 15 · `howto` 12 · `synthesis` 12 · `troubleshoot` 12 · `refusal` 9. Pilot batch (this session) ≥18 across all five journeys; remaining rows authored via the skill in later sessions before freeze.

## 4. Row schema

Extends the curveball row shape (`evidence/orionfold-advisor/advisor-curveball-v0.2.jsonl`) so loaders/scorers stay one family. JSONL, one row per question:

```json
{
  "task_id": "cg-lookup-0001",
  "version": "v0.1",
  "journey": "lookup",
  "question": "operator-voice question, hint-free, no article-title echo",
  "expected_behavior": "answer",            // answer | refuse
  "gold_source_ids": ["article_..."],        // retrieval gate: ≥1 must appear in the live top-k receipt
  "accepted_citation_ids": ["article_..."],  // citation gate: any-of passes; synthesis rows may set require_all
  "require_all_citations": false,             // synthesis rows: every accepted id must be cited
  "key_facts": [                              // deterministic answer gate (all must pass)
    {"kind": "contains", "value": "108 GB", "alt": ["108GB"]},
    {"kind": "regex", "value": "pkill -f ['\"]?vllm\\|EngineCore"}
  ],
  "expected_answer": "1-3 sentence gold for display + judge reference",
  "in_sft_corpus": null,                      // filled by verify_pack.py from the SFT corpus manifest when present
  "notes": "authoring provenance: which miner candidate / article section"
}
```

Rules:

- `refusal` rows: `expected_behavior: "refuse"`, `gold_source_ids: []`, `key_facts: []`. Two sub-kinds, recorded in `notes`: *out-of-corpus* (no source covers it) and *superseded* (only a superseded/retired claim exists — correct behavior is refusal or an explicit "this changed" grounded in the current source; v1 scores these as refuse-or-cite-current via `accepted_citation_ids`).
- `key_facts.kind` ∈ {`contains` (case-insensitive substring, with `alt` synonyms — any-of within one fact), `regex`, `numeric` (`value` + `rel_tol`, first-number match within tolerance)}.
- Questions are **production-shaped**: no evaluator hints, no "according to article X", no source-title echo (the curveball discipline).
- Every non-refusal row's `key_facts` must be verifiable verbatim against the gold source body — the validator enforces this mechanically for `contains`/`numeric` kinds.

## 5. Scoring — `grounded_contract`

One deterministic scorer kind, four components; **pass = all gates pass** (binary, like `advisor_contract`), components surfaced individually in `why`:

1. **retrieval_hit** — ≥1 of `gold_source_ids` present in the live retrieval receipt's deduped top-k (`refusal` rows skip). *This is the component frozen-packet benches structurally cannot measure.*
2. **citation_integrity** — exact `Citations: [...]` line present; cited ids ⊆ retrieved packet ids; any-of `accepted_citation_ids` cited (all-of when `require_all_citations`); refusal rows require empty citations + refusal wording (reuse `_ADVISOR_REFUSAL_WORDS`).
3. **key_facts** — all facts pass against the answer channel (think-stripped).
4. **contract hygiene** — no `<think>` leak; private-state risk scan on refusal rows (reuse advisor mirrors).

**Judge advisory (non-gating):** optional groundedness/faithfulness grade via the existing judge backends, stored as a *separate* `eval_scores` row (`scorer_kind: judge_groundedness`) — never folded into the gate number. Report = reality: the leaderboard tier shows the deterministic gate; judge columns are clearly advisory.

Receipt plumbing (no schema change): the chat-stream handler builds the live packet, so it computes `retrieval_hit` at stream time and stashes the retrieval receipt in an in-memory `turn_id → receipt` map consumed by `POST /api/chat/score`; the offline runner (§7) scores everything in-process. If the in-memory receipt is gone (restart), the score degrades honestly: `retrieval_hit: unknown`, gate scored on components 2–4 with `why` flagging the missing component — never silently passes.

## 6. Generation pipeline (hybrid, per `feedback_llm_skill_pattern`)

**(a) Deterministic mining — `scripts/grounded_eval/mine_candidates.py`.** Pure transforms over the corpus manifest + article bodies; no LLM. Emits journey-tagged *candidates* (JSONL to `/tmp/grounded-eval/candidates.jsonl`; re-runnable, untracked):

- `lookup` seeds: sentences carrying measurement-shaped claims (numbers + units: tok/s, GB, %, ×-speedups, counts) with surrounding context.
- `howto` seeds: fenced command blocks + their preceding prose, per source.
- `troubleshoot` seeds: gotcha-shaped sentences (markers: "trap", "gotcha", "symptom", "fails", "breaks", "crash", "wedge", "landmine", "orphan", negative-result phrasing).
- `synthesis` seeds: source pairs sharing ≥2 frontmatter tags or comparison vocabulary ("vs", "bakeoff", "compared"), with both excerpts.
- `refusal` seeds: superseded/retired markers ("SUPERSEDED", "retired", "historical") + a topic list the corpus does NOT cover (derived: high-frequency AI terms absent from the corpus vocabulary).

**(b) Session-model authoring — `.claude/skills/grounded-eval-synth/SKILL.md`.** The session model (Claude in CC) turns candidates into rows via Edit-append, cursor-driven batches (claude-corpus-synth pattern). BANNED: `anthropic`, `claude-agent-sdk`, any LLM call from scripts. The skill's per-batch loop: pick candidates → read the gold source section → write row → run `verify_pack.py` → fix or drop failures.

**(c) Deterministic validation — `scripts/grounded_eval/verify_pack.py`.** Gates (all mechanical):

- schema + task_id uniqueness + journey enum + quota report;
- every `gold_source_ids` / `accepted_citation_ids` exists in the corpus manifest;
- `contains`/`numeric` key_facts verbatim-verifiable in a gold source body; `regex` compiles;
- refusal rows: empty gold ids, no key_facts;
- question hygiene: no source-title echo (≥4-token overlap with gold title), no "according to", length bounds;
- near-dup scan (normalized-token Jaccard across rows);
- `in_sft_corpus` computed from the SFT corpus source list when available;
- on `--freeze`: sha12 over the pack bytes → receipt JSON.

**(d) Arena re-validation (Phase 4).** Generation stays a skill; *regression detection* is Arena's job: the offline runner (§7) replays the frozen pack against the live stack on demand (and later as a job), writing per-run receipts. The existing `leaderboard_baseline` regression pattern applies to the grounded tier.

## 7. Offline runner — the canonical receipt

`scripts/grounded_eval/run_pack.py` (deterministic; sibling of `preflight.py`): for each row → `cortex_chat.build_packet(question)` live → chat against the selected lane (`--base-url`, default the resident `:8091`) → `grounded_contract` score → `results/<run>/results.jsonl` + summary (pass rate overall + per journey + per component). Supports `--no-retrieval` (question sent with the same system contract but no context blocks) to produce the **grounding-lift** pair from the same run harness. Receipts under `evidence/grounded-eval/results/` are the publish evidence; interactive cockpit grades are a convenience, never the receipt (advisor precedent).

## 8. Arena surfacing — distinct from model-only evals

- **Bench registration:** `BenchSpec(bench_id="cortex-grounded", vertical="advisor", fmt="grounded", live_retrieval=True, …)` — `live_retrieval` is the new flag meaning *no packet_files; eval mode must build the packet via `cortex_chat.build_packet()` at send time and force `retrieval: true`*. Cortex down → hard error (never an ungrounded turn scored as grounded).
- **Eval drawer:** grounded bench rows render under a **Grounded** group with journey chips; selecting one forces the Cortex toggle ON and shows **gold-source chips beside the live retrieval chips** so a retrieval miss is visible before scoring.
- **Ablation duel (compare):** per-side `retrieval` flag (`retrieval_a`/`retrieval_b`) so the same lane can run Cortex-ON vs Cortex-OFF on one question. Per-question grounding lift = on-score − off-score; corpus-level lift aggregates on the leaderboard tier. (Plumbing note: today `retrieval` is per-run on chat only; compare gains per-side flags.)
- **Leaderboard tier:** grounded scores land in `eval_scores` under `bench_id="cortex-grounded"`; the display layer renders a separate **"Grounded (live Cortex)"** group via the `advisorBenchDisplay` pattern — friendly head, journey breakdown, grounding-lift column, manifest sha pill (`⛁ advisor_corpus_v01 · <sha12>`). Grounded and frozen-packet numbers never share a rollup.
- **Contextual surfacing (stretch, v1.1):** nearest-neighbor the operator's free-chat question against pack rows; offer "score this against cg-…".

## 9. Contamination & freeze discipline (non-negotiable)

1. **Pack out of its own corpus:** `evidence/grounded-eval/` must never be ingested into any retrieval corpus. `generate.py`-class corpus builders must exclude it (extend the exclusion mechanism at the next corpus rebuild; re-run ALL gates after any rebuild per `feedback_proof_control_specs_out_of_eval_corpus`). **This spec file** (`grounded-eval-v1.md`) is proof-control: add to `EXCLUDED_SPEC_BASENAMES` at the next corpus build.
2. **Pre-registration:** freeze `cortex-grounded-v0.1` (sha12) **before** any Advisor v0.3 training (sibling of the curveball-v0.3 freeze in Open Items). Training on failure classes of a frozen bench makes the *successor* the gate — same ladder as curveballs.
3. **Overlap honesty:** `in_sft_corpus` per row; the leaderboard journey breakdown can split in-SFT vs out-of-SFT so near-distribution rows never inflate the OOD read.
4. **Human review gate:** drafts → operator review → freeze. Solo-blog discipline; no auto-freeze.

## 10. Generalization — the Cortex eval-pack contract

v1 hardcodes the Advisor pack (`advisor_corpus_v01` + its manifest) but every interface is parameterized for the customer story (*bring your docs → ingest → eval pack → grounded leaderboard over your corpus*):

- A **pack** = corpus manifest (existing jsonl schema) + eval rows (§4 schema, corpus-generic) + receipt. Nothing in the row schema names field-notes concepts; journeys are archetypes.
- Miner/validator/runner take `--manifest` / `--table` / `--pack` args (defaults = Advisor pack) — a second corpus is a config change, not new code.
- Promotion rule (`feedback_keep_scorer_local_until_reuse`): the scorer lands in `fieldkit.arena.benches` now; a `fieldkit.cortex`-level pack abstraction is cut only when a **second real corpus** exercises it.

## 11. Phases

| Phase | Scope | Gate |
|---|---|---|
| **1** (this session) | spec; miner; validator; skill; pilot batch (≥18 rows, all 5 journeys) as `.draft` | verify_pack green on the draft |
| **2** | `fieldkit.arena`: BenchSpec + `fmt="grounded"` loader + `grounded_contract` scorer + live-packet chat eval mode + receipt map; tests | arena suite green |
| **3** | UI: Grounded drawer group, gold-vs-actual chips, per-side retrieval in compare (ablation duel); rebake + CDP smoke per pinned discipline | live browser smoke |
| **4** | offline runner + grounding-lift rollup + leaderboard tier display; complete pack to 60; operator review → **freeze v0.1** | frozen sha12 + first full receipt |
| **v1.1** | J5 multi-turn scripts + runner; Arena synth/re-validation job kind; contextual surfacing; extension-set graduation to v0.2 | — |

## 12. Out of scope (v1)

- arena.db schema changes (receipt map is in-memory; canonical receipts are files).
- Multi-turn J5 (v1.1), Arena-native generation jobs (v1.1).
- Judge scores in the gate (advisory only).
- Re-ranking / retrieval-parameter sweeps (that's `rag_eval_index` territory).
