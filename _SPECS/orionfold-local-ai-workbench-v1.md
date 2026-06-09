---
project: orionfold-local-ai-workbench
version: v1.0
status: DRAFT (new product-positioning track)
created: 2026-06-09
authoritative: Spark
---

# Orionfold Local AI Workbench v1.0

> Product track: Arena bundled with fieldkit and the surrounding Spark-local
> operator tools as a local AI workbench for building, evaluating, governing,
> and operating enterprise AI artifacts on NVIDIA hardware.

## 1. Pivot

Advisor and Workbench are now separate concerns.

- **Advisor** is the flagship model product: a local expert over Orionfold's
  public corpus.
- **Workbench** is the build/govern/operate environment that creates and proves
  artifacts like Advisor.

The Workbench can later host partner integrations, including non-NVIDIA tools,
but its positioning should start from NVIDIA DGX Spark leverage: local lanes,
NVIDIA runtimes, visible eval gates, source provenance, and rejection receipts.

## 2. Product Thesis

The Workbench is for enterprise AI teams who have NVIDIA infrastructure and need
to turn model experiments into governed local artifacts.

It answers:

```text
What is running, what did it score, what changed, what should be promoted,
and what must be rejected?
```

It is not a hosted MLOps platform and not a notebook collection. It is a local
operator cockpit plus Python package for the DGX Spark-class workflow.

## 3. Bundle Shape

| Layer | Product surface |
|---|---|
| Arena cockpit | Browser UI for lanes, chat, compare, jobs, evals, Cortex/Knowledge, run context, screenshots, and operator gates. |
| fieldkit | Python package for evals, manifests, publishing, RAG, memory, training orchestration, cost/budget, lanes, and evidence. |
| Cortex / Knowledge | Local retrieval, public/private source boundary, provenance, recall gates. |
| LaneTruth / Models | One-lane serving discipline, active lane registry, teardown-first launch, drift detection. |
| Training bridge | NeMo / NVIDIA-native SFT/RL runs with heartbeat artifacts and Arena-visible receipts. |
| Artifact pipeline | Publish or rejection receipts, model/dataset/bench/notebook manifests, field notes. |
| Status beacon | Short operator/cockpit state in `_STATUS.json`. |

Advisor is the first flagship artifact built with this bundle. The Workbench
must also be able to support future customer-style verticals without assuming
the corpus is Orionfold-specific.

## 4. NVIDIA-Native Runtime Posture

The Workbench should expose NVIDIA runtime choices as first-class lanes:

- NIM on Spark for packaged microservice inference.
- TRT-LLM for throughput and NVFP4 / FP8 paths.
- vLLM where it is the practical OpenAI-compatible server.
- llama.cpp where Spark playbooks or GGUF artifacts make it the fastest route.
- NeMo / NeMo AutoModel for fine-tuning and SFT smoke runs.
- Optional hosted NVIDIA Build endpoints as teacher/evaluator/ceiling lanes.

Runtime selection is a product decision, not a hidden script detail. Arena should
show the active runtime, model id, source, port, quantization, and run context.

## 5. Salvaged Dogfood From Advisor

The Advisor workstream produced useful Workbench requirements:

| Finding | Workbench requirement |
|---|---|
| Advisor corpus/bench/recall was initially terminal-only | Workbench needs a corpus/bench/recall receipt surface. |
| Base-model scout lived in `/tmp/hf-scout` outside Arena | Workbench needs model-scout visibility and candidate comparison. |
| Manual Chat packet smoke was not a scored eval row | Workbench needs visible preflight/eval execution tied to run context. |
| Qwen2.5 receipt improved from 4/8 to 5/8 but still failed | Workbench must preserve failed receipts, not only successful demos. |
| Cockpit still carried Kepler/astrodynamics run context | Workbench needs artifact-specific run-context labeling. |
| Prompt/scorer changes changed pass/fail state | Workbench needs versioned evaluator policy and prompt-packet provenance. |

The old Advisor dogfood ledger remains useful history, but new Workbench
findings should be tracked here or in a future `arena-enhancements-v*` spec when
they are broad enough.

## 6. Workbench Backlog

Use `WB-*` IDs for product-track requirements. Promote mature Arena-specific
items into `arena-enhancements-v*`; promote reusable Python package work into a
fieldkit release plan.

| ID | Status | Requirement | Release posture |
|---|---|---|---|
| WB-1 | accepted | Advisor/Product run context: every pane should identify current artifact, model, corpus, eval, and stale/fresh state. | next Arena enhancement |
| WB-2 | accepted | Model scout surface: compare NVIDIA Build + HF candidates, licensing, runtime path, Spark fit, and behavioral preflight. | next Arena enhancement |
| WB-3 | accepted | Corpus boundary surface: show public/private exclusions, source roles, recall gate, and source freshness. | next Arena enhancement |
| WB-4 | accepted | Eval receipt surface: run tracked packet sets through active lane, store row-level score, show failed rows without leaking prompt/output bodies by default. | built for Advisor preflight; generalize |
| WB-5 | proposed | Runtime lane matrix: NIM / TRT-LLM / vLLM / llama.cpp / hosted endpoint, with one-lane guardrails. | next Arena enhancement |
| WB-6 | proposed | NeMo training heartbeat: SFT/RL progress, peak memory, logs, checkpoint, held-out delta. | next fieldkit/Arena release |
| WB-7 | proposed | Rejection receipt: first-class artifact for failed candidates with reason, evidence, and next action. | next fieldkit release |
| WB-8 | proposed | Evaluator-policy versioning: prompt packet version, scorer version, model output hash, and scorer changelog. | next fieldkit release |
| WB-9 | proposed | NVIDIA Build catalog ingest: model/runtime metadata from build.nvidia plus HF sidecars. | future spec |
| WB-10 | proposed | Enterprise demo mode: sanitized sample corpus + canned failed/pass receipts for sales walkthroughs. | product launch input |

## 7. Operator Flow

The Workbench should guide a model artifact through this flow:

```text
select domain
  -> build public/private source boundary
  -> index corpus
  -> generate bench
  -> scout base models
  -> serve candidate lane
  -> run preflight
  -> train / tune if justified
  -> re-evaluate
  -> decide publish or reject
  -> produce receipt
```

Each stage needs:

- visible current state
- source/evidence link
- operator gate if destructive or expensive
- pass/fail status
- next action

## 8. Enterprise Positioning Notes

Workbench messaging should emphasize:

- local AI artifact factory for NVIDIA customers
- inspectable eval and provenance
- one-lane discipline on DGX Spark
- NVIDIA-native runtime leverage
- failed receipts as governance, not embarrassment
- fieldkit as the Python substrate behind the cockpit

Avoid:

- generic "no-code fine-tuning UI"
- "we support every model and runtime equally"
- Unsloth as a first-page integration
- claiming automated promotion without human/operator gates

## 9. Acceptance Criteria

Workbench v1 is credible when:

- Advisor can be presented as an artifact built and governed inside it.
- A failed model candidate can be explained in the UI with row-level evidence.
- The active lane and run context are accurate.
- Model scouting sees NVIDIA-native candidates and open-weight baselines.
- NeMo/NVIDIA training receipts can be surfaced without terminal archaeology.
- fieldkit APIs can reproduce the evidence outside the UI.

## 10. Relationship To Existing Specs

- `spark-arena-v1.md` remains the original Arena architecture spec.
- `arena-enhancements-v1.md` and `arena-enhancements-v2.md` remain concrete
  shipped/in-flight enhancement specs.
- `orionfold-advisor-dogfood-v1.md` is superseded by this broader Workbench
  product track for future dogfood, but remains as the Advisor proof history.
- `orionfold-advisor-nvidia-native-v1.md` is the flagship model track that
  Workbench should support first.

## 11. Change Log

| Date | Change | Author |
|---|---|---|
| 2026-06-09 | Created the local AI Workbench product spec by separating Arena/fieldkit/workbench positioning from the Advisor model track and folding in Advisor dogfood findings. | Manav (with Codex) |
