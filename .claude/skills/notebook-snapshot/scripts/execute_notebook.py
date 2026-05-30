#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Execute a notebook headless with a chosen runtime parameter, surfacing
errors instead of hiding them. DETERMINISTIC — no LLM.

Prefers papermill (injects the `runtime` parameter into the `parameters`-tagged
cell); falls back to `jupyter nbconvert --execute --allow-errors` with
`FIELDKIT_RUNTIME` in the env. Either way `--allow-errors` semantics hold: a
failing cell renders its traceback into the output so the snapshot tells the
truth (spec §13).

Output goes to /tmp scratch — only the final marketing PNGs are tracked.

Usage:
    execute_notebook.py --notebook notebooks/patent-strategist/user.ipynb \
        --runtime spark [--out /tmp/aifn-nb-snapshot/<v>/user.executed.ipynb] \
        [--timeout 1800]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRATCH = Path("/tmp/aifn-nb-snapshot")


def _default_out(notebook: Path) -> Path:
    vertical = notebook.parent.name
    return SCRATCH / vertical / f"{notebook.stem}.executed.ipynb"


def run_papermill(nb_in: Path, nb_out: Path, runtime: str, timeout: int) -> int:
    import papermill as pm
    nb_out.parent.mkdir(parents=True, exist_ok=True)
    pm.execute_notebook(
        str(nb_in), str(nb_out),
        parameters={"runtime": runtime},
        kernel_name="python3",
        execution_timeout=timeout,
        # papermill raises on cell error by default; mimic --allow-errors so the
        # traceback is captured in the output cell rather than aborting.
        progress_bar=False,
    )
    return 0


def run_nbconvert(nb_in: Path, nb_out: Path, runtime: str, timeout: int) -> int:
    env = dict(os.environ)
    if runtime != "auto":
        env["FIELDKIT_RUNTIME"] = runtime
    nb_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook",
        "--execute", "--allow-errors",
        f"--ExecutePreprocessor.timeout={timeout}",
        "--output", nb_out.name, "--output-dir", str(nb_out.parent), str(nb_in),
    ]
    return subprocess.run(cmd, env=env).returncode


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--notebook", required=True, type=Path)
    ap.add_argument("--runtime", default="spark",
                    choices=["spark", "colab", "kaggle", "local", "auto"])
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args(argv)

    if not args.notebook.exists():
        print(f"notebook not found: {args.notebook}", file=sys.stderr)
        return 2
    out = args.out or _default_out(args.notebook)

    try:
        import papermill  # noqa: F401
        # papermill aborts on first error; for --allow-errors parity, fall to
        # nbconvert when a cell raises. Try papermill, on failure use nbconvert.
        try:
            rc = run_papermill(args.notebook, out, args.runtime, args.timeout)
        except Exception as exc:  # noqa: BLE001 - cell error → fall back to allow-errors path
            print(f"papermill raised ({exc}); re-running via nbconvert --allow-errors",
                  file=sys.stderr)
            rc = run_nbconvert(args.notebook, out, args.runtime, args.timeout)
    except ImportError:
        rc = run_nbconvert(args.notebook, out, args.runtime, args.timeout)

    if out.exists():
        print(f"executed → {out}")
        print(f"runtime={args.runtime}; next: export_figures.py + notebook_to_html.py")
    else:
        print("execution produced no output notebook", file=sys.stderr)
        return rc or 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
