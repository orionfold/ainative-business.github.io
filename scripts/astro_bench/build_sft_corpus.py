#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""build_sft_corpus.py — render the C1 SFT-init corpus from the worklist.

The 16 worked-solution chains below are session-authored (one per formula family,
with phrasing variants for diversity). This script does ONLY the deterministic
parts (`feedback_llm_skill_pattern` / invariant #4): substitute each queue row's
params into the authored template, show the arithmetic, box the gold answer
verbatim, and serialize JSON. No model calls, no `anthropic`/SDK.

Every emitted row is then gated by `verify_sft.py` (real <think> chain +
\\boxed{} + self-verify through astro_numeric_match at ±2%).

    python build_sft_corpus.py                       # full queue -> corpus.jsonl
    python build_sft_corpus.py --queue <q> --out <c>
"""

from __future__ import annotations

import argparse
import json
import os
from math import pi, sqrt

MU = 3.986e14        # Earth μ, m³/s²
RE = 6.371e6         # Earth radius, m
G = 6.674e-11        # gravitational constant
C = 2.998e8          # speed of light, m/s
MSUN = 1.989e30      # solar mass, kg
RSUN = 6.957e8       # solar radius, m
B_WIEN = 2.898e-3    # Wien constant, m·K
SIGMA = 5.670e-8     # Stefan–Boltzmann, W m⁻² K⁻⁴
H0 = 70.0            # Hubble constant, km/s/Mpc

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DIR = os.path.join(_REPO_ROOT, "evidence", "astrodynamics")


def g(x: float, sig: int = 4) -> str:
    return f"{x:.{sig}g}"


def _pick(idx: int, options: list[str]) -> str:
    return options[idx % len(options)]


def _wrap(chain: str, restate: str, boxed: str) -> str:
    return f"<think>\n{chain.strip()}\n</think>\n\n{restate.strip()}\n\n\\boxed{{{boxed}}}"


# ── per-subtopic authored solutions ─────────────────────────────────────────

def leo_period(p, idx):
    h = p["h_km"] * 1e3
    r = RE + h
    val = r**3 / MU
    T = 2 * pi * sqrt(val)
    op = _pick(idx, [
        "We want the orbital period of a satellite at altitude h",
        "Find the period for a circular orbit at altitude h",
    ])
    chain = (
        f"{op} = {p['h_km']:,} km.\n"
        f"First the orbital radius: r = R + h = 6.371e6 m + {h:,.0f} m = {g(r,5)} m.\n"
        f"Kepler's third law for a circular orbit: T = 2π·√(r³/μ).\n"
        f"r³ = {g(r**3)} m³, so r³/μ = {g(val)} s², and √(r³/μ) = {g(sqrt(val),5)} s.\n"
        f"T = 2π × {g(sqrt(val),5)} = {g(T,5)} s = {g(T/60,4)} min."
    )
    restate = f"The orbital period is T = 2π√(r³/μ) with r = {g(r,5)} m, giving {g(T/60,4)} min."
    return chain, restate


def synodic_period(p, idx):
    t1, t2 = p["T1_d"], p["T2_d"]
    inv = abs(1.0 / t1 - 1.0 / t2)
    tsyn = 1.0 / inv
    chain = (
        f"Two bodies with sidereal periods T₁ = {g(t1,5)} d and T₂ = {g(t2,5)} d.\n"
        f"The synodic period satisfies 1/T_syn = |1/T₁ − 1/T₂|.\n"
        f"1/T₁ = {g(1/t1)} /d, 1/T₂ = {g(1/t2)} /d, difference = {g(inv)} /d.\n"
        f"T_syn = 1 / {g(inv)} = {g(tsyn,4)} d."
    )
    restate = f"Inverting the rate difference, T_syn = {g(tsyn,4)} days."
    return chain, restate


def parallax_distance(p, idx):
    pa = p["p_arcsec"]
    d = 1.0 / pa
    chain = (
        f"A parallax of p = {g(pa,4)} arcsec.\n"
        f"By definition the distance in parsecs is d = 1/p (p in arcsec).\n"
        f"d = 1 / {g(pa,4)} = {g(d,4)} pc."
    )
    restate = f"Distance d = 1/p = {g(d,4)} pc."
    return chain, restate


def kepler_third_law(p, idx):
    a = p["a_km"] * 1e3
    val = a**3 / MU
    T = 2 * pi * sqrt(val)
    chain = (
        f"Semi-major axis a = {p['a_km']:,} km = {g(a,5)} m.\n"
        f"Kepler's third law: T = 2π·√(a³/μ).\n"
        f"a³ = {g(a**3)} m³, a³/μ = {g(val)} s², √ = {g(sqrt(val),5)} s.\n"
        f"T = 2π × {g(sqrt(val),5)} = {g(T,5)} s = {g(T/3600,4)} hr."
    )
    restate = f"T = 2π√(a³/μ) = {g(T,5)} s = {g(T/3600,4)} hours."
    return chain, restate


def transit_radius(p, idx):
    depth, rs = p["depth"], p["r_star_rsun"]
    ratio = sqrt(depth)
    rstar = rs * RSUN
    rp = ratio * rstar
    re = rp / RE
    chain = (
        f"Transit depth ΔF/F = {g(depth,5)}, host radius R★ = {g(rs,4)} R_⊙.\n"
        f"Since ΔF/F = (R_p/R★)², we have R_p/R★ = √(ΔF/F) = {g(ratio,4)}.\n"
        f"R★ = {g(rs,4)} × 6.957e8 = {g(rstar)} m, so R_p = {g(ratio,4)} × {g(rstar)} = {g(rp)} m.\n"
        f"In Earth radii: R_p = {g(rp)} / 6.371e6 = {g(re,4)} R_⊕."
    )
    restate = f"R_p = R★·√(ΔF/F) = {g(re,4)} Earth radii."
    return chain, restate


def wien_law(p, idx):
    T = p["T_K"]
    lam = B_WIEN / T
    chain = (
        f"Surface temperature T = {T:,} K.\n"
        f"Wien's displacement law: λ_peak = b/T with b = 2.898e-3 m·K.\n"
        f"λ_peak = 2.898e-3 / {T:,} = {g(lam)} m = {g(lam*1e9,4)} nm."
    )
    restate = f"λ_peak = b/T = {g(lam*1e9,4)} nm."
    return chain, restate


def hubble_law(p, idx):
    v = p["v_kms"]
    d = v / H0
    chain = (
        f"Recession velocity v = {v:,} km/s.\n"
        f"Hubble's law: v = H₀·d, so d = v/H₀ with H₀ = 70 km/s/Mpc.\n"
        f"d = {v:,} / 70 = {g(d,4)} Mpc."
    )
    restate = f"d = v/H₀ = {g(d,4)} Mpc."
    return chain, restate


def distance_modulus(p, idx):
    m, M = p["m"], p["M"]
    mu = m - M
    d = 10 ** (mu / 5 + 1)
    chain = (
        f"Apparent magnitude m = {g(m,4)}, absolute magnitude M = {g(M,4)}.\n"
        f"Distance modulus: m − M = 5·log₁₀(d/10 pc), so d = 10^((m−M)/5 + 1) pc.\n"
        f"m − M = {g(mu,4)}; (m−M)/5 + 1 = {g(mu/5 + 1,4)}.\n"
        f"d = 10^{g(mu/5 + 1,4)} = {g(d,4)} pc."
    )
    restate = f"d = 10^((m−M)/5 + 1) = {g(d,4)} pc."
    return chain, restate


def schwarzschild_radius(p, idx):
    ms = p["m_solar"]
    M = ms * MSUN
    rs = 2 * G * M / C**2
    chain = (
        f"Black-hole mass M = {g(ms,4)} M_⊙ = {g(ms,4)} × 1.989e30 = {g(M)} kg.\n"
        f"Schwarzschild radius: r_s = 2GM/c².\n"
        f"2GM = 2 × 6.674e-11 × {g(M)} = {g(2*G*M)}; c² = {g(C**2)}.\n"
        f"r_s = {g(2*G*M)} / {g(C**2)} = {g(rs,5)} m = {g(rs/1e3,4)} km."
    )
    restate = f"r_s = 2GM/c² = {g(rs/1e3,4)} km."
    return chain, restate


def hohmann_transfer(p, idx):
    r1 = p["r1_km"] * 1e3
    r2 = p["r2_km"] * 1e3
    v1 = sqrt(MU / r1)
    v2 = sqrt(MU / r2)
    at = (r1 + r2) / 2
    vp = sqrt(MU * (2 / r1 - 1 / at))
    va = sqrt(MU * (2 / r2 - 1 / at))
    dv1 = vp - v1
    dv2 = v2 - va
    total = dv1 + dv2
    chain = (
        f"Hohmann transfer between circular orbits r₁ = {p['r1_km']:,} km and r₂ = {p['r2_km']:,} km.\n"
        f"Circular speeds: v₁ = √(μ/r₁) = {g(v1,5)} m/s, v₂ = √(μ/r₂) = {g(v2,5)} m/s.\n"
        f"Transfer ellipse a_t = (r₁+r₂)/2 = {g(at,5)} m.\n"
        f"Perigee speed v_p = √(μ(2/r₁ − 1/a_t)) = {g(vp,5)} m/s; apogee v_a = √(μ(2/r₂ − 1/a_t)) = {g(va,5)} m/s.\n"
        f"First burn Δv₁ = v_p − v₁ = {g(dv1,4)} m/s; second burn Δv₂ = v₂ − v_a = {g(dv2,4)} m/s.\n"
        f"Total Δv = {g(dv1,4)} + {g(dv2,4)} = {g(total,4)} m/s."
    )
    restate = f"Summing both burns, total Δv = {g(total,4)} m/s."
    return chain, restate


def circular_velocity(p, idx):
    r = p["r_km"] * 1e3
    v = sqrt(MU / r)
    chain = (
        f"Circular orbit radius r = {p['r_km']:,} km = {g(r,5)} m.\n"
        f"Circular orbital speed: v = √(μ/r).\n"
        f"μ/r = {g(MU/r)} m²/s², v = √ = {g(v,5)} m/s = {g(v/1e3,4)} km/s."
    )
    restate = f"v = √(μ/r) = {g(v/1e3,4)} km/s."
    return chain, restate


def specific_orbital_energy(p, idx):
    a = p["a_km"] * 1e3
    eps = -MU / (2 * a)
    chain = (
        f"Semi-major axis a = {p['a_km']:,} km = {g(a,5)} m.\n"
        f"Specific orbital energy: ε = −μ/(2a).\n"
        f"2a = {g(2*a,5)} m; ε = −3.986e14 / {g(2*a,5)} = {g(eps,5)} J/kg = {g(eps/1e6,4)} MJ/kg."
    )
    restate = f"ε = −μ/(2a) = {g(eps/1e6,4)} MJ/kg."
    return chain, restate


def escape_velocity(p, idx):
    r = p["r_km"] * 1e3
    v = sqrt(2 * MU / r)
    chain = (
        f"Distance from Earth's center r = {p['r_km']:,} km = {g(r,5)} m.\n"
        f"Escape velocity: v = √(2μ/r).\n"
        f"2μ/r = {g(2*MU/r)} m²/s², v = √ = {g(v,5)} m/s = {g(v/1e3,4)} km/s."
    )
    restate = f"v = √(2μ/r) = {g(v/1e3,4)} km/s."
    return chain, restate


def vis_viva(p, idx):
    a = p["a_km"] * 1e3
    r = p["r_km"] * 1e3
    v = sqrt(MU * (2 / r - 1 / a))
    chain = (
        f"Orbit with a = {p['a_km']:,} km = {g(a,5)} m, current distance r = {g(r,5)} m.\n"
        f"Vis-viva equation: v = √(μ(2/r − 1/a)).\n"
        f"2/r = {g(2/r)} /m, 1/a = {g(1/a)} /m, difference = {g(2/r - 1/a)} /m.\n"
        f"μ × {g(2/r - 1/a)} = {g(MU*(2/r - 1/a))} m²/s², v = √ = {g(v,5)} m/s = {g(v/1e3,4)} km/s."
    )
    restate = f"v = √(μ(2/r − 1/a)) = {g(v/1e3,4)} km/s."
    return chain, restate


def altitude_from_period(p, idx):
    T = p["T_hr"] * 3600
    a = (MU * T**2 / (4 * pi**2)) ** (1.0 / 3.0)
    alt = a - RE
    chain = (
        f"Orbital period T = {g(p['T_hr'],4)} hr = {g(T,5)} s.\n"
        f"Invert Kepler's third law: a = (μT²/4π²)^(1/3).\n"
        f"μT² = {g(MU*T**2)}; /(4π²) = {g(MU*T**2/(4*pi**2))}; cube root a = {g(a,5)} m.\n"
        f"Altitude above the surface: a − R = {g(a,5)} − 6.371e6 = {g(alt,5)} m = {g(alt/1e3,4)} km."
    )
    restate = f"a = (μT²/4π²)^(1/3), then altitude = a − R = {g(alt/1e3,4)} km."
    return chain, restate


def stefan_boltzmann(p, idx):
    R = p["r_rsun"] * RSUN
    T = p["T_K"]
    L = 4 * pi * R**2 * SIGMA * T**4
    chain = (
        f"Radius R = {g(p['r_rsun'],4)} R_⊙ = {g(p['r_rsun'],4)} × 6.957e8 = {g(R)} m, temperature T = {T:,} K.\n"
        f"Luminosity (Stefan–Boltzmann over the surface): L = 4πR²σT⁴.\n"
        f"R² = {g(R**2)} m², T⁴ = {g(T**4)} K⁴.\n"
        f"L = 4π × {g(R**2)} × 5.670e-8 × {g(T**4)} = {g(L,4)} W."
    )
    restate = f"L = 4πR²σT⁴ = {g(L,4)} W."
    return chain, restate


_DISPATCH = {
    "leo_period": leo_period,
    "synodic_period": synodic_period,
    "parallax_distance": parallax_distance,
    "kepler_third_law": kepler_third_law,
    "transit_radius": transit_radius,
    "wien_law": wien_law,
    "hubble_law": hubble_law,
    "distance_modulus": distance_modulus,
    "schwarzschild_radius": schwarzschild_radius,
    "hohmann_transfer": hohmann_transfer,
    "circular_velocity": circular_velocity,
    "specific_orbital_energy": specific_orbital_energy,
    "escape_velocity": escape_velocity,
    "vis_viva": vis_viva,
    "altitude_from_period": altitude_from_period,
    "stefan_boltzmann": stefan_boltzmann,
}


def build_row(q: dict, idx: int) -> dict:
    fn = _DISPATCH.get(q["subtopic"])
    if fn is None:
        raise SystemExit(f"no template for subtopic {q['subtopic']!r}")
    chain, restate = fn(q["params"], idx)
    completion = _wrap(chain, restate, q["answer"])
    return {
        "task_id": q["task_id"],
        "topic": q["topic"],
        "subtopic": q["subtopic"],
        "tier": q["tier"],
        "prompt": q["prompt"],
        "completion": completion,
        "answer": q["answer"],
        "gold_value_si": q["gold_value_si"],
        "gold_unit": q["gold_unit"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queue", default=os.path.join(_DIR, "astro-sft-queue.jsonl"))
    ap.add_argument("--out", default=os.path.join(_DIR, "astro-sft-corpus.jsonl"))
    args = ap.parse_args()

    with open(args.queue, encoding="utf-8") as fh:
        queue = [json.loads(line) for line in fh if line.strip()]

    rows = [build_row(q, i) for i, q in enumerate(queue)]
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    lens = [len(r["completion"]) for r in rows]
    print(f"[build-sft] wrote {len(rows)} rows -> {args.out}")
    print(f"[build-sft] mean completion {sum(lens)//len(lens)} chars (min {min(lens)}, max {max(lens)})")


if __name__ == "__main__":
    main()
