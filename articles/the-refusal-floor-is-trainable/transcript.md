# Source material: the-refusal-floor-is-trainable

Synthesized 2026-06-10 from the Orionfold Advisor proof workstream (2026-06-09/10),
written the day the 4B-SFT-v0.2 lane was promoted and published.

## Primary evidence (tracked in this repo)

- `evidence/orionfold-advisor/advisor-curveball2-compare-v0.1.json` — the headline
  three-lane comparison on frozen curveball-v0.2 (sha12 `4b6cac85e41f`):
  30B prompt-contract lane 8/21 scored==strict, refusals 3/9, 3 private_state_risk
  rows; 4B-SFT-v0.2 18/21, refusals 9/9, 0 risk. Per-behavior splits quoted in the
  article table come from this file.
- `evidence/orionfold-advisor/advisor-curveball-compare-v0.1.json` +
  `advisor-curveball-4bsft-v0.1.*` — the v0.1 regression: 4B-SFT-v0.1 refusals 9/15
  on curveball-v0.1 (sha12 `122bcd619e9d`) vs the untrained init's 14/15.
- `evidence/orionfold-advisor/advisor-preflight-4b-wide-v0.1.*` and
  `advisor-preflight-4b-wide-nohint-v0.1.*` — the 28/28 scored+strict held-out
  receipts (hinted and hint-free) for SFT-v0.2.
- `evidence/orionfold-advisor/advisor-sft-corpus-v0.2.json` — corpus report: 827 rows,
  48 rejects, three new hint-free refusal families, 50/50 evaluator-hint alternation,
  sha `e096aa6b12cc`.
- `evidence/orionfold-advisor/advisor-publish-receipt-v0.1.json` — the §14 promotion
  receipt (9 gates, verdict PROMOTED) assembled by
  `scripts/orionfold_advisor/publish_receipt.py`.
- Training/runtime numbers (285 iters ≈ 21 min, val PPL 1.60, ~12 GB resident,
  warm ~2 s) from the SFT-v0.2 session records in `HANDOFF.md` (git history) and
  `_SPECS/orionfold-advisor-nvidia-native-v1.md`. The ~42 tok/s decode figure was
  measured live on the serving lane during the launch session (two runs, 42.1/41.8).

## Method notes

- Both lanes in the comparison answered byte-identical packets (preflight
  `_system_prompt`/`_user_prompt` replay) through the same deterministic scorer
  (`scripts/orionfold_advisor/preflight.py`).
- Curveball-v0.2 was authored, verified (`verify_curveball.py`, gold@5 12/12), and
  sha-pinned before SFT-v0.2 training started — the pre-registration discipline the
  article is about.
- Public artifacts shipped the same day: `Orionfold/Advisor-GGUF`,
  `Orionfold/Advisor-bench` (HF), `products/orionfold-advisor/` (launch page).
