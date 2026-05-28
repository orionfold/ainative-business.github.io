export const ARTIFACT_KINDS = [
  'quant',
  'lora',
  'adapter',
  'dataset',
  'bench',
  'notebook',
  'harness',
  'skill',
] as const;

export type ArtifactKind = (typeof ARTIFACT_KINDS)[number];

const SEGMENT_BY_KIND: Record<ArtifactKind, string> = {
  quant: 'quants',
  lora: 'loras',
  adapter: 'adapters',
  dataset: 'datasets',
  bench: 'benches',
  notebook: 'notebooks',
  harness: 'harnesses',
  skill: 'skills',
};

const DISPLAY_NAME_BY_KIND: Record<ArtifactKind, string> = {
  quant: 'Quantization',
  lora: 'LoRA adapter',
  adapter: 'Adapter',
  dataset: 'Dataset',
  bench: 'Benchmark',
  notebook: 'Notebook',
  harness: 'Harness',
  skill: 'Skill',
};

const PLURAL_DISPLAY_NAME_BY_KIND: Record<ArtifactKind, string> = {
  quant: 'Quantizations',
  lora: 'LoRA adapters',
  adapter: 'Adapters',
  dataset: 'Datasets',
  bench: 'Benchmarks',
  notebook: 'Notebooks',
  harness: 'Harnesses',
  skill: 'Skills',
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
  recommended_variant?: string;
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

  // Manifest-level override wins when set and references a real candidate.
  // Source's pipeline knows the per-card recommended variant from the article
  // narrative; this surface lets the manifest declare it directly instead of
  // the picker inferring from rank-avg.
  if (artifact.recommended_variant && candidates.includes(artifact.recommended_variant)) {
    return artifact.recommended_variant;
  }

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

// --- Bench-specific helpers (kind: bench) ----------------------------------

export const BENCH_SCORER_TIERS = ['deterministic', 'structural', 'judge'] as const;
export type BenchScorerTier = (typeof BENCH_SCORER_TIERS)[number];

// CSS-custom-property token for each scorer tier. Components use these to
// color the BenchSignature segments and the BenchSampleRow scorer pills.
const SCORER_TIER_TOKEN: Record<BenchScorerTier, string> = {
  deterministic: '--color-primary',
  structural: '--color-accent',
  judge: '--color-text-muted',
};

export function scorerTierColor(tier: BenchScorerTier): string {
  return `var(${SCORER_TIER_TOKEN[tier]})`;
}

export interface BenchShape {
  code: string;
  label: string;
  count: number;
  scorer: BenchScorerTier;
  source: string;
}

export interface BenchResults {
  [shapeOrOverall: string]: { [mode: string]: number };
}

// Pick the shape that produced the biggest closed→oracle lift among
// deterministically-scorable shapes. This is the bench's "sweet spot" —
// the singular finding worth surfacing on the list card and highlighting
// in the detail-page bracket table. Returns null when no deterministic
// shape has all required modes populated.
export function pickStrongestDeterministicShape(
  results: BenchResults | undefined,
  shapes: BenchShape[] | undefined,
): { code: string; closed: number; oracle: number; span: number } | null {
  if (!results || !shapes) return null;
  const detCodes = new Set(
    shapes.filter((s) => s.scorer === 'deterministic').map((s) => s.code),
  );
  let best: { code: string; closed: number; oracle: number; span: number } | null = null;
  for (const [code, modeScores] of Object.entries(results)) {
    if (!detCodes.has(code)) continue;
    const closed = modeScores.closed;
    const oracle = modeScores.oracle;
    if (typeof closed !== 'number' || typeof oracle !== 'number') continue;
    const span = oracle - closed;
    if (!best || span > best.span) {
      best = { code, closed, oracle, span };
    }
  }
  return best;
}
