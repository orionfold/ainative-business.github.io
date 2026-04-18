# API Domain Mapping

Last updated: 2026-04-18

## Domain Inventory

| Domain | Route Files | Endpoints | Validator | Types | Page | Group |
|--------|-------------|-----------|-----------|-------|------|-------|
| tasks | 11 | 14 | task.ts | task-status.ts, task-assist-types.ts | tasks.mdx | Core |
| projects | 3 | 7 | project.ts | — | projects.mdx | Core |
| workflows | 10 | 14 | blueprint.ts | workflows/types.ts | workflows.mdx | Core |
| blueprints | 4 | 6 | blueprint.ts | — | blueprints.mdx | Core |
| schedules | 5 | 8 | — | — | schedules.mdx | Core |
| chat | 11 | 15 | — | chat/types.ts | chat.mdx | Intelligence |
| profiles | 14 | 19 | profile.ts | agents/profiles/types.ts | profiles.mdx | Intelligence |
| runtimes | 2 | 3 | — | agents/runtime/catalog.ts | runtimes.mdx | Intelligence |
| memory | 1 | 4 | — | — | memory.mdx | Intelligence |
| documents | 4 | 7 | — | — | documents.mdx | Content |
| tables | 17 | 30 | — | tables/types.ts | tables.mdx | Content |
| uploads | 3 | 4 | — | — | uploads.mdx | Content |
| views | 2 | 4 | — | — | views.mdx | Content |
| settings | 19 | 35 | settings.ts | — | settings.mdx | Platform |
| permissions | 2 | 6 | — | — | permissions.mdx | Platform |
| notifications | 5 | 6 | — | — | notifications.mdx | Platform |
| channels | 6 | 9 | — | — | channels.mdx | Platform |
| environment | 14 | 19 | — | — | environment.mdx | Platform |
| snapshots | 4 | 7 | — | — | snapshots.mdx | Platform |
| workspace | 4 | 4 | workspace.ts | — | workspace.mdx | Platform |
| instance | 5 | 5 | — | — | instance.mdx | Platform |
| logs | 1 | 1 | — | — | logs.mdx | Operations |
| handoffs | 2 | 4 | — | — | handoffs.mdx | Operations |
| data | 2 | 2 | — | — | data.mdx | Operations |
| context | 1 | 1 | — | — | context.mdx | Operations |
| command-palette | 1 | 1 | — | — | — | Operations |
| user-guide | 1 | 1 | — | — | — | Operations |
| book | 4 | 4 | — | — | — | Operations |
| diagnostics | 1 | 1 | — | — | — | Operations |
| onboarding | 1 | 1 | — | — | — | Operations |
| telemetry | 1 | 1 | — | — | — | Operations |

## Route File Locations

### Core
- `src/app/api/tasks/` — route.ts, [id]/route.ts, [id]/execute/route.ts, [id]/resume/route.ts, [id]/cancel/route.ts, [id]/respond/route.ts, [id]/output/route.ts, [id]/logs/route.ts, [id]/provenance/route.ts, [id]/siblings/route.ts, assist/route.ts
- `src/app/api/projects/` — route.ts, [id]/route.ts, [id]/documents/route.ts
- `src/app/api/workflows/` — route.ts, [id]/route.ts, [id]/execute/route.ts, [id]/status/route.ts, [id]/documents/route.ts, [id]/steps/[stepId]/retry/route.ts, [id]/debug/route.ts, [id]/resume/route.ts, from-assist/route.ts, optimize/route.ts
- `src/app/api/blueprints/` — route.ts, [id]/route.ts, [id]/instantiate/route.ts, import/route.ts
- `src/app/api/schedules/` — route.ts, [id]/route.ts, [id]/execute/route.ts, [id]/heartbeat-history/route.ts, parse/route.ts

### Intelligence
- `src/app/api/chat/` — conversations/route.ts, conversations/[id]/route.ts, conversations/[id]/messages/route.ts, conversations/[id]/respond/route.ts, conversations/[id]/skills/activate/route.ts, conversations/[id]/skills/deactivate/route.ts, models/route.ts, suggested-prompts/route.ts, entities/search/route.ts, export/route.ts, files/search/route.ts
- `src/app/api/profiles/` — route.ts, [id]/route.ts, [id]/test/route.ts, [id]/test-results/route.ts, [id]/test-single/route.ts, [id]/context/route.ts, assist/route.ts, import/route.ts, import-repo/route.ts, import-repo/scan/route.ts, import-repo/preview/route.ts, import-repo/confirm/route.ts, import-repo/check-updates/route.ts, import-repo/apply-updates/route.ts
- `src/app/api/runtimes/` — ollama/route.ts, suggest/route.ts
- `src/app/api/memory/` — route.ts

### Content
- `src/app/api/documents/` — route.ts, [id]/route.ts, [id]/file/route.ts, [id]/versions/route.ts
- `src/app/api/tables/` — route.ts, templates/route.ts, [id]/route.ts, [id]/rows/route.ts, [id]/rows/[rowId]/route.ts, [id]/rows/[rowId]/history/route.ts, [id]/columns/route.ts, [id]/charts/route.ts, [id]/charts/[chartId]/route.ts, [id]/triggers/route.ts, [id]/triggers/[triggerId]/route.ts, [id]/export/route.ts, [id]/import/route.ts, [id]/history/route.ts, [id]/enrich/route.ts, [id]/enrich/plan/route.ts, [id]/enrich/runs/route.ts
- `src/app/api/uploads/` — route.ts, [id]/route.ts, cleanup/route.ts
- `src/app/api/views/` — route.ts, [id]/route.ts

### Platform
- `src/app/api/settings/` — route.ts, openai/route.ts, openai/login/route.ts, openai/logout/route.ts, chat/route.ts, chat/pins/route.ts, chat/saved-searches/route.ts, test/route.ts, budgets/route.ts, providers/route.ts, routing/route.ts, learning/route.ts, author-default/route.ts, browser-tools/route.ts, pricing/route.ts, ollama/route.ts, web-search/route.ts, runtime/route.ts, environment/route.ts
- `src/app/api/permissions/` — route.ts, presets/route.ts
- `src/app/api/notifications/` — route.ts, [id]/route.ts, mark-all-read/route.ts, pending-approvals/route.ts, pending-approvals/stream/route.ts
- `src/app/api/channels/` — route.ts, [id]/route.ts, [id]/test/route.ts, inbound/slack/route.ts, inbound/telegram/route.ts, inbound/telegram/poll/route.ts
- `src/app/api/environment/` — scan/route.ts, rescan-if-stale/route.ts, artifacts/route.ts, artifacts/[id]/route.ts, checkpoints/route.ts, checkpoints/[id]/route.ts, templates/route.ts, templates/[id]/route.ts, sync/route.ts, sync/preview/route.ts, sync/history/route.ts, profiles/create/route.ts, profiles/suggest/route.ts, skills/route.ts
- `src/app/api/snapshots/` — route.ts, [id]/route.ts, [id]/restore/route.ts, settings/route.ts
- `src/app/api/workspace/` — discover/route.ts, context/route.ts, import/route.ts, fix-data-dir/route.ts
- `src/app/api/instance/` — config/route.ts, init/route.ts, upgrade/route.ts, upgrade/check/route.ts, upgrade/status/route.ts

### Operations
- `src/app/api/logs/` — stream/route.ts
- `src/app/api/handoffs/` — route.ts, [id]/route.ts
- `src/app/api/data/` — clear/route.ts, seed/route.ts
- `src/app/api/context/` — batch/route.ts
- `src/app/api/command-palette/` — recent/route.ts
- `src/app/api/user-guide/` — status/route.ts
- `src/app/api/book/` — bookmarks/route.ts, progress/route.ts, regenerate/route.ts, stage/route.ts
- `src/app/api/diagnostics/` — chat-streams/route.ts
- `src/app/api/onboarding/` — progress/route.ts
- `src/app/api/telemetry/` — route.ts (internal telemetry ingest)

## Validator Files

| File | Schemas | Used By |
|------|---------|---------|
| task.ts | createTaskSchema, updateTaskSchema | tasks |
| project.ts | createProjectSchema, updateProjectSchema | projects |
| blueprint.ts | createBlueprintSchema | blueprints, workflows |
| profile.ts | profileSchema | profiles |
| settings.ts | settingsSchema | settings |
| workspace.ts | workspaceImportSchema | workspace |

## Notes

- `command-palette`, `user-guide`, `book`, `diagnostics`, `onboarding`, and `telemetry` are internal-facing APIs with limited external utility. Not documented in public API docs.
- Settings has 19 sub-routes for different configuration domains. Documented as one page with grouped sections.
- The `chat/conversations/[id]/messages` endpoint uses SSE streaming for real-time responses.
- The `notifications/pending-approvals/stream` endpoint uses SSE for real-time approval notifications.
- The `logs/stream` endpoint uses SSE for real-time agent log streaming.
- Release 0.12.1 additions vs prior mapping: +1 `/api/tasks/assist`, +1 `/api/blueprints/import`, +2 schedules (execute, heartbeat-history), +2 chat endpoints (skills/activate, skills/deactivate), +4 profiles (import-repo/check-updates, import-repo/apply-updates, [id]/test-single, [id]/context methods), +1 runtimes/suggest, +2 memory PATCH/DELETE, +1 `/api/tables/[id]/enrich/runs`, +11 settings (chat/pins, chat/saved-searches, openai/login×3, openai/logout, web-search×2, environment×2, runtime×2), +1 permissions/presets DELETE, +3 channels (inbound slack, inbound telegram, telegram poll), +9 environment (artifacts×2, checkpoints×4, templates, sync, profiles/create, profiles/suggest, rescan-if-stale), +3 snapshots (settings GET/PUT, [id]/restore), +2 handoffs ([id]/route GET, PATCH).
