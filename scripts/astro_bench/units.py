# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""units.py — minimal SI unit-normalization for the astrodynamics bench verifier.

Stdlib only (no ``pint`` dependency — matches the fieldkit no-extra-deps
discipline). The verifier compares a model's answer to gold by converting both
to SI within the same *dimension*; a dimension mismatch (gold is a period in
seconds, the model answered a speed in km/s) is a hard miss.

Public surface:
    parse_quantity(text)      -> (value: float, unit_norm: str) | None   (first qty)
    parse_last_quantity(text) -> (value, unit_norm) | None               (last qty)
    to_si(value, unit)        -> (si_value: float, dimension: str)
    same_dimension(u1, u2)    -> bool
"""

from __future__ import annotations

import re

# unit token (lowercased) -> (dimension, factor-to-SI)
# One canonical SI unit per dimension; factor converts the token TO that SI unit.
_UNITS: dict[str, tuple[str, float]] = {
    # time -> seconds
    "s": ("time", 1.0), "sec": ("time", 1.0), "second": ("time", 1.0), "seconds": ("time", 1.0),
    "min": ("time", 60.0), "mins": ("time", 60.0), "minute": ("time", 60.0), "minutes": ("time", 60.0),
    "h": ("time", 3600.0), "hr": ("time", 3600.0), "hrs": ("time", 3600.0),
    "hour": ("time", 3600.0), "hours": ("time", 3600.0),
    "day": ("time", 86400.0), "days": ("time", 86400.0),
    "yr": ("time", 3.15576e7), "year": ("time", 3.15576e7), "years": ("time", 3.15576e7),
    # length -> meters
    "m": ("length", 1.0), "meter": ("length", 1.0), "meters": ("length", 1.0), "metre": ("length", 1.0),
    "km": ("length", 1e3), "cm": ("length", 1e-2), "mm": ("length", 1e-3),
    "nm": ("length", 1e-9), "angstrom": ("length", 1e-10),
    "au": ("length", 1.495978707e11),
    "pc": ("length", 3.0856775815e16), "kpc": ("length", 3.0856775815e19),
    "mpc": ("length", 3.0856775815e22), "ly": ("length", 9.4607e15),
    "r_earth": ("length", 6.371e6), "rearth": ("length", 6.371e6),
    "r_sun": ("length", 6.957e8), "rsun": ("length", 6.957e8),
    # speed -> m/s
    "m/s": ("speed", 1.0), "km/s": ("speed", 1e3), "km/h": ("speed", 1000.0 / 3600.0),
    # energy -> joules
    "j": ("energy", 1.0), "kj": ("energy", 1e3), "mj": ("energy", 1e6), "gj": ("energy", 1e9),
    # power / luminosity -> watts
    "w": ("power", 1.0), "kw": ("power", 1e3), "mw": ("power", 1e6),
    "watt": ("power", 1.0), "watts": ("power", 1.0),
    "l_sun": ("power", 3.828e26), "lsun": ("power", 3.828e26),
    # specific energy -> J/kg
    "j/kg": ("specific_energy", 1.0), "kj/kg": ("specific_energy", 1e3), "mj/kg": ("specific_energy", 1e6),
    # mass -> kg
    "kg": ("mass", 1.0), "m_sun": ("mass", 1.989e30), "msun": ("mass", 1.989e30),
    "m_earth": ("mass", 5.972e24),
    # angle -> arcsec
    "arcsec": ("angle", 1.0), '"': ("angle", 1.0), "as": ("angle", 1.0),
    # dimensionless (bare ratio)
    "": ("dimensionless", 1.0),
}

# number: optional sign, digits/commas, optional decimal, optional exponent.
_NUM = r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?"
# a unit token: letters/percent/slash/underscore, or a literal double-quote (arcsec).
_UNIT = r'(?:[A-Za-z_]+(?:/[A-Za-z_]+)?|")'
_QTY_RE = re.compile(rf"({_NUM})\s*({_UNIT})?")


def _clean_latex(text: str) -> str:
    """Normalize LaTeX/scientific notation into a plain ``1.23e4 unit`` form."""
    t = text
    t = t.replace("$", " ").replace("\\,", " ").replace("~", " ").replace("\\;", " ")
    t = re.sub(r"\\text\s*\{([^}]*)\}", r" \1 ", t)
    t = re.sub(r"\\mathrm\s*\{([^}]*)\}", r" \1 ", t)
    t = t.replace("\\times", "x").replace("·", "x").replace("⋅", "x").replace("×", "x")
    t = t.replace("\\cdot", "x").replace("∗", "x").replace("*", "x")
    t = t.replace("^{", "^").replace("}", " ")
    # collapse "1.2 x 10^3" / "1.2 x10 3" -> "1.2e3"
    t = re.sub(r"(\d(?:\.\d+)?)\s*x\s*10\s*\^?\s*([-+]?\d+)", r"\1e\2", t)
    # superscript exponent without base mantissa already handled; tidy spaces
    t = re.sub(r"\s+", " ", t)
    return t


def _norm_unit(raw: str | None) -> str | None:
    if raw is None:
        return ""
    u = raw.strip().lower().rstrip(".")
    # strip a trailing plural 's' only if that lands on a known unit and the
    # original didn't (guards "meters" handled above, but catches "joules").
    if u in _UNITS:
        return u
    if u.endswith("s") and u[:-1] in _UNITS:
        return u[:-1]
    return None  # unknown unit token


def _parse_one(text: str, *, last: bool) -> tuple[float, str] | None:
    t = _clean_latex(text)
    matches = list(_QTY_RE.finditer(t))
    if not matches:
        return None
    order = reversed(matches) if last else matches
    for mobj in order:
        raw_num = mobj.group(1).replace(",", "")
        try:
            val = float(raw_num)
        except ValueError:
            continue
        unit = _norm_unit(mobj.group(2))
        if unit is None:
            # number had a trailing token that isn't a unit we know — treat as
            # unitless (the model wrote e.g. "5.3 (approx)"); keep scanning only
            # if there might be a better-tagged quantity, else accept unitless.
            unit = ""
        return (val, unit)
    return None


def parse_quantity(text: str) -> tuple[float, str] | None:
    """First ``(value, normalized_unit)`` in `text`, or ``None``."""
    return _parse_one(text, last=False)


def parse_last_quantity(text: str) -> tuple[float, str] | None:
    """Last ``(value, normalized_unit)`` in `text`, or ``None``."""
    return _parse_one(text, last=True)


def to_si(value: float, unit: str) -> tuple[float, str]:
    """Convert ``(value, unit)`` to ``(si_value, dimension)``.

    Raises ``KeyError`` for an unknown unit (callers pass only normalized units).
    """
    dim, factor = _UNITS[unit]
    return value * factor, dim


def same_dimension(unit_a: str, unit_b: str) -> bool:
    """True if both units exist and share a dimension."""
    if unit_a not in _UNITS or unit_b not in _UNITS:
        return False
    return _UNITS[unit_a][0] == _UNITS[unit_b][0]


def is_known_unit(unit: str) -> bool:
    return unit in _UNITS
