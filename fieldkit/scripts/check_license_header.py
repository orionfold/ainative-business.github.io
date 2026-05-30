#!/usr/bin/env python3
# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Pre-commit hook: enforce a short Apache-2.0 SPDX header on every fieldkit Python file.

We deliberately use the short SPDX form rather than the full 15-line Apache
preamble so the header doesn't dominate small files. The full LICENSE text
lives at fieldkit/LICENSE.

Required header (first comment lines after an optional shebang / encoding line):

    # Copyright <year> Manav Sehgal
    # SPDX-License-Identifier: Apache-2.0

Run manually:
    fieldkit/scripts/check_license_header.py path/to/file.py [...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

COPYRIGHT_RE = re.compile(r"^# Copyright \d{4} Manav Sehgal\s*$")
SPDX_LINE = "# SPDX-License-Identifier: Apache-2.0"


def has_required_header(path: Path) -> bool:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return False

    head = []
    for line in lines:
        if not head and (line.startswith("#!") or line.startswith("# -*-")):
            continue
        head.append(line)
        if len(head) == 2:
            break

    if len(head) < 2:
        return False
    return bool(COPYRIGHT_RE.match(head[0])) and head[1].strip() == SPDX_LINE


def main(argv: list[str]) -> int:
    missing = [p for p in argv if not has_required_header(Path(p))]
    if missing:
        sys.stderr.write(
            "Missing Apache-2.0 SPDX header in:\n  "
            + "\n  ".join(missing)
            + "\n\nAdd these two lines after any shebang / encoding line:\n"
            "  # Copyright 2026 Manav Sehgal\n"
            f"  {SPDX_LINE}\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
