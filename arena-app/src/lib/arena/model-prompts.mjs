// Per-model example prompts + a null-safe recommended-variant picker.
//
// Shared by the models index, the [slug] detail page, and the command palette
// so the "Try in chat" / "Send to compare" deep-links and the highlighted
// quant row aren't reimplemented three times. Pure, deterministic, no deps.

// Vertical-appropriate example prompts. Keyed by manifest slug with a couple
// of base-model heuristics as a fallback so a new GGUF still gets a sensible
// default before its slug is added here.
const PROMPTS_BY_SLUG = {
  'patent-strategist-v3-nemo-gguf':
    'Construct the claim scope for a Markush group reciting "a halogen selected from F, Cl, Br" and explain the doctrine-of-equivalents exposure.',
  'patent-strategist-v3-nemo':
    'Draft an MPEP-grounded response to a §103 obviousness rejection that combines two references with no motivation to combine.',
  'finance-chat-gguf':
    'Walk through how a 50 bps rate cut flows to a regional bank\'s net interest margin over the next two quarters.',
  'saul-7b-instruct-v1-gguf':
    'Apply IRAC to whether a clickwrap agreement with a buried arbitration clause is enforceable against a consumer.',
  'securityllm-gguf':
    'Triage this alert: outbound DNS to a newly-registered domain every 60s from a finance workstation. Likely technique + first 3 response steps.',
  'ii-medical-8b-gguf':
    'A 58-year-old presents with crushing substernal chest pain radiating to the left arm. Give the differential and the immediate work-up.',
};

const PROMPTS_BY_KEYWORD = [
  [/patent|mpep|claim/i, 'Construct the claim scope and flag the prior-art exposure for this invention.'],
  [/finance|bank|invest/i, 'Explain the second-order effects of a 50 bps rate cut on bank margins.'],
  [/legal|law|saul/i, 'Apply IRAC to the enforceability of a buried arbitration clause.'],
  [/security|cyber|threat/i, 'Triage a suspicious outbound-DNS beacon and give the first response steps.'],
  [/medical|clinical|health/i, 'Give the differential and immediate work-up for acute substernal chest pain.'],
];

/** Best example prompt for an artifact (accepts a slug string or `data`). */
export function examplePromptFor(slugOrData) {
  const data = typeof slugOrData === 'string' ? { slug: slugOrData } : (slugOrData || {});
  const slug = data.slug || '';
  if (PROMPTS_BY_SLUG[slug]) return PROMPTS_BY_SLUG[slug];
  const hay = `${slug} ${data.base_model || ''} ${data.vertical_eval_name || ''}`;
  for (const [re, prompt] of PROMPTS_BY_KEYWORD) if (re.test(hay)) return prompt;
  return 'Show me what you can do — answer a hard question in your domain and show your reasoning.';
}

/**
 * Null-safe recommended-variant picker.
 * Precedence: explicit `recommended_variant` → highest vertical_eval (tie-break
 * faster tok/s) → lowest perplexity (tie-break faster tok/s) → first variant.
 * Returns null when the manifest carries no variant data at all.
 */
export function recommendedVariant(data = {}) {
  if (data.recommended_variant) return data.recommended_variant;
  const toks = data.spark_tokens_per_sec || {};
  const speed = (v) => (typeof toks[v] === 'number' ? toks[v] : -Infinity);

  const evals = data.vertical_eval || {};
  const evalKeys = Object.keys(evals);
  if (evalKeys.length) {
    return evalKeys.sort((a, b) => (evals[b] - evals[a]) || (speed(b) - speed(a)))[0];
  }
  const ppl = data.perplexity || {};
  const pplKeys = Object.keys(ppl);
  if (pplKeys.length) {
    return pplKeys.sort((a, b) => (ppl[a] - ppl[b]) || (speed(b) - speed(a)))[0];
  }
  return (data.variants && data.variants[0]) || null;
}

/** Infer a short vertical label from the manifest, for filter chips/badges. */
export function verticalOf(data = {}) {
  const hay = `${data.slug || ''} ${data.base_model || ''} ${data.vertical_eval_name || ''}`.toLowerCase();
  if (/patent|mpep/.test(hay)) return 'patent';
  if (/finance|bank/.test(hay)) return 'finance';
  if (/saul|legal|law/.test(hay)) return 'legal';
  if (/security|cyber/.test(hay)) return 'cyber';
  if (/medical|clinical|ii-medical/.test(hay)) return 'medical';
  return 'general';
}
