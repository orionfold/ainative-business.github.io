"""Prepare a deterministic JSONL queue of patent corpus prompts.

⚠️ DEMOTED 2026-05-20 — SPICE F-STRING QUEUE CONSTRUCTION IS HISTORICAL.
The lambda-based ``FAMILY_TEMPLATES`` + ``SPICE`` categorical-pool sampling
below is preserved for the claude-corpus-synth in-CC-session pathway, but the
**pigeon-hole defect** it caused on patent-strategist v2 (5000 target rows
against a ~250-prompt pool, ~20× saturation; see
``ideas/rca-g4-corpus-failure-2026-05-20.md`` defect 4 +
``ideas/uber-local-corpus-gen-decision.md`` §209) means it MUST NOT be reused
for new NIM-driven corpora at production volume. The NeMo DataDesigner stack
(per uber doc Phase 7 §613) replaces this with ``SamplerColumnConfig`` +
``LLMTextColumnConfig`` pools and a pigeon-hole pre-flight gate
(uber doc §415). For new verticals: build pools as DataDesigner categorical
columns, not f-string lambdas.

Materializes N prompts following spec §6.1 + §5.3 family distribution into a
JSONL queue that the claude-corpus-synth skill consumes in-CC-session. NO Claude
calls — this is pure deterministic prep. Same `--seed` always yields the same
queue, so resume + dedup are trivial.

Output schema (one JSONL line per row):
  {"row_idx": 0, "family": "A1", "prompt": "Draft a single independent claim 1 …"}

Usage:
  python prepare_queue.py --rows 5 --seed 42 --output /tmp/aifn-corpus-synth/queue.jsonl
  python prepare_queue.py --rows 25000 --seed 42 \\
      --output /home/nvidia/data/corpus/queues/queue-2026-05-18.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# Spec §6.1 — synthetic share family distribution (~25k rows total in the
# production corpus, scaled here to whatever --rows N the user picks).
FAMILY_DIST = {
    "A1": 0.30,  # claim drafting
    "A2": 0.25,  # 112(b) indefiniteness analysis
    "A4": 0.20,  # office-action traversal
    "E1": 0.15,  # plain-English explanations
    "E2": 0.10,  # MCQ generation
}

FAMILY_TEMPLATES = {
    "A1": lambda s: (
        f"Draft a single independent claim 1 for an invention that {s['invention']}. "
        f"Include exactly one transition phrase (comprising) and 3-5 claim elements. "
        f"Constraint: {s['constraint']}."
    ),
    "A2": lambda s: (
        f"Identify any 35 USC §112(b) indefiniteness risks in this claim: "
        f"'{s['draft_claim']}' Flag the specific phrases and cite the controlling MPEP section. "
        f"Be concrete about why each phrase is problematic."
    ),
    "A4": lambda s: (
        f"An examiner issued a {s['rejection_type']} rejection citing {s['cited_ref']} as "
        f"{s['rejection_basis']} an applicant's claim to {s['claim_subject']}. The applicant "
        f"believes the prior art teaches {s['applicant_position']}. Draft a 2-paragraph "
        f"traversal argument that distinguishes the references by claim element."
    ),
    "E1": lambda s: (
        f"Explain to {s['audience']} (in {s['n_sentences']} short sentences) what {s['concept']} "
        f"means in patent law and why an inventor would care. Use plain language."
    ),
    "E2": lambda s: (
        f"Generate one multiple-choice question (4 options) testing a paralegal's knowledge of "
        f"{s['mpep_topic']}. Include the answer key with a one-sentence rationale."
    ),
}

SPICE = {
    "A1": {
        "invention": [
            "improves thermal management in lithium-ion battery packs via phase-change material",
            "reduces audio latency in wireless earbuds via predictive packet retransmission",
            "increases yield in CRISPR gene editing via guide-RNA secondary-structure prediction",
            "improves photovoltaic efficiency via spectral down-conversion coating",
            "reduces aircraft drag via active boundary-layer suction",
        ],
        "constraint": [
            "claim must be patent-eligible under 35 USC §101 Alice step 2",
            "claim must avoid means-plus-function (35 USC §112(f)) interpretation",
            "claim must read on a system, not a method",
            "claim must include a non-obvious narrowing element over US-2018/0123456",
            "claim must use only structural language (no functional limitations)",
        ],
    },
    "A2": {
        "draft_claim": [
            "A device for measuring user satisfaction, comprising means for displaying results, wherein the device operates substantially when needed.",
            "A method comprising the steps of: receiving data; processing the data; and producing a desirable output.",
            "An apparatus comprising a controller configured to optimize performance using known techniques.",
            "A system for handling user requests, wherein the system is essentially user-friendly and operates in real-time or near real-time.",
            "A composition comprising about 5-10% by weight of a suitable polymer and a meaningful amount of a stabilizer.",
        ],
    },
    "A4": {
        "rejection_type": ["102(a)(1)", "103", "102(a)(2)", "112(a) enablement", "112(b) indefiniteness"],
        "cited_ref": ["US-2019/0012345", "Smith et al. (2018) IEEE Trans.", "JP-H10-123456", "WO-2020/098765", "US-9,876,543"],
        "rejection_basis": ["anticipating", "rendering obvious", "describing", "failing to enable"],
        "claim_subject": [
            "a fluid-cooled CPU package",
            "a method of edge-deploying a quantized transformer",
            "a soft-pneumatic robotic gripper",
            "a polyethylene-glycol-coated drug carrier",
            "a wavelet-based image compression pipeline",
        ],
        "applicant_position": [
            "the cited reference teaches an air-cooled embodiment",
            "the cited reference uses a non-quantized model in the cloud",
            "the cited reference uses a rigid actuator",
            "the cited reference does not disclose surface coating",
            "the cited reference uses DCT, not wavelet, transformation",
        ],
    },
    "E1": {
        "audience": ["a 7-year-old", "a college freshman", "an MBA student", "a software engineer", "a patent paralegal"],
        "n_sentences": ["2", "3", "4", "3-4", "exactly 3"],
        "concept": [
            "an independent claim",
            "the doctrine of equivalents",
            "a continuation-in-part application",
            "an Information Disclosure Statement (IDS)",
            "a terminal disclaimer",
        ],
    },
    "E2": {
        "mpep_topic": [
            "MPEP 706.07(f) — request for reconsideration",
            "MPEP 2106 — patent subject matter eligibility",
            "MPEP 2143 — basic requirements for obviousness",
            "MPEP 608.01(p) — disclosure of best mode",
            "MPEP 1207 — appeals practice and procedure",
            "MPEP 715 — Rule 1.131 affidavits",
            "MPEP 803 — restriction requirements",
        ],
    },
}


def assign_families(n_rows: int, rng: random.Random) -> list[str]:
    plan: list[str] = []
    for fam, frac in FAMILY_DIST.items():
        plan.extend([fam] * round(n_rows * frac))
    while len(plan) < n_rows:
        plan.append(rng.choice(list(FAMILY_DIST)))
    plan = plan[:n_rows]
    rng.shuffle(plan)
    return plan


def build_prompt(family: str, rng: random.Random) -> str:
    pool = SPICE[family]
    spice = {k: rng.choice(v) for k, v in pool.items()}
    return FAMILY_TEMPLATES[family](spice)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, required=True, help="Total queue size")
    p.add_argument("--seed", type=int, default=42, help="RNG seed (same seed → identical queue)")
    p.add_argument("--output", required=True, help="JSONL output path")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    plan = assign_families(args.rows, rng)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fh:
        for idx, family in enumerate(plan):
            row = {
                "row_idx": idx,
                "family": family,
                "prompt": build_prompt(family, rng),
            }
            fh.write(json.dumps(row) + "\n")

    counts: dict[str, int] = {}
    for fam in plan:
        counts[fam] = counts.get(fam, 0) + 1
    print(f"Wrote {out_path} ({args.rows} rows, seed={args.seed})")
    for fam in sorted(counts):
        pct = 100 * counts[fam] / args.rows
        target = 100 * FAMILY_DIST[fam]
        print(f"  {fam}: {counts[fam]:>5}  ({pct:.1f}% vs {target:.1f}% target)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
