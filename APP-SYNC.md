# APP-SYNC.md — Orionfold Arena → ainative.business (the PUBLISHER)

> Builder-authored handoff for the **app** distribution surface. Sibling to the
> content `SYNC-WORKFLOW.md` (which covers articles/fieldkit-docs), scoped only
> to **Orionfold Arena**. The destination repo (ainative.business) points at
> this file to know what to do with Arena's assets.
>
> Distribution pipeline: **this repo (BUILDER, on Spark) → ainative.business
> (PUBLISHER) → orionfold.com (MARKETER).** PyPI / HF / GitHub are the external
> artifact hosts the publisher and marketer link to.

## What Orionfold Arena is

A standalone, dark, local-first **operator cockpit** for the DGX Spark — chat
against the resident brain, side-by-side rubric-scored compare, a private
leaderboard, a cost/quality efficiency frontier, a models/notebooks/benches
browser, live telemetry, and a co-iteration Lab. It is built **on** fieldkit
(`harness`/`eval`/`notebook`/`publish`) and shipped **by** fieldkit.

## Split of responsibility (read this first)

- **The runnable app is distributed via PyPI** — `pip install fieldkit[arena]`
  → `fieldkit arena up` → the full cockpit at `http://127.0.0.1:7866/arena/`.
  The web UI is **baked into the fieldkit wheel** at
  `fieldkit/src/fieldkit/arena/_webui/` and served by the sidecar's
  `StaticFiles` mount. **This is NOT distributed via the content sync.**
- **ainative.business owns only Track 2** — the static **web preview** at
  `/arena/` + a nav entry + linking out to the pip install. Nothing dynamic.

## Track 2 deploy — the static web preview at `ainative.business/arena/`

1. **Take the prebuilt bundle, verbatim.** The builder produces a
   self-contained Astro build rooted at `base: '/arena'` (`ARENA_BUILD=1`); the
   exact same bundle that goes in the wheel serves the web preview. **Do NOT
   re-skin** with Mac's light-first editorial design system — Arena owns its own
   `<html>`/dark cockpit shell (`ArenaAppLayout.astro`, never `BaseLayout`).
   Deploy at the top-level `/arena/` segment (mirrors `/fieldkit/`).
2. **If Mac builds from source** instead of taking the bundle, the
   self-contained set is:
   - `src/pages/arena/**`
   - `src/layouts/ArenaAppLayout.astro`
   - `src/components/arena/**`
   - `src/lib/arena/**`
   - `src/data/arena-mirror/**` (the leak-proof mirror JSON)
   - `src/data/arena-changelog.json` (the Lab "built together" timeline)
   - `getCollection('artifacts')` / `('articles')` data (already synced)
   Build with `ARENA_BUILD=1 node node_modules/astro/astro.js build` (the
   `.bin/astro` symlink is flattened on the SMB checkout — never `npm run
   build`).

## Static-vs-live contract (load-bearing)

- **No sidecar, no API calls, no secrets on the public host.** Every live
  island (`TelemetryGauge`, `TelemetryRail`, `ChatLane`, `CompareDuel`,
  `LiveVsBaseline`, `LabNotes`) short-circuits via `isPublicMirrorHost()` /
  `resolveSidecarUrl()` in `src/lib/arena/sidecar.mjs` and renders its static
  data + an offline banner. Chat/compare/Lab-notes are inert on the preview.
- The **only dynamic surface is `src/data/arena-mirror/*.json`**, and it is
  leak-proof by construction: the M6 exporter uses a hardcoded allowlist
  (`fieldkit.arena.mirror.PUBLISHABLE_TABLES`); `chat_*` + `lab_notes` are never
  enumerated, and `compare_runs.prompt` / response content is never emitted. The
  regression test `fieldkit/tests/arena/test_mirror_does_not_leak.py` pins this.

## The one chrome coordination point

Add **Arena** to the Mac-owned global nav:
`Book · Field Notes · Artifacts · Fieldkit · **Arena** · Platform · GitHub`.

## Release signal

- Bundle is **version-pinned to fieldkit** (same version string).
- Before each ship: run `fieldkit arena mirror` to refresh
  `src/data/arena-mirror/*.json`, and `node scripts/gen_arena_changelog.mjs` to
  refresh the Lab timeline.
- Rebuild the bundle each cut (`fieldkit arena build`, baked by the
  `fieldkit-curator` release pre-step).

## Do-not

- Don't re-skin with the editorial light theme.
- Don't run or proxy the sidecar publicly.
- Don't expose `~/.fieldkit/arena.db`.

## Runnable-app pointer (for the preview's CTA)

```
pip install fieldkit[arena]
fieldkit arena up
```

Link the launch story (`/story/<arena-launch>/`) when it ships.
