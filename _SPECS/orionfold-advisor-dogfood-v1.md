---
project: orionfold-advisor-dogfood
version: v1.0
status: DRAFT (companion ledger for Orionfold Advisor proof; unbuilt)
created: 2026-06-09
authoritative: Spark
---

# Orionfold Advisor Dogfood v1.0

> Parallel tracked dogfood spec for the Orionfold Advisor Unsloth + Arena proof.
> Its job is to preserve the fieldkit and Arena improvements discovered while
> operating the run like a real user in browser-use mode. The main proof spec
> asks "did the model-to-evidence loop work?" This spec asks "what did the loop
> teach the machine that runs the loop?"

## 1. Context

The prior long Arena tasks proved that dogfooding should be tracked as its own
body of work. `arena-enhancements-v1.md` and `arena-enhancements-v2.md`
formalized features that fell out of live runs: build-spine visibility, reward
observability, lane truth, run context, inventory truth, corpus handshake, and
guarded lane launch. The Advisor proof should use the same discipline from the
start.

The run should be operated through Arena as much as possible:

```bash
.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh restart --browser
```

Arena is the system of record. If a necessary observation or action can only be
done in the terminal, that is either:

1. expected external setup, or
2. a dogfood finding recorded here.

## 2. Relationship to the Main Spec

Companion spec:

- `_SPECS/orionfold-advisor-unsloth-arena-v1.md`

The main spec owns:

- domain gate
- corpus manifest
- Advisor bench
- Unsloth Core training/export
- fieldkit manifest/import
- Arena lane launch/inference/eval
- RL headroom decision
- publish or rejection receipt

This dogfood spec owns:

- fieldkit feature and enhancement findings
- Arena feature and enhancement findings
- browser-use evidence discipline
- release posture for any fixes discovered during the run

## 3. Browser-Use Operating Contract

The proof run should follow the narrated operator-smoke cadence from
`_GUIDES/arena-e2e-smoke-runbook.md`.

For each step:

1. State the step and success criterion before acting.
2. Name the Arena pane the operator should watch.
3. Prefer Arena UI/API actions over terminal commands.
4. Confirm whether Arena's render matched reality.
5. Capture a scoped screenshot when the pane carries useful evidence.
6. Record any mismatch or terminal-only workaround in this spec.

Browser harness:

- Sidecar: `http://127.0.0.1:7866/`
- CDP Chromium: `127.0.0.1:9222`
- Screenshot staging: `/tmp/orionfold-advisor-dogfood/`

After any Arena UI change:

```bash
fieldkit arena build --repo-root arena-app
.claude/skills/arena-lifecycle/scripts/arena_lifecycle.sh restart --browser
```

Then browser-smoke the affected pane before resuming the model run.

## 4. Finding IDs and Ledger Shape

Use two prefixes:

- `AD-FK-*` for fieldkit findings.
- `AD-AE-*` for Arena findings.

Each finding uses this shape:

```text
ID:
Status: proposed | accepted | built | deferred | rejected
Finding:
Observed during:
Expected operator behavior:
Current workaround:
Proposed fix class:
Release posture:
Evidence:
```

Fix classes:

- bug
- observability
- UX
- import/export
- eval
- provenance
- guardrail
- docs
- packaging
- browser-use

Release posture values:

- fix-now
- next-fieldkit-release
- next-arena-enhancement
- future-spec
- document-only
- no-build

## 5. Fieldkit Dogfood Track

The fieldkit track records gaps in reusable package behavior, docs, import
helpers, eval surfaces, manifests, packaging, and release readiness.

Seed finding candidates:

| ID | Status | Finding | Release posture |
|---|---|---|---|
| AD-FK-1 | proposed | Unsloth export metadata may need a stable import receipt: base model, adapter path, export kind, training source, license, corpus manifest, and eval target. | next-fieldkit-release if repeated beyond this run |
| AD-FK-2 | proposed | Advisor bench loader may need a reusable source-citation eval shape rather than script-local parsing. | document-only for v1; promote on second reuse |
| AD-FK-3 | proposed | fieldkit publish manifests may need clearer `training_source` / `stack_origin` fields for Unsloth Core vs Studio vs NeMo. | next-fieldkit-release if publish gate passes |
| AD-FK-4 | proposed | RAG recall gates should be easy to run against public product/book/artifact sources, not just article chunks. | next-fieldkit-release if current memory API friction appears |
| AD-FK-5 | proposed | A rejection receipt pattern may need first-class support so failed candidates still preserve evidence without becoming promoted artifacts. | future-spec unless needed immediately |
| AD-FK-6 | proposed | Unsloth Core setup/install friction on Spark should be documented as a deterministic recipe if repeated. | document-only or next-fieldkit-release |
| AD-FK-7 | proposed | Privacy scan may need corpus-manifest-specific checks for private paths, handoff references, and operator state. | fix-now if leakage risk appears |

During the run, add concrete findings only when observed. Do not build a new
fieldkit abstraction merely because one run used a script. Promotion rule:
script-local first, fieldkit module after repeat reuse or clear stable metadata.

## 6. Arena Dogfood Track

The Arena track records gaps in observing, arming, dispatching, scoring,
explaining, and preserving the Advisor run.

Seed finding candidates:

| ID | Status | Finding | Release posture |
|---|---|---|---|
| AD-AE-1 | proposed | Domain gate and base-model scout may not be visible from Arena, forcing terminal/report reading before the run starts. | next-arena-enhancement if it blocks operator flow |
| AD-AE-2 | proposed | Corpus manifest and public/private source boundary may need a first-class Build or Knowledge pane view. | next-arena-enhancement |
| AD-AE-3 | proposed | Unsloth training progress may not feed SFT/Training panes without a heartbeat adapter. | fix-now if screenshots/evidence require it |
| AD-AE-4 | proposed | Arena import flow may not capture Unsloth adapter/GGUF metadata cleanly. | next-arena-enhancement |
| AD-AE-5 | proposed | Advisor eval families may need a richer bench preview than existing prompt/gold display. | document-only for v1 unless blocking |
| AD-AE-6 | proposed | RL headroom decision may need a visible gate card before an `rl_run` can be armed. | next-arena-enhancement if the gate is terminal-only |
| AD-AE-7 | proposed | Autonomous-harness screenshots may need a dedicated run digest tying domain gate, training, eval, and publish/reject outcomes together. | next-arena-enhancement |
| AD-AE-8 | proposed | Any live pane that shows stale/prior-run Advisor data without a provenance chip becomes a run-context defect. | fix-now if misleading |
| AD-AE-9 | proposed | Any lane launch/select step done outside Arena despite a known recipe becomes a lane-lifecycle finding. | next-arena-enhancement |
| AD-AE-10 | proposed | Any publish/rejection decision not visible in Arena becomes a workflow-completion finding. | future-spec or product article input |

Concrete findings observed during the run:

```text
ID: AD-AE-11
Status: proposed
Finding: Advisor proof-start evidence can be generated and scored locally, but the live Cortex pane cannot display the Advisor public corpus manifest, bench, or recall receipt as a run-specific artifact.
Observed during: 2026-06-09 Advisor manifest + local RAG recall gate after bringing Arena up in browser-use mode.
Expected operator behavior: The operator should be able to watch an Advisor/Knowledge/Cortex pane show the 181-source public manifest, source-role/book-surface coverage, bench row counts, and recall gate result before moving to base-model scout.
Current workaround: Run `scripts/orionfold_advisor/generate.py` and `scripts/orionfold_advisor/score_recall.py` in the terminal, then inspect tracked evidence under `evidence/orionfold-advisor/`. Live Cortex shows no eval runs and no Advisor-specific receipt.
Proposed fix class: observability
Release posture: next-arena-enhancement
Evidence: `/tmp/orionfold-advisor-dogfood/cortex-no-advisor-recall.png`; tracked recall report `evidence/orionfold-advisor/rag-recall-v0.1.json`.

ID: AD-AE-12
Status: proposed
Finding: The Advisor base-model scout was completed with metadata probes, but Arena/browser-use did not advance past the Cortex pane because the cockpit has no visible base-model scout or preflight artifact surface.
Observed during: 2026-06-09 Advisor base-model scout after `AD-AE-11`; the visible CDP Chromium tab remained on `http://127.0.0.1:7866/arena/cortex/` while `hf-model-scout` wrote `/tmp/hf-scout/2026-06-09/advisor-8B/report.md` and `candidates.json`.
Expected operator behavior: The operator should be able to watch an Advisor/Arena pane show candidate model probes, license/gating status, chat-template and llama.cpp compatibility checks, Spark envelope estimates, the recommended pick, fallbacks, and the next generator-preflight gate.
Current workaround: Run the scout from the terminal with Hugging Face metadata queries and read the scratch report under `/tmp/hf-scout/`. The cockpit remains parked on Cortex and gives no indication that the model-scout step completed.
Proposed fix class: observability
Release posture: next-arena-enhancement
Evidence: Scratch scout report `/tmp/hf-scout/2026-06-09/advisor-8B/report.md`; sidecar `/tmp/hf-scout/2026-06-09/advisor-8B/candidates.json`; read-only CDP tab query showed active page `Orionfold Arena — Cortex` at `/arena/cortex/`.
```

## 7. Expected External Setup vs Dogfood Gap

Expected external setup is not automatically a defect. Examples:

- Installing Unsloth Core or CUDA/PyTorch dependencies.
- Pulling a new base model from Hugging Face.
- Operator-owned secrets or tokens.
- One-time root-owned directory cleanup.
- Confirming license terms outside the cockpit.

Dogfood gaps include:

- Arena cannot show the source corpus boundary after it exists.
- Arena cannot show training progress after a heartbeat or log exists.
- Arena cannot import or describe an exported candidate.
- Arena cannot select or launch a known lane recipe.
- Arena cannot run or display the Advisor eval once the bench exists.
- Arena cannot show the headroom gate that decides RL vs skip.
- Arena reports a lane, run, score, or source boundary that does not match
  reality.

## 8. Evidence and Screenshot Discipline

Screenshots must be scoped and public-safe.

Required evidence classes:

- Corpus/Knowledge coverage.
- Advisor bench preview or eval result.
- Unsloth training/export receipt, if visible.
- fieldkit manifest/import receipt.
- LaneTruth / Models active lane.
- Chat or Compare inference.
- Jobs card for eval/training/RL/headroom.
- Leaderboard or score surface.
- Reward/headroom gate.
- Standup or autonomous-harness digest.
- Any mismatch between Arena report and observed reality.

Do not capture secrets, full filesystem paths where avoidable, token values, or
private handoff content.

## 9. Closeout Rules

At run close:

1. Classify every open finding.
2. Mark each as fix-now, defer, document-only, or no-build.
3. Move mature Arena items into a future `arena-enhancements-v*` spec only if
   they are broader than the Advisor run.
4. Move mature fieldkit items into a fieldkit release plan only if they deserve
   package support.
5. Keep rejected or one-off findings in this spec as historical dogfood notes.
6. Update `HANDOFF.md` with only the current next action and release posture.

## 10. Acceptance Criteria

The dogfood track succeeds if:

- Every terminal-only workaround is classified.
- Every Arena report-vs-reality mismatch is recorded.
- fieldkit abstractions are not invented prematurely.
- Arena enhancements are tied to observed operator friction.
- Screenshots are sufficient for the autonomous-harness product article.
- The final public receipt can say what Arena made easier and what the run
  taught the cockpit to improve next.

## 11. References

- `_SPECS/orionfold-advisor-unsloth-arena-v1.md`
- `_GUIDES/arena-e2e-smoke-runbook.md`
- `_SPECS/arena-enhancements-v1.md`
- `_SPECS/arena-enhancements-v2.md`
- `_SPECS/spark-arena-v1.md`
- `_IDEAS/unsloth-compete-partner-analysis.md`

## 12. Change Log

| Date | Change | Author |
|---|---|---|
| 2026-06-09 | Companion dogfood spec authored from Codex planning session. Establishes AD-FK and AD-AE ledgers, browser-use operating contract, expected external setup boundary, and closeout rules. | Manav (with Codex) |
