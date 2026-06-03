# Provenance — the-machine-improves-itself

A synthesis/concept piece (no fresh install, no screenshots), drafted 2026-06-03 as the
**Phase-3 ENGINE installment** of the Machine-that-Builds-Machines arc — the closing of the
loop the [meta-program opener](/field-notes/the-meta-program-on-spark/) promised ("Next, the
part the pane is still missing"). Since that opener, the pane (Arena control plane), the hands
(autonomous harness / budget-governed drain), and now the engine (`fieldkit.rl` + `fieldkit.reward`,
shipped in `fieldkit v0.20.0`) all landed.

## Editorial overlay
Closed-loop RLVR on the Spark: the eval harness IS the reward (no learned reward model);
GRPO/REINFORCE; the t2po held-out inversion defense; the as-built `fieldkit.rl`/`fieldkit.reward`
engine; + a Looking-Beyond-Spark extrapolation. `book_chapters: [10, 11, 14]`.

## Source grounding (all pre-existing, version-controlled in this repo)
- **`_SPECS/rlvr-loop-v1.md`** — the spec + §10.1 as-built map. The 10 decisions RV-1…10, the
  three corrections, and the injected-GPU-seams design.
- **Proven run** — `articles/clawgym-on-spark-grpo/`: single GB10, 42-task pool (8/step × K=4 =
  32-rollout bundle), 34 GRPO steps in 8.5 h, `task_complete 0/158 → 154/158` (+97.5 pp), mean
  turns −58%, wall −62%, no learned reward model.
- **The inversion** — `articles/t2po-uncertainty-guided-rl-on-spark/`: step 45 pool 87.5% (28/32)
  vs held-out 5.7% (9/158) = 81.8 pp inversion; per-assertion ~47.7% ceiling vs ~80% synth floor;
  T²PO 18.5 h vs GRPO 8.5 h for a worse result.
- **Mode collapse** — `articles/distill-architect-lora-from-trajectories/` +
  `articles/trajectory-eval-is-the-agent-flailing/`: 42-row corpus → 5/5 train keeps, 0/8 held-out.
- **9-class enum precedent** — `articles/auto-research-loop-on-spark/` → built as `fieldkit.lineage.FailureLabel`.
- **Runtime drift** — `articles/runtime-frontier-six-patches-on-spark/`: 6 vLLM API drifts / 2 minor
  versions, 1 silent return-shape change. Step breakdown: rollout ~13 min / restart ~3.5 min /
  trainer ~22 s.
- **Envelope** — `articles/baseline-training-loop-on-spark/`: 50 GiB pretrain + 28 trainer + 20 vLLM
  ≈ 98/128, ~30 GiB margin → trainer-resident, one lane.

## Code blocks — faithful to the shipped surface
Verified against `fieldkit/src/fieldkit/{rl.py,reward.py}` (v0.20.0):
- `fieldkit.reward`: `RewardAdapter(verifier, pass_threshold, scorer_kwargs)`, `.score_group(rollouts)`,
  `Reward(success, failure_class, auxiliary)`, `.scalar`, `.failure_class` (reuses `lineage.FailureLabel`),
  `group_advantage(rewards)`.
- `fieldkit.rl`: `GRPOConfig(base, vllm_pin, group_k, tasks_per_step, heldout_every, corpus_min, …)`,
  `RLLoop(cfg, reward, bench, sampler, trainer, heldout_eval)`, `.run() -> LineageSnapshot`,
  `summary()["selected_on"] == "heldout"`, `gpu_seams(cfg)` (raises until `fieldkit[rl]` GPU backend
  is vendored). The article's code block mirrors the `harness.mcp.run_rl_loop` wiring.

## Honesty notes
- The 97.5-pp number is the **predecessor** clawgym run's, not a run through the shipped engine —
  the engine ships as orchestration with injected seams; `gpu_seams` raises until the pinned
  aarch64+CUDA-13 vLLM backend is vendored. The article states this plainly.
- The "living model" product launch is staked as a `status: upcoming` placeholder (sibling task) —
  no real `rl_run` lineage delta data exists yet.

## Artifacts produced
- `articles/the-machine-improves-itself/article.md` — the essay (8-section, 10 explainers,
  1 inline fn-diagram accenting the held-out gate).
- `src/components/field-notes/svg/ClosedLoopRlvr.astro` — the signature (closed-loop ring,
  SCORE accent = eval-is-reward).
