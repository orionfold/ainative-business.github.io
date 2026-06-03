#!/usr/bin/env python3
"""fieldkit-curator audit-docs — drift check for `fieldkit/docs/api/<module>.md`.

For each module in `FIELDKIT_MODULES`, parses the module's `__all__` via AST and
verifies every exported symbol is mentioned somewhere in the corresponding API
doc file. Catches four kinds of release-blocking drift:

  1. **Missing API page** — the module exists in source + ships in the package,
     but `fieldkit/docs/api/<module>.md` doesn't. The Astro `/fieldkit/api/<mod>/`
     route would 404. This is the v0.4 trap that motivated this script.
  2. **Missing symbol** — a new class/function/constant landed in `__all__`
     but the docs file doesn't mention it (substring match against the source
     text, with word-boundary regex so `Capability` doesn't false-match
     `Capabilities`).
  3. **Mention of a removed symbol** — the docs reference a name no longer in
     `__all__`. Surfaces in the orphans report but doesn't fail the audit on
     its own (prose may legitimately reference removed APIs in a Changelog
     paragraph).
  4. **Kwarg drift** — a public function (top-level or method of a class in
     `__all__`) has a keyword-only argument that isn't mentioned in the docs
     file. The v0.4.1 trap: `VerticalBench.from_jsonl` gained `open_book` +
     `subset` kwargs but the docs page still documented the v0.4.0 signature.
     **Soft warning by default** (visibility-only, doesn't fail the audit) so
     pre-existing drift across modules doesn't block tagging. Pass
     `--strict-kwargs` to elevate kwarg drift to a hard FAIL; the
     `fieldkit-curator release` flow flips this on once existing drift is
     documented.

Exit code = number of audit FAILs (kinds 1 + 2; also 4 when `--strict-kwargs`).
0 means ready to release.

Usage:
  python3 audit_docs.py
  python3 audit_docs.py --json             # machine-readable output for `release` flow
  python3 audit_docs.py --strict-kwargs    # elevate kwarg drift to FAIL
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

REPO = Path("/home/nvidia/ainative-business.github.io")
PKG = REPO / "fieldkit" / "src" / "fieldkit"
DOCS = REPO / "fieldkit" / "docs" / "api"

# Canonical module list — mirrors src/content.config.ts FIELDKIT_MODULES.
# If FIELDKIT_MODULES grows, update this list (or read it from content.config.ts,
# but that's overkill for nine entries that change every quarter at most).
MODULES = [
    "capabilities", "nim", "rag", "eval", "training",
    "lineage", "quant", "publish", "cli", "viz", "notebook", "harness",
    "arena", "cost", "memory",
]

# Visual output toggles
GREEN = "\033[1;32m"
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
DIM = "\033[2m"
RESET = "\033[0m"


def find_module_source(module_name: str) -> Path | None:
    """Return the importable source file for `fieldkit.<module_name>`.

    Packages export from `<mod>/__init__.py`; flat modules from `<mod>.py`.
    We document the package's public surface, so for packages we always look
    at the top-level __init__ (sub-module symbols would be tracked there via
    re-exports).
    """
    package_init = PKG / module_name / "__init__.py"
    flat_module = PKG / f"{module_name}.py"
    if package_init.exists():
        return package_init
    if flat_module.exists():
        return flat_module
    return None


def extract_all_symbols(source: Path) -> list[str]:
    """Parse `__all__ = [...]` (or tuple) from a Python module's source.

    Returns `[]` if `__all__` is missing OR is not a plain list/tuple of string
    literals (e.g. computed `__all__`). For audit purposes we want the curated
    public surface — modules without an explicit `__all__` aren't audited.
    """
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets_are_all = any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        )
        if not targets_are_all:
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            return []
        symbols: list[str] = []
        for el in node.value.elts:
            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                symbols.append(el.value)
        return symbols
    return []


def mentioned_symbols(docs_text: str, symbols: list[str]) -> set[str]:
    """Return the subset of `symbols` mentioned in `docs_text` via word-boundary match."""
    hit: set[str] = set()
    for sym in symbols:
        if re.search(rf"\b{re.escape(sym)}\b", docs_text):
            hit.add(sym)
    return hit


def find_module_sources(module_name: str) -> list[Path]:
    """Return all .py source files contributing to `fieldkit.<module_name>`.

    For flat modules: just `<mod>.py`. For packages: `<mod>/__init__.py` plus
    every `<mod>/*.py` sub-module (e.g. `eval/vertical.py`, `quant/_paths.py`).
    Sub-modules are included so kwargs on methods of classes re-exported from
    `__init__.py` (like `VerticalBench` defined in `eval/vertical.py`) are
    discoverable.
    """
    package_dir = PKG / module_name
    flat_file = PKG / f"{module_name}.py"
    if package_dir.is_dir():
        init = package_dir / "__init__.py"
        subs = sorted(p for p in package_dir.glob("*.py") if p.name != "__init__.py")
        return ([init] if init.exists() else []) + subs
    if flat_file.exists():
        return [flat_file]
    return []


def collect_public_kwargs(
    sources: list[Path], class_names_in_all: set[str], function_names_in_all: set[str]
) -> list[tuple[str, str]]:
    """Return [(qualified_name, kwarg)] for every keyword-only arg on a public
    function or method we should document.

    Scope:
      - Top-level `def` whose name is in `__all__` (i.e. a publicly-exported function).
      - Method `def` inside `class` whose class name is in `__all__`, where the
        method name doesn't start with `_` (skips dunders + private helpers).
      - Only **keyword-only** args (after `*` or `*args`) — these are the explicit
        "options" surface where additive-kwarg drift happens. Positional args
        are typically obvious from the signature snippet and don't need a separate
        prose entry.
    """
    pairs: list[tuple[str, str]] = []
    for src in sources:
        try:
            tree = ast.parse(src.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in function_names_in_all and not node.name.startswith("_"):
                    for a in node.args.kwonlyargs:
                        pairs.append((node.name, a.arg))
            elif isinstance(node, ast.ClassDef) and node.name in class_names_in_all:
                for m in node.body:
                    if not isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if m.name.startswith("_"):
                        continue
                    for a in m.args.kwonlyargs:
                        pairs.append((f"{node.name}.{m.name}", a.arg))
    return pairs


def kwarg_drift(docs_text: str, kwarg_pairs: list[tuple[str, str]]) -> list[str]:
    """Return ["Symbol.method(kwarg)", ...] for kwargs not mentioned in docs.

    Match via word-boundary regex (same convention as symbol coverage). A kwarg
    is "mentioned" if its name appears anywhere in the docs — the audit doesn't
    enforce *how* it's documented, only that prose acknowledges its existence.
    """
    missing: list[str] = []
    for qual, kw in kwarg_pairs:
        if not re.search(rf"\b{re.escape(kw)}\b", docs_text):
            missing.append(f"{qual}({kw})")
    return missing


def audit_module(module_name: str) -> dict:
    """Run the audit for one module. Returns a dict with the verdict + details."""
    source = find_module_source(module_name)
    if source is None:
        return {
            "module": module_name,
            "verdict": "skip",
            "reason": f"no source file at {PKG}/{module_name}[.py | /__init__.py]",
        }

    symbols = extract_all_symbols(source)
    if not symbols:
        return {
            "module": module_name,
            "verdict": "skip",
            "reason": f"{source.name} has no explicit `__all__` (or it's computed)",
        }

    docs_md = DOCS / f"{module_name}.md"
    if not docs_md.exists():
        return {
            "module": module_name,
            "verdict": "fail",
            "reason": f"docs file missing: {docs_md}",
            "exported": len(symbols),
            "missing": symbols,
        }

    docs_text = docs_md.read_text(encoding="utf-8")
    hit = mentioned_symbols(docs_text, symbols)
    missing = [s for s in symbols if s not in hit]

    # Kwarg-drift check (warn-by-default, fail with --strict-kwargs).
    # Discover public functions + classes from `__all__`; AST-walk the module's
    # sources (init + sub-modules); collect kwonly args; check docs coverage.
    sources = find_module_sources(module_name)
    fn_set: set[str] = set()
    cls_set: set[str] = set()
    try:
        # Re-parse to classify __all__ entries into functions vs classes.
        for src in sources:
            tree = ast.parse(src.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in symbols:
                    fn_set.add(node.name)
                elif isinstance(node, ast.ClassDef) and node.name in symbols:
                    cls_set.add(node.name)
    except SyntaxError:
        pass
    kwarg_pairs = collect_public_kwargs(sources, cls_set, fn_set)
    kwargs_missing = kwarg_drift(docs_text, kwarg_pairs)

    if missing:
        return {
            "module": module_name,
            "verdict": "fail",
            "reason": f"{len(missing)} of {len(symbols)} symbols undocumented",
            "exported": len(symbols),
            "missing": missing,
            "kwargs_total": len(kwarg_pairs),
            "kwargs_missing": kwargs_missing,
        }

    return {
        "module": module_name,
        "verdict": "pass",
        "exported": len(symbols),
        "kwargs_total": len(kwarg_pairs),
        "kwargs_missing": kwargs_missing,
    }


def render_human(results: list[dict], strict_kwargs: bool) -> tuple[int, int]:
    """Print a human-readable table. Returns (fails, warns).

    Warns are kwarg-drift items when not in strict mode; they are upgraded to
    fails when `--strict-kwargs` is on.
    """
    fails = 0
    warns = 0
    for r in results:
        v = r["verdict"]
        if v == "pass":
            print(
                f"[{GREEN}PASS{RESET}] {r['module']:14s} "
                f"{DIM}all {r['exported']} __all__ symbols documented{RESET}"
            )
        elif v == "skip":
            print(
                f"[{YELLOW}SKIP{RESET}] {r['module']:14s} "
                f"{DIM}{r['reason']}{RESET}"
            )
        else:  # fail
            fails += 1
            print(
                f"[{RED}FAIL{RESET}] {r['module']:14s} {r['reason']}"
            )
            if "missing" in r and r["missing"]:
                preview = ", ".join(r["missing"][:5])
                ellipsis = "…" if len(r["missing"]) > 5 else ""
                print(f"        missing: {preview}{ellipsis}")
        # Kwarg drift sub-line — applies whether the symbol-coverage verdict
        # passed or failed. SKIP modules have no kwarg data.
        if v != "skip" and r.get("kwargs_missing"):
            count = len(r["kwargs_missing"])
            total = r.get("kwargs_total", 0)
            preview = ", ".join(r["kwargs_missing"][:4])
            ellipsis = "…" if count > 4 else ""
            label = f"{RED}FAIL{RESET}" if strict_kwargs else f"{YELLOW}WARN{RESET}"
            print(
                f"        [{label}] kwarg drift: {count}/{total} undocumented — "
                f"{preview}{ellipsis}"
            )
            if strict_kwargs:
                fails += 1
            else:
                warns += 1
    return fails, warns


def main(argv: list[str]) -> int:
    want_json = "--json" in argv
    strict_kwargs = "--strict-kwargs" in argv
    results = [audit_module(m) for m in MODULES]

    if want_json:
        print(json.dumps({"results": results, "strict_kwargs": strict_kwargs}, indent=2))
        # Exit code follows the strict-kwargs flag in JSON mode too.
        sym_fails = sum(1 for r in results if r["verdict"] == "fail")
        kwarg_fails = (
            sum(1 for r in results if r.get("kwargs_missing")) if strict_kwargs else 0
        )
        return sym_fails + kwarg_fails

    fails, warns = render_human(results, strict_kwargs)
    passes = sum(1 for r in results if r["verdict"] == "pass")
    skips = sum(1 for r in results if r["verdict"] == "skip")
    color = GREEN if fails == 0 else RED
    verdict = "ready to release" if fails == 0 else "fix drift before tagging"
    summary = (
        f"\n{color}{passes}/{len(MODULES)} PASSED{RESET}, "
        f"{skips} skipped, {fails} failed"
    )
    if warns:
        summary += f", {YELLOW}{warns} kwarg-drift WARN{RESET} (pass --strict-kwargs to fail on these)"
    summary += f" — {verdict}"
    print(summary)

    return fails


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
