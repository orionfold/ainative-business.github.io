# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Side-effectful Arena scripts (M2 onward).

This package holds the **runnable** scripts that operate on a live
``~/.fieldkit/arena.db`` — the retroactive M2 import + the M6/M7
mirror/export drivers. The logic lives in sibling modules
(``fieldkit.arena.importer``, ``fieldkit.arena.mirror``); these scripts
are thin ``if __name__ == "__main__"`` shims so a `python -m` invocation
works alongside the ``fieldkit arena <cmd>`` Typer CLI.
"""

__all__: list[str] = []
