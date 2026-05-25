---
module: notebook
title: fieldkit.notebook
summary: Dual-path notebook runtime + scaffolding for Orionfold artifact notebooks. `detect_runtime()` branches Spark (full local fieldkit path) vs Colab/Kaggle (pull published GGUF → llama-cpp-python on the free GPU); `open_model(hf_repo, variant=...)` returns a backend-agnostic `ChatClient` with one `.chat()` surface; URL/badge builders + a deterministic `NotebookBuilder` lay the jupytext py:percent skeleton the notebook-author skill fills with prose. Lazy + optional — behind the `fieldkit[notebook]` extra.
order: 11
---

## What it is

The runtime + authoring spine of the notebooks-as-artifacts pilot (`specs/notebooks-as-artifacts-v1.md`). A vertical's two notebooks — a builder notebook for the AI engineer and a user notebook for the app developer — must run unchanged on a DGX Spark *and* on a free Colab/Kaggle GPU. This module is what makes one notebook source serve both: detect the runtime, open a model behind a uniform chat surface, and scaffold the cells deterministically so the session model only writes prose.

Three concerns:

1. **Runtime detection.** `detect_runtime()` → `"spark" | "colab" | "kaggle" | "local"`. The notebook's parameterized first cell branches on it: Spark runs the full local path (quantize, train, thermal probe live); Colab/Kaggle pull the published GGUF from HF and run it on the free GPU; hardware-only builder steps render recorded outputs behind a "Spark-only — showing recorded run" banner instead of erroring.
2. **Unified inference.** `open_model(...)` returns a `ChatClient` whose `.chat(messages)` works the same against an OpenAI-compatible endpoint (a local NIM / `llama-server`) or in-process `llama-cpp-python`. The use-case cells stay backend-agnostic.
3. **Scaffolding.** `colab_url` / `kaggle_url` / `badge_markdown` build the one-click links and the badge row; `NotebookBuilder` assembles the jupytext `py:percent` skeleton. Per `feedback_llm_skill_pattern`, the *prose* cells are filled by the session model (the `notebook-author` skill) — `NotebookBuilder` only lays the deterministic structure.

Heavy deps (`llama-cpp-python`, `huggingface_hub`, `jupytext`) are lazy + optional (`fieldkit[notebook]`). `httpx` (the endpoint client path) is a core dep, so the OpenAI-compatible path works without the extra.

## Public API

```python
from fieldkit.notebook import (
    detect_runtime, is_cloud, Runtime,           # runtime
    open_model, ChatClient, OpenAICompatClient, LlamaCppClient,  # inference
    split_think, display_reply, stream_reply,    # reply rendering
    discover_local_server, local_server,         # local server (Spark)
    colab_url, kaggle_url, notebook_path, badge_markdown, GITHUB_REPO,  # links
    NotebookBuilder, NotebookNotAvailable,       # scaffold
)
```

### `detect_runtime() -> Runtime`

Resolution order (first wins): `FIELDKIT_RUNTIME` env override → Colab (`google.colab` importable / `COLAB_*` env) → Kaggle (`KAGGLE_*` env or `/kaggle` mount) → Spark (`aarch64` host whose `nvidia-smi` reports `GB10`) → `local`. `is_cloud(runtime=None)` is True for Colab/Kaggle — the runtimes that use the cloud-fallback path and hide hardware-only steps.

### `open_model(hf_repo, variant=None, *, runtime=None, endpoint=None, autodiscover=None, ...) -> ChatClient`

Resolution order:

1. **`endpoint` given** (or `FIELDKIT_OPENAI_ENDPOINT` env) → an `OpenAICompatClient` against that NIM / `llama-server`; `model` defaults to `hf_repo`.
2. **autodiscovered local server** — on Spark (default; `autodiscover=True` forces, `False` skips) probe `127.0.0.1:8080` (llama-server) then `:8000` (NIM) for a `/health`; use the first that answers. The in-process path needs `llama-cpp-python`, which has **no aarch64 wheel**, so a running server is the working Spark path — start one with `local_server`.
3. **in-process** → `LlamaCppClient.from_pretrained(...)`, pulling the GGUF from HF. Default `variant` is `Q4_K_M` on cloud runtimes (fits a free GPU), `Q5_K_M` on Spark/local.

```python
from fieldkit.notebook import open_model
client = open_model("Orionfold/patent-strategist-v3-unsloth-GGUF")   # backend chosen by runtime
reply = client.chat([{"role": "user", "content": "Is claim 1 anticipated by D1?"}])
```

`ChatClient.chat(messages, *, temperature=0.0, max_tokens=2048, **kw)` returns the assistant reply text. Reasoning models emit a `<think>…</think>` prefix — the client returns it raw; split downstream. **`OpenAICompatClient` reconstructs the think block** when the server's `--reasoning-format` routes it into a separate `reasoning_content` field (which would otherwise leave `content` empty for a reasoning model) — so a reply is never silently blank regardless of how the server is configured. It uses `httpx` (and takes an `api_key`); `LlamaCppClient` wraps `llama_cpp.Llama` and lazy-imports it (raising `NotebookNotAvailable` with an install hint if absent).

**Inference keyword arguments.** `open_model` (and `LlamaCppClient.from_pretrained`) forward the llama.cpp load knobs: `gguf_file` (explicit filename, overriding the variant glob), `n_ctx` (context length), `n_gpu_layers` (`-1` = offload all), `chat_format` (e.g. `chatml`), `verbose`, and `hf_token` for gated repos. `api_key` is the OpenAI-compatible-endpoint bearer token. **`chat_format` applies only to the in-process backend** — on a server path the server owns the chat template, so passing it to a server-backed `open_model` warns and is ignored (start the server with the matching `--chat-template` / `--jinja` instead).

### `split_think(reply) -> (reasoning, answer)`, `display_reply(reply)`, `stream_reply(client, messages)`

A reasoning model's reply is `<think>…</think>answer`. These render it for a notebook cell instead of dumping the raw tagged blob.

- **`split_think(reply)`** — pure function returning `(reasoning, answer)`. Handles a closed block, an **unclosed** `<think>…` (the chain ran past `max_tokens` → all reasoning, empty answer), and no-think (`("", reply)`); picks the longest block when an R1-distill false-starts with an empty `<think></think>`.
- **`display_reply(reply, *, reasoning_label="💭 Reasoning")`** — in a Jupyter kernel, renders the reasoning in an always-visible muted box (brand palette, NeMo-green rule) above the answer rendered as **Markdown**; outside a kernel it prints the raw reply. Returns `None` (a display side-effect, so a cell ending in `display_reply(r)` doesn't echo the raw string). This is the default the notebooks use (`display_reply(client.chat(...))`) — deterministic for re-runs and snapshots.

```python
from fieldkit.notebook import display_reply
display_reply(client.chat(messages, max_tokens=3000))   # reasoning box + markdown answer
```

- **`stream_reply(client, messages, **kw)`** — opt-in live streaming: drives `client.chat_stream(...)`, filling the reasoning box token-by-token then the answer, and returns the full reply string (streams to stdout outside a kernel). Every `ChatClient` has **`chat_stream(messages, **kw) -> Iterator[str]`** yielding the reply in order; `OpenAICompatClient` parses SSE and reconstructs the `<think>…</think>` shape across both server reasoning-formats (tag-in-`content` vs. `reasoning_content` deltas), `LlamaCppClient` streams the in-process engine, and the base falls back to one chunk so any backend works.

### `local_server(hf_repo, *, variant="Q5_K_M", n_ctx=8192, chat_template="jinja", reasoning_format="none", ...)` and `discover_local_server(...)`

`local_server` is a context manager that serves `hf_repo`'s GGUF on a local `llama-server` for the `with` block, yielding the endpoint URL: it resolves+downloads the GGUF (cached), GPU-offloads (`-ngl 99`), waits for `/health`, and **tears the server down on exit** — the OOM-safe "one model at a time" pattern. The binary is found via `server_bin=` → `FIELDKIT_LLAMA_SERVER` env → `PATH` → the known Spark build. `reasoning_format="none"` (default) keeps the raw `<think>` block in `content`; `chat_template="jinja"` uses the GGUF's embedded template (pass a named template like `"zephyr"` to override). It binds `host`/`port` (default `127.0.0.1:8080`, the first endpoint `open_model` autodiscovers), gives up after `startup_timeout` seconds waiting for `/health` (default 180), and tees the server's stdout/stderr to `log_path` when set (otherwise discarded).

```python
from fieldkit.notebook import local_server, open_model
with local_server("Orionfold/patent-strategist-v3-unsloth-GGUF", n_ctx=8192) as ep:
    client = open_model(hf_repo, endpoint=ep)
    print(client.chat([{"role": "user", "content": "Construe the Markush limitation."}]))
# server is stopped here
```

`discover_local_server(candidates=None, *, timeout=0.5)` returns the base URL of a reachable local server (probing `/health` then `/v1/models`) or `None` — the probe `open_model` uses for autodiscovery on Spark.

### Link + badge builders

| Function | Returns |
|---|---|
| `notebook_path(vertical, which="builder")` | `notebooks/<vertical>/<which>.ipynb` |
| `colab_url(path, *, repo=GITHUB_REPO, branch="main")` | `colab.research.google.com/github/<repo>/blob/<branch>/<path>` |
| `kaggle_url(path, ...)` | Kaggle import-from-GitHub URL (native kernels deferred, spec §14) |
| `badge_markdown(*, colab=, kaggle=, hf=, label=)` | one markdown line of badge links; empty string if no URLs |

`GITHUB_REPO` is `manavsehgal/ai-field-notes` (public, so the import URLs resolve without auth).

### `NotebookBuilder`

Assemble a jupytext `py:percent` notebook scaffold cell-by-cell. Deterministic structure only. Chainable adders: `markdown` / `code` / `step(explainer, code, interpretation)` (the spec §4.3 explainer→code→interpretation cadence), each accepting `tags` (cell tags like `parameters` / `banner` / `badges` carried into the `.ipynb`), plus the standard top cells `header_banner(...)` (branded HTML banner), `parameters_cell(...)` (papermill `parameters`-tagged), and `badge_row(...)`. Then `render()` for the `.py` percent text (the reviewable source of truth) or `write_py` / `write_ipynb` to disk (`write_ipynb` lazy-imports jupytext).

```python
from fieldkit.notebook import NotebookBuilder, colab_url, kaggle_url, notebook_path

p = notebook_path("patent-strategist", "user")
b = NotebookBuilder(vertical="patent-strategist", audience="App developer", title="Use patent-strategist in your app")
b.parameters_cell({"hf_repo": "Orionfold/patent-strategist-v3-unsloth-GGUF"})
b.header_banner(badges="", subtitle="Claim construction, MPEP-grounded office-action drafting")
b.badge_row(colab=colab_url(p), kaggle=kaggle_url(p), label="Open this notebook")
b.step("Open the model — backend picked by runtime.",
       "client = open_model(hf_repo)", "On Spark this is in-process llama.cpp; on Colab it pulls Q4_K_M.")
b.write_py("notebooks/patent-strategist/user.py")
b.write_ipynb("notebooks/patent-strategist/user.ipynb")
```

## Notes

- **Source of truth is the `.py` percent**; the `.ipynb` is generated + committed because Colab opens it directly from GitHub. Keep them in sync via jupytext (the `notebook-author` / `notebook-snapshot` skills do this deterministically).
- **No blank lines inside the banner HTML** — markdown breaks out of an HTML block on a blank line (`feedback_fn_diagram_no_blank_lines`). The banner is one HTML block; the markdown badge row is a *separate* cell (`badge_row`), never embedded in the banner.
- **`open_model` is intentionally not `fieldkit.infer`.** Promotion to a generic backend abstraction is gated on a 2nd non-notebook consumer (spec §8.5) — until then it lives here.
