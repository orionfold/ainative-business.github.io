# Plan: patent-strategist v4 on the NeMo stack — fix hallucinations + spaceless-think

> Status: **SUPERSEDED 2026-05-24 by the unpublish-Unsloth pivot** (see the S1 block below).
> The v4 NeMo retrain arc (S2–S6) did NOT execute: S1 showed the spaceless defect is
> Unsloth-lane-only and the already-published nemo lane is spacing-clean, so the user pivoted to
> **unpublishing the Unsloth artifacts** instead of retraining. The corpus MPEP-hallucination
> fix (S2) remains an open, lower-priority follow-up — it lives in the nemo lane too, currently
> shipped as bounded `known_drift` on the cards. This file is retained as the strategy + S1
> diagnostic record. Living doc per `feedback_ideas_docs_living`.

> ## S1 EXECUTION UPDATE — 2026-05-24 (spaceless root-cause: RESOLVED for the nemo flagship)
>
> **Verdict: the spaceless-`<think>` defect is UNSLOTH-LANE-SPECIFIC. The nemo lane is already clean.**
> Derived deterministically (no GPU) by applying the current `think_space_ratio` metric to the real
> 20-q generations captured during the 2026-05-21 bakeoff, correcting two of them for a capture-time
> `Ġ`/`Ċ` byte-level-BPE decode leak (literal `Ġ` left in `response` → `count(" ")`=0 spuriously):
>
> | Model | Lane | true `think_space_ratio` (de-BPE) | Verdict |
> |---|---|---|---|
> | `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` | base | **0.158** | spaced ✓ |
> | v3-**unsloth** merged BF16 (`…/patent-strategist-v3-2026-05-21/merged-bf16`) | unsloth | **~0.0002** | **spaceless ✗** |
> | v3-**nemo** merged BF16 (`…/p65-nemo/merged-hf-bf16`) | nemo | **0.163** | spaced ✓ |
>
> - **Hypothesis (a) base-inherited = FALSE** — the base produces healthy spaced reasoning (0.158).
> - **Hypothesis (b) FT-introduced = TRUE, but only in the unsloth lane** — the nemo lane used the
>   *identical* recipe (q/k/v/o, r=16, α=32, ~625 steps) on the *identical* corpus and is spaced (0.163).
>   So it is NOT a recipe-capacity problem; it is an Unsloth-lane training artifact.
> - **Why the user saw it:** the patent-strategist user notebook serves `Orionfold/patent-strategist-v3-unsloth-GGUF`
>   (`user.py:20`, manifest `stack_origin: unsloth`) — the spaceless lane. The 05-23 memory diagnosis was
>   also run against the unsloth GGUF; "HF agrees" there meant the HF *tokenizer* decoding the GGUF-generated
>   IDs, not an independent HF-model generation run.
> - **Consequence for v4:** the spaceless half of this plan is moot for the NeMo flagship. **S4b
>   (base-switch) and the risky MLP-expansion recipe (spec §4 reasoning-collapse risk) are NOT needed for
>   spacing.** The only remaining v4-justifying defect is the **corpus MPEP hallucination** (Issue 1) — which
>   IS lane-independent (the nemo v3 model carries it too).
>
> **PIVOT (2026-05-24, user-directed): unpublish the Unsloth lane instead of retraining.** Since the
> spaceless defect is Unsloth-only and the nemo lane already ships spacing-clean, the user chose to:
> 1. **Delete** `Orionfold/patent-strategist-v3-unsloth{,-GGUF}` from HF (done — irreversible).
> 2. **Repoint** the patent-strategist notebooks (builder+user `.py`/`.ipynb` + `patent-strategist-notebooks.yaml`)
>    to the nemo lane; user notebook pins **Q5_K_M** (10.04 ppl @ 35 tok/s — the fast+accurate knee).
> 3. **Remove** the two unsloth website artifact cards (`src/content/artifacts/patent-strategist-v3-unsloth{,-gguf}.yaml`).
> 4. **Strip** unsloth repo links from the bakeoff article + the surviving nemo HF cards
>    (`republish_patent_strategist_readmes.py` SIBLINGS now nemo-only; cards re-pushed).
> The Unsloth lane stays in the article/decide-entry/notebook prose as the measured **comparison baseline**,
> just not as a downloadable artifact. **Follow-ups:** (a) corpus MPEP-hallucination fix (S2) — still
> shipped as bounded drift (OPEN); (b) ✅ DONE (`c04326c`) — regenerated `notebooks/patent-strategist/exports/`
> PNGs for the nemo lane (green `#76B900`, ppl 10.24→9.93, 35 tok/s) via `notebook-snapshot`.
> Memory `reference_r1_qwen3_gguf_detok_spaces` corrected: the defect is unsloth-specific, NOT inherent to
> the R1-Qwen3 base or the light LoRA recipe.

## Context

The patent-strategist v3 release (DeepSeek-R1-0528-Qwen3-8B base, shipped 2026-05-22 as the
paired Unsloth-vs-NeMo bakeoff) carries two known defects that keep it an honest research
preview rather than a usable model. Both are documented in the repo history. This plan turns
them into a single corrective release — **patent-strategist-v4-nemo** — built end-to-end on
the NVIDIA NeMo / Megatron-Bridge stack (the strategic-default train layer per
`ideas/uber-local-corpus-gen-decision.md`).

### The two defects (verified against the codebase, not assumed)

**1. Hallucinated MPEP content baked into the synthetic corpus.** Two corpus-generator
artifacts learned equally by both backends:
- `"metes-and-times"` where the standard claim-construction term is *metes-and-bounds*.
- A fabricated `MPEP §2163.05(s)` citation — real §2163.05 has only subsections (a)–(f).

Evidence: `articles/patent-strategist-bakeoff-unsloth-vs-nemo-framework/article.md:254-256`
and the captured probe `probes/rerun/p-p-strat-01-rerun.json`. The article names the remedy
itself: *"A v4 corpus generation with a fact-check pass is the next iteration."* The
**HF-card presentation** problem (drift above-the-fold) is **already fixed** — bounded
`known_drift` rendered below Methods via `scripts/republish_patent_strategist_readmes.py` +
`_GUIDES/NARRATIVE-CONTRACT.md` Rules 1–2. What remains is the **content** fix: the model still emits
the fabricated cites because they're in its weights. `claude-corpus-synth`'s `verify_chunk.py`
gates catch meta-state leakage but have **no MPEP-grounding check** — that gap is why the
artifacts shipped.

**2. Spaceless-think generation.** v3 emits no-space tokens inside `<think>`
("Okay,let'stackle" instead of "Okay, let's tackle"). Re-diagnosed 2026-05-23
(`memory/reference_r1_qwen3_gguf_detok_spaces.md`): **NOT** a detokenizer or data/prep bug —
corpus (`response` ~14% spaces), trainer-input (838 spaces/row), and both tokenizers all
round-trip cleanly. The model **argmaxes the no-`Ġ` token variants** → a *learned-weights*
behavior. Two open hypotheses: **(a)** inherited from the base's think-mode prior, or **(b)**
under-corrected because the v3 LoRA is attention-only (`q/k/v/o`, r=16, ~625 steps) — too
light to overwrite a base generation-style prior. Disambiguating needs a base-model
generation run (GPU). Detection guard already exists: `scripts/probe_reasoning.py` warns when
`think_space_ratio < 0.08` (`MIN_THINK_SPACE_RATIO`, line 69).

Both lanes used an **identical** recipe (`r=16, α=32, targets=q/k/v/o, lr=1e-4 cosine,
625 iters`), so the nemo lane almost certainly exhibits the spaceless behavior too — the v3
diagnosis only tested `Orionfold/patent-strategist-v3-unsloth-GGUF`. Confirming the nemo lane
is part of the diagnostic.

## Decisions locked with the user (do not relitigate)

1. **Corpus fix = scrub + verify gate.** Fact-check/repair the existing `v3_full_5000.jsonl`
   (fix the two known artifacts, scan all 5000 rows for other fabricated MPEP cites against a
   real-section allowlist) **and** add an MPEP-grounding gate to
   `claude-corpus-synth/verify_chunk.py` so future rows can't fabricate cites. No full NeMo
   data-layer regen now (logged as a later vertical-curator cycle).
2. **Spaceless fix = open to switching base.** Diagnostic-gated: try the recipe-only fix
   first (expand LoRA to MLP `gate/up/down → linear_fc1/linear_fc2` — already supported by
   `TrainRecipe.lora_target_modules_for_backend()` — and/or bump rank/steps). If a bounded
   recipe sweep still trips the spaceless guard, escalate to scouting an alternate reasoning
   base via the `hf-model-scout` skill.
3. **Release = NeMo flagship only.** Ship `patent-strategist-v4-nemo` (+ `-GGUF`) as the
   single flagship. v3-unsloth stays as the prior research preview; no v4-unsloth lane, no
   re-run of the paired bakeoff.
4. **New v4 HF repos** (`Orionfold/patent-strategist-v4-nemo{,-GGUF}`); v3 repos stay live
   as the documented prior preview.

## Fix design

### Corpus (Issue 1)
- **Grounding allowlist:** assemble a deterministic set of real MPEP section numbers (at
  minimum the sections the corpus families reference; the `mpep_context` field in each corpus
  row is the grounding source). Build `scripts/v4_corpus_factcheck.py` — a deterministic
  pre-pass that flags rows whose `chain`/`answer` cite a `§NNNN.NN(x)` subsection not present
  in the row's `mpep_context` or the allowlist, plus a terminology blocklist
  (`metes-and-times` → `metes-and-bounds`, etc.).
- **Repair flagged rows in-session** per `feedback_llm_skill_pattern` (Claude edits the
  flagged rows; no API/SDK). The article implies ~1% of answers drift, so the flagged set is
  expected to be small (~tens of rows).
- **New verify gate:** extend `.claude/skills/claude-corpus-synth/scripts/verify_chunk.py`
  with an MPEP-grounding check (reject a chunk whose cites aren't in `mpep_context`/allowlist)
  — sibling to the existing `META_ROW_REF_RE` / meta-state gates.
- **Output:** `/home/nvidia/data/aifn-corpus-v4/v4_full_5000.jsonl` (same `<think>chain
  </think>answer` schema). Keep the explicit `{BOS}{User}{prompt}{Assistant}{response}{EOS}`
  wrapping (`feedback_sft_eos_bos_explicit`).

### Spaceless-think (Issue 2)
- **Diagnostic (gates the recipe):** run `scripts/probe_reasoning.py` on (i) the **base**
  `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` and (ii) the v3 **nemo** merged BF16
  (`/home/nvidia/data/aifn-train-lora/p65-nemo/merged-hf-bf16-clean`). Compare
  `think_space_ratio`. Base spaceless ⇒ hypothesis (a); base spaced but v3 spaceless ⇒ (b).
- **Recipe branch (default fix):** v4 `TrainRecipe` with
  `lora_target_modules=("q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj")`
  and a rank/steps bump (e.g. r=32, ~2–3 epochs), so the FT has the capacity to overwrite the
  generation-style prior. **Risk:** MLP targeting is the dominant `<think>`-degradation source
  per `_SPECS/patent-strategist-v1.md` §4 — so the probe must check `think_presence_rate` +
  `think_token_length` **alongside** `think_space_ratio` and revert if reasoning collapses.
- **Base-switch fallback (only if the bounded recipe sweep still trips `< 0.08`):**
  `hf-model-scout` for an alternate open-license reasoning base without the spaceless think
  prior; re-run convert + train + probe.

### Release pipeline (NeMo stack — `nvcr.io/nvidia/nemo:26.04.00` / container `nemo-train`)
Reuse the proven v3 path end-to-end — no new training infra:
- `scripts/p65_v3_to_nemo_jsonl.py` → reshape v4 corpus to `{input,output}`.
- `fieldkit.training.convert` (`HFToMegatron`, `patch_yarn_defaults`,
  `register_llama_cpp_pretokenizer_hash`) → HF→mcore.
- `scripts/p65_train_nemo_lora.{py,sh}` driven by the v4 `TrainRecipe`; smoke (10 iter) →
  project full wall (pad ×1.16 per `feedback_smoke_projection_slack`) → launch full in
  background; liveness via `latest_checkpointed_iteration.txt` (not train.log —
  `feedback_megatron_train_log_buffering`).
- `fieldkit.training.run.merge_and_export` + `standardize_hf_export` → clean HF BF16.
- Quantize → GGUF (Q4_K_M/Q5_K_M/Q6_K/Q8_0); perplexity + vertical bench
  (`scripts/g3_measure_variants.py`).
- Publish via `fieldkit.publish.ModelCard` + `hf-publisher` skill; **update `known_drift`**:
  drop the two now-fixed artifacts, bound any residual. Refresh the notebook manifest +
  HF-card badges. Update the bakeoff article's "next iteration" note, add a `decide.py`
  entry, refresh stats.

## Critical files

| Purpose | Path |
|---|---|
| Spaceless diagnosis + guard | `scripts/probe_reasoning.py` (`think_space_ratio`, `MIN_THINK_SPACE_RATIO=0.08`) |
| Recipe (MLP expansion already supported) | `fieldkit/src/fieldkit/training/recipe.py` (`lora_target_modules_for_backend`) |
| HF→mcore + YARN + pretokenizer | `fieldkit/src/fieldkit/training/convert.py` |
| Train run + merge/export + liveness | `fieldkit/src/fieldkit/training/run.py` |
| NeMo trainer + orchestrator | `scripts/p65_train_nemo_lora.{py,sh}`, `scripts/p65_v3_to_nemo_jsonl.py` |
| Corpus (v3 source) | `/home/nvidia/data/aifn-corpus-v3/v3_full_5000.jsonl` |
| Corpus verify gates | `.claude/skills/claude-corpus-synth/scripts/verify_chunk.py` |
| Hallucination evidence | `articles/patent-strategist-bakeoff-unsloth-vs-nemo-framework/article.md:254-256` |
| Card drift + render | `scripts/republish_patent_strategist_readmes.py`, `fieldkit/src/fieldkit/publish/__init__.py`, `_GUIDES/NARRATIVE-CONTRACT.md` |
| v3 nemo merged BF16 (diagnostic target) | `/home/nvidia/data/aifn-train-lora/p65-nemo/merged-hf-bf16-clean` |
| Decision context | `ideas/uber-local-corpus-gen-decision.md`, `_SPECS/patent-strategist-v1.md` §4 |
| **NEW** fact-check pre-pass | `scripts/v4_corpus_factcheck.py` |

## Session-sized task breakdown (each = one CC session context)

| # | Task | Gate / output |
|---|---|---|
| **S1** | **Spaceless root-cause diagnostic.** `probe_reasoning.py` on the base model AND the v3-nemo merged BF16; record `think_space_ratio` for each. | Verdict (a) base-inherited vs (b) FT-introduced → selects v4 recipe branch. |
| **S2** | **Corpus scrub + grounding gate.** Build `scripts/v4_corpus_factcheck.py`, flag fabricated cites/terminology across the 5000 rows, repair flagged rows in-session, add the MPEP-grounding gate to `verify_chunk.py`. | `aifn-corpus-v4/v4_full_5000.jsonl`; 0 ungrounded cites; gate unit-tested. |
| **S3** | **v4 recipe + convert + smoke + launch full train.** Write the v4 `TrainRecipe` (branch from S1), reshape corpus → mcore dataset, smoke (10 iter) + project wall, launch full NeMo train on `nemo-train` in background. | Full train launched + monitored to first checkpoint. |
| **S4** | **Merge/export + probe (decision point).** `merge_and_export` → `standardize_hf_export` → `probe_reasoning.py`. | **Gate:** `think_space_ratio ≥ 0.08` AND reasoning metrics intact. Pass → S5; trip → S4b. |
| **S4b** | **(conditional) base-model switch + retrain.** Only if S4 trips the guard after the recipe sweep: `hf-model-scout` an alternate reasoning base → re-run S3/S4. | New base picked; retrain passes the S4 gate. |
| **S5** | **Quantize + bench + publish dry-run.** GGUF Q4/Q5/Q6/Q8 + pretokenizer hash; perplexity + vertical bench; `publish_quant(..., dry_run=True)`; rewrite `known_drift` (drop the two fixed artifacts). | Dry-run stage verified; bench numbers recorded; spaced `<think>` sample captured. |
| **S6** | **Live publish + cards + article + stats.** Live HF push of `patent-strategist-v4-nemo{,-GGUF}`; republish cards; update bakeoff article + add a `decide.py` v4 entry; refresh notebook manifest/badges; `nvidia-learn-stats`; commit. | v4 cards positioning-first w/ shrunken drift; `astro sync` clean; stats refreshed; pushed. |

## Verification

- **S1:** diagnostic JSON shows base vs v3-nemo `think_space_ratio` side-by-side; verdict
  recorded here + in HANDOFF.
- **S2:** `v4_corpus_factcheck.py` reports 0 ungrounded cites on the repaired corpus;
  `verify_chunk.py` new gate has a unit test that rejects a known-fabricated `§2163.05(s)`
  row and passes a grounded one; spot-check repaired rows by eye.
- **S4 (the headline gate):** `probe_reasoning.py` on the v4 merged BF16 returns
  `think_space_ratio ≥ 0.08` (no SPACELESS-THINK WARNING) with `think_presence_rate` and
  `think_token_length` within range of the v3-nemo baseline — proves the spaceless fix
  without trading away reasoning.
- **S5:** GGUF perplexity sweep + vertical-bench numbers recorded; a `<think>` sample from
  the served Q5_K_M is spaced (the user-visible proof).
- **S6:** all v4 HF cards render positioning-first with bounded (shrunken) `known_drift`;
  `astro sync` clean; stats refreshed; commit pushed.
