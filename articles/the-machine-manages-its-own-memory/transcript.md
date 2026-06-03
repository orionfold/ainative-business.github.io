# Provenance — the-machine-manages-its-own-memory

Source: a 2026-06-03 session driving the Arena recall layer (M10, `fieldkit.memory`
+ `/arena/knowledge/`) end-to-end on this repo's own corpus, as the Phase-A dogfood
of the completed `pane → hands → engine` arc.

## What actually happened (the record behind the article)

1. Brought the cockpit up (`arena_lifecycle.sh up`), confirmed pgvector (`vectors`
   db, 313 chunks / 50 slugs) + the NIM embedder (`:8001`) live. The knowledge pane
   showed coverage 100% but `index_note: live index unavailable: column "source" does
   not exist` — provenance columns not yet present.
2. Drove the cockpit through the VISIBLE Chromium over CDP (`playwright-core
   connectOverCDP` to `:9222`), operator-style. Clicked **rebuild** → `reindex` +
   chained `rag_eval`.
3. The chained `rag_eval` FAILED: `name 'json' is not defined`. Root cause:
   `fieldkit/src/fieldkit/harness/mcp.py` `rag_eval_index()` parses the gold set with
   `json.loads` but the module shipped (since M10) without a module-level `import json`
   — the single `json.` reference in the file. The mock-injected `rag_eval` job tests
   never executed the real tool body.
4. Fixed (one-line `import json`), added a regression test
   (`test_rag_eval_index_parses_gold_jsonl`, infra-free via monkeypatched
   `MemoryIndex`/`resolve_qa_set`), CHANGELOG `[Unreleased]` Fixed entry. Restarted
   the cockpit (editable install picks up the source).
5. Re-drove the loop. Re-index ran `ensure_schema` (added provenance columns,
   stamped all 313 chunks → provenance 313/313), built `idx-50d-313c`. RAG-eval scored
   **chunk-recall@5 0.4091 / slug-recall@5 0.7273** over the 44-question
   `articles/rag-eval-ragas-and-nemo-evaluator/evidence/qa-eval.jsonl` gold set,
   cosine-only (no GB10 reranker; `rerank=True` hard-raises).
6. Second `rag_eval` exercised the promotion gate: `prior=0.4091, delta=0.0,
   promote=true` (first run promotes unconditionally; second defends the baseline).
7. Queried the Second Brain live through the cockpit console ("how does GRPO use the
   eval harness as the reward model on the Spark?") → cited hits from
   `t2po-uncertainty-guided-rl-on-spark`, `clawgym-on-spark-grpo`,
   `a2tgpo-turn-clipping-on-spark`, each tagged `article` provenance.
8. Morning standup: RAN 3 · 0 regressed · 0 failed · 0 queued · spend $0.0000/$5.00 ·
   staged-only (no push path).

Screenshots are the operator-journey captures (same set staged under
`products/local-knowledge-appliance/screenshots/`), re-numbered for article flow.

Measured numbers are byte-matched to the `rag_eval_runs` rows; nothing here is
estimated.
