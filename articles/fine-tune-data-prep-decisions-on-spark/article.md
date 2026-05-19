---
title: "The Trainer Was Fine, the Corpus Wasn't: Three Misdiagnoses on a Patent-Specialist Fine-Tune"
date: 2026-05-19
author: Manav Sehgal
product: Foundation
stage: fine-tuning
difficulty: advanced
time_required: "~12 hours (2× 131-min trains + diagnosis)"
hardware: "NVIDIA DGX Spark"
tags: [fine-tuning, lora, sft, trl, r1-distill, patent-strategist, data-prep, corpus-quality, deep-seek, dgx-spark]
summary: "Five thousand rows of synthetic patent reasoning, two clean 131-minute LoRA trains, three rounds of confident diagnosis — and none of them found the bug. The bug was the corpus all along. A field report on the cheapest mistake to make on the Spark."
signature: CorpusContaminationLayers
series: Machine that Builds Machines
---

The model thinks in Korean for a while, then starts repeating itself.

It is supposed to be an English-speaking patent strategist. I have just spent 131 minutes training it on five thousand rows of synthetic patent reasoning. The loss curve descended cleanly from 3.17 to 1.21. The layer-1 isolation check confirmed only the attention projections moved. The merged BF16 weights sit at 16 gigabytes on disk. Everything looks right. Then I run the first probe row — an AIME-style math problem chosen specifically because the spec wants the fine-tune to *preserve* general reasoning — and the model opens a `<think>` block, generates a string of Korean Hangul characters rendered as Latin-1 mojibake, finds an actual factorization of 1000 in there somewhere, and then falls into a loop. The same sentence repeats forty-some times. The MNT=4096 budget burns to zero. The `<think>` block never closes.

This is the second time this has happened. The first time, I had a confident diagnosis — missing BOS/EOS tokens in the training text — and a one-line code fix. I shipped it, retrained for 131 minutes, ran the probe again, watched the same failure, and finally realized the diagnosis was wrong. Then I had a second confident diagnosis — catastrophic forgetting on out-of-distribution input — which was *also* wrong, or at least incomplete. The actual bug had been sitting in the corpus the entire time. Fifty-six percent of the rows contained the synth pipeline's internal scaffolding, leaked verbatim into the `<think>` block. The model learned the scaffolding as if it were patent reasoning. The trainer was fine. The corpus wasn't.

## Why this matters for a personal AI builder

When you fine-tune on a single GPU, every diagnostic round costs you a real chunk of your evening. A 131-minute train plus a 30-minute probe plus the diagnostic time around them is half a working day. If you're using a cap-bound LLM (Max 20x weekly tokens, in my case) to synthesize the corpus, every retry also burns a fraction of that cap. The asymmetry between "spending an hour examining your corpus before training" and "spending three hours training on a corpus and then debugging the probe" is not subtle — it's twenty-to-one in favor of looking at the corpus.

:::why[Corpus quality gates are the cheapest gates you'll ever build]
Mechanical gates — line count, `<think>` presence, character length — pass at near-zero cost. Content gates — *does the think block actually contain patent reasoning?* — cost slightly more but still pennies on the dollar compared to one wrong train. Skipping them moves the same diagnostic load to expensive checkpoints downstream, which is where I learned it.
:::

The lesson is portable. Anyone building an MTBM-shaped pipeline on the Spark — a small reasoning model fine-tuned on a corpus their agent generated — is going to be in this same loop: the agent synthesizes, the trainer absorbs, the probe judges. The bug can hide at any layer, but the cheapest layer to inspect is also the layer where defects are most likely to be introduced and most likely to cascade. This article is a field report on what that loop looks like when it goes wrong and how the misdiagnoses chain together.

## The pipeline I thought I was running

The W3 patent-strategist pipeline has four stages and one fork-in-the-road decision baked in upstream of the trainer:

<figure class="fn-diagram" aria-label="The intended W3 pipeline runs synth → corpus → trainer → probe → publish in a clean line. What actually happened diverged at probe-time: round 1 diagnosed a missing-EOS bug and retrained, round 2 diagnosed catastrophic forgetting, round 3 finally inspected the corpus and found 56 percent of rows leaking the producer subagent's internal state. The real bug was upstream of the trainer all along.">
  <svg viewBox="0 0 900 440" role="img" preserveAspectRatio="xMidYMid meet" aria-label="The intended W3 pipeline runs synth → corpus → trainer → probe → publish in a clean line. What actually happened diverged at probe-time: round 1 diagnosed a missing-EOS bug and retrained, round 2 diagnosed catastrophic forgetting, round 3 finally inspected the corpus and found 56 percent of rows leaking the producer subagent's internal state. The real bug was upstream of the trainer all along.">
    <defs>
      <linearGradient id="d01-intended-lane" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-blue)" stop-opacity="0.16"/>
        <stop offset="100%" stop-color="var(--svg-accent-blue)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d01-actual-lane" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--svg-accent-red)" stop-opacity="0.14"/>
        <stop offset="100%" stop-color="var(--svg-accent-red)" stop-opacity="0.02"/>
      </linearGradient>
      <linearGradient id="d01-corpus-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.32"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0.08"/>
      </linearGradient>
      <radialGradient id="d01-corpus-halo" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="var(--color-primary)" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="20" y="40" width="860" height="170" rx="10" fill="url(#d01-intended-lane)" stroke="none"/>
    <rect x="20" y="240" width="860" height="170" rx="10" fill="url(#d01-actual-lane)" stroke="none"/>
    <g class="fn-diagram__edges">
      <path class="fn-diagram__edge" pathLength="100" d="M 180 125 L 280 125"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 400 125 L 500 125"/>
      <path class="fn-diagram__edge" pathLength="100" d="M 620 125 L 720 125"/>
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 180 325 L 280 325"/>
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 400 325 L 500 325"/>
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 620 325 L 720 325"/>
      <path class="fn-diagram__edge fn-diagram__edge--dashed" pathLength="100" d="M 560 280 L 560 250"/>
      <path class="fn-diagram__edge fn-diagram__edge--accent" pathLength="100" d="M 340 280 L 340 165"/>
    </g>
    <rect x="20" y="85" width="160" height="80" rx="10" fill="url(#d01-corpus-halo)" stroke="none"/>
    <g class="fn-diagram__nodes">
      <rect class="fn-diagram__node" x="20" y="85" width="160" height="80" rx="10"/>
      <rect class="fn-diagram__node fn-diagram__node--accent fn-diagram__pulse" x="280" y="85" width="120" height="80" rx="10" style="fill: url(#d01-corpus-grad)"/>
      <rect class="fn-diagram__node" x="500" y="85" width="120" height="80" rx="10"/>
      <rect class="fn-diagram__node" x="720" y="85" width="160" height="80" rx="10"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="20" y="285" width="160" height="80" rx="10"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="280" y="285" width="120" height="80" rx="10"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="500" y="285" width="120" height="80" rx="10"/>
      <rect class="fn-diagram__node fn-diagram__node--ghost" x="720" y="285" width="160" height="80" rx="10"/>
    </g>
    <g class="fn-diagram__labels">
      <text class="fn-diagram__label fn-diagram__label--mono" x="100" y="68" text-anchor="middle">intended</text>
      <text class="fn-diagram__label" x="100" y="120" text-anchor="middle">synth</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="100" y="140" text-anchor="middle">5000 rows</text>
      <text class="fn-diagram__label" x="340" y="120" text-anchor="middle">corpus</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="340" y="140" text-anchor="middle">56% contam</text>
      <text class="fn-diagram__label" x="560" y="120" text-anchor="middle">trainer</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="560" y="140" text-anchor="middle">LoRA r=16</text>
      <text class="fn-diagram__label" x="800" y="120" text-anchor="middle">probe + publish</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="800" y="140" text-anchor="middle">20q gate</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="100" y="268" text-anchor="middle">actual — three rounds of misdiagnosis</text>
      <text class="fn-diagram__label" x="100" y="320" text-anchor="middle">round 1</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="100" y="340" text-anchor="middle">BOS / EOS</text>
      <text class="fn-diagram__label" x="340" y="320" text-anchor="middle">round 2</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="340" y="340" text-anchor="middle">forgetting</text>
      <text class="fn-diagram__label" x="560" y="320" text-anchor="middle">round 3</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="560" y="340" text-anchor="middle">corpus audit</text>
      <text class="fn-diagram__label" x="800" y="320" text-anchor="middle">root cause</text>
      <text class="fn-diagram__label fn-diagram__label--mono" x="800" y="340" text-anchor="middle">meta-leakage</text>
    </g>
    <g class="fn-diagram__annotations">
      <text class="fn-diagram__annotation" x="340" y="78" text-anchor="middle">the bug lived here</text>
      <text class="fn-diagram__annotation" x="450" y="250" text-anchor="middle">3 hours wasted before this loop closed</text>
    </g>
  </svg>
  <figcaption>Two layers of the same pipeline. Each round of probe-time diagnosis looked downstream of where the bug actually lived. The third round finally walked back to the corpus and found 56 percent of rows leaking the synth pipeline's internal state into the training signal.</figcaption>
</figure>

The intended path is the top row: a `claude-corpus-synth` skill drives an in-CC-session fan-out that produces five thousand patent-reasoning rows; the rows feed a TRL `SFTTrainer` with a LoRA adapter on `DeepSeek-R1-0528-Qwen3-8B`'s q/k/v/o projections; the trainer emits a merged BF16 model; a twenty-row reasoning-preservation probe judges whether `<think>` blocks still open and close cleanly across general-reasoning + patent rows; if the gate passes, the model goes to Hugging Face as `Orionfold/patent-strategist-v1-GGUF` alongside a paired bench dataset. Standard MTBM-shape pipeline. Each piece had been validated independently on smaller artifacts.

The actual path is the bottom row. The probe failed on the first row, three times in a row, across two complete trains. Every round of diagnosis targeted a different layer downstream of where the bug actually lived. The third round was the first one that walked back upstream of the trainer.

:::define[LoRA r=16 attention-only]
A parameter-efficient fine-tuning configuration where rank-16 low-rank adapters are inserted at the q, k, v, and o projections of every attention layer. The MLP layers are frozen. Adapter parameters add 0.01 percent of the base model's size; the spec calls this "Layer 1 isolation" because only attention pathways update during training.
:::

## Round 1: the BOS/EOS diagnosis that wasn't

The first train completed at 08:32 on the morning of session 39 — 128 minutes wall, exactly as predicted. The loss curve was textbook for an R1-Distill SFT: step 5 at 3.17, step 100 at 1.57, step 200 at 1.40, step 626 stable at 1.17 to 1.25. `mean_token_accuracy` climbed from 0.48 to 0.72. `grad_norm` held steady between 0.4 and 0.9. The Layer-1 isolation check confirmed only the attention LoRA tensors had moved. The merge stage wrote 16.38 gigabytes of BF16 in 47 seconds. Then I fired the probe.

The probe loads the model, then walks twenty pre-canned questions in three categories: ten AIME-style math problems, five patent-IRAC scenarios, five patent-strategic questions. For each row, it generates with `max_new_tokens=4096`, parses the response for `<think>...</think>` markers, records wall time. The baseline (raw R1-Distill, same probe, same MNT) had measured 0.60 think-presence rate and 1285-token mean think length. The fine-tune was supposed to clear at least 0.54 presence and 964 tokens to count as "reasoning-preserved."

The first row hit wall=369 seconds. `has_think=False`. The model had generated the full 4096-token budget without ever closing a `</think>` tag. The mean per-row wall on the baseline run had been 94 seconds. Something was clearly broken.

My first diagnosis was that the training text was missing BOS+EOS bookends. The synth pipeline produces rows shaped like `{"prompt": ..., "response": "<think>...</think>...answer"}`. The TRL `SFTTrainer` expects a `text` field. The conversion script I had written — `scripts/build_train_jsonl.py` — composed `text = f"<|User|>{prompt}<|Assistant|>{response}"` and nothing else. No `<｜begin▁of▁sentence｜>` at the front. No `<｜end▁of▁sentence｜>` at the back. The DeepSeek-R1 tokenizer's `encode()` doesn't auto-add either; I had verified this. The model had been trained on prompt-response pairs that never showed it where a row ended. *Of course* it didn't know when to stop.

```python
BOS = "<｜begin▁of▁sentence｜>"  # 151643
EOS = "<｜end▁of▁sentence｜>"    # 151645
text = f"{BOS}<｜User｜>{prompt}<｜Assistant｜>{response}{EOS}"
```

I wrote the one-line fix. I tokenized the first row inside the container and confirmed `ids[0] == 151643` and `ids[-1] == 151645`. I saved a memory entry — `feedback_sft_eos_bos_explicit` — so the next fine-tune wouldn't fall into the same trap. I scheduled the retrain. The first 131-minute train was now wall-clock debt.

:::pitfall[BOS/EOS in the corpus doesn't reach the loss if the trainer masks it]
Adding BOS/EOS markers to the corpus text is necessary but not sufficient. The data collator's labels-masking rules govern what reaches the loss function. With pad_token == eos_token, many transformers-default collators mask every EOS position in labels — but TRL's `DataCollatorForLanguageModeling` does not. I assumed the first behavior and re-encoded the corpus before checking which collator I was actually using. That assumption sent me down round one.
:::

## Round 2: the catastrophic-forgetting diagnosis that was also wrong

The second train completed at 11:38 on session 40 — 131 minutes wall, within ±5 minutes of the s39 reference. Same monotonic descent: step 5 at 3.17, step 100 at 1.59, step 200 at 1.49, step 626 stable at 1.17 to 1.25. Same layer-1 isolation. Same merge. Same probe. First row hit wall=399 seconds. `has_think=False`.

The retrain had not fixed the bug.

I went and read the TRL 1.4 source for `DataCollatorForLanguageModeling.torch_call()`. The relevant lines:

```python
output["input_ids"] = pad(input_ids, padding_value=self.pad_token_id, padding_side="right", ...)
output["labels"] = pad(labels, padding_value=-100, padding_side="right", ...)
```

The collator pads `labels` with the literal value `-100`, *not* by masking positions where `input_ids == pad_token_id`. The transformers-default `DataCollatorForLanguageModeling(mlm=False)` does the latter and would have masked every EOS position from the loss; the TRL version does not. The real EOS at the end of an unpadded sequence is, in fact, in the gradient. My round-one diagnosis had been wrong about the level the bug lived at. Adding EOS to the corpus had not changed the outcome because the outcome wasn't gated by corpus shape at the trainer.

So I reproduced the first probe row in isolation, with a script that only loaded the model, ran one generate, and dumped the raw output. The model generated 4096 tokens without closing `</think>`. The decoded output was the Korean mojibake + repetition loop I described in the opening. The same `<think>` token (`151667`) opened the block; nothing closed it. Mid-chain, the model had fallen into Korean Hangul rendered as Latin-1 bytes — the underlying language of R1-Distill's reasoning data, surfacing as the English-math mode collapsed — and then into a degenerate repetition: `1000=2^3*5^3` followed by the same Korean fragment repeating forty-some times until the budget ran out.

This was my round-two diagnosis: catastrophic forgetting on general-reasoning input. The corpus is 100% patent. The training has no general-reasoning rows. The model's broad pretraining mode has been suppressed by the LoRA in favor of patent reasoning, and on out-of-distribution prompts (AIME math) the residual reasoning mode is degraded. The fallback to Korean is consistent with R1-Distill's underlying multilingual reasoning data showing through where the surface English-math mode has been overwritten.

To check whether the patent side actually worked, I ran a patent-only filter of the probe — ten patent rows, no math — and let it complete.

```
patent-only overall:
  think_presence_rate: 1.00
  think_token_length:  126 tok  (vs baseline 1252 tok)
```

Ten out of ten patent rows opened *and* closed `<think>` blocks. The model stopped naturally between 52 and 189 seconds per row — comparable to the baseline's per-row range. The fine-tune *had* learned to emit and close think tags on patent prompts. The "catastrophic forgetting" diagnosis was partially right — general-reasoning had collapsed — but it was incomplete. The think length was an order of magnitude shorter than baseline (126 versus 1252 tokens). And when I started reading the actual content of those think blocks, the story shifted again.

:::define[Catastrophic forgetting]
The phenomenon where a fine-tuned model loses capabilities present in its base model on data distributions outside the fine-tuning corpus. With a 100% patent corpus on an 8B base, the model's general-reasoning mode is the most exposed — it had no positive training signal in this run, and only had to compete with the patent mode for shared attention weights.
:::

## Round 3: walking back to the corpus

I pulled up the patent-only probe output and started reading.

The MPEP citations were structurally correct. The IRAC format held. The model knew its way around §103, §112(a), §112(b), §102. It cited KSR v. Teleflex correctly. It invoked Nautilus v. Biosig and In re Robertson in roughly the right contexts. The reasoning was specialty-shaped, not generic. *And yet* — the words inside the think blocks ran together with no spaces. `Claim1.Awirelesschargingstationcomprising:aninductivecoilarrangedto…` was the actual output, not a transcription artifact. Worse: every `<think>` block started with what looked like a synth-pipeline annotation — `"A4 spice combinator: rejection is framed as…"`, `"duplicate of 3886. Diversify by emphasizing the §103 reasoning structure…"`, `"E1 duplicate of 12*17 (seen earlier). Diversify by showing different methods"`. And one row's response cited "Mayo Clinic v. Klein Electric, 564 U.S. 638 (2011)." Klein Electric does not exist. *Mayo Collaborative Services v. Prometheus Laboratories* is the case at that citation.

The model was emitting the producer subagent's *meta-state* as if it were patent reasoning. The "A4 spice combinator" prefix is something the corpus-build pipeline writes into its own working notes — the family designator (A1 / A2 / A4 / E1 / E2) plus a free-text variation tag. It should have been stripped before the row was ever committed to the corpus. It wasn't.

I wrote a quick audit:

```python
rows = [json.loads(l) for l in open('/home/nvidia/data/corpus/patent-prod-2026-05-19.jsonl')]
fam_prefix = re.compile(r'^(A[124]|E[12])(\s|:|\.|duplicate|spice)')

leak_prefix = sum(1 for r in rows if fam_prefix.match(extract_think(r['response'])[:30]))
leak_dup    = sum(1 for r in rows if 'duplicate of' in extract_think(r['response']).lower())
leak_div    = sum(1 for r in rows if 'diversify'    in extract_think(r['response']).lower())
```

The numbers:

| Leakage pattern | Rows | Share |
|---|---|---|
| Family-prefix in `<think>` (`A1 / A2 / A4 / E1 / E2 …`) | 2,797 | 56 % |
| `duplicate of N` annotation | 311 | 6 % |
| `diversify by …` instruction | 1,012 | 20 % |

Fifty-six percent. More than half of every think block in the training corpus started with the synth pipeline's family designator. The model had not learned to reason about patents starting from the prompt — it had learned to emit a family label, follow it with the synth pipeline's working notes, *then* reason. And because the family label is short and decisive (`A1`, `A4`, `E2`), the model had clearly internalized "start the chain with a short token-block, no spaces, then continue" as the structural prior. That structural prior is what produced the no-spaces output and the meta-annotation chum at the start of every chain.

The corpus had a defect rate measurable to the percent. The trainer had reproduced it faithfully. The probe had caught the failure but had blamed the wrong layer twice.

:::why[The synth pipeline's working notes are not training data]
The producer subagent inside `claude-corpus-synth`'s fan-out mode keeps a small amount of meta-state — what family this row is, whether it's a re-draft, what the diversification angle is — so that the verifier downstream can score variety. That state is supposed to stay in the producer's scratch space and only the cleaned think + answer should land in the corpus. Without an explicit strip step, the state bleeds through. The model can't tell the difference between "patent reasoning" and "the synth pipeline's annotation of patent reasoning"; both have the same surface shape.
:::

## The probe was probing for the wrong thing

The spec's reasoning-preservation gate requires think-presence rate ≥ 0.54 and mean think length ≥ 964 tokens, both relative to baseline. By those numbers, the s40 fine-tune fails: overall presence is 0.50, length is ~125. But the patent-only subset of the same probe shows the model emits and closes `<think>` perfectly — *exactly* what the gate is supposed to measure. The gate is doing its job, and the model is doing its job, *and the corpus is the problem*.

The gate measures emission. It does not measure content. A model that emits `<think>spicecombinatordiversifybyemphasizing§103</think>` will pass an emission gate as confidently as a model that emits `<think>The Examiner's §103 rejection is improper under KSR…</think>`. The difference is invisible to the regex. To catch the corpus contamination at probe time, the gate would need an LLM judge scoring think coherence — and that judge would need a content rubric for the domain. Otherwise the gate becomes "did the model emit *any* think block at all," which is a much weaker contract than the spec wanted.

This is the single most portable lesson of the W3 cycle. The shape of your probe has to match the shape of the failures you actually fear. An emission gate catches mechanics. A content gate catches semantics. They are different checks and they belong at different layers.

:::math[The probe budget you actually need]
Twenty rows × ~150 seconds per patent row + ~400 seconds per general-reasoning row × overhead ≈ 50 minutes of probe wall on a clean run. Adding an LLM judge step at 5 seconds per row + ~3000 tokens of grading prompt × 20 rows ≈ 60 000 judge-side tokens. That's ~$0.30 on Sonnet 4.6, or about 1 percent of one in-session generation row. The content gate is essentially free; the only reason to skip it is the small operational cost of writing the rubric.
:::

## What I'm taking forward

The trainer was untouched between session 39 and session 40. Same `SFTTrainer`, same hyperparameters, same image, same Layer-1 isolation result. Two clean trains, side by side, on a deterministic queue. The wall time was reproducible to within five minutes. The loss curves overlay. None of that was the problem; the trainer is, in fact, fine.

The corpus build pipeline was the problem, and the mechanical verifier was not equipped to catch it. The producer-subagent meta-state leakage was structural — every fan-out subagent had been emitting the same prefix pattern, and the verifier scored line count, `<think>` presence, length, and a whitelist of MPEP anchors. The verifier never asked "does this think text contain anything other than patent reasoning?" Adding even a one-line check — `if think_text.lstrip().startswith(('A1', 'A2', 'A4', 'E1', 'E2', 'duplicate of', 'spice combinator'))` — would have caught 56 percent of the corpus before training fired the first time.

The probe was probing for the right thing at the wrong layer. The mechanical emission check is fine as a smoke test. The content check is what catches the corpus contamination. The two together are cheap; either one alone is a partial gate.

:::pitfall[Two clean trains side by side feels like the trainer is the right place to look]
Loss curves overlay. Wall time within 5 minutes. Layer-1 isolation verified twice. Identical merged-BF16 size. Identical hyperparameters. *Of course* the trainer is fine. But this is also exactly when the cognitive pull is strongest to keep poking at the trainer — because everything looks right. Walk upstream of the trainer before downstream. The corpus rarely lies but it sometimes leaks.
:::

The cost was three hours of wall — two 131-minute trains plus the diagnostic time — and a 5-percent slice of the weekly cap on synthesis that I had to throw away. The model isn't shipping. The bench dataset isn't shipping. What is shipping is this article and four memorized lessons (`feedback_sft_eos_bos_explicit`, the TRL-collator-doesn't-mask-EOS correction, the catastrophic-forgetting-is-real-but-incomplete observation, the corpus-quality-bar-is-upstream finding) and a clear next step for the patent-strategist work: rebuild the corpus with the leak stripped, optionally interleave general-reasoning rows to dampen the math collapse, retrain, content-judge the probe.

## What this unlocks for the reader

Three things to do before your next fine-tune, in increasing order of effort:

**Audit the corpus for synth-pipeline meta-state.** Grep your training corpus for the first 20 characters of every think block. If anything other than your domain's natural opening words shows up — family designators, producer notes, diversification tags, "duplicate of" annotations — your synth pipeline is leaking. Strip it before training, not after. Five minutes with regex saves three hours of train + probe wall.

**Add a content gate to your probe, not just an emission gate.** Sample five to ten rows. Run an LLM judge with a domain rubric ("does this think block contain reasoning about the specific question, or generic boilerplate?"). The judge is essentially free compared to the train. If your gate only measures `<think>...</think>` markers, it is silently passing corpus contamination.

**Reproduce one probe row in isolation before firing the full probe.** A 30-minute single-row script with a small inspection harness can tell you ninety percent of what a 30-minute twenty-row probe will tell you, but at one-twentieth the wall and with the actual model output sitting on disk for grep. The probe pipeline is meant for batch judgment, not for diagnosis. Diagnosis wants the smallest reproducer that still shows the failure.

The DGX Spark's 128 GB unified memory makes the entire MTBM loop — synth, train, probe — fit on one machine without renegotiating a cluster's calendar. That is the unlock. The cost is that you own every layer of the pipeline, and a defect at any one layer cascades to every layer downstream until you walk it back. The trainer was fine. The corpus was 56 percent contaminated. The probe was measuring the wrong thing. The fix is upstream of the trainer, and the next iteration of the patent-strategist arc opens with the corpus rebuild, not another train.

:::deeper
- `articles/patent-strategist-v1-baseline-on-spark/` — the closed/retrieval/oracle bracket on the same R1-Distill base, before any fine-tune. Defines what "reasoning preservation" was supposed to mean.
- `articles/lora-fine-tune-nemotron-on-spark/` — sibling LoRA piece on a different base. The mechanics overlap; the corpus quality discipline applies identically.
- `articles/gpu-sizing-math-for-fine-tuning/` — the arithmetic for what fits on the Spark vs. what needs an H100. None of that math saves you from a corrupt corpus.
- [TRL `SFTTrainer` source](https://github.com/huggingface/trl/blob/main/trl/trainer/sft_trainer.py) — the `DataCollatorForLanguageModeling.torch_call()` that pads labels with `-100` and *does not* mask EOS positions. Worth reading once.
:::

:::hardware[The arithmetic still scales the same way on bigger hardware]
On an H100, the same 5000-row × 2-epoch train compresses from 131 minutes to roughly 25 minutes — about 5× faster on the train side, before accounting for the data-load and merge overheads which scale less aggressively. On an H200 the train side compresses further to perhaps 15-18 minutes. None of that changes the analysis: the 56-percent corpus contamination would have produced the same model in 18 minutes that I produced in 131. Faster hardware lowers the cost of *one* iteration; it does not raise the corpus-quality bar by itself.
:::

**MTBM now:** the patent-strategist arc is paused for a corpus rebuild. The W1 baseline (`patent-strategist-v1-baseline-on-spark`) is the floor; the next attempt at the W3 fine-tune will land after the cleaner, the content-judging probe, and a 10–15 percent general-reasoning mix to dampen the math-mode collapse. Same trainer, different corpus, different probe.

Next up in the MTBM track: a content-judging probe scaffold that runs an LLM judge alongside the mechanical emission gate, and ships as a `fieldkit.eval` extension once a second vertical reuses the pattern. The article that comes with it will be much shorter — corpus quality discipline is most teachable on the failure case, and now the failure case is on record.
