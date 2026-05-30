# HuggingFace license tags — decision tree for `model_license`

The `license:` scalar in HF model-card frontmatter is what HuggingFace surfaces as the model's license badge — it must reflect the **upstream model's** actual terms. Defaulting to `apache-2.0` is the trap that produced a wrong license badge on `Orionfold/finance-chat-GGUF` in its first staged dry-run (the model is Llama-2 lineage; the right tag is `llama2`).

## Common tags

| Tag           | License                                | Common bases                                          | Red flag                                      |
|---------------|----------------------------------------|-------------------------------------------------------|-----------------------------------------------|
| `apache-2.0`  | Apache 2.0                             | Mistral 7B, Phi, many fine-tunes derived from Apache  | Default — verify before assuming              |
| `mit`         | MIT                                    | Some Microsoft + research models                      | Rare in production fine-tunes                 |
| `llama2`      | Llama 2 Community License              | Llama-2-{7,13,70}B + AdaptLLM/finance-chat etc.       | Card may say "License: Other" → likely llama2 |
| `llama3`      | Llama 3 Community License              | Llama-3-{8,70}B + Meta-derived                        | Same trap as llama2                           |
| `llama3.1`    | Llama 3.1 Community License            | Llama-3.1-{8,70,405}B                                 | Distinct from `llama3`                        |
| `llama3.2`    | Llama 3.2 Community License            | Llama-3.2-{1,3,11,90}B                                | Distinct from `llama3` and `llama3.1`         |
| `gemma`       | Gemma Terms of Use                     | Gemma-1, Gemma-2, Gemma-3 + derivatives               | Includes prohibited-use clause                |
| `cc-by-nc-4.0`| Creative Commons BY-NC 4.0 (NON-COMM.) | Some research-only fine-tunes                         | **BLOCKS commercial Orionfold tier**          |
| `cc-by-4.0`   | Creative Commons BY 4.0                | Open datasets + permissive research models            | Commercial-friendly attribution required      |
| `cc-by-sa-4.0`| CC BY-SA 4.0 (share-alike)             | Some open data, rare in production weights            | Share-alike viral term to consider            |
| `openrail`    | OpenRAIL-M (use restrictions)          | StarCoder, BLOOM family                               | Restricts certain end-uses                    |
| `bigscience-bloom-rail-1.0` | BigScience BLOOM RAIL 1.0  | BLOOM-176B + BLOOM-derived                            | Distinct from generic openrail                |
| `bigcode-openrail-m` | BigCode OpenRAIL-M              | StarCoder family (specifically)                       | Distinct from generic openrail                |
| `mistral-ai`  | Mistral Research License (non-comm.)   | Mistral-Large + non-Apache Mistral                    | Distinct from Mistral 7B (which is `apache-2.0`) |
| `qwen`        | Tongyi Qianwen License                 | Qwen-{1,1.5,2,2.5,3}                                  | Per-version variations exist                  |
| `qwen-research`| Tongyi Qianwen Research License       | Qwen-Research variants                                | Non-commercial restriction                    |
| `deepseek`    | DeepSeek License                       | DeepSeek-V2/V3, DeepSeek-Coder                        | Custom license, read full terms               |
| `other`       | Custom / non-standard                  | Anything not in the HF dropdown                       | HF won't render a friendly badge              |

If unsure, prefer `other` over guessing — at least it's honest and won't display a misleading badge. **Never default to `apache-2.0` silently.**

## How to detect

Run these checks against the source HF repo OR against `/home/nvidia/data/models/<slug>/` if already downloaded:

### 1. Read the source repo's README

The "License" section of the source model's `README.md` is the highest-signal source. Grep for these phrases:

| Phrase in README                                | → Tag                |
|--------------------------------------------------|----------------------|
| "Apache 2.0" / "Apache License, Version 2.0"     | `apache-2.0`         |
| "MIT License"                                    | `mit`                |
| "Llama 2 Community License" / "Meta Llama 2"     | `llama2`             |
| "Llama 3 Community License" / "Meta Llama 3"     | `llama3` (check version subtag too) |
| "Gemma Terms of Use" / "Gemma is provided"       | `gemma`              |
| "non-commercial" + "CC BY-NC"                    | `cc-by-nc-4.0`       |
| "Tongyi Qianwen" / "Qwen License"                | `qwen`               |
| "OpenRAIL"                                       | `openrail` (or family-specific) |

### 2. Read the source repo's HF model-card frontmatter

```bash
hf download <repo> README.md --local-dir /tmp/license-probe
head -30 /tmp/license-probe/README.md | grep -E '^license:'
```

If the source repo has `license: <something>` in its own frontmatter, **inherit that exactly**. Don't translate or approximate.

### 3. Trace the lineage

Many fine-tunes inherit license terms from their base. Read the "How to use" snippet in the source README — it usually loads weights from a base model. If the base is Llama-2-Chat, the derivative is `llama2`. If base is Mistral-7B-v0.1, derivative is typically `apache-2.0`. AdaptLLM/finance-chat is the canonical example: continued pre-trained from Llama-2-Chat-7B → `llama2`, even though the AdaptLLM card itself is silent on license.

### 4. Check `tokenizer_config.json` for chat-template lineage hints

`[INST]` markers in `chat_template` strongly suggest Llama-2 lineage → `llama2`. `<|start_header_id|>` suggests Llama-3 → `llama3`. `<start_of_turn>` suggests Gemma → `gemma`. These aren't authoritative, but they're a useful sanity check against the README claim.

## When in doubt — bail and ask

If you can't confidently pick a tag from the above signals, the right action is to STOP and ask the user. A wrong license badge is a customer-trust problem; a 5-minute pause to ask is cheap. Per `[[feedback_customer_link_audit]]`, customer-facing surfaces have a higher bar than internal stuff.
