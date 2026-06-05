# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""transfer.py — Tier-1 *transfer* templates for the RL-headroom gate (AV-12 / RV-11).

The C5 RLVR run was a clean null: the selection held-out (in-loop 0.958, external
44-row 86.36%) was already saturated by the 86% SFT init, so GRPO had no headroom
(`_SPECS/astrodynamics-vertical-v1.md` AV-12 / AV-R6; memory `feedback_rlvr_headroom_gate`).
RLVR *amplifies existing competence* — it needs the init **partially** right, in
the ~30–70% Goldilocks band, to climb at all.

These templates are deliberately built to push the SFT init OUT of saturation, in
the two ways AV-R6 prescribes:

  1. **error-mined** — concentrated on the init's *measured* weak spots from the
     C6 generalization run (`evidence/astrodynamics/c6-sft-heldout.json`):
     ``hohmann_transfer`` (3/6 misses) and ``altitude_from_period`` (2/6), plus the
     one ``hubble_in_pc`` cross-scale miss. "Harder/off-template" alone does NOT
     create headroom — the external curveballs were off-template and still scored
     86%. The weakness is *compositional*, so we hammer the compositional families.
  2. **transfer** — the four shifts the SFT corpus never showed the model:
       * **un-named formula** — the scenario is stated; the equation is NOT given
         (the SFT corpus always named the formula, e.g. "use vis-viva v=√(...)").
       * **new central bodies** — μ_Mars/μ_Moon/μ_Jupiter (+ their radii) supplied
         in-prompt; the corpus was Earth/Sun only, so a memorized Earth-μ now fails.
       * **two-hop chains** — altitude→circular-speed, period→altitude→speed: a
         second computed intermediate the corpus's single-step rows never required.
       * **mild extrapolation e>1** — hyperbolic excess speed (unbound orbits); the
         corpus was bound (circular/elliptical) only.

Every constant the answer needs is still IN the prompt (no rote-recall confound) —
only the *formula* is withheld. Subtopics are ``xfer_*`` so they can never collide
with the pool / generalization-held-out / SFT-corpus subtopic names.

These prompts are kept **OUT of the SFT corpus** (else SFT re-saturates) and
**separate** from the publish/generalization held-out — they exist only to be
scored, then filtered to the in-band rows that become the RL selection held-out.
"""

from __future__ import annotations

import math
from random import Random

from formulas import (
    C,
    G,
    H0,
    MU_EARTH,
    M_SUN,
    PROMPT_TAIL,
    R_EARTH,
    Problem,
    _g,
    _sci,
)

# --- new central bodies (value SHOWN == value used for gold) ---
MU_MARS = 4.283e13      # m^3/s^2
MU_MOON = 4.905e12      # m^3/s^2
MU_JUP = 1.267e17       # m^3/s^2
R_MARS = 3.390e6        # m
R_MOON = 1.737e6        # m
R_JUP = 6.991e7         # m

# (name, μ, R) for the un-named / new-body templates.
_BODIES = [
    ("Mars", MU_MARS, R_MARS),
    ("the Moon", MU_MOON, R_MOON),
    ("Jupiter", MU_JUP, R_JUP),
]


# ----------------------------------------------------------------------------
# Error-mined weak spots (hohmann, altitude_from_period) — un-named + new body
# ----------------------------------------------------------------------------

def xfer_hohmann_unnamed(rng: Random) -> Problem:
    """Hohmann Δv, NO burn formulas given, around a non-Earth body (error-mine)."""
    name, mu, _ = rng.choice(_BODIES)
    r1_km = rng.randrange(4000, 9000, 100)
    r2_km = rng.randrange(15000, 40000, 100)
    r1, r2 = r1_km * 1e3, r2_km * 1e3
    a_t = (r1 + r2) / 2.0
    dv1 = math.sqrt(mu * (2.0 / r1 - 1.0 / a_t)) - math.sqrt(mu / r1)
    dv2 = math.sqrt(mu / r2) - math.sqrt(mu * (2.0 / r2 - 1.0 / a_t))
    dv = dv1 + dv2
    prompt = (
        f"A spacecraft must move between two coplanar circular orbits about {name}, "
        f"from radius r₁ = {r1_km:,} km to r₂ = {r2_km:,} km, using the most "
        f"fuel-efficient two-impulse manoeuvre. The body's gravitational parameter "
        f"is μ = {_sci(mu)} m³/s². What is the total speed change required, in m/s? "
        f"{PROMPT_TAIL}"
    )
    return Problem("xfer_hohmann_unnamed", "orbital_mechanics", 3, prompt,
                   _g(dv, "m/s"), dv, "m/s", {"body": name, "r1_km": r1_km, "r2_km": r2_km})


def xfer_altitude_from_period_unnamed(rng: Random) -> Problem:
    """Altitude from period — formula NOT given, non-Earth body (error-mine)."""
    name, mu, rbody = rng.choice(_BODIES)
    T_hr = rng.randrange(20, 200) / 10.0
    T = T_hr * 3600.0
    a = (mu * T ** 2 / (4 * math.pi ** 2)) ** (1.0 / 3.0)
    alt = (a - rbody) / 1e3
    prompt = (
        f"A satellite circles {name} once every {T_hr:g} hours. Given μ = {_sci(mu)} "
        f"m³/s² and the body's radius R = {_sci(rbody)} m, how high above the surface "
        f"does it orbit, in km? {PROMPT_TAIL}"
    )
    return Problem("xfer_altitude_from_period", "orbital_mechanics", 3, prompt,
                   _g(alt, "km"), alt * 1e3, "m", {"body": name, "T_hr": T_hr})


def xfer_hohmann_earth_unnamed(rng: Random) -> Problem:
    """Earth Hohmann but un-named (formula withheld) — error-mine, same body."""
    r1_km = rng.randrange(6800, 11000, 100)
    r2_km = rng.randrange(25000, 42000, 100)
    r1, r2 = r1_km * 1e3, r2_km * 1e3
    a_t = (r1 + r2) / 2.0
    dv1 = math.sqrt(MU_EARTH * (2.0 / r1 - 1.0 / a_t)) - math.sqrt(MU_EARTH / r1)
    dv2 = math.sqrt(MU_EARTH / r2) - math.sqrt(MU_EARTH * (2.0 / r2 - 1.0 / a_t))
    dv = dv1 + dv2
    prompt = (
        f"A satellite in a {r1_km:,} km circular Earth orbit is to be raised to a "
        f"{r2_km:,} km circular orbit with the least total propellant. Earth's "
        f"μ = {_sci(MU_EARTH)} m³/s². Report the total Δv (sum of both burns) in m/s. "
        f"{PROMPT_TAIL}"
    )
    return Problem("xfer_hohmann_earth_unnamed", "orbital_mechanics", 3, prompt,
                   _g(dv, "m/s"), dv, "m/s", {"r1_km": r1_km, "r2_km": r2_km})


# ----------------------------------------------------------------------------
# Two-hop chains (a second computed intermediate)
# ----------------------------------------------------------------------------

def xfer_altitude_to_speed(rng: Random) -> Problem:
    """altitude → orbital radius → circular speed (two hops, un-named)."""
    name, mu, rbody = rng.choice(_BODIES + [("Earth", MU_EARTH, R_EARTH)])
    h_km = rng.randrange(300, 3000, 10)
    r = rbody + h_km * 1e3
    v = math.sqrt(mu / r)
    prompt = (
        f"A probe flies in a circular orbit {h_km:,} km above the surface of {name} "
        f"(radius R = {_sci(rbody)} m, μ = {_sci(mu)} m³/s²). How fast is it "
        f"travelling, in km/s? {PROMPT_TAIL}"
    )
    return Problem("xfer_altitude_to_speed", "orbital_mechanics", 2, prompt,
                   _g(v / 1e3, "km/s"), v, "m/s", {"body": name, "h_km": h_km})


def xfer_period_to_speed(rng: Random) -> Problem:
    """period → semi-major axis → circular speed (two hops, un-named, Earth)."""
    T_hr = rng.randrange(15, 240) / 10.0
    T = T_hr * 3600.0
    a = (MU_EARTH * T ** 2 / (4 * math.pi ** 2)) ** (1.0 / 3.0)
    v = math.sqrt(MU_EARTH / a)   # circular speed at that radius
    prompt = (
        f"A satellite completes one circular Earth orbit every {T_hr:g} hours. With "
        f"μ = {_sci(MU_EARTH)} m³/s², determine its orbital speed in km/s. "
        f"{PROMPT_TAIL}"
    )
    return Problem("xfer_period_to_speed", "orbital_mechanics", 3, prompt,
                   _g(v / 1e3, "km/s"), v, "m/s", {"T_hr": T_hr})


def xfer_altitude_to_period_newbody(rng: Random) -> Problem:
    """altitude → radius → period, non-Earth body, un-named."""
    name, mu, rbody = rng.choice(_BODIES)
    h_km = rng.randrange(200, 4000, 10)
    r = rbody + h_km * 1e3
    T = 2 * math.pi * math.sqrt(r ** 3 / mu)
    T_min = T / 60.0
    prompt = (
        f"A spacecraft orbits {name} in a circle {h_km:,} km above its surface "
        f"(R = {_sci(rbody)} m, μ = {_sci(mu)} m³/s²). How long does one orbit take, "
        f"in minutes? {PROMPT_TAIL}"
    )
    return Problem("xfer_altitude_to_period", "orbital_mechanics", 3, prompt,
                   _g(T_min, "min"), T, "s", {"body": name, "h_km": h_km})


# ----------------------------------------------------------------------------
# Un-named single-step on a new body (mild transfer)
# ----------------------------------------------------------------------------

def xfer_circular_speed_newbody(rng: Random) -> Problem:
    """Circular speed on a new body, formula NOT given."""
    name, mu, _ = rng.choice(_BODIES)
    r_km = rng.randrange(2500, 30000, 100)
    v = math.sqrt(mu / (r_km * 1e3))
    prompt = (
        f"A satellite is held in a circular orbit of radius {r_km:,} km around {name} "
        f"(μ = {_sci(mu)} m³/s²). What is its orbital speed, in km/s? {PROMPT_TAIL}"
    )
    return Problem("xfer_circular_speed", "orbital_mechanics", 2, prompt,
                   _g(v / 1e3, "km/s"), v, "m/s", {"body": name, "r_km": r_km})


def xfer_escape_newbody(rng: Random) -> Problem:
    """Escape speed on a new body, formula NOT given (mild transfer)."""
    name, mu, rbody = rng.choice(_BODIES)
    r = rbody + rng.randrange(0, 2000, 100) * 1e3
    v = math.sqrt(2 * mu / r)
    prompt = (
        f"At a distance r = {r / 1e3:,.0f} km from the center of {name} "
        f"(μ = {_sci(mu)} m³/s²), what is the minimum speed needed to escape its "
        f"gravity, in km/s? {PROMPT_TAIL}"
    )
    return Problem("xfer_escape_speed", "orbital_mechanics", 2, prompt,
                   _g(v / 1e3, "km/s"), v, "m/s", {"body": name, "r_km": r / 1e3})


# ----------------------------------------------------------------------------
# Mild extrapolation: e > 1 (hyperbolic, unbound) — OOD vs the bound corpus
# ----------------------------------------------------------------------------

def xfer_hyperbolic_excess(rng: Random) -> Problem:
    """Hyperbolic excess speed v_∞ = √(v² − 2μ/r) — unbound orbit (e>1), light hint."""
    name, mu, rbody = rng.choice(_BODIES + [("Earth", MU_EARTH, R_EARTH)])
    r = rbody + rng.randrange(200, 3000, 50) * 1e3
    v_esc = math.sqrt(2 * mu / r)
    v = v_esc * rng.choice([1.15, 1.25, 1.4, 1.6])   # faster than escape -> e>1
    v_inf = math.sqrt(v ** 2 - 2 * mu / r)
    prompt = (
        f"A probe passes {name} at radius r = {r / 1e3:,.0f} km moving at "
        f"v = {v / 1e3:.3f} km/s — faster than escape speed, so its orbit is "
        f"hyperbolic. With μ = {_sci(mu)} m³/s², the speed it retains infinitely far "
        f"away is v_∞ = √(v² − 2μ/r). Compute v_∞ in km/s. {PROMPT_TAIL}"
    )
    return Problem("xfer_hyperbolic_excess", "orbital_mechanics", 3, prompt,
                   _g(v_inf / 1e3, "km/s"), v_inf, "m/s", {"body": name, "r_km": r / 1e3})


# ----------------------------------------------------------------------------
# Astrophysics error-mine: hubble cross-scale (the 1 C6 miss)
# ----------------------------------------------------------------------------

def xfer_hubble_cross_scale(rng: Random) -> Problem:
    """Recession speed → distance asked in a NON-default length unit (kpc/ly)."""
    v_rec = rng.randrange(400, 6000, 50)        # km/s
    d_mpc = v_rec / H0
    unit = rng.choice(["kpc", "ly"])
    if unit == "kpc":
        val = d_mpc * 1e3
        si = val * 3.0856775815e19
    else:                                       # light-years
        val = d_mpc * 3.0856775815e22 / 9.4607e15
        si = val * 9.4607e15
    prompt = (
        f"A galaxy recedes at v = {v_rec:,} km/s (H₀ = {H0:g} km/s/Mpc). Give its "
        f"distance in {'kiloparsecs (kpc)' if unit == 'kpc' else 'light-years (ly)'}, "
        f"not Mpc. {PROMPT_TAIL}"
    )
    return Problem("xfer_hubble_cross_scale", "astrophysics", 2, prompt,
                   _g(val, unit), si, "m", {"v_kms": v_rec, "unit": unit})


def xfer_schwarzschild_newunit(rng: Random) -> Problem:
    """Schwarzschild radius asked in AU for an SMBH (cross-scale astrophysics)."""
    m_solar = float(rng.randrange(10, 500)) * 1e5      # 10^6–5×10^7 M_sun
    M = m_solar * M_SUN
    rs = 2 * G * M / C ** 2
    rs_au = rs / 1.495978707e11
    prompt = (
        f"A supermassive black hole has mass M = {_sci(m_solar)} solar masses "
        f"(M_⊙ = {_sci(M_SUN)} kg, G = {_sci(G)} m³ kg⁻¹ s⁻², c = {_sci(C)} m/s). "
        f"Express its Schwarzschild radius in astronomical units (AU). {PROMPT_TAIL}"
    )
    return Problem("xfer_schwarzschild_au", "astrophysics", 3, prompt,
                   _g(rs_au, "au"), rs, "m", {"m_solar": m_solar})


# (template-fn, weight) — weighted HEAVY toward the C6 error-mined weak spots
# (hohmann + altitude_from_period) per AV-R6; ~75% orbital / ~25% astrophysics.
TRANSFER_TEMPLATES: list[tuple] = [
    # error-mined weak spots (hohmann, altitude_from_period)
    (xfer_hohmann_unnamed, 6),
    (xfer_hohmann_earth_unnamed, 4),
    (xfer_altitude_from_period_unnamed, 6),
    # two-hop chains
    (xfer_altitude_to_speed, 4),
    (xfer_period_to_speed, 4),
    (xfer_altitude_to_period_newbody, 3),
    # un-named single-step on new bodies
    (xfer_circular_speed_newbody, 3),
    (xfer_escape_newbody, 2),
    # mild extrapolation e>1
    (xfer_hyperbolic_excess, 4),
    # astrophysics error-mine / cross-scale
    (xfer_hubble_cross_scale, 3),
    (xfer_schwarzschild_newunit, 2),
]


def weighted_plan(n: int) -> list:
    """Expand TRANSFER_TEMPLATES into a length-`n` list honoring weights."""
    total = sum(w for _, w in TRANSFER_TEMPLATES)
    plan: list = []
    for fn, w in TRANSFER_TEMPLATES:
        plan.extend([fn] * round(n * w / total))
    i = 0
    while len(plan) < n:
        plan.append(TRANSFER_TEMPLATES[i % len(TRANSFER_TEMPLATES)][0])
        i += 1
    return plan[:n]
