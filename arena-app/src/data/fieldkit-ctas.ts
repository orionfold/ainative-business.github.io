import { FIELDKIT_MODULES } from '../content.config.ts';

type ModuleSlug = (typeof FIELDKIT_MODULES)[number];

export type FieldkitCTAComponent = {
  name: string;
  module: ModuleSlug;
  why: string;
};

export type FieldkitCTAEntry = {
  headline: string;
  pitch: string;
  components: FieldkitCTAComponent[];
};

export const FIELDKIT_CTAS: Record<string, FieldkitCTAEntry> = {
  'nim-first-inference-dgx-spark': {
    headline: 'Skip the curl scaffolding around your NIM',
    pitch:
      'The NIM client in this article — connect, retry on cold-start, preflight the 8192-token ceiling, parse a streaming response — is exactly what fieldkit.nim ships out of the box. Drop ten lines of boilerplate per script.',
    components: [
      {
        name: 'fieldkit.nim.NIMClient',
        module: 'nim',
        why: 'OpenAI-compatible client with retry, warm-wait, and context-overflow preflight built in.',
      },
      {
        name: 'fieldkit.nim.wait_for_warm()',
        module: 'nim',
        why: 'Block until the NIM is serving — replaces hand-rolled cold-start polling.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Aggregate the 24.8 tok/s number with mean / median / min / max + per-call traces.',
      },
    ],
  },

  'naive-rag-on-spark': {
    headline: 'Three endpoints, one Python import',
    pitch:
      'The naive ingest → retrieve → generate chain in this article is the canonical source for fieldkit.rag.Pipeline. The eval harness behind every latency table is fieldkit.eval.Bench. Pip install and skip the boilerplate.',
    components: [
      {
        name: 'fieldkit.rag.Pipeline',
        module: 'rag',
        why: 'Drop-in replacement for the 200-line embed → retrieve → fuse loop in this article.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Per-stage latency aggregation (embed_ms / retrieve_ms / generate_ms) — same JSON shape.',
      },
      {
        name: 'fieldkit.eval.is_refusal()',
        module: 'eval',
        why: 'Refusal regex from this article, lifted into a one-call helper.',
      },
    ],
  },

  'nemo-retriever-embeddings-local': {
    headline: 'Skip the embed-curl loop',
    pitch:
      'fieldkit.rag.Pipeline ships with the Nemotron Retriever endpoint pre-wired (DEFAULT_EMBED_MODEL, 1024-dim). The throughput sweep below — batch 1 / 8 / 32 / 64 — is one Bench loop.',
    components: [
      {
        name: 'fieldkit.rag.Pipeline',
        module: 'rag',
        why: 'Embedder, pgvector store, and reranker behind one context-managed object.',
      },
      {
        name: 'fieldkit.rag.DEFAULT_EMBED_MODEL',
        module: 'rag',
        why: 'Constant pointing at the Nemotron Retriever ID this article validates.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Per-batch and aggregate timing — reproduces this article\'s throughput table.',
      },
    ],
  },

  'pgvector-on-spark': {
    headline: 'Pipeline writes pgvector for you',
    pitch:
      'The pgvector schema, HNSW index, and ingest-then-query loop in this article are baked into fieldkit.rag.Pipeline. The latency-sweep harness is fieldkit.eval.Bench.',
    components: [
      {
        name: 'fieldkit.rag.Pipeline',
        module: 'rag',
        why: 'ensure_schema() + ingest() handle the pgvector setup this article walks through manually.',
      },
      {
        name: 'fieldkit.rag.Document',
        module: 'rag',
        why: 'Typed dataclass for the rows this article inserts as raw SQL.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Mean / median / min / max latency rollup — replaces the hand-rolled timing block.',
      },
    ],
  },

  'guardrails-on-the-retrieval-path': {
    headline: 'Per-rail Bench gives you the table for free',
    pitch:
      'The same NeMo Guardrails configs in this article slot into fieldkit.rag.Pipeline as a wrapper, and fieldkit.eval.Bench produces the block / pass counts per policy without rewriting the harness.',
    components: [
      {
        name: 'fieldkit.rag.Pipeline',
        module: 'rag',
        why: 'Pipe rail-filtered queries through the same retrieve-and-fuse path.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'One Bench(name="…") per rail config — block / pass counts roll up automatically.',
      },
    ],
  },

  'bigger-generator-grounding-on-spark': {
    headline: 'Swap the generator in one line',
    pitch:
      'The 8B / 49B / 70B A/B in this article reduces to swapping the NIMClient passed into fieldkit.rag.Pipeline. fieldkit.eval.is_refusal reproduces the over-refusal table without re-deriving the regex.',
    components: [
      {
        name: 'fieldkit.rag.Pipeline',
        module: 'rag',
        why: 'Same retrieval, three generators — only the NIMClient argument changes.',
      },
      {
        name: 'fieldkit.eval.is_refusal()',
        module: 'eval',
        why: 'Lifted verbatim from this article\'s refusal regex.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Per-generator latency + refusal-rate aggregation in one harness.',
      },
    ],
  },

  'rerank-fusion-retrieval-on-spark': {
    headline: 'One Pipeline, four retrieval modes',
    pitch:
      'BM25, dense, RRF fusion, and rerank — fieldkit.rag.Pipeline switches between them with a constructor flag. fieldkit.eval.Bench reproduces the recall@5 / @10 sweep table.',
    components: [
      {
        name: 'fieldkit.rag.Pipeline',
        module: 'rag',
        why: 'Same ingest, four retrieval strategies — switch by argument.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Per-mode latency + recall aggregation, merged into the comparison table.',
      },
    ],
  },

  'rag-eval-ragas-and-nemo-evaluator': {
    headline: 'The Judge rubrics live here verbatim',
    pitch:
      'The 0-5 correctness, 0-1 faithfulness, and 0-1 relevance system prompts derived in this article are the canonical source for fieldkit.eval.RUBRIC_*. Pip install and grade with one call per rubric.',
    components: [
      {
        name: 'fieldkit.eval.Judge',
        module: 'eval',
        why: 'LLM-as-judge with built-in correctness / faithfulness / relevance rubrics.',
      },
      {
        name: 'fieldkit.eval.RUBRIC_CORRECTNESS',
        module: 'eval',
        why: 'The exact 0-5 rubric prompt this article distills, importable.',
      },
      {
        name: 'fieldkit.eval.summarize_metric()',
        module: 'eval',
        why: 'Roll a list of JudgeResults into mean / median / pass-rate.',
      },
    ],
  },

  'lora-on-your-own-qa-pairs': {
    headline: 'Drop the hand-rolled grader',
    pitch:
      'The LLM-as-judge correctness loop and refusal-rate detector in evidence/judge.py from this article are now fieldkit.eval.Judge.builtin("correctness") and fieldkit.eval.is_refusal — two imports replace the harness.',
    components: [
      {
        name: 'fieldkit.eval.Judge',
        module: 'eval',
        why: 'Judge.builtin(NIMClient(...), "correctness").grade(...) replaces evidence/judge.py.',
      },
      {
        name: 'fieldkit.eval.is_refusal()',
        module: 'eval',
        why: 'Refusal regex from this article, top-level helper.',
      },
    ],
  },

  'gpu-sizing-math-for-fine-tuning': {
    headline: 'Stop hand-deriving the bytes',
    pitch:
      'Every weight and KV figure in this article — fp8, bf16, nf4 — is exactly what fieldkit.capabilities.weight_bytes() and kv_cache_bytes() return. Use them before you size a cluster.',
    components: [
      {
        name: 'fieldkit.capabilities.weight_bytes()',
        module: 'capabilities',
        why: 'params × dtype-bytes — the formula behind every "weights" row in this article.',
      },
      {
        name: 'fieldkit.capabilities.kv_cache_bytes()',
        module: 'capabilities',
        why: '2 × layers × hidden × ctx × batch × dtype — for the per-step KV table.',
      },
      {
        name: 'fieldkit.capabilities.practical_inference_envelope()',
        module: 'capabilities',
        why: 'String like "tight but possible" — the article\'s envelope verdict, automated.',
      },
    ],
  },

  'kv-cache-arithmetic-at-inference': {
    headline: 'The KV equation, importable',
    pitch:
      'The canonical 2 × layers × hidden × ctx × batch × dtype equation from this article is the body of fieldkit.capabilities.kv_cache_bytes(). The CLI lets you sanity-check any model size without writing Python.',
    components: [
      {
        name: 'fieldkit.capabilities.kv_cache_bytes()',
        module: 'capabilities',
        why: 'The 70B FP8 / 32-user / 16K-ctx ≈ 168 GB number, in one call.',
      },
      {
        name: 'fieldkit envelope <size>',
        module: 'cli',
        why: 'CLI wrapper — `fieldkit envelope "70B params fp8"` returns a one-line verdict.',
      },
      {
        name: 'fieldkit feasibility <model> --ctx --batch --dtype',
        module: 'cli',
        why: 'Full breakdown matching the per-batch tables in this article.',
      },
    ],
  },

  'derisk-cloud-pretraining-on-the-spark': {
    headline: 'Size the cloud run before you book it',
    pitch:
      'The Spark-vs-cloud arithmetic in this article — what fits, what spills — is exactly what fieldkit.capabilities.practical_inference_envelope() answers. Run the check before the H100 invoice arrives.',
    components: [
      {
        name: 'fieldkit.capabilities.practical_inference_envelope()',
        module: 'capabilities',
        why: 'String verdict per model size — feasible on Spark, borderline, or cloud-only.',
      },
      {
        name: 'fieldkit.capabilities.weight_bytes()',
        module: 'capabilities',
        why: 'Cross-check the params × dtype math behind the cloud-vs-Spark spreadsheet.',
      },
    ],
  },

  'trtllm-and-triton-on-spark': {
    headline: 'Same client, TRT-LLM endpoint',
    pitch:
      'fieldkit.nim.NIMClient is OpenAI-compatible — point it at the TRT-LLM Triton endpoint from this article and the rest of your eval harness keeps working. Use fieldkit.capabilities to envelope-check NVFP4 before deploy.',
    components: [
      {
        name: 'fieldkit.nim.NIMClient',
        module: 'nim',
        why: 'Drop-in client for any OpenAI-compatible endpoint, NIM or TRT-LLM Triton.',
      },
      {
        name: 'fieldkit.capabilities.weight_bytes()',
        module: 'capabilities',
        why: 'NVFP4 = 0.5 bytes/param — quantify the article\'s 4-bit win in one call.',
      },
    ],
  },

  'nemo-framework-on-spark': {
    headline: 'Bench the throughput sweep',
    pitch:
      'The +5.8% throughput / -30% memory comparison in this article is exactly the per-config aggregation fieldkit.eval.Bench is built for. Drive both training paths through one harness, get the table for free.',
    components: [
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'tok/s + memory aggregation per config — reproduces this article\'s comparison table.',
      },
      {
        name: 'fieldkit.eval.summarize_metric()',
        module: 'eval',
        why: 'Mean / median / min / max rollup across the run.',
      },
    ],
  },

  'nemo-curator-training-data-prep': {
    headline: 'Quantify the data-path overhead',
    pitch:
      'The 0.01–0.04% data-path overhead measurement in this article is one Bench wrap around the dataloader. Reproduce the 14,980 tok/s peak with three lines.',
    components: [
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Per-step timing — wrap the dataloader call and read mean / p99 / max.',
      },
    ],
  },

  'baseline-training-loop-on-spark': {
    headline: 'Replace the 16-config sweep harness',
    pitch:
      'The batch / sequence / precision sweep table in this article — 16 configs, 14,266 tok/s peak — is what fieldkit.eval.Bench produces when you wrap a single train-step callable.',
    components: [
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Per-config aggregation with full per-call traces — drop into any sweep loop.',
      },
      {
        name: 'fieldkit.eval.summarize_metric()',
        module: 'eval',
        why: 'Cross-config rollup for the comparison table.',
      },
    ],
  },

  'autoresearch-agent-loop': {
    headline: 'Trajectory analysis, importable',
    pitch:
      'The 50-iteration JSONL log, knob-touch counts, and revert ratios in this article are exactly what fieldkit.eval.Trajectory unpacks. Stop writing the parser per agent loop.',
    components: [
      {
        name: 'fieldkit.eval.Trajectory',
        module: 'eval',
        why: 'JSONL agent-loop iterator — counts per knob, reverts, repeated proposals.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Per-iteration timing + val_bpb tracking across the run.',
      },
    ],
  },

  'trajectory-eval-is-the-agent-flailing': {
    headline: 'The Trajectory class is literally this article',
    pitch:
      'Every metric this article hand-derives — k=5 history window, 72% repeated proposals, 6/13 knobs touched — is exposed by fieldkit.eval.Trajectory. The article is the canonical derivation.',
    components: [
      {
        name: 'fieldkit.eval.Trajectory',
        module: 'eval',
        why: 'Knob-touch counts, repeated-proposal rate, history-window analysis — all built in.',
      },
      {
        name: 'fieldkit.eval.summarize_metric()',
        module: 'eval',
        why: 'Roll trajectory metrics across runs without re-deriving the loop.',
      },
    ],
  },

  'distill-architect-lora-from-trajectories': {
    headline: 'Source the data, score the model',
    pitch:
      'fieldkit.eval.Trajectory unpacks the agent JSONL this LoRA trains from. fieldkit.eval.Judge grades the 0/8 exact-match + 4/8 partial-match table without a hand-rolled grader.',
    components: [
      {
        name: 'fieldkit.eval.Trajectory',
        module: 'eval',
        why: 'Source the (state → action) pairs from the agent run that feed this LoRA.',
      },
      {
        name: 'fieldkit.eval.Judge',
        module: 'eval',
        why: 'LLM-as-judge for the 0/8 exact-match table on held-out probes.',
      },
    ],
  },

  'mcp-second-brain-in-claude-code': {
    headline: 'Pipeline.ask() collapses the four MCP tools',
    pitch:
      'The four MCP tools (embed / retrieve / rerank / generate) wrapping the Second Brain stack in this article reduce to one call: fieldkit.rag.Pipeline.ask(). 200 lines becomes 5.',
    components: [
      {
        name: 'fieldkit.rag.Pipeline',
        module: 'rag',
        why: 'Pipeline.ask(question) returns answer + grounded chunks — the four MCP tools, fused.',
      },
      {
        name: 'fieldkit.nim.NIMClient',
        module: 'nim',
        why: 'OpenAI-compatible client for the generator step, with the 8192-tok preflight built in.',
      },
    ],
  },

  'one-substrate-three-apps': {
    headline: 'The whole foundation stack in three imports',
    pitch:
      'fieldkit lifts the NIM client, the RAG pipeline, and the eval harness out of this foundation into three imports — the same three primitives every article in this arc reuses.',
    components: [
      {
        name: 'fieldkit.nim.NIMClient',
        module: 'nim',
        why: 'OpenAI-compatible client — one line per generator endpoint.',
      },
      {
        name: 'fieldkit.rag.Pipeline',
        module: 'rag',
        why: 'Ingest → retrieve → rerank → fuse — the substrate, importable.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Latency aggregation behind every per-stage table in this arc.',
      },
    ],
  },

  'what-the-agent-actually-built': {
    headline: 'The toolkit behind the autoresearch arc',
    pitch:
      'Every primitive the agent reaches for in this five-piece arc — sizing arithmetic, NIM client, Bench aggregation, Trajectory analysis — is in fieldkit. Pip install once, follow the arc with the same APIs the articles use.',
    components: [
      {
        name: 'fieldkit.eval.Trajectory',
        module: 'eval',
        why: 'JSONL agent-loop iterator — what the autoresearch retrospectives are built on.',
      },
      {
        name: 'fieldkit.eval.Bench',
        module: 'eval',
        why: 'Per-iteration timing + val_bpb across the 50-iter loop.',
      },
      {
        name: 'fieldkit.capabilities.kv_cache_bytes()',
        module: 'capabilities',
        why: 'Sizing arithmetic the architect-LoRA pieces lean on.',
      },
    ],
  },
};
