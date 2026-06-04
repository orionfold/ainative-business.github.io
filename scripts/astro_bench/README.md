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
| `test_astro_bench.py` | 20 real tests (no mocks): unit conversion, dimension-mismatch rejection, tolerance edges, boxed/last extraction, generator determinism, 70/30 mix, tier spread, **every-gold-self-verifies**, pool↔held-out disjointness, and a "wrong-method solver is rejected" guard. |

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

Wiring into the RLVR engine (next step — needs the pinned-vLLM lane):

```python
from fieldkit.reward import RewardAdapter, Rollout
from verifier import astro_numeric_match
adapter = RewardAdapter(astro_numeric_match, scorer_kwargs={"rel_tolerance": 0.02})
reward  = adapter.score(Rollout(prediction=rollout_text, expected=row["answer"]))
```

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
- SFT-init worked-solution corpus is **not** generated here — that's the `claude-corpus-synth`-pattern step (session-model writes CoT; deterministic scripts only), gated next.
