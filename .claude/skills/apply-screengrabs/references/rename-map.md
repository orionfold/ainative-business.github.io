# Screenshot Rename Map (Pre-Migration)

Pairs of pre-rebrand (website, current) → post-rebrand (product, canonical) filenames. This file is consumed by `apply-screengrabs` in migration mode. After the first successful migration the skill sets mode=incremental in `manifest-cache.md` and this file becomes informational only.

Dataset as of 2026-04-18 (against product manifest generated 2026-04-18T17:25:00Z, 67 screenshots, and website `public/screenshots/` containing 126 PNGs).

## Confirmed rename pairs (clear 1:1 mapping)

| Old (website) | New (product) | Notes |
|---|---|---|
| dashboard-list.png | tasks-list.png | `/dashboard` route renamed to `/tasks` |
| dashboard-below-fold.png | tasks-below-fold.png | same |
| dashboard-bulk-select.png | tasks-bulk-select.png | same |
| dashboard-card-edit.png | tasks-card-edit.png | same |
| dashboard-table.png | tasks-table.png | same |
| dashboard-create-form-empty.png | tasks-create-form-empty.png | same |
| dashboard-create-form-filled.png | tasks-create-form-filled.png | same |
| dashboard-create-form-ai-applied.png | tasks-create-form-ai-applied.png | same |
| dashboard-create-form-ai-assist.png | tasks-create-form-ai-assist.png | same |
| dashboard-create-form-ai-breakdown.png | tasks-create-form-ai-breakdown.png | same |
| dashboard-workflow-confirm.png | tasks-workflow-confirm.png | same |
| cost-usage-list.png | costs-list.png | `/cost-usage` renamed to `/costs` |
| chat-model-selector.png | chat-model-picker.png | component renamed `Selector` → `Picker` |

## Ambiguous — product has no direct counterpart (user decision required)

| Old (website) | Candidate new (product) | Reason for ambiguity | Suggested action |
|---|---|---|---|
| dashboard-detail.png | — | no product `tasks-detail.png` (detail view merged into card-edit) | delete |
| dashboard-filtered.png | — | filter UI changed | delete |
| dashboard-new-entity.png | — | "new entity" pattern dropped | delete |
| dashboard-sorted.png | — | sort UI changed | delete |
| dashboard-card-detail.png | tasks-card-edit.png (maybe) | could be the same thing renamed | user confirm |
| task-ai-assist.png | tasks-create-form-ai-assist.png (maybe) | older naming without `-form-` infix | user confirm |
| task-create-panel.png | tasks-create-form-empty.png (maybe) | older naming | user confirm |
| task-detail-panel.png | — | likely removed | delete |
| home-dashboard.png | home-list.png (maybe) | composite rename | user confirm |
| chat-create-tab.png | — | tab removed / merged into chat-list | delete |
| chat-quick-access.png | — | quick-access pattern removed | delete |
| cost-codex-claude-code.png | — | specific comparison screenshot no longer in product | delete |

## Content orphans (no known product counterpart, likely obsolete)

| Filename | Likely origin | Suggested action |
|---|---|---|
| kanban-board.png | pre-rebrand task board screenshot | delete if no references |
| trust-tier-popover.png | removed feature | delete |
| monitor-logs.png | legacy; product now has `monitor-list.png` | candidate rename to monitor-list.png — user confirm |
| playbook-list.png | "playbook" concept renamed to "blueprint" | delete; product has `workflows-blueprints.png` |
| project-detail.png | legacy singular; product has `projects-detail.png` | candidate rename — user confirm |
| inbox-fully-expanded.png | legacy; product has `inbox-expanded.png` | candidate rename — user confirm |
| inbox-notifications.png | duplicate of inbox-list | delete |
| inbox-permissions.png | removed screenshot | delete |
| journey-inbox-action.png | old journey illustration series (not in product manifest) | user decision |
| journey-project-tasks.png | same | user decision |
| journey-task-detail.png | same | user decision |
| settings-page.png | legacy; product has `settings-list.png` | candidate rename — user confirm |
| settings-permissions.png | removed screenshot | delete |
| settings-oauth-tested.png | removed flow | delete |
| settings-ollama-connected.png | legacy; product has `settings-ollama.png` | candidate rename — user confirm |
| settings-channels-telegram-form.png | removed sub-form | delete |
| settings-channels-webhook-form.png | removed sub-form | delete |
| document-detail-pdf.png | legacy; product has `documents-*` instead | user decision |
| document-upload-dialog.png | legacy | delete |
| documents-create-form-empty.png | legacy | delete (product doesn't document create form) |
| documents-create-form-filled.png | legacy | delete |
| documents-detail.png | legacy | delete |
| documents-new-entity.png | legacy | delete |
| documents-table.png | legacy | delete |
| documents-upload-form.png | legacy | delete |
| profiles-create-form-empty.png | legacy | delete |
| profiles-create-form-filled.png | legacy | delete |
| profiles-new-entity.png | legacy | delete |
| projects-create-form-empty.png | legacy | delete |
| projects-create-form-filled.png | legacy | delete |
| projects-new-entity.png | legacy | delete |
| schedules-new-entity.png | legacy | delete |
| schedules-edit-form.png | legacy | delete |
| tables-create-form-empty.png | legacy; product only has `tables-create-form-filled.png` | delete |
| workflow-create-dialog.png | legacy; product has `workflows-create-form-delay.png` | delete |
| workflow-detail.png | legacy singular; product has `workflows-detail.png` | candidate rename — user confirm |
| workflows-create-form-empty.png | legacy | delete |
| workflows-create-form-filled.png | legacy | delete |
| workflows-new-entity.png | legacy | delete |
| workflows-runs.png | removed; run history merged into workflows-detail | delete |
| workflows-templates.png | renamed to `workflows-blueprints.png` | rename to workflows-blueprints.png — user confirm |

## Book orphans (belong in public/book/images/, not public/screenshots/)

These were likely uploaded to the wrong directory during early book development. They should move to `public/book/images/` — but that directory is owned by `apply-book-update`, so this skill only flags them.

| Filename | Suggested action |
|---|---|
| book-chapter-header.png | flag for manual move or delete |
| book-chapter-nav.png | flag for manual move or delete |
| book-list.png | flag for manual move or delete (same-name exists in product screengrabs too — check) |
| book-reader.png | flag for manual move or delete |
| book-settings.png | flag for manual move or delete |
| book-toc.png | flag for manual move or delete |
| book-try-it-now.png | flag for manual move or delete |

**Note:** `book-list.png` exists both in `public/screenshots/` (likely legacy) AND in product's `/screengrabs/` (per manifest.json). The product version wins — the website copy should be updated from product, not flagged as orphan.
