# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.notebook`.

Dep-free where possible: runtime detection (env-driven), URL/badge builders,
and the `NotebookBuilder` percent renderer are pure-Python. The
OpenAI-compatible client is exercised with `respx` (a dev dep) mocking httpx —
no live server. The in-process llama-cpp path asserts a clean
`NotebookNotAvailable` when the optional dep is missing.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

import fieldkit.notebook as nb
from fieldkit.notebook import (
    GITHUB_REPO,
    NotebookBuilder,
    NotebookNotAvailable,
    OpenAICompatClient,
    _build_llama_server_cmd,
    _find_llama_server,
    badge_markdown,
    colab_url,
    detect_runtime,
    discover_local_server,
    is_cloud,
    kaggle_url,
    notebook_path,
    open_model,
)

# ---------------- runtime detection ----------------------------------------


def test_detect_runtime_env_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIELDKIT_RUNTIME", "colab")
    assert detect_runtime() == "colab"
    monkeypatch.setenv("FIELDKIT_RUNTIME", "Spark")
    assert detect_runtime() == "spark"


def test_detect_runtime_ignores_garbage_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIELDKIT_RUNTIME", "nonsense")
    # Falls through to real detection; on the CI/dev box that's "local".
    assert detect_runtime() in ("spark", "local")


def test_detect_runtime_colab_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIELDKIT_RUNTIME", raising=False)
    monkeypatch.setenv("COLAB_RELEASE_TAG", "release-2026")
    assert detect_runtime() == "colab"


def test_detect_runtime_kaggle_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIELDKIT_RUNTIME", raising=False)
    monkeypatch.delenv("COLAB_RELEASE_TAG", raising=False)
    monkeypatch.setenv("KAGGLE_KERNEL_RUN_TYPE", "Interactive")
    assert detect_runtime() == "kaggle"


def test_is_cloud() -> None:
    assert is_cloud("colab") is True
    assert is_cloud("kaggle") is True
    assert is_cloud("spark") is False
    assert is_cloud("local") is False


# ---------------- URL + badge builders -------------------------------------


def test_notebook_path() -> None:
    assert notebook_path("patent-strategist", "builder") == "notebooks/patent-strategist/builder.ipynb"
    assert notebook_path("finance", "user.ipynb") == "notebooks/finance/user.ipynb"


def test_colab_url_targets_public_github() -> None:
    url = colab_url("notebooks/patent-strategist/user.ipynb")
    assert url == (
        f"https://colab.research.google.com/github/{GITHUB_REPO}/blob/main/"
        "notebooks/patent-strategist/user.ipynb"
    )


def test_kaggle_url_is_import_from_github_form() -> None:
    url = kaggle_url("notebooks/patent-strategist/user.ipynb")
    assert url.startswith("https://kaggle.com/kernels/welcome?src=https://github.com/")
    assert GITHUB_REPO in url


def test_badge_markdown_renders_present_links_only() -> None:
    md = badge_markdown(colab="https://c", kaggle="https://k", label="Use it")
    assert md.startswith("**Use it:** ")
    assert "colab-badge.svg" in md and "(https://c)" in md
    assert "open-in-kaggle.svg" in md and "(https://k)" in md


def test_badge_markdown_empty_when_no_urls() -> None:
    assert badge_markdown(label="x") == ""


# ---------------- OpenAI-compatible client (respx) -------------------------


@respx.mock
def test_openai_compat_client_chat() -> None:
    route = respx.post("http://127.0.0.1:8000/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "claim 1 is anticipated"}}]
        })
    )
    client = OpenAICompatClient("http://127.0.0.1:8000", model="patent-strategist")
    out = client.chat([{"role": "user", "content": "is claim 1 anticipated?"}])
    assert out == "claim 1 is anticipated"
    assert route.called


def test_openai_compat_client_normalizes_endpoint() -> None:
    c = OpenAICompatClient("http://127.0.0.1:8080/", model="m")
    assert c.endpoint == "http://127.0.0.1:8080/v1"
    c2 = OpenAICompatClient("http://127.0.0.1:8080/v1", model="m")
    assert c2.endpoint == "http://127.0.0.1:8080/v1"


@respx.mock
def test_open_model_endpoint_returns_openai_client() -> None:
    client = open_model("Orionfold/patent-strategist-v3-unsloth-GGUF",
                        endpoint="http://127.0.0.1:8000")
    assert isinstance(client, OpenAICompatClient)
    assert client.backend == "openai-compat"
    assert client.model == "Orionfold/patent-strategist-v3-unsloth-GGUF"


def test_open_model_endpoint_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIELDKIT_OPENAI_ENDPOINT", "http://127.0.0.1:9000")
    client = open_model("Orionfold/x-GGUF")
    assert isinstance(client, OpenAICompatClient)
    assert client.endpoint == "http://127.0.0.1:9000/v1"


def test_open_model_inprocess_path_requires_llama_cpp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIELDKIT_OPENAI_ENDPOINT", raising=False)
    pytest.importorskip  # noqa - keep import local
    try:
        import llama_cpp  # type: ignore[import-not-found]  # noqa: F401
        pytest.skip("llama-cpp-python is installed; the missing-dep path can't be exercised")
    except ImportError:
        pass
    with pytest.raises(NotebookNotAvailable):
        open_model("Orionfold/x-GGUF", variant="Q4_K_M", runtime="colab")


# ---------------- P0/P1: reasoning fallback, autodiscovery, local_server ----


@respx.mock
def test_chat_reconstructs_think_block_from_reasoning_content() -> None:
    # Server split the <think> stream into reasoning_content, leaving content
    # empty (default --reasoning-format). chat() must rebuild the think block
    # rather than return "" — what made the patent-strategist notebook blank.
    respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {
                "role": "assistant", "content": "",
                "reasoning_content": "the claim is anticipated by Smith",
            }}]
        })
    )
    client = OpenAICompatClient("http://127.0.0.1:8080", model="m")
    out = client.chat([{"role": "user", "content": "?"}])
    assert out == "<think>the claim is anticipated by Smith</think>"


@respx.mock
def test_chat_keeps_content_when_already_present() -> None:
    # --reasoning-format none path: content already carries <think>...; no-op.
    respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {
                "role": "assistant", "content": "<think>x</think>answer",
                "reasoning_content": "x",
            }}]
        })
    )
    client = OpenAICompatClient("http://127.0.0.1:8080", model="m")
    assert client.chat([{"role": "user", "content": "?"}]) == "<think>x</think>answer"


# ---------------- split_think / display_reply / chat_stream ----------------


def test_split_think_shapes() -> None:
    assert nb.split_think("<think>r</think>a") == ("r", "a")
    # unclosed chain (ran past the token budget): all reasoning, no answer
    assert nb.split_think("<think>still going") == ("still going", "")
    # no think block → straight answer
    assert nb.split_think("just the answer") == ("", "just the answer")
    # empty false-start: pick the longest real block
    assert nb.split_think("<think></think><think>real</think>ans") == ("real", "ans")
    assert nb.split_think("") == ("", "")


def test_display_reply_prints_outside_notebook(capsys: pytest.CaptureFixture) -> None:
    # Not in a kernel → falls back to print, returns None (display side-effect).
    out = nb.display_reply("<think>r</think>the answer")
    assert out is None
    assert "the answer" in capsys.readouterr().out


def _sse(*chunks: dict) -> str:
    import json
    lines = [f"data: {json.dumps({'choices': [{'delta': c}]})}" for c in chunks]
    lines.append("data: [DONE]")
    return "\n\n".join(lines) + "\n\n"


@respx.mock
def test_chat_stream_reconstructs_think_from_reasoning_deltas() -> None:
    # Parsing reasoning-format: reasoning arrives in reasoning_content deltas,
    # then the answer in content deltas. chat_stream wraps the chain in tags.
    body = _sse(
        {"reasoning_content": "think "}, {"reasoning_content": "more"},
        {"content": "ans"}, {"content": "wer"},
    )
    respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=body)
    )
    client = OpenAICompatClient("http://127.0.0.1:8080", model="m")
    chunks = list(client.chat_stream([{"role": "user", "content": "?"}]))
    assert "".join(chunks) == "<think>think more</think>answer"
    assert chunks[0] == "<think>" and "</think>" in chunks


@respx.mock
def test_chat_stream_passthrough_content_with_think_tag() -> None:
    # --reasoning-format none: the <think> tag is already in content deltas.
    body = _sse({"content": "<think>r</think>"}, {"content": "answer"})
    respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=body)
    )
    client = OpenAICompatClient("http://127.0.0.1:8080", model="m")
    assert "".join(client.chat_stream([{"role": "user", "content": "?"}])) == "<think>r</think>answer"


@respx.mock
def test_chat_stream_closes_unclosed_think_at_eos() -> None:
    # Budget hit mid-reasoning: stream ends still inside <think>; we close it.
    body = _sse({"reasoning_content": "still going"})
    respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=body)
    )
    client = OpenAICompatClient("http://127.0.0.1:8080", model="m")
    assert "".join(client.chat_stream([{"role": "user", "content": "?"}])) == "<think>still going</think>"


def test_base_chat_stream_falls_back_to_single_chunk() -> None:
    # A backend that only implements .chat() is still streamable (one chunk).
    class _Stub(nb.ChatClient):
        def chat(self, messages, **kw):  # type: ignore[override]
            return "<think>r</think>a"
    assert list(_Stub().chat_stream([{"role": "user", "content": "?"}])) == ["<think>r</think>a"]


@respx.mock
def test_discover_local_server_returns_first_healthy() -> None:
    respx.get("http://127.0.0.1:8080/health").mock(return_value=httpx.Response(200))
    assert discover_local_server() == "http://127.0.0.1:8080"


@respx.mock
def test_discover_local_server_none_when_unreachable() -> None:
    for base in ("http://127.0.0.1:8080", "http://127.0.0.1:8000"):
        for path in ("/health", "/v1/models"):
            respx.get(base + path).mock(side_effect=httpx.ConnectError("down"))
    assert discover_local_server() is None


@respx.mock
def test_open_model_autodiscovers_on_spark(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIELDKIT_OPENAI_ENDPOINT", raising=False)
    respx.get("http://127.0.0.1:8080/health").mock(return_value=httpx.Response(200))
    client = open_model("Orionfold/x-GGUF", runtime="spark")
    assert isinstance(client, OpenAICompatClient)
    assert client.endpoint == "http://127.0.0.1:8080/v1"


def test_open_model_warns_chat_format_on_endpoint() -> None:
    with pytest.warns(UserWarning, match="ignored on the server path"):
        c = open_model("Orionfold/x-GGUF", endpoint="http://127.0.0.1:8080",
                       chat_format="zephyr")
    assert isinstance(c, OpenAICompatClient)


def test_build_llama_server_cmd_jinja_and_reasoning() -> None:
    cmd = _build_llama_server_cmd(
        "/bin/llama-server", "/m.gguf", host="127.0.0.1", port=8080,
        n_ctx=8192, n_gpu_layers=99, chat_template="jinja", reasoning_format="none")
    assert "--jinja" in cmd and "--chat-template" not in cmd
    assert cmd[cmd.index("--reasoning-format") + 1] == "none"
    assert cmd[cmd.index("-c") + 1] == "8192"
    assert cmd[cmd.index("-ngl") + 1] == "99"


def test_build_llama_server_cmd_named_template() -> None:
    cmd = _build_llama_server_cmd(
        "/bin/llama-server", "/m.gguf", host="0.0.0.0", port=9, n_ctx=4096,
        n_gpu_layers=0, chat_template="zephyr", reasoning_format=None)
    assert cmd[cmd.index("--chat-template") + 1] == "zephyr"
    assert "--jinja" not in cmd and "--reasoning-format" not in cmd


def test_find_llama_server_honors_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "llama-server"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("FIELDKIT_LLAMA_SERVER", str(fake))
    assert _find_llama_server() == str(fake)


def test_find_llama_server_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIELDKIT_LLAMA_SERVER", "/nonexistent/llama-server")
    monkeypatch.setattr(nb.shutil, "which", lambda _: None)
    monkeypatch.setattr(nb, "_KNOWN_LLAMA_SERVER", "/also/nonexistent")
    with pytest.raises(NotebookNotAvailable):
        _find_llama_server()


# ---------------- NotebookBuilder ------------------------------------------


def test_notebook_builder_renders_percent_with_cells() -> None:
    b = NotebookBuilder(vertical="patent-strategist", audience="AI researcher", title="Build it")
    b.parameters_cell({"hf_repo": "Orionfold/patent-strategist-v3-unsloth-GGUF"})
    b.markdown("## Step 1\nWhy we baseline first.")
    b.code("print('hello')")
    out = b.render()
    assert "format_name: percent" in out
    assert "# %% [markdown]" in out
    assert "# %% tags=[\"parameters\"]" in out
    assert "print('hello')" in out
    assert "# ## Step 1" in out  # markdown lines are comment-prefixed
    assert 'hf_repo' in out


def test_notebook_builder_header_banner_is_first_cell() -> None:
    b = NotebookBuilder(vertical="finance", audience="App developer", title="Use it")
    b.parameters_cell()
    b.header_banner(subtitle="Run the finance model in your app")
    out = b.render()
    banner_at = out.index('Orionfold · ai-field-notes')
    params_at = out.index('parameters')
    assert banner_at < params_at, "banner must be inserted as the first cell"
    assert "Use it" in out


def test_notebook_builder_step_enforces_cadence() -> None:
    b = NotebookBuilder(vertical="cyber")
    b.step("Explain why.", "run_it()", "Interpret the result.")
    kinds = [c.kind for c in b.cells]
    assert kinds == ["markdown", "code", "markdown"]


def test_notebook_builder_write_py(tmp_path: Path) -> None:
    b = NotebookBuilder(vertical="legal", title="Build it")
    b.code("x = 1")
    out = b.write_py(tmp_path / "notebooks" / "legal" / "builder.py")
    assert out.exists()
    assert "x = 1" in out.read_text()


def test_notebook_builder_write_ipynb_when_jupytext_available(tmp_path: Path) -> None:
    pytest.importorskip("jupytext")
    b = NotebookBuilder(vertical="legal", title="Build it")
    b.parameters_cell()
    b.markdown("## Heading")
    b.code("x = 1")
    out = b.write_ipynb(tmp_path / "builder.ipynb")
    assert out.exists()
    import json
    doc = json.loads(out.read_text())
    assert doc["cells"], "ipynb should have cells"
