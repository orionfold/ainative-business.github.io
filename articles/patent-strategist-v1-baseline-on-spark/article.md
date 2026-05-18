---
title: "Three-Mode Bracket: Baselining a Reasoning Model Before Fine-Tuning, On One Spark"
date: 2026-05-17
author: Manav Sehgal
product: Foundation
stage: fine-tuning
difficulty: advanced
time_required: "~10 hours (mostly automated overnight sweeps)"
hardware: "NVIDIA DGX Spark"
tags: [eval, rag, reasoning-models, llama-cpp, deepseek-r1, vertical-bench, patent-strategist]
summary: "Before you fine-tune a small reasoning model on a domain bench you need to know where it stands. Three context modes — closed, retrieval, oracle — triangulate the model's ceiling on one Spark, no Judge backend or cluster required."
signature: PatentBracketSignature
---

A small reasoning model dropped onto a 200-row patent-law bench will answer every multiple-choice question with a 3000-token think trace, and every claim-rewrite question with a confident draft. That doesn't tell you whether the model knows patent law. It tells you the model knows how to answer questions. The interesting signal is somewhere underneath — and you can't get to it without bracketing.

The bracket is three runs over the same bench, varying only one thing: what context, if any, the model gets to see before it answers. **Closed-book** gives the model nothing — pure parametric knowledge. **Retrieval** gives it the top-eight chunks from a BGE-small / FAISS index over the MPEP, BigPatent abstracts, and the HPI-Naumann PatentMatch corpus. **Oracle** gives it the gold passage the bench author anchored the question to. The closed-book score is the floor — what the model already knows. The oracle score is the ceiling — what the model could do if retrieval were perfect. Retrieval lands somewhere in between, and the *shape* of that landing is the engineering signal: how much does retrieval close the gap, and does the gap close uniformly across question shapes or only on the ones where the corpus actually contains the answer?

This article is the methodology piece. The model is `DeepSeek-R1-0528-Qwen3-8B`, quantized to `Q5_K_M`, running under `llama.cpp` on a DGX Spark — about five and a half gigabytes of weights on disk, eight gigabytes of unified memory at inference time, comfortable next to a 124 GB envelope. The bench is `patent-strategist-v0.1` — 200 hand-anchored questions across seven shapes (claim drafting, prior-art ranking, prosecution argument, MPEP rule-application MCQs, IRAC structured answers, and two judge-rubric shapes deferred to a later cycle). The eval driver is ~580 lines of stdlib Python. The whole bracket runs in roughly nine hours of unattended wall time — overnight on the Spark, with no cloud, no Judge backend, and no cluster.

## Why this matters for a personal AI builder

The disconnect between "I have a domain-specific corpus" and "I have a model that handles my domain" is a real cliff in practice. Cloud playgrounds aren't going to tell you where your model is on that cliff — they don't have your corpus. Fine-tuning without baselining is a recipe for cooking compute against a moving target. The three-mode bracket is the smallest experimental design that answers "is fine-tuning worth running?" — and a 128 GB unified-memory Spark is exactly the hardware envelope where one practitioner can run all three modes, look at the results, and decide.

There's a deeper unlock here too: this is the same scaffold any vertical-bench needs. The patent specifics — MPEP sections, IRAC structure, prior-art ranking — are interchangeable parts. Replace the corpus, replace the question shapes, swap the scorers, and you have a finance-strategist bench, a clinical-reasoning bench, a security-analyst bench. Owning the bracket means owning the iteration loop, and owning the iteration loop on one machine means you can run cycle-after-cycle without renegotiating cluster budget every time.

## Where this sits in the stack

The eval scaffold is four parts: a bench (rows on disk, in JSONL), a retrieval index (FAISS + BGE-small embeddings), an inference backend (`llama-server` serving an OpenAI-compatible chat endpoint), and a driver that fuses them. Each part has a degree of freedom; the discipline of the design is keeping the *bench* fixed across runs while varying only the *context strategy* fed into the model.

<figure class="fn-diagram" aria-label="Three-mode bracket: closed, retrieval, and oracle routes converge on the same R1-0528-Qwen3-8B model and the same scorer, varying only what context is prepended to the question. D-mcq scores are 0.625 closed, 0.85 retrieval, 0.95 oracle.">
  <svg viewBox="0 0 900 440" role="img" preserveAspectRatio="xMidYMid meet" aria-label="Three-mode bracket: closed, retrieval, and oracle routes converge on the same R1-0528-Qwen3-8B model and the same scorer, varying only what context is prepended to the question. D-mcq scores are 0.625 closed, 0.85 retrieval, 0.95 oracle.">
    <defs>
      <linearGradient id="three-mode-lane-closed" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-indigo)" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="var(--svg-accent-indigo)" stop-opacity="0.04"/>
      </linearGradient>
      <linearGradient id="three-mode-lane-retrieval" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.20"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.04"/>
      </linearGradient>
      <linearGradient id="three-mode-lane-oracle" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.22"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.04"/>
      </linearGradient>
      <linearGradient id="three-mode-accent" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.32"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="three-mode-modelhalo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.36"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="three-mode-scorerhalo" cx="0.5" cy="0.5" r="0.6">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.40"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="20" y="40" width="320" height="100" rx="10" fill="url(#three-mode-lane-closed)" stroke="none"/>
    <rect x="20" y="170" width="320" height="100" rx="10" fill="url(#three-mode-lane-retrieval)" stroke="none"/>
    <rect x="20" y="300" width="320" height="100" rx="10" fill="url(#three-mode-lane-oracle)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 340 90 L 620 215" stroke="var(--svg-accent-indigo)" stroke-opacity="0.75"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 340 220 L 620 220" stroke="var(--svg-accent-blue)" stroke-opacity="0.85"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 340 350 L 620 225" stroke="var(--color-primary)" stroke-opacity="0.80"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 760 220 L 840 220"/>
    </g>
    <g class="fn-diagram__lane-scores">
      <text x="362" y="96" fill="var(--svg-accent-indigo)" font-family="var(--font-mono)" font-size="22" font-weight="700">0.625</text>
      <text x="362" y="112" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="10" letter-spacing="0.08em">D-mcq · closed</text>
      <text x="362" y="226" fill="var(--svg-accent-blue)" font-family="var(--font-mono)" font-size="22" font-weight="700">0.850</text>
      <text x="362" y="242" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="10" letter-spacing="0.08em">D-mcq · retrieval</text>
      <text x="362" y="356" fill="var(--color-primary)" font-family="var(--font-mono)" font-size="22" font-weight="700">0.950</text>
      <text x="362" y="372" fill="var(--svg-text-faint)" font-family="var(--font-mono)" font-size="10" letter-spacing="0.08em">D-mcq · oracle</text>
    </g>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="40" y="60" width="280" height="60" rx="8"/>
      <rect class="fn-diagram__node" x="40" y="190" width="280" height="60" rx="8"/>
      <rect class="fn-diagram__node" x="40" y="320" width="280" height="60" rx="8"/>
      <circle cx="690" cy="220" r="80" fill="url(#three-mode-modelhalo)"/>
      <rect class="fn-diagram__node fn-diagram__node--accent" x="620" y="180" width="140" height="80" rx="8" style="fill: url(#three-mode-accent)"/>
      <circle cx="860" cy="220" r="36" fill="url(#three-mode-scorerhalo)"/>
      <rect class="fn-diagram__node" x="840" y="180" width="40" height="80" rx="8"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label" x="180" y="86" text-anchor="middle">Closed-book</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="180" y="106" text-anchor="middle">no context prepended</text>
      <text class="fn-diagram__label" x="180" y="216" text-anchor="middle">Retrieval (BGE-small + FAISS)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="180" y="236" text-anchor="middle">top-8 chunks · 39,777 vectors</text>
      <text class="fn-diagram__label" x="180" y="346" text-anchor="middle">Oracle (seeded anchor)</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="180" y="366" text-anchor="middle">gold passage from bench row</text>
      <text class="fn-diagram__label" x="690" y="210" text-anchor="middle">R1-0528-Qwen3-8B</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="690" y="232" text-anchor="middle">Q5_K_M · think + answer</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="860" y="225" text-anchor="middle">scorer</text>
    </g>
  </svg>
  <figcaption>Three runs, one variable. The lanes differ only in what is prepended to the question; the model, the prompt template, and the scorer hold constant. The right-edge numbers are the D-mcq accuracy at the end of each lane — the closed-to-retrieval lift is 2.25× the retrieval-to-oracle gap.</figcaption>
</figure>

The bench itself was seeded in a prior session — 200 rows generated by Claude Opus against anchored corpora (MPEP subsections, BigPatent abstracts, EPO PatentMatch claim pairs). 60 of those rows are synthesized from anchor text; 140 are direct rewrites of anchored material with no model in the loop. Distribution: 50 claim-rewrite (A), 40 prior-art ranking (B), 20 landscape essays (C), 40 procedural MCQs (D-mcq), 10 office-action responses (D-oa), 10 IRAC-structured arguments (D-irac), 30 strategy essays (E). Five of those shapes have deterministic or rank-based scorers; two (C and E) need an LLM-as-judge that this session deliberately defers. Out of the deterministic-scored shapes, only D-mcq and D-irac produce numbers without a Judge — A and D-oa are wired to scorers that take a `judge` keyword and fall through to `None` in this bracket. That's a feature, not a bug: the bracket is meant to ship without a Judge in scope.

## The journey

### Picking the model

The decision sat between two families. **Continued-pretrain shapes** like `instruction-pretrain/finance-Llama3-8B` are tempting because they advertise domain specialization out of the box — but the namespace is misleading. Microsoft's instruction-pretrain methodology is *pre-training*, not chat fine-tuning, and these models ship without a `chat_template` of any kind. The trap is real enough that it cost a full vertical-curator cycle in a prior session before being caught. **Reasoning-distill models** like `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` are the alternative — Qwen3 base, distilled against R1's reasoning traces, with a proper Hermes-style chat template baked in. The chat-vs-continued-pretrain test is one regex over the model card: search for `chat_template`, `SFT`, `DPO`, `Hermes`, `Tulu`, or `Zephyr`. None of those? Skip.

R1 has a second property that matters for a bench heavy on MCQs and structured arguments: the `<think>...</think>` block. When a reasoning model is asked a procedural patent question — "Under MPEP 716.05, expert skepticism is relevant to which statutory basis?" — it explicitly reasons through the four options before naming one. That's gold for an MCQ scorer that can strip the think block and look at the conclusion. It's also a liability — the think trace eats tokens, and if the answer comes after the trace exhausts the budget, the model never reaches the answer. More on that in §Tradeoffs.

### Picking the quantization

Q5_K_M sits at the sweet spot for a Spark workload — 5.5 GB on disk, ~6.5 GB resident with KV cache for 16K context, room to spare on the 128 GB unified envelope. The instinct is to reach for Q8_0 instead — fewer quantization errors, closer to fp16 — but the throughput math has surprised us before. On continued-pretrain shapes Q8_0 has been ~30 % faster than fp16; on chat-tune shapes Q8_0 has been ~75 % slower. The split runs along the model lineage in a way that's hard to predict without testing. For R1, Q5_K_M is well-trodden ground (Bartowski publishes the canonical GGUF), and the per-token latency at this quant is dominated by the reasoning trace length anyway, not by the quant precision. The decision: ship Q5_K_M, log the latency distribution, revisit if results suggest the quant is the bottleneck.

```bash
HF_HUB_CACHE=/home/nvidia/data/.hf-cache/hub HF_HOME=/home/nvidia/data/.hf-cache \
  hf download bartowski/deepseek-ai_DeepSeek-R1-0528-Qwen3-8B-GGUF \
    deepseek-ai_DeepSeek-R1-0528-Qwen3-8B-Q5_K_M.gguf \
    --local-dir /home/nvidia/data/quants/DeepSeek-R1-0528-Qwen3-8B/
```

Two things to know about that command. First, the deprecated `huggingface-cli` exits with status 0 even when it downloads nothing — switch to `hf` or the script silently succeeds against an empty destination. Second, the default HF cache (`~/.cache/huggingface`) on this Spark is root-owned from earlier in-container `sudo`'d downloads, so any HF-touching code must override `HF_HUB_CACHE` and `HF_HOME` or it crashes with `PermissionError [Errno 13]` on the first `SentenceTransformer(...)` call. The transfer itself ran around 28 MB/s with the token exported — about three minutes for the full 5.5 GB.

### Standing up llama-server

The CUDA-built `llama.cpp` is at `/home/nvidia/llama.cpp/build/bin/llama-server`. Three flags matter for this workload:

```bash
/home/nvidia/llama.cpp/build/bin/llama-server \
  -m /home/nvidia/data/quants/DeepSeek-R1-0528-Qwen3-8B/deepseek-ai_DeepSeek-R1-0528-Qwen3-8B-Q5_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  -c 16384 -ngl 99 \
  --temp 0.6 \
  --reasoning-format none \
  --alias deepseek-r1-0528-qwen3-8b
```

`-ngl 99` offloads every transformer layer to the GB10 — full GPU inference. `-c 16384` is the context window; 16K is generous for retrieved contexts of eight chunks plus a question plus a 4K-token completion budget. `--temp 0.6` is the DeepSeek-recommended sampling temperature for R1-distill — lower than the GGUF default of 0.8, which keeps the reasoning trace coherent. `--reasoning-format none` is the critical one: it leaves the entire response (think block plus answer) in `message.content` rather than extracting the think into a separate `reasoning_content` field. The scorer downstream strips think on its own; we want the raw, full output in one field. Loading takes about ten seconds; the server settles into the chat-template detection and the listening line:

```text
srv    load_model: prompt cache is enabled, size limit: 8192 MiB
srv          init: init: chat template, thinking = 1
main: model loaded
main: server is listening on http://0.0.0.0:8080
main: starting the main loop...
srv  update_slots: all slots are idle
```

Two lines of that block are worth a second look. `chat template, thinking = 1` is llama-server confirming that the GGUF carries a `<think>...</think>` template — without that detection, the server would treat the think trace as ordinary content and the scorer's think-strip would have nothing to strip. `prompt cache is enabled, size limit: 8192 MiB` is a free win for an overnight sweep: repeated queries against the same retrieved chunks reuse the cached prefix, shaving the prompt-eval cost on every D-mcq batch that shares a top-k chunk.

Once requests start flowing, each completion logs its own timing block. A typical D-mcq query — short prompt, short answer letter, but ~600 tokens of `<think>` in between — looks like this:

```text
prompt eval time =      38.10 ms /     4 tokens (    9.53 ms per token,   104.98 tokens per second)
       eval time =    6828.27 ms /   240 tokens (   28.45 ms per token,    35.15 tokens per second)
      total time =    6866.38 ms /   244 tokens
```

Thirty-five tokens a second is the steady-state generation rate on this Spark for R1-0528-Qwen3-8B Q5_K_M — about half the rate of a non-reasoning Qwen3-8B at the same quant, which is the price of the think block. Multiply that by the typical 600-token think+answer envelope and a D-mcq row clears in about twenty seconds. A D-irac row that runs the trace out to 1500 tokens lands closer to forty-five.

### The driver

The eval driver — `scripts/run_rag_baseline.py` — is around 580 lines of stdlib Python (plus `faiss`, `sentence-transformers`, and `fieldkit.eval` as external dependencies). Its job is small and well-bounded: load bench rows, optionally retrieve or attach oracle context, build a prompt, call the chat endpoint, dispatch the response to a scorer, write a row to `predictions.jsonl`, and aggregate `scores.json` at the end. The driver runs three times — once per mode — against the same 200-row bench, writing to a fresh `evidence/patent-strategist/baseline-runs/<run-id>/` directory each time. A small shell script chains the three runs together: when one driver exits, the next mode starts automatically.

```python
SYSTEM_PROMPT = (
    "You are a U.S. patent attorney and patent strategist. Answer the question "
    "precisely and concisely. If a context section is provided, ground your "
    "answer in it. For multiple-choice questions, end your answer with "
    "'Answer: <letter>'."
)
```

The system prompt is deliberately short. One sentence of role, one sentence on context grounding, one sentence on output format for MCQs. Reasoning models punish elaborate system prompts — they tend to incorporate the prompt's structure into the reasoning trace, lengthening it. The output-format clause is the load-bearing part of the prompt: it tells the model how the scorer will read the answer, which keeps the model from emitting "the answer would be the third option" instead of "Answer: C".

## Verification — what success looks like on DGX Spark

Verification has two layers: per-row plausibility and across-mode coherence.

**Per-row plausibility** is easiest to read off a single prediction's structure. A healthy R1 response on a D-mcq row looks like ~3000-4000 characters of `<think>...</think>` followed by 200-600 characters of post-think prose ending in `Answer: C`. The think block walks through the four options, eliminating distractors and converging on the chosen letter. The post-think prose paraphrases the conclusion. The first row of the retrieval-mode run lands at 89 seconds wall — the warm-up cost — and subsequent D-mcq rows settle around 25-40 seconds. Claim-rewrite rows are heavier (60-120 seconds), prior-art ranking rows are heavier still because the model emits five separate queries.

**Across-mode coherence** is read off the `per_shape` block of `scores.json`. The bracket is internally consistent if oracle ≥ retrieval ≥ closed on every shape that has real comparison signal. Inverted gaps — retrieval scoring worse than closed-book — usually mean the retrieved context is misleading the model rather than helping it. Equal gaps — oracle == retrieval == closed — usually mean the question doesn't actually require the corpus to answer.

```bash
$ free -h
               total        used        free      shared  buff/cache   available
Mem:           121Gi        22Gi        80Gi       132Mi        20Gi        99Gi
```

The Spark sits at 22 GB used during the sweep — that's llama-server's weights and KV cache (~8 GB), the FAISS index and embedder loaded in the driver Python process (~2 GB), and the OS plus the dev environment for everything else. Plenty of headroom; no risk of unified-memory pressure stalling either process.

## What the bracket revealed

All three modes are in. The overall means trace a clean ladder — closed 0.397, retrieval 0.489, oracle 0.541 across the 90 scorer-supported rows (B + D-mcq + D-irac) — and the per-shape breakdown is where the structure lives.

| Shape    | Closed-book | Retrieval | Oracle | Scorer                           |
|----------|-------------|-----------|--------|----------------------------------|
| D-mcq    | **0.625**   | **0.850** | **0.950** | regex letter pick + think strip  |
| D-irac   | **1.000**   | **1.000** | **1.000** | IRAC checklist (regex)           |
| B        | 0.018       | 0.000     | 0.017  | Spearman ρ on item lists         |
| Overall  | **0.397**   | **0.489** | **0.541** | mean over 90 scorer-supported rows |
| A        | (no Judge)  | —         | —      | rubric, deferred                 |
| D-oa     | (no Judge)  | —         | —      | rubric, deferred                 |
| C, E     | (no Judge)  | —         | —      | judge_rubric, deferred           |

The numbers that matter: **D-mcq climbs from 0.625 closed → 0.85 retrieval → 0.95 oracle.** That's the cleanest signal in the bracket. Closed-book at 0.625 says the model already knows about three out of five MPEP rules-of-thumb from pretraining alone — better than a coin flip, well below a passing grade. Retrieval adds 22.5 percentage points; oracle adds another 10. The closed-to-retrieval lift is more than double the retrieval-to-oracle lift, which means **the BGE-small/FAISS index is doing real work** — most of the available gain from external context is being delivered, and the residual gap to oracle is the part where retrieval pulls in a *related-but-wrong* MPEP subsection. Spot-checking confirms it: on procedural-prosecution rows that anchor to MPEP §2141 (obviousness), rank-0 retrieval scores at cosine ~0.75 — the right section, near the top.

D-irac scoring 1.0 across modes is a different kind of finding. The IRAC scorer is structural — it regex-checks for Issue / Rule / Application / Conclusion markers in the response. R1 emits IRAC structure on its own, regardless of whether the prompt mentions IRAC, because the reasoning trace naturally walks that shape. The 1.0 is more a property of the model's output format than a measure of its legal reasoning. That's a real limitation of the scorer, not a triumph of the model; the W4 pass will pair IRAC structure with a content scorer that checks whether the *Rule* identified actually maps to the question's statutory basis.

B scoring 0.0 across retrieval and oracle is the third kind of finding — a scorer/format mismatch caught only when the numbers came in. The seeder produced gold rankings as five descriptive phrases of the form `"device cooperation service information registration combined device function operation definition file"` — bag-of-keyword retrieval cues. The model, asked to draft "five prior-art retrieval queries", paraphrases naturally — `"receiving a list from predetermined device"`, `"determining operation inclusion via function combination"`. The B scorer rank-correlates exact string matches between the two lists. With zero string overlap, Spearman ρ collapses to ~0. The numerator on B is not the model's weakness; it's the scorer's assumption that the publish-cycle of the bench would produce normalized phrases. W4 fixes that with either fuzzy string matching, embedding-cosine matching, or a judge-rubric scorer.

## Tradeoffs, gotchas, surprises

Three bugs landed in the eval scaffold itself, caught mid-flight. They're worth naming.

**The options-blind prompt.** The first version of the eval driver passed only the `question` field to the model. For free-form shapes that's fine — the question is self-contained. For D-mcq rows the `options` field carries the four lettered choices, and dropping them on the floor means the model is being asked a question it cannot possibly answer without inventing the options to choose from. Caught after the 5-row smoke test happened to score 5/5 (R1 invented the four likely letters and ran into the gold), then re-verified by inspecting the first prompt sent to the server. One-line fix: pass the options list into `build_user_prompt` and render them as labeled choices. Cost: about ten minutes; would have been three days if discovered after a full overnight run.

**The first-Option-wins scorer bug.** `fieldkit.eval.mcq_letter` extracts the model's letter choice from prose using a regex that looks for `\b(answer|choice|option)\b ... [A-D]`. The regex uses `re.search`, which returns the *first* match. R1's habit on a D-mcq row is to say "Option A is incorrect because… Option D is incorrect because… Answer: B." First match: A. The scorer reports the model picked A — wrong. Fix: switch to `re.findall` and use the *last* match. The shift biases toward the model's concluding pick rather than its eliminated distractors. Caught about 130 rows into the retrieval sweep when D-mcq rows showed `Answer: B` in the prediction text but scored 0; verified against a 25-test pytest suite that all pass with the new logic; rescored the in-flight predictions in place using a small `rescore_predictions.py` helper that re-applies the patched scorer without re-running inference. Net lift on retrieval D-mcq: 0.775 → 0.850, +3 rows correct out of 40.

**Token truncation mid-think.** The driver's default `max_tokens` is 4096. About 20 % of A-shape claim rewrites and 40 % of B-shape ranking rows exhaust that budget *while still inside the `<think>` block*, so the model never emits the post-think answer. The fix is one of two: bump `max_tokens` to 8192 (doubles wall time on the truncated rows), or use llama-server's `--reasoning-budget N` to force a transition to the answer once the think trace consumes N tokens. For W4, `--reasoning-budget 2048` is the cleaner knob — it caps reasoning at a level that still produces useful traces and leaves a 2K-token budget for the actual answer. The current bracket holds `max_tokens=4096` constant across the three modes so the comparison is matched; the truncation rate is the same on closed/retrieval/oracle and washes out of the gap analysis.

The deeper meta-tradeoff: shipping a bench-and-bracket scaffold before a Judge backend is in scope means accepting that two of seven question shapes have no numbers in this pass. That's the right cost. Judge backends have their own validation work — calibration against human graders, rubric drift across model versions, the cost of re-running judgments after the rubric changes. Pulling that into the same session as the inference bracket would have doubled the surface area and probably surfaced a different set of bugs. The W4 pass adds Judge backends with the scaffold *already known to work*, and any new bugs show up against a baseline whose dynamics are already understood.

## What this unlocks

Three concrete next steps off the back of this bracket:

**Targeted fine-tuning, not blanket fine-tuning.** The D-mcq spread — 0.625 closed → 0.85 retrieval → 0.95 oracle — answers the lever question directly. Closed is 22.5 percentage points below retrieval, so the model genuinely doesn't know enough patent procedure to score well unaided. Fine-tuning has real headroom to close that gap. Retrieval is only 10 points below oracle, so the embedder is already pulling in mostly-right context; a stronger retriever (BGE-large, or a domain-tuned embedder over the MPEP) would buy back at most those 10 points and only on the residual fraction where retrieval misses. The bracket says: fine-tune the model first, retriever upgrades later.

**A reusable scaffold for the next vertical.** The patent-strategist pieces of this pipeline — the MPEP corpus puller, the PatentMatch downloader, the IRAC scorer — are vertical-specific. The bracket itself is not. A clinical-reasoning bench replaces MPEP with MeSH/PubMed and the IRAC regex with a SOAP-note regex; a security-analyst bench replaces them with MITRE ATT&CK and an incident-template regex. Same driver, same modes, same overnight cadence. Each new vertical is a corpus + a question generator + a handful of scorers, not a rebuild of the eval system.

**Honest scorer auditing under reasoning models.** The two scorer bugs caught here — options-blind prompts, first-Option-wins regex — are not unique to patent law. They're failure modes of building an eval scaffold against a model class (reasoning-distill) whose output format is different from earlier instruction-tuned models. Every scorer in `fieldkit.eval` that was promoted from cyber, medical, or finance benches deserves a second look under R1-distill traffic. The bracket is the place where those failure modes show up cheaply — a 20-row smoke per shape will surface most of them in an hour, against a 200-row full sweep that would cost five.

## Closing

The DGX Spark's promise has always been that one practitioner can hold the whole iteration loop on one machine. The three-mode bracket is one of the loops worth holding — small enough to run in a session, big enough to settle a real fine-tuning decision, durable enough to point at the next vertical. The patent corpus is interchangeable; the bracket scaffolding is the lasting asset.

Next up in the arc: with the bracket complete and the closed-to-retrieval gap measured at 22.5 points on D-mcq, the W3 fine-tune begins — a Qwen3-8B-based GRPO loop against the deterministic-scorable shapes (D-mcq, D-irac), targeting that gap directly.
