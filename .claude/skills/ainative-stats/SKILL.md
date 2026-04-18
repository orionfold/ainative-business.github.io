---
name: ainative-stats
description: Collect development metrics (LOC, tests, commits, features, infrastructure, velocity, business functionality) from the ainative project and write a timestamped report to ainative-stats.md and stats/YYYY-MM-DD-HHMM.md. Then update all stat locations across the marketing website. Use when the user asks to check project stats, update metrics, or track development velocity.
---

This skill collects comprehensive development metrics from the ainative project and writes them to `ainative-stats.md` as a timestamped entry and saves each snapshot to an individual file in `stats/`. Each run appends a new entry, building a time-series of project velocity with per-day and per-feature efficiency ratios. It then propagates the collected stats to all locations across the marketing website.

## Target Project

The ainative codebase lives at `/Users/manavsehgal/Developer/ainative/`. All metric collection commands run against that directory. The report file `ainative-stats.md` is written to the current working directory.

## Architecture

ainative is a pure **Next.js 16 + React 19** web application with local SQLite storage via Drizzle ORM. AI integration uses the **Claude Agent SDK** v0.2.71. There is no Rust, Tauri, or native desktop component.

## Collection Steps

### 1. Verify Tools

Check availability of these tools before proceeding:
- `tokei` — fast LOC counter (install: `brew install tokei`)
- `git` — version control

If `tokei` is missing, fall back to `find + wc -l` for LOC counting. Note any missing tools in the report.

### 2. Collect LOC

Run `tokei` on the ainative project root:
```bash
tokei /Users/manavsehgal/Developer/ainative/ --sort code -t=TypeScript,TSX,CSS,JSON
```

If `tokei` is unavailable, use:
```bash
find /Users/manavsehgal/Developer/ainative/src -name '*.ts' -o -name '*.tsx' | xargs wc -l
```

Record: TypeScript production LOC, TypeScript test LOC, total LOC.

### 3. Count Tests

Count test functions (Vitest only — no Playwright or Rust tests):
```bash
grep -r "it(\|test(" /Users/manavsehgal/Developer/ainative/src --include="*.test.ts" --include="*.test.tsx" --include="*.spec.ts" | wc -l
```

Record: Vitest count, total.

### 4. Git Velocity

```bash
cd /Users/manavsehgal/Developer/ainative/
git rev-list --count HEAD
git log --oneline --since="$(git log --reverse --format='%aI' | head -1)" | wc -l
git log --reverse --format='%aI' | head -1  # first commit timestamp
git log -1 --format='%aI'                   # latest commit timestamp
git log --format='%ad' --date=short | sort -u | wc -l  # active development days
```

Compute:
- Total commits
- Hours elapsed (latest - first commit)
- Commits per hour (commits / hours)
- LOC per hour (total LOC / hours)
- Calendar days elapsed (date diff between first and latest commit, in days)
- Active development days (unique dates with at least 1 commit)
- Commits per calendar day (commits / calendar days)
- Commits per active day (commits / active days)
- LOC per calendar day (total LOC / calendar days)
- LOC per active day (total LOC / active days)
- Features per calendar day (completed features / calendar days) — uses feature count from step 5
- Features per active day (completed features / active days) — uses feature count from step 5
- LOC per commit (total LOC / commits)
- LOC per feature (total LOC / completed features)
- Tests per feature (total tests / completed features) — uses test count from step 3
- Hours per feature (hours elapsed / completed features)

### 5. Feature Status

```bash
# Count features from roadmap
cat /Users/manavsehgal/Developer/ainative/features/roadmap.md
```

Count completed vs total features from the roadmap file. List completed feature names.

### 6. Infrastructure Counts

```bash
# API routes
find /Users/manavsehgal/Developer/ainative/src/app/api -name "route.ts" 2>/dev/null | wc -l

# Database tables
grep -c "export const" /Users/manavsehgal/Developer/ainative/src/db/schema.ts 2>/dev/null || echo 0

# React components
find /Users/manavsehgal/Developer/ainative/src/components -name "*.tsx" 2>/dev/null | wc -l

# Pages (operator surfaces)
find /Users/manavsehgal/Developer/ainative/src/app -name "page.tsx" 2>/dev/null | wc -l

# Agent profiles
find /Users/manavsehgal/Developer/ainative/src -path "*/agents/*" -name "*.ts" 2>/dev/null | wc -l

# Service modules
find /Users/manavsehgal/Developer/ainative/src/services -maxdepth 1 -name "*.ts" 2>/dev/null | wc -l

# Workflow patterns
find /Users/manavsehgal/Developer/ainative/src -path "*/workflows/*" -name "*.ts" 2>/dev/null | wc -l
```

### 7. Quality Indicators

Note TypeScript strict mode and ESLint config status if available.

### 7b. Business Functionality

Count the pre-built business primitives that ship with the product — these represent out-of-the-box value, not just code infrastructure.

```bash
cd /Users/manavsehgal/Developer/ainative/

# Workflow blueprints (YAML files in builtins)
find src/lib/workflows/blueprints/builtins -name "*.yaml" 2>/dev/null | wc -l

# Built-in agent profiles (directories in builtins)
find src/lib/agents/profiles/builtins -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l

# Runtime providers (entries in catalog)
grep -c "id:" src/lib/agents/runtime/catalog.ts 2>/dev/null || echo 0

# Workflow execution patterns
grep -c "'" src/lib/workflows/types.ts 2>/dev/null | head -1
# Better: manually count from the WorkflowPattern union type (sequence, planner-executor, checkpoint, loop, parallel, swarm)

# Channel integrations (adapter files)
find src/lib/channels -name "*-adapter.ts" 2>/dev/null | wc -l

# Permission presets
grep -c "id:" src/lib/settings/permission-presets.ts 2>/dev/null || echo 0

# Table templates (pre-built structured data templates)
grep -c "name:" src/lib/data/seed-data/table-templates.ts 2>/dev/null || echo 0

# Column data types (from constants)
grep -c "'" src/lib/constants/table-status.ts 2>/dev/null | head -1
# Better: count entries in the ColumnType enum/union (text, number, date, boolean, select, url, email, relation, computed)

# Notification types
grep "permission_required\|task_completed\|task_failed\|agent_message\|budget_alert\|context_proposal\|tier_limit" src/lib/db/schema.ts | head -1
# Better: count distinct notification type values from the schema enum

# Activity/metering types (from usageLedger schema)
grep "task_run\|task_resume\|workflow_step\|scheduled_firing\|task_assist\|profile_test\|pattern_extraction\|context_summarization\|chat_turn\|profile_assist\|manual_force_bypass" src/lib/db/schema.ts | head -1
# Better: count distinct activity type values from the schema enum

# Schedule types
grep -c "scheduled\|heartbeat" src/lib/db/schema.ts 2>/dev/null | head -1
# Count: scheduled, heartbeat

# Seed data generators (exported create* functions)
grep -c "export.*function\|export.*const.*create\|export.*const.*seed\|export.*const.*upsert" src/lib/data/seed-data/*.ts 2>/dev/null
```

Record these business functionality counts:

| Primitive | Description |
|-----------|-------------|
| Workflow blueprints | Pre-built YAML workflow templates (e.g., sprint-planning, content-marketing) |
| Agent profiles (built-in) | Ready-to-use specialist agent configurations |
| Runtime providers | AI execution backends (Claude, OpenAI, Ollama, etc.) |
| Workflow patterns | Execution models (sequence, parallel, swarm, loop, etc.) |
| Channel integrations | Bidirectional messaging adapters (Slack, Telegram, webhook) |
| Permission presets | Layered approval configurations (read-only, git-safe, full-auto) |
| Table templates | Pre-built structured data templates across business categories |
| Column data types | Available data types for user tables |
| Notification types | Distinct alert/event categories |
| Activity types | Usage metering classifications |
| Schedule types | Execution timing models (cron, heartbeat) |

### 8. Write Report

Read the existing `ainative-stats.md` file if it exists. Append a new timestamped entry in this format:

```markdown
## [YYYY-MM-DD HH:MM] Metrics Snapshot

| Category | Metric | Value |
|----------|--------|-------|
| LOC | TypeScript (production) | X,XXX |
| LOC | TypeScript (tests) | X,XXX |
| LOC | **Total** | **X,XXX** |
| Tests | Vitest | XXX |
| Tests | **Total** | **XXX** |
| Git | Commits | XX |
| Git | Hours elapsed | XX.X |
| Git | Commits/hour | X.X |
| Git | LOC/hour | XXX |
| Velocity | Calendar days | XX |
| Velocity | Active dev days | XX |
| Velocity | Commits/day (calendar) | X.X |
| Velocity | Commits/day (active) | X.X |
| Velocity | LOC/day (calendar) | X,XXX |
| Velocity | LOC/day (active) | X,XXX |
| Velocity | Features/day (calendar) | X.X |
| Velocity | Features/day (active) | X.X |
| Velocity | LOC/commit | XXX |
| Velocity | LOC/feature | XXX |
| Velocity | Tests/feature | X.X |
| Velocity | Hours/feature | X.X |
| Features | Completed | XX/XX |
| Infra | API routes | XX |
| Infra | DB tables | XX |
| Infra | UI components | XX |
| Infra | Pages | XX |
| Infra | Agent profiles | XX |
| Business | Workflow blueprints | XX |
| Business | Built-in agent profiles | XX |
| Business | Runtime providers | X |
| Business | Workflow patterns | X |
| Business | Channel integrations | X |
| Business | Permission presets | X |
| Business | Table templates | XX |
| Business | Column data types | X |
| Business | Notification types | X |
| Business | Activity types | XX |
| Business | Schedule types | X |
```

### 9. Trend Comparison

If previous entries exist in `ainative-stats.md`, compute and display deltas:
- LOC: +X,XXX since last snapshot
- Tests: +XX since last snapshot
- Commits: +XX since last snapshot
- Commits/day (active): X.X → X.X
- Features/day (active): X.X → X.X
- LOC/commit: XXX → XXX
- Hours/feature: X.X → X.X

Format deltas with arrows: `↑ +1,234 LOC` or `→ no change`. For rate metrics, show the previous → current value.

### 10. Save Snapshot to `stats/`

After writing the snapshot to `ainative-stats.md`, also save it as an individual timestamped file in the `stats/` directory within this project:

```bash
mkdir -p stats/
```

Write the full snapshot content (metrics table, velocity section, trend comparison, feature status, and notes) to:

```
stats/YYYY-MM-DD-HHMM.md
```

Example: `stats/2026-04-12-1430.md`

This creates a per-snapshot archive for easy git diffing, individual review, and programmatic consumption. Include the saved file path in the final output summary.

## Updating the Website

After collecting stats, update ALL stat locations across the marketing website so they stay in sync. The sections below list every file and the specific values to update.

### Deriving Website Stats from Collected Metrics

Use this mapping to translate collected metrics into website values:

| Website Stat | Source |
|-------------|--------|
| Features Shipped | `Features | Completed` — the shipped count (numerator only) |
| Operator Surfaces | `Infra | Pages` count from step 6 |
| AI Runtimes | Count from product's runtime config (typically stable at 5) |
| Agent Profiles | `Infra | Agent profiles` count from step 6 |
| Workflow Patterns | Workflow patterns count from step 6 |
| LOC (ainative) | `LOC | Total` from step 2, formatted as `XXK` |
| Tests | `Tests | Total` from step 3 |
| API Endpoints | `Infra | API routes` from step 6 |
| DB Tables | `Infra | DB tables` from step 6 |
| Service Modules | Service modules count from step 6 |
| TypeScript % | From `tokei` output, compute TS LOC / Total LOC |
| Business-function profiles | Manually count profiles tagged as business-function in the product |

### Update Target 1: Proof Section (Homepage)

**File:** `src/components/sections/Proof.astro` (lines 5-11)

Update the `metrics` array with current values:
```javascript
const metrics = [
  { value: '<FEATURES_SHIPPED>', label: 'Features Shipped' },
  { value: '<OPERATOR_SURFACES>', label: 'Operator Surfaces' },
  { value: '<AI_RUNTIMES>', label: 'AI Runtimes' },
  { value: '<AGENT_PROFILES>+', label: 'Agent Profiles' },
  { value: '<WORKFLOW_PATTERNS>', label: 'Workflow Patterns' },
];
```

### Update Target 2: Projects Page Metrics Bar

**File:** `src/data/timeline.ts` (lines 23-29)

Update the top-level `metrics` array:
```typescript
export const metrics = [
  { label: 'Lines of Code', target: <PORTFOLIO_LOC_K>, suffix: 'K+' },
  { label: 'AI Agents', target: <PORTFOLIO_AGENTS>, suffix: '+' },
  { label: 'Production Systems', target: <PRODUCTION_SYSTEMS>, suffix: '' },
  { label: 'Projects', target: <PROJECTS>, suffix: '+' },
  { label: 'Blog Articles', target: <BLOG_ARTICLES>, suffix: '+' },
];
```

Note: Portfolio-wide metrics (LOC, AI Agents, Projects, Blog Articles) include ALL projects, not just ainative. To update these, sum LOC across all project entries and count agents across the portfolio. `Production Systems` and `Projects` count the total number of shipped systems and projects respectively.

Also update the ainative project entry's `stats` field (search for the ainative entry near the bottom of the timeline array):
```
stats: '<LOC>K LOC · <TESTS> tests · <FEATURES_COMPLETED>/<FEATURES_TOTAL> features shipped'
```

### Update Target 3: Research Page — "What's Shipped Today" Table

**File:** `src/pages/research.mdx` (~lines 177-193)

Update these table rows with current values:
```markdown
| Capability | Status |
|-----------|--------|
| <FEATURES_TOTAL> features across <OPERATOR_SURFACES> operator surfaces | Shipped |
| <AGENT_PROFILES>+ specialist agent profiles (incl. <BIZ_PROFILES> business-function profiles) | Shipped |
| <WORKFLOW_PATTERNS> workflow patterns with blueprint catalog | Shipped |
| <AI_RUNTIMES> AI runtimes (Claude, OpenAI, Ollama, direct APIs) | Shipped |
```

Keep the remaining rows (Slack/Telegram, heartbeat, memory, etc.) unchanged unless the product has added new shipped capabilities.

### Update Target 4: Research Page — Architecture Section

**File:** `src/pages/research.mdx` (~lines 229-233)

Update the architecture bullets:
```markdown
- **Browser layer** — React 19 with <OPERATOR_SURFACES> operator surfaces, real-time SSE streaming
- **Server layer** — Next.js 16 with <SERVICE_MODULES> service modules, <API_ENDPOINTS> API endpoints
- **External layer** — Local SQLite database (WAL mode, <DB_TABLES>+ tables), no cloud dependency

Technology stack: TypeScript (<TS_PERCENT>% of codebase), Tailwind CSS v4, shadcn/ui, Drizzle ORM.
```

### Update Target 5: Architecture Glance SVG (Homepage)

**File:** `src/components/svg/ArchitectureGlance.astro`

This is a simplified 4-pillar architecture diagram on the homepage Proof section. Update text elements containing stats:
- Orchestrate pillar: `<AGENT_PROFILES>+ Agent Profiles` (search for `Agent Profiles`)
- Automate pillar: `<WORKFLOW_PATTERNS> Workflow Patterns` (search for `Workflow Patterns`)

### Update Target 6: System Architecture SVG (Research Page)

**File:** `src/components/svg/SystemArchitecture.astro`

This is the detailed 4-column × 3-row architecture diagram in the research page. Update text elements containing stats:
- Row label: `<OPERATOR_SURFACES> screens` (search for `screens`)
- Row label: `<API_ENDPOINTS> APIs` (search for `APIs`)
- Orchestrate surfaces cell: `Profiles (<AGENT_PROFILES>+)` (search for `Profiles (`)
- Automate infra cell: `SQLite (<DB_TABLES>+ tables)` (search for `SQLite (`)

### Update Target 7: Detailed Architecture SVG (Research Page)

**File:** `src/components/svg/DetailedArchitecture.astro`

This is the 3-layer detailed architecture diagram. Update text elements containing stats:
- Browser subtitle: `<OPERATOR_SURFACES> operator-facing surfaces across 3 workspace categories`
- Workflow Engine card: `<WORKFLOW_PATTERNS> orchestration patterns` (search for `orchestration patterns`)
- Server subtitle: `<SERVICE_MODULES> service modules` (search for `service modules`)
- External storage: `SQLite DB (<DB_TABLES>+ tables)` (search for `SQLite DB (`)

### Update Target 8: Homepage FAQ (JSON-LD Structured Data)

**File:** `src/pages/index.astro` (~lines 60-80)

Update the stat references in FAQ answers:
- "supports **<AI_RUNTIMES> AI runtimes**, **<AGENT_PROFILES>+ specialist agent profiles**, **<WORKFLOW_PATTERNS> workflow patterns**"

### Update Target 9: ainative Timeline Entry

**File:** `src/data/timeline.ts` (ainative entry near bottom of timeline array)

Update these fields:
- `stats` — LOC count, test count, features shipped ratio
- `achievements` — notable milestones if any new ones
- `description` — if scope has meaningfully changed

### Update Target 10: Standalone Architecture SVG (Product README)

**File:** `/Users/manavsehgal/Developer/ainative/public/readme/architecture.svg`

This is a self-contained SVG (900x520 viewBox) referenced by the product's README.md on GitHub. It mirrors the 3-layer architecture from Target 7 (Browser → Server → External) but uses hardcoded hex colors instead of CSS custom properties. After updating stats in the website SVGs, update this file with the **same stat values** and ensure it uses the **light theme** color scheme so it renders cleanly on GitHub's white background.

**Stats to update:**
- DB tables: search for text containing `tables · Self-healing bootstrap` — replace the table count with `<DB_TABLES>` (e.g., `<DB_TABLES> tables · Self-healing bootstrap`)
- Agent profiles: search for text containing `agent profiles` — replace the profile count with `<AGENT_PROFILES>` (e.g., `<AGENT_PROFILES> agent profiles`)
- Route pills (Browser layer): verify the listed route pills match current operator surfaces from step 6. Add or remove `<rect>`/`<text>` pairs as needed, adjusting x-positions to fit within the 820px row.

**Light theme color scheme — apply these hex replacements throughout the file:**

| Dark Hex | Role | Light Hex |
|----------|------|-----------|
| `#0F172A` | Background / card fill | `#F0F1F5` |
| `#1E293B` | Card fill / gradient end | `#FCFCFD` |
| `#334155` | Card stroke / border | `#D4D6DE` |
| `#F8FAFC`, `#F1F5F9` | Bright text (on dark bg) | `#2D3250` |
| `#94A3B8` | Title / subtitle text | `#656A80` |
| `#64748B` | Description text | `#7B8099` |
| `#475569` | Dim labels / footer | `#7B8099` |
| `#60A5FA` | Route pill text | `#2563EB` |
| `#22D3EE` | Teal accent / connectors | `#0D7D8C` |
| `#7C3AED` | Purple accent | `#7233B8` |
| `#F59E0B` | Orange accent bar | `#A66D0A` |
| `#10B981` | Green accent bar | `#0D7D5A` |
| `#EC4899` | Pink accent bar | `#B83D75` |
| `#EF4444` | Red accent bar | `#C23030` |
| `#06B6D4` | Cyan accent bar | `#0D7D8C` |
| `#D97706` | Anthropic icon | `#A66D0A` |
| `#10A37F` | OpenAI icon | `#0D7D5A` |
| `#000` (shadow filter) | Drop shadow | `#475569` at `flood-opacity="0.1"` |

**Gradient updates:**
- `bgGrad`: both stops → `#F0F1F5` (flat light background)
- `browserGrad`: `#2563EB` → `#0D7D8C`
- `serverGrad`: `#FCFCFD` → `#F0F1F5`
- `externalGrad`: `#7233B8` → `#A78BFA`

**Footer text:** update `fill` to `#656A80`.

Light hex values are derived from the website's OKLCH light-theme tokens in `src/styles/global.css` (lines 70-92).

## Post-Update Verification

### Build Check
```bash
cd /path/to/ainative.business && npm run build
```

Verify the build completes without errors.

### Consistency Check

After updating all locations, grep for the OLD values to catch any stragglers:
```bash
grep -rn '<OLD_FEATURES_COUNT>\|<OLD_SURFACES_COUNT>\|<OLD_AGENT_COUNT>' src/
```

Report any remaining mismatches to the user.

## Output

After writing the report and updating the website, summarize:
1. Key metrics from the latest snapshot
2. Velocity dashboard highlights (commits/day, LOC/day, features/day, hours/feature)
3. Trend deltas vs previous snapshot (including velocity rate changes)
4. All website files that were updated
5. Build verification result
6. Any consistency issues found
7. Path to the saved snapshot file in `stats/`
