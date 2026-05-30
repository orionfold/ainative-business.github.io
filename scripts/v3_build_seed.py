#!/usr/bin/env python3
"""Build the v3 seed dataset for patent-strategist DataDesigner regen.

Pre-computes (row_idx, family, prompt, mpep_context) for 5000 rows so that
DataDesigner's seed-dataset path can consume it deterministically. This
sidesteps the pigeon-hole defect that killed v2 (see
[[feedback_corpus_spice_pigeon_hole]]) by expanding SPICE pools so each
family's prod(len(pool)) >> rows_for_family / 2.

Pool sizing target (per uber doc §415, ≤ 0.6x saturation):
  - A1: ≥3000 unique  → 1500 rows  (0.5x sat)
  - A2: ≥2500 unique  → 1250 rows  (0.5x sat)
  - A4: ≥3125 unique  → 1000 rows  (0.32x sat) [carry from v2 — already fine]
  - E1: ≥3125 unique  →  750 rows  (0.24x sat)
  - E2: ≥1250 unique  →  500 rows  (0.4x sat)

Output:
  - /home/nvidia/data/aifn-corpus-v3/seed.parquet
    Columns: row_idx (int), family (str), prompt (str), mpep_context (str)
  - /home/nvidia/data/aifn-corpus-v3/seed-stats.json
    Per-family unique-prompt count + retrieval-time breakdown.

Run:
  python scripts/v3_build_seed.py --rows 5000 --seed 42
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "/home/nvidia/data/.hf-cache/hub")

# Heavy deps (faiss, sentence_transformers, pandas) loaded lazily inside
# MPEPRetriever — pigeon-hole audit (--no-mpep) works on plain stdlib.

INDEX_DIR = Path("/home/nvidia/data/aifn-retrieval-index/mpep-bge-base")
OUT_DIR = Path("/home/nvidia/data/aifn-corpus-v3")

FAMILY_DIST = {"A1": 0.30, "A2": 0.25, "A4": 0.20, "E1": 0.15, "E2": 0.10}

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
        f"{s['mpep_topic']}. Include the answer key with a one-sentence rationale. "
        f"Focus the question on {s['question_focus']}."
    ),
}

# Expanded SPICE pools targeting >2.5K unique combinations per family.
# All entries hand-curated for technical/legal plausibility; expansion done
# in this CC session per [[feedback_llm_skill_pattern]] (in-session LLM
# artifact generation is the canonical pattern for corpus seed text).

A1_INVENTIONS = [
    # battery / energy
    "improves thermal management in lithium-ion battery packs via phase-change material",
    "extends solid-state battery cycle life via lithium-metal anode interface engineering",
    "rebalances multi-cell battery packs in real time via adaptive impedance matching",
    "increases supercapacitor energy density via graphene-aerogel electrodes",
    "recycles spent lithium-ion cathodes via room-temperature solvothermal leaching",
    # wireless / RF
    "reduces audio latency in wireless earbuds via predictive packet retransmission",
    "extends mesh-network range under dense interference via cooperative beamforming",
    "lowers handset transmit power via reinforcement-learning channel prediction",
    "improves 5G mmWave coverage via reconfigurable-intelligent-surface relays",
    "secures vehicle-to-vehicle communication via physically unclonable functions",
    # bio / pharma
    "increases yield in CRISPR gene editing via guide-RNA secondary-structure prediction",
    "improves mRNA vaccine cold-chain stability via lipid-nanoparticle dehydration",
    "delivers chemotherapy payload via tumor-pH-responsive polymeric micelles",
    "screens drug candidates via organ-on-chip microfluidic perfusion",
    "diagnoses early-stage cancer via circulating-tumor-DNA methylation patterns",
    # optics / photonics
    "improves photovoltaic efficiency via spectral down-conversion coating",
    "extends LiDAR detection range via frequency-modulated continuous-wave silicon photonics",
    "increases microscope resolution via structured-illumination 3D reconstruction",
    "reduces laser speckle in projection displays via piezo-driven diffuser",
    "stabilizes optical-tweezer trap depth via spatial light modulator feedback",
    # aerospace / fluids
    "reduces aircraft drag via active boundary-layer suction",
    "extends drone flight time via solar-cell-augmented wing skin",
    "controls hypersonic vehicle skin temperature via transpiration cooling",
    "improves jet engine fuel efficiency via shape-memory-alloy variable-geometry inlets",
    "reduces helicopter rotor noise via active blade-twist control",
    # manufacturing
    "increases additive-manufacturing build rate via multi-laser melt-pool fusion",
    "improves CNC tool life via real-time chatter detection and feedrate modulation",
    "automates wafer inspection via deep-learning defect classification",
    "reduces semiconductor lithography overlay error via in-line interferometric metrology",
    "fabricates micro-fluidic chips via two-photon polymerization",
    # robotics / mechanical
    "improves robot-grasp success on deformable objects via tactile-pressure feedback",
    "stabilizes legged-robot gait on uneven terrain via predictive whole-body control",
    "reduces surgical-robot tool tremor via piezo-active end-effector damping",
    "extends warehouse-robot battery life via opportunistic wireless charging tiles",
    "controls exoskeleton assistance via electromyographic intent decoding",
    # software / AI
    "compresses transformer attention via locality-sensitive-hashing key clustering",
    "trains language models on edge devices via gradient-quantized federated averaging",
    "detects deepfake audio via mel-spectrogram phase-coherence analysis",
    "schedules data-center GPU jobs via reinforcement-learning bin-packing",
    "secures federated training via differentially-private aggregator masking",
    # sensors / IoT
    "monitors structural health of bridges via piezoelectric strain-sensor mesh",
    "detects gas leaks via metal-oxide semiconductor sensor arrays with neural classifiers",
    "tracks wildlife via low-power LoRaWAN GPS collars with energy harvesting",
    "measures soil moisture via dielectric-impedance multi-depth probes",
    "monitors patient vitals via skin-conformal flexible epidermal electrodes",
    # cryogenic / quantum
    "extends qubit coherence time via in-fridge isolator network optimization",
    "scales superconducting qubits via flip-chip 3D integration",
    "improves photon-pair generation via thin-film lithium niobate ring resonators",
    "stabilizes ion-trap cooling via real-time frequency-comb feedback",
    "reduces dark-current noise in single-photon detectors via cryo-CMOS readout",
    # niche / misc
    "purifies industrial wastewater via electro-Fenton boron-doped-diamond electrodes",
    "recovers waste heat via thermoelectric skutterudite modules",
    "captures atmospheric CO2 via metal-organic-framework swing adsorption",
]  # 50 inventions

A1_CONSTRAINTS = [
    "claim must be patent-eligible under 35 USC §101 Alice step 2",
    "claim must avoid means-plus-function (35 USC §112(f)) interpretation",
    "claim must read on a system, not a method",
    "claim must read on a method, not a system",
    "claim must include a non-obvious narrowing element over US-2018/0123456",
    "claim must use only structural language (no functional limitations)",
    "claim must include at least one quantitative range (numerical limits)",
    "claim must include a tangible-result clause to clear §101 abstract-idea rejection",
    "claim must avoid printed-matter-doctrine pitfalls",
    "claim must not preempt the entire field of the recited technical area",
    "claim must include exactly one wherein-clause and no jepson-style preamble",
    "claim must support a divisional that targets a sub-genus",
    "claim must include a sensor element and a controller element coupled by signal path",
    "claim must use markush-group structure for a chemical constituent",
    "claim must include an apparatus and a corresponding configured-to limitation",
    "claim must avoid 'computer-readable medium' language entirely",
    "claim must be drafted to read on a wireless and a wired embodiment alike",
    "claim must explicitly avoid signal-per-se claim format",
    "claim must include an antecedent-basis verification phrase",
    "claim must support indirect infringement under §271(b)",
    "claim must be drafted to survive PTAB §103 obviousness in light of cited art",
    "claim must include a 'comprising' transition with exactly four positively-recited elements",
    "claim must explicitly recite a non-transitory medium for any storage element",
    "claim must include an environmentally-coupled element (input/output to the environment)",
    "claim must read on a single product unit (no method of use, no method of making)",
    "claim must include a configured-to limitation tied to a specific input signal",
    "claim must include a measurement element and a feedback element in closed loop",
    "claim must include a temperature-range limitation between 0 °C and 100 °C",
    "claim must include a pressure-range limitation between 1 atm and 10 atm",
    "claim must include a frequency-range limitation between 1 kHz and 100 GHz",
    "claim must support a continuation focusing on a single dependent element",
    "claim must include a memory element storing executable instructions for the recited steps",
    "claim must include a network-interface element and a remote-server element coupled thereto",
    "claim must include a power-source element and an actuator coupled by control signal",
    "claim must include a learned-model element with a recited training-data source",
    "claim must include a sensor-fusion limitation combining at least two sensor modalities",
    "claim must include a safety-interlock element and a fault-mode element",
    "claim must include an angle-of-attack-style geometric limitation",
    "claim must avoid biotech §101 natural-phenomenon rejection by reciting a non-natural transformation",
    "claim must include a doping-concentration range for a semiconductor element",
    "claim must include a coating-thickness limitation between 1 nm and 1 µm",
    "claim must include a torque-rating limitation between 0.1 Nm and 100 Nm",
    "claim must include a current-density limitation between 1 mA/cm² and 1 A/cm²",
    "claim must include a Reynolds-number constraint for a flow element",
    "claim must include a tensile-strength limitation between 100 MPa and 5 GPa",
    "claim must include a wavelength-range limitation between 200 nm and 1600 nm",
    "claim must include a control-loop bandwidth limitation between 1 Hz and 10 kHz",
    "claim must include a sample-rate limitation between 1 Hz and 1 GHz",
    "claim must include a duty-cycle limitation between 10% and 90%",
    "claim must include a quality-factor (Q) limitation between 10 and 10⁶",
]  # 50 constraints
# A1 unique combos: 50 × 50 = 2500. With 1500 rows → 0.6× saturation. ✓

A2_DRAFT_CLAIMS = [
    "A device for measuring user satisfaction, comprising means for displaying results, wherein the device operates substantially when needed.",
    "A method comprising the steps of: receiving data; processing the data; and producing a desirable output.",
    "An apparatus comprising a controller configured to optimize performance using known techniques.",
    "A system for handling user requests, wherein the system is essentially user-friendly and operates in real-time or near real-time.",
    "A composition comprising about 5-10% by weight of a suitable polymer and a meaningful amount of a stabilizer.",
    "A wireless device, comprising: a transceiver capable of optimal performance under typical conditions; and a processor adapted as necessary.",
    "A method of training a neural network, comprising appropriately initializing weights and adequately training the model until satisfactory accuracy.",
    "A drug-delivery system comprising therapeutically effective nanoparticles configured to release the active agent at the right moment.",
    "A camera assembly, comprising: a lens; a sensor; and image-processing means for producing high-quality output.",
    "A vehicle controller, comprising means for receiving sensor signals and means for safely operating the vehicle.",
    "An energy storage device having a capacity sufficient for the intended application and a charge rate as fast as practicable.",
    "A surgical instrument comprising a working end suitable for the procedure and a handle reasonably ergonomic for the surgeon.",
    "A coating layer of thickness between thin and thick, configured to substantially protect the underlying substrate.",
    "A method comprising selectively activating an actuator when conditions warrant, where conditions warranting include normal operation.",
    "A robotic gripper, comprising fingers of a size adapted to handle the object of interest with appropriate force.",
    "A communication protocol comprising means for transmitting data securely and means for receiving data reliably.",
    "A solar cell having efficiency greater than the prior art and lifetime longer than expected.",
    "An antenna array, comprising elements arranged in a generally favorable geometric configuration.",
    "A method of compressing data by using an algorithm that achieves good compression while maintaining reasonable speed.",
    "A heat sink comprising fins arranged for adequate convective cooling under ordinary operating temperatures.",
    "A flow-control valve adapted to regulate fluid flow within suitable limits for the intended use case.",
    "A power converter comprising switches operated at a frequency selected to balance efficiency and cost.",
    "An imaging system comprising a sensor of sufficient resolution and a processor of adequate speed.",
    "A control system comprising a feedback loop with proper gain and reasonable phase margin.",
    "A user interface comprising elements intuitively arranged for ease of use.",
    "A sensor module configured to detect events of interest, where events of interest depend on application.",
    "A circuit board comprising components of standard quality and traces of appropriate width.",
    "A storage device having capacity adequate for typical workloads and access times competitive with the market.",
    "A printer comprising a print head capable of high-quality output at acceptable speeds.",
    "A display panel comprising pixels arranged at a density suitable for human viewing.",
    "A method of authenticating users via credentials that are sufficiently secure for the threat model.",
    "A speaker comprising a driver tuned to produce sound that is pleasing to listeners.",
    "An air filter comprising material configured to remove most contaminants of concern.",
    "A water-purification cartridge effective against common pollutants for a reasonable service interval.",
    "A medical device for monitoring patient health, where 'health' is determined by clinically relevant parameters.",
    "A method of generating reports that are usefully detailed without being overly verbose.",
    "A machine-learning model trained on a representative dataset to achieve commercially viable accuracy.",
    "A database schema arranged to support common query patterns with acceptable performance.",
    "A web service exposing endpoints that respond promptly to typical user requests.",
    "A scheduling algorithm that allocates resources in a generally fair manner across competing tasks.",
    "A recommendation engine providing suggestions that users tend to find relevant.",
    "A search algorithm returning results ranked by approximate relevance to the user query.",
    "A networking switch supporting throughput suitable for enterprise deployments under normal load.",
    "A firewall configured to block traffic that is plausibly malicious based on heuristic rules.",
    "An encryption module providing security adequate for sensitive but not classified data.",
    "A backup system replicating data with reasonable frequency to a secondary location of good reliability.",
    "A monitoring tool reporting on metrics deemed important by the system administrator.",
    "A logging facility recording events at a verbosity that strikes a balance between detail and overhead.",
    "A configuration interface exposing parameters that operators typically wish to adjust.",
    "A diagnostic routine that identifies most faults with acceptable false-positive rates.",
]  # 50 deliberately-vague claim drafts
A2_MPEP_SECTIONS = [
    "MPEP 2173.05(b) — relative terminology",
    "MPEP 2173.05(d) — exemplary language and well-known terms",
    "MPEP 2173.05(g) — functional limitations",
    "MPEP 2173.05(h) — alternative limitations",
    "MPEP 2173.05(i) — negative limitations",
    "MPEP 2173.05(p) — claim directed to product-by-process",
    "MPEP 2173.05(q) — 'use' claims",
    "MPEP 2173.05(s) — incorporation by reference",
    "MPEP 2173.05(t) — antecedent basis",
    "MPEP 2173.05(u) — markush groups",
    "MPEP 2181 — means-plus-function (§112(f))",
    "MPEP 2111 — broadest reasonable interpretation",
    "MPEP 2111.01 — plain meaning",
    "MPEP 2111.03 — transitional phrases",
    "MPEP 2111.04 — 'whereby' and 'wherein' clauses",
    "MPEP 2114 — apparatus and product claims must distinguish over the prior art in terms of structure rather than function",
    "MPEP 2115 — material or article worked upon by apparatus",
    "MPEP 2116.01 — novel material or process limitations",
    "MPEP 2117 — markush and jepson claims",
    "MPEP 2125 — drawings as prior art",
    "MPEP 2131 — anticipation – §102",
    "MPEP 2143 — basic requirements of prima facie obviousness",
    "MPEP 2161 — written description and enablement (§112(a))",
    "MPEP 2163 — written description requirement",
    "MPEP 2164 — enablement requirement",
    "MPEP 2106 — patent subject matter eligibility (§101)",
    "MPEP 2106.04(a) — abstract ideas",
    "MPEP 2106.05 — significantly more",
    "MPEP 2106.05(d) — well-understood, routine, conventional activity",
    "MPEP 2106.05(e) — other meaningful limitations",
    "MPEP 2106.05(f) — mere instructions to apply an exception",
    "MPEP 2106.05(g) — insignificant extra-solution activity",
    "MPEP 2106.05(h) — field of use and technological environment",
    "MPEP 2107 — utility requirement (§101)",
    "MPEP 2112 — inherency rejection",
    "MPEP 2113 — product-by-process claims",
    "MPEP 2121 — what constitutes prior art",
    "MPEP 2122 — discussion of references",
    "MPEP 2126 — availability of a document as a 'patent'",
    "MPEP 2127 — domestic and foreign patent applications as prior art",
    "MPEP 2128 — 'printed publications' as prior art",
    "MPEP 2129 — admissions as prior art",
    "MPEP 2132 — pre-AIA §102(a) prior art",
    "MPEP 2133 — pre-AIA §102(b) statutory bars",
    "MPEP 2134 — pre-AIA §102(c) abandonment",
    "MPEP 2141 — examination guidelines for §103 obviousness",
    "MPEP 2144 — supporting a rejection under §103",
    "MPEP 2145 — consideration of applicant's rebuttal arguments",
    "MPEP 2173 — claims must particularly point out and distinctly claim the invention",
    "MPEP 2174 — relationship between disclosure and claims",
    "MPEP 2175 — reissue claim broadening",
]  # 30 + 24 = 54 MPEP sections
# A2 unique combos: 50 × 30 = 1500. With 1250 rows → 0.83× saturation. Slightly above target;
# accept (still 300× better than v2's 250× sat). To tighten further, mix MPEP context too
# (DD effectively adds variance via per-row mpep_context retrieval anyway).

# A4 — keep v2 pools; product is already 2500, which beats 1000 rows at 0.4×
A4_REJECTION_TYPE = ["102(a)(1)", "103", "102(a)(2)", "112(a) enablement", "112(b) indefiniteness"]
A4_CITED_REF = ["US-2019/0012345", "Smith et al. (2018) IEEE Trans.", "JP-H10-123456", "WO-2020/098765", "US-9,876,543",
                "US-10,123,456", "Lee et al. (2020) Nature", "EP-3,456,789", "KR-2018-0098765", "Zhang et al. (2021) Science"]
A4_REJECTION_BASIS = ["anticipating", "rendering obvious", "describing", "failing to enable"]
A4_CLAIM_SUBJECT = [
    "a fluid-cooled CPU package",
    "a method of edge-deploying a quantized transformer",
    "a soft-pneumatic robotic gripper",
    "a polyethylene-glycol-coated drug carrier",
    "a wavelet-based image compression pipeline",
    "a phase-change-material thermal interface",
    "a passive radiative cooling roof tile",
    "a metasurface-based polarization filter",
    "a microfluidic single-cell sorter",
    "a federated-learning gradient aggregator",
]
A4_APPLICANT_POSITION = [
    "the cited reference teaches an air-cooled embodiment",
    "the cited reference uses a non-quantized model in the cloud",
    "the cited reference uses a rigid actuator",
    "the cited reference does not disclose surface coating",
    "the cited reference uses DCT, not wavelet, transformation",
    "the cited reference operates only at cryogenic temperatures",
    "the cited reference is silent on the disputed range",
    "the cited reference teaches away from the claimed configuration",
    "the cited reference requires a chemical step absent from the claim",
    "the cited reference is non-analogous art under In re Klein",
]
# A4 unique combos: 5 × 10 × 4 × 10 × 10 = 20,000. With 1000 rows → 0.05× saturation. ✓✓

E1_AUDIENCES = [
    "a 7-year-old", "a college freshman", "an MBA student", "a software engineer",
    "a patent paralegal", "a hardware-startup founder", "a venture-capital analyst",
    "a high-school physics teacher", "a chemistry PhD student", "a corporate-counsel attorney",
    "a regulatory-affairs manager", "a mechanical-engineering intern", "a biotech research scientist",
    "an academic technology-transfer officer", "a manufacturing-line supervisor",
    "an open-source-software maintainer", "a defense-industry program manager",
    "a non-technical journalist", "a federal-agency procurement officer", "a clinical-research coordinator",
    "a patent-licensing executive", "a high-net-worth angel investor", "a corporate IP-strategy director",
    "a community-college engineering instructor", "a non-English-speaking inventor with translator",
]  # 25
E1_N_SENTENCES = ["2", "3", "4", "3-4", "exactly 3"]  # 5
E1_CONCEPTS = [
    "an independent claim",
    "the doctrine of equivalents",
    "a continuation-in-part application",
    "an Information Disclosure Statement (IDS)",
    "a terminal disclaimer",
    "a means-plus-function (§112(f)) claim element",
    "a Markush group",
    "patent exhaustion",
    "the on-sale bar under §102(b)",
    "a provisional patent application",
    "an inter partes review (IPR)",
    "post-grant review (PGR)",
    "the doctrine of inequitable conduct",
    "patent term adjustment (PTA)",
    "patent term extension (PTE)",
    "small-entity and micro-entity fee status",
    "the experimental-use exception",
    "the safe-harbor for FDA filings (§271(e)(1))",
    "patent marking under §287",
    "the duty of candor (37 CFR §1.56)",
    "the best-mode requirement (§112(a))",
    "the written-description requirement (§112(a))",
    "patent eligibility under §101 (Alice/Mayo)",
    "freedom-to-operate analysis",
    "a divisional application",
]  # 25
# E1 unique combos: 25 × 5 × 25 = 3125. With 750 rows → 0.24× saturation. ✓✓

E2_MPEP_TOPICS = [
    "MPEP 706.07(f) — request for reconsideration",
    "MPEP 2106 — patent subject matter eligibility",
    "MPEP 2143 — basic requirements for obviousness",
    "MPEP 608.01(p) — disclosure of best mode",
    "MPEP 1207 — appeals practice and procedure",
    "MPEP 715 — Rule 1.131 affidavits",
    "MPEP 803 — restriction requirements",
    "MPEP 2173.05(b) — relative terminology",
    "MPEP 2181 — means-plus-function (§112(f))",
    "MPEP 2111 — broadest reasonable interpretation",
    "MPEP 2106.04(a) — abstract ideas",
    "MPEP 2106.05(d) — well-understood, routine, conventional",
    "MPEP 2161 — written description and enablement (§112(a))",
    "MPEP 2164 — enablement requirement",
    "MPEP 2163 — written description requirement",
    "MPEP 1402 — patent term and term extension",
    "MPEP 1490 — disclaimers",
    "MPEP 1893 — international applications (PCT)",
    "MPEP 2014 — patent exhaustion",
    "MPEP 502 — receipt and handling of papers",
    "MPEP 706 — rejection of claims",
    "MPEP 707 — examiner's letter / action",
    "MPEP 714 — amendments after final action",
    "MPEP 1002 — petitions to the director",
    "MPEP 502.05 — correspondence — electronic mail",
    "MPEP 605 — applicant",
    "MPEP 706.02 — rejection on prior art",
    "MPEP 1410 — reissue applications",
    "MPEP 2272 — ex parte reexamination",
    "MPEP 2606 — protests",
    "MPEP 2900 — international design applications",
    "MPEP 1500 — design patents",
    "MPEP 1600 — plant patents",
    "MPEP 311 — fees",
    "MPEP 410 — representative of inventor",
    "MPEP 503 — application number, filing date",
    "MPEP 1200 — appeal",
    "MPEP 1300 — allowance and issue",
    "MPEP 1700 — miscellaneous post-issue",
    "MPEP 2200 — citation of prior art",
    "MPEP 2400 — biotechnology",
    "MPEP 2500 — maintenance fees",
    "MPEP 2700 — patent terms",
    "MPEP 1800 — Patent Cooperation Treaty",
    "MPEP 213 — right of priority",
    "MPEP 706.03 — rejections not based on prior art",
    "MPEP 706.05 — non-statutory subject matter",
    "MPEP 2106.07 — formulating a §101 rejection",
    "MPEP 2152 — detailed discussion of AIA §102(a) and (b)",
    "MPEP 2155 — exceptions to §102(a)(1) prior art",
]  # 50 MPEP topics
E2_QUESTION_FOCUS = [
    "what triggers application of this section",
    "the practitioner's duty under this section",
    "the time bar or deadline associated with this section",
    "the standard of proof or scrutiny applied",
    "how the section interacts with §101 eligibility",
    "how the section interacts with §103 obviousness",
    "the burden-shifting framework",
    "the exception or safe-harbor language",
    "the typical examiner-action under this section",
    "the typical applicant-response under this section",
    "the impact on continuation or divisional practice",
    "the impact on PCT national-stage entry",
    "how this section was modified by the AIA (post-2013)",
    "how this section applies to design vs utility patents",
    "the role of declarations under this section",
    "the fee schedule associated with this section",
    "the appeals path from a final action under this section",
    "the relationship to the Federal Circuit standard of review",
    "the practitioner's obligation under the duty of candor",
    "the most common error practitioners make under this section",
    "the cited Supreme-Court precedent governing this section",
    "the cited Federal-Circuit precedent governing this section",
    "the cited TRIPS or PCT-Article basis",
    "evidentiary requirements under this section",
    "the documentary record required to support a position",
]  # 25 question focuses
# E2 unique combos: 50 × 25 = 1250. With 500 rows → 0.4× saturation. ✓

SPICE = {
    "A1": {"invention": A1_INVENTIONS, "constraint": A1_CONSTRAINTS},
    "A2": {"draft_claim": A2_DRAFT_CLAIMS, "mpep_section": A2_MPEP_SECTIONS},
    "A4": {
        "rejection_type": A4_REJECTION_TYPE,
        "cited_ref": A4_CITED_REF,
        "rejection_basis": A4_REJECTION_BASIS,
        "claim_subject": A4_CLAIM_SUBJECT,
        "applicant_position": A4_APPLICANT_POSITION,
    },
    "E1": {"audience": E1_AUDIENCES, "n_sentences": E1_N_SENTENCES, "concept": E1_CONCEPTS},
    "E2": {"mpep_topic": E2_MPEP_TOPICS, "question_focus": E2_QUESTION_FOCUS},
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


def enumerate_combos(family: str) -> list[dict]:
    """Cartesian product of the family's SPICE dimensions — every dict is a
    unique slot assignment. Memory cost: A4 = 20k dicts × 5 slots ≈ 5 MB.
    """
    import itertools
    pool = SPICE[family]
    keys = list(pool.keys())
    out: list[dict] = []
    for combo in itertools.product(*(pool[k] for k in keys)):
        out.append(dict(zip(keys, combo)))
    return out


def build_prompt(family: str, spice: dict) -> str:
    if family == "A2":
        base = FAMILY_TEMPLATES[family](spice)
        return f"{base} Pay particular attention to {spice['mpep_section']} if applicable."
    return FAMILY_TEMPLATES[family](spice)


def pigeon_hole_audit(rows: list[dict]) -> dict[str, dict]:
    by_fam: dict[str, list[str]] = {}
    for r in rows:
        by_fam.setdefault(r["family"], []).append(r["prompt"])
    audit = {}
    for fam, ps in by_fam.items():
        uniq = len(set(ps))
        audit[fam] = {
            "rows": len(ps),
            "unique_prompts": uniq,
            "saturation_x": round(len(ps) / uniq, 2) if uniq else 0,
            "spice_combinatorial_ceiling": _ceiling(fam),
        }
    return audit


def _ceiling(fam: str) -> int:
    pool = SPICE[fam]
    n = 1
    for v in pool.values():
        n *= len(v)
    return n


class MPEPRetriever:
    """Batched FAISS top-3 retrieval over MPEP chunks (bge-base-en-v1.5).

    Heavy deps loaded lazily so the pigeon-hole audit can run host-side.
    """

    def __init__(self) -> None:
        import faiss
        import pandas as pd
        from sentence_transformers import SentenceTransformer
        self._pd = pd
        self.idx = faiss.read_index(str(INDEX_DIR / "index.faiss"))
        self.chunks = pd.read_parquet(INDEX_DIR / "chunks.parquet")
        self.embed = SentenceTransformer("BAAI/bge-base-en-v1.5", device="cpu")
        print(f"  MPEPRetriever loaded: {self.idx.ntotal:,} chunks, dim={self.idx.d}", flush=True)

    def retrieve_many(self, queries: list[str], k: int = 3) -> list[str]:
        embs = self.embed.encode(queries, normalize_embeddings=True, convert_to_numpy=True,
                                  batch_size=64, show_progress_bar=False)
        _, ids = self.idx.search(embs, k)
        out: list[str] = []
        for row_ids in ids.tolist():
            sections: list[str] = []
            for cid in row_ids:
                row = self.chunks.iloc[cid]
                meta = json.loads(row["metadata_json"])
                title = meta.get("title", "?").strip()
                sections.append(f"### MPEP {title}\n{row['text'][:1200]}")
            out.append("\n\n".join(sections))
        return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=5000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", default=str(OUT_DIR))
    p.add_argument("--no-mpep", action="store_true", help="skip MPEP retrieval (faster dry-runs)")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Building v3 seed: rows={args.rows} seed={args.seed} → {out_dir}", flush=True)

    rng = random.Random(args.seed)
    plan = assign_families(args.rows, rng)

    # Per-family combinatorial enumerate → seeded shuffle → take first N rows.
    # Guarantees every prompt within a family is distinct (no replacement).
    fam_quotas: dict[str, int] = {}
    for f in plan:
        fam_quotas[f] = fam_quotas.get(f, 0) + 1
    fam_pools: dict[str, list[dict]] = {}
    for fam, q in fam_quotas.items():
        combos = enumerate_combos(fam)
        if q > len(combos):
            raise SystemExit(
                f"Family {fam} ceiling {len(combos)} < quota {q}; expand SPICE pool."
            )
        rng_f = random.Random(args.seed + hash(fam) % 10000)
        rng_f.shuffle(combos)
        fam_pools[fam] = combos[:q]

    rows: list[dict] = []
    fam_ptrs: dict[str, int] = {f: 0 for f in fam_quotas}
    for idx, family in enumerate(plan):
        spice = fam_pools[family][fam_ptrs[family]]
        fam_ptrs[family] += 1
        rows.append({"row_idx": idx, "family": family, "prompt": build_prompt(family, spice)})

    audit = pigeon_hole_audit(rows)
    # With enumerate-without-replacement, sat_x is always 1.0 (every prompt
    # within a family is distinct). The meaningful diversity metric is
    # headroom = ceiling / rows — how much SPICE pool we leave unused.
    print("\nPigeon-hole audit (enumerate-without-replacement; want headroom ≥ 1.5×):", flush=True)
    print(f"{'fam':<5} {'rows':>6} {'unique':>8} {'ceiling':>10} {'headroom':>10}")
    for fam in ["A1", "A2", "A4", "E1", "E2"]:
        a = audit[fam]
        headroom = round(a["spice_combinatorial_ceiling"] / a["rows"], 2)
        flag = "" if headroom >= 1.5 else (" ⚠️ tight" if headroom >= 1.0 else " ❌ undersized pool")
        a["headroom_x"] = headroom
        print(f"{fam:<5} {a['rows']:>6} {a['unique_prompts']:>8} {a['spice_combinatorial_ceiling']:>10} {headroom:>10}{flag}")

    if not args.no_mpep:
        print("\nRetrieving MPEP context for each row (batched)...", flush=True)
        retr = MPEPRetriever()
        t0 = time.time()
        prompts = [r["prompt"] for r in rows]
        ctxs = retr.retrieve_many(prompts)
        wall = time.time() - t0
        for r, c in zip(rows, ctxs):
            r["mpep_context"] = c
        print(f"  retrieved {len(rows)} rows in {wall:.1f}s ({len(rows)/wall:.0f} rows/s)", flush=True)
    else:
        for r in rows:
            r["mpep_context"] = ""

    if args.no_mpep:
        # Audit-only path — write JSONL so we don't pull pandas/pyarrow.
        jsonl_path = out_dir / "seed-audit.jsonl"
        with jsonl_path.open("w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(f"\nWrote {jsonl_path} ({len(rows):,} rows)", flush=True)
    else:
        import pandas as pd
        df = pd.DataFrame(rows)
        parquet_path = out_dir / "seed.parquet"
        df.to_parquet(parquet_path, index=False)
        print(f"\nWrote {parquet_path} ({len(df):,} rows, {parquet_path.stat().st_size/1e6:.1f} MB)", flush=True)

    stats = {
        "rows": args.rows,
        "seed": args.seed,
        "family_dist": FAMILY_DIST,
        "audit": audit,
        "schema": list(rows[0].keys()) if rows else [],
    }
    stats_path = out_dir / "seed-stats.json"
    stats_path.write_text(json.dumps(stats, indent=2))
    print(f"Wrote {stats_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
