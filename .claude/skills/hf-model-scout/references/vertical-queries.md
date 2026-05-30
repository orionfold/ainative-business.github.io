# HF search-query stems per vertical

The first step in scout mode is finding 8–12 candidate models on HF for a named vertical. HF's `hf models list --search ...` matches against repo names, descriptions, and tags. Picking the right keyword stem is what separates "you got chat-tuned variants" from "you got pretrain dumps and dataset cards."

The principle: search for what the **product** is, not what the **paper** says. "finance-chat" surfaces chat-tuned variants; "financial-pretrain" surfaces continued-pretrain bases (the trap). Same logic across verticals.

## Finance

| Query                          | Why                                                                                          |
|--------------------------------|----------------------------------------------------------------------------------------------|
| `finance OR financial`         | Primary stem. Surfaces AdaptLLM/finance-chat, FinLlama, FinanceConnect, Llama-3.1-FinChat-8B |
| `(no negative — too broad)`    | The fallback above is the fallback; if it yields <5 results, try `accounting OR earnings`.   |

Bench: FinanceBench (Patronus AI, JSONL with `evidence[].evidence_text` open-book column).
Bench loader: `fieldkit.eval.VerticalBench.from_jsonl(open_book=True, subset='metrics-generated')`.

## Legal

| Query                          | Why                                                                                                                  |
|--------------------------------|----------------------------------------------------------------------------------------------------------------------|
| `legal OR law`                 | Primary stem. Surfaces equall/Saul-7B-Instruct-v1, AdaptLLM/law-chat, llama2-13b-lawyer, lex-fridman-podcast (no, kidding) |
| `contract OR statute`          | Fallback when "legal OR law" hits noise (legal-aid-bot vs legal-LLM).                                                |
| **AVOID**: `attorney OR judge` | Too noisy — pulls in role-play fine-tunes that aren't real legal-domain bases.                                       |

Bench: LegalBench (Stanford CRFM, ~162 sub-tasks with `text` + `answer` schema).
Bench loader: `fieldkit.eval.VerticalBench.from_jsonl(format='legalbench')` — closed-book; per-task scoring via the `task` tag.

## Cyber

| Query                          | Why                                                                                                            |
|--------------------------------|----------------------------------------------------------------------------------------------------------------|
| `cyber OR security`            | Primary stem. Surfaces segolilylabs/Lily-Cybersecurity-7B-v0.2, hackergpt, AnyaSchen/cybersec-llama          |
| `infosec OR malware`           | Fallback when too broad. `malware` alone pulls dataset cards rather than LLM bases.                            |
| **AVOID**: `hacker`            | Pulls hackathon-output personas, not domain LLMs.                                                              |

Bench: CTI-Bench (cyber-threat-intel benchmark) OR purple-team-bench. The cyber vertical lacks a clean canonical bench like FinanceBench/LegalBench — the eval is often custom (per the Lily-Cybersecurity-7B README).

## Medical

| Query                          | Why                                                                                                       |
|--------------------------------|-----------------------------------------------------------------------------------------------------------|
| `medical OR clinical`          | Primary stem. Surfaces aaditya/Llama3-OpenBioLLM-8B, m42-health/Llama3-Med42-8B, johnsnowlabs/JSL-MedLlama  |
| `health OR biomed`             | Fallback. `biomed` skews toward research models; `health` skews toward consumer-app fine-tunes.            |
| **AVOID**: `medic`             | Surfaces unrelated proper nouns (Medic, MedCAT).                                                          |

Bench: MedQA-USMLE (multi-choice — convert to `format='generic'` JSONL via question + label fields), or MedMCQA.

## Code

| Query                          | Why                                                                                                       |
|--------------------------------|-----------------------------------------------------------------------------------------------------------|
| `code OR coding`               | Too broad — pulls hundreds of tiny code-helper fine-tunes. Prefer the more specific:                      |
| `codellama OR deepseek-coder OR qwen-coder` | Family-name search — catches the canonical lineages.                                          |
| **NOTE**: Most Code bases are large (≥7B); pre-filter to ≤9B for first Spark cards.                                                          |

Bench: HumanEval (well-known but small; ~164 problems), MBPP, or LiveCodeBench.

## Math

| Query                          | Why                                                                                                       |
|--------------------------------|-----------------------------------------------------------------------------------------------------------|
| `math OR mathematical`         | Primary stem. Surfaces deepseek-math-7b-instruct, Llama-2-7B-MathInstruct, NuminaMath-7B-CoT             |
| `arithmetic OR reasoning`      | Fallback. "reasoning" pulls in distillation models from o1/r1 traces (more useful than pure-math models).  |

Bench: GSM8K (grade-school math), MATH (competition-level), MMLU-Math (multi-choice).

## General-purpose (no specific vertical)

When the user wants a "next strong general base" rather than a vertical pick, the right search shifts to family + size + recency:

| Query                          | Why                                                                                                       |
|--------------------------------|-----------------------------------------------------------------------------------------------------------|
| `llama-3` / `llama-3.1` / `llama-3.2` | Pulls the canonical Meta family + derivatives                                                       |
| `mistral OR mixtral`           | Apache-licensed mainstream                                                                                 |
| `qwen2 OR qwen2.5 OR qwen3`    | Alibaba's strong-on-code-and-multilingual family                                                          |
| `gemma-2 OR gemma-3`           | Google's compact + commercially-permissive family                                                          |

For general-purpose the user usually wants the latest revision — sort by `last_modified` rather than `trending_score`.

## Why these specific stems vs alternatives

The trap-avoidance principle: **AVOID stems that surface continued-pretrain models**. Examples:

- ❌ `pretraining OR pretrained` — pulls AdaptLLM continued-pretrain bases (the 0/50 trap)
- ❌ `domain-adapted` — same surface
- ❌ `tokenizer` — pulls dataset cards
- ❌ `lora` — pulls adapter weights, not base models
- ❌ `gguf OR quantized` — pulls *already-quantized* community drops, not source weights

Use the "what's the product?" framing: a finance LLM's *product* is "answers finance questions correctly", so the search stem is `finance`, not `finance-pretraining`.

## Cross-reference

When a search returns >25 candidates, prefer the ones that overlap multiple verticals (e.g., legal + finance often co-occur in `lawyer-llama` variants) — they're typically broader-coverage SFT fine-tunes vs narrow continued-pretrains. The `score` in `probe.json` rewards this via the `trending_score × downloads × likes` floor.
