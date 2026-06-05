# Frontier Scout refresh — 2026-06-05

**Mode:** refresh, **methodology-lens** (not a generic triage sweep). Goal: surface *more areas of exploration*
to improve the end-to-end greenfield-vertical pipeline (domain identification → base-model match →
training-method selection → training-run optimization). Feeds **SHIP-TASK 1** (the methodology-improvement
article) and **`_IDEAS/methodology-improvement-frontiers.md`** — see `HANDOFF.md`.

## ⚠️ Run caveats (honest)

- **arXiv source was DOWN this run** (`arxiv: exhausted retries` — persistent 429 across two attempts).
  Candidate pool is **HuggingFace daily papers only (49 candidates, 30-day window)**. The method-specific
  arXiv long-tail (new GRPO/process-reward variants that don't trend on HF) was **not** swept — re-run when
  arXiv recovers to widen the training-method-selection bucket.
- **This was a curation pass, not a full triage regeneration.** The canonical `papers/papers.json` store
  (last full refresh 2026-05-14) was **left intact** — no lossy hand-merge, no per-paper `paper.md`
  regeneration. The deliverable here is this curated synthesis + the `_IDEAS` seed. Promote any single paper
  with `/frontier-scout eval <id>` if it earns a standalone deep-dive later.

## Recommended exploration areas — mapped to the four flow stages

Each pick: HF upvotes · one-line relevance · Spark-feasibility (grounded in `spark-capabilities.json`).

### Stage (i) — Domain identification (what makes a domain RLVR-amenable)

- **DataCOPE — Unsupervised Skill Discovery for Agentic Data Analysis** (`2606.06416`, ↑10) ·
  *Derives **verifier signals from exploration trajectories** themselves* — the auto-verifier angle on
  "what makes a domain checkable." Directly extends our verifier-IS-the-reward stance: when a clean
  programmatic checker is hard to author, mine it from rollouts. · **Spark-feasible** (inference-time skill
  augmentation, no weight updates).
- **Large Language Models Hack Rewards, and Society** (`2606.04075`, ↑8) ·
  *Reward functions get **gap-exploited** during RL.* The cautionary frame for "is this domain's verifier
  robust?" — our `astro_numeric_match` (±2% boxed-extraction) is exactly the kind of surface metric that
  could be hacked. Argues for an adversarial verifier-stress step in domain qualification. · **Spark-feasible**
  (study/eval shape).

### Stage (ii) — Base-model match (beyond license/arch/size)

- **SePO — Self-Evolving Prompt Agent for System Prompt Optimization** (`2606.04465`, ↑3) ·
  *Conditioning gains **without weight updates**, via evolutionary prompt search.* This is the formal
  generalization of our **few-shot conditioning probe** (the cheap 3-shot proxy that forked the astro
  stick-vs-flip decision). Suggests a richer "conditioning-fixability" diagnostic for base-match: if a
  prompt-search lifts the base, the gap is conditioning, not capability. · **Spark-feasible** (prompt-space
  search, local inference only).

### Stage (iii) — Training-method selection (SFT / DPO / GRPO / RLVR / process-reward)

- **RL Elicits Contextual Learning of Unseen Language Translation** (`2606.06428`, ↑22) ·
  *RL teaches the **meta-skill** of using in-context knowledge rather than memorizing* — a clean, concrete
  instance of the **"verify ≫ demonstrate / compositional-OOD"** case where RL beats SFT. The textbook
  counter-example to our astro null (where SFT sufficed). Strong citation for the SFT-vs-RL decision section. ·
  **Spark-feasible** (the recipe shape; the eval is light, RL run depends on model size).
- **Meta-Cognitive Memory Policy Optimization for Long-Horizon Agents** (`2605.30159`, ↑3) ·
  *Outcome-only RL fails to **localize where intermediate quality degrades** → argues for process-level
  optimization.* Adds the **process-reward vs outcome-reward** axis to our method-selection tree — relevant
  the moment a domain has long chains where the boxed answer hides mid-chain rot. · **Spark-feasible** (LoRA-
  scale policy opt).
- **OPRD — On-Policy Representation Distillation** (`2606.06021`, ↑4) ·
  *Distill teacher **hidden states**, not just output logits — kills MC-KL sampling variance over Qwen's
  ~150k vocab.* A third lane beside SFT/RL: when you have a strong teacher, representation-distillation may
  beat output-SFT. Explicitly names Qwen-vocab variance (our base family). · **Spark-feasible** (needs teacher
  + student resident — tight at 8B+8B; single-lane scheduling applies).

### Stage (iv) — Training-run optimization (efficiency, degenerate steps, curriculum, budgets)

- **The Shadow Price of Reasoning — CLEAR** (`2606.03092`, ↑6) ·
  *Per-query **optimal thinking-budget allocation** via a global shadow price + "rational abandonment."*
  Directly attacks our **AV-R1 truncation / flat `FK_RL_MAX_TOKENS=2048`** crudeness — allocate the token
  budget per-query by marginal utility instead of a flat cap. High-value run-optimization lever. ·
  **Spark-feasible** (inference-time budget policy).
- **Rethinking Continual Experience Internalization for Self-Evolving Agents** (`2606.04703`, ↑15) ·
  *Multi-iteration experience learning causes **progressive capability collapse**; principle-level experience
  is more durable than instance-level.* Maps to our degenerate-step / multi-round-RL collapse worry and to
  curriculum design — and warns against the naive "just keep RL-ing" branch. · **Spark-feasible** (the
  internalization study; LoRA-scale).
- **TIDE — Proactive Multi-Problem Discovery via Template-Guided Iteration** (`2606.04743`, ↑33) ·
  *Template-guided iteration to **surface hidden problems** in context.* The mirror of our template-generated
  bench + the **error-mining** step (STEP-1.5 weak-spot discovery). A more systematic way to grow harder
  held-out rows where the model is silently wrong. · **Spark-feasible** (data-synthesis loop).
- **MLEvolve — Self-Evolving Automated ML Algorithm Discovery** (`2606.06473`, ↑3) &
  **EvoDS — Self-Evolving Data Science Agent** (`2606.03841`, ↑2) ·
  *Automating method **discovery** itself (tree/graph search over ML pipelines; agentic skill learning).*
  The far-horizon "the machine selects its own training method" frame — caps the forward roadmap. ·
  **Borderline** on Spark (multi-agent search is light, but the inner ML runs it spawns must each fit the
  one-lane envelope).

## Dropped / out-of-lens this run

The rest of HF's top-49 was multimodal / video-gen / robotics / domain-eval (ArcANE role-play, VideoKR,
ZipSplat, LoomVideo, RobotValues, Dream.exe, AdaCodec, MechVQA, ASR) — off the methodology lens for SHIP-TASK 1.
Not classified into the canonical store this pass.

## Next move

Synthesis lives in **`_IDEAS/methodology-improvement-frontiers.md`** (the article-research seed).
No promote this run. Re-run a full triage (`/frontier-scout refresh`) when arXiv recovers to catch the
method-paper long tail.
