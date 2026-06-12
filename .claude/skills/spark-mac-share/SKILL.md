---
name: spark-mac-share
description: >-
  Sync the gitignored _IDEAS/ strategy folder between this machine and the private
  Google Drive share (My Drive/Orionfold/spark-mac-share/_IDEAS), respecting the
  share contract (Drive wins, check-before-edit, push+reindex-after-edit). Trigger
  when the user says "sync ideas", "sync the share", "sync spark-mac-share",
  "push _IDEAS to drive", "pull ideas from drive", "is the share in sync?", or at
  the START of any session that will read/edit _IDEAS/ files and at the END of any
  session that changed them. Works identically on Spark and Mac (the skill +
  scripts live IN the share). Do NOT use the Google Drive MCP create_file tool for
  bulk or binary transfers — rclone is the channel; MCP is the single-small-file
  fallback only.
---

# spark-mac-share — sync the private _IDEAS/ share

**Contract (authoritative copy: `_IDEAS/README.md`, also on Drive):** Drive is the
source of truth; the latest file version wins; check Drive before editing; push the
changed files + a regenerated `_SYNC-INDEX.md` after editing; `_IDEAS/` never enters
a public repo.

**Why rclone, not the Drive MCP** (measured 2026-06-12, the founding session):
the MCP `create_file` channel forces every byte through model context (~2x tokens
per byte), has no update/delete (same-title pushes create duplicates), cannot carry
binaries >~100 KB (the SOTU PDF is unsendable), hard-blocks subagent uploads
(exfiltration classifier), and Cloudflare WAF-blocks payloads containing security
vocabulary (the `evaluate.md` research brief was unsendable — "jailbreak/injection"
content). Seeding ~20 text files cost ~45 minutes and ~350k tokens. `rclone` moves
the same set in seconds, bytes never enter context, handles binaries, and updates
in place.

## Procedure

### 0. Locate the share
The local share is the `_IDEAS/` directory at the repo root (Spark:
`/home/nvidia/ainative-business.github.io/_IDEAS/`; Mac: the equivalent checkout).
All sync tooling lives inside it: `_sync.sh`, `_sync_index_gen.py`,
`_SYNC-INDEX.md`, `README.md` (contract), `spark-mac-share-skill-spec.md` (this
skill's spec, for bootstrapping the other machine).

### 1. Preflight (first run on a machine only)
```bash
command -v rclone || echo missing
rclone listremotes | grep gdrive: || echo unconfigured
```
If missing/unconfigured, hand the operator this one-time setup (interactive —
suggest they run it themselves; it opens a browser OAuth):
```bash
# install:  Mac: brew install rclone   Spark: sudo apt install rclone
rclone config        # n) new remote -> name: gdrive -> type: drive
                     # default client id/secret -> scope: drive -> auto auth
rclone lsd gdrive:Orionfold/spark-mac-share   # verify
```
Until rclone exists, fall back to the Drive MCP for **single small text files
only** (folder IDs in `_IDEAS/README.md`; `disableConversionToGoogleType: true`;
expect a permission prompt; never attempt bulk/binary/security-vocabulary content).

### 2. Sync down (start of session, or before editing any _IDEAS file)
```bash
_IDEAS/_sync.sh pull      # or `_sync.sh status` to just diff
```
Drive-newer files overwrite local (`--update` = newest mtime wins — the contract's
"latest version wins"). Then read/edit freely.

### 3. Sync up (end of session, after any _IDEAS change)
```bash
_IDEAS/_sync.sh push      # regenerates _SYNC-INDEX.md (writer auto: spark|mac), then pushes
```
Or `_IDEAS/_sync.sh` (no args) for the full pull → reindex → push cycle.

### 4. Verify + report
`_sync.sh status` should show no differences. Report to the user: files pulled,
files pushed, index writer/stamp. If rclone warns about **duplicate objects**
(legacy of the MCP-seeded era), run `rclone dedupe --dedupe-mode newest
gdrive:Orionfold/spark-mac-share/_IDEAS` — newest matches the contract.

## Rules

- **Never** sync `_IDEAS/` content into a git commit, a public page, or any other
  external service. HANDOFF.md may reference paths only.
- Conflict (both sides edited since last sync): the pull brings Drive's newer copy
  over local — if local had unpushed work, `git`-style rescue does not exist; the
  skill's pull-first ordering plus end-of-session pushes make this window small.
  When in doubt run `status` first and show the user the diff list before pulling.
- The index (`_SYNC-INDEX.md`) is generated, never hand-edited.
- Living-doc protocol applies to the contents (refresh after gates/pivots; mark
  superseded, don't delete).
- Mac bootstrap: pull the share once (rclone), then copy
  `spark-mac-share-skill-spec.md` → the Mac repo's `.claude/skills/spark-mac-share/SKILL.md`
  (the spec body IS this skill).
