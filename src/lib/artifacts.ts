export const ARTIFACT_KINDS = [
  'quant',
  'lora',
  'adapter',
  'embed',
  'reranker',
  'dataset',
  'space',
  'bench',
] as const;

export type ArtifactKind = (typeof ARTIFACT_KINDS)[number];

const SEGMENT_BY_KIND: Record<ArtifactKind, string> = {
  quant: 'quants',
  lora: 'loras',
  adapter: 'adapters',
  embed: 'embeds',
  reranker: 'rerankers',
  dataset: 'datasets',
  space: 'spaces',
  bench: 'benches',
};

const DISPLAY_NAME_BY_KIND: Record<ArtifactKind, string> = {
  quant: 'Quantization',
  lora: 'LoRA adapter',
  adapter: 'Adapter',
  embed: 'Embedding model',
  reranker: 'Reranker',
  dataset: 'Dataset',
  space: 'Space',
  bench: 'Benchmark',
};

const PLURAL_DISPLAY_NAME_BY_KIND: Record<ArtifactKind, string> = {
  quant: 'Quantizations',
  lora: 'LoRA adapters',
  adapter: 'Adapters',
  embed: 'Embedding models',
  reranker: 'Rerankers',
  dataset: 'Datasets',
  space: 'Spaces',
  bench: 'Benchmarks',
};

export function kindToSegment(kind: ArtifactKind): string {
  return SEGMENT_BY_KIND[kind];
}

export function kindToDisplayName(kind: ArtifactKind): string {
  return DISPLAY_NAME_BY_KIND[kind];
}

export function kindToPluralDisplayName(kind: ArtifactKind): string {
  return PLURAL_DISPLAY_NAME_BY_KIND[kind];
}

export function rankWithin(
  values: Record<string, number>,
  higherIsBetter: boolean,
): Record<string, number> {
  const entries = Object.entries(values);
  if (entries.length === 0) return {};
  const xs = entries.map(([, v]) => v);
  const min = Math.min(...xs);
  const max = Math.max(...xs);
  const span = max - min;
  const out: Record<string, number> = {};
  for (const [k, v] of entries) {
    if (span === 0) {
      out[k] = 1;
      continue;
    }
    const norm = (v - min) / span;
    out[k] = higherIsBetter ? norm : 1 - norm;
  }
  return out;
}

export interface ArtifactDataShape {
  variants?: string[];
  perplexity?: Record<string, number>;
  spark_tokens_per_sec?: Record<string, number>;
  vertical_eval?: Record<string, number>;
}

// Unquantized reference variants by GGUF convention — these are what the
// quants are derived FROM, not a recommended download for a downstream user.
// Excluded from sweet-spot consideration so the picker stays product-honest.
const UNQUANTIZED_REFERENCE_VARIANTS = new Set(['F16', 'BF16', 'FP16', 'FP32', 'F32']);

export function pickSweetSpot(artifact: ArtifactDataShape): string | null {
  const allVariants = artifact.variants ?? [];
  const candidates = allVariants.filter((v) => !UNQUANTIZED_REFERENCE_VARIANTS.has(v));
  if (candidates.length === 0) return null;

  const perplexity = artifact.perplexity ?? null;
  const throughput = artifact.spark_tokens_per_sec ?? null;
  const verticalEval = artifact.vertical_eval ?? null;

  // Rank within the full variant set (including F16) so the heatmap scale on
  // the detail page stays consistent. The sweet-spot pick draws from
  // `candidates` only.
  const qualityRank = perplexity ? rankWithin(perplexity, false) : null;
  const throughputRank = throughput ? rankWithin(throughput, true) : null;
  const verticalRank = verticalEval ? rankWithin(verticalEval, true) : null;

  let best: { name: string; score: number } | null = null;
  for (const v of candidates) {
    const parts: number[] = [];
    if (qualityRank && v in qualityRank) parts.push(qualityRank[v]);
    if (throughputRank && v in throughputRank) parts.push(throughputRank[v]);
    if (verticalRank && v in verticalRank) parts.push(verticalRank[v]);
    if (parts.length === 0) continue;
    const score = parts.reduce((a, b) => a + b, 0) / parts.length;
    if (!best || score > best.score) best = { name: v, score };
  }
  return best ? best.name : null;
}
