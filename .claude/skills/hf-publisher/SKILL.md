---
name: hf-publisher
description: End-to-end workflow conductor for publishing Orionfold artifacts (GGUF / LoRA / adapter) to HuggingFace under the `Orionfold` user handle. **Trigger aggressively** on "publish to HF", "push to huggingface", "ship the GGUF", "push the quant", "release `<slug>`-GGUF", "flip dry_run=False", "live HF push", `/hf-publisher`, OR whenever the user has just finished a `fieldkit.publish.publish_quant(..., dry_run=True)` cycle and the natural next step is the real push. **Three modes:** `interactive` (default — confirm at every gate), `resume-stage` (when a verified stage already exists at `/tmp/orionfold-stage/<slug>/`, skip dry-run + jump to push), `full-auto` (triggered by phrases like "publish/ship/distribute to hf" — auto-resolve everything, stop only on hard errors). Owns the *artifact-publish surface* — sibling to `fieldkit-curator` (PyPI) and `frontier-scout` (paper scouting). Walks Claude through pre-stage license + chat-format + recommended-variant resolution, dry-run, automated stage verification, manual review gate, detached upload with anchor-tight progress monitoring, and the easy-to-forget post-push tail (HANDOFF, descriptive commit, project-stats refresh, article promotion). Skip on general HF questions ("what is HF?"), pure quantize intent (no publish), or `huggingface-cli download` flows — those aren't this skill's job.
---

# hf-publisher

Owns the *Orionfold HuggingFace publish surface*. Codifies the gates we burned an hour discovering on `Orionfold/finance-chat-GGUF` so the next push (legal-chat, cyber-chat, etc.) hits the live upload in one Claude session.

This skill is a **workflow conductor**, not a code library. The actual push primitives live in `/home/nvidia/ainative-business.github.io/fieldkit/src/fieldkit/publish/__init__.py` (`ModelCard`, `HFHubAdapter`, `publish_quant`, `ArtifactManifest`). The skill orchestrates which knobs to set, which gates to pass, and what to do after.

## Mode router

| Mode             | Triggered by                                                         | Behavior                                                       |
|------------------|----------------------------------------------------------------------|----------------------------------------------------------------|
| `interactive`    | default; "publish to HF", "push to huggingface", `/hf-publisher`     | Confirm license, chat_format, recommended_variant, push gate via `AskUserQuestion` at each step. Quote staged README slices back. |
| `resume-stage`   | a verified stage already exists at `/tmp/orionfold-stage/<slug>/`    | Auto-detect via `ls`. Skip dry-run + metadata resolution. Run verify_stage, brief stage-content sanity, then push. |
| `full-auto`      | "publish/ship/distribute `<slug>` to hf", "auto-publish to hf"       | Auto-resolve everything. Hard-stop on: missing token, verify_stage <6/6, missing override for non-Apache license. Otherwise proceed. |
| `card-audit`     | "audit `<repo>`'s HF card", "card-audit `Orionfold/<slug>-GGUF`", "what's missing from the `<X>` card", `/hf-publisher card-audit <repo>` | Read-only: pull README + file list from an *already-pushed* HF repo, run verify_stage + diff against `references/card-polish.md`, report gaps. No upload. |

If the user's intent is ambiguous, default to `interactive`. Never escalate to `full-auto` without an explicit auto-phrase from the user.

## Every invocation — read these first

Five non-skippable preflights. Run all five before doing anything else; if any fails, surface to the user and bail.

### 1. Auth — `HF_TOKEN` must resolve to user `Orionfold`

```bash
set -a && source /home/nvidia/ainative-business.github.io/.env.local && set +a
HF_TOKEN="$HF_TOKEN" /tmp/fk-test/bin/hf auth whoami
# Expected: user=Orionfold orgs=orionfoldllc
```

If `HF_TOKEN` is missing from `.env.local`, see `[[reference_fieldkit_pypi_auth]]` for token-store shape (chmod 600, gitignored). If `whoami` returns the wrong user, the token belongs to a different account — STOP and ask the user.

### 2. Spark xet-permission safety — set every time

```bash
export HF_HOME=/home/nvidia/data/.hf-cache
export HF_HUB_DISABLE_XET=1
```

The system `~/.cache/huggingface/` is root-owned (legacy from a past sudo run); the Rust xet uploader explodes with `Permission denied (os error 13)` when it tries to write log + cache files. These two env vars route around it. **Bake into every script the skill ships.** The bundled `scripts/hf_push.py` sets them via `os.environ.setdefault`; if you write any inline Python, do the same.

### 3. Spark unified-memory headroom

```bash
free -h | grep '^Mem:' | awk '{print $7}'
# Need ≥ 80 GB free for safe push of large GGUFs alongside any running services
```

Per `[[project_spark_unified_memory_oom]]`. If under 80 GB, suggest stopping NemoClaw / Ollama / vLLM first.

### 4. Identify stage dir + auto-suggest mode

```bash
MODEL_SLUG=<from-user-or-MODEL_ID-basename>
STAGE_DIR=/tmp/orionfold-stage/$MODEL_SLUG
[ -f "$STAGE_DIR/README.md" ] && echo "stage exists — suggest resume-stage mode"
```

If the stage exists and is < 24 hours old, recommend `resume-stage`. If it's older or partial (no README.md), recommend the full `interactive` flow.

### 5. Bandwidth realism

```bash
du -sh "$STAGE_DIR" 2>/dev/null
# Estimate: 32 GB at observed Spark upstream (~5 MB/s aggregate) ≈ 1.5–2 hours
```

Tell the user the size + ETA *before* they commit to the push. We observed ~5 MB/s aggregate across 5 parallel LFS uploads on Spark home network. A 32 GB push takes ~1.5–2 hours. Set this expectation early so the user doesn't think it's hung at the 30-minute mark.

## Workflow (default `interactive` mode)

The spine. Mode-specific deviations called out inline.

### Step 1 — Resolve metadata (skip in resume-stage)

Three coupled inputs the rendered card needs. Get all three before running dry-run.

**model_license** — the upstream model's HF license tag. Defaulting to `apache-2.0` is the trap that bit `Orionfold/finance-chat-GGUF`. To resolve:
1. Read `references/license-tags.md` for the decision tree.
2. Pull `tokenizer_config.json` + `README.md` from the source HF repo (or `/home/nvidia/data/models/<slug>/` if already downloaded).
3. Look at the README's "License" section, the model card's `license:` frontmatter, and the lineage ("derived from Llama-2-Chat" → `llama2`).
4. In `interactive` mode: surface the inferred answer + alternatives via `AskUserQuestion`. In `full-auto`: pick the inferred answer; **bail if confidence is low** (e.g., README says "License: Other" with no further clarification).

**chat_format** — the `llama_cpp.Llama(chat_format=...)` value threaded into the rendered llama-cpp-python snippet. Resolve via `references/chat-formats.md` + grep the `chat_template` field in `tokenizer_config.json`. Same `AskUserQuestion` / infer split as above. Empty string is valid for base / no-chat-template models — but per `[[feedback_chat_vs_continued_pretrain_trap]]`, that's a publishing red flag worth surfacing.

**recommended_variant** — the variant featured in default `## How to run` snippets. Default `Q5_K_M` if present in the variants list; else first listed. In `full-auto`, just pick. In `interactive`, confirm.

Show the user the final triple before proceeding:

> Resolved metadata for `<repo>`:
> - model_license: `llama2`  ← detected from tokenizer chat_template ([INST]) + README mentioning Llama-2 lineage
> - chat_format: `llama-2`
> - recommended_variant: `Q5_K_M`
>
> Proceed?

### Step 2 — Run dry-run (skip in resume-stage)

For G3-shaped quants:

```bash
cd /home/nvidia/ainative-business.github.io
MODEL_ID=<repo> MODEL_LICENSE=<tag> CHAT_FORMAT=<format> RECOMMENDED_VARIANT=<var> \
  ./scripts/g3_build_first_quant.sh publish-dryrun
```

For non-G3 paths (bespoke `fieldkit.publish.publish_quant` calls), thread the same three kwargs into the call. Don't accept a dry-run that runs without explicit `model_license=` — that's the bug.

The dry-run writes:
- `/tmp/orionfold-stage/<slug>/README.md` — rendered model card
- `/tmp/orionfold-stage/<slug>/model-*.gguf` — staged binary files
- `/home/nvidia/ainative-business.github.io/src/content/artifacts/<slug>-gguf.yaml` — manifest

### Step 3 — Verify stage (always)

```bash
bash /home/nvidia/.claude/skills/hf-publisher/scripts/verify_stage.sh /tmp/orionfold-stage/<slug>
```

Six automated checks:
1. `license:` frontmatter is non-default (or explicitly `apache-2.0` after upstream-Apache verification).
2. `## How to run` body has ≥ 8 non-empty lines after the header.
3. `## Spark-tested` table column count matches variants count + 1.
4. `## Methods` link points at an existing `/home/nvidia/ainative-business.github.io/articles/<slug>/` directory.
5. The `## Variants` table covers every `model-*.gguf` file in stage.
6. Engagement-pull metadata: `pipeline_tag` + `library_name` present, `tags:` has ≥ `$VERIFY_MIN_TAGS` (default 3) entries including the required tag(s) in `$VERIFY_REQUIRED_TAGS` (default `spark-tested`). The 0-likes / 472-DL gap on `Orionfold/II-Medical-8B-GGUF` was the lesson here — HF's discoverability surfaces rank these fields heavily and a card that lands without them gets buried regardless of measurement quality. See `references/card-polish.md` for the full engagement-pull recipe.

Exit code = number of failed checks. **In `full-auto` mode, hard-stop if exit > 0.** In `interactive`, surface failures + ask whether to fix and re-dry-run. The fix path for check 6 is usually: re-run `publish_quant(..., tags=("gguf", "llama-cpp", "spark-tested", "<vertical>", ...))` in step 2; for older already-pushed cards, see the `card-audit` mode below.

### Step 4 — Manual review gate (interactive only; auto-pass in full-auto when verify is 5/5)

Read the staged README and **quote three slices back to the user**:

1. The full YAML frontmatter (so they can verify license + tags + base_model).
2. The first `## How to run` code block (so they can confirm the snippets are what customers will see).
3. The `## Spark-tested` table (so they can sanity-check the numbers).

Then ask explicitly: "Push to `https://huggingface.co/Orionfold/<repo>` (public, ~<size>, ETA ~<minutes>)?"

This is also where the **customer-link audit** runs — if the article at `articles/<slug>/article.md` is linked from the Methods section (it always is by default), confirm it has passed the audit per `[[feedback_customer_link_audit]]` and `tech-writer` skill `references/voice-and-style.md`. If not, redirect to `tech-writer` before pushing.

### Step 5 — Live push (detached)

**Two push scripts ship with this skill** — pick by connection profile:

| Script | Backing API | Default workers | Resumable | When to use |
|---|---|---|---|---|
| `hf_push.py` | `HfApi.upload_folder` (via `fieldkit.publish.HFHubAdapter.push_folder`) | parallel LFS streams (HF-internal) | NO — partial uploads must restart from 0 | Fast, stable connections (≥100 Mbit/s upstream); single-shot pushes where the cost of a re-upload is acceptable |
| `hf_push_resilient.py` | `HfApi.upload_large_folder` directly | configurable, **default 1** (sequential) | YES — `<stage>/.cache/.huggingface/` persists per-task state across runs; re-running picks up where the last attempt left off | **Default on Spark** (~38 Mbit/s upstream measured 2026-05-14); any push >5 GB; any push retry after a crash; long-running detached uploads |

The lesson behind the second script: on 2026-05-14, the Saul-7B push crashed at the 1h29m mark with `httpx.RemoteProtocolError: Server disconnected without sending a response` inside `_wrapped_lfs_upload`. The whole upload pipeline died on a single transient server hiccup with zero retry — `upload_folder` doesn't propagate `http_backoff` retries to multipart LFS uploads (known: <https://github.com/huggingface/huggingface_hub/issues/2539>). `upload_large_folder` was designed for exactly this case: split the work into many small tasks, persist per-task state, retry indefinitely on transient errors. HF explicitly recommends **low `num_workers`** for slower connections: "partially uploaded files will have to be completely re-uploaded if the process is interrupted." The Spark IS the slower-connection case.

**Default (resilient) push:**

```bash
REPO_NAME=<repo> STAGE_DIR=/tmp/orionfold-stage/<slug> \
NUM_WORKERS=1 PRINT_EVERY=30 \
  nohup /tmp/fk-test/bin/python /home/nvidia/.claude/skills/hf-publisher/scripts/hf_push_resilient.py \
  >> /tmp/orionfold-push.log 2>&1 &
disown
```

**Legacy (fast) push, for stable high-bandwidth connections only:**

```bash
REPO_NAME=<repo> STAGE_DIR=/tmp/orionfold-stage/<slug> \
  nohup /tmp/fk-test/bin/python /home/nvidia/.claude/skills/hf-publisher/scripts/hf_push.py \
  >> /tmp/orionfold-push.log 2>&1 &
disown
```

Both scripts reuse the staged dir — never re-copy GGUF bytes via the `publish_quant` orchestrator just to flip `dry_run`. `nohup` + `disown` lets the upload survive shell exits.

**Resume-after-crash:** if `hf_push_resilient.py` exits with `=== PUSH PARTIAL` (or `=== PUSH INTERRUPTED`), the cache at `<STAGE_DIR>/.cache/.huggingface/` is intact — re-run the same command verbatim. The SDK picks up from the last successfully-completed task; nothing is re-uploaded that was already on the Hub.

### Step 6 — Monitor terminal state

Arm a Monitor with the **anchor-tight grep pattern**. The naive filter `401|403|429` is the trap that fired 8 times during the finance-chat push because tqdm progress bars contain `401M`, `403M`, etc. — bare 3-digit codes false-match megabyte counters.

The good filter:

```
tail -F /tmp/orionfold-push.log 2>/dev/null | grep -E --line-buffered \
  "^Traceback|^OSError|HfHubHTTPError|HFAuthError|RepositoryNotFoundError|Permission denied|HTTP/[0-9]\.[0-9]\" 4[0-9][0-9]|HTTP/[0-9]\.[0-9]\" 5[0-9][0-9]|Upload [0-9]+ LFS files: 100%|^hf_url:|^public URL:|huggingface\.co/Orionfold"
```

Anchored: `^Traceback` (line-start), `HTTP/X.Y" 4XX` (proper request-log format), `Upload N LFS files: 100%` (tqdm completion bar). Never bare digits.

### Step 7 — Post-push obligations

The easy-to-forget tail. Compounds across releases — every skipped item is a future "wait, why isn't the stats page updated" thread.

- [ ] **Update `HANDOFF.md`** — live URL + variant table (size, ppl, tok/s, vertical-eval) + actual upload time + any new lessons. Per `[[feedback_handoff_md_update_protocol]]`.
- [ ] **Write a descriptive commit subject** — Mac's `/sync-field-notes` skill reads `git log` over the NFS-mounted source to know what shipped. `feat(field-notes): publish Orionfold/<slug>` + a body summarizing variant table is the change narrative. No separate SYNC-HANDOFF / SYNC-RENAMES files to maintain — those were deleted in the 2026-05-22 workflow simplification per `[[sync-workflow-nfs-mount]]`.
- [ ] **Check `mirrors/destination-overrides.md`** — only if the push introduces a new top-level page or path (most pure-quant pushes don't touch Mac-owned chrome). Per `[[destination-overrides-mirror]]`.
- [ ] **Refresh `src/data/project-stats.json`** — invoke the `nvidia-learn-stats` skill. Per `[[feedback_refresh_stats_on_publish]]` — the home "At a glance" infographic drifts silently otherwise.
- [ ] **Promote the article** — flip `status: upcoming` → `status: published` in `articles/<slug>/article.md` if not already done. Add `hf_url` to frontmatter if the schema supports it.
- [ ] **Commit + push to main** — solo-blog repo per `[[project_nvidia_learn_git_workflow]]`. Confirm with the user first; expect a permission prompt on first main-push per session.

## `card-audit` mode — gap report against an already-pushed card

Read-only mode for **post-hoc remediation** of cards that landed before `references/card-polish.md` codified the engagement-pull recipe. The canonical use case is `Orionfold/II-Medical-8B-GGUF` (472 DL / 0 likes), but applies to any Orionfold card whose pull doesn't match the v5 §3.15.b recipe.

This mode does **not** push. It produces a gap report; the user picks which gaps to remediate and runs the retro-fix playbook in `references/card-polish.md` (steps 1–5).

### Step A — Resolve the audit target

```bash
REPO=<user-supplied>                    # e.g., Orionfold/II-Medical-8B-GGUF
SLUG=$(basename "$REPO")                # II-Medical-8B-GGUF
AUDIT_DIR=/tmp/card-audit/$SLUG
mkdir -p "$AUDIT_DIR"
```

`REPO` should already exist on HF — confirm with `hf auth whoami` + a `list_repo_files` round-trip.

### Step B — Pull the README + file list (no LFS download)

```bash
set -a && source /home/nvidia/ainative-business.github.io/.env.local && set +a
PYBIN=${HF_VENV:-/tmp/fk}/bin/python    # /tmp/fk-test is stale per [[reference_fk_test_venv_stale]]
"$PYBIN" - <<EOF
from huggingface_hub import HfApi
import os, pathlib
api = HfApi(token=os.environ["HF_TOKEN"])
audit_dir = pathlib.Path("$AUDIT_DIR")
# README only — no LFS bytes
api.hf_hub_download(repo_id="$REPO", filename="README.md", local_dir=str(audit_dir))
# File list → synthesise empty model-*.gguf placeholders so Check 5 can pass
files = api.list_repo_files(repo_id="$REPO")
for f in files:
    if f.startswith("model-") and f.endswith(".gguf"):
        (audit_dir / f).touch()
print(f"audit ready: {audit_dir}")
EOF
```

The `touch` placeholders are how Check 5 (Variants table coverage) passes against an HF audit without paying the LFS-download bandwidth. The verifier opens README, scans `## Variants` rows, and compares against `ls`-visible files — empty stubs are equivalent for that check.

### Step C — Run verify_stage against the audit dir

```bash
bash /home/nvidia/.claude/skills/hf-publisher/scripts/verify_stage.sh "$AUDIT_DIR"
```

In audit mode, all six checks are meaningful:
1. License frontmatter — usually passes (cards were dry-run-verified at push time)
2. `## How to run` body — usually passes
3. `## Spark-tested` table shape — usually passes
4. `## Methods` article link — usually passes (article is local)
5. Variants table covers `model-*.gguf` — passes via touch'd placeholders from step B
6. **The check that triggered this mode** — `pipeline_tag` / `library_name` / `tags` completeness, including required `spark-tested`

If 6/6 PASSED → the card metadata is current; the engagement gap (if any) is content-design, not metadata. Move on to step D for the deeper card-polish.md diff anyway.

### Step D — Diff against `references/card-polish.md` engagement-pull recipe

verify_stage covers the *automatable* metadata gates. The five engagement-pull elements in `references/card-polish.md` include three that aren't easily greppable:

1. Spark-tested block placement (must be above `## How to run`, not buried)
2. `## Other Orionfold vertical curators` block presence + completeness (all sibling cards listed)
3. GitHub Sponsors footer line presence

For each, hand-read the staged README and report. Suggested grep helpers:

```bash
# Element 1 — Spark-tested position relative to How to run
grep -n -E "^## Spark-tested|^## How to run" "$AUDIT_DIR/README.md"
# Spark-tested line number should be LESS than How to run line number.

# Element 2 — Cross-link block
grep -n "Other Orionfold vertical curators" "$AUDIT_DIR/README.md"
# Expect 1 hit; if 0, missing.

# Element 3 — Launch-list footer (Sponsors is deferred per references/card-polish.md §4)
grep -nE "Join the launch list|github\.com/sponsors" "$AUDIT_DIR/README.md"
# Expect ≥1 hit; if 0, missing. Launch-list is the current default endpoint;
# Sponsors becomes valid once orionfold.com launches + 6+ verticals ship.

# Element 4 — Read-the-deep-dive wire-back
grep -nE "Read the deep-dive|ainative\.business/field-notes" "$AUDIT_DIR/README.md"
# Expect ≥1 hit.

# Element 5 — Recommended variant prominence
grep -nE "^\*\*Recommended:?\*\*|Recommended.*Q[0-9]_K_M" "$AUDIT_DIR/README.md"
# Expect ≥1 hit ABOVE or IN the variants table, not just under it.
```

### Step E — Write the gap report

Write `$AUDIT_DIR/gaps.md` summarising verify_stage output + the step-D hand-checks. Quote the failing lines back to the user. Recommended template:

```markdown
# Card audit — $REPO

> Audited: <YYYY-MM-DD HH:MM UTC>

## verify_stage.sh

<paste the [PASS]/[FAIL] table here>

## Engagement-pull elements (references/card-polish.md)

| Element                              | Present? | Notes                                    |
|--------------------------------------|----------|-------------------------------------------|
| Spark-tested block above How to run | <Y/N>    | <line numbers>                           |
| Cross-link block                     | <Y/N>    | <listed siblings vs expected>            |
| Launch-list footer                   | <Y/N>    | (Sponsors deferred — see card-polish.md §4) |
| Article wire-back                    | <Y/N>    |                                          |
| Recommended variant prominent        | <Y/N>    |                                          |

## Recommended retro-fix

<one paragraph naming the gaps + linking to card-polish.md step 1–5>
```

Print only the gap-count summary + audit-dir path to chat. The user opens `gaps.md` for detail.

### Step F — Stop. Do not upload.

`card-audit` is read-only. The retro-fix playbook in `references/card-polish.md` (steps 1–5) is the user's call after reading the gap report. If they want, they can invoke `hf-publisher` in `interactive` mode pointed at the audit dir with explicit `card-only-push` intent — but that's a follow-on session, not this mode's responsibility.

## Non-negotiables

- **Never push without dry-run + verify_stage in the same session.** The `fieldkit.publish` rendering bugs that cost the finance-chat push were both invisible until the staged README hit human eyes.
- **Never re-copy GGUF bytes.** `publish_quant(..., dry_run=False)` re-stages the entire folder via `shutil.copy2` — for 32 GB, that's 5 minutes of disk churn for nothing. Reuse the existing stage via `HFHubAdapter(staging_dir=..., dry_run=False).push_folder()`.
- **Never use bare 3-digit HTTP codes in monitors.** Use anchored patterns. The lesson cost 8 false-positive notifications on the finance-chat push.
- **Never skip the post-push checklist.** Each skipped item is a debt that compounds across releases. The stats infographic, in particular, is user-facing.
- **Never default `model_license` to `apache-2.0` silently.** If the source model is Llama / Gemma / Qwen / CC-BY-NC, the HF badge will be wrong and the customer will trust an incorrect license claim.
- **Never use `hf_push.py` for >5 GB pushes from the Spark.** Bandwidth profile is ~38 Mbit/s upstream; the `upload_folder` API doesn't retry on transient `httpx.RemoteProtocolError` and the whole pipeline dies on a single server hiccup, forcing a full re-upload. Use `hf_push_resilient.py` instead — same env vars, resumable cache, sequential default.

## Where to look for deeper guidance

- `references/license-tags.md` — common HF license tags + decision tree + how to detect from a downloaded model.
- `references/chat-formats.md` — `llama_cpp.Llama(chat_format=...)` reference for the rendered card snippets.
- `references/card-polish.md` — v5 §3.15.b engagement-pull recipe (Spark-tested placement, sibling cross-links, llms.txt wire-back, GH Sponsors, frontmatter completeness) — driver for `verify_stage.sh` Check 6 and the `card-audit` mode.
- `/home/nvidia/ainative-business.github.io/scripts/g3_build_first_quant.sh` — canonical dry-run + measure pipeline; read `step_dry_run_publish` for the publish_quant call shape.
- `/home/nvidia/ainative-business.github.io/fieldkit/src/fieldkit/publish/__init__.py` — `publish_quant` kwargs (especially `model_license`, `chat_format`, `recommended_variant`, `vertical_eval`, `vertical_eval_name`).
- `/home/nvidia/ainative-business.github.io/.env.local` — `HF_TOKEN` store. chmod 600. Don't leak.
- Memory: `[[reference_fieldkit_pypi_auth]]`, `[[feedback_handoff_md_update_protocol]]`, `[[feedback_sync_handoff_per_release]]`, `[[feedback_sync_handoff_frontmatter_schema]]`, `[[feedback_refresh_stats_on_publish]]`, `[[feedback_customer_link_audit]]`, `[[feedback_preflight_bench_before_quant]]`, `[[feedback_chat_vs_continued_pretrain_trap]]`, `[[project_spark_unified_memory_oom]]`, `[[project_orionfold_parent_brand]]`, `[[project_nvidia_learn_git_workflow]]`.
- Sibling skills: `fieldkit-curator` (the PyPI-publishing analogue; same mode-router pattern), `tech-writer` (article side of the customer-link contract; voice-and-style.md has the audit rules).
