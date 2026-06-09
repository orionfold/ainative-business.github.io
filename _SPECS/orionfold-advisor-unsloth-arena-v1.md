---
project: orionfold-advisor-unsloth-arena
version: v1.0
status: DRAFT (planning decisions captured 2026-06-09; unbuilt)
created: 2026-06-09
authoritative: Spark
---

# Orionfold Advisor Unsloth + Arena Proof v1.0

> The publish-grade, small end-to-end proof that treats the Unsloth partner path
> as real: Unsloth trains and exports the candidate; fieldkit and Arena import,
> govern, launch, score, publish, or reject it. The default domain is
> **Orionfold Advisor**: a public-corpus assistant expert in Orionfold's
> published Field Notes, product launches, artifact cards, public docs/specs,
> releases, and book chapters.
>
> This spec intentionally combines the **run**, not the final public artifacts.
> The run should generate one integrated evidence trail. The writeups stay
> separate: a Field Note for the Unsloth-to-Arena partner receipt, a product
> article/update for the autonomous-harness cockpit, and optional HF artifacts
> only if the gates pass.

## 1. Context

The Unsloth strategy memo recommends not competing with Unsloth on kernels or
generic training UI. The stronger wedge is:

```text
Fine-tune in Unsloth; decide in Arena.
```

Existing Orionfold evidence already proves basic Unsloth Core feasibility on
Spark and also shows why Arena must remain the decision layer: the prior
patent-strategist Unsloth lane was real, useful, and still not the promoted
artifact after scoring against the NeMo lane. The missing proof is therefore not
"can Unsloth train here?" It is:

```text
public corpus -> Unsloth Core SFT/export -> fieldkit manifest ->
Arena lane launch/inference -> Advisor evals -> RL headroom check ->
publish or reject with receipts
```

The Advisor idea is deliberately recursive. It uses Orionfold's public body of
work to build an assistant that helps operate and explain Orionfold. That makes
it a strong dogfood target, but also a risky one: "expert on everything
Orionfold" is too broad unless RAG, SFT, and RL have sharp separation of
concerns.

Prior Second Brain findings govern the separation:

- RAG owns factual recall, citations, provenance, source filtering, and
  freshness.
- SFT owns answer shape, routing behavior, citation discipline, refusal
  behavior, and Orionfold workflow recommendations.
- RL is conditional. It runs only after a measured headroom gate shows that
  reinforcement has useful signal.

## 2. Outcome Path

The run path is fixed:

```text
domain gate
  -> public corpus manifest
  -> Cortex/RAG index
  -> Advisor bench
  -> base-model scout
  -> Unsloth Core SFT/export
  -> fieldkit manifest/import
  -> Arena lane launch/inference
  -> evals
  -> RL headroom check
  -> publish receipt or rejection receipt
```

The first run is **publish-grade small**: small enough to finish under the
one-lane DGX Spark envelope, but real enough to produce held-out evals,
screenshots, artifact metadata, and a useful public receipt if it passes.

## 3. Locked Planning Decisions

| ID | Decision | Value | Why |
|---|---|---|---|
| OA-1 | Default domain | **Orionfold Advisor**, with a real domain gate before training | Strongest recursive dogfood target; still needs a gate because the scope is broad. |
| OA-2 | Corpus boundary | **Public-only** | Keeps the artifact publishable and avoids handoff/operator/private-state leakage. |
| OA-3 | Learning posture | **RAG-first** | Prior Second Brain work showed LoRA teaches behavior/voice more reliably than facts. |
| OA-4 | Unsloth surface | **Core primary; Studio optional** | Core is scriptable and reproducible. Studio screenshots are useful only if stable. |
| OA-5 | Run scale | **Publish-grade small** | Avoids a toy smoke while respecting one-lane memory and cleanup cost. |
| OA-6 | Public output | **Full receipt if gates pass** | Field Note + optional HF artifact + bench/dataset card + autonomous-harness screenshots. |
| OA-7 | RL posture | **Headroom-gated** | RL runs only if the selection held-out is neither saturated nor sparse. |
| OA-8 | Operating surface | **Arena browser-use first** | Arena is the system of record; terminal-only steps become dogfood findings unless explicitly external setup. |

## 4. Domain Gate

The domain gate happens before corpus generation or training. Advisor is the
default winner, but the gate must compare it against at least two alternatives.

Recommended alternatives:

1. **Orionfold Advisor** - public Orionfold corpus expert.
2. **Arena Operator Advisor** - narrower assistant over Arena/fieldkit docs,
   runbooks, release notes, and product pages.
3. **External vertical candidate** - a customer-style public domain chosen for
   market-facing evidence if Advisor proves too recursive.

Score each candidate 1-5 on:

- Public corpus quality and source clarity.
- Evaluation tractability.
- Market or narrative value.
- Publishability and license safety.
- One-lane Spark feasibility.
- Unsloth/Arena proof value.
- Screenshot/product-story value.

Default rule: Advisor proceeds unless it scores below 4 on either
publishability or evalability. If it fails, use Arena Operator Advisor as the
first narrower fallback.

## 5. Corpus Boundary

Advisor v1 uses only public-safe source classes:

- Published Field Notes under `articles/*/article.md`.
- Product launch pages under `products/*/product.md`.
- Artifact cards and release metadata that are already public-facing.
- Public fieldkit docs, guides, and specs where citation is safe.
- Public book chapters under `src/data/book/chapters/`.
- Public release notes and changelog excerpts.

Explicitly excluded:

- `HANDOFF.md` details unless manually promoted into public docs.
- `_STATUS.json`, operator beacon state, live runtime notes, and private
  scheduler state.
- `.env.local`, secrets, keys, tokens, local paths that reveal private state,
  and unpublished internal evidence not intended for citation.
- Private or root-owned generated data unless converted into a public artifact.

The corpus manifest must assign every source:

- `source_id`
- `path_or_url`
- `source_class`
- `trust_tier`
- `public_safe`
- `date_or_version`
- `citation_label`
- optional `artifact_slug` / `product_slug` / `chapter_id`

If "the three books" are not all present in this repo, the source audit must
record which book surfaces are missing before ingestion. Missing books are not
silently approximated from related docs.

## 6. Advisor Bench

The Advisor bench is the decision surface. It must test behavior that RAG, SFT,
and RL can improve separately.

Bench families:

| Family | What it tests | Expected owner |
|---|---|---|
| Cited factual QA | Can the system answer with correct source citations? | RAG |
| Artifact/release facts | Can it state model/package/product facts without drift? | RAG + provenance |
| Book thesis synthesis | Can it synthesize the public book argument without inventing? | RAG + generator |
| Workflow routing | Can it route requests to fieldkit, Arena, product-writer, tech-writer, etc.? | SFT |
| Missing-source refusal | Does it refuse when the public corpus does not support the answer? | SFT + prompt |
| Operator recommendations | Can it recommend next steps while naming uncertainty and gates? | SFT + eval |
| Unsloth/Arena partner path | Can it explain train/export vs score/govern/publish separation? | SFT + RAG |

Minimum first-run bench:

- 80-120 total questions.
- 20-30 frozen held-out questions.
- Every held-out row maps to one or more public sources.
- Every row carries expected citation targets.
- At least 15 refusal or insufficient-context cases.

Use separate eval slices:

- **Selection held-out** for SFT/RL decisions.
- **Generalization held-out** for publish claims.

Do not train on either held-out slice.

## 7. Base Model Scout

The base model is not locked in this spec. Use the existing `hf-model-scout`
discipline and add Advisor-specific gates.

Required scout axes:

- Chat template and tokenizer sanity.
- License and redistribution posture.
- llama.cpp/GGUF architecture support.
- 128 GB one-lane envelope.
- Unsloth Core support.
- Long-context and RAG prompt behavior.
- Citation/refusal behavior on a 5-question Advisor preflight.
- Throughput and expected export path.

Base model candidates should include at least one Qwen-family instruct/reasoning
model because prior Orionfold work has strong Qwen evidence, but the scout must
be allowed to reject it.

Preflight before training:

- Ask 5-10 Advisor held-out-style questions with retrieved context.
- Check citation format, refusal behavior, and tendency to invent.
- Record whether failure is retrieval, generation, formatting, or source-gap.

## 8. RAG, SFT, and RL Separation

### RAG

RAG is the source of truth. It uses Cortex/fieldkit memory patterns:

- Public-source ingestion.
- Provenance columns and trust filters.
- Recall gate before training.
- Like-for-like comparison across retrieval modes.
- Citation ids carried into prompts and evals.

Training should not compensate for a stale or low-recall index. If recall is
weak, fix retrieval before SFT.

### SFT

SFT teaches the Advisor how to use the retrieved evidence.

Training rows should be context-aware triples:

```text
question + retrieved context + expected cited answer/refusal/routing decision
```

Do not use context-free Q&A as the main corpus. Prior Second Brain work showed
that context-free LoRA can teach confidence, terseness, and voice while leaving
facts fragile.

SFT success criteria:

- Better citation adherence.
- Better refusal discipline.
- Better workflow routing.
- Better answer shape for operator guidance.
- No regression in factual correctness against the same retrieved context.

### RL

RL is optional and headroom-gated.

Before any RL run:

- Score the SFT+RAG system on the exact selection held-out.
- Proceed only if the score is in the useful middle band.
- Skip RL if the score is saturated or if reward density is too low.

Default interpretation:

- High score: ship SFT/RAG, do not waste a run.
- Low score: fix corpus/retrieval/SFT first.
- Middle score: run a small RL check and compare held-out-only.

## 9. Unsloth Core Training Path

Use Unsloth Core as the primary training/export lane.

Expected artifacts:

- Training corpus JSONL with source ids.
- Unsloth run config.
- LoRA adapter or merged checkpoint.
- Export metadata.
- GGUF or safetensors export if supported and useful.
- Training log summary.
- Peak memory and wall-clock receipt.

Studio is optional:

- Do not make Studio a hard dependency.
- Capture Studio only if setup is stable and it contributes useful evidence.
- Do not bundle, modify, or depend on AGPL Studio components without a separate
  license review.

No new `fieldkit.training.unsloth` abstraction is required for v1. If the run
needs a local helper, keep it script-local. Promote a fieldkit module only after
repeat reuse or a clear stable metadata import need.

## 10. Arena Browser-Use Execution

The proof should be operated through the running Arena cockpit wherever
possible.

Required harness:

```bash
.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh restart --browser
```

Expected surfaces:

- `http://127.0.0.1:7866/`
- CDP Chromium on `127.0.0.1:9222`

Browser-use rules:

- Use Arena as the system of record for observations.
- Operate from Arena panes when a pane/action exists.
- Capture screenshots from live panes, not empty states.
- If terminal work is required, classify it as expected external setup or a
  dogfood finding in the companion spec.
- After any `arena-app/` edit, rebake `_webui`, restart Arena, and browser-smoke
  the affected pane before continuing.

Screenshots to harvest:

- Knowledge/Cortex corpus and recall.
- Build spine / manifest.
- Jobs board.
- Training/SFT progress.
- LaneTruth / Models.
- Chat and Compare.
- Leaderboard/evals.
- Reward/RL headroom.
- Budget/guardrail surfaces.
- Standup/autonomous harness.

## 11. Arena Import and Publish Flow

After Unsloth export:

1. Import the candidate into a fieldkit manifest or script-local import receipt.
2. Preserve base model, training source, adapter path, export type, license,
   source corpus, and known drift.
3. Launch or select the lane from Arena if the shipped surface supports it.
4. Run Advisor held-out evals in Arena.
5. Compare base, RAG-only, SFT+RAG, and any RL candidate.
6. Publish only if the held-out gates pass.

If the candidate fails:

- Preserve the manifest and measurements.
- Record the reason not promoted.
- Publish a decision receipt only if it is useful and safe.

This rejection path is a feature, not a failure: it proves Arena is the decision
layer, not a rubber stamp for the training lane.

## 12. Deliverables

| Deliverable | Gate |
|---|---|
| Domain gate report | Advisor wins or fallback chosen with scores |
| Public corpus manifest | Every source public-safe and citable |
| Advisor bench | Held-out slices frozen and source-mapped |
| RAG recall report | Cortex-style recall gate recorded |
| Base scout report | Four traps + Advisor-specific preflight passed |
| Unsloth Core training receipt | Logs, memory, wall time, export path captured |
| Arena run receipt | Live pane screenshots + eval rows + provenance |
| RL headroom decision | Run/skip justified by measured held-out score |
| Publish or rejection receipt | Artifact promoted only if gates pass |
| Dogfood ledger | All fieldkit/Arena findings classified |

## 13. Success Criteria

The run succeeds if:

- The public corpus boundary holds.
- Advisor bench and held-out slices are source-mapped.
- Unsloth Core produces a usable candidate or a documented failure receipt.
- Arena imports, launches/selects, evaluates, and records the candidate.
- SFT+RAG improves at least one targeted behavior without factual regression.
- RL is either correctly skipped or run under the headroom gate.
- Browser-use screenshots provide real evidence for the autonomous-harness
  product article.
- Every out-of-Arena workaround is captured in the dogfood companion spec.

## 14. Risks

| ID | Risk | Mitigation |
|---|---|---|
| OA-R1 | Advisor is too broad | Domain gate; fallback to Arena Operator Advisor. |
| OA-R2 | SFT memorizes stale facts | Public RAG owns facts; SFT rows include retrieved context. |
| OA-R3 | Context-free training teaches confidence over truth | Avoid context-free Q&A as the main corpus. |
| OA-R4 | RL has no useful signal | Headroom gate before any RL run. |
| OA-R5 | Private state leaks into corpus | Public-only manifest and secret/privacy scan. |
| OA-R6 | Studio friction blocks the run | Core is primary; Studio optional. |
| OA-R7 | Arena cannot operate enough of the flow | Companion dogfood spec records gaps and release posture. |

## 15. References

- `_IDEAS/unsloth-compete-partner-analysis.md`
- `_GUIDES/arena-e2e-smoke-runbook.md`
- `_SPECS/spark-arena-v1.md` sections 14 and 15
- `_SPECS/rlvr-loop-v1.md`
- `_SPECS/arena-enhancements-v1.md`
- `_SPECS/arena-enhancements-v2.md`
- `products/orionfold-cortex/product.md`
- `articles/lora-on-your-own-qa-pairs/article.md`
- `articles/rag-eval-ragas-and-nemo-evaluator/article.md`
- `articles/mcp-second-brain-in-claude-code/article.md`

## 16. Change Log

| Date | Change | Author |
|---|---|---|
| 2026-06-09 | Spec authored from the Codex planning session: Advisor default, public corpus, RAG-first, Unsloth Core primary, publish-grade small run, Arena browser-use first, companion dogfood spec required. | Manav (with Codex) |
