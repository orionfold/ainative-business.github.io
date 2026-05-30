# `llama_cpp.Llama(chat_format=...)` reference

The `chat_format` value gets threaded into the rendered `## How to run` llama-cpp-python snippet on the model card. Picking the wrong one means the customer's `create_chat_completion(...)` calls will silently format messages incorrectly — the model receives raw prompt text instead of the expected `[INST]` / `<|im_start|>` / etc. wrapping, and quality cratters. Per `[[feedback_chat_vs_continued_pretrain_trap]]`, a missing or mismatched chat template is a class of publishing trap that costs evaluation accuracy without any visible error.

## Common values

| `chat_format`  | Families                                              | Detection signal                                                  |
|----------------|-------------------------------------------------------|-------------------------------------------------------------------|
| `llama-2`      | Llama-2-Chat + AdaptLLM family + Vicuna-derived       | `[INST]` + `<<SYS>>` markers in `chat_template`                   |
| `llama-3`      | Llama-3-Instruct (and 3.1, 3.2 instruct variants)     | `<\|start_header_id\|>` + `<\|end_header_id\|>` + `<\|eot_id\|>`  |
| `chatml`       | Qwen, OpenChat, many fine-tunes following ChatML      | `<\|im_start\|>` + `<\|im_end\|>` in `chat_template`              |
| `mistral`      | Mistral-Instruct (NOT same as llama-2)                | `[INST]` BUT no `<<SYS>>` system block                            |
| `vicuna`       | Vicuna, WizardLM                                      | `"USER: {prompt} ASSISTANT: "` literal in `chat_template`         |
| `gemma`        | Gemma-Instruct + Gemma-2/3 instruct                   | `<start_of_turn>user` + `<end_of_turn>` markers                   |
| `zephyr`       | Zephyr-7B and HuggingFaceH4 family                    | `<\|user\|>` + `<\|assistant\|>` + `<\|system\|>`                 |
| `phi-3`        | Phi-3-mini-instruct, Phi-3-medium-instruct            | `<\|user\|>...<\|end\|>` with Phi-specific tokens                 |
| `qwen`         | Qwen-1 (NOT Qwen-1.5+, which use chatml)              | Older Qwen-specific `<\|im_start\|>system` variant                |
| `openchat`     | OpenChat-3.5+ specifically                            | `GPT4 Correct User:` literal in chat_template                     |
| `(empty / unset)` | **Base / continued-pretrain models** (DANGER)      | **No `chat_template` field at all** in tokenizer_config.json      |

The "no chat_template" row is the publishing trap. If `tokenizer_config.json` has no `chat_template` field, the model is either (a) a true base model not meant for chat OR (b) a continued-pretrain that needs the user to apply chat formatting themselves. Per `[[feedback_chat_vs_continued_pretrain_trap]]`, the AdaptLLM/finance-chat case shows even chat-tuned models can publish without an inline `chat_template` (their card uses `[INST]` formatting in the example code, so we infer `llama-2`). Don't auto-publish a model with no detectable chat format — surface it to the user.

## How to detect

```bash
# 1. Pull tokenizer_config.json from the source repo (or read from local download)
hf download <repo> tokenizer_config.json --local-dir /tmp/chatfmt-probe

# 2. Inspect the chat_template field
jq -r '.chat_template // "MISSING"' /tmp/chatfmt-probe/tokenizer_config.json

# 3. Match against the table above
```

The string returned from step 2 will usually be a Jinja-style template; pattern-match against the "Detection signal" column. If MISSING, fall back to:
1. The source repo's README "How to use" snippet — most models include a working example that reveals the expected format.
2. The model name — `*-Chat`, `*-Instruct`, `*-Hermes`, `*-Tulu`, `*-Zephyr`, `*-DPO` all signal chat-tuning + a likely format.
3. The lineage — if derived from Llama-2-Chat-7B, format is `llama-2`.

## When in doubt — leave it empty

The rendered card snippet works fine without a `chat_format=` kwarg — the customer's call falls back to llama-cpp-python's default no-format mode. That's better than picking the wrong format, which silently corrupts every chat call. So if confidence is low, leave `CHAT_FORMAT=""` and add a one-line note in the article's "Using this release" section telling the user to wrap prompts manually.
