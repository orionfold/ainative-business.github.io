# A²TGPO: Agentic Turn-Group Policy Optimization with Adaptive Turn-level Clipping

## Hypothesis

Agentic LLM RL typically optimizes against a sparse trajectory-level outcome reward, which makes per-turn credit assignment in multi-turn tool-use loops hard. Information Gain (IG) — the per-turn change in the policy's predicted probability of the ground-truth answer — is an attractive intrinsic process signal but is unstable across turn positions. A²TGPO redesigns how IG is normalized, accumulated, and consumed: (i) **turn-group normalization** compares each turn against peers at the same depth, (ii) **variance-rescaled discounted accumulation** (cumulative IG / √n) keeps advantage magnitudes comparable across turn positions, and (iii) **adaptive turn-level clipping** widens the PPO clipping range for informative turns and narrows it for uninformative ones via `c_{i,t} = 1 + β(2σ(IG_{i,t}) − 1)`. Result: +1.75 on multi-hop QA and +1.69 on single-hop QA over RL baselines. The IG signal forward-pass adds 164 s/step but is largely offset by 86 s of saved generation time.

## Memory budget

Trained on **Qwen3-4B** (also Qwen3-8B and Qwen2.5-7B) on **8×H20** single node. The Spark fits the 4B reference cleanly:

- `weight_bytes(params_b=4, dtype="bf16")` ≈ 8 GB.
- LoRA training overhead at ~1.5×: ≈ 12 GB total weights+grads+optimizer.
- GRPO rollouts: group size 8, ctx 8192, hidden=2560 (Qwen3-4B), n_layers=28: `kv_cache_bytes(hidden=2560, n_layers=28, ctx=8192, batch=8, dtype="bf16")` ≈ 9 GB.
- IG forward pass adds one extra logit computation per turn — same model, paged-attention reuse — no additional weights resident.
- Local retriever (e5_Flat over wiki-18) requires faiss-gpu ~5 GB index. The repo already separates this into a FastAPI server (`rag_server/launch.sh`).

**Total working set at 4B:** ~30 GB. Comfortable on Spark's 128 GB unified pool with full-precision GRPO + retriever co-resident. 8B variant: ~50 GB, still in-envelope.

## Proposed Spark recipe

The repo is at `github.com/CuSO4-Chen/A-TGPO` and uses **verl** for RL. Reproduction path:

1. `git clone --depth 1 https://github.com/CuSO4-Chen/A-TGPO && cd A-TGPO`
2. Two conda envs as the README prescribes — one for the retriever (`pyserini` + `faiss-gpu=1.8.0`), one for training (`torch==2.6.0` + `flash-attn`). The `flash-attn` build needs CUDA 12.4; capability map confirms Spark ships CUDA 12.x in the NeMo / PyTorch containers, so this works inside `nvcr.io/nvidia/pytorch:25.x` (avoid the venv-trap from memory note `feedback_nvidia_container_uv_venv_trap`).
3. Stand up the local retriever: `python rag_server/download.py` then `bash rag_server/launch.sh`. Wiki-18 + e5_Flat fits the Spark NVMe budget (~50 GB).
4. Process datasets: `python data_process/hotpotqa_multihop_train.py` + `python data_process/multihop_test_merge.py` for multi-hop, plus the single-hop pair.
5. Run `bash ATGPO/scripts/ATGPO_multihop_qwen3_4B.sh`. The script's batch sizes will need a halve-or-quarter pass for single-GPU verl (the published 8×H20 schedule won't map 1:1), but the algorithm is the same.
6. Eval on the seven QA datasets the paper uses: HotpotQA, 2WikiMultihopQA, MuSiQue, Bamboogle (multi-hop) + NaturalQuestions, TriviaQA, PopQA (single-hop).

The IG forward + adaptive-clipping logic lives in `verl_atgpo/` and is the actual extractable abstraction — three small overrides on top of verl's GRPO loss.

## Blockers

- (none for the algorithm itself — recipe should run as-is at reduced batch)
- `flash-attn` precompiled wheel availability for Blackwell (sm_100) is the only environment-side risk. Falls back to PyTorch SDPA at modest throughput cost if unavailable; capability map's PyTorch container ships an SDPA path that's "in-envelope."
- verl on a single GB10 vs the published 8×H20 means longer wall-clock per epoch (estimated ~6–8× slowdown), not a memory blocker.

## Verdict

**spark-feasible** — Qwen3-4B at bf16 with GRPO rollouts + local faiss retriever totals ~30 GB on the 128 GB unified pool, well inside the in-envelope signal "fine-tuning ≤ 70B with LoRA / QLoRA"; the IG forward adds ~30% per-step latency but no additional resident memory.

## Fieldkit fit

- **Would import:** `fieldkit.capabilities` (verify the 4B-bf16 envelope before kicking off training), `fieldkit.nim` (the trained policy gets served back as a NIM endpoint for downstream eval).
- **Would extend:** `fieldkit.training` (currently a stub) — promote it to first-class with a `fieldkit.training.rl` submodule.
- **Would propose for v0.2:** `fieldkit.training.rl` — three composable primitives lifted directly from `verl_atgpo/`: `InformationGain` (per-turn logit-diff), `TurnGroupNormalizer` (depth-aware advantage normalization), `AdaptiveTurnClipper` (β-scaled clipping range). Each is ~50 lines of pure tensor code; they wrap any GRPO loss without taking ownership of the loop. Pairs with the `Trial` / `Lineage` types proposed in the Auto Research eval — A²TGPO becomes the loss the lineage records.

## Article suggestion

- **Would write?** yes
- **Suggested slug:** a2tgpo-turn-clipping-on-spark
- **Suggested stage:** fine-tuning
- **Suggested series:** Machine that Builds Machines
- **Suggested book chapters (MTBM only):** [10]
- **Suggested mtbm_station (MTBM only):** forge
- **Suggested tags:** reinforcement-learning, grpo, agentic, credit-assignment, information-gain, qwen, verl
- **Suggested summary:** Reproducing A²TGPO turn-level clipping on Qwen3-4B on a single DGX Spark — local faiss retriever + verl + the three IG primitives, then promoting fieldkit.training.rl to a first-class submodule.
- **Suggested `fieldkit_modules`:** [capabilities, nim]

## Alignment lens (MTBM only)

- **Ontological** — strong: IG is a single scalar per (prompt, turn-index) — every turn has the same shape regardless of tool-call type, so the credit-assignment primitive is uniform across agentic surfaces.
- **Teleological** — strong: ground-truth-probability change *is* a measurable, falsifiable definition of "did this turn move us toward success?" — answers ad-hoc heuristic process rewards.
- **Behavioral** — partial: clipping range adapts to informativeness, but the policy still learns no explicit refusal or abstention behavior — uninformative turns get a *narrower* update, not a *no-op* signal.
- **Temporal** — strong: depth-aware normalization is exactly the temporal-stability property — alignment doesn't drift as turn count grows because magnitudes are comparable across turn positions.
- **Reflexive** — partial: the policy doesn't know its own IG, but the clipping range *implicitly* encodes uncertainty (high σ(IG) ⇒ wider, low ⇒ narrower); a first step toward reflexive RL.
