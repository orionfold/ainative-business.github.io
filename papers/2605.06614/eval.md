# SkillOS: Learning Skill Curation for Self-Evolving Agents

## Hypothesis

LLM agents that handle streaming tasks tend to remain one-off problem solvers because the *skill curator* — the policy that decides what to add, update, or delete in an external SkillRepo — has historically been hand-rolled or heuristic. SkillOS pairs a *frozen executor* (an LLM that retrieves and applies skills) with a *trainable curator* (an LLM whose actions are `insert_skill | update_skill | delete_skill` over a markdown skill library), and trains the curator end-to-end with GRPO under a composite reward (task outcome, function-call validity, content quality, compression). The split lets the executor stay frozen while the agent's *memory* gets better over time. The reusable contribution is the curator/executor decoupling and the markdown-file-based SkillRepo schema — both directly extractable as fieldkit primitives.

## Memory budget

Both executor and curator are **Qwen3-8B** at training time (Qwen3-32B / Gemini-2.5-Pro / Gemini-3.1-Flash-Lite tested for generalization).

- `weight_bytes(params_b=8, dtype="bf16")` ≈ 16 GB per model, so 32 GB for executor + curator co-resident.
- GRPO rollouts hold N parallel trajectories with KV cache. At 8B with hidden=4096, n_layers=32, ctx=8192, batch=8 (modest rollout group): `kv_cache_bytes(hidden=4096, n_layers=32, ctx=8192, batch=8, dtype="bf16")` ≈ 17 GB.
- Curator-side gradient + optimizer state for LoRA: ~1.5× the curator's 16 GB ≈ 24 GB. Full-FT curator: ~64 GB and pushes against the 128 GB envelope under unified-memory pressure.

**Spark verdict on memory:** comfortable for inference (32 GB co-resident) and LoRA-curator GRPO (≈ 70 GB total with KV + grads). Full-fine-tune of an 8B curator is borderline — practical answer is LoRA on the curator, executor frozen.

The published training used **16×H100 with verl** for 3–5 days. On a single Spark this is wall-clock-bound, not memory-bound — running a *demo* on AIME24 (~30 problems) is hours, not days.

## Proposed Spark recipe

No public code release found in the paper or trivial GitHub search — this is the dominant blocker (see below). Plausible Spark reconstruction once code lands (or as a from-scratch build):

1. Pull Qwen3-8B from NGC or HF: `huggingface-cli download Qwen/Qwen3-8B-Instruct`.
2. Stand up the executor as a NIM endpoint — capability map confirms NIM serves Qwen3-class models with paged-attention KV economics (see "NIM First Inference on DGX Spark" in the blog).
3. Build the SkillRepo as a flat directory of markdown files: `skills/<skill_name>.md` with YAML frontmatter (`name`, `usage`) + body (workflow, constraints). Retrieval: BM25 over the YAML+body via `rank_bm25` (no embedding model needed — directly mirrors the paper's choice and aligns with DCI-style "no vector index" thinking).
4. Wire the curator policy as a separate Qwen3-8B with a small action head emitting one of `insert_skill | update_skill | delete_skill` + the target file path; train with `verl` (paper's framework) or NeMo-Aligner GRPO. Capability map says fine-tuning ≤ 70B with LoRA is in-envelope; do LoRA on the curator.
5. Composite reward: task_outcome (judge model = Qwen3-32B served on a second NIM, or use the local NeMo Evaluator pattern from "RAG Eval — Ragas + NeMo Evaluator" in the blog) + λf · validity + λu · content_quality + λc · compression. Weights from the paper: λf=1.0, λu=0.1, λc=0.05.
6. Eval on **ALFWorld** subsets (Pick=35, Look=13, Clean=27, Heat=16, Cool=25, Pick2=24 — small enough to run in a few hours on Spark) before scaling to WebShop or DeepMath-103k.

## Blockers

- **No public code as of 2026-05-08** — the dominant blocker. Reproduction is a from-scratch reimplementation of the curator/executor split, which is a multi-week effort, not a weekend.
- BM25 over markdown is fine, but the paper doesn't publicly release initial skill seeds; you'd need to bootstrap the SkillRepo from logged executor traces, which adds a "trajectory→skill" extraction step the paper glosses.
- The 16-GPU verl training schedule is the published path; getting GRPO to converge on a single Spark requires reduced batch size and longer wall-clock — convergence isn't guaranteed to match published deltas, but the *architectural pattern* is what's reproducible.

## Verdict

**spark-feasible** — both Qwen3-8B models fit co-resident in unified memory with comfortable headroom for LoRA GRPO; the only real adaptation is wall-clock (single GB10 vs 16×H100), not memory budget.

## Fieldkit fit

- **Would import:** `fieldkit.nim` (executor + judge served as NIM endpoints), `fieldkit.eval` (reward = composite + task_outcome judge).
- **Would extend:** `fieldkit.rag` — add a `SkillRepo(Pipeline)` subclass over markdown files with BM25 retrieval; reuses the existing `Document`/`Chunk` shapes with `kind="skill"` and a frontmatter parser. The retrieval primitive is a near-clone of the existing rag pipeline, just over a different document type.
- **Would propose for v0.2:** `fieldkit.skills` — first-class types `Skill` (markdown body + YAML frontmatter), `SkillRepo` (directory + BM25 index), `SkillCurator` (policy wrapper for insert/update/delete actions). Pairs with `fieldkit.training.rl` (the v0.2 RL primitives proposed in the A²TGPO eval) — the curator is what gets trained, the SkillRepo is what it acts on. Together this is the *agent memory* primitive the MTBM arc lacks today.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** skill-os-on-spark
- **Suggested stage:** agentic
- **Suggested series:** Machine that Builds Machines
- **Suggested book chapters (MTBM only):** [10]
- **Suggested mtbm_station (MTBM only):** forge
- **Suggested tags:** agentic, skills, reinforcement-learning, grpo, self-improvement, lora, bm25
- **Suggested summary:** Reproducing the SkillOS curator/executor split on a DGX Spark — both Qwen3-8B (frozen executor + LoRA-trained curator) over a markdown SkillRepo with BM25 retrieval, then extracting the pattern into `fieldkit.skills`.
- **Suggested `fieldkit_modules`:** [nim, rag, eval]

## Alignment lens (MTBM only)

- **Ontological** — strong: every Skill is a markdown file with the same YAML schema; the curator's action space is closed (`insert | update | delete`) over a typed object.
- **Teleological** — partial: the composite reward ties curator updates to downstream task outcome, but the four-component blend (success, validity, quality, compression) is itself a balancing problem the paper picks weights for.
- **Behavioral** — partial: the executor's behavior is shaped by which skills are retrieved, but executor refusal/abstention is not modeled — it acts on whatever the curator surfaces.
- **Temporal** — strong: this is the paper's whole point. The SkillRepo is a *durable* artifact that survives across executor sessions; the curator updates it from delayed feedback, so alignment with task success accumulates rather than resetting.
- **Reflexive** — partial: the curator can `delete_skill`, which is a coarse self-correction primitive, but there's no explicit uncertainty estimate per skill.
