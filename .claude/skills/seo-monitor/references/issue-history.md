# Issue History

Append-only log of every `<file>:<issue-id>` key surfaced in a `seo-monitor` snapshot. Drives the `stale` flag.

The columns are: snapshot date, issue key, class (`auto`/`console`), and status (`new`, `stale`, `manual-review-needed`). One row per (date, issue-key) pair.

Rows older than 6 months can be safely truncated — only the most recent occurrence per key matters for the stale-flag rule.

| Date | Issue key | Class | Status |
|------|-----------|-------|--------|
| _(empty — first run will populate)_ | | | |
