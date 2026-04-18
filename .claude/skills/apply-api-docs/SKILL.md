---
name: apply-api-docs
description: >-
  Scan the ainative product API routes, validators, types, and database schema to generate or incrementally update the developer-facing API documentation subsite on the ainative.business marketing website. Use this skill whenever the user says "update api docs", "sync api docs", "refresh api reference", "generate api docs", "apply api docs", "update api reference", "sync api reference from product", "refresh developer docs", "update REST docs", "apply api changes", or any request to create, update, regenerate, or sync the API documentation pages from the product codebase. Also use when the user mentions "new endpoints", "api changed", or wants to document new product features from an API perspective.
---

# Apply API Docs Skill

Generates and incrementally updates the `/docs/api/` subsite on the ainative.business marketing website by reading API route handlers, Zod validators, TypeScript types, and database schema from the ainative product codebase.

## Source and Target

- **Product API Routes**: `/Users/manavsehgal/Developer/ainative/src/app/api/` (26 domain directories, 120+ route files)
- **Validators**: `/Users/manavsehgal/Developer/ainative/src/lib/validators/` (Zod schemas)
- **DB Schema**: `/Users/manavsehgal/Developer/ainative/src/lib/db/schema.ts` (table definitions)
- **Types**: `/Users/manavsehgal/Developer/ainative/src/lib/*/types.ts` (TypeScript interfaces)
- **Target**: `/Users/manavsehgal/Developer/ainative.business/src/pages/docs/api/` (MDX pages)
- **Reference manifest**: Read `references/api-domain-mapping.md` (co-located with this skill)

## Design System Requirements

All generated pages must follow the ainative.business design system:
- Layout: `ApiDocsLayout.astro` (wider 90ch content area, grouped sidebar)
- Components: `MethodBadge`, `EndpointCard`, `SchemaTable`, `ParamTable`, `CodeExample`, `StatusBadge` from `src/components/api/`
- Trailing slashes on all internal links (astro.config.mjs `trailingSlash: 'always'`)
- Light-first design (OKLCH color tokens adapt automatically)
- Code blocks are always dark (dark background + light syntax text) in both light and dark mode — forced via CSS overriding Shiki's dual themes. This provides high contrast and matches developer expectations from tools like Stripe, Vercel, and Tailwind docs. Inline `code` stays theme-aware (light bg in light mode)

## Code Sample Guidelines

Every API page must include rich, developer-friendly code samples. Bare curl commands and minimal fetch calls are not acceptable. Follow these rules:

### Quick Start Section (required on every page)
Add a **Quick Start** section after the intro paragraph and before the Base URL. This shows a complete, realistic integration flow (3-6 steps) that tells a story. Example: "create a task → queue it → execute → stream logs → get output." Each step should have a comment explaining what it does. Use a `<CodeExample ts={...} python={...} />` component (NOT a fenced code block) so the Quick Start gets TypeScript/Python tabs, copy button, and localStorage sync — consistent with all other code on the page.

### Code Examples in EndpointCards
The CodeExample component takes `ts` (TypeScript, required) and `python` (optional) props. Both tabs should be provided for every endpoint.

- **Add explanation text** before each `<CodeExample>` — a sentence saying what the code does and when you'd use it
- **TypeScript (`ts` prop)**: Use `async/await` with `fetch`, add type annotations on responses, use interfaces for response types where they add clarity. Include comments on non-obvious lines
- **Python (`python` prop)**: Use `import requests`, add type hints where natural, use f-strings for interpolation. Include comments
- **Realistic values** in both languages — proper UUIDs like "proj-8f3a-4b2c", real model names, timestamps
- Every endpoint that returns a non-trivial response should include a **response example** as a fenced `json` code block after the CodeExample

### Tab Behavior
- TypeScript is the default tab
- When a user clicks Python on any CodeExample, ALL other CodeExamples on the page switch to Python (and vice versa)
- The preference is saved to `localStorage` key `api-docs-lang` and restored on page load
- A copy button in the top-right of the tab bar copies the active tab's code to clipboard

### Response Examples
Add example JSON response blocks after these endpoint types:
- List endpoints — show an array with 1-2 items
- Create endpoints — show the created object with generated ID
- Get endpoints — show the full object with all fields populated
- Status/output endpoints — show realistic state data

### Realistic Values
Use values that help developers understand the data:
- UUIDs: `"task-9d4e-a1b2"`, `"proj-8f3a-4b2c"`, `"wf-7c1d-3e5f"`
- Timestamps: `"2026-04-03T10:30:00.000Z"`
- Model IDs: `"claude-sonnet-4-6-20250514"`, `"gpt-4o-mini"`
- Status fields: Use varied states to show the enum values in context
- Token counts and costs: Use realistic numbers (e.g., `totalTokens: 15650`, `costMicros: 48200`)

## Exemplar Pages

Before generating new pages, read these 3 exemplar pages to understand the exact format, component usage, and writing tone:

1. `src/pages/docs/api/tasks.mdx` — Richest domain: 13 endpoints, Zod schemas, status transitions, constants table
2. `src/pages/docs/api/projects.mdx` — Simple CRUD baseline: 7 endpoints with document bindings
3. `src/pages/docs/api/workflows.mdx` — Complex domain: 11 endpoints, 6 patterns, execution state docs

These set the quality bar. Match their structure, detail level, and developer-friendly tone.

## 10-Step Workflow

### Step 1: Inventory API Routes

List all route files in the product:

```bash
find /Users/manavsehgal/Developer/ainative/src/app/api -name "route.ts" | sort
```

For each route file, determine:
- HTTP methods exported (GET, POST, PATCH, PUT, DELETE)
- The full API path (from directory structure)
- Group by domain directory (first segment after `/api/`)

Present the inventory table to the user:

```
| Domain | Routes | Endpoints | Status |
|--------|--------|-----------|--------|
| tasks  | 10     | 13        | Existing |
| chat   | 6      | 9         | New |
| ...    | ...    | ...       | ... |
```

### Step 2: Extract Validators and Schemas

Read all validator files:

```bash
ls /Users/manavsehgal/Developer/ainative/src/lib/validators/
```

For each validator file:
- Extract all Zod schema definitions (field names, types, constraints like min/max/enum, defaults)
- Map each schema to the route(s) that import it (grep for the import)
- Note transform functions that modify the validated data

Also read relevant sections of the database schema:

```bash
# Read the schema file for table definitions
cat /Users/manavsehgal/Developer/ainative/src/lib/db/schema.ts
```

Extract column definitions, types, enums, and foreign key relationships for each domain's tables.

### Step 3: Extract Type Definitions

Search for types files referenced by route handlers:

```bash
find /Users/manavsehgal/Developer/ainative/src/lib -name "types.ts" | sort
```

Read each types file and extract:
- TypeScript interfaces and type aliases that define request/response shapes
- Enum values and union types
- Map these to the domains that use them

### Step 4: Read Existing API Docs (Incremental Check)

Read `references/api-domain-mapping.md` to load the last-known state.

List existing API doc pages:

```bash
ls src/pages/docs/api/
```

For each domain, compare:
- Route file count and endpoints (from Step 1) vs. manifest
- Validator schemas (from Step 2) vs. manifest
- Identify: **new domains** (no existing page), **changed domains** (different route/endpoint count), **unchanged** (skip)

### Step 5: User Confirmation Gate

Present a change summary and **wait for user approval**:

```
## API Docs Update Plan

| Domain | Action | Endpoints | Reason |
|--------|--------|-----------|--------|
| chat   | Create | 9         | New domain, no existing page |
| tables | Create | 12        | New domain, no existing page |
| tasks  | Skip   | 13        | Unchanged since last run |
| ...    | ...    | ...       | ... |

Domains to create: X
Domains to update: Y
Domains unchanged: Z

Proceed? [Wait for user confirmation]
```

### Step 6: Generate/Update Domain Pages

For each confirmed domain, generate an MDX file following this template structure:

```mdx
---
layout: ../../../layouts/ApiDocsLayout.astro
title: "{Domain} API"
description: "{One-line description of the domain}"
---

import EndpointCard from '../../../components/api/EndpointCard.astro'
import SchemaTable from '../../../components/api/SchemaTable.astro'
import ParamTable from '../../../components/api/ParamTable.astro'
import CodeExample from '../../../components/api/CodeExample.astro'

# {Domain} API

{2-3 sentence introduction explaining what this domain does and key concepts}

## Quick Start

<CodeExample ts={`// Complete TypeScript integration flow for this domain
// 3-6 steps, each with a comment explaining what it does`} python={`# Equivalent Python flow using requests library
# 3-6 steps with comments`} />

## Base URL

\`\`\`
/api/{domain}
\`\`\`

## Endpoints

### {Endpoint Name}

<EndpointCard method="{METHOD}" path="/api/{path}" description="{Brief description}">

{SchemaTable, ParamTable, CodeExample components as appropriate}

</EndpointCard>

{Repeat for each endpoint}

## {Additional sections: status tables, error formats, constants}
```

**Content generation rules:**
- Read each route handler to understand request/response shapes
- Use Zod schemas for request body field documentation (name, type, required, constraints)
- Derive response shapes from the handler's NextResponse.json() calls
- **Every endpoint** must have a CodeExample with both TypeScript (`ts`) and Python (`python`) props
- **Every CodeExample** must be preceded by a brief explanation sentence saying what the code does
- **Every non-trivial endpoint** (list, create, get, status) must have an example JSON response block
- TypeScript examples must use `fetch` with type annotations, `async/await`, interfaces for response types
- Python examples must use `import requests`, type hints, f-strings
- Use developer-friendly descriptions — polished but technical, not marketing copy
- Document special behaviors: fire-and-forget (202), SSE streaming, cascade deletes, atomic operations
- Organize endpoints in logical order: list, create, get, update, delete, then action endpoints
- For SSE endpoints, use `method="SSE"` on EndpointCard and show EventSource usage with onmessage/onerror

**Endpoint ordering within a page:**
1. List (GET collection)
2. Create (POST collection)
3. Get (GET item)
4. Update (PATCH/PUT item)
5. Delete (DELETE item)
6. Action endpoints (execute, cancel, resume, etc.)
7. Sub-resource endpoints (documents, steps, etc.)

### Step 7: Generate/Update Index Page

Update `src/pages/docs/api/index.astro`:
- Add new domains to the appropriate group (Core, Intelligence, Content, Platform, Operations)
- Update endpoint counts for changed domains
- Update descriptions based on the route analysis

Group assignments:
- **Core**: tasks, projects, workflows, blueprints, schedules
- **Intelligence**: chat, profiles, runtimes, memory
- **Content**: documents, tables, uploads, views
- **Platform**: settings, permissions, notifications, channels, environment, snapshots, workspace
- **Operations**: logs, handoffs, data, context

### Step 8: Update Navigation

Check that `src/components/ApiDocsSidebar.astro` nav groups include all generated pages:
- If a new domain was added, add it to the correct group
- If a domain was removed from the product, remove it from the sidebar
- Ensure all `href` values use trailing slashes

Check `src/components/Nav.astro` has the top-level "API" link (between Docs and GitHub, not inside the dropdown).
Check `src/components/DocsSidebar.astro` has the "API Reference" bridge link at the bottom of `navItems`.

### Step 9: Update Reference Manifest

Write the updated state to `references/api-domain-mapping.md`:

```markdown
# API Domain Mapping

Last updated: {YYYY-MM-DD}

## Domain Inventory

| Domain | Route Files | Endpoints | Validator | Types | Page |
|--------|-------------|-----------|-----------|-------|------|
| tasks  | 10          | 13        | task.ts   | —     | tasks.mdx |
| projects | 3         | 7         | project.ts | —    | projects.mdx |
| ...    | ...         | ...       | ...       | ...   | ... |

## Route File Checksums

{Per-domain list of route files with line counts for change detection}
```

This manifest enables the next run to quickly identify which domains changed.

### Step 10: Verify and Summarize

Run build verification:

```bash
npm run build 2>&1 | tail -5
```

Present the final summary:

```
## API Docs Update Summary

| Domain | Action | Endpoints | Files Scanned |
|--------|--------|-----------|--------------|
| chat   | Created | 9        | 6 route files |
| tables | Created | 12       | 8 route files |
| ...    | ...     | ...      | ... |

### Files Created/Modified
- src/pages/docs/api/*.mdx ({N} files)
- src/pages/docs/api/index.astro (updated counts)
- src/components/ApiDocsSidebar.astro (nav updated)

### Build Result
✓ {N} pages built successfully

### Next Run
Re-run this skill after the next product release to pick up new endpoints.
```

## Key Rules

- **Idempotent**: Safe to run multiple times — generates the same output for the same input
- **Non-destructive**: Never deletes pages for domains that still exist in the product
- **Incremental**: Compares current route inventory against manifest to skip unchanged domains
- **User confirmation**: Always wait for approval before generating or modifying files
- **Trailing slashes**: All internal links must end with `/` (GitHub Pages requirement)
- **Tone**: Developer-friendly, technical, polished — not raw code comments or marketing copy
- **Components**: Always use the API components (EndpointCard, SchemaTable, etc.) — never raw HTML tables
- **Exemplar quality**: Generated pages must match the detail level of tasks.mdx — Quick Start, explained code, response examples
- **No bare code**: Every CodeExample must be preceded by an explanation sentence. No unexplained code snippets
- **TypeScript + Python**: All CodeExamples use `ts` and `python` props. TypeScript is default tab. User preference persists via localStorage
- **Always-dark code blocks**: Code blocks use a uniform dark background with contrasting syntax colors in both themes (Shiki dark forced via CSS, per-line/span backgrounds set to transparent). No light code blocks, no per-line highlight stripes — clean flat dark surface with syntax coloring only
- **Realistic values**: Use proper UUIDs, timestamps, model names in all examples — never "abc-123" or placeholder text
- **MDX escaping**: Inside CodeExample prop strings (backtick-delimited), escape `${...}` as `\${...}` in TypeScript template literals. For Python f-strings, avoid `${}` patterns (MDX parses `${` as JSX expression) — use simpler string concatenation instead of `f"${var:.2f}"`. Also avoid complex f-string format specs like `:.2f` inside nested braces
- **Navigation**: "API" appears as a top-level nav item (not inside Docs dropdown). DocsSidebar has an "API Reference" bridge link at the bottom. ApiDocsSidebar has a "Product Docs" bridge link back
- **Shiki config**: `astro.config.mjs` uses dual themes `{ light: 'github-light', dark: 'github-dark' }` for markdown fenced blocks. The `<Code>` component inside CodeExample uses single `theme="github-dark"` — these are different and intentional (see global.css for the CSS that coordinates them)
