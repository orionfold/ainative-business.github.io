# fieldkit imports — lookup table for `draft` mode

When an article's frontmatter declares `fieldkit_modules: [...]`, the article's
Python code blocks should import from `fieldkit` instead of pasting the
boilerplate the package was built to replace.

This file is the canonical mapping. Keep it in sync with the package's public
surface (`__all__` in each module's `__init__.py`) and the
`/fieldkit/api/<module>/` Astro reference pages.

The `fieldkit_modules` enum is defined in `src/content.config.ts`
(`FIELDKIT_MODULES = ['capabilities', 'nim', 'rag', 'eval', 'cli']`). Articles
should set the modules they actually import — conservative, not aspirational.

## How to use this in `draft` and `polish`

1. Read the article's frontmatter. If `fieldkit_modules` is present, every
   Python snippet in the article must use the imports below for the listed
   modules.
2. Replace inlined helpers — KV-cache math, retry-loop NIM clients, pgvector
   chunk-and-embed glue, `bench.py`-shaped benchmark runners, LLM-as-judge
   rubric prompts — with the published `fieldkit` API. The article should
   read like a power-user reaching for the package, not a tutorial that
   re-derives the package from scratch.
3. The article's *prose* still walks the math and the design choices — the
   thinking is the value. The *code* points at the canonical implementation
   so readers can `pip install` and reproduce.
4. Cross-link the first mention of each module to its reference page:
   `[\`fieldkit.rag\`](/fieldkit/api/rag/)`. The Astro layout already adds a
   "USES fieldkit.X" chip on the article card from the frontmatter — the
   prose-side link is the call-to-action inside the article.
5. After drafting, sanity-check that every import in code blocks resolves
   against the surface below. Drift here is a `tech-writer extract` smell.

## Module → import boilerplate

### `capabilities`

```python
from fieldkit.capabilities import (
    Capabilities,
    kv_cache_bytes,
    weight_bytes,
    practical_inference_envelope,
)

caps = Capabilities.load()
caps.hardware                       # GB10 spec, unified memory budget
caps.in_envelope_signals            # what the Spark can do today
caps.out_of_envelope_signals        # the documented out-of-envelope cases
caps.stack                          # NIM/NeMo/TRT-LLM verified surface
caps.stage_routing_hints            # used by frontier-scout classify
caps.series_routing_hints           # used by frontier-scout classify

# Canonical math — same equations the kv-cache + sizing-math articles walk
weight_bytes(params_b=70, dtype="fp8")
kv_cache_bytes(hidden=8 * 128, n_layers=80, ctx=16384, batch=32, dtype="fp8")
practical_inference_envelope("70B params fp8")
```

Use this **instead of**: hand-coded `bytes_per_param` dicts; inline KV-cache
formulas pasted into the article from `kv-cache-arithmetic-at-inference`;
`json.load(open("scripts/lib/spark-capabilities.json"))` calls.

### `nim`

```python
from fieldkit.nim import (
    NIMClient,
    NIMError,
    NIMHTTPError,
    NIMTimeoutError,
    NIMContextOverflowError,
    chunk_text,
    estimate_tokens,
    wait_for_warm,
    NIM_CONTEXT_WINDOW,        # 8192
    DEFAULT_CHUNK_TOKENS,      # 1024
)

client = NIMClient(
    base_url="http://localhost:8000/v1",
    model="meta/llama-3.1-8b-instruct",
)
wait_for_warm(client.base_url, timeout=120)
client.chat([{"role": "user", "content": "Hello"}])
```

Use this **instead of**: hand-rolled `httpx` clients with `tenacity` retry
decorators; `requests.post(..., headers={"Authorization": ...})` boilerplate;
ad-hoc 8192-token preflight checks; the opaque NIM-400 fallout from
`project_spark_nim_context_window`.

### `rag`

```python
from fieldkit.rag import (
    Pipeline,
    Document,
    Chunk,
    DEFAULT_RERANK_URL,
    DEFAULT_EMBED_URL,
)
from fieldkit.nim import NIMClient

generator = NIMClient(base_url="http://localhost:8000/v1",
                      model="meta/llama-3.1-8b-instruct")
pipeline = Pipeline(
    embed_url="http://localhost:8001/v1",
    rerank_url=None,                       # opt-in; local reranker is GB10-blocked
    pgvector_dsn="postgresql://spark@localhost:5432/vectors",
    generator=generator,
)
pipeline.ingest([Document(id=1, text="..."), ...])
answer = pipeline.ask("What does the field guide say about KV cache?")
```

Use this **instead of**: hand-written `psycopg` upsert loops; inline
chunk-by-token-count helpers; the strict-context system prompt copy-pasted
from `naive-rag-on-spark`; manual top-K → rerank → fuse glue.

### `eval`

```python
from fieldkit.eval import (
    Bench,
    Judge,
    JudgeResult,
    Trajectory,
    is_refusal,
    summarize_metric,
)
from fieldkit.nim import NIMClient

with Bench(name="rag-fuse", metrics=["latency_ms", "tokens"]) as bench:
    for q in queries:
        bench.record(callable=lambda: pipeline.ask(q))
bench.report()                              # markdown table

judge = Judge(client=NIMClient(...), rubric="correctness")
judge.grade(predicted="...", reference="...")

traj = Trajectory.from_jsonl("evidence/run.jsonl")
traj.knob_coverage()
traj.repeat_rate(window=10)
```

Use this **instead of**: hand-written `time.perf_counter()` timing loops;
ad-hoc latency-aggregation dicts; bespoke LLM-as-judge prompts (use the
built-in `correctness` / `faithfulness` / `relevance` rubrics + `Judge.parse`);
hand-parsed agent-loop JSONL summaries.

### `cli`

The CLI is consumed in *prose* (showing `$ fieldkit feasibility ...` output
in a fenced shell block), not imported in Python. Use it when the article
demonstrates the demo moment:

```bash
$ fieldkit version
0.1.0
$ fieldkit envelope "70B params fp8"
~70 GB weights; leaves ~50 GB for KV / activations / system
$ fieldkit feasibility llama-3.1-70b --ctx 4096 --batch 32 --dtype fp8
$ fieldkit bench rag --pipeline=evidence/pipeline.toml
```

Use this **instead of**: writing a one-off CLI inside the article's `evidence/`
to demo the same numbers.

## When the article needs something fieldkit doesn't have yet

Two options, in order of preference:

1. **File an extraction candidate.** Run `tech-writer` in `extract` mode after
   the article ships. It scans the article's `evidence/` for code that should
   land in fieldkit and proposes a patch. Track it in
   `fieldkit/CHANGELOG.md` under `[Unreleased]`.
2. **Inline the helper *and* note it.** If extraction would take longer than
   the publication window allows, inline the code in `evidence/` and add a
   `# TODO(fieldkit): lift to fieldkit.<module>` comment so `extract` mode
   finds it.

Never silently re-implement something that's already in fieldkit — that's
the failure mode this whole convention exists to prevent.
