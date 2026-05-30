#!/usr/bin/env python3
"""G2-extra — Isolate where R1-Qwen3-8B output gets byte-mangled.

Three probes:
  A. /v1/completions with the BARE-BONES prompt (no chat-template)
  B. /v1/completions with a manually-formatted prompt using the DS-R1 template
  C. /v1/chat/completions (server applies the chat-template)

If A or B is clean and C is mangled → chat-template application is the bug.
If all three are mangled → vllm streaming detokenizer + LlamaTokenizerFast bug.
"""
import json
import os
import httpx

os.environ.setdefault("HF_HOME", "/home/nvidia/data/.hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "/home/nvidia/data/.hf-cache/hub")

SERVER = "http://127.0.0.1:8000/v1"
MODEL = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"

USR = (
    'Identify any 35 USC §112(b) indefiniteness risks in this claim: '
    '"A system for handling user requests, wherein the system is essentially '
    'user-friendly and operates in real-time or near real-time." Cite MPEP.'
)


def show(label, content):
    print(f"\n=== {label} (first 400 chars) ===")
    print(content[:400])
    has_mojibake = any(ch in content for ch in ["Ġ", "Ċ", "ĉ"])
    print(f"  [mojibake markers present: {has_mojibake}]")


# Probe A — /v1/completions raw, no chat template
print("\n### PROBE A: /v1/completions with PLAIN prompt (no template)")
rA = httpx.post(
    f"{SERVER}/completions",
    json={
        "model": MODEL,
        "prompt": f"Question: {USR}\n\nAnswer:",
        "max_tokens": 400,
        "temperature": 0.6,
    },
    timeout=600.0,
).json()
show("PROBE A", rA.get("choices", [{}])[0].get("text", json.dumps(rA)[:300]))

# Probe B — /v1/completions with manually-applied chat template
# Use HuggingFace tokenizer to render messages → string
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(MODEL)
messages = [
    {"role": "user", "content": USR},
]
chat_str = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
print("\n=== APPLIED CHAT-TEMPLATE STRING (first 500 chars) ===")
print(chat_str[:500])

print("\n### PROBE B: /v1/completions with HF-rendered chat template")
rB = httpx.post(
    f"{SERVER}/completions",
    json={
        "model": MODEL,
        "prompt": chat_str,
        "max_tokens": 400,
        "temperature": 0.6,
        "skip_special_tokens": True,
    },
    timeout=600.0,
).json()
show("PROBE B", rB.get("choices", [{}])[0].get("text", json.dumps(rB)[:300]))

# Probe C — /v1/chat/completions (server applies template)
print("\n### PROBE C: /v1/chat/completions (server-side template)")
rC = httpx.post(
    f"{SERVER}/chat/completions",
    json={
        "model": MODEL,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.6,
    },
    timeout=600.0,
).json()
show("PROBE C", rC.get("choices", [{}])[0].get("message", {}).get("content", json.dumps(rC)[:300]))
