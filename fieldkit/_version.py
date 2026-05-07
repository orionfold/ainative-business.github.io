# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Single source of truth for the fieldkit version.

`pyproject.toml`'s `[tool.hatch.version]` reads `__version__` from this file at
build time, so bumping it here is enough to bump the wheel version too.
"""

__version__ = "0.2.0.post1"
