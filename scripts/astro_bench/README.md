# astro_bench — the astrodynamics RLVR bench generator + numeric verifier

The **B step** of the Phase-C `A→B→C` program (`_IDEAS/astrodynamics-rlvr-vertical.md`):
a deterministic, license-clean bench for the greenfield **astrodynamics /
quantitative-astrophysics** Orionfold vertical, plus the numeric verifier that
*is* the reward (RV-2 — the eval harness is the reward model, no learned RM).

Base model: **`Qwen/Qwen3-8B`** (scouted + locked 2026-06-04). The bench feeds
both the SFT-init corpus and the RLVR held-out gate.

## Files

| File | Role |
|------|------|
| `formulas.py` | 16 physics templates (9 orbital + 7 astrophysics), ~70/30 by weight. Each samples realistic params from a seeded RNG, embeds the needed constants **in the prompt** (gold reproducible from given numbers — no rote-recall confound), and computes gold at full precision. |
| `units.py` | Stdlib SI unit-normalization (no `pint`): parse a quantity, convert to SI, compare dimensions. |
| `verifier.py` | `astro_numeric_match(predicted, expected, *, rel_tolerance=0.02)` → 1.0/0.0. `\boxed{}` → "final answer:" → last-quantity extraction; unit-normalized, **binary**, relative-tolerance. Conforms to the `fieldkit.eval` verifier signature so `fieldkit.reward.RewardAdapter` wraps it unchanged. |
| `generate.py` | Emits the train/eval pool + a frozen held-out split (different seed, RV-10 no-leakage `exclude`, + 4 computed off-template "curveballs"). Self-checks every gold through the verifier before write. |
| `build_sft_corpus.py` / `sft_queue.py` / `verify_sft.py` | The **C1** SFT-init corpus pipeline: 16 authored worked-solution templates → deterministic substitution → 600-row `<think>…\boxed{}` corpus, every row gated through the verifier (`feedback_llm_skill_pattern`). |
| `preflight_av10.py` | The **C2(a)** AV-10 conditioning/behavioral preflight on `Qwen3-8B` FP (boxed-rate · reward@step-0 · truncation; `--fewshot K` prepends terse exemplars — the "will SFT fix the over-think?" probe). Writes `av10-preflight*.json` the cockpit reward gauge follows. |
| `loader.py` | **C3** glue: bench JSONL → `AstroTask` / `AstroBench` (the `.questions` shape `fieldkit.rl.RLLoop` reads) + `make_rollout(task, gen)` (prediction ← gen, expected ← `answer`, RV-2) + `astro_reward()` (the `astro_numeric_match` → `fieldkit.reward.RewardAdapter` wrap, `rel_tolerance=0.02`). |
| `smoke_rl.py` | **C3** CPU smoke: a ≤2-step `fieldkit.rl.RLLoop` with **injected fake seams** (no GPU) scripted into a pool↔held-out inversion — pool climbs, held-out peaks early — proving the loop selects its checkpoint on **held-out only** (RV-4, the t2po defense). Run it: `… smoke_rl.py`. |
| `test_astro_bench.py` | 39 real tests (no mocks): the 20 bench/verifier tests + 6 C1 corpus-gate tests + 9 C3 tests (loader round-trip, RewardAdapter grading + tolerance forwarding, the held-out-only-selection proof, the ≥100-row RV-10 floor). |

## Grading policy (decided 2026-06-04)

- **Binary** 1.0/0.0 — no partial credit (partial credit invites Goodhart).
- **Relative tolerance ±2%** — answers span orders of magnitude; absolute tolerance breaks across scales.
- **Unit-normalized** — both sides → SI; a dimension mismatch is a hard miss. A bare number is graded in gold's unit.
- **Constants given in-prompt** — isolates the reasoning skill RLVR improves from constant recall.

## Use

```bash
# regenerate the bench (writes evidence/astrodynamics/astro-bench-v0.1*.jsonl):
/tmp/fk/bin/python scripts/astro_bench/generate.py            # 120 pool + 44 held-out
/tmp/fk/bin/python scripts/astro_bench/generate.py --n 200 --heldout 60 --seed 7

# tests:
/tmp/fk/bin/python scripts/astro_bench/test_astro_bench.py    # standalone runner
/tmp/fk/bin/python -m pytest scripts/astro_bench/test_astro_bench.py -q
```

Wiring into the RLVR engine (C3 — built; the GPU seams still need the pinned-vLLM lane):

```python
from loader import load_bench, astro_reward, make_rollout
bench  = load_bench()                       # 120-row AstroBench (.questions)
reward = astro_reward()                      # astro_numeric_match → RewardAdapter
reward.score(make_rollout(bench.questions[0], rollout_text))   # → Reward(success, …)

# CPU smoke — RLLoop orchestration with fake seams, proves held-out-only selection:
#   /tmp/fk/bin/python scripts/astro_bench/smoke_rl.py
```

The real run swaps the fake seams for `fieldkit.rl.gpu_seams(config, reward=…)`
(needs the `fieldkit[rl]` extra + a pinned aarch64+CUDA-13 vLLM — C4, operator-owned).

## Bench row schema (`evidence/astrodynamics/astro-bench-v0.1.jsonl`)

```json
{"task_id": "astro-orb-circular_velocity-0007", "topic": "orbital_mechanics",
 "subtopic": "circular_velocity", "tier": 1, "prompt": "...\\boxed{value unit}.",
 "answer": "3.8 km/s", "gold_value_si": 3800.0, "gold_unit": "m/s",
 "rel_tol": 0.02, "hand_curated": false, "params": {"r_km": 27600}}
```

## Known v0.1 bounds (candidates for v0.2)

- `transit_radius` can emit super-Jupiter radii (the math is exact; realism isn't enforced — fine for a *numeric* bench).
- Single global `rel_tol=0.02`; per-subtopic tolerances are a v0.2 refinement.
- The SFT-init corpus (`build_sft_corpus.py`) uses an **authored-template** builder (16 session-written CoT chains → deterministic substitution), not free-form `claude-corpus-synth` generation — the physics is deterministic, the verifier gates correctness (operator-chosen 2026-06-04).
