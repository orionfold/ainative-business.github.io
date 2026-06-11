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
  3. **Module tagline coverage + balance** — both copies of
     `FieldkitModules.astro` (main site AND `arena-app/src/.../fieldkit/` —
     the arena-app copy is the easy miss) carry a per-module `taglines` map;
     every entry in `FIELDKIT_MODULES` must have a tagline ≤56 chars, else
     the card falls back to the doc summary (longer and visually misaligned)
     or one card's anchor line wraps while its siblings don't. Catches the
     pre-v0.31 drift where arena-app froze at 13 taglines after 5 modules
     shipped and `arena`'s tagline ran 71 chars.
  4. **Doc-page order frontmatter** — `fieldkit/docs/api/<module>.md`
     frontmatter `order:` must equal the module's 1-based index in
     `FIELDKIT_MODULES`. Catches the v0.4 collision where `cli.md` stayed
     at order=7 after `quant`/`publish` shifted it to 9.
  5. **Landing version source** — `src/pages/fieldkit/index.astro` must read
     the package's canonical `fieldkit/src/fieldkit/_version.py`, and the
     retired two-repo-era mirror `fieldkit/_version.py` must not exist.
     Catches the post-cutover drift where the live page rendered v0.13.0
     for 18 releases (caught 2026-06-10) because releases bumped only the
     canonical file while the page read the orphaned mirror.
  6. **Doc summary balance** — each `fieldkit/docs/api/<module>.md`
     `summary:` renders verbatim as the landing-card body, so it must stay
     reader-facing and balanced: 60–260 chars, no internal milestone
     codenames (`M6`, `H3`, `Bet 5`, `Phase 2`, `_SPECS/` paths). Catches
     the pre-v0.31 state where `training`'s summary ran ~780 chars beside
     `cli`'s 96 and `arena`'s read like a ship log.

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
ARENA_SECTIONS = REPO / "arena-app" / "src" / "components" / "sections" / "fieldkit"
CONTENT_CONFIG = REPO / "src" / "content.config.ts"
DOCS = REPO / "fieldkit" / "docs" / "api"
VERSION_FILE = REPO / "fieldkit" / "src" / "fieldkit" / "_version.py"
LANDING_PAGE = REPO / "src" / "pages" / "fieldkit" / "index.astro"
RETIRED_VERSION_MIRROR = REPO / "fieldkit" / "_version.py"

# Doc summaries render verbatim as landing-card bodies.
SUMMARY_MIN_CHARS = 60
SUMMARY_MAX_CHARS = 260
TAGLINE_MAX_CHARS = 56
# Internal milestone codenames that mean nothing to a reader landing on the
# page: arena milestones (M6), harness stages (H3), corpus waves (W3),
# bet/phase numbering, and spec paths.
INTERNAL_CODENAME_RE = re.compile(
    r"\b(?:[MHW]\d{1,2}|Bet\s+\d|Phase\s+\d(?:\.\d)?)\b|_SPECS/"
)

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
    # The array literal may be assigned to FIELDKIT_MODULES directly, or (the
    # monorepo form) to a lowercase `fieldkitModules` const that FIELDKIT_MODULES
    # then re-exports. Match the literal under either name.
    m = re.search(r"FIELDKIT_MODULES\s*=\s*\[([^\]]+)\]", src) or re.search(
        r"fieldkitModules\s*=\s*\[([^\]]+)\]", src
    )
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
    """Every `FIELDKIT_MODULES` entry must have a ≤56-char tagline in BOTH
    copies of `FieldkitModules.astro` (main site + arena-app)."""
    findings: list[str] = []
    found: dict[str, list[str]] = {}
    copies = {
        "FieldkitModules.astro": SECTIONS / "FieldkitModules.astro",
        "arena-app FieldkitModules.astro": ARENA_SECTIONS / "FieldkitModules.astro",
    }
    for label, path in copies.items():
        if not path.exists():
            findings.append(f"{label}: file missing at {path}")
            continue
        comp = path.read_text(encoding="utf-8")
        tagline_block = re.search(
            r"taglines:\s*Record<string,\s*string>\s*=\s*\{([^}]+)\}",
            comp,
        )
        if not tagline_block:
            findings.append(f"{label}: `taglines` map missing")
            continue
        entries = dict(re.findall(r"(\w+):\s*'([^']*)'", tagline_block.group(1)))
        found[label] = sorted(entries)
        for m in modules:
            if m not in entries:
                findings.append(
                    f"{label}: no tagline for `{m}` "
                    f"(card will fall back to long doc summary)"
                )
        for m in sorted(set(entries) - set(modules)):
            findings.append(f"{label}: tagline for `{m}` no longer in FIELDKIT_MODULES")
        for m, tag in entries.items():
            if len(tag) > TAGLINE_MAX_CHARS:
                findings.append(
                    f"{label}: tagline for `{m}` is {len(tag)} chars "
                    f"(max {TAGLINE_MAX_CHARS}) — `{tag}`"
                )
    return {
        "check": "module_taglines",
        "verdict": "fail" if findings else "pass",
        "findings": findings,
        "expected": list(modules),
        "found": found,
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


def audit_version_source() -> dict:
    """The landing page must read the package's canonical version file.

    `src/pages/fieldkit/index.astro` reads `_version.py` at build time. It
    must point at `fieldkit/src/fieldkit/_version.py` (the hatch single
    source of truth that releases bump) — and the retired two-repo-era
    mirror `fieldkit/_version.py` must not exist, or the page silently
    freezes at whatever version the mirror last saw (v0.13.0 for 18
    releases, 2026-06-10).
    """
    findings: list[str] = []
    if not LANDING_PAGE.exists():
        findings.append(f"landing page missing at {LANDING_PAGE}")
    else:
        text = LANDING_PAGE.read_text(encoding="utf-8")
        if "fieldkit/src/fieldkit/_version.py" not in text:
            findings.append(
                "index.astro: does not read `fieldkit/src/fieldkit/_version.py` "
                "(the canonical version source releases bump)"
            )
        if re.search(r"['\"]fieldkit/_version\.py['\"]", text):
            findings.append(
                "index.astro: reads the retired `fieldkit/_version.py` mirror"
            )
    if RETIRED_VERSION_MIRROR.exists():
        findings.append(
            "fieldkit/_version.py: retired two-repo-era version mirror exists "
            "— delete it; nothing should maintain or read it since the "
            "2026-05-29 monorepo cutover"
        )
    return {
        "check": "landing_version_source",
        "verdict": "fail" if findings else "pass",
        "findings": findings,
    }


def audit_summary_balance(modules: list[str]) -> dict:
    """Doc `summary:` frontmatter renders verbatim as the landing-card body.

    Keep every summary reader-facing and balanced: 60–260 chars, no internal
    milestone codenames (`M6` / `H3` / `W3` / `Bet 5` / `Phase 2` / `_SPECS/`
    paths). The ship-log detail belongs in the doc body, not the card.
    """
    findings: list[str] = []
    lengths: dict[str, int] = {}
    for mod in modules:
        page = DOCS / f"{mod}.md"
        if not page.exists():
            continue  # audit-docs catches missing pages
        m = re.search(r"^summary:\s*(.+)$", page.read_text(encoding="utf-8"), re.MULTILINE)
        if not m:
            findings.append(f"{mod}.md: missing `summary:` frontmatter")
            continue
        summary = m.group(1).strip().strip("\"'")
        lengths[mod] = len(summary)
        if len(summary) > SUMMARY_MAX_CHARS:
            findings.append(
                f"{mod}.md: summary is {len(summary)} chars "
                f"(max {SUMMARY_MAX_CHARS}) — move the detail into the doc body"
            )
        elif len(summary) < SUMMARY_MIN_CHARS:
            findings.append(
                f"{mod}.md: summary is {len(summary)} chars "
                f"(min {SUMMARY_MIN_CHARS}) — too thin to anchor a landing card"
            )
        codenames = INTERNAL_CODENAME_RE.findall(summary)
        if codenames:
            shown = ", ".join(f"`{c}`" for c in codenames if c) or "`_SPECS/`"
            findings.append(
                f"{mod}.md: summary leaks internal codenames ({shown}) — "
                f"rewrite reader-facing"
            )
    return {
        "check": "doc_summary_balance",
        "verdict": "fail" if findings else "pass",
        "findings": findings,
        "lengths": lengths,
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
        audit_version_source(),
        audit_summary_balance(modules),
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
