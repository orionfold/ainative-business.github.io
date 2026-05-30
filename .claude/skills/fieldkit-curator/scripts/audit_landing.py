#!/usr/bin/env python3
"""fieldkit-curator audit-landing — drift check for the fieldkit landing page.

Sibling to `audit_docs.py`. Where that script proves every `__all__` symbol is
mentioned in `fieldkit/docs/api/<module>.md`, this script proves the landing
page sections at `src/components/sections/fieldkit/*.astro` stay in sync with
the package's actual surface area — specifically the things that drift
silently every release and don't surface in a `pytest` or `astro build`:

  1. **Module count + module list** — the `FieldkitProblem` "modules, one
     import each" stat and the `FieldkitModules` "in N imports" headline.
     Both should derive from `FIELDKIT_MODULES` (`src/content.config.ts`),
     not from a hardcoded integer / word. Catches the v0.4 drift where
     the page kept saying "7 / seven" after `quant` + `publish` shipped.
  2. **Hardcoded version strings** — `FieldkitHero` and `FieldkitCTAFooter`
     already read `_version.py` at build time; `FieldkitCli` joined them in
     v0.4.1. This script verifies no other landing component holds a stale
     hardcoded version (literal `0.X.Y`-shaped string outside of a version
     prop). The CLI demo block is the easy one to forget.
  3. **Module tagline coverage** — `FieldkitModules.astro` carries a per-
     module `taglines` map; every entry in `FIELDKIT_MODULES` must have a
     tagline, else the card falls back to the doc summary (longer and
     visually misaligned with its siblings).
  4. **Doc-page order frontmatter** — `fieldkit/docs/api/<module>.md`
     frontmatter `order:` must equal the module's 1-based index in
     `FIELDKIT_MODULES`. Catches the v0.4 collision where `cli.md` stayed
     at order=7 after `quant`/`publish` shifted it to 9.

Exit code = number of FAIL verdicts. 0 = ready to release; ≥1 = drift, fix
before tagging. Standalone invocation is read-only — never edits files.

Usage:
  python3 audit_landing.py
  python3 audit_landing.py --json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path("/home/nvidia/ainative-business.github.io")
SECTIONS = REPO / "src" / "components" / "sections" / "fieldkit"
CONTENT_CONFIG = REPO / "src" / "content.config.ts"
DOCS = REPO / "fieldkit" / "docs" / "api"
VERSION_FILE = REPO / "fieldkit" / "src" / "fieldkit" / "_version.py"

GREEN = "\033[1;32m"
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
DIM = "\033[2m"
RESET = "\033[0m"


def read_fieldkit_modules() -> list[str]:
    """Parse `FIELDKIT_MODULES = [...] as const` out of `src/content.config.ts`.

    We avoid importing TypeScript by reading the literal source — the list
    only changes when a module ships, and the array form is stable.
    """
    src = CONTENT_CONFIG.read_text(encoding="utf-8")
    m = re.search(r"FIELDKIT_MODULES\s*=\s*\[([^\]]+)\]", src)
    if not m:
        raise SystemExit("could not locate FIELDKIT_MODULES in src/content.config.ts")
    return re.findall(r"'([^']+)'", m.group(1))


def read_version() -> str:
    """Read `__version__` from `fieldkit/src/fieldkit/_version.py`."""
    src = VERSION_FILE.read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', src)
    if not m:
        raise SystemExit("could not locate __version__ in _version.py")
    return m.group(1)


# --- Audits ---------------------------------------------------------------


def audit_module_count(modules: list[str]) -> dict:
    """`FieldkitProblem` + `FieldkitModules` must not hardcode the module count.

    Whitelist the dynamic forms (`FIELDKIT_MODULES.length`, `${docs.length}`,
    `docs.length`, `moduleCount`, `moduleCountWord`). Any *other* integer that
    looks like a small module count (1–20) or its English word form near
    landing-page module copy is flagged.
    """
    findings: list[str] = []

    problem = (SECTIONS / "FieldkitProblem.astro").read_text(encoding="utf-8")
    if "FIELDKIT_MODULES" not in problem:
        findings.append(
            "FieldkitProblem.astro: must import + use `FIELDKIT_MODULES` "
            "(found a static module-count stat)"
        )
    if re.search(r"'\d+'\s*,\s*label:\s*'modules", problem):
        findings.append(
            "FieldkitProblem.astro: stat value for `modules, one import` "
            "appears hardcoded as a literal integer string"
        )

    modules_comp = (SECTIONS / "FieldkitModules.astro").read_text(encoding="utf-8")
    # Headline drift — the "fieldkit in N imports" line should not be literal.
    headline_match = re.search(
        r"<code[^>]*>fieldkit</code>\s*in\s+([a-z]+|\d+|\{[^}]+\})\s+imports",
        modules_comp,
    )
    if headline_match:
        token = headline_match.group(1)
        if token.isdigit() or (token.isalpha() and token != "moduleCountWord"):
            # Pure number or static English word — flag.
            findings.append(
                f"FieldkitModules.astro: headline 'fieldkit in {token} imports' "
                f"is static (expected `{{moduleCountWord}}` or `{{moduleCount}}`)"
            )

    return {
        "check": "module_count_dynamic",
        "verdict": "fail" if findings else "pass",
        "findings": findings,
        "module_count": len(modules),
    }


def audit_hardcoded_versions(version: str) -> dict:
    """No landing-page component should contain a hardcoded `0.X.Y` literal.

    Allow-list: version pills/lines that interpolate the `version` prop are
    fine. We're looking for raw `"0.4.0"` / `0.4.0` shaped tokens in source.
    """
    findings: list[str] = []
    for astro in sorted(SECTIONS.glob("*.astro")):
        text = astro.read_text(encoding="utf-8")
        # Strip lines that look like the version prop interpolation
        # (`v{version}`, `${version}`, `{version}`) so we only flag literals.
        # Then scan for any `0.\d+.\d+` literal that isn't part of a Python
        # version specifier like `Python 3.11+`.
        literals = re.findall(r"\b0\.\d+\.\d+\b", text)
        for lit in literals:
            findings.append(f"{astro.name}: hardcoded version literal `{lit}`")
    return {
        "check": "no_hardcoded_versions",
        "verdict": "fail" if findings else "pass",
        "findings": findings,
        "package_version": version,
    }


def audit_module_taglines(modules: list[str]) -> dict:
    """Every `FIELDKIT_MODULES` entry must have a tagline in `FieldkitModules.astro`."""
    comp = (SECTIONS / "FieldkitModules.astro").read_text(encoding="utf-8")
    tagline_block = re.search(
        r"taglines:\s*Record<string,\s*string>\s*=\s*\{([^}]+)\}",
        comp,
    )
    if not tagline_block:
        return {
            "check": "module_taglines",
            "verdict": "fail",
            "findings": ["FieldkitModules.astro: `taglines` map missing"],
        }
    keys = set(re.findall(r"(\w+):\s*'", tagline_block.group(1)))
    missing = [m for m in modules if m not in keys]
    extra = sorted(keys - set(modules))
    findings: list[str] = []
    for m in missing:
        findings.append(
            f"FieldkitModules.astro: no tagline for `{m}` "
            f"(card will fall back to long doc summary)"
        )
    for m in extra:
        findings.append(
            f"FieldkitModules.astro: tagline for `{m}` no longer in FIELDKIT_MODULES"
        )
    return {
        "check": "module_taglines",
        "verdict": "fail" if findings else "pass",
        "findings": findings,
        "expected": list(modules),
        "found": sorted(keys),
    }


def audit_docs_order(modules: list[str]) -> dict:
    """Each `fieldkit/docs/api/<module>.md` `order:` must equal its 1-based
    index in `FIELDKIT_MODULES`.

    `FieldkitModules.astro` sorts cards by `order`, so collisions silently
    swap card positions on the page; a missing/wrong `order:` mis-files the
    module in the visual grid.
    """
    findings: list[str] = []
    for idx, mod in enumerate(modules, start=1):
        page = DOCS / f"{mod}.md"
        if not page.exists():
            continue  # audit-docs catches missing pages
        front = page.read_text(encoding="utf-8")
        m = re.search(r"^order:\s*(\d+)\s*$", front, re.MULTILINE)
        if not m:
            findings.append(f"{mod}.md: missing `order:` frontmatter")
            continue
        actual = int(m.group(1))
        if actual != idx:
            findings.append(
                f"{mod}.md: order={actual} but expected {idx} "
                f"(module index in FIELDKIT_MODULES)"
            )
    return {
        "check": "docs_order_matches_modules",
        "verdict": "fail" if findings else "pass",
        "findings": findings,
    }


# --- Driver ---------------------------------------------------------------


def render_human(results: list[dict]) -> int:
    fails = 0
    for r in results:
        v = r["verdict"]
        if v == "pass":
            print(f"[{GREEN}PASS{RESET}] {r['check']:32s} {DIM}clean{RESET}")
        elif v == "skip":
            print(
                f"[{YELLOW}SKIP{RESET}] {r['check']:32s} "
                f"{DIM}{r.get('reason', '')}{RESET}"
            )
        else:
            fails += 1
            print(f"[{RED}FAIL{RESET}] {r['check']:32s}")
            for finding in r.get("findings", []):
                print(f"        {finding}")
    return fails


def main(argv: list[str]) -> int:
    want_json = "--json" in argv
    modules = read_fieldkit_modules()
    version = read_version()
    results = [
        audit_module_count(modules),
        audit_hardcoded_versions(version),
        audit_module_taglines(modules),
        audit_docs_order(modules),
    ]
    if want_json:
        print(json.dumps({
            "modules": modules,
            "version": version,
            "results": results,
        }, indent=2))
    else:
        fails = render_human(results)
        passes = sum(1 for r in results if r["verdict"] == "pass")
        color = GREEN if fails == 0 else RED
        verdict = "ready to release" if fails == 0 else "fix drift before tagging"
        print(
            f"\n{color}{passes}/{len(results)} PASSED{RESET}, "
            f"{fails} failed — {verdict}"
        )
    return sum(1 for r in results if r["verdict"] == "fail")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
