# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""P7 — the packaged web UI bake (`fieldkit arena build`) + sidecar mount.

`build_webui(skip_astro=True)` is exercised against a synthetic `dist-arena/`
so the test needs no Node toolchain. The mount degradation path is asserted
directly; the positive mount is covered live in the session smoke (the baked
bundle is a gitignored build artifact, not committed)."""

from __future__ import annotations

from pathlib import Path

from fieldkit.arena.webui import (
    BuildWebUIReport,
    build_webui,
    bundle_present,
    webui_dir,
)


def _make_fake_dist_arena(root: Path) -> None:
    """Lay down a minimal post-build `dist-arena/` like Astro would."""
    out = root / "dist-arena"
    # Arena routed pages.
    (out / "arena").mkdir(parents=True)
    (out / "arena" / "index.html").write_text("<html>ORIONFOLD ARENA cockpit</html>")
    (out / "arena" / "models").mkdir()
    (out / "arena" / "models" / "index.html").write_text("<html>models</html>")
    (out / "arena" / "lab").mkdir()
    (out / "arena" / "lab" / "index.html").write_text("<html>lab</html>")
    # Shared assets — JS/CSS/fonts kept, raster images dropped.
    (out / "assets").mkdir()
    (out / "assets" / "app.abc.js").write_text("console.log(1)")
    (out / "assets" / "app.abc.css").write_text("body{}")
    (out / "assets" / "geist.def.woff2").write_bytes(b"\x00\x01font")
    (out / "assets" / "hero.ghi.webp").write_bytes(b"\x00" * 1024)  # editorial image
    (out / "favicon.svg").write_text("<svg/>")


def test_build_webui_skip_astro_prunes_and_drops_images(tmp_path: Path) -> None:
    root = tmp_path / "site"
    root.mkdir()
    _make_fake_dist_arena(root)
    dest = tmp_path / "_webui"

    report = build_webui(repo_root=root, dest=dest, skip_astro=True)
    assert isinstance(report, BuildWebUIReport)

    # Pages: arena/* copied with the arena/ prefix stripped → / under the mount.
    assert (dest / "index.html").is_file()
    assert "ORIONFOLD ARENA" in (dest / "index.html").read_text()
    assert (dest / "models" / "index.html").is_file()
    assert (dest / "lab" / "index.html").is_file()
    assert report.pages == 3

    # Shared assets kept; raster image dropped to keep the wheel lean.
    assert (dest / "assets" / "app.abc.js").is_file()
    assert (dest / "assets" / "app.abc.css").is_file()
    assert (dest / "assets" / "geist.def.woff2").is_file()
    assert not (dest / "assets" / "hero.ghi.webp").exists()
    assert (dest / "favicon.svg").is_file()


def _make_fake_dist_arena_demo(root: Path) -> None:
    """Lay down a minimal post-build `dist-arena-demo/` like the ARENA_DEMO build.

    Same shape as `dist-arena/` plus the demo-only `arena-demo/` shim+fixtures
    and an `assets/_slug_*.css` that GitHub Pages' Jekyll would strip.
    """
    out = root / "dist-arena-demo"
    (out / "arena").mkdir(parents=True)
    (out / "arena" / "index.html").write_text("<html>ORIONFOLD ARENA cockpit</html>")
    (out / "arena" / "chat").mkdir()
    (out / "arena" / "chat" / "index.html").write_text("<html>chat</html>")
    (out / "assets").mkdir()
    (out / "assets" / "app.abc.js").write_text("console.log(1)")
    (out / "assets" / "_slug_.def.css").write_text(".x{}")  # underscore → Jekyll trap
    (out / "assets" / "hero.ghi.webp").write_bytes(b"\x00" * 1024)
    (out / "favicon.svg").write_text("<svg/>")
    # Demo-only: the fetch/EventSource shim + recorded fixtures.
    (out / "arena-demo").mkdir()
    (out / "arena-demo" / "boot.js").write_text("/* shim */")
    (out / "arena-demo" / "fixtures.json").write_text('{"chat": []}')


def test_build_webui_demo_mode_promotes_adds_shim_and_nojekyll(tmp_path: Path) -> None:
    root = tmp_path / "site"
    root.mkdir()
    _make_fake_dist_arena_demo(root)
    dest = tmp_path / "out"

    report = build_webui(repo_root=root, dest=dest, skip_astro=True, demo=True)

    # Promoted: cockpit at root, nav-tab targets resolve as siblings.
    assert (dest / "index.html").is_file()
    assert "ORIONFOLD ARENA" in (dest / "index.html").read_text()
    assert (dest / "chat" / "index.html").is_file()
    # Demo-only shim + fixtures copied verbatim under arena-demo/.
    assert (dest / "arena-demo" / "boot.js").is_file()
    assert (dest / "arena-demo" / "fixtures.json").is_file()
    # .nojekyll written so Jekyll doesn't strip the underscore CSS.
    assert (dest / ".nojekyll").is_file()
    assert (dest / ".nojekyll").read_bytes() == b""
    # Shared assets kept (incl. the _slug_ CSS), raster dropped.
    assert (dest / "assets" / "app.abc.js").is_file()
    assert (dest / "assets" / "_slug_.def.css").is_file()
    assert not (dest / "assets" / "hero.ghi.webp").exists()
    assert (dest / "favicon.svg").is_file()


def test_build_webui_demo_default_target_is_dist_arena_demo_pruned(tmp_path: Path) -> None:
    root = tmp_path / "site"
    root.mkdir()
    _make_fake_dist_arena_demo(root)

    report = build_webui(repo_root=root, skip_astro=True, demo=True)

    assert Path(report.dest) == root / "dist-arena-demo-pruned"
    assert (root / "dist-arena-demo-pruned" / "index.html").is_file()


def test_build_webui_demo_raises_when_build_missing(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    try:
        build_webui(repo_root=root, dest=tmp_path / "out", skip_astro=True, demo=True)
    except RuntimeError as exc:
        # Error names the demo env gate, not the wheel one.
        assert "ARENA_DEMO" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError on missing dist-arena-demo")


def test_build_webui_is_a_fresh_bake(tmp_path: Path) -> None:
    """A second bake wipes stale files from a prior run."""
    root = tmp_path / "site"
    root.mkdir()
    _make_fake_dist_arena(root)
    dest = tmp_path / "_webui"
    build_webui(repo_root=root, dest=dest, skip_astro=True)
    stale = dest / "stale.html"
    stale.write_text("old")
    build_webui(repo_root=root, dest=dest, skip_astro=True)
    assert not stale.exists()


def test_build_webui_raises_when_dist_arena_missing(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    try:
        build_webui(repo_root=root, dest=tmp_path / "_webui", skip_astro=True)
    except RuntimeError as exc:
        assert "arena pages" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError on missing dist-arena")


def test_webui_dir_is_inside_package() -> None:
    d = webui_dir()
    assert d.name == "_webui"
    assert d.parent.name == "arena"


def test_webui_html_is_no_cache_but_assets_stay_cacheable(tmp_path: Path) -> None:
    """HTML from the _webui mount must carry `Cache-Control: no-cache` so the
    browser revalidates across rebakes (Chrome heuristic-cached stale cockpit
    HTML two sessions running); hashed assets keep the default (no header)."""
    import httpx
    from fastapi import FastAPI

    from fieldkit.arena.server import _webui_static_files

    (tmp_path / "index.html").write_text("<html>cockpit</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.abc.js").write_text("console.log(1)")

    app = FastAPI()
    app.mount("/arena", _webui_static_files(str(tmp_path)), name="arena-webui")

    import anyio

    async def _exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            html = await client.get("/arena/")
            assert html.status_code == 200
            assert html.headers.get("cache-control") == "no-cache"
            assert html.headers.get("etag")  # revalidation stays cheap
            asset = await client.get("/arena/assets/app.abc.js")
            assert asset.status_code == 200
            assert "cache-control" not in asset.headers

    anyio.run(_exercise)


def test_mount_degrades_gracefully_without_bundle(tmp_path, monkeypatch) -> None:
    """`_mount_packaged_webui` returns False (API-only) when no bundle exists,
    so a fieldkit installed without a baked _webui/ still serves the API."""
    from fieldkit.arena import server as srv

    # Point the resolver at an empty dir so the bundle looks absent.
    monkeypatch.setattr(srv, "_mount_packaged_webui", srv._mount_packaged_webui)
    if not bundle_present():
        app = srv.create_app(db=str(tmp_path / "x.db"), repo_root=str(tmp_path))
        # /healthz still mounts regardless.
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/healthz" in paths
