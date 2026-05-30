# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Build + bake the Orionfold Arena web UI into the fieldkit wheel (P7).

The runnable cockpit ships *inside* the package: a self-contained Astro build
rooted at ``base: '/arena'`` (``ARENA_BUILD=1``) is pruned into
``fieldkit/src/fieldkit/arena/_webui/`` and declared in ``pyproject.toml``'s
hatch ``include`` lists so ``pip install fieldkit[arena]`` carries it. The
sidecar serves it via a ``StaticFiles`` mount at ``/arena`` (same mechanism as
``eval/rubrics/*.md`` data files).

``build_webui`` is **builder-side only** — it shells out to the Astro
toolchain in the website checkout (per ``reference_astro_build_smb_symlink_break``
it invokes ``node node_modules/astro/astro.js`` directly, never ``npm``). A
pip-installed fieldkit on an arbitrary box can't run it (no Node / no website),
which is fine: ``fieldkit arena up`` just *serves* the pre-baked bundle.

Deterministic file orchestration only — no LLM, no network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["build_webui", "webui_dir", "bundle_present", "BuildWebUIReport"]


def webui_dir() -> Path:
    """Absolute path to the packaged ``_webui/`` dir inside this package."""
    return Path(__file__).resolve().parent / "_webui"


def bundle_present() -> bool:
    """True if the baked bundle is present (``_webui/index.html`` exists)."""
    return (webui_dir() / "index.html").is_file()


@dataclass
class BuildWebUIReport:
    """Outcome of :func:`build_webui`."""

    dest: str
    files_copied: int
    bytes_copied: int
    pages: int

    def summary_line(self) -> str:
        mb = self.bytes_copied / (1024 * 1024)
        return (
            f"{self.pages} page(s), {self.files_copied} files, "
            f"{mb:.1f} MB → {self.dest}"
        )


# Top-level entries (relative to the Astro outDir) that make up the
# self-contained arena bundle. ``arena/`` holds the routed pages; ``assets/``
# holds the shared hashed JS/CSS/fonts (build.assets='assets'); favicon is
# referenced as ``/arena/favicon.svg`` by the layout <head>.
_SHARED = ("assets", "favicon.svg")

# The whole-site build puts every page's hashed assets in one ``assets/`` dir,
# including editorial article hero images the dark cockpit never references.
# The cockpit is all CSS/SVG/canvas, so we drop raster images from the bake to
# keep the wheel lean (saves ~1 MB of dead webp/png per the v0.2 build).
_DROP_ASSET_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".avif"}

# Demo-only top-level dir copied verbatim (no image drop): the sidecar-less
# fetch/EventSource shim + recorded fixtures, referenced as
# ``/arena/arena-demo/{boot.js,fixtures.json}``. See
# ``reference_arena_demo_mode``. (Emitted from ``public/arena-demo/`` by Astro.)
_DEMO_EXTRA = ("arena-demo",)


def build_webui(
    repo_root: str | os.PathLike[str] | None = None,
    *,
    dest: str | os.PathLike[str] | None = None,
    skip_astro: bool = False,
    demo: bool = False,
) -> BuildWebUIReport:
    """Run the Astro arena build and prune the ``/arena`` bundle.

    Two modes, sharing one prune (promote ``arena/*`` → bundle root so
    ``/arena/`` is the cockpit and the absolute single-``/arena/`` nav hrefs
    resolve; copy shared ``assets/``+favicon, dropping raster images):

    * **wheel** (default) — ``ARENA_BUILD=1`` → ``dist-arena/`` → pruned into the
      packaged :func:`webui_dir` (``_webui/``) so ``pip install fieldkit[arena]``
      ships it; served by the sidecar's ``StaticFiles`` mount.
    * **demo** (``demo=True``) — ``ARENA_DEMO=1`` → ``dist-arena-demo/`` → pruned
      into ``dist-arena-demo-pruned/`` for the sidecar-less public web preview
      (GitHub Pages). Adds the demo-only ``arena-demo/`` dir (the fetch/EventSource
      shim + recorded fixtures) and a ``.nojekyll`` marker (GH Pages' Jekyll would
      otherwise strip ``assets/_slug_*.css``). See ``reference_arena_demo_mode``.

    Parameters
    ----------
    repo_root
        The website checkout root (must contain ``astro.config.mjs`` +
        ``node_modules/astro``). Defaults to the current working directory.
    dest
        Override the bake destination. Defaults to the packaged
        :func:`webui_dir` (wheel mode) or ``<repo_root>/dist-arena-demo-pruned``
        (demo mode).
    skip_astro
        Skip the Astro invocation and only re-prune the existing build output
        (used by tests + fast re-bakes).
    demo
        Build the sidecar-less demo bundle instead of the wheel bundle.
    """
    root = Path(repo_root or Path.cwd()).resolve()
    if demo:
        env_flag = "ARENA_DEMO"
        out_dir = root / "dist-arena-demo"
        default_target = root / "dist-arena-demo-pruned"
    else:
        env_flag = "ARENA_BUILD"
        out_dir = root / "dist-arena"
        default_target = webui_dir()
    target = Path(dest) if dest else default_target

    if not skip_astro:
        astro_cli = root / "node_modules" / "astro" / "astro.js"
        if not astro_cli.is_file():
            raise RuntimeError(
                f"Astro toolchain not found at {astro_cli}. `fieldkit arena build` "
                f"is builder-side only — run it from the ai-field-notes website "
                f"checkout (where node_modules/astro lives). End users run "
                f"`fieldkit arena up`, which serves the pre-baked bundle."
            )
        env = dict(os.environ)
        env[env_flag] = "1"
        # Per reference_astro_build_smb_symlink_break: invoke astro.js via node
        # directly — the .bin/astro symlink is flattened on the SMB checkout.
        subprocess.run(
            ["node", str(astro_cli), "build"],
            cwd=str(root),
            env=env,
            check=True,
        )

    arena_pages = out_dir / "arena"
    if not (arena_pages / "index.html").is_file():
        raise RuntimeError(
            f"Expected arena pages at {arena_pages}/index.html after the build — "
            f"did the {env_flag} gate in astro.config.mjs run? (outDir={out_dir})"
        )

    # Fresh bake: wipe the target, then copy arena pages (stripping the
    # arena/ prefix) + the shared asset dirs.
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    files_copied = 0
    bytes_copied = 0
    pages = 0

    def _copy_tree(src: Path, dst: Path, *, drop_images: bool = False) -> None:
        nonlocal files_copied, bytes_copied, pages
        for p in src.rglob("*"):
            if p.is_dir():
                continue
            if drop_images and p.suffix.lower() in _DROP_ASSET_EXTS:
                continue
            rel = p.relative_to(src)
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
            files_copied += 1
            bytes_copied += p.stat().st_size
            if p.name == "index.html":
                pages += 1

    # arena/* → <target>/* (so /arena/ → <target>/index.html under the mount)
    _copy_tree(arena_pages, target)
    # shared assets + favicon at the bundle root (referenced as /arena/<x>)
    for entry in _SHARED:
        src = out_dir / entry
        if src.is_dir():
            _copy_tree(src, target / entry, drop_images=True)
        elif src.is_file():
            shutil.copy2(src, target / entry)
            files_copied += 1
            bytes_copied += src.stat().st_size

    if demo:
        # The fetch/EventSource shim + recorded fixtures (copied verbatim —
        # fixtures.json is data, not a raster image to drop).
        for entry in _DEMO_EXTRA:
            src = out_dir / entry
            if src.is_dir():
                _copy_tree(src, target / entry)
        # Stop GitHub Pages' Jekyll from stripping any ``_``-prefixed file
        # (e.g. the dead ``assets/_slug_*.css`` carried from the build).
        nojekyll = target / ".nojekyll"
        nojekyll.write_bytes(b"")
        files_copied += 1

    return BuildWebUIReport(
        dest=str(target),
        files_copied=files_copied,
        bytes_copied=bytes_copied,
        pages=pages,
    )
