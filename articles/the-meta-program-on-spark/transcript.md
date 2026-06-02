# Provenance — the-meta-program-on-spark

**Type:** concept / thesis essay (no hands-on session). MTBM-arc opener.
**Authored:** 2026-06-02, directly in-repo per the editorial-overlay plan in `WORKFLOWS.md` §3 and the HANDOFF "Editorial overlay" open item.

## Origin instruction

Operator request: "read handoff and recommend next steps" → "start the thesis-spine
deep-dive." Staked as a full published draft (vs the `status: upcoming` placeholder
option) per AskUserQuestion. Slug + title chosen: `the-meta-program-on-spark` /
"The Meta-Program on a DGX Spark — When the Tool You Build With Is an Instance of
the Thing You Build."

## Editorial overlay (from the operator)

Frame the "machine that builds machines" journey on the Spark as a **pane → hands →
engine** arc, folding in Chapter 14's meta-program framing (the tool you build with
is itself an instance of the thing you build; the specification IS the application;
configuration over code). Cross-link the published chapters via
`book_chapters: [10, 11, 14]`. Concept piece — no shipped product required.

## Grounding sources (verified on disk 2026-06-02)

- **Book chapters** at `src/data/book/chapters/`:
  - `ch-10-the-world-model.md` — queryable organizational state.
  - `ch-11-the-machine-that-builds-machines.md` — "the specification IS the machine's
    input"; Karpathy `program.md`; 8090 assembly-line-that-remembers; the recursion's
    bottlenecks (compute, long-tail complementarity, diminishing returns).
  - `ch-14-the-meta-program.md` — "the tool used to build domain applications IS a
    domain application"; "the specification IS the application"; "configuration over
    code" (~7,400 lines vs est. 30,000–50,000); governance inherited structurally;
    "cattle, not pets."
- **WORKFLOWS.md §1** — "This doc is itself a Ch-14 artifact"; the
  `origin instruction → skill → script → artifact` legend = the `program.md` pattern;
  the ~24 skills are configuration over the fieldkit + Claude-Code substrate.
- **WORKFLOWS.md §3** — the `pane → hands → engine` sequencing principle (verbatim:
  "Each phase makes the next more valuable, never the reverse … autonomy is useless
  without a control plane to approve and dispatch from"). NB: the article frames this
  as a *way of seeing the machine*, NOT as the roadmap phase plan — deliberately no
  Phase 0/1/2/3 leak.

## Published articles cited as evidence (cross-linked, /field-notes/<slug>/)

- `autoresearch-agent-loop` (A4) — the engine: 50 iters, 73.4 min, ~0.07 kWh, 8 keeps,
  best +0.93% over baseline; single recurring d_model=768 win = long-tail ceiling.
- `hermes-drives-the-spark-via-fieldkit-mcp` (H4) — the hands: fieldkit-as-MCP,
  llama-bench gate, 0% tool-call format error, no API key.
- `hardening-the-hermes-harness-on-spark` (H3) — harden-before-write-surface ordering.
- `distill-architect-lora-from-trajectories` (A8) — the recursion: agent trajectory →
  3B architect LoRA = the diagram's return arc as a file on disk.
- `trajectory-eval-is-the-agent-flailing` (A9) — observability on the loop.
- `guardrails-for-code-generation` (A5) — code-edit rails on the engine.
- `one-substrate-three-apps` (B) — the fork into the three arcs.

## Artifacts produced

- `article.md` — 8-section essay (~2,400 words); 1 inline `fn-diagram` (flow archetype,
  4 beats + dashed return arc, SPEC = accent node); 8 explainers (3 define / 2 why /
  1 pitfall / 1 deeper / 1 hardware).
- `src/components/field-notes/svg/MetaProgramRecursion.astro` — new signature
  (concentric mise-en-abyme + dashed loop arrow).

## Honest framing notes

- The **pane** is the least-built of the three beats (operator's seat = terminal +
  review-the-diff discipline today). The article says so explicitly rather than
  implying the loop is more autonomous than it is.
- Closed-loop eval→reward→fine-tune→re-eval is **not** wired; the pieces exist, the
  wiring is future work. Stated plainly in the Tradeoffs section.
- Bridge made explicit: the book's meta-program is the *ainative* SaaS platform; this
  is the *same pattern, another instance* on one Spark (per WORKFLOWS §1 framing).
