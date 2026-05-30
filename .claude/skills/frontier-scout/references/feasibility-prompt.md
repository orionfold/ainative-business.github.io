# Deep feasibility eval — prompt + template

Used in `eval` mode. Output is one structured markdown document at `papers/<arxiv-id>/eval.md` — browsable directly on GitHub or in any markdown reader. Write clean markdown — no raw HTML, no MDX, no Astro components.

## Method

1. Fetch the paper body. Try `https://ar5iv.labs.arxiv.org/html/<id>` first (clean HTML render); fallback to `https://arxiv.org/abs/<id>`. Use `WebFetch`. Read the actual paper, not just the abstract.
2. Survey the linked repo if any. Use `gh api`:
   - `gh api /repos/<owner>/<repo>/readme -q '.content' | base64 -d` for README
   - `gh api /repos/<owner>/<repo>/contents/` for top-level file list
   - `gh api /repos/<owner>/<repo>/languages` for language stats
   - Skim any `requirements.txt`, `pyproject.toml`, or `environment.yml` — name dependencies explicitly in the recipe
3. Consult the Spark capability map actively. Preferred: `from fieldkit.capabilities import Capabilities, kv_cache_bytes, weight_bytes, practical_inference_envelope` — `Capabilities.load()` gives you the typed view of `.hardware`, `.stack`, `.in_envelope_signals`, `.out_of_envelope_signals`, `.stage_routing_hints`, `.series_routing_hints`. Fallback: read `scripts/lib/spark-capabilities.json` directly when `fieldkit` isn't importable. Every claim about what NIM / NeMo / TRT-LLM can do today must be defensible against this map. If the map says something is *aspirational*, mark it as a blocker.
4. Run the memory math (below) whenever the paper involves a specific model size.
5. Form the verdict and write the markdown.

## Memory math

The unified 128 GB pool serves both CPU and GPU on GB10. Allocations from one shrink the budget of the other.

Use the typed helpers from `fieldkit.capabilities` — they encode the same equations and pull dtype constants from the capability map, so the eval and the published math stay aligned:

```python
from fieldkit.capabilities import kv_cache_bytes, weight_bytes, practical_inference_envelope

weights = weight_bytes(params_b=70, dtype="fp8")           # 70_000_000_000 bytes ≈ 70 GB
kv = kv_cache_bytes(                                       # KV bytes for the working point
    hidden=8 * 128,    # n_kv_heads × head_dim (e.g. Llama-3 GQA)
    n_layers=80,
    ctx=16384,
    batch=32,
    dtype="fp8",
)
print(practical_inference_envelope("70B params fp8"))      # the curated rule-of-thumb string
```

If `fieldkit` isn't installed in the active environment, fall back to the equivalent formulas:

```
weights_gb         = params_b * bytes_per_param
kv_per_token_layer = 2 * hidden_size * bytes_per_param          # `hidden_size` here = n_kv_heads × head_dim
kv_gb              = kv_per_token_layer * n_layers * kv_ctx_tokens * batch / 1e9
total_gb           = weights_gb + kv_gb
```

`bytes_per_param`: fp32=4, bf16=2, fp16=2, fp8=1, int8=1, int4=0.5

For training overhead, multiply weights by ~4× for full fine-tune (params + grads + optimizer state + activations); ~1.5× for LoRA.

### Common shape examples

- Llama 3.1 8B bf16: 16 GB weights, comfortable
- Llama 3.3 70B bf16: 140 GB — already over budget *before* KV
- Llama 3.3 70B fp8: 70 GB weights, ~50 GB headroom for KV + activations + system → tight but possible
- Llama 3.3 70B int4: 35 GB weights → comfortable
- 405B+ at any quant: out of envelope

If you don't know `n_layers` / `hidden_size`, look them up from the model's config or assume Llama-class defaults (n_layers=32, hidden=4096 for 8B; 80, 8192 for 70B) and call out the assumption.

## Output template

Write exactly this structure. The section ordering is load-bearing — `papers-promote` extracts sections by name. Sections in order: **Hypothesis · Memory budget · Proposed Spark recipe · Blockers · Verdict · Fieldkit fit · Article suggestion**.

```markdown
# {Paper title}

## Hypothesis

One paragraph restating the paper's core claim in your own words. Plain prose, no jargon padding.

## Memory budget

Show the arithmetic explicitly. If multiple model sizes are studied in the paper, walk the most-Spark-relevant size and tabulate the others briefly. Compare against the 128 GB envelope.

## Proposed Spark recipe

Concrete, sequenced steps using specific NVIDIA tools. Reference exact stack items from the capability map (NIM, NeMo, TRT-LLM build flags like `--use_paged_context_fmha`, etc.) and call out where the curated map says something is possible vs aspirational.

If the paper has a working repo, include a step like `git clone --depth 1 <repo>` and reference the actual files it ships.

## Blockers

- Bulleted list, one blocker per line.
- Be honest: missing kernels, incompatible quant flows, training-data scale, multi-GPU dependencies.
- Empty list is fine if there are no genuine blockers — say so explicitly: `- (none — recipe should run as-is)`.

## Verdict

**spark-feasible** — one-sentence justification tying the verdict to the strongest evidence (e.g., "8B fp8 weights fit in 16 GB and the existing NIM container serves this exact model").

(Or **borderline** if the recipe works but with caveats; **out-of-envelope** if the paper requires hardware the Spark doesn't have.)

## Fieldkit fit

Map the paper's reproduction to one or more `fieldkit` modules so the package becomes a roadmap of the editorial calendar. Pick the most-relevant published or planned module(s); keep the section to 1–3 short bullets.

- **Would import:** `fieldkit.<module1>`, `fieldkit.<module2>` — one phrase per module saying which abstraction it covers (e.g., "`fieldkit.nim` for the OpenAI-compatible NIM client; `fieldkit.eval` for the Pass@k bench").
- **Would extend (if any):** module name + one phrase on the proposed addition (e.g., "`fieldkit.eval` — adds a `PassAtKBench` subclass; trivially generalizes the existing `Bench`."). Skip the bullet if the existing API is enough.
- **Would propose for v0.x:** if no current or planned module covers the paper's contribution cleanly, name a candidate module + one-line scope (e.g., "`fieldkit.distill` — test-time-training distiller wrapping a shallow→deep MLP probe alongside vLLM. Candidate for v0.3."). Skip the bullet if the existing surface is enough.

The deferred-modules table in `ideas/fieldkit.md` is the menu — `fieldkit.retriever`, `fieldkit.ft`, `fieldkit.guardrails`, `fieldkit.agents` (v0.2), `fieldkit.train`, `fieldkit.observe` (v0.3) — prefer those slots before inventing new module names. The current published surface (v0.1) is `capabilities | nim | rag | eval | cli`.

## Article suggestion

- **Would write?** yes / no
- **Suggested slug:** kebab-case-slug
- **Suggested stage:** one of foundations | training | fine-tuning | inference | deployment | agentic | observability | dev-tools
- **Suggested series:** one of Foundations | "Second Brain" | "LLM Wiki" | "Machine that Builds Machines" | "Looking Beyond Spark" | "Frontier Scout"
- **Suggested book chapters (MTBM only):** integer array of `/book/` chapter numbers 1–14 (default `[10]` for "The Machine That Builds Machines"; add `[11]` for meta-programming, `[8]` for swarm, `[7]` for institutional memory). Skip when series is not MTBM.
- **Suggested mtbm_station (MTBM only):** one of `refinery | forge | planner | validator | knowledge-graph`. Skip when series is not MTBM or fit is ambiguous.
- **Suggested tags:** comma-separated
- **Suggested summary:** ≤300 chars; will become the article frontmatter `summary` field on promote
- **Suggested `fieldkit_modules`:** ordered list of v0.1 modules the article would actually import (e.g., `[nim, eval]`); leave empty if the paper proposes only deferred-version modules.

## Alignment lens (MTBM only)

When the suggested series is `"Machine that Builds Machines"`, close with this five-bullet inset borrowed from 8090.ai's "Alignment Engineering" framework. One sentence per bullet — say which alignment failure the paper addresses, or `_n/a_` if the layer doesn't apply. Skip the section entirely for non-MTBM evals.

- **Ontological** — does the paper agree with the rest of the stack on *what things are*? (shared vocabulary, schemas, ontologies)
- **Teleological** — does the paper agree on *what success looks like*? (reward, eval, benchmark choice)
- **Behavioral** — does the paper specify *what the system does in all situations*? (edge cases, defaults, refusals)
- **Temporal** — does alignment *survive over time* as the system trains, drifts, or is retrained? (online learning, continual fine-tuning, catastrophic forgetting)
- **Reflexive** — can the system *detect its own misalignment*? (self-correction, uncertainty estimation, abstention)
```

## Style notes for the eval

- Voice: senior solutions engineer briefing a peer. Specific, terse, no hedging beyond what the technical reality justifies.
- Length: ~600–900 words total is the sweet spot. Long enough to defend the verdict, short enough to skim. Memory budget should be ≤150 words; recipe should be the longest section.
- Don't speculate on novel kernels you'd write. If something requires custom CUDA the user hasn't already shipped in the capability map, that's a blocker, not a recipe step.
- Cross-link to existing articles when the paper directly extends published work. Use the `mcp__second-brain__search_blog` MCP tool if available — it surfaces semantically-related articles. Format: `(see "Article Title" in the blog)`.

## After writing the markdown

1. Save to `papers/<arxiv-id>/eval.md`. **Refuse to overwrite an existing `eval.md`** — evals are immutable; revisions go through `annotate` mode.
2. Patch `papers/papers.json`: add `deep_eval: { path: "papers/<id>/eval.md", evaluated_at: <iso-now>, verdict: "<extracted-from-Verdict-section>" }` to the paper's entry.
3. Regenerate `papers/<arxiv-id>/paper.md` so its frontmatter `has_deep_eval: true` and the body links to `eval.md` (template in `references/data-schema.md`).
4. Report verdict + 1–3 sentence recipe summary in chat. Offer the next move (`/frontier-scout promote <id>`).
