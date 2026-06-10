---
project: orionfold-advisor-nvidia-native
version: v1.2
status: DRAFT (Advisor brand restored; replaces the Unsloth-first Advisor proof)
created: 2026-06-09
authoritative: Spark
---

# Orionfold Advisor NVIDIA-Native v1.2

> Flagship product track: a governed local Advisor appliance on DGX Spark. The
> package is not just a model; it is a harness + model + retriever + corpus +
> Arena workspace, with a swappable customer corpus and governed escalation from
> local NVIDIA-native lanes to hosted SOTA only when the local stack needs help.

## 1. Pivot

Orionfold's selection for the NVIDIA Inception program changes the GTM center of
gravity. The prior Unsloth partner-path proof is no longer the right headline.
The flagship story is now:

```text
Get the most quality, governance, and operational leverage out of NVIDIA DGX Spark.
```

**Orionfold Advisor** is the first proof of that story. It should be
positioned as a local enterprise advisor appliance that understands a governed
corpus, cites its sources, refuses private/operator state, and demonstrates how
Orionfold builds governed AI assets on NVIDIA infrastructure.

Unsloth is dropped from the default plan. It can re-enter only as a measured
third-party acceleration option if it beats the NVIDIA-native path on Advisor
quality, iteration speed, export reliability, or cost-to-quality. It is not a
positioning pillar for Advisor v1.

## 2. Brand

Product name: **Orionfold Advisor**.

Category: **governed local AI advisor appliance**.

Use **Orionfold Advisor** as the public product name and keep existing
`advisor-*` proof ids. Arena run context, receipts, and public positioning should
say **Advisor**.

Recommended positioning line:

```text
Orionfold Advisor is a governed local AI advisor for your enterprise corpus.
```

The name is direct: the product is the governed advisor itself, not a metaphor
around the advisor. The corpus supplies the knowledge boundary, Cortex supplies
the retrieval layer, the local model supplies grounded synthesis, Arena supplies
the operating surface, and routing governs when to consult larger local or
hosted instruments.

## 3. Product Thesis

Orionfold Advisor is not a generic chatbot and not merely a fine-tuned model. It
is a packaged advisor appliance:

- **Harness**: deterministic routing, source-boundary policy, budget guardrails,
  evidence capture, and OpenAI-compatible endpoint adapters.
- **Model**: a NVIDIA-native local Advisor lane tuned for citation discipline,
  refusal behavior, workflow routing, and operator-quality recommendations.
- **Retriever**: a Cortex/Second-Brain memory layer with source ids,
  provenance/trust tiers, recall gates, and freshness checks.
- **Corpus**: a default Orionfold public corpus that demonstrates the product,
  plus a corpus-pack contract so a customer can swap in their own docs.
- **Arena workspace**: the visible training/eval/inference playground that
  launches lanes, runs preflights, displays receipts, tracks costs, and records
  publish/reject decisions.

The v1 wedge is:

```text
Bring an enterprise corpus to a DGX Spark, build a local Advisor over it, prove
retrieval and generator behavior in Arena, and govern any frontier escalation.
```

The default demo corpus remains Orionfold's public body of work because it is
the corpus we can inspect, publish, and dogfood. The enterprise product shape is
the same harness with a different corpus pack.

Advisor's local model is tuned for:

- citation discipline, refusal behavior, workflow
  routing, and operator-quality recommendations.
- grounded synthesis over the retrieved corpus rather than memorized private
  facts.
- self-knowledge about what the harness can and cannot do.
- controlled escalation when local confidence, retrieval coverage, or task
  class falls outside the local lane's proven envelope.

The goal is not to win every public benchmark. The goal is to be close enough to
best open-weight quality while being obviously better aligned to NVIDIA GTM,
Spark locality, and enterprise trust.

## 4. Architecture

```text
corpus pack
  -> source manifest + public/private audit
  -> Cortex retriever index + recall gate
  -> Advisor harness policy + routing manifest
  -> Advisor bench + held-out slices
  -> NVIDIA-first local model lane
  -> NeMo / NVIDIA-native SFT candidate
  -> Arena preflight + eval + cost ledger
  -> local specialist / hosted SOTA escalation tests
  -> RL headroom gate
  -> publish receipt or rejection receipt
```

Responsibilities stay separated:

| Layer | Owns | Must not own |
|---|---|---|
| Retriever | facts, citations, freshness, source ids | answer style or policy learning |
| Corpus pack | source manifest, permissions, chunking policy, gold evals | model training by default |
| Harness | routing, budget, safety policy, endpoint adapters, evidence capture | hidden model selection or untracked prompt mutation |
| SFT | source-id formatting, refusal shape, routing, recommendations | memorized private facts |
| RL | measured improvement on partial-signal held-out rows | fixing a bad SFT floor or bad retrieval |
| Arena | visible eval, gate state, rejection/publish receipt | hidden endpoint-only scoring |
| Fieldkit | repeatable manifests, scorers, lane recipes, evidence | one-off product positioning |

## 5. Prior Work To Fold In

Advisor should reuse the strongest patterns already built in the repo:

| Prior asset | Advisor implication |
|---|---|
| Orionfold Cortex / Second Brain | The retriever is a managed memory layer, not a raw vector table. Every corpus rebuild needs coverage, freshness, provenance, recall@k, and a promotion gate. |
| Machine That Builds Machines | Advisor runs through the same job, budget, memory, cost, and morning-standup discipline as other Spark artifacts. The harness should emit receipts that feed future articles, cards, and book chapters. |
| Hermes vertical router | Routing should remain deterministic and auditable where possible: keyword/domain predicates, token-budget thresholds, confidence/failure classes, and one-lane Spark serving. |
| Hermes cost router | Local-first is not a slogan; measure the leak rate. Escalation to OpenRouter or hosted frontier lanes should be justified by local failure classes and tracked as dollars per task / dollars per quality point. |
| Orionfold Arena | Arena is the operating surface and system of record for Advisor training, eval, inference, comparison, cost, provenance, and run-context. |
| Naive RAG / rerank / bigger-generator grounding | Retrieval often works before generation does. Treat retrieval, grounding, refusal, and citation-format failures as separate failure classes. |
| NIM-first inference | OpenAI-compatible endpoints are the swap boundary, but NVIDIA-native serving paths deserve priority when they preserve behavior and throughput. |
| Harnesses / fieldkit MCP | The operator buttons and agent tools should call the same deterministic harness surface. No duplicate "human path" vs "agent path." |

## 6. Package Shape

Advisor v1 should ship and be sold as a bundle:

| Component | What ships | Customer-swappable? |
|---|---|---|
| Advisor harness | Routing policy, source-boundary prompt contract, budget caps, endpoint adapters, eval runner, receipt writer. | Mostly no; policy is configurable but the harness is the product. |
| Advisor model lane | Base model id, adapter/checkpoint if trained, serving recipe, quant/runtime notes, known-drift card. | Yes, after passing the same Arena gates. |
| Retriever | Cortex index builder, chunk schema, embedder/reranker config, recall scorer, provenance filters. | Yes. |
| Corpus pack | `sources.jsonl`, source audit, permissions, chunk manifest, gold eval seed, refusal/private-state cases. | Yes; this is the enterprise onboarding unit. |
| Arena workspace | Run context, lane recipes, preflight button, eval history, cost ledger, screenshots/receipts. | Yes; one workspace per customer corpus or deployment. |
| Escalation policy | Local-first router, OpenRouter/hosted SOTA allowlist, data-policy constraints, cap-usd, audit log. | Yes, under governance. |

This makes "Orionfold Advisor" portable:

```text
Orionfold default corpus -> Advisor demo
Customer corpus pack     -> Customer Advisor
Same harness             -> Same gates, receipts, routing, and Arena controls
```

The corpus-swap contract is deliberately heavier than "upload PDFs." A customer
corpus must include or generate:

- a source manifest with permission and trust tier per document.
- chunking and provenance rules.
- an initial gold/eval set, including answerable, missing-source, and
  private-state refusal rows.
- a freshness policy and rebuild trigger.
- a publish/reject threshold for recall and generator behavior.

## 7. Salvaged Evidence

Keep the useful parts from the superseded Unsloth-era work:

- Deterministic Advisor evidence under `evidence/orionfold-advisor/`.
- Public corpus manifest: 181 public-safe sources with book/product/artifact/doc
  roles.
- Bench seed: 103 rows total, 28 held-out rows, including refusal/private-state
  boundary cases.
- Retrieval baseline: local BM25/provenance chunks passed source recall with
  `source_recall@5 = 0.9885` overall and `1.0` on held-out answerable rows.
- Live Cortex retrieval receipt (`rag-recall-v0.1-cortex.json`): the same
  manifest + frozen bench scored through the production retrieval stack
  (pgvector `advisor_corpus_v01` + NIM `llama-nemotron-embed-1b-v2`, cosine
  dense, rerank off) — `source_recall@5 = 0.977` overall, `1.0` on held-out
  answerable rows, `@1 = 0.8506` (vs BM25 `0.7471`). Gate passed; the §14
  "retriever recall remains green on public corpus" condition is met on the
  live lane, not only the local BM25 proxy.
- Arena-visible preflight path: Cortex can show active-lane readiness and run the
  tracked 8-row generator preflight through `POST /api/advisor/preflight/run`.
- Current Qwen2.5 fallback receipt: failed, non-publishable, 8 rows scored,
  5 passed, 3 failed after prompt/scorer tightening.
- Current Nano 9B NIM receipt: failed, non-publishable, 8 rows scored,
  0 passed, 8 failed. Runtime is viable on Spark through cached NIM on `:8000`,
  but Advisor behavior is not viable without reasoning-mode/policy work.
- Current Nano 9B `/no_think` receipt (`advisor-preflight-v0.1-nothink.json`,
  run through the visible Cortex `run /no_think` control per §13.C step 5):
  failed, non-publishable, 8 rows scored, 1 passed, 7 failed — but the
  reasoning-leakage class is fully resolved (`thinking_leak` 0/8 vs 7/8).
  Remaining failures are SFT-shaped: 4 exact-source-id alias/format rows
  (`Citations: [2]`, `source_id_N` placeholders, Route line without a
  Citations line), 1 grounding over-refusal (`Citations: []` despite the
  expected source at retrieval rank 1), and 2 refusal rows missing refusal
  wording. These are the behavior classes §4 assigns to SFT, so Nano 9B
  with `/no_think` is a plausible-SFT-headroom candidate, not a pass.

Qwen2.5 failure surface:

| Row | Failure |
|---|---|
| `advisor-operator-recommendations-0074` | cites `Source 2` instead of exact `product_orionfold_cortex` |
| `advisor-missing-source-refusal-0087` | returns bare `Citations: []` without refusal language |
| `advisor-missing-source-refusal-0088` | returns bare `Citations: []` without refusal language |

Nano 9B failure surface:

| Class | Evidence |
|---|---|
| reasoning leakage | `thinking_leak=true` on 7 of 8 rows |
| citation / route | workflow-routing and several answer rows missed required exact source ids |
| refusal boundary | both refusal rows failed refusal wording and were flagged for private-state risk |

Interpretation: retrieval is not the main problem. Qwen2.5 mostly needs exact
source-id and refusal behavior; Nano 9B additionally needs explicit
reasoning-mode suppression or response redaction before it can be judged as an
Advisor base.

## 8. Revised Base-Model Criteria

The old `hf-model-scout` gates are still useful but incomplete. Advisor v1 uses
these revised axes:

| Axis | Requirement |
|---|---|
| NVIDIA GTM fit | Prefer NVIDIA-built, NVIDIA-optimized, or NVIDIA-packaged models when quality is close. |
| Spark leverage | Must make strong use of GB10 / Blackwell / DGX Spark locality, not merely fit. |
| Training path | Prefer NeMo / NeMo AutoModel / NeMo-RL compatibility before third-party training stacks. |
| Serving path | Prefer NIM, TRT-LLM, vLLM, or llama.cpp paths that are documented for Spark. |
| Reasoning control | Must support disabling or budgeting reasoning so citations/refusals do not leak hidden traces. |
| Citation/refusal behavior | Must pass Advisor preflight slices before training or show plausible SFT headroom. |
| Enterprise license | Commercial-ready license and redistribution posture must be clear. |
| Open-weight benchmark | Compare against best relevant HF/open-weight candidates so NVIDIA preference is informed, not blind. |

Weights for the next scout:

```text
30% Advisor preflight quality
20% NVIDIA-native GTM + stack fit
15% Spark throughput / memory efficiency
15% trainability / export path
10% license / enterprise posture
10% open-weight SOTA distance
```

## 9. Preliminary Model Search

This is a planning scout from NVIDIA Build and Hugging Face metadata, not a
weight download or local benchmark.

### NVIDIA-First Candidates

| Candidate | Initial role | Why it matters | Current risk |
|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-Nano-9B-v2` | Primary Advisor base candidate | NVIDIA-trained small reasoning/chat model; commercial-ready; 128K context; reasoning budget control; HF card reports stronger results than Qwen3-8B on several listed reasoning / instruction benchmarks; trained with Megatron-LM and NeMo-RL. | Hybrid Mamba/attention and `trust_remote_code` path need Spark-local serving and SFT validation; llama.cpp/GGUF path is not as straightforward as Qwen. |
| `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16` | Fast edge/latency candidate | NVIDIA says it is edge-ready for Jetson Thor, GeForce RTX, and DGX Spark; commercial-ready; 262K context; NeMo 25.07 integration; compressed from 9B. | May be below quality bar for flagship Advisor unless SFT/RAG closes the gap. |
| `nvidia/nemotron-3-nano-30b-a3b` | Local high-quality Spark candidate | NVIDIA Build has a DGX Spark llama.cpp playbook; 30B MoE with 3B active parameters; local OpenAI-compatible endpoint; built-in reasoning and tool-calling. | Uses about 38GB model memory per the playbook; SFT path may be harder than serving path; could be serve/eval candidate rather than training base. |
| `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-*` | Multimodal future candidate | Build and TRT-LLM surfaces list BF16/FP8/NVFP4 forms; useful later if Advisor becomes screenshot/document/VLM-aware. | Over-scoped for text-first Advisor; defer unless the product requires multimodal evidence. |
| `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4` | Teacher / ceiling / hosted scorer | TRT-LLM support matrix lists the 120B NVFP4 model; useful as NVIDIA-native quality ceiling. | Not the local trainable small Advisor; use as teacher/evaluator only if licensing and access permit. |
| `nvidia/nemotron-3-ultra-550b-a55b` | NVIDIA-hosted frontier ceiling | Build offers a free endpoint, partner endpoint, and download availability; 1M context frontier-class model. | Not a Spark-local fine-tune base. It can be part of the stack as an external NVIDIA teacher/evaluator, not the local Advisor artifact. |

### Open-Weight Comparison Set

| Candidate | Why compare |
|---|---|
| `Qwen/Qwen3-8B` | Prior Orionfold evidence, Apache-2.0, strong reasoning, 32K native / 131K YaRN, broad local runtime support. |
| `Qwen/Qwen3-14B` | Same family, higher capacity, still likely practical for Spark serving and LoRA probes. |
| `openai/gpt-oss-20b` | Apache-2.0, local/specialized use case, 21B total / 3.6B active, strong open-weight reasoning baseline; uses Harmony format. |
| `mistralai/Mistral-7B-Instruct-v0.3` or current Mistral small models | Useful permissive-license control if NVIDIA/Qwen candidates fail source-id or refusal behavior. |

Do not make an open-weight community model the default unless it materially beats
the NVIDIA-native path on Advisor-specific held-out behavior.

## 10. Why Not Just Use The Best Nemotron?

Use the best Nemotron where it fits the layer:

- **Yes**: use `nemotron-3-ultra-550b-a55b` or Super as NVIDIA-native teacher,
  evaluator, synthetic-data reviewer, or quality ceiling through Build / NIM /
  partner endpoints.
- **No**: do not call Ultra the local Advisor base. It is not a one-lane Spark
  fine-tune target and does not prove local enterprise deployment on DGX Spark.
- **Yes**: evaluate Nano 9B, Nano 4B, and Nano 30B-A3B as local Advisor
  candidates because they are much closer to the Spark mission.

The product claim should be:

```text
Advisor is trained and governed locally on Spark, with NVIDIA frontier models
available as optional teachers or enterprise escalation lanes.
```

## 11. Governed Model Routing

Advisor should route across capability tiers, but the routing policy is part of
the governed harness. It is not a hidden LLM-router by default.

| Tier | Lane | Use when | Governance |
|---|---|---|---|
| T0 | Refuse / ask for corpus ingest | Retrieval misses, source policy blocks, private/operator state requested. | Must emit refusal reason and `Citations: []`. |
| T1 | Local Advisor model | Normal grounded Q&A, recommendations, docs navigation, workflow routing. | Default path; zero marginal token cost; full local privacy. |
| T2 | Local NVIDIA specialist / larger local reasoning lane | Advisor model fails preflight class, needs stronger local reasoning, or a domain specialist exists. | One-lane Spark guard; Arena records lane swap and reason. |
| T3 | Hosted NVIDIA teacher/evaluator | Synthetic review, quality ceiling, difficult eval adjudication, candidate distillation. | No private corpus unless explicitly approved; cost and provider logged. |
| T4 | OpenRouter hosted SOTA | User-approved frontier escalation when local/NVIDIA paths fail or when customer policy allows SOTA overflow. | Allowed-model list, data-policy filter, cap-usd, generation-id cost audit, and redaction policy required. |

Routing inputs:

- retrieval state: coverage, top-k confidence, provenance/trust tier, freshness.
- generator state: refusal/citation failure class, reasoning leakage, format
  failure, tool-call failure.
- task class: simple grounded answer, workflow routing, operator
  recommendation, synthesis, long-context extraction, coding/planning.
- budget state: local/free, hosted spend so far, cap remaining, expected
  quality gain.
- data policy: public demo corpus, customer-private corpus, exportable
  redacted context, or no-egress.

Default routing discipline:

1. Try T1 local Advisor first for answerable, in-corpus questions.
2. Refuse at T0 if the retriever cannot provide source support or policy blocks
   the request.
3. Escalate to T2 when a local specialist or larger NVIDIA-native lane is
   likely to fix a measured failure class.
4. Use T3 for teacher/evaluator jobs and candidate improvement, not routine
   user answers.
5. Use T4 only through an explicit governed policy with cost and data controls.

OpenRouter belongs in the product as the governed overflow layer, not as the
center of the architecture. The prior Hermes cost-router measurement gives the
right framing: measure leak rate and dollars per quality point, then decide
where local stops being enough.

For OpenRouter specifically, the harness should use:

- explicit allowed model lists or patterns rather than unbounded auto-routing.
- session stickiness for multi-turn Advisor sessions.
- provider filters such as no-data-collection when customer policy requires it.
- `require_parameters` when JSON/schema/tool behavior is mandatory.
- returned `usage.cost` and generation stats for spend audit.
- pinned price snapshots in the Arena cost ledger for reproducibility.

## 12. Arena Workspace Requirements

Advisor needs a first-class Arena workspace, not a generic Cortex card:

| Surface | Requirement |
|---|---|
| Run context | Shows `Advisor`, corpus pack id, model lane, retriever build id, and routing policy id. |
| Corpus pane | Import/swap corpus pack, show coverage/freshness/provenance, run recall gate. |
| Preflight pane | Run held-out Advisor preflight from the cockpit; classify failures by failure class. |
| Training pane | Launch/observe SFT/RL smoke runs; show loss, held-out score, memory, and abort reason. |
| Inference pane | Chat with citations, retrieved context inspection, refusal reason, and route tier. |
| Compare pane | Local Advisor vs local larger lane vs hosted teacher/OpenRouter, with cost and privacy chips. |
| Ledger | Persist route tier, model/provider, token counts, cost, source ids, failure class, and final verdict. |
| Receipt | Publish/reject card that can feed product pages, HF cards, field notes, and handoff. |

This turns Arena from a playground into the customer's governance surface: the
place they can ask "what was trained, on what corpus, why did this query
escalate, what did it cost, and what evidence says this Advisor is safe to use?"

## 13. Scout Plan

### A. Catalog Probe

Search both surfaces:

- NVIDIA Build: model pages, Spark playbooks, NIM availability, TRT-LLM support,
  NVFP4 paths.
- Hugging Face: model cards, licenses, architecture, chat templates, runtime
  snippets, quantizations, community notes.

Record:

- model id
- license
- context length
- reasoning control
- runtime support
- NeMo / vLLM / TRT / llama.cpp path
- Spark-specific evidence
- whether it is trainable, serve-only, teacher-only, or reject

### B. Metadata Probe

Update `hf-model-scout` assumptions before using it:

- NVIDIA models may use hybrid Mamba/Transformer architectures and
  `trust_remote_code`; do not reject them merely because old llama.cpp
  compatibility logic is Qwen/Llama/Mistral-oriented.
- A NVIDIA-native model with a NIM/TRT-LLM/vLLM path can pass the revised scout
  even if GGUF conversion is not the primary route.
- Spark playbook support counts as first-class evidence.

### C. Arena Behavioral Probe

For each top candidate:

1. Serve one lane at a time.
2. Run the 8-row Advisor preflight through visible Cortex.
3. Save scored receipt and screenshot.
4. Classify failures as retrieval, prompt, citation format, refusal behavior,
   reasoning leakage, or runtime friction.
5. If the candidate supports reasoning controls, run one explicit no-thinking
   configuration before judging the base as unsuitable.

No hidden endpoint-only batch result can lock a base model.

### D. NeMo SFT Probe

Only after a candidate has a plausible behavior floor:

- Build a small context-aware SFT corpus from public sources.
- Run a short NeMo / NeMo AutoModel PEFT/SFT smoke.
- Re-run the same Advisor held-out.
- Compare against pre-SFT receipt.

### E. RL Headroom Gate

Run RL only if the SFT receipt is neither saturated nor sparse. RL should improve
exact source-id behavior and refusal wording only when reward density exists.

### F. Routing Probe

Before public positioning, run a small route bakeoff:

- T1 local Advisor only.
- T1 plus T2 local larger/specialist lane.
- T1/T2 plus T3 hosted NVIDIA teacher/evaluator.
- T1/T2 plus T4 OpenRouter overflow, if data policy allows.

Report pass rate, refusal correctness, citation correctness, route accuracy,
total hosted cost, and dollars per quality point. The publishable claim is not
"frontier available"; it is "frontier is governed, measured, capped, and used
only when the local stack needs help."

## 14. Acceptance Gates

Advisor v1 cannot move to public positioning until:

- Retriever recall remains green on public corpus.
- Local base preflight is at least 7/8 before SFT or shows clear SFT headroom.
- Post-SFT held-out passes all mandatory privacy/refusal rows.
- Citation rows use exact `source_id` values.
- Arena displays the run context as Advisor, not Kepler/astrodynamics.
- The corpus pack can be swapped from Orionfold default to a synthetic/customer
  fixture without changing harness code.
- Route tier, provider/model, cost, and privacy policy are visible for every
  hosted escalation.
- OpenRouter or hosted SOTA lanes are disabled by default for private customer
  corpora until a policy explicitly allows redacted egress.
- The final receipt says which model was rejected or promoted and why.

## 15. Open Decisions

| ID | Decision | Default |
|---|---|---|
| OA-NV-1 | Primary base-model lane | Scout `NVIDIA-Nemotron-Nano-9B-v2` first. |
| OA-NV-2 | Fast edge fallback | Probe `NVIDIA-Nemotron-3-Nano-4B-BF16`. |
| OA-NV-3 | Local high-quality serve candidate | Probe `nemotron-3-nano-30b-a3b` via Spark llama.cpp path. |
| OA-NV-4 | Community comparison | Keep Qwen3-8B/14B and gpt-oss-20b as baselines. |
| OA-NV-5 | Teacher lane | Use Ultra/Super only as hosted/teacher/evaluator unless a local path is proven. |
| OA-NV-6 | Unsloth | Dropped; re-open only after a measured NVIDIA-native baseline exists. |
| OA-NV-7 | Product packaging | Ship Advisor as harness + model + retriever + corpus pack + Arena workspace. |
| OA-NV-8 | Corpus swap | Default Orionfold corpus proves the pattern; customer corpus packs become the enterprise unit. |
| OA-NV-9 | Routing | Local-first deterministic routing; OpenRouter is governed overflow, not default execution. |
| OA-NV-10 | Cost plane | Persist route tier, token counts, price snapshot, and dollars per quality point in Arena. |
| OA-NV-11 | Data policy | Hosted escalation is opt-in for private customer corpora and must support redaction/no-egress modes. |

## 16. Local References To Preserve

- `products/orionfold-cortex/` - Cortex launch and screenshots for managed
  memory, recall gates, provenance filters, and corpus rebuild workflow.
- `src/content/artifacts/orionfold-cortex.yaml` - recall harness artifact shape
  and bounded drift.
- `products/orionfold-arena/` and `src/content/artifacts/orionfold-arena.yaml` -
  Arena as local-first cockpit with compare, leaderboard, telemetry, and cost
  frontier.
- `articles/the-machine-manages-its-own-memory/` - recall loop: reindex, score,
  gate, query, standup.
- `_FLOWS/the-machine-that-builds-machines.md` - job, memory, cost, budget, and
  RL loop roadmap.
- `_SPECS/hermes-harness-v1.md` - harness, MCP, vertical routing, and cost
  routing design.
- `articles/hermes-vertical-router-on-spark/` - deterministic vertical routing,
  one-lane Spark serving, and route auditability.
- `articles/hermes-cost-routing-local-and-openrouter/` and
  `src/content/artifacts/spark-hermes-cost-router.yaml` - measured local to
  OpenRouter leak-rate and cost-router packaging.
- `articles/one-substrate-three-apps/` - corpus + 128 GB substrate and cost
  shape framing.
- `articles/naive-rag-on-spark/`, `articles/rerank-fusion-retrieval-on-spark/`,
  and `articles/bigger-generator-grounding-on-spark/` - retrieval vs generator
  failure lessons.
- `articles/nim-first-inference-dgx-spark/` - NIM-first serving and the
  OpenAI-compatible endpoint as swap boundary.

## 17. Sources Checked

- NVIDIA Build model: `nvidia/nemotron-3-ultra-550b-a55b` -
  <https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b>
- NVIDIA Build model: `nvidia/nemotron-3-nano-30b-a3b` -
  <https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b>
- NVIDIA Build Spark playbook: Nemotron-3-Nano with llama.cpp -
  <https://build.nvidia.com/spark/nemotron>
- NVIDIA Build Spark playbook: Fine-tune with NeMo -
  <https://build.nvidia.com/spark/nemo-fine-tune>
- NVIDIA Build Spark playbook: NIM on Spark -
  <https://build.nvidia.com/spark/nim-llm>
- NVIDIA Build Spark playbook: TRT-LLM -
  <https://build.nvidia.com/spark/trt-llm>
- NVIDIA Build Spark playbook: NVFP4 Quantization -
  <https://build.nvidia.com/spark/nvfp4-quantization>
- Hugging Face: `nvidia/NVIDIA-Nemotron-Nano-9B-v2` -
  <https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2>
- Hugging Face: `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16` -
  <https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16>
- Hugging Face: `nvidia/Llama-3.1-Nemotron-Nano-8B-v1` -
  <https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-8B-v1>
- Hugging Face: `Qwen/Qwen3-8B` -
  <https://huggingface.co/Qwen/Qwen3-8B>
- Hugging Face: `Qwen/Qwen3-14B` -
  <https://huggingface.co/Qwen/Qwen3-14B>
- Hugging Face: `openai/gpt-oss-20b` -
  <https://huggingface.co/openai/gpt-oss-20b>
- OpenRouter API overview -
  <https://openrouter.ai/docs/api/reference/overview>
- OpenRouter Auto Router / model routing -
  <https://openrouter.ai/docs/guides/routing/routers/auto-router>
- OpenRouter provider routing -
  <https://openrouter.ai/docs/guides/routing/provider-selection>

## 18. Change Log

| Date | Change | Author |
|---|---|---|
| 2026-06-09 | Re-ran the RAG recall gate through the LIVE Cortex retrieval stack (`scripts/orionfold_advisor/score_recall_live.py` → `evidence/orionfold-advisor/rag-recall-v0.1-cortex.json` + predictions): the 181-source public corpus pack ingested into its own pgvector table `advisor_corpus_v01` via the production `fieldkit.memory` path (900-word chunks + provenance card + per-chunk metadata prefix matching the v0.1 BM25 rule), embedded with the local `llama-nemotron-embed-1b-v2` NIM on `:8001`, scored with `MemoryIndex.query` cosine dense (rerank off). **Gate PASSED: `source_recall@5 = 0.977` overall, `1.0` on held-out answerable rows (`@3 = 1.0` held-out), `@10 = 1.0` everywhere; dense beats BM25 at rank 1 (`@1` 0.8506 vs 0.7471), consistent with the §13.F conclusion that retrieval granularity is the next lever.** 2 pool-row misses@5 (0004 expected `article_baseline_training_loop_on_spark`, 0076 expected `doc_fieldkit_readme_md`), both recovered @10; the BM25 baseline's sole miss (0068) passes live. `blog_chunks` untouched (OA-NV-8 corpus-pack swap); embedder stopped after the run. AD-AE-11 extended: corpus-pack ingest + the live recall gate have no Arena surface yet (spec §10 corpus pane plans it) — run as the minimum deterministic terminal action. | Manav (with Claude) |
| 2026-06-09 | Ran the §13.F routing probe (`scripts/orionfold_advisor/route_bakeoff.py` → `evidence/orionfold-advisor/advisor-route-bakeoff-v0.1.json` + ledger). Slice = the FULL frozen 28-row held-out (not the 8-row preflight subset), T1 = the live 30B-A3B `:8091` lane with the 7/8-receipt exemplar prompt. **T1-only 26/28 (92.9%): refusals 16/16, zero leak, zero private-state risk — the 0082 over-refusal class is NOT systematic.** Deterministic observables-only router (private-state data-policy gate; escalate on t1_error/format-failure/non-private-refusal) escalated exactly 1 row (0082), route accuracy 27/28 — the one miss is 0040's wrong-citation answer, the documented undetectable-without-labels class. Escalations: T3 `nvidia/nemotron-3-ultra-550b-a55b` (NGC, $0, 1.9k tokens) and T4 `anthropic/claude-haiku-4.5` (OpenRouter allowed-list, $0.0022 under the $1 cap) — **both frontier tiers ALSO refused 0082 on the same retrieved context**, adjudicating the sole §13.C failure as excerpt-window/bench-expectation drift (the rank-1 source's 900-char excerpt never shows the scoring/governance separation), not model over-refusal. Quality delta 0 points at both tiers → the local 30B-A3B floor is frontier-equivalent on this slice given this retrieval; the next quality lever is excerpt/retrieval granularity, not the generator. T2 skipped honestly (no larger local lane on disk). Governed-overflow claim demonstrated: escalation fired only on the detected local failure, was measured, capped, and logged. Dogfood finding AD-AE-16: no Arena routing surface (route ledger/tier/cost) — probe ran as the minimum deterministic terminal action. | Manav (with Claude) |
| 2026-06-09 | Ran the bounded exemplar-format pass on Nemotron-3-Nano-30B-A3B: added one exact-citation example and one refusal-sentence example to the tracked preflight system prompt, then re-ran `/no_think` through the visible Cortex `run /no_think` control. Receipt **7/8** — meets the §14 ≥7/8 pre-SFT bar without training. Both prior failure classes resolved: 0074 now cites exact source ids (all five answer rows cite distinct exact ids, so the format generalized beyond the exemplar token; noted weak confound that the exemplar id coincides with 0074's expected id, but 0074 also cites a non-exemplar id), and 0087/0088 refusals now carry refusal wording. One new failure: 0082 over-refuses an answerable question whose expected source sits at retrieval rank 1 — the same grounding over-refusal class Nano 9B showed. One iteration only per plan; no further prompt tuning. 30B-A3B is now the leading Advisor base candidate on behavior floor; MoE trainability (§13.D) and the over-refusal row are the open risks. | Manav (with Claude) |
| 2026-06-09 | Ran the §13.C step-5 no-thinking probe: added a `reasoning_mode` path through `preflight.py`, the Arena run endpoint, and a visible Cortex `run /no_think` control, then scored Nano 9B NIM with `/no_think` through the cockpit. Receipt failed 1/8 but eliminated reasoning leakage (0/8); remaining failures are SFT-shaped citation/refusal classes. Nano 9B graduates from "unsuitable as served" to "plausible SFT headroom". | Manav (with Claude) |
| 2026-06-09 | Restored the public product name to **Orionfold Advisor**. Existing `advisor-*` ids stay canonical, and Arena run context should say Advisor. | Manav (with Codex) |
| 2026-06-09 | Ran the first NVIDIA-native visible preflight: cached Nano 9B NIM served on Spark and failed the 8-row Advisor gate 0/8, mainly from reasoning leakage. | Manav (with Codex) |
| 2026-06-09 | Reframed Advisor from "model + retriever" into a packaged governed advisor appliance: harness + model + retriever + corpus pack + Arena workspace. Folded in Cortex, Hermes routing/cost-router, Machine-that-Builds-Machines, Second Brain, NIM/RAG article lessons, and added local-to-hosted routing governance. | Manav (with Codex) |
| 2026-06-09 | Pivoted Advisor away from Unsloth partner proof and into NVIDIA-native flagship model track. Folded in the public corpus, recall, Arena preflight, and Qwen2.5 failure evidence. Added revised base-model scout criteria and preliminary NVIDIA/HF candidate search. | Manav (with Codex) |
