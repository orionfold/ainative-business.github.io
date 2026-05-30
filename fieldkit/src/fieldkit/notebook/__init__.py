# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Dual-path notebook runtime + scaffolding for Orionfold artifact notebooks.

The runtime + authoring spine of the notebooks-as-artifacts pilot
(`specs/notebooks-as-artifacts-v1.md`). Three concerns:

1. **Runtime detection** — `detect_runtime()` returns `"spark" | "colab" |
   "kaggle" | "local"`. The notebook's parameterized first cell branches on it:
   Spark runs the full local fieldkit path; Colab/Kaggle pull the published
   GGUF from HF and run it on the free GPU; hardware-only builder steps render
   recorded outputs behind a banner.

2. **Unified inference** — `open_model(hf_repo, variant=...)` returns a
   `ChatClient` with a single `.chat(messages)` surface regardless of backend
   (OpenAI-compatible endpoint like NIM / `llama-server`, or in-process
   `llama-cpp-python` pulling the GGUF from HF). The use-case cells stay
   backend-agnostic — write `client.chat(...)` once, runs everywhere.

3. **Scaffolding** — URL/badge builders (`colab_url`, `kaggle_url`,
   `badge_markdown`) and a deterministic `NotebookBuilder` that assembles a
   jupytext `py:percent` skeleton from a manifest + article + template. The
   *prose* cells are filled by the session model (the `notebook-author` skill,
   per `feedback_llm_skill_pattern`); `NotebookBuilder` only lays the
   deterministic structure — banner, parameters cell, badge row, and the
   explainer→code→interpretation cell rhythm.

Heavy deps (`llama-cpp-python`, `huggingface_hub`, `jupytext`) are lazy and
optional — they live behind the `fieldkit[notebook]` extra. `httpx` (the
OpenAI-compatible client path) is a core fieldkit dep, so the endpoint path
works without the extra. `import fieldkit.notebook` stays cheap.
"""

from __future__ import annotations

import html
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence, Union

__all__ = [
    "Runtime",
    "detect_runtime",
    "is_cloud",
    "ChatClient",
    "OpenAICompatClient",
    "LlamaCppClient",
    "open_model",
    "split_think",
    "display_reply",
    "stream_reply",
    "discover_local_server",
    "local_server",
    "NotebookNotAvailable",
    "GITHUB_REPO",
    "colab_url",
    "kaggle_url",
    "notebook_path",
    "badge_markdown",
    "NotebookBuilder",
]

# The public GitHub repo Colab/Kaggle import URLs resolve against. Public so
# `colab.research.google.com/github/<repo>/blob/main/...` works without auth.
GITHUB_REPO: str = "manavsehgal/ai-field-notes"

# Standard one-click-notebook badge SVGs (identical to the set
# `fieldkit.publish` inlines for the card badge row).
_COLAB_BADGE_SVG = "https://colab.research.google.com/assets/colab-badge.svg"
_KAGGLE_BADGE_SVG = "https://kaggle.com/static/images/open-in-kaggle.svg"
_HF_BADGE_SVG = "https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg"

Runtime = str
"""One of `"spark" | "colab" | "kaggle" | "local"`. Aliased to `str` so the
notebook param cell can pass a plain string without importing an enum."""


class NotebookNotAvailable(ImportError):
    """An optional `fieldkit[notebook]` dependency is missing for the path you
    called (e.g. `llama-cpp-python` for in-process inference, `jupytext` for
    `.ipynb` generation). Install with `pip install fieldkit[notebook]`."""


# --- runtime detection -----------------------------------------------------


def detect_runtime() -> Runtime:
    """Detect the execution environment: `spark` / `colab` / `kaggle` / `local`.

    Resolution order (first match wins):

    1. `FIELDKIT_RUNTIME` env override — the notebook's parameterized cell sets
       this when the user pins a runtime instead of auto-detecting.
    2. Colab — `google.colab` importable or a `COLAB_*` env marker.
    3. Kaggle — a `KAGGLE_*` env marker or the `/kaggle` mount.
    4. Spark — `aarch64` host whose GPU reports `GB10` (cheap `nvidia-smi`
       name query, best-effort; failures fall through).
    5. `local` — anything else (a dev box; treated like Spark for the
       in-process inference path but without the hardware-only builder steps).
    """
    override = os.environ.get("FIELDKIT_RUNTIME", "").strip().lower()
    if override in ("spark", "colab", "kaggle", "local"):
        return override

    if "google.colab" in sys.modules or any(
        os.environ.get(k) for k in ("COLAB_RELEASE_TAG", "COLAB_GPU", "COLAB_BACKEND_VERSION")
    ):
        return "colab"
    try:
        import google.colab  # type: ignore[import-not-found]  # noqa: F401
        return "colab"
    except ImportError:
        pass

    if any(os.environ.get(k) for k in ("KAGGLE_KERNEL_RUN_TYPE", "KAGGLE_URL_BASE")) or \
            os.path.isdir("/kaggle"):
        return "kaggle"

    if _is_spark():
        return "spark"
    return "local"


def is_cloud(runtime: Optional[Runtime] = None) -> bool:
    """True for Colab / Kaggle — the runtimes that use the cloud-fallback path
    (pull published GGUF → llama-cpp-python) and hide hardware-only builder
    steps behind a recorded-output banner."""
    return (runtime or detect_runtime()) in ("colab", "kaggle")


def _is_spark() -> bool:
    if platform.machine() != "aarch64":
        return False
    smi = shutil.which("nvidia-smi")
    if not smi:
        return False
    try:
        out = subprocess.run(
            [smi, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=4,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "GB10" in out.stdout


# --- unified inference ------------------------------------------------------


class ChatClient:
    """Backend-agnostic chat surface. Subclasses implement `.chat(messages)`.

    `messages` is the OpenAI-style list of `{"role", "content"}` dicts; `.chat`
    returns the assistant's reply text. Reasoning models emit a `<think>...
    </think>` prefix — call `fieldkit.eval`/`split_think` downstream to split
    it, the client returns the raw content."""

    backend: str = "base"
    model: str = ""

    def chat(self, messages: Sequence[dict[str, str]], **kwargs: Any) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def chat_stream(self, messages: Sequence[dict[str, str]], **kwargs: Any) -> Iterator[str]:
        """Yield the assistant reply in text chunks as the model produces it.

        Each chunk is a piece of the full `<think>…</think>answer` reply in
        order — concatenating all chunks equals what `.chat(...)` returns.
        Default implementation falls back to a single non-streamed chunk so any
        backend is usable with `stream_reply`; subclasses override for true
        token-by-token streaming."""
        yield self.chat(messages, **kwargs)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} backend={self.backend!r} model={self.model!r}>"


class OpenAICompatClient(ChatClient):
    """Talk to an OpenAI-compatible `/v1/chat/completions` endpoint — a local
    NIM (`127.0.0.1:8000`) or `llama-server` (`:8080`) on Spark. Uses `httpx`
    (a core fieldkit dep), so this path needs no extra."""

    backend = "openai-compat"

    def __init__(self, endpoint: str, model: str, *, api_key: Optional[str] = None,
                 timeout: float = 120.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        if not self.endpoint.endswith("/v1"):
            self.endpoint += "/v1"
        self.model = model
        self.api_key = api_key or "not-needed"
        self.timeout = timeout

    def chat(self, messages: Sequence[dict[str, str]], *, temperature: float = 0.0,
             max_tokens: int = 2048, **kwargs: Any) -> str:
        import httpx
        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        resp = httpx.post(
            f"{self.endpoint}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        # Reasoning models served with the server's default `--reasoning-format`
        # route the `<think>` stream into a separate `reasoning_content` field,
        # leaving `content` empty when the chain doesn't close within the token
        # budget. The notebooks expect the think block *in* the reply ("read the
        # <think> block"), so reconstruct it rather than return an empty string.
        # (Serving with `--reasoning-format none` keeps it in `content` already —
        # then `reasoning_content` is empty and this is a no-op.)
        reasoning = msg.get("reasoning_content") or ""
        if reasoning and "<think>" not in content:
            content = f"<think>{reasoning}</think>{content}"
        return str(content)

    def chat_stream(self, messages: Sequence[dict[str, str]], *, temperature: float = 0.0,
                    max_tokens: int = 2048, **kwargs: Any) -> Iterator[str]:
        """Stream via SSE (`stream: true`). Reconstructs the `<think>…</think>`
        shape across both server reasoning-formats: `--reasoning-format none`
        delivers the tag in `delta.content`; the parsing formats deliver the
        chain in `delta.reasoning_content` (wrapped here in `<think>…</think>`)."""
        import json as _json

        import httpx
        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        in_think = False  # currently emitting reasoning_content (tag left open)
        with httpx.stream(
            "POST", f"{self.endpoint}/chat/completions", json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"}, timeout=self.timeout,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = _json.loads(data)["choices"][0].get("delta", {})
                except (KeyError, IndexError, ValueError):
                    continue
                rc = delta.get("reasoning_content")
                if rc:
                    if not in_think:
                        in_think = True
                        yield "<think>"
                    yield rc
                piece = delta.get("content")
                if piece:
                    if in_think:
                        in_think = False
                        yield "</think>"
                    yield piece
        if in_think:  # chain never closed within the budget
            yield "</think>"


class LlamaCppClient(ChatClient):
    """In-process `llama-cpp-python`, pulling the GGUF from HF on first use.

    This is the cloud-fallback path (Colab / Kaggle free GPU) and also works on
    Spark / local when no server is running. Lazy-imports `llama_cpp`."""

    backend = "llama-cpp-python"

    def __init__(self, llm: Any, model: str) -> None:
        self._llm = llm
        self.model = model

    @classmethod
    def from_pretrained(
        cls, hf_repo: str, *, variant: Optional[str] = None,
        gguf_file: Optional[str] = None, n_ctx: int = 4096, n_gpu_layers: int = -1,
        chat_format: Optional[str] = None, hf_token: Optional[str] = None,
        verbose: bool = False, **kwargs: Any,
    ) -> "LlamaCppClient":
        try:
            from llama_cpp import Llama  # type: ignore[import-not-found]
        except ImportError as exc:
            raise NotebookNotAvailable(
                "open_model's in-process path needs llama-cpp-python."
                " Install: `pip install fieldkit[notebook]` (or"
                " `pip install llama-cpp-python`)."
            ) from exc
        # Glob match the variant within the repo (filenames vary across repos).
        filename = gguf_file or (f"*{variant}*.gguf" if variant else "*.gguf")
        llm = Llama.from_pretrained(
            repo_id=hf_repo, filename=filename, n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers, chat_format=chat_format,
            verbose=verbose, token=hf_token, **kwargs,
        )
        return cls(llm, model=f"{hf_repo}::{filename}")

    def chat(self, messages: Sequence[dict[str, str]], *, temperature: float = 0.0,
             max_tokens: int = 2048, **kwargs: Any) -> str:
        out = self._llm.create_chat_completion(
            messages=list(messages), temperature=temperature,
            max_tokens=max_tokens, **kwargs,
        )
        return str(out["choices"][0]["message"]["content"])

    def chat_stream(self, messages: Sequence[dict[str, str]], *, temperature: float = 0.0,
                    max_tokens: int = 2048, **kwargs: Any) -> Iterator[str]:
        """Stream from the in-process llama-cpp engine (`stream=True`). The GGUF
        emits its `<think>` tag in `content`, so chunks need no reconstruction."""
        for out in self._llm.create_chat_completion(
            messages=list(messages), temperature=temperature,
            max_tokens=max_tokens, stream=True, **kwargs,
        ):
            piece = out["choices"][0].get("delta", {}).get("content")
            if piece:
                yield piece


# --- reply rendering: split + display the <think> reasoning ----------------

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)

_REASONING_BOX_CSS = (
    "border:1px solid #2A2F3A;border-left:3px solid #76B900;border-radius:10px;"
    "background:#0E1116;color:#9AA3AF;padding:0.75rem 1rem;margin:0.25rem 0 0.75rem;"
    "font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.82rem;"
    "line-height:1.55;white-space:pre-wrap;overflow-x:auto"
)


def split_think(reply: str) -> tuple[str, str]:
    """Split a reasoning-model reply into `(reasoning, answer)`.

    Three shapes a served reply takes:
      - closed `<think>…</think>answer` → `(reasoning, answer)`
      - an unclosed `<think>…` (chain ran past the token budget) → everything
        after the opener is reasoning, answer is `""`
      - no think block → `("", reply)`
    Picks the longest closed block when several are present (R1-distill models
    sometimes false-start with an empty `<think></think>`)."""
    if not reply:
        return "", ""
    matches = _THINK_RE.findall(reply)
    if matches:
        return max(matches, key=len).strip(), _THINK_RE.sub("", reply).strip()
    if "<think>" in reply:  # unclosed chain (hit the token budget mid-think)
        return reply.split("<think>", 1)[1].strip(), ""
    return "", reply.strip()


def _in_notebook() -> bool:
    """True inside a Jupyter/IPython kernel with rich display (not a plain REPL
    or a `python script.py` run) — gates whether to render HTML or just print."""
    try:
        from IPython import get_ipython  # type: ignore[import-not-found]
        ip = get_ipython()
        return ip is not None and getattr(ip, "has_trait", lambda *_: False)("kernel")
    except Exception:
        return False


def _reasoning_box_html(reasoning: str, *, label: str = "💭 Reasoning") -> str:
    return (
        f'<div style="{_REASONING_BOX_CSS}">'
        f'<div style="color:#5B9CFF;font-size:0.72rem;letter-spacing:0.06em;'
        f'text-transform:uppercase;margin-bottom:0.4rem">{html.escape(label)}</div>'
        f'{html.escape(reasoning)}</div>'
    )


_NO_ANSWER_NOTE = (
    "_(no answer text yet — the reasoning chain may have run past the token "
    "budget; raise `max_tokens`.)_"
)


def display_reply(reply: str, *, reasoning_label: str = "💭 Reasoning") -> None:
    """Render a chat reply in a notebook cell: an always-visible muted box for
    the `<think>` reasoning (when present) above the answer rendered as Markdown.

    Outside a Jupyter kernel (or if IPython is absent) this prints the raw reply.
    Returns `None` (a display side-effect) so a cell ending in `display_reply(r)`
    renders cleanly without echoing the raw string."""
    reasoning, answer = split_think(reply)
    if not _in_notebook():
        print(reply)
        return
    from IPython.display import HTML, Markdown, display  # type: ignore[import-not-found]
    if reasoning:
        display(HTML(_reasoning_box_html(reasoning, label=reasoning_label)))
    display(Markdown(answer or _NO_ANSWER_NOTE))


def stream_reply(client: "ChatClient", messages: Sequence[dict[str, str]], *,
                 reasoning_label: str = "💭 Reasoning", **kwargs: Any) -> str:
    """Stream `client.chat_stream(messages)` into the current cell live — the
    reasoning box fills as the model thinks, then the answer renders as Markdown
    below — and return the full reply string.

    Opt-in: the notebooks call `.chat` + `display_reply` by default (clean,
    deterministic re-runs/snapshots); reach for this for a live demo. Outside a
    notebook it streams to stdout."""
    if not _in_notebook():
        acc: list[str] = []
        for piece in client.chat_stream(messages, **kwargs):
            acc.append(piece)
            sys.stdout.write(piece)
            sys.stdout.flush()
        sys.stdout.write("\n")
        return "".join(acc)

    from IPython.display import HTML, Markdown, display, update_display  # type: ignore[import-not-found]
    handle = display(HTML('<div style="color:#5B9CFF">…</div>'), display_id=True)
    acc = []
    last = 0.0
    for piece in client.chat_stream(messages, **kwargs):
        acc.append(piece)
        now = time.time()
        if now - last < 0.08:  # throttle re-renders so the cell doesn't thrash
            continue
        last = now
        reasoning, answer = split_think("".join(acc))
        parts = []
        if reasoning:
            parts.append(_reasoning_box_html(reasoning, label=reasoning_label))
        if answer:
            parts.append(f'<div style="white-space:pre-wrap">{html.escape(answer)}</div>')
        update_display(HTML("".join(parts) or '<div style="color:#5B9CFF">…</div>'),
                       display_id=handle.display_id)
    full = "".join(acc)
    reasoning, answer = split_think(full)
    # settle: final reasoning box in the handle, answer re-rendered as Markdown
    update_display(HTML(_reasoning_box_html(reasoning, label=reasoning_label) if reasoning else ""),
                   display_id=handle.display_id)
    if answer:
        display(Markdown(answer))
    return full


# Cloud free-GPU envelope is tighter than Spark's 128 GB unified memory — pick
# the smallest quality-respecting variant by default so it fits a T4/P100.
_CLOUD_DEFAULT_VARIANT = "Q4_K_M"
_SPARK_DEFAULT_VARIANT = "Q5_K_M"

# Local OpenAI-compatible servers we autodiscover on Spark, in priority order:
# llama-server (`:8080`) then NIM (`:8000`). `local_server` starts the former.
_LOCAL_SERVER_CANDIDATES = ("http://127.0.0.1:8080", "http://127.0.0.1:8000")


def _warn_chat_format_ignored(chat_format: Optional[str]) -> None:
    if chat_format:
        warnings.warn(
            f"chat_format={chat_format!r} is ignored on the server path — the "
            "NIM / llama-server owns the chat template. Start the server with "
            "the matching `--chat-template` (or `--jinja` for the GGUF's own "
            "template) instead.",
            stacklevel=3,
        )


def discover_local_server(
    candidates: Optional[Sequence[str]] = None, *, timeout: float = 0.5,
) -> Optional[str]:
    """Return the base URL of a reachable local OpenAI-compatible server, or
    `None`. Probes each candidate's `/health` (then `/v1/models`) with a short
    timeout — used by `open_model` on Spark to prefer a running `llama-server`
    / NIM over the in-process path (which needs the aarch64-unavailable
    `llama-cpp-python`)."""
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx is a core dep
        return None
    for base in (candidates or _LOCAL_SERVER_CANDIDATES):
        base = base.rstrip("/")
        for path in ("/health", "/v1/models"):
            try:
                if httpx.get(base + path, timeout=timeout).status_code == 200:
                    return base
            except Exception:
                continue
    return None


def open_model(
    hf_repo: str, variant: Optional[str] = None, *, runtime: Optional[Runtime] = None,
    endpoint: Optional[str] = None, model: Optional[str] = None,
    gguf_file: Optional[str] = None, chat_format: Optional[str] = None,
    n_ctx: int = 4096, n_gpu_layers: int = -1, hf_token: Optional[str] = None,
    api_key: Optional[str] = None, autodiscover: Optional[bool] = None,
    **llama_kwargs: Any,
) -> ChatClient:
    """Open a `ChatClient` for `hf_repo`, choosing the backend by runtime.

    Resolution order:

    1. **`endpoint` given** (or `FIELDKIT_OPENAI_ENDPOINT` env) → an
       `OpenAICompatClient` against that NIM / `llama-server`. `model` defaults
       to `hf_repo`.
    2. **autodiscovered local server** — on Spark (default; `autodiscover=True`
       forces, `False` skips) probe `127.0.0.1:8080` (llama-server) and `:8000`
       (NIM) for a `/health`; if one answers, use it. The in-process path needs
       `llama-cpp-python`, which has no aarch64 wheel, so a running server is the
       working Spark path — use `local_server` to start one.
    3. **in-process** → `LlamaCppClient.from_pretrained(...)` pulling the GGUF
       from HF. Default `variant` is `Q4_K_M` on cloud (fits a free GPU),
       `Q5_K_M` on Spark/local.

    `chat_format` applies only to the in-process backend; on a server path the
    server owns the chat template, so passing it there warns and is ignored.

    A single `.chat(messages)` works against whichever backend you get back.
    """
    rt = runtime or detect_runtime()
    endpoint = endpoint or os.environ.get("FIELDKIT_OPENAI_ENDPOINT")
    if endpoint:
        _warn_chat_format_ignored(chat_format)
        return OpenAICompatClient(endpoint, model or hf_repo, api_key=api_key)
    if autodiscover is None:
        autodiscover = rt == "spark"
    if autodiscover:
        found = discover_local_server()
        if found:
            print(f"fieldkit: using local server at {found} "
                  f"(autodiscovered; pass autodiscover=False for in-process)")
            _warn_chat_format_ignored(chat_format)
            return OpenAICompatClient(found, model or hf_repo, api_key=api_key)
    if variant is None:
        variant = _CLOUD_DEFAULT_VARIANT if rt in ("colab", "kaggle") else _SPARK_DEFAULT_VARIANT
    return LlamaCppClient.from_pretrained(
        hf_repo, variant=variant, gguf_file=gguf_file, n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers, chat_format=chat_format, hf_token=hf_token,
        **llama_kwargs,
    )


# --- local llama-server lifecycle (Spark) -----------------------------------

# Known-good CUDA llama-server build on the Spark; overridable via env / arg.
_KNOWN_LLAMA_SERVER = "/home/nvidia/llama.cpp/build/bin/llama-server"


def _find_llama_server(server_bin: Optional[str] = None) -> str:
    """Locate a `llama-server` binary: explicit arg → `FIELDKIT_LLAMA_SERVER`
    env → `PATH` → the known Spark build path."""
    for cand in (server_bin, os.environ.get("FIELDKIT_LLAMA_SERVER"),
                 shutil.which("llama-server"), _KNOWN_LLAMA_SERVER):
        if cand and Path(cand).exists():
            return cand
    raise NotebookNotAvailable(
        "llama-server binary not found. Build llama.cpp, put `llama-server` on "
        "PATH, or set FIELDKIT_LLAMA_SERVER=/path/to/llama-server."
    )


def _resolve_gguf(hf_repo: str, *, variant: Optional[str] = None,
                  gguf_file: Optional[str] = None,
                  hf_token: Optional[str] = None) -> str:
    """Download (cached) and return a local path to a GGUF for `hf_repo` —
    `gguf_file` exactly, else the shortest filename globbing `*{variant}*.gguf`."""
    try:
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError as exc:
        raise NotebookNotAvailable(
            "local_server's GGUF resolve needs huggingface_hub "
            "(`pip install fieldkit[notebook]`)."
        ) from exc
    filename = gguf_file
    if filename is None:
        ggufs = [f for f in list_repo_files(hf_repo, token=hf_token) if f.endswith(".gguf")]
        if variant:
            ggufs = [f for f in ggufs if variant in f] or ggufs
        if not ggufs:
            raise NotebookNotAvailable(f"no .gguf files found in {hf_repo}")
        filename = sorted(ggufs, key=len)[0]
    return hf_hub_download(repo_id=hf_repo, filename=filename, token=hf_token)


def _build_llama_server_cmd(
    server_bin: str, gguf_path: str, *, host: str, port: int, n_ctx: int,
    n_gpu_layers: int, chat_template: Optional[str], reasoning_format: Optional[str],
) -> list[str]:
    """Assemble the `llama-server` argv. `chat_template` of `"jinja"`/`"auto"`/
    `None` uses the GGUF's embedded template (`--jinja`); any other value is
    passed as a named `--chat-template`. `reasoning_format="none"` keeps the raw
    `<think>` block in the OpenAI `content` field (else a reasoning model splits
    it into `reasoning_content` and returns empty `content`)."""
    cmd = [server_bin, "-m", gguf_path, "--host", host, "--port", str(port),
           "-ngl", str(n_gpu_layers), "-c", str(n_ctx)]
    if chat_template in (None, "jinja", "auto"):
        cmd.append("--jinja")
    else:
        cmd += ["--chat-template", chat_template]
    if reasoning_format:
        cmd += ["--reasoning-format", reasoning_format]
    return cmd


@contextmanager
def local_server(
    hf_repo: str, *, variant: str = _SPARK_DEFAULT_VARIANT,
    gguf_file: Optional[str] = None, n_ctx: int = 8192, n_gpu_layers: int = 99,
    chat_template: Optional[str] = "jinja", reasoning_format: Optional[str] = "none",
    host: str = "127.0.0.1", port: int = 8080, server_bin: Optional[str] = None,
    hf_token: Optional[str] = None, startup_timeout: float = 180.0,
    log_path: Optional[Union[str, Path]] = None,
) -> Iterator[str]:
    """Serve `hf_repo`'s GGUF on a local `llama-server` for the `with` block,
    yielding the endpoint URL. Resolves+downloads the GGUF, GPU-offloads
    (`-ngl 99`), waits for `/health`, and tears the server down on exit — the
    OOM-safe "one model at a time" pattern. Pair with `open_model`:

        with local_server("Orionfold/patent-strategist-v3-unsloth-GGUF") as ep:
            client = open_model(hf_repo, endpoint=ep)
            client.chat(messages)
    """
    import httpx
    server = _find_llama_server(server_bin)
    gguf_path = _resolve_gguf(hf_repo, variant=variant, gguf_file=gguf_file, hf_token=hf_token)
    cmd = _build_llama_server_cmd(
        server, gguf_path, host=host, port=port, n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers, chat_template=chat_template,
        reasoning_format=reasoning_format,
    )
    endpoint = f"http://{host}:{port}"
    log = open(log_path, "w") if log_path else subprocess.DEVNULL
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + startup_timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                raise NotebookNotAvailable(
                    f"llama-server exited (code {proc.returncode}) during startup"
                    + (f"; see {log_path}" if log_path else "")
                )
            try:
                if httpx.get(endpoint + "/health", timeout=1.0).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(1.0)
        else:
            raise NotebookNotAvailable(
                f"llama-server did not become healthy within {startup_timeout:.0f}s"
            )
        yield endpoint
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if hasattr(log, "close"):
            log.close()


# --- URL + badge builders ---------------------------------------------------


def notebook_path(vertical: str, which: str = "builder") -> str:
    """Repo-relative path to a vertical's notebook, e.g.
    `notebooks/patent-strategist/builder.ipynb`."""
    stem = which if which.endswith(".ipynb") else f"{which}.ipynb"
    return f"notebooks/{vertical}/{stem}"


def colab_url(path: str, *, repo: str = GITHUB_REPO, branch: str = "main") -> str:
    """Open-in-Colab URL for a committed `.ipynb` at `path` (repo-relative).
    Colab imports straight from the public GitHub repo on `branch`."""
    return f"https://colab.research.google.com/github/{repo}/blob/{branch}/{path.lstrip('/')}"


def kaggle_url(path: str, *, repo: str = GITHUB_REPO, branch: str = "main") -> str:
    """Open-in-Kaggle URL — the import-from-GitHub-URL form (pilot uses this;
    native kernels are deferred per spec §14)."""
    raw = f"https://github.com/{repo}/blob/{branch}/{path.lstrip('/')}"
    return f"https://kaggle.com/kernels/welcome?src={raw}"


def badge_markdown(*, colab: Optional[str] = None, kaggle: Optional[str] = None,
                   hf: Optional[str] = None, label: Optional[str] = None) -> str:
    """One markdown line of badge links (Colab / Kaggle / HF), in that order,
    with an optional bold `label:` prefix. Mirrors the badge row
    `fieldkit.publish` renders under the card one-liner. Entries with no URL are
    skipped; returns `""` when nothing is passed."""
    badges: list[str] = []
    if colab:
        badges.append(f"[![Open In Colab]({_COLAB_BADGE_SVG})]({colab})")
    if kaggle:
        badges.append(f"[![Open in Kaggle]({_KAGGLE_BADGE_SVG})]({kaggle})")
    if hf:
        badges.append(f"[![Hugging Face]({_HF_BADGE_SVG})]({hf})")
    if not badges:
        return ""
    prefix = f"**{label}:** " if label else ""
    return prefix + " ".join(badges)


# --- scaffolding ------------------------------------------------------------


@dataclass
class _Cell:
    kind: str  # "markdown" | "code"
    content: str
    tags: tuple[str, ...] = ()


@dataclass
class NotebookBuilder:
    """Assemble a jupytext `py:percent` notebook scaffold cell-by-cell.

    Deterministic structure only — the `notebook-author` skill (the session
    model) fills the prose. Use `header_banner` / `parameters_cell` /
    `badge_row` for the standard top-of-notebook cells, then `markdown` / `code`
    / `step` for body cells, then `render()` for the `.py` percent text (the
    reviewable source of truth) or `write_py` / `write_ipynb` to disk.

    The `step(explainer, code, interpretation)` helper enforces the validated
    cadence from spec §4.3: every code cell is *preceded* by a why-explainer and
    *followed* by an interpretation. `notebook-snapshot`/`notebook-author`
    validators check this rhythm; building via `step` makes it automatic.
    """

    vertical: str
    audience: str = ""
    title: str = ""
    cells: list[_Cell] = field(default_factory=list)

    # -- cell adders --
    def markdown(self, text: str, *, tags: Sequence[str] = ()) -> "NotebookBuilder":
        self.cells.append(_Cell("markdown", text.rstrip(), tuple(tags)))
        return self

    def code(self, code: str, *, tags: Sequence[str] = ()) -> "NotebookBuilder":
        self.cells.append(_Cell("code", code.rstrip(), tuple(tags)))
        return self

    def step(self, explainer: str, code: str, interpretation: str = "",
             *, tags: Sequence[str] = ()) -> "NotebookBuilder":
        """Add an explainer→code→interpretation triad (spec §4.3 cadence)."""
        self.markdown(explainer)
        self.code(code, tags=tags)
        if interpretation:
            self.markdown(interpretation)
        return self

    def header_banner(self, *, badges: str = "", subtitle: str = "") -> "NotebookBuilder":
        """A branded HTML banner markdown cell (ainative dark palette) carrying
        title, audience tag, optional subtitle, and a badge row."""
        html = _banner_html(self.title or self.vertical, self.audience, subtitle, badges)
        self.cells.insert(0, _Cell("markdown", html, ("banner",)))
        return self

    def badge_row(self, *, colab: Optional[str] = None, kaggle: Optional[str] = None,
                  hf: Optional[str] = None, label: Optional[str] = None) -> "NotebookBuilder":
        line = badge_markdown(colab=colab, kaggle=kaggle, hf=hf, label=label)
        if line:
            self.markdown(line, tags=["badges"])
        return self

    def parameters_cell(self, params: Optional[dict[str, Any]] = None) -> "NotebookBuilder":
        """The papermill `parameters`-tagged first code cell. Defaults set up
        runtime auto-detection + the sibling HF repo."""
        params = params or {}
        lines = ["# Parameters — overridable by papermill / Colab form.",
                 'runtime = "auto"  # "auto" | "spark" | "colab" | "kaggle" | "local"']
        for k, v in params.items():
            lines.append(f"{k} = {v!r}")
        lines += [
            "",
            "import os",
            'if runtime != "auto":',
            '    os.environ["FIELDKIT_RUNTIME"] = runtime',
            "from fieldkit.notebook import detect_runtime",
            "RUNTIME = detect_runtime()",
            'print(f"runtime: {RUNTIME}")',
        ]
        self.code("\n".join(lines), tags=["parameters"])
        return self

    # -- rendering --
    def render(self) -> str:
        """Render the cells to jupytext `py:percent` text."""
        out: list[str] = [
            "# ---",
            "# jupyter:",
            "#   jupytext:",
            "#     text_representation:",
            "#       extension: .py",
            "#       format_name: percent",
            "#   kernelspec:",
            "#     display_name: Python 3",
            "#     name: python3",
            "# ---",
            "",
        ]
        for cell in self.cells:
            tag_suffix = ""
            if cell.tags:
                tag_suffix = ' tags=["' + '", "'.join(cell.tags) + '"]'
            if cell.kind == "markdown":
                out.append(f"# %% [markdown]{tag_suffix}")
                for line in cell.content.splitlines() or [""]:
                    out.append(f"# {line}" if line else "#")
            else:
                out.append(f"# %%{tag_suffix}")
                out.append(cell.content)
            out.append("")
        return "\n".join(out).rstrip() + "\n"

    def write_py(self, path: Union[str, Path]) -> Path:
        """Write the `.py` percent source (the reviewable source of truth)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.render(), encoding="utf-8")
        return out

    def write_ipynb(self, path: Union[str, Path]) -> Path:
        """Convert + write the paired `.ipynb` (what Colab opens). Lazy-imports
        jupytext."""
        try:
            import jupytext  # type: ignore[import-not-found]
        except ImportError as exc:
            raise NotebookNotAvailable(
                "write_ipynb needs jupytext. Install: `pip install fieldkit[notebook]`."
            ) from exc
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        nb = jupytext.reads(self.render(), fmt="py:percent")
        jupytext.write(nb, str(out), fmt="ipynb")
        return out


def _banner_html(title: str, audience: str, subtitle: str, badges: str) -> str:
    """Brand banner as a single-line-safe HTML block. No blank lines inside —
    markdown breaks out of an HTML block on a blank line (see
    `feedback_fn_diagram_no_blank_lines`); the badge row, which must render as
    markdown, is emitted as a separate cell by `badge_row`, not embedded here."""
    aud = f'<div style="color:#9AA3AF;font-size:0.95rem;margin-top:0.35rem">{audience}</div>' if audience else ""
    sub = f'<div style="color:#C2C9D4;margin-top:0.5rem">{subtitle}</div>' if subtitle else ""
    bdg = f'<div style="margin-top:0.75rem">{badges}</div>' if badges else ""
    return (
        '<div style="background:#0E1116;border:1px solid #2A2F3A;border-radius:14px;'
        'padding:1.5rem 1.75rem;font-family:Geist,Inter,sans-serif">'
        f'<div style="color:#5B9CFF;font-size:0.8rem;letter-spacing:0.08em;'
        f'text-transform:uppercase">Orionfold · ai-field-notes</div>'
        f'<div style="color:#E6E9EE;font-size:1.6rem;font-weight:700;margin-top:0.4rem">{title}</div>'
        f'{aud}{sub}{bdg}'
        '</div>'
    )
