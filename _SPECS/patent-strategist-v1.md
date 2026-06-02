---
project: patent-strategist
version: v1.0
status: locked
created: 2026-05-17
authoritative: Spark
---

# Patent Strategist v1.0 — Project Specification

## 1. Context

### Why this project

Through sessions 1-17 of the Orionfold publishing arc, every shipped vertical (finance / legal / cyber / medical) followed the same pattern: **find an existing domain LLM → quantize → publish GGUF**. Useful but commodity-shaped. The hf-model-scout cycle for vertical #5 (patent prosecution, session 17) ran into a thin field — only 3 documented patent post-training events on HuggingFace at 6-9B, none production-quality, none commercially-licensed for redistribution.

This project flips the pattern: **hand-curate a patent corpus, fine-tune a reasoning model on it, publish dataset + model + benchmark together as a coherent strategist artifact**. The Spark stops being a packaging tool and starts being the *making* tool.

Editorial uber theme alignment: "DGX Spark as personal AI power user / edge AI builder" gets the strongest expression yet — the Spark user becomes an inventor with an IP-savvy co-pilot, not a paralegal automating rejections.

### Use case taxonomy

The model targets **13 use cases across 5 families**, reflecting the full strategist surface (generative + analytical + procedural + educational), not just the original prosecution-defense framing:

**Family A — Generative / inventive (the net-new value layer)**
- A1. Patentable-idea brainstorming — given a tech area, generate N novel patent angles + white-space scoring
- A2. Invention disclosure assistant — Socratic Q&A → structured ID form → first-draft claims
- A3. Claim broadening/narrowing — broadest version surviving stated prior art / narrowest maximizing allowance
- A4. Continuation/divisional strategy — propose claim families left unfiled

**Family B — Search / analytical**
- B1. Prior art search query generation — terms + CPC/IPC codes + adjacent-claim hops
- B2. Freedom-to-operate (FTO) analysis — claim-element conflict surfacing
- B3. Invalidity analysis (offensive) — prior art proposals invalidating competitor patents

**Family C — Strategic / portfolio**
- C1. Patent landscape mapping — clusters / leaders / gaps in a tech area
- C2. License negotiation prep — cross-licensing overlap identification
- C3. International filing strategy — EPO/JPO/CNIPA claim particularities

**Family D — Procedural prosecution (the original framing — now one of five)**
- D1. MPEP citation + office-action response
- D2. Patent Bar-style IRAC reasoning
- D3. Prior-art relevance classification

**Family E — Communication / education**
- E1. Patent-to-engineer explainer — claim interpretation for technologists
- E2. Inventor interview — multi-turn extraction Socratic dialogue

### Deliverables

| Artifact | Surface | Week |
|---|---|---|
| `Orionfold/patent-strategist-bench-v0.1` (200 Qs, CC-BY-4.0) | HF Dataset | end W2/start W3 |
| RAG-only baseline scores on the bench | embedded in article 1 | end W3 |
| `Orionfold/Patent-Strategist-Qwen3-8B-v1` (LoRA SFT, merged + GGUF quant ladder) | HF Model | end W4 |
| `articles/becoming-a-patent-strategist-on-spark/` (corpus + bench piece, ~380 lines) | published article | end W3 |
| `articles/becoming-a-patent-strategist-on-spark-part-2/` (fine-tune + RAG comparison, ~420 lines) | published article | end W4 |
| `fieldkit` v0.4.3 release (promoted `mcq_letter` + 4 new scorers + `format='patent-strategist'`) | PyPI | end W2 |

## 2. Decisions

### 2.1 Locked decisions

| # | Decision | Value |
|---|---|---|
| 1 | Bench distribution | 60% strategic/analytical + 40% procedural |
| 2 | RAG sequencing | RAG-only baseline first; fine-tune second |
| 3 | Article shape | 2-part series, linked via `series:` frontmatter |
| 4 | Project scope | v1.0 balanced, 4 weeks PT, ~85-95 hours |
| 5 | Base model | DeepSeek-R1-0528-Qwen3-8B |
| 6 | Training framework | HuggingFace TRL (`SFTTrainer` + `peft.LoraConfig`) |
| 7 | LoRA recipe (conservative) | q+k+v+o targets, r=16, α=32, lr=1e-4, 2 epochs, 100% `<think>`-structured + 10% reasoning anchor |
| 8 | Bench license | CC-BY-4.0 |
| 9 | Synthetic seed | Claude API (Orionfold owns outputs per Anthropic Commercial Terms) |
| 10 | Inference UX | Deployment guide only (llama-server quickstart in README); defer Gradio Space to v1.1 |
| 11 | Fine-tune orchestration | Inline scripts for v1.0; promote to `fine-tune-curator` skill on v1.1+ if recipe reuses |

### 2.2 Base model: DeepSeek-R1-0528-Qwen3-8B

**HuggingFace ID:** `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B`

**Why this won (three rounds of reconsideration):**
1. Latest 8B-class DeepSeek distill (May 2025; verified no V3.2-Distill or R2-Distill exists as of early 2026)
2. AIME 2024: 86% (vs R1-Distill-Llama-8B's 71%) — patent reasoning will benefit from this
3. Native `<think>...</think>` reasoning traces — examiners, inventors, attorneys *want* to see the why; product differentiation surface
4. 131K native context — full MPEP sections + claim + prior art fit comfortably in oracle mode
5. Same arch as our shipped medical card (II-Medical-8B = Qwen3-8B base) — Spark conversion path already validated
6. Community GGUF quants exist (bartowski, unsloth) proving conversion path
7. License is clean: MIT distill + Apache 2.0 via Qwen3 base — no naming prefix, no attribution string, no MAU threshold

**Costs accepted:**
- Loses kim's Llama-3-8B-patent-small-dataset head-to-head (different arch family; still report kim's results as a baseline data point with explicit "different arch" caveat)
- Loses bar-exam paper precedent (was Llama-3-specific)
- Inference slower per question (must emit reasoning trace; `LLAMA_CLI_NPREDICT≥1024` per `[[feedback_reasoning_model_npredict]]`)
- Bench `mcq_letter` scorer needs `<think>`-aware extension (useful — promotion to `fieldkit.eval` v0.4.3 per `[[feedback_keep_scorer_local_until_reuse]]`, 3rd reuse)

**Spark envelope (LoRA SFT, batch=2, seq=2048, BF16):**
- Frozen base: 16 GB
- LoRA adapters: 1.5 GB
- Optimizer state (adapters only): 3 GB
- Activations + gradients (with checkpointing): ~25 GB
- **Peak: ~45 GB** within practical ~80 GB envelope

QLoRA explicitly rejected: 4-bit base loading degrades reasoning behavior on R1-distill family (arXiv 2505.02390). BF16 LoRA fits comfortably; spend the memory.

### 2.3 Model name

`Orionfold/Patent-Strategist-Qwen3-8B-v1` for the HF repo (model card). GGUF variants ship in the same repo per `hf-publisher` skill convention. Family will mirror: `Orionfold/Patent-Strategist-Qwen3-8B-v1-GGUF` may also be created if separating quant variants from FP16 simplifies the README.

### 2.4 Q8_0 anomaly testing nuance

The medical vertical (II-Medical-8B) is also Qwen3-8B-based. Patent will be the second Qwen3 sample on the chat-tune-only side of the Q8_0 anomaly split. This weakens arch-diversity (n=3 chat-tune-only across 2 arches: Mistral + 2× Qwen3) but **strengthens the training-shape hypothesis test**: same arch + similar training shape → if Q8_0 still shows ~75% faster, we've eliminated arch as a confound for the Q8_0 anomaly. n=2-with-arch-controlled is more informative than n=2-with-different-arches for that specific hypothesis.

## 3. Architecture

### 3.1 Training framework: HuggingFace TRL

**`SFTTrainer` + `peft.LoraConfig`** is where R1-distill LoRA recipes live in 2025-2026.

Justification:
- DeepSeek-R1-Distill family ships its public LoRA recipes through TRL/PEFT
- `<think>...</think>` token preservation needs `dataset_text_field` + `packing=False` and explicit non-stripping — TRL's `formatting_func` API is exactly the right hook
- Spark `pytorch:25.11-py3` image has working `transformers` + `trl` + `peft` + flash-attn 2.7.4.post1 (per `[[reference_pytorch_2511_image_contents]]`)
- This repo's `articles/lora-on-your-own-qa-pairs` already demonstrates working HF PEFT + Qwen2.5-3B on Spark (69s training run, no aarch64 drama documented) — strongest signal that the path works

**Rejected alternatives:**
- NeMo Framework — tuned for Nemotron bases, not Llama/Qwen-derived; YAML config friction; checkpoint conversion (megatron ↔ HF) overhead
- llama-factory — kim's failed Llama-3-8B-patent precedent; debugging YAML-driven config layer is harder than owning ~120 LOC TRL
- unsloth — aarch64 support undocumented (per memory `[[feedback_*]]`)
- TorchTune — newer, less stable, more risk

### 3.2 New scripts (~1500 LOC total)

| File | Purpose | LOC |
|---|---|---|
| `scripts/build_patent_corpus.py` | PatentMatch + BIGPATENT + GPat (BigQuery) + MPEP scrape + USPTO OARD pulls; writes to `/home/nvidia/data/corpus/patent/{patentmatch,bigpatent,gpat,mpep,oa}/*.jsonl` | ~250 |
| `scripts/build_rag_index.py` | bge-small embedder + FAISS persist at `/home/nvidia/data/rag/patent-bge-small/` | ~180 |
| `scripts/seed_patent_bench.py` | Claude API seeder, prompts per family, writes `/home/nvidia/data/eval-benches/patent-strategist/seed-<family>.jsonl` | ~200 |
| `scripts/review_patent_bench.py` | Human-review CLI (TUI or line-iterator) flipping `reviewed: true` + attaching `rubric_notes` | ~120 |
| `scripts/run_rag_baseline.py` | RAG-only eval driver; runs `VerticalBench` against R1-0528-Qwen3-8B + FAISS layer | ~150 |
| `scripts/probe_reasoning.py` | 20-question reasoning-preservation probe (presence rate / length / quality score) | ~150 |
| `scripts/g3_train_first_lora.sh` | Bash orchestrator mirroring `g3_build_first_quant.sh` (env-overridable; stages: prepare → train → merge → handoff-to-quant) | ~250 |
| `scripts/g3_train_first_lora.py` | TRL trainer body; loads R1-0528-Qwen3-8B in BF16, attaches PEFT config, uses `fieldkit.training.WeightDeltaTracker` | ~300 |
| `scripts/g3_merge_adapter.py` | peft merge → BF16 safetensors → handoff path for `g3_build_first_quant.sh` | ~80 |
| `scripts/run_eval_matrix.py` | 6-config × 3-mode comparison driver; materializes per-config prompts; writes per-cell JSONL | ~220 |

### 3.3 fieldkit extensions (drives v0.4.3 release)

**`fieldkit/src/fieldkit/eval/vertical.py`** — add `format='patent-strategist'` branch:

```python
# Required JSONL fields for format='patent-strategist'
{
  "qid": str,           # stable identifier
  "question": str,
  "family": "A"|"B"|"C"|"D"|"E",
  "use_case": str,      # e.g. "A1", "D2"
  "scoring_mode": "closed"|"retrieval"|"oracle",
  "gold_label": str,    # MCQ letter for D; free-text for A/B/C/E
  "options": list[str], # MCQ only (Family D + Family E quiz subset)
  "context": str|None,  # populated by retrieval/oracle modes
  "oracle_context": str|None,  # ideal-retrieval reference (MPEP / cited prior art)
  "rubric": dict|None,  # for non-MCQ rows; keys vary by scorer
  "reviewed": bool,
  "tags": dict          # jurisdiction, art-unit, year-band, etc.
}
```

Scorer-dispatch table (module-level dict in `vertical.py`):
- Family D MCQ rows → `mcq_letter`
- Family A claim-broadening/narrowing → `patent_claim_validity`
- Family D office-action response → `office_action_argument`
- Family D IRAC scenarios → `irac_structure`
- Family B prior-art-relevance → `prior_art_relevance`
- Family C, E open-ended → `Judge` with rubric (correctness 0-5 + faithfulness 0-1)

**`fieldkit/src/fieldkit/eval/__init__.py`** — promote `mcq_letter` (3rd reuse triggers promotion per `[[feedback_keep_scorer_local_until_reuse]]`):

```python
def mcq_letter(predicted: str, expected: str, *, strip_think: bool = True) -> float:
    """Score MCQ letter responses, with <think>-aware extraction for reasoning models."""
```

When `strip_think=True` (default), regex-strip `<think>.*?</think>` (DOTALL, non-greedy) from `predicted` *before* the existing three-step letter decision (one-letter / "answer: X" / first bounded [A-D]).

Cyber + medical merge scripts get one-line import swap: `from fieldkit.eval import mcq_letter` replacing local copies. Backward compatible — `strip_think=True` is a no-op regex match on cyber/medical text lacking `<think>` tags.

**Four new scorers** (all in `fieldkit/src/fieldkit/eval/__init__.py`):

- `patent_claim_validity(predicted, expected, *, rubric)` — PatentScore-methodology 7-dim rubric (novelty, non-obviousness, written-description, enablement, indefiniteness, subject-matter-eligibility, dependent-claim-structure). LLM-judge backed via `fieldkit.eval.Judge`. Rubric prompt at `fieldkit/src/fieldkit/eval/rubrics/patent_claim_validity.md`. **Note: PatentScore methodology only, NOT data reuse — that paper's license is unclear.**
- `office_action_argument(predicted, expected, *, rubric)` — 4-dim: rejection-type identification, statutory citation accuracy, argument-structure (CFR/MPEP citation correctness), persuasiveness
- `irac_structure(predicted, expected)` — 4-checklist deterministic (no LLM judge): regex/keyword presence for Issue / Rule / Application / Conclusion. Returns 0.0-1.0 in 0.25 steps
- `prior_art_relevance(predicted, expected)` — accepts ranked list[str] + gold ranking → returns `spearman_rho` + `mse_likert` floats; bench averages the rho

**Promotion ladder for v0.4.3:**
1. Lift `mcq_letter` into `fieldkit/src/fieldkit/eval/__init__.py` with `<think>` extension
2. Add to `__all__`
3. Delete local copies in `scripts/g3_preflight_bench.py:89` and `scripts/g3_measure_variants.py:105`; replace with imports
4. Add unit tests at `fieldkit/tests/eval/test_mcq_letter.py` (bare letter / "answer: X" / noisy prose / `<think>` wrapped / empty / malformed)
5. Bump to v0.4.3, regenerate CHANGELOG, run `fieldkit-curator` skill in `interactive` mode

### 3.4 RAG baseline stack

- **Embedder:** `BAAI/bge-small-en-v1.5` — 384-dim, 33M params, MIT-licensed, ~80 MB. Local CPU/GPU embedding fast on Spark
- **Vector store:** FAISS flat IVF index, on-disk at `/home/nvidia/data/rag/patent-bge-small/index.faiss` + `chunks.parquet` sidecar. Avoiding pgvector for v1.0 (long-lived Postgres container is operational surface we don't need); `fieldkit.rag.LocalFAISSPipeline` becomes a v0.5 fieldkit follow-up
- **Chunking:**
  - MPEP at semantic-section (~800 tokens, overlap 100)
  - PatentMatch claim ↔ prior-art pairs as atomic chunks (no chunking)
  - BIGPATENT abstracts as atomic (single chunk per patent)
  - Google Patents US subset filtered by IPC class + last-10-years recency — abstract + claim 1 per patent
- **Generator:** DeepSeek-R1-0528-Qwen3-8B served via `llama-server` at Q5_K_M, called through `fieldkit.nim.NIMClient` (OpenAI-compatible). Temperature 0.6 (R1-Distill recommended), `max_tokens=4096`
- **Retrieval:** top-k=8, no reranker in v1.0 (NVIDIA `nv-rerankqa-1b-v2` in `fieldkit.rag` is an NVIDIA-API call; v1.1)
- **Eval surface:** same bench via `VerticalBench.from_jsonl(format='patent-strategist')`

### 3.5 Eval matrix for article 2

**6 configs × 3 scoring modes = 17 cells** (closed-book skips RAG configs):

| Config | Closed | Retrieval | Oracle |
|---|---|---|---|
| C1: Llama-3.1-8B-Instruct (control) | ✓ | ✓ | ✓ |
| C2: kim's Llama-3-8B-patent (competitor, different-arch caveat) | ✓ | ✓ | ✓ |
| C3: DeepSeek-R1-0528-Qwen3-8B zero-shot | ✓ | ✓ | ✓ |
| C4: C3 + FAISS RAG (no FT) | — | ✓ | ✓ |
| C5: C3 + our LoRA (no RAG) | ✓ | ✓ | ✓ |
| C6: C3 + LoRA + FAISS RAG (full stack) | — | ✓ | ✓ |

**Wall-clock estimate:** R1-Distill configs emit ~600-1500 reasoning tokens per Family A/D question → ~50s/question × 200 Qs ≈ 2.8h per R1-Distill config. Non-reasoning configs (C1, C2) ≈ 45min/config. Matrix total: 4 × 2.8h + 2 × 0.75h ≈ ~13 hours; add 30% buffer → **~17 hours over 2-3 overnight runs in W4**.

**Bench-equivalence checks:** identical prompts byte-for-byte across configs (asserted by `hashlib.sha256` of prompt list per mode), same temperature (0.6), same `max_tokens` (4096), same minimal system prompt. The `run_eval_matrix.py` script writes a `prompt-hash.json` per mode for cross-config validation.

## 4. Reasoning preservation strategy

R1 (reasoning trace degradation during LoRA) is the project-killer-class risk. The whole differentiation thesis depends on the model continuing to emit `<think>...</think>` traces post-fine-tune. Mitigation stack:

### Layer 1 — Conservative LoRA target selection

```python
peft.LoraConfig(
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],  # attention only, NOT MLP
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
)
```

Per 2024-2026 reasoning-preservation literature: MLP targeting (`gate_proj` + `up_proj` + `down_proj`) is the dominant `<think>`-degradation source. Attention projections are recoverable; MLPs aren't. All-linear targeting is what produced kim's reasoning-collapse symptom on related Llama-3 base.

### Layer 2 — Training data structure mandate

100% of patent training examples carry `<think>chain</think>answer` structure. No direct-answer training examples in the SFT set.

Claude API seeder prompt explicitly requires both halves:

```
For each patent prosecution question, generate:
<think>
[step-by-step reasoning: identify the claim element, cite the MPEP section,
apply the rule, conclude]
</think>
[final answer in 1-3 sentences]
```

Mixed-structure training (some `<think>`, some direct) is worse than uniform — model learns *when* to skip reasoning, which we don't want.

### Layer 3 — Reasoning anchor mix-in

10% of training examples are non-patent reasoning samples — AIME 2024, MATH, GPQA. All MIT/Apache 2.0 licensed, commercial-OK.

Keeps `<think>` distribution sharp on questions where patent expertise isn't activated; prevents collapse into "always think about patents, never reason generally."

### Layer 4 — Hyperparameter conservatism

- **Learning rate:** 1e-4 (not TRL default 2e-4)
- **Schedule:** cosine, warmup_ratio=0.05
- **Epochs:** max 2
- **Effective batch:** 16-32 with gradient accumulation
- **Precision:** bf16 (NOT QLoRA per arXiv 2505.02390 — 4-bit base degrades reasoning on R1-distill family)
- **Checkpoint frequency:** every 200 steps

### Layer 5 — Active reasoning-preservation monitoring

20-question probe runs every 200 training steps. Three metrics tracked across checkpoints:

| Metric | Definition | Pass threshold (relative to pre-FT baseline) |
|---|---|---|
| `think_presence_rate` | % responses containing `<think>...</think>` block | ≥ 90% |
| `think_token_length` | mean tokens between `<think>` and `</think>` | ≥ 75% |
| `think_quality_score` | LLM-judge (Claude) on reasoning coherence, 0-5 | ≥ 80% |

Probe composition: 10 AIME/MATH/GPQA (general reasoning), 5 patent IRAC scenarios (in-domain), 5 strategic prompts (Family A use cases).

**Hard rule:** if ANY metric drops below threshold at a checkpoint, revert to last-good checkpoint, diagnose, restart.

### Layer 6 — Early-stopping discipline

Pick the **earliest** checkpoint that still reasons well, NOT the lowest-loss checkpoint.

Conventional LoRA wisdom (ride the loss curve down) vs reasoning preservation (stop the second we have enough patent adaptation) are in tension. We resolve in favor of reasoning every time.

### Day-1 (Week 3) smoke test — P0 derisking action

Before scaling to 20+ hour overnight runs, 3-hour validation:

```bash
# 1. Measure baseline reasoning probe on pre-FT model
python scripts/probe_reasoning.py \
  --model deepseek-ai/DeepSeek-R1-0528-Qwen3-8B \
  --probe-set probes/reasoning-preservation-20q.jsonl \
  --output probes/baseline.json

# 2. Run 200-step smoke fine-tune on 50 examples with smaller-than-final LoRA
MODEL_ID=deepseek-ai/DeepSeek-R1-0528-Qwen3-8B \
DATASET=corpus/smoke-50.jsonl \
LORA_TARGETS=q_proj,k_proj,v_proj,o_proj \
LORA_R=8 LORA_ALPHA=16 LR=3e-5 \
MAX_STEPS=200 CHECKPOINT_EVERY=50 \
PROBE_EVERY=50 \
./scripts/g3_train_first_lora.sh
```

What's validated in 3 hours:
1. **Stack works:** TRL imports, LoRA attaches, training loop runs on aarch64/CUDA-13
2. **Tokenizer surgery survives (R14):** `<think>` tokens persist through tokenization, training, generation — verify by inspecting token IDs in a probe response
3. **Reasoning preserved:** probe scores at step 200 within tolerance of baseline
4. **Adapter shape correct:** `WeightDeltaTracker` confirms expected modules updated, MLPs untouched
5. **Smoke loss converges:** training loss drops meaningfully (signal the recipe is learning *something*)

If any check fails: 4 days budget to fix before W3-Friday overnight runs. If all pass: scale to full 25k-example overnight with confidence.

### Fallback ladder if reasoning degrades despite Layer 1-6

1. **Tighter recipe:** drop to r=8, target q+v only, lr=3e-5
2. **Regenerate training data:** ensure 100% strict `<think>...</think>` structure, replace borderline examples
3. **Two-pass adapter inference:** ship base + adapter separately, blend with alpha=0.6 at inference (reasoning recovers, inference heavier)
4. **Pivot to RAG-only v1.0:** ship bench + 1 article on RAG-on-R1-distill; defer fine-tune to v2.0 (Plan Agent B's Alt-A path)

## 5. Bench design

### 5.1 Composition: 200 Qs across 5 families

| Family | Use cases | Q count | Scoring approach |
|---|---|---|---|
| A — Generative/inventive | A1-A4 | 50 | LLM-judge rubric (`patent_claim_validity`) + human-review |
| B — Search/analytical | B1-B3 | 40 | `prior_art_relevance` (Spearman) + LLM-judge |
| C — Strategic/portfolio | C1-C3 | 20 | LLM-judge rubric (correctness 0-5 + faithfulness 0-1) |
| D — Procedural prosecution | D1-D3 | 60 | `mcq_letter` (40 MCQ) + `office_action_argument` + `irac_structure` (20 free-text rubric) |
| E — Communication/education | E1-E2 | 30 | LLM-judge rubric + `mcq_letter` for quiz subset |

Total strategic/analytical (A+B+C+E generative): **130 (65%)**. Total procedural: **70 (35%)**. Approximates the locked 60/40 split with slight strategic emphasis.

### 5.2 3-way scoring split per question

Each question is evaluated in three modes (mirrors PANORAMA):

- **Closed-book:** no context provided; tests model's internal knowledge
- **Open-book / retrieval:** RAG-retrieved context (top-k=8 from FAISS index)
- **Oracle:** ideal context (the specific MPEP section / prior art passage) hand-curated at bench-authoring time

Closed-book skipped for RAG configs (it's not a meaningful comparison).

### 5.3 Source allocation

| Source | Q count target | License | Notes |
|---|---|---|---|
| MPEP-derived (Family D MCQ + D2 IRAC) | 50 | Public domain (17 USC §105) | Scrape eMPEP; section IDs as gold labels |
| PatentMatch-derived (Family B B1+B3) | 30 | CC-BY-4.0 | Atomic pair → claim+prior-art relevance question |
| BIGPATENT-derived (Family A claim-drafting) | 20 | CC-BY-4.0 | Abstract → draft claim 1 task |
| Google Patents BigQuery (Family C landscape) | 20 | CC-BY-4.0 | IPC-class subsets, recent-10y filter |
| USPTO OARD (Family D office-action response) | 20 | Public domain | Real Non-Final Rejection text → draft response |
| Claude-seeded synthetic (Families A1, A2, A3, A4, E1, E2) | 60 | Orionfold-owned (Anthropic Commercial Terms) | Generative families where no public ground truth exists |

### 5.4 Bench publication

- **Path:** `Orionfold/patent-strategist-bench-v0.1` on HuggingFace Datasets
- **License:** CC-BY-4.0 (matches all source licenses; signals open contribution)
- **README structure:** sources cited with attribution, task family descriptions, scoring rubric pointers, baseline-numbers table populated by W3 RAG-only baseline run
- **Versioning:** v0.1 (alpha) — explicit "expect breaking changes" disclaimer; v1.0 (stable) after second-vertical validation per R17 (`fieldkit.eval` scorer generalization gate)

### 5.5 Bench discrimination derisking (R5)

**Paired bootstrap scorer** added to the eval matrix: for any two configs evaluated on identical Qs, compute paired-difference 95% CI rather than independent-sample CI. This is a 4-hour scorer addition that converts a thin bench (13 Qs per family-mode cell) into a useful one without writing more Qs.

Week-2 preflight: run 50-Q preflight against 3 models (C3 base, C1 control, GPT-5 ceiling). If preflight scores within 5pp across families, bench has insufficient discrimination → collapse 5 families to 3 (Strategic Analysis / Prior-Art Reasoning / Procedural).

## 6. Corpus assembly

### 6.1 Commercial-safe sources only

| Source | License | Scale | Role in training mix |
|---|---|---|---|
| **PatentMatch** (HPI, `pakuvis/PatentMatch`) | CC-BY-4.0 | 6.2M EPO claim↔prior-art pairs | 35% — Family B analytical primary |
| **USPTO OARD** (Office Action Research Dataset) | Public domain (17 USC §105) | 4.4M actions 2008-2017 | 25% — Family D procedural primary |
| **USPTO MPEP** (eMPEP scrape) | Public domain | ~2K sections | 15% — Family D anchor, RAG corpus |
| **BIGPATENT** (HF `big_patent`) | CC-BY-4.0 | 1.3M US patents + abstracts | 10% — Family A drafting + general patent style |
| **Google Patents BigQuery** (`patents-public-data`) | CC-BY-4.0 | 90M publications, free 1TB/month | 5% — Family C landscape; US-only filtered |
| **Claude-seeded synthetic** | Orionfold-owned | ~25k examples | 10% — generative/strategic families where no public corpus exists |

### 6.2 Hard blockers (DO NOT USE)

| Source | License | Reason |
|---|---|---|
| HUPD (`HUPD/hupd`) | CC-BY-NC-SA-4.0 | Non-commercial; blocks Orionfold tier |
| PANORAMA (`LG-AI-Research/PANORAMA`) | CC-BY-NC-4.0 | Non-commercial |
| PatenTEB | CC-BY-NC-SA-4.0 | Non-commercial |
| The Pile USPTO subset | Mixed/pirated risk | Post-Bartz v. Anthropic (2025); source USPTO directly |
| EPO OPS commercial tier | €2,800/yr | Cost prohibitive; PatentMatch covers EPO-side |
| PatentMatch raw redistribution beyond bench attribution | CC-BY-4.0 OK to use, not gated | Just cite + attribute |

### 6.3 Citation-only benchmarks

These benchmarks have unclear licenses for data redistribution. Use methodology + cite, **do not include their data in our bench**:
- **PatRe** (480 office-action ↔ rebuttal cases)
- **PILOT-Bench** (PTAB IRAC, 18K cases)
- **PatentScore** (methodology citation OK for `patent_claim_validity` rubric design)
- **LegalBench** (per-task licensing audit before pulling any)

Author-permission emails are the v1.1+ unblock path if we want their cases later.

### 6.4 Snapshot protocol (R10 mitigation)

Week-1 corpus pull writes `evidence/patent-strategist/corpus-snapshot.json`:

```json
{
  "pulled_at": "2026-05-...",
  "sources": {
    "patentmatch": {
      "hf_repo": "pakuvis/PatentMatch",
      "commit_sha": "abc123...",
      "license": "CC-BY-4.0"
    },
    "bigpatent": {...},
    ...
  }
}
```

Bench dataset card references this snapshot. If a source license drifts mid-project, we have provable acquisition-state for fair-use defense under Bartz precedent.

## 7. Risks and contingencies

### 7.1 Risk register

| ID | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| R1 | Reasoning trace degradation under LoRA | **High** | **High** | 6-layer stack (§4) | Two-pass adapter inference; pivot to RAG-only v1.0 |
| R2 | EPO (PatentMatch) corpus undershoots US Family D | High | Med | 25% USPTO OARD + 15% MPEP weighting | Re-split bench 70/30 strategic/procedural |
| R3 | TRL/aarch64/CUDA-13 instability | Med | High | Day-1 W3 smoke test (§4) catches early | llama-factory → NeMo as sequential fallbacks |
| R4 | Llama Community License compliance | **N/A** | N/A | **Resolved by switch to R1-0528-Qwen3-8B (MIT+Apache)** | N/A |
| R5 | Bench too small for discrimination | Med-High | High | Paired bootstrap scorer (§5.5) + W2 preflight | Collapse 5→3 families; or scale to 300 Qs |
| R6 | RAG dominates fine-tune | Med | Med (story-level) | Pre-commit to "where FT still wins" framing | Both articles structured for either outcome |
| R7 | GGUF `<think>` stop-token breakage | Med | Med | 1h preflight on 5 reasoning prompts before HF push | Ship LoRA adapter only (no GGUF); defer GGUF to v1.1 |
| R8 | 4-week scope creep | High | Med | Hard cut lines per week (§9) | Ship v0.9-beta with explicit gap list |
| R9 | HF upload reliability | Low (bench) / Med (model) | Low | `upload_large_folder` + `num_workers=1` per `[[feedback_hf_upload_resilient_api]]` | Retry pattern; multi-day push window if needed |
| R10 | Corpus license drift | Very low | High if hits | Snapshot URLs + commit hashes (§6.4) | Defensible under Bartz fair-use precedent |
| R11 | kim baseline unfairness | High (perception) | Low-Med | Triple baseline (vanilla L3.1 + R1-Qwen3 zero-shot + kim) | Explicit caveat in eval article |
| R12 | Synthetic-corpus contamination of bench | Med | Med | Hand-author bench Qs in isolated Claude session w/ strict prompt | If overlap detected, regenerate offending Qs |
| R13 | No domain-expert validation | High | Med | Schedule 1-2h patent-attorney review at end of W2 ($300-500) | Defer review to v1.1 with explicit "not legally reviewed" disclaimer in v1.0 |
| R14 | Tokenizer surgery on `<think>` | Low | High | Unit test in W3 smoke kit: tokenize + decode roundtrip | Explicitly use R1-0528-Qwen3-8B's chat_template, not Qwen3 base |
| R15 | Catastrophic forgetting of non-patent capability | Med | Med | 10% AIME/MATH/GPQA anchor in training mix | Probe checkpoints with AIME questions |
| R16 | Article narrative pre-committed to result | Med | Low (with R6 framing) | Both articles outlined to ship either outcome | Article 2 frame is "we tested X vs Y, here's what we found" — agnostic |
| R17 | fieldkit scorer promotion gated on cross-vertical reuse | Low | Low | Don't promote `patent_claim_validity` etc. to fieldkit until 2nd vertical needs them | Keep new scorers local to patent until 2026-Q3 |

### 7.2 Top 3 must-do early actions

1. **Day-1 W3 reasoning preservation smoke test (R1 + R3 + R14)** — 3 hours; validates entire stack before scaling
2. **W2 preflight on 50-Q bench against 3 models (R5)** — 4 hours; decides whether to collapse families or scale up
3. **Schedule W2-end patent-attorney review (R13)** — 1-2 hours external review; book early to land in W2 window

### 7.3 Hard cut lines per week

- **End of W1**: Bench v0.1 skeleton + RAG index + spec finalized. Cut if: corpus pull failed or fieldkit ext didn't land
- **End of W2**: RAG baseline scored on bench. **Cut if:** RAG dominates 4/5 families → pivot to "RAG-product" article + defer fine-tune to v2.0
- **End of W3**: Smoke test passed + overnight LoRA complete. **Cut if:** reasoning collapsed and Layer 5+6 didn't recover → ship RAG + bench, defer fine-tune
- **End of W4**: v1.0 or v0.9-beta. **Never v0.5.**

## 8. Week-by-week task plan

### Week 1 (~22 PT hours)
- **T1** (2h): Scaffold `_SPECS/patent-strategist-v1.md` (this file) — *done as part of plan-mode exit*
- **T2** (6h): `scripts/build_patent_corpus.py` — PatentMatch + BIGPATENT + GPat + MPEP + OARD pulls + snapshot.json
- **T3** (3h): `scripts/build_rag_index.py` — bge-small + FAISS persist
- **T4** (2h): Add `format='patent-strategist'` branch to `fieldkit/src/fieldkit/eval/vertical.py`
- **T5** (1.5h): Promote `mcq_letter` to `fieldkit.eval.__init__` with `<think>` extension + tests

Parallelizable: T2/T3 run in background; T4/T5 are fieldkit edits independent of corpus.

### Week 2 (~25 PT hours)
- **T6** (4h): Add 4 new scorers + rubric files (`patent_claim_validity`, `office_action_argument`, `irac_structure`, `prior_art_relevance`)
- **T7** (1h): Cut fieldkit v0.4.3 via `fieldkit-curator` skill in interactive mode (CHANGELOG + tag + PyPI)
- **T8** (5h): `scripts/seed_patent_bench.py` — Claude API seeder for 5 families
- **T9** (12h): `scripts/review_patent_bench.py` + manual review of 200 Qs to v0.1 (peak labor)
- **T10** (4h): `scripts/run_rag_baseline.py` + run RAG-only baseline (3 modes × bench)
- **External**: Book patent-attorney review of bench (R13) for end-W2

### Week 3 (~16 PT hours + overnight wall-clock)
- **T11** (10h): `scripts/g3_train_first_lora.sh` + `g3_train_first_lora.py` + `g3_merge_adapter.py`
- **T11.5** (3h): **Day-1 smoke test** with conservative-but-smaller LoRA on 50 examples — validates R1+R3+R14
- **T12** (24h wall, ~4h hands-on): Friday-night overnight LoRA on full 25k examples → quant via `g3_build_first_quant.sh` → measure variants

### Week 4 (~22 PT hours + overnight wall-clock)
- **T13a** (8h): `scripts/run_eval_matrix.py` + run 6-config × 3-mode matrix (~17h overnight)
- **T13b** (10h): Draft both articles, embed eval matrix tables
- **T13c** (4h): HF publish — model card + dataset card + GGUF push via `upload_large_folder`, attribution strings, license declarations

### Total: ~85 PT hands-on + 41h overnight wall-clock = fits 85-95h envelope

## 9. Publish checklist

### 9.1 Bench dataset card (`Orionfold/patent-strategist-bench-v0.1`)

```yaml
---
license: cc-by-4.0
language:
- en
tags:
- patent
- legal
- reasoning
- benchmark
- spark-tested
size_categories:
- n<1K
pretty_name: Patent Strategist Bench v0.1
---
```

Required sections in README:
- Sources cited per-row provenance
- Task family descriptions (A-E)
- Scoring rubrics (link to fieldkit.eval scorer docs)
- Baseline numbers table (RAG-only baseline from W3)
- Corpus snapshot reference

### 9.2 Model card (`Orionfold/Patent-Strategist-Qwen3-8B-v1`)

```yaml
---
license: mit
language:
- en
base_model:
- deepseek-ai/DeepSeek-R1-0528-Qwen3-8B
- Qwen/Qwen3-8B
library_name: transformers
pipeline_tag: text-generation
tags:
- patent
- legal
- reasoning
- lora
- spark-tested
---
```

Required sections:
- Attribution: credit DeepSeek-R1-0528 + Qwen3-8B
- License declaration: MIT (inherits Apache 2.0 from Qwen3 base; both stack cleanly)
- Spark-tested numbers table (5 variants × 5 metrics, matching cyber/medical/legal/finance cadence)
- Variant picker table
- Quickstart code blocks (huggingface-cli, llama-server with `LLAMA_CLI_NPREDICT≥1024` flag, llama-cpp-python in-process, LM Studio)
- Example reasoning-trace output (showcasing the `<think>` differentiation)
- Cross-link block to the 4 other Orionfold cards (finance, legal, cyber, medical) per `card-polish.md` convention
- Launch-list footer line per `card-polish.md` v3 (orionfold.com)

### 9.3 HF upload protocol

Per `[[feedback_hf_upload_resilient_api]]`:
```python
from huggingface_hub import upload_large_folder
upload_large_folder(
    folder_path="/tmp/orionfold-stage/patent-strategist-qwen3-8b-v1/",
    repo_id="Orionfold/Patent-Strategist-Qwen3-8B-v1",
    repo_type="model",
    num_workers=1,  # Spark unified-memory caution
)
```

Pre-push verification: `verify_stage.sh` Check 6 (frontmatter engagement-pull gate) + Check 7/8 if promoted from card-audit Step D.

## 10. Hard cut lines per week (cross-reference §7.3)

See risk register §7.3 for the cut-line table. Cut decisions go in the spec NOW, not the retrospective.

## 11. Change log

| Date | Change | Author |
|---|---|---|
| 2026-05-17 | Initial spec landed (v1.0 locked) | Manav (with Claude planning sessions 1-3) |
| 2026-05-17 | T4 + T5 landed: `format='patent-strategist'` branch in `fieldkit.eval.vertical` + `mcq_letter` promoted to `fieldkit.eval` with `strip_think=True` (3rd vertical reuse). 35 new tests (`tests/eval/test_mcq_letter.py` + `tests/test_vertical_bench.py::TestPatentStrategistFormat`); 414 in suite, all green. **Spec drift caught:** `pakuvis/PatentMatch` (spec §6.1 + §6.4) returns 404 on HF; `BNNT/PatentMatch` substituted as 500-row instruction-shape stop-gap. Canonical HPI-Naumann PatentMatch (6.2M EPO pairs, direct download) needs wiring before W2 bench preflight. | Session 19 |
| 2026-05-17 | T2 scaffolded: `scripts/build_patent_corpus.py` pulls BIGPATENT (10k rows, configs g+h) + PatentMatch substitute (500 rows). MPEP scraper stub, USPTO OARD + Google Patents BigQuery scaffolded as `blocked` (need eMPEP-TOC Playwright pass, USPTO data-portal account, gcloud auth respectively). Snapshot at `evidence/patent-strategist/corpus-snapshot.json`. HF cache redirected to `/home/nvidia/data/.hf-cache` (default `~/.cache/huggingface/hub` is root-owned on this Spark — old container-pull artifact). | Session 19 |
| 2026-05-17 | T3 landed: `scripts/build_rag_index.py` (~290 LOC) — `BAAI/bge-small-en-v1.5` on CUDA → FAISS `IndexFlatIP` (cosine via L2-normalized inner product). End-to-end on 10,500 chunks (BIGPATENT atomic abstracts + PatentMatch atomic instruction rows) in 15.5s; 16.1 MB FAISS + 4.9 MB Parquet sidecar at `/home/nvidia/data/rag/patent-bge-small/`. `--index-type ivf` wired but defaulted off (flat is right at <100k vectors; flip when MPEP + USPTO OARD + GPat land). Sanity retrieval verified cross-source (peanut-planter query → all 3 hits from PatentMatch; semiconductor + wireless queries → top-3 BIGPATENT abstracts at sim 0.77-0.80). RAG-baseline ceiling on patent-strategist queries (sim 0.67-0.74 for "claim broadening / prior art rejection") confirms spec §7.3 W2 cut-line concern — patent-prosecution surface is thin in current corpus, motivates MPEP + OARD T2-followup. Snapshot at `evidence/patent-strategist/rag-index-snapshot.json`. | Session 20 |
| 2026-05-17 | T2-followup-MPEP landed (§6.1 unblock for tier 2 anchor): `pull_mpep` in `scripts/build_patent_corpus.py` rewritten — session-19's "JS-rendered, needs Playwright" claim was wrong; the USPTO **static** mirror at `https://www.uspto.gov/web/offices/pac/mpep/` serves chapter TOCs (mpep-0XXX.html) + per-section pages (s<NNN>.html) directly. Pulled all 29 chapters (100..2900) → 2,047 subsections at h1.page-title granularity (16 MB JSONL + 47 MB cached raw HTML at `/home/nvidia/data/corpus/patent/mpep/`). Chunker side: `chunk_mpep` in `build_rag_index.py` now does spec-prescribed token-aware sliding window (800 tokens, 100 overlap) using the BGE-small tokenizer → 4,437 chunks. **Index rebuilt:** 14,937 vectors (was 10,500), 22.9 MB FAISS. **Retrieval ceiling jumped on Family A/D queries:** "patent claim broadening prior art rejection" 0.74 → 0.82 (top-3 MPEP §706, §804.03, §707); "obviousness 35 USC 103" → top-5 MPEP §2141/§2144/§2145/§2131 at sim 0.79-0.80; "written description 35 USC 112" → §2161-§2164; "double patenting terminal disclaimer" → §804.02/§1490 at sim 0.83-0.85 (new ceiling). Spec §7.3 W2 cut-line concern is now substantially mitigated for Family A + D. Corpus-snapshot writer also fixed to **merge** (not overwrite) so `--sources mpep` doesn't wipe bigpatent/patentmatch provenance. | Session 21 |
| 2026-05-17 | T2-followup-PMatch landed (§6.1 unblock for tier 1 Family B primary): canonical HPI-Naumann PatentMatch (Risch et al. 2021) wired in `pull_patentmatch`. The HPI page at `https://hpi.de/naumann/s/patentmatch` redirects to a HiDrive share at `my.hidrive.com/share/rwfam92omy`. Reverse-engineered the share-token flow (POST `id=<share>` to `/api/share/token` → 4hr Bearer; then GET `/api/file?path=/<name>&access_token=...`) so no Playwright needed for the actual pull. Pulled the ultra-balanced subset (train + test) = **25,340 rows** at `patentmatch-ultrabalanced.jsonl` (32 MB JSONL + 8 MB cached raw zips). Schema: `{claim_id, patent_application_id, cited_document_id, claim_text, cited_text, label (1=X / 0=A), label_letter, date, split}`. Replaces session-19's BNNT 500-row substitute (50× more pairs, EPO-examiner-labeled). Chunker side: `chunk_patentmatch` now produces one atomic chunk per row with `<claim> [PRIOR ART X|A]: <cited>` shape, label/IDs in metadata. **Index rebuilt:** 39,777 vectors (was 14,937), 61.1 MB FAISS + 22.4 MB Parquet. **Family B retrieval validated:** gold prior-art pair returned at rank 0 for all 3 X-labeled test queries (sim 0.83 / 0.92 / 0.95); top-20 X-vs-A label bias is consistent (7-12 X chunks vs 7-8 A in top-20). License: MIT per the project GitHub. | Session 22 |
| 2026-05-17 | T6 landed (§3.3 scorer build-out): four new scorers in `fieldkit.eval` — `patent_claim_validity` (PatentScore 7-dim, LLM-judge backed) + `office_action_argument` (4-dim, LLM-judge backed) + `irac_structure` (deterministic 4-checklist, 0.25-step granularity) + `prior_art_relevance` (Spearman ρ on ranked prior-art lists; `prior_art_relevance_full` exposes the Likert-MSE second metric via `PriorArtRelevanceResult`). Rubric markdown shipped at `fieldkit/src/fieldkit/eval/rubrics/{patent_claim_validity,office_action_argument}.md` and loaded via `load_rubric(name)`; hatch wheel `include` extended to ship `*.md` under that subtree. `vertical.py` gets a live-callable companion `PATENT_STRATEGIST_SCORER_FNS: dict[str, Callable]` alongside the name-only `PATENT_STRATEGIST_SCORERS` — drift-detected by a new `test_scorer_name_map_matches_fn_map` test. **+93 new tests** across `tests/eval/{test_irac_structure,test_prior_art_relevance,test_judge_backed_scorers}.py` + 3 integration tests in `tests/test_vertical_bench.py::TestPatentStrategistFormat`. Suite: **507 passed, 2 skipped** (`pytest -q`, `/tmp/fk` venv); the 2 skips are the long-standing `--spark`-gated live-NIM tests. Promotion-ladder bug caught + fixed in-test: my first Spearman impl was Pearson-on-rank-like-vectors and gave ρ≈0.98 instead of 1.0 on `["a","a","b","c"]` vs `["a","b","c"]` (positional gaps from dup-skipping); now `_rankify` runs on the paired vectors before correlation. The four scorers are now the only blocker between W1 corpus completion and the fieldkit v0.4.3 cut (T7). | Session 23 |

## 12. References

### Internal
- Plan workspace: `/home/nvidia/.claude/plans/yes-let-us-do-temporal-dawn.md`
- Vertical-curator article template: `/home/nvidia/ainative-business.github.io/articles/becoming-a-cyber-curator-on-spark/article.md`
- fieldkit eval module: `/home/nvidia/ainative-business.github.io/fieldkit/src/fieldkit/eval/`
- Cluster-G pipeline: `/home/nvidia/ainative-business.github.io/scripts/g3_*.sh`, `g3_*.py`
- hf-publisher card-polish convention: `/home/nvidia/ainative-business.github.io/.claude/skills/hf-publisher/references/card-polish.md`
- Sync contract: `/home/nvidia/ainative-business.github.io/SYNC-CONTRACT.md`

### External (commercial-safe)
- DeepSeek-R1-0528-Qwen3-8B: https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B
- PatentMatch (HPI): https://hpi.de/naumann/s/patentmatch (CC-BY-4.0)
- BIGPATENT: https://huggingface.co/datasets/big_patent (CC-BY-4.0)
- Google Patents Public Data: https://github.com/google/patents-public-data (CC-BY-4.0)
- USPTO MPEP: https://www.uspto.gov/web/offices/pac/mpep/index.html (public domain, 17 USC §105)
- USPTO Open Data Portal: https://developer.uspto.gov/api-catalog/bdss (public domain)
- BAAI bge-small-en-v1.5: https://huggingface.co/BAAI/bge-small-en-v1.5 (MIT)

### Citation-only benchmarks (do NOT redistribute data)
- PatRe paper: https://arxiv.org/abs/2605.03571
- PILOT-Bench paper: https://arxiv.org/abs/2601.04758
- PatentScore paper: https://arxiv.org/abs/2505.19345
- Bartz v. Anthropic (2025) fair-use ruling: https://www.afslaw.com/perspectives/alerts/landmark-ruling-ai-copyright-fair-use-vs-infringement-bartz-v-anthropic

### Memory cross-references (`[[name]]`)
- `[[feedback_keep_scorer_local_until_reuse]]` — promotion rule for `mcq_letter` (3rd reuse triggers)
- `[[feedback_reasoning_model_npredict]]` — `LLAMA_CLI_NPREDICT≥1024` for R1-distill family
- `[[feedback_chat_vs_continued_pretrain_trap]]` — why we explicitly skip CPT+SFT
- `[[feedback_preflight_bench_before_quant]]` — preflight gate before scaling
- `[[project_q8_anomaly_model_specific]]` — Q8_0 anomaly hypothesis; patent contributes 2nd Qwen3 chat-tune-only sample
- `[[project_spark_unified_memory_oom]]` — Spark envelope hard ceiling
- `[[reference_pytorch_2511_image_contents]]` — TRL framework's container precedent
- `[[feedback_hf_upload_resilient_api]]` — `upload_large_folder` push pattern
- `[[project_orionfold_parent_brand]]` — commercial-tier constraint
- `[[project_publishing_to_ainative]]` — articles publish to ainative.business/field-notes/
