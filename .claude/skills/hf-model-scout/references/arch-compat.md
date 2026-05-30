# llama.cpp architecture compatibility for `convert_hf_to_gguf.py`

The GGUF publishing pipeline depends on `llama.cpp/convert_hf_to_gguf.py` handling the source-weight architecture. Unsupported architectures cause `convert_hf_to_gguf.py` to fail with `NotImplementedError` mid-conversion (after the user has already downloaded ~25 GB of weights), which is the third trap this skill exists to prevent.

This list is calibrated against llama.cpp release `b6065` (the build the Spark uses, vendored at `/home/nvidia/llama.cpp/`). If the user updates llama.cpp, re-check by running `python3 /home/nvidia/llama.cpp/convert_hf_to_gguf.py --help-models` (when that flag lands) or scanning the file's class registry.

## Supported architectures (safe — emit `convert_hf_to_gguf.py` will work)

| `config.json:model_type` / arch class       | Common HF families                                                    |
|---------------------------------------------|-----------------------------------------------------------------------|
| `llama` / `LlamaForCausalLM`                | Llama-2, Llama-3.x, CodeLlama, Llama-2-Chat, AdaptLLM/* (most)         |
| `mistral` / `MistralForCausalLM`            | Mistral-7B, Mistral-Instruct, Mixtral-8x7B, Mistral-Nemo               |
| `qwen2` / `Qwen2ForCausalLM`                | Qwen2-{0.5,1.5,3,7,14,32,72}B, Qwen2.5-*                              |
| `qwen3` / `Qwen3ForCausalLM`                | Qwen3-{4,8,14,32,72,235}B                                              |
| `gemma` / `GemmaForCausalLM`                | Gemma-{2,7}B (original)                                               |
| `gemma2` / `Gemma2ForCausalLM`              | Gemma-2-{2,9,27}B                                                     |
| `gemma3` / `Gemma3ForCausalLM`              | Gemma-3-{1,4,12,27}B                                                  |
| `phi3` / `Phi3ForCausalLM`                  | Phi-3-mini, Phi-3-medium, Phi-3.5-mini                                |
| `phi` / `PhiForCausalLM`                    | Phi-2 (older Phi-1.5 also OK)                                          |
| `falcon` / `FalconForCausalLM`              | Falcon-7B, Falcon-40B, Falcon-180B                                     |
| `stablelm` / `StableLmForCausalLM`          | StableLM-Zephyr-3B, StableLM-2-12B                                     |
| `deepseek_v2` / `DeepseekV2ForCausalLM`     | DeepSeek-V2, DeepSeek-V2-Lite                                          |
| `deepseek_v3` / `DeepseekV3ForCausalLM`     | DeepSeek-V3 (huge — won't fit Spark; envelope check should rule out)   |
| `mixtral` / `MixtralForCausalLM`            | Mixtral-8x7B (MoE; verify llama.cpp build supports MoE GGUF for 1xV0) |
| `command_r` / `CohereForCausalLM`           | Cohere Command-R                                                       |
| `dbrx` / `DbrxForCausalLM`                  | Databricks DBRX (huge — same envelope caveat)                          |
| `granite` / `GraniteForCausalLM`            | IBM Granite-3.x                                                        |
| `internlm2` / `InternLM2ForCausalLM`        | InternLM-2-{7,20}B-Chat                                                |

## Unsupported architectures (rule out)

These will fail `convert_hf_to_gguf.py` with `NotImplementedError` or produce a broken GGUF:

| `config.json:model_type` / arch class       | Why                                                                |
|---------------------------------------------|--------------------------------------------------------------------|
| `skywork` / `SkyworkForCausalLM` (MoE)      | MoE variant not yet in llama.cpp registry                          |
| `minimax` / `MiniMaxText01ForCausalLM`      | Custom attention layout                                            |
| `internlm3` / `InternLM3ForCausalLM`        | Awaiting llama.cpp PR (as of 2026-05)                              |
| `chatglm` / `ChatGLMModel` (≤v3)            | Custom tokenizer; v4 (`glm` arch) is supported, ≤v3 is not         |
| `baichuan` (older `Baichuan2ForCausalLM`)   | Custom; some forks support, mainline llama.cpp doesn't             |
| `rwkv`, `mamba`, `mamba2`                   | State-space; not transformer — different GGUF format               |
| `t5` / `T5ForConditionalGeneration`         | Encoder-decoder — different GGUF target (use convert_t5 if needed) |
| `bart` / `BartForConditionalGeneration`     | Same encoder-decoder reason                                        |
| `bert` / `BertForSequenceClassification`    | Wrong objective; not a generative model                             |

## Quirks and one-offs

These work but with caveats:

| Family                | Caveat                                                                                          |
|-----------------------|-------------------------------------------------------------------------------------------------|
| Llama-3.2 multimodal  | Vision tower in `config.json` adds `model_type: mllama`; vision-only path; text-only path works |
| Phi-3-vision          | Same as Llama-3.2-multimodal — strip vision before convert                                       |
| Gemma-3 multimodal    | Vision encoder bundled; convert handles text path                                                |
| AdaptLLM/*            | All are Llama-2 lineage; arch detection should land on `LlamaForCausalLM`                       |

## How `probe_model.sh` consumes this list

The bash script reads `config.json` for `model_type` (preferred) or `architectures[0]` (fallback). It hardcodes the safe list above for the most common cases. When detection lands on something not in the safe list, `llama_cpp_compat: "unknown"` is emitted; the report flags this as "needs manual verification" but doesn't automatically rule it out — the user might know about a recent llama.cpp PR the skill doesn't.

## Updating this list

When llama.cpp ships a new `convert_hf_to_gguf.py` (vendored in `/home/nvidia/llama.cpp/`), scan the file for new `@Model.register("...")` decorators and add any new model_type strings to the supported list above. The probe script's case-statement should be updated in parallel.
