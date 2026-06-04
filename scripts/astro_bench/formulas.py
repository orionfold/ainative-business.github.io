# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""formulas.py — deterministic astrodynamics / astrophysics problem templates.

Each template samples realistic parameters from a seeded RNG, embeds the needed
physical constants *in the prompt* (so the gold answer is reproducible from the
given numbers — no rote-recall confound), computes the gold answer at full float
precision, and returns a :class:`Problem`.

Formulas and physical constants are not copyrightable — this is an
Orionfold-authored, license-clean corpus (`_IDEAS/astrodynamics-rlvr-vertical.md`).

Mix: 9 orbital-mechanics templates + 7 quantitative-astrophysics templates,
weighted ~70/30 by row count in :data:`TEMPLATES`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from random import Random
from typing import Callable

# --- physical constants: the value SHOWN in the prompt == the value used for gold ---
MU_EARTH = 3.986e14      # m^3/s^2  (GM_Earth)
MU_SUN = 1.327e20        # m^3/s^2  (GM_Sun)
G = 6.674e-11            # m^3 kg^-1 s^-2
C = 2.998e8              # m/s
R_EARTH = 6.371e6        # m
SIGMA = 5.670e-8         # W m^-2 K^-4
B_WIEN = 2.898e-3        # m K
H0 = 70.0                # km/s/Mpc  (shown as-is)
M_SUN = 1.989e30         # kg
R_SUN = 6.957e8          # m
PROMPT_TAIL = "Give your final answer as \\boxed{value unit}."


@dataclass(frozen=True, slots=True)
class Problem:
    subtopic: str
    topic: str            # "orbital_mechanics" | "astrophysics"
    tier: int             # 1 | 2 | 3
    prompt: str
    answer: str           # canonical "<value> <unit>" gold string
    gold_value_si: float
    gold_unit: str
    params: dict = field(default_factory=dict)


def _sci(x: float, sig: int = 4) -> str:
    """Format as ``a.bcde×10^n`` for prompt display."""
    if x == 0:
        return "0"
    exp = math.floor(math.log10(abs(x)))
    mant = x / (10 ** exp)
    return f"{mant:.{sig - 1}f}×10^{exp}"


def _g(val: float, unit: str, sig: int = 4) -> str:
    """Canonical gold string with `sig` significant figures."""
    return f"{val:.{sig}g} {unit}"


# ----------------------------------------------------------------------------
# Orbital mechanics (topic="orbital_mechanics")
# ----------------------------------------------------------------------------

def kepler3_period(rng: Random) -> Problem:
    a_km = rng.randrange(7000, 45000, 100)           # semi-major axis, km
    a = a_km * 1e3
    T = 2 * math.pi * math.sqrt(a ** 3 / MU_EARTH)   # seconds
    T_hr = T / 3600.0
    prompt = (
        f"A satellite is in an Earth orbit with semi-major axis a = {a_km:,} km. "
        f"Earth's standard gravitational parameter is μ = {_sci(MU_EARTH)} m³/s². "
        f"Compute the orbital period in hours. {PROMPT_TAIL}"
    )
    return Problem("kepler_third_law", "orbital_mechanics", 1, prompt,
                   _g(T_hr, "hr"), T, "s", {"a_km": a_km})


def vis_viva(rng: Random) -> Problem:
    a_km = rng.randrange(8000, 40000, 100)
    a = a_km * 1e3
    r = rng.randrange(int(0.5 * a_km), int(1.8 * a_km), 100) * 1e3   # within orbit
    v = math.sqrt(MU_EARTH * (2.0 / r - 1.0 / a))                    # m/s
    prompt = (
        f"A spacecraft is on an Earth orbit with semi-major axis a = {a_km:,} km. "
        f"At an instant its distance from Earth's center is r = {r / 1e3:,.0f} km. "
        f"With μ = {_sci(MU_EARTH)} m³/s², use the vis-viva equation "
        f"v = √(μ(2/r − 1/a)) to find its speed in km/s. {PROMPT_TAIL}"
    )
    return Problem("vis_viva", "orbital_mechanics", 2, prompt,
                   _g(v / 1e3, "km/s"), v, "m/s", {"a_km": a_km, "r_km": r / 1e3})


def circular_velocity(rng: Random) -> Problem:
    r_km = rng.randrange(6600, 42000, 100)
    r = r_km * 1e3
    v = math.sqrt(MU_EARTH / r)
    prompt = (
        f"A satellite is in a circular Earth orbit of radius r = {r_km:,} km. "
        f"With μ = {_sci(MU_EARTH)} m³/s², compute the circular orbital speed "
        f"v = √(μ/r) in km/s. {PROMPT_TAIL}"
    )
    return Problem("circular_velocity", "orbital_mechanics", 1, prompt,
                   _g(v / 1e3, "km/s"), v, "m/s", {"r_km": r_km})


def escape_velocity(rng: Random) -> Problem:
    r_km = rng.randrange(6400, 20000, 100)
    r = r_km * 1e3
    v = math.sqrt(2 * MU_EARTH / r)
    prompt = (
        f"From a distance r = {r_km:,} km from Earth's center, with "
        f"μ = {_sci(MU_EARTH)} m³/s², compute the escape velocity "
        f"v = √(2μ/r) in km/s. {PROMPT_TAIL}"
    )
    return Problem("escape_velocity", "orbital_mechanics", 1, prompt,
                   _g(v / 1e3, "km/s"), v, "m/s", {"r_km": r_km})


def hohmann_dv(rng: Random) -> Problem:
    r1_km = rng.randrange(6800, 12000, 100)
    r2_km = rng.randrange(20000, 42000, 100)
    r1, r2 = r1_km * 1e3, r2_km * 1e3
    a_t = (r1 + r2) / 2.0
    v1 = math.sqrt(MU_EARTH / r1)
    v_peri = math.sqrt(MU_EARTH * (2.0 / r1 - 1.0 / a_t))
    dv1 = v_peri - v1
    v2 = math.sqrt(MU_EARTH / r2)
    v_apo = math.sqrt(MU_EARTH * (2.0 / r2 - 1.0 / a_t))
    dv2 = v2 - v_apo
    dv = dv1 + dv2
    prompt = (
        f"Compute the total Δv for a Hohmann transfer between two coplanar "
        f"circular Earth orbits of radii r₁ = {r1_km:,} km and r₂ = {r2_km:,} km. "
        f"Use μ = {_sci(MU_EARTH)} m³/s². Sum the two burns and give the total in m/s. "
        f"{PROMPT_TAIL}"
    )
    return Problem("hohmann_transfer", "orbital_mechanics", 3, prompt,
                   _g(dv, "m/s"), dv, "m/s", {"r1_km": r1_km, "r2_km": r2_km})


def specific_energy(rng: Random) -> Problem:
    a_km = rng.randrange(7000, 45000, 100)
    a = a_km * 1e3
    eps = -MU_EARTH / (2.0 * a)            # J/kg (negative)
    eps_mj = eps / 1e6
    prompt = (
        f"For an Earth orbit with semi-major axis a = {a_km:,} km and "
        f"μ = {_sci(MU_EARTH)} m³/s², compute the specific orbital energy "
        f"ε = −μ/(2a) in MJ/kg. {PROMPT_TAIL}"
    )
    return Problem("specific_orbital_energy", "orbital_mechanics", 1, prompt,
                   _g(eps_mj, "MJ/kg"), eps, "J/kg", {"a_km": a_km})


def orbital_altitude_from_period(rng: Random) -> Problem:
    T_hr = rng.randrange(20, 240) / 10.0    # 2.0–23.9 h, 0.1-h steps (high cardinality)
    T = T_hr * 3600.0
    a = (MU_EARTH * T ** 2 / (4 * math.pi ** 2)) ** (1.0 / 3.0)
    alt = (a - R_EARTH) / 1e3                                    # km
    prompt = (
        f"An Earth satellite has an orbital period of T = {T_hr:g} hours. "
        f"Using μ = {_sci(MU_EARTH)} m³/s² and Earth radius R = {_sci(R_EARTH)} m, "
        f"solve Kepler's third law for the semi-major axis, then report the "
        f"altitude above Earth's surface in km. {PROMPT_TAIL}"
    )
    return Problem("altitude_from_period", "orbital_mechanics", 3, prompt,
                   _g(alt, "km"), alt * 1e3, "m", {"T_hr": T_hr})


def synodic_period(rng: Random) -> Problem:
    T1 = rng.randrange(80, 200, 5) / 100.0 * 365.0     # days, inner
    T2 = rng.randrange(220, 600, 5) / 100.0 * 365.0    # days, outer
    T_syn = 1.0 / abs(1.0 / T1 - 1.0 / T2)             # days
    prompt = (
        f"Two planets orbit the Sun with sidereal periods T₁ = {T1:,.1f} days and "
        f"T₂ = {T2:,.1f} days. Compute their synodic period (1/T_syn = |1/T₁ − 1/T₂|) "
        f"in days. {PROMPT_TAIL}"
    )
    return Problem("synodic_period", "orbital_mechanics", 2, prompt,
                   _g(T_syn, "days"), T_syn * 86400.0, "s", {"T1_d": T1, "T2_d": T2})


def leo_period_from_altitude(rng: Random) -> Problem:
    h_km = rng.randrange(300, 2000, 10)
    r = (R_EARTH / 1e3 + h_km) * 1e3
    T = 2 * math.pi * math.sqrt(r ** 3 / MU_EARTH)
    T_min = T / 60.0
    prompt = (
        f"A satellite orbits at altitude h = {h_km:,} km above Earth's surface. "
        f"With Earth radius R = {_sci(R_EARTH)} m and μ = {_sci(MU_EARTH)} m³/s², "
        f"compute its orbital period in minutes. {PROMPT_TAIL}"
    )
    return Problem("leo_period", "orbital_mechanics", 2, prompt,
                   _g(T_min, "min"), T, "s", {"h_km": h_km})


# ----------------------------------------------------------------------------
# Quantitative astrophysics (topic="astrophysics")
# ----------------------------------------------------------------------------

def distance_modulus(rng: Random) -> Problem:
    M = rng.randrange(-60, 50, 5) / 10.0      # absolute magnitude
    mu = rng.randrange(50, 250, 5) / 10.0     # distance modulus m - M
    m = M + mu
    d = 10 ** ((m - M + 5) / 5.0)             # parsecs
    prompt = (
        f"A star has apparent magnitude m = {m:.1f} and absolute magnitude "
        f"M = {M:.1f}. Using the distance modulus m − M = 5·log₁₀(d/10 pc), "
        f"compute the distance d in parsecs. {PROMPT_TAIL}"
    )
    return Problem("distance_modulus", "astrophysics", 2, prompt,
                   _g(d, "pc"), d * 3.0856775815e16, "m", {"m": m, "M": M})


def hubble_distance(rng: Random) -> Problem:
    v = rng.randrange(1000, 30000, 100)       # km/s recession
    d = v / H0                                # Mpc
    prompt = (
        f"A galaxy recedes at v = {v:,} km/s. Using Hubble's law with "
        f"H₀ = {H0:g} km/s/Mpc, compute its distance in Mpc. {PROMPT_TAIL}"
    )
    return Problem("hubble_law", "astrophysics", 1, prompt,
                   _g(d, "Mpc"), d * 3.0856775815e22, "m", {"v_kms": v})


def schwarzschild_radius(rng: Random) -> Problem:
    # mix stellar-mass and supermassive regimes, high cardinality.
    if rng.random() < 0.7:
        m_solar = float(rng.randrange(3, 120))                  # stellar-mass BH
    else:
        m_solar = float(rng.randrange(10, 900)) * 1e4           # 10^5–10^7 M_sun SMBH
    M = m_solar * M_SUN
    rs = 2 * G * M / C ** 2                    # m
    prompt = (
        f"A black hole has mass M = {m_solar:g} solar masses "
        f"(M_⊙ = {_sci(M_SUN)} kg). With G = {_sci(G)} m³ kg⁻¹ s⁻² and "
        f"c = {_sci(C)} m/s, compute the Schwarzschild radius r_s = 2GM/c² in km. "
        f"{PROMPT_TAIL}"
    )
    return Problem("schwarzschild_radius", "astrophysics", 2, prompt,
                   _g(rs / 1e3, "km"), rs, "m", {"m_solar": m_solar})


def parallax_distance(rng: Random) -> Problem:
    p = rng.randrange(5, 800, 1) / 1000.0     # arcsec
    d = 1.0 / p                                # pc
    prompt = (
        f"A star has a measured parallax of p = {p:.3f} arcsec. Compute its "
        f"distance in parsecs (d = 1/p). {PROMPT_TAIL}"
    )
    return Problem("parallax_distance", "astrophysics", 1, prompt,
                   _g(d, "pc"), d * 3.0856775815e16, "m", {"p_arcsec": p})


def wien_peak(rng: Random) -> Problem:
    T = rng.randrange(2500, 30000, 100)       # K
    lam = B_WIEN / T                          # m
    lam_nm = lam * 1e9
    prompt = (
        f"A star has surface temperature T = {T:,} K. Using Wien's "
        f"displacement law λ_peak = b/T with b = {_sci(B_WIEN)} m·K, compute the "
        f"peak emission wavelength in nm. {PROMPT_TAIL}"
    )
    return Problem("wien_law", "astrophysics", 1, prompt,
                   _g(lam_nm, "nm"), lam, "m", {"T_K": T})


def stefan_boltzmann_luminosity(rng: Random) -> Problem:
    r_rsun = rng.randrange(5, 200, 1) / 10.0  # stellar radius in R_sun
    R = r_rsun * R_SUN
    T = rng.randrange(3000, 12000, 100)       # K
    L = 4 * math.pi * R ** 2 * SIGMA * T ** 4  # W
    prompt = (
        f"A star has radius R = {r_rsun:g} R_⊙ (R_⊙ = {_sci(R_SUN)} m) and "
        f"surface temperature T = {T:,} K. With σ = {_sci(SIGMA)} W m⁻² K⁻⁴, "
        f"compute its luminosity L = 4πR²σT⁴ in watts. {PROMPT_TAIL}"
    )
    return Problem("stefan_boltzmann", "astrophysics", 3, prompt,
                   _g(L, "W"), L, "W", {"r_rsun": r_rsun, "T_K": T})


def transit_planet_radius(rng: Random) -> Problem:
    depth = rng.randrange(50, 30000, 10) / 1e6    # fractional transit depth
    r_star_rsun = rng.randrange(5, 25, 1) / 10.0
    R_star = r_star_rsun * R_SUN
    Rp = R_star * math.sqrt(depth)                # m
    Rp_rearth = Rp / R_EARTH
    prompt = (
        f"An exoplanet transit has fractional depth ΔF/F = {depth:.6f}. The host "
        f"star radius is R_★ = {r_star_rsun:g} R_⊙ (R_⊙ = {_sci(R_SUN)} m, "
        f"R_⊕ = {_sci(R_EARTH)} m). Using ΔF/F = (R_p/R_★)², compute the planet "
        f"radius in Earth radii (R_⊕). {PROMPT_TAIL}"
    )
    return Problem("transit_radius", "astrophysics", 2, prompt,
                   _g(Rp_rearth, "R_earth"), Rp, "m", {"depth": depth, "r_star_rsun": r_star_rsun})


# (subtopic-weight) — weights sum to 100; ~70 orbital / ~30 astrophysics.
TEMPLATES: list[tuple[Callable[[Random], Problem], int]] = [
    # orbital mechanics (70)
    (kepler3_period, 10),
    (circular_velocity, 9),
    (escape_velocity, 8),
    (vis_viva, 9),
    (hohmann_dv, 8),
    (leo_period_from_altitude, 9),
    (orbital_altitude_from_period, 7),
    (synodic_period, 5),
    (specific_energy, 5),
    # astrophysics (30)
    (hubble_distance, 6),
    (parallax_distance, 5),
    (wien_peak, 5),
    (distance_modulus, 5),
    (schwarzschild_radius, 4),
    (transit_planet_radius, 3),
    (stefan_boltzmann_luminosity, 2),
]


def weighted_plan(n: int) -> list[Callable[[Random], Problem]]:
    """Expand TEMPLATES into a length-`n` list of template fns honoring weights."""
    total = sum(w for _, w in TEMPLATES)
    plan: list[Callable[[Random], Problem]] = []
    for fn, w in TEMPLATES:
        plan.extend([fn] * round(n * w / total))
    # pad/trim to exactly n (rounding drift)
    i = 0
    while len(plan) < n:
        plan.append(TEMPLATES[i % len(TEMPLATES)][0])
        i += 1
    return plan[:n]
