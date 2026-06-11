# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Server-side plumbing for the grounded eval bench (grounded-eval-v1 §5/§8):
``_resolve_eval_prompt`` must mark live-retrieval rows (so the chat/compare
handlers build the packet through the live Cortex stack and force retrieval),
and the in-memory turn→receipt map must stay bounded."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fieldkit.arena import benches
from fieldkit.arena import server as arena_server


@pytest.fixture
def grounded_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "grounded-eval"
    root.mkdir(parents=True)
    rows = [
        {
            "task_id": "cg-lookup-0001", "version": "v0.1", "journey": "lookup",
            "question": "Which model shape won the serving bakeoff?",
            "expected_behavior": "answer",
            "gold_source_ids": ["article_bakeoff"],
            "accepted_citation_ids": ["article_bakeoff"],
            "require_all_citations": False,
            "key_facts": [{"kind": "contains", "value": "8.5×", "alt": ["8.5x"]}],
            "expected_answer": "The MoE, by ~8.5×.",
            "in_sft_corpus": True,
        }
    ]
    (root / "cortex-grounded-v0.1.draft.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n"
    )
    monkeypatch.setenv("FK_ARENA_GROUNDED_DIR", str(root))
    benches._CACHE.clear()
    yield root
    benches._CACHE.clear()


def test_resolve_eval_prompt_marks_live_retrieval(grounded_root: Path) -> None:
    body = SimpleNamespace(
        bench_id="cortex-grounded",
        eval_qid="cg-lookup-0001",
        # the composer sends the (prefilled) question text, like the client
        prompt="Which model shape won the serving bakeoff?",
    )
    model_prompt, eval_context, eval_system, eval_kwargs = (
        arena_server._resolve_eval_prompt(body)
    )
    # The bare question — the packet is live-built by the handler, never here.
    assert model_prompt == "Which model shape won the serving bakeoff?"
    assert eval_context["live_retrieval"] is True
    assert eval_context["gold_source_ids"] == ["article_bakeoff"]
    assert eval_context["journey"] == "lookup"
    assert eval_context["reasoning_mode"] == "off"
    # No frozen system contract on the row (the live packet carries it)…
    assert eval_system is None
    # …but the measured reasoning-off rider still applies on local lanes.
    assert eval_kwargs == {"chat_template_kwargs": {"enable_thinking": False}}


def test_resolve_eval_prompt_untouched_for_packet_benches(grounded_root: Path) -> None:
    """Non-grounded paths keep their shape — no live_retrieval key leaks into
    other benches' eval context."""
    body = SimpleNamespace(bench_id="does-not-exist", eval_qid="x", prompt="")
    assert arena_server._resolve_eval_prompt(body) == (None, None, None, None)


def test_retrieval_receipt_map_is_bounded() -> None:
    arena_server._GROUNDED_RECEIPTS.clear()
    cap = arena_server._GROUNDED_RECEIPTS_CAP
    for i in range(cap + 10):
        arena_server._remember_retrieval_receipt(i, {"sources": [], "n": i})
    assert len(arena_server._GROUNDED_RECEIPTS) == cap
    # Oldest entries evicted first; the newest survive.
    assert 0 not in arena_server._GROUNDED_RECEIPTS
    assert (cap + 9) in arena_server._GROUNDED_RECEIPTS
    arena_server._GROUNDED_RECEIPTS.clear()
