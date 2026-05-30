# Training-type detection — name and README signals

The single most expensive trap in vertical-curator picks is mistaking a **continued-pretrain** model for a **chat-tuned** model. The continued-pretrain `instruction-pretrain/finance-Llama3-8B` scored 0/250 on FinanceBench in session 2 because the model had been further-trained on finance text but never SFT-tuned to answer questions in a Q&A shape. The chat-tuned sibling `AdaptLLM/finance-chat` scored 14–18% across variants on the same JSONL.

The detection is mostly readable from the repo name + README; this reference codifies the heuristics so `probe_model.sh` can flag the trap before the user invests hours downloading + quantizing.

## Repo-name patterns

| Pattern in repo name              | Inferred training type    | Confidence | Notes                                                              |
|-----------------------------------|---------------------------|------------|--------------------------------------------------------------------|
| `*-Chat`, `*-chat`                | SFT                       | high       | Llama-2-7B-Chat, AdaptLLM/finance-chat, llama2-7b-chat-hf           |
| `*-Instruct`, `*-instruct`        | SFT (instruction-tuned)   | high       | Llama-3.1-8B-Instruct, Mistral-7B-Instruct-v0.3                   |
| `*-Hermes-*`, `*-hermes-*`        | SFT (Hermes flavor)       | high       | OpenHermes-2.5-Mistral-7B, Nous-Hermes-Llama2-13b                  |
| `*-Tulu-*`, `*-tulu-*`            | SFT (Tulu flavor)         | high       | Tulu-3-8B-DPO                                                       |
| `*-Zephyr-*`, `*-zephyr-*`        | SFT (Zephyr flavor)       | high       | HuggingFaceH4/zephyr-7b-beta                                       |
| `*-DPO`, `*-ORPO`, `*-KTO`        | DPO/RLHF                  | high       | All preference-optimization outputs are SFT + DPO downstream        |
| `*-SFT`                           | SFT (explicit)            | very high  | The explicit label                                                  |
| `*-Llama-2-7B` (no `-Chat`)       | base                      | very high  | The bare base model                                                 |
| `*-pretrain*`, `*-continued*`     | continued-pretrain        | very high  | **The trap.** Instruction-pretrain, domain-pretrain, etc.           |
| `*-base`, `*-Base`                | base                      | high       | TheBloke/Llama-2-7b-Base — confirm in README                       |
| `*-it`, `*-IT`                    | SFT (Gemma instruction-tuned) | high   | gemma-2-9b-it                                                       |
| `*-Coder*-Instruct`               | SFT (code-tuned)          | high       | deepseek-coder-7b-instruct                                          |

When **multiple signals conflict** (e.g., `*-pretrain-chat`), trust the LATER suffix — chat-tuning happens after pretraining. So `xxx-pretrain-chat` is SFT-tuned.

## README signals

When the repo name is ambiguous (no clear suffix), the README usually disambiguates:

### Continued-pretrain signals (the trap)

- "**Continued pre-training**" or "continued pretraining" — explicit; this is the canonical phrase
- "**Further pre-trained**" / "**further pretrained**" / "**further pre-training**" — BioMistral-class phrasing; missed on the 2026-05-16 medical scout (BioMistral has 166K downloads and would have been the highest-popularity miss-pick had the scout not flagged it manually)
- "**Domain-adaptive pretraining**"
- "We further-trained the model on `<corpus>`"
- "**Adapt Large Language Models via Reading Comprehension**" — the AdaptLLM paper signal
- "The model has NOT been fine-tuned for question-answering"
- A "How to use" snippet that shows ONLY raw completion (no chat template, no `[INST]`, no instruction template)
- README mentions "tokenizer" + "vocabulary" extensions — usually paired with continued-pretrain

### SFT / instruct signals (safe)

- "**Supervised fine-tuning**" or "**SFT**"
- "**Instruction tuning**" or "**Instruction-tuned**"
- A code block with `[INST]` / `<|user|>` / `<|im_start|>` / `<start_of_turn>` wrapping the example prompt
- An OpenAI-style chat-completion example: `messages = [{"role": "user", "content": "..."}]`
- A `chat_template` documentation block
- "**RLHF**" — implies SFT happened upstream
- "**DPO**" / "**ORPO**" / "**KTO**" — preference-tuning implies SFT happened first

### Base-only signals (also a trap for chat use, but well-known)

- "**This is the base model**" — explicit
- "We recommend fine-tuning before deployment"
- Card has NO "How to use" section, just architecture details
- Inference example uses raw completion only

## When all signals are weak

Some models — particularly **older fine-tunes** before HF normalized `chat_template` — ship without any of the above markers. Fall back to:

1. **Look at the base_model field** in the HF model card frontmatter. If `base_model: meta-llama/Llama-2-7b-chat-hf`, the derivative inherits the chat-tuning. If `base_model: meta-llama/Llama-2-7b` (the raw base), the derivative might be continued-pretrain.
2. **Look at the dataset field**. SFT datasets like `Open-Orca/SlimOrca`, `WizardLM/WizardLM_evol_instruct_70k`, `teknium/OpenHermes-2.5`, `argilla/distilabel-intel-orca-dpo-pairs` all signal SFT.
3. **Look at the model creator's other repos**. AdaptLLM publishes both `*-pretrain` and `*-chat` siblings — the convention is enforced across their releases.

## Hard-rule cases

These cases yield deterministic verdicts regardless of name/README:

| Case                                                              | Verdict                            |
|-------------------------------------------------------------------|------------------------------------|
| `tokenizer_config.json` has `chat_template` field + non-trivial Jinja content | SFT (verified)              |
| `tokenizer_config.json` has NO `chat_template` field + README confirms continued-pretrain | continued-pretrain (TRAP) |
| `tokenizer_config.json` has NO `chat_template` field + README has `[INST]` example | SFT (with caveat — `chat_format=llama-2` works but no auto-template) |
| Card frontmatter declares `pipeline_tag: text-generation` AND `tags: [continued-pretraining]` | continued-pretrain (TRAP) |
| Card frontmatter declares `tags: [instruct, sft]`                | SFT                                |

## The AdaptLLM/finance-chat exception

AdaptLLM/finance-chat is the canonical edge case: chat-tuned (continued pre-trained from `Llama-2-Chat-7B`) but ships **without** a `chat_template`. The README's "How to use" snippet uses raw `[INST]` formatting. This is the case where:

- `chat_format` detection sees MISSING (because no `chat_template`)
- Repo-name signal says `*-chat` (high-confidence SFT)
- README signal says `[INST]` example exists

When `chat_format` is MISSING but the name + README both signal SFT, surface as `MANUAL_REVIEW` — not as the trap. The user can recover by setting `chat_format="llama-2"` explicitly on the HF card via `publish_quant(chat_format="llama-2")`. AdaptLLM/finance-chat got 14–18% with this override; the trap-pattern repo `instruction-pretrain/finance-Llama3-8B` got 0%.

## When in doubt

Recommend the SAFE choice: a clearly SFT-tagged sibling. Almost every domain has both `*-pretrain` and `*-chat` variants from the same author (AdaptLLM publishes both, EleutherAI publishes both, Microsoft publishes both). Pick the chat variant; let the user override if they specifically want pretrain.

## Downstream — the Q8_0 shape implication

The training-type classification above has a second use beyond trap-avoidance: it predicts Q8_0 throughput on GB10 (continued-pretrain shapes saw Q8_0 *slower* than F16; chat-tune-only shapes saw Q8_0 *faster*). See `references/quant-shape-signals.md` for the n=4 evidence table, per-shape Q8_0 expectation, and the vertical N+1 sample-balancing rule the scout report should encode.
