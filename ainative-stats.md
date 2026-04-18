# ainative Development Metrics

## [2026-03-02 22:00] Metrics Snapshot

| Category | Metric | Value |
|----------|--------|-------|
| LOC | Rust | 4,489 |
| LOC | TypeScript (production) | 6,960 |
| LOC | TypeScript (tests) | 4,836 |
| LOC | SQL / CSS / HTML | 511 |
| LOC | **Total** | **16,796** |
| Tests | Vitest (src) | 171 |
| Tests | Vitest (sidecar) | 194 |
| Tests | Playwright | 3 |
| Tests | Rust | 53 |
| Tests | **Total** | **421** |
| Git | Commits | 27 |
| Git | Hours elapsed | 33.5 |
| Git | Commits/hour | 0.81 |
| Git | LOC/hour | 501 |
| Intents | Completed | 10/37 |
| Infra | IPC commands | 31 |
| Infra | DB tables | 11 |
| Infra | UI components | 16 |

### Completed Intents
- 001-tauri-app-scaffold
- 002-shared-types-and-schemas
- 003-sqlite-database-layer
- 004-tauri-ipc-bridge
- 005-sidecar-process-manager
- 006-config-and-settings
- 007-model-registry-providers
- 008-multi-model-router
- 009-task-graph-data-model
- 012-agent-lifecycle-interface

### Trend (vs previous snapshot — Day 2 partial)
- ↑ +9,515 LOC (7,281 → 16,796)
- ↑ +304 tests (117 → 421)
- ↑ +8 commits (19 → 27)
- ↑ +5 intents completed (5 → 10)
- ↑ +9 IPC commands (22 → 31)
- ↑ +6 UI components (10 → 16)

### Notes
- LOC counted via `find + wc -l` (tokei not installed)
- Rust LOC includes inline `#[cfg(test)]` test modules
- TypeScript production = `src/` + `sidecar/src/` minus test files
- TypeScript tests = `src/test/` + `sidecar/src/__tests__/` + `e2e/`

---

## [2026-03-09 18:00] Metrics Snapshot — Next.js Rewrite

| Category | Metric | Value |
|----------|--------|-------|
| LOC | Production | 18,423 |
| LOC | Tests | 1,580 |
| LOC | **Total** | **20,003** |
| Tests | Vitest | 132 |
| Tests | **Total** | **132** |
| Git | Commits | 22 |
| Git | Days elapsed | 3 |
| Git | Commits/day | 7.2 |
| Git | LOC/day | 6,575 |
| Features | Completed | 21/30 |
| Infra | API routes | 32 |
| Infra | DB tables | 8 |
| Infra | UI components | 91 |
| Infra | Pages | 12 |
| Infra | Agent profiles | 12 |

### Per-Day Feature Velocity
- Day 1 (Mar 6): 0 features (initial commit/setup)
- Day 2 (Mar 8): 18 features shipped (MVP + polish + documents)
- Day 3 (Mar 9): 3 features shipped (agent intelligence + platform)

### Trend (vs previous snapshot — Tauri → Next.js rewrite)
- ↑ +3,207 LOC (16,796 → 20,003)
- ↓ -289 tests (421 → 132) — architecture rewrite, Rust/Playwright tests removed
- ↑ +11 features completed (10/37 → 21/30)
- ↑ +75 UI components (16 → 91)
- ↓ -3 DB tables (11 → 8) — simplified schema
- New: 32 API routes, 12 agent profiles, 12 pages

### Notes
- Complete rewrite from Tauri (Rust + TypeScript) to pure Next.js 16
- LOC/day velocity of 6,575 reflects AI-assisted development with Claude Code
- Feature count methodology changed: "intents" → "features" with new scope (30 total)

---

## [2026-03-18 19:00] Metrics Snapshot — Post-MVP Maturity

| Category | Metric | Value |
|----------|--------|-------|
| LOC | Production | 42,673 |
| LOC | Tests | 6,997 |
| LOC | **Total** | **49,670** |
| Tests | Vitest | 312 |
| Tests | **Total** | **312** |
| Git | Commits | 93 |
| Git | Hours elapsed | 282.9 |
| Git | Commits/hour | 0.33 |
| Git | LOC/hour | 175.6 |
| Features | Completed | 51/53 |
| Infra | API routes | 52 |
| Infra | DB tables | 10 |
| Infra | UI components | 149 |
| Infra | Pages | 29 |
| Infra | Agent files | 34 |

### Feature Status
- 51 completed, 1 in-progress (workflow-ux-overhaul), 1 deferred (npm-publish-readiness)
- 14 MVP features + 39 post-MVP features across 8 categories
- 6 workflow patterns, 11 product surfaces, 13+ agent profiles, 8 workflow blueprints
- Dual-runtime: Claude Agent SDK + OpenAI Codex App Server

### Trend (vs previous snapshot — 9 days of post-MVP development)
- ↑ +29,667 LOC (20,003 → 49,670)
- ↑ +180 tests (132 → 312)
- ↑ +71 commits (22 → 93)
- ↑ +30 features completed (21/30 → 51/53)
- ↑ +20 API routes (32 → 52)
- ↑ +2 DB tables (8 → 10)
- ↑ +58 UI components (91 → 149)
- ↑ +17 pages (12 → 29)

### Notes
- LOC counted via `find + wc -l` (tokei not installed)
- Production LOC = total TypeScript minus test files
- Post-MVP shipped: dual-runtime, cost governance, agent self-improvement, parallel/swarm/loop workflows, permission presets, E2E tests, playbook docs
- Feature scope expanded from 30 → 53 as post-MVP categories grew

---

## [2026-04-01 00:15] Metrics Snapshot — Vision Alignment & 5-Runtime

| Category | Metric | Value |
|----------|--------|-------|
| LOC | Production | 84,670 |
| LOC | Tests | 8,512 |
| LOC | **Total** | **93,182** |
| Tests | Vitest | 409 |
| Tests | **Total** | **409** |
| Git | Commits | 213 |
| Git | Hours elapsed | 603.9 |
| Git | Commits/hour | 0.35 |
| Git | LOC/hour | 154.3 |
| Features | Completed | 97/103 |
| Infra | API routes | 112 |
| Infra | DB tables | 27 |
| Infra | UI components | 244 |
| Infra | Pages | 34 |
| Infra | Agent profiles | 52 |

### Feature Status
- 97 completed, 3 in-progress, 1 deferred, 2 planned
- In-progress: dynamic-slash-commands, runtime-validation-hardening, profile-environment-sync
- Deferred: npm-publish-readiness
- Planned: direct-runtime-prompt-caching, direct-runtime-advanced-capabilities
- Feature scope expanded from 53 → 103 with 8 new initiative areas

### Key Milestones Since Last Snapshot (13 days)
- **5 AI runtimes**: Claude Agent SDK, Codex App Server, Anthropic Direct, OpenAI Direct, Ollama
- **Smart runtime router**: auto-selects best runtime per task
- **Chat system**: full conversation UI with multi-agent routing and Codex engine
- **Living Book**: 9-chapter "AI Native" book with markdown pipeline and self-updating chapters
- **Vision alignment**: heartbeat scheduler, episodic memory, multi-channel delivery (Slack/Telegram), bidirectional channel chat, agent async handoffs
- **21+ agent profiles**, 6 workflow patterns, browser automation (Chrome DevTools + Playwright)

### Trend (vs previous snapshot — 13 days of development)
- ↑ +43,512 LOC (49,670 → 93,182)
- ↑ +97 tests (312 → 409)
- ↑ +120 commits (93 → 213)
- ↑ +46 features completed (51/53 → 97/103)
- ↑ +60 API routes (52 → 112)
- ↑ +17 DB tables (10 → 27)
- ↑ +95 UI components (149 → 244)
- ↑ +5 pages (29 → 34)
- ↑ +18 agent profiles (34 → 52)

### Notes
- LOC counted via `find + wc -l` (tokei not installed)
- Production LOC = all .ts/.tsx in src/ minus test files
- Feature scope nearly doubled (53 → 103) with vision alignment initiatives
- 5-runtime architecture is the most significant platform evolution since the Next.js rewrite

## [2026-04-02 14:00] Metrics Snapshot

| Category | Metric | Value |
|----------|--------|-------|
| LOC | TypeScript (production) | 75,662 |
| LOC | TypeScript (tests) | 7,289 |
| LOC | **Total** | **98,189** |
| Tests | Vitest | 426 |
| Tests | **Total** | **426** |
| Git | Commits | 226 |
| Git | Hours elapsed | 639.2 |
| Git | Commits/hour | 0.35 |
| Git | LOC/hour | 153.6 |
| Features | Completed | 102/110 |
| Infra | API routes | 114 |
| Infra | DB tables | 30 |
| Infra | UI components | 244 |
| Infra | Pages | 34 |
| Infra | Agent profiles | 52 |
| Infra | Service modules | 20 |
| Infra | Workflow patterns | 25 |

### Feature Status
- 102 completed, 4 in-progress, 1 deferred, 3 planned
- In-progress: chat-settings-tool, dynamic-slash-commands, runtime-validation-hardening, profile-environment-sync
- Deferred: npm-publish-readiness
- Planned: workflow-document-pool, direct-runtime-prompt-caching, direct-runtime-advanced-capabilities
- Feature scope expanded from 103 → 110 with new chat tooling, runtime hardening, and document workflow features

### Trend (vs previous snapshot — 13 days of development)
- ↑ +5,007 LOC (93,182 → 98,189)
- ↑ +17 tests (409 → 426)
- ↑ +13 commits (213 → 226)
- ↑ +5 features completed (97/103 → 102/110)
- ↑ +2 API routes (112 → 114)
- ↑ +3 DB tables (27 → 30)
- → no change UI components (244)
- → no change pages (34)
- → no change agent profiles (52)
- ↑ +9 service modules (11 → 20)
- ↑ +19 workflow patterns (6 → 25)

### Notes
- LOC now counted via `tokei` (previously used `find + wc -l`)
- TypeScript is 85.0% of codebase (TS+TSX code / total code)
- Velocity stabilizing as project matures: 0.35 commits/hour sustained over 639 hours

---

## [2026-04-03 15:00] Metrics Snapshot

| Category | Metric | Value |
|----------|--------|-------|
| LOC | TypeScript (production) | 86,909 |
| LOC | TypeScript (tests) | 8,800 |
| LOC | **Total** | **110,915** |
| Tests | Vitest | 426 |
| Tests | **Total** | **426** |
| Git | Commits | 251 |
| Git | Hours elapsed | 667.5 |
| Git | Commits/hour | 0.38 |
| Git | LOC/hour | 166.2 |
| Features | Completed | 116/128 |
| Infra | API routes | 134 |
| Infra | DB tables | 44 |
| Infra | UI components | 265 |
| Infra | Pages | 37 |
| Infra | Agent profiles | 52 |
| Infra | Service modules | 26 |
| Infra | Workflow patterns | 25 |

### Feature Status
- 116 completed, 5 in-progress, 1 deferred, 6 planned
- In-progress: chat-settings-tool, database-snapshot-backup, dynamic-slash-commands, runtime-validation-hardening, profile-environment-sync
- Deferred: npm-publish-readiness
- Planned: workflow-document-pool, direct-runtime-prompt-caching, direct-runtime-advanced-capabilities, workflow-run-history, entity-relationship-detail-views, relationship-summary-cards
- Feature scope expanded from 110 → 128 with new entity/relationship views, backup, and workflow history features

### Trend (vs previous snapshot — 1 day of development)
- ↑ +12,726 LOC (98,189 → 110,915)
- → no change tests (426)
- ↑ +25 commits (226 → 251)
- ↑ +14 features completed (102/110 → 116/128)
- ↑ +20 API routes (114 → 134)
- ↑ +14 DB tables (30 → 44)
- ↑ +21 UI components (244 → 265)
- ↑ +3 pages (34 → 37)
- → no change agent profiles (52)
- ↑ +6 service modules (20 → 26)
- → no change workflow patterns (25)

### Notes
- LOC counted via `tokei` — TypeScript is 86.3% of codebase (TS+TSX code / total code)
- Massive single-day velocity: +12.7K LOC, +25 commits, +14 features in ~28 hours
- DB schema grew significantly (+14 tables) suggesting major data model expansion
- Commits/hour ticked up from 0.35 → 0.38, reflecting sustained acceleration

---

## [2026-04-07 12:30] Metrics Snapshot

| Category | Metric | Value |
|----------|--------|-------|
| LOC | TypeScript (production) | 94,127 |
| LOC | TypeScript (tests) | 9,322 |
| LOC | **Total** | **118,855** |
| Tests | Vitest | 487 |
| Tests | **Total** | **487** |
| Git | Commits | 294 |
| Git | Hours elapsed | 753.3 |
| Git | Commits/hour | 0.39 |
| Git | LOC/hour | 157.8 |
| Features | Completed | 137/149 |
| Infra | API routes | 149 |
| Infra | DB tables | 45 |
| Infra | UI components | 286 |
| Infra | Pages | 39 |
| Infra | Agent profiles | 52 |
| Infra | Service modules | 33 |
| Infra | Workflow patterns | 31 |

### Feature Status
- 137 completed, 5 in-progress, 1 deferred, 6 planned
- In-progress: chat-settings-tool, database-snapshot-backup, dynamic-slash-commands, runtime-validation-hardening, profile-environment-sync
- Deferred: npm-publish-readiness
- Planned: workflow-document-pool, direct-runtime-prompt-caching, direct-runtime-advanced-capabilities, workflow-run-history, entity-relationship-detail-views, relationship-summary-cards
- Feature scope expanded from 128 → 149 with new tables/structured-data, PLG monetization, and entity relationship initiatives

### Trend (vs previous snapshot — ~4 days of development)
- ↑ +7,940 LOC (110,915 → 118,855)
- ↑ +61 tests (426 → 487)
- ↑ +43 commits (251 → 294)
- ↑ +21 features completed (116/128 → 137/149)
- ↑ +15 API routes (134 → 149)
- ↑ +1 DB table (44 → 45)
- ↑ +21 UI components (265 → 286)
- ↑ +2 pages (37 → 39)
- → no change agent profiles (52)
- ↑ +7 service modules (26 → 33)
- ↑ +6 workflow patterns (25 → 31)

### Notes
- LOC counted via `tokei` — TypeScript is 87.0% of codebase (TS+TSX code / total code)
- Steady cadence: 0.39 commits/hour sustained over 753 hours (~31 days)
- Major scope additions: Tables/Structured Data (14 features) and PLG Monetization (17 features) — product is evolving from local-first OS to commercial PLG platform
- Test growth (+61) is the strongest in any snapshot, signaling a quality push alongside scope expansion

---

## [2026-04-12 14:30] Metrics Snapshot

| Category | Metric | Value |
|----------|--------|-------|
| LOC | TypeScript (production) | 109,233 |
| LOC | TypeScript (tests) | 14,821 |
| LOC | **Total** | **139,478** |
| Tests | Vitest | 1,005 |
| Tests | **Total** | **1,005** |
| Git | Commits | 410 |
| Git | Hours elapsed | 876.0 |
| Git | Commits/hour | 0.47 |
| Git | LOC/hour | 159.2 |
| Velocity | Calendar days | 36 |
| Velocity | Active dev days | 34 |
| Velocity | Commits/day (calendar) | 11.4 |
| Velocity | Commits/day (active) | 12.1 |
| Velocity | LOC/day (calendar) | 3,874 |
| Velocity | LOC/day (active) | 4,102 |
| Velocity | Features/day (calendar) | 4.25 |
| Velocity | Features/day (active) | 4.50 |
| Velocity | LOC/commit | 340 |
| Velocity | LOC/feature | 912 |
| Velocity | Tests/feature | 6.6 |
| Velocity | Hours/feature | 5.7 |
| Features | Completed | 153/198 |
| Infra | API routes | 173 |
| Infra | DB tables | 46 |
| Infra | UI components | 311 |
| Infra | Pages | 42 |
| Infra | Agent profiles | 56 |
| Infra | Service modules | 35 |
| Infra | Workflow patterns | 37 |
| Business | Workflow blueprints | 13 |
| Business | Built-in agent profiles | 21 |
| Business | Runtime providers | 6 |
| Business | Workflow patterns | 6 |
| Business | Channel integrations | 3 |
| Business | Permission presets | 4 |
| Business | Table templates | 76 |

### Feature Status
- 153 completed, 8 in-progress, 1 deferred, 36 planned
- In-progress: chat-settings-tool, database-snapshot-backup, dynamic-slash-commands, runtime-validation-hardening, profile-environment-sync, fix-exported-bundle-registration, fix-sidebar-reactive-update, fix-sidebar-accordion-behavior
- Deferred: npm-publish-readiness
- Planned: 36 features including app-builder suite (app-cli-tools, app-conflict-resolution, etc.), marketplace features, workflow-run-history, upgrade-detection/session, and more
- Feature scope expanded from 149 → 198 with major app-builder and marketplace initiatives

### Trend (vs previous snapshot — ~5 days of development)
- ↑ +20,623 LOC (118,855 → 139,478)
- ↑ +518 tests (487 → 1,005) — **tests more than doubled**
- ↑ +116 commits (294 → 410)
- ↑ +16 features completed (137/149 → 153/198)
- ↑ +24 API routes (149 → 173)
- ↑ +1 DB table (45 → 46)
- ↑ +25 UI components (286 → 311)
- ↑ +3 pages (39 → 42)
- ↑ +4 agent profiles (52 → 56)
- ↑ +2 service modules (33 → 35)
- ↑ +6 workflow patterns (31 → 37)
- Commits/hour: 0.39 → 0.47 (+20%)
- LOC/hour: 157.8 → 159.2

### Notes
- LOC counted via `tokei` — TypeScript is 88.9% of codebase (TS+TSX code / total code)
- Tests more than doubled (+518) — the largest test growth in any snapshot, indicating a major quality and reliability push
- Commits/hour jumped 20% (0.39 → 0.47), the highest velocity rate recorded
- Roadmap scope expanded by 49 features (149 → 198), driven by app-builder and marketplace vision
- 4 new agent profiles added, growing the built-in catalog to 56
- Hours/feature dropped to 5.7 (from ~5.5 implied last snapshot), sustaining remarkable efficiency

## [2026-04-13 10:10] Metrics Snapshot — Community Edition Pivot

| Category | Metric | Value |
|----------|--------|-------|
| LOC | TypeScript (production) | 97,735 |
| LOC | TypeScript (tests) | 14,787 |
| LOC | **Total** | **127,103** |
| Tests | Vitest | 810 |
| Tests | **Total** | **810** |
| Git | Commits | 432 |
| Git | Hours elapsed | 901.5 |
| Git | Commits/hour | 0.48 |
| Git | LOC/hour | 141 |
| Velocity | Calendar days | 37 |
| Velocity | Active dev days | 35 |
| Velocity | Commits/day (calendar) | 11.7 |
| Velocity | Commits/day (active) | 12.3 |
| Velocity | LOC/day (calendar) | 3,435 |
| Velocity | LOC/day (active) | 3,632 |
| Velocity | Features/day (calendar) | 4.0 |
| Velocity | Features/day (active) | 4.2 |
| Velocity | LOC/commit | 294 |
| Velocity | LOC/feature | 858 |
| Velocity | Tests/feature | 5.5 |
| Velocity | Hours/feature | 6.1 |
| Features | Completed | 148/198 |
| Infra | API routes | 151 |
| Infra | DB tables | 45 |
| Infra | UI components | 292 |
| Infra | Pages | 38 |
| Infra | Agent profiles | 56 |
| Business | Workflow blueprints | 13 |
| Business | Built-in agent profiles | 21 |
| Business | Runtime providers | 6 |
| Business | Workflow patterns | 6 |
| Business | Channel integrations | 3 |
| Business | Permission presets | 4 |
| Business | Table templates | 76 |

### Trend (vs 2026-04-12 — community edition pivot)
- ↓ -12,375 LOC (139,478 → 127,103) — marketplace, licensing, cloud sync code removed
- ↓ -195 tests (1,005 → 810) — marketplace/licensing tests removed
- ↓ -5 completed features (153 → 148) — app marketplace features rolled back
- ↓ -22 API routes (173 → 151) — licensing, marketplace, sync, telemetry routes removed
- ↓ -4 pages (42 → 38) — marketplace UI pages removed
- +22 commits (410 → 432)

### Notes
- Community edition pivot (v0.10.0): removed subscription tiers, Stripe billing, Supabase cloud, telemetry, marketplace
- LOC decreased because code was deliberately removed, not because work was lost
- All features now free and unlimited — no feature gating, no cloud dependency, zero telemetry
- Product is 100% local-first with Apache 2.0 open source license
