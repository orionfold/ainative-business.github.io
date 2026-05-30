"""Reasoning-preservation probe runner (spec §4 Layer 5).

Loads a model (HF id or local path), runs the 20-question reasoning probe
at probes/reasoning-preservation-20q.jsonl, and measures:

  - think_presence_rate   = fraction of responses containing <think>...</think>
  - think_token_length    = mean tokens between <think> and </think>

The third metric in the spec — `think_quality_score` (LLM-judge coherence
0-5) — is no longer scored in this script. Per repo policy any LLM-artifact-
generation step (judging is one) is owned by an in-CC-session orchestrator
skill, not a Python subprocess. To score the chains post-hoc, run a CC
session that reads the `raw_responses[].response` field, asks Claude to
rate each on the spec §4 Layer 5 rubric, and writes back a sidecar JSON
with quality scores joined on `qid`.

Output JSON shape (one record per checkpoint):
  {
    "model": "<id-or-path>",
    "lora_path": null | "<adapter-path>",
    "step": null | int,
    "n_probe": 20,
    "by_category": {
      "general-reasoning": {"think_presence_rate": ..., "think_token_length": ..., "n": ...},
      "patent-irac":       {...},
      "patent-strategic":  {...}
    },
    "overall": {...},
    "raw_responses": [{"qid": ..., "response": ..., "has_think": bool, "think_n_tok": int|null, "think_text": str}],
    "wall_seconds": float
  }

Usage:
  python scripts/probe_reasoning.py \
    --model deepseek-ai/DeepSeek-R1-0528-Qwen3-8B \
    --probe-set probes/reasoning-preservation-20q.jsonl \
    --output probes/baseline.json

  # Post-FT, optionally with an adapter:
  python scripts/probe_reasoning.py \
    --model deepseek-ai/DeepSeek-R1-0528-Qwen3-8B \
    --lora /work/runs/checkpoint-200 \
    --step 200 \
    --output probes/smoke-step200.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_CACHE", "/root/.cache/huggingface/hub")
os.environ.setdefault("HF_HOME", "/root/.cache/huggingface")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)

# Minimum word-boundary space ratio for healthy English reasoning text. Natural
# prose runs ~0.14–0.16; a model that emits no-Ġ (spaceless) token variants in
# <think> mode lands near 0. Below this, generation is degenerate even though
# the corpus + tokenizer round-trip cleanly — the patent-strategist-v3 failure
# mode (see memory `reference_r1_qwen3_gguf_detok_spaces`): the bug is in the
# learned weights, NOT the data/tokenization, so it must be caught at PROBE
# time (here) — before quantize + publish — not after.
MIN_THINK_SPACE_RATIO = 0.08


def think_space_ratio(text: str) -> float:
    """Fraction of characters that are spaces — a cheap detector for the
    spaceless-think generation artifact. Returns 0.0 for empty text."""
    return text.count(" ") / len(text) if text else 0.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="HF id or local path of base model")
    p.add_argument("--lora", default=None, help="Optional peft adapter path to attach after base load")
    p.add_argument("--probe-set", default="probes/reasoning-preservation-20q.jsonl")
    p.add_argument("--output", required=True, help="JSON output path")
    p.add_argument("--step", type=int, default=None, help="Training step (for checkpoint probes)")
    p.add_argument("--max-new-tokens", type=int, default=1024,
                   help="Per [[feedback_reasoning_model_npredict]]: <1024 truncates <think> blocks")
    p.add_argument("--temperature", type=float, default=0.6, help="R1-Distill recommended")
    return p.parse_args()


def load_probe_set(path: Path) -> list[dict]:
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_model(model_id: str, lora_path: str | None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"loading tokenizer ({model_id})...", flush=True)
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    print(f"loading base model bf16 on cuda:0...", flush=True)
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=torch.bfloat16,
        device_map="cuda:0",
        attn_implementation="sdpa",
        trust_remote_code=True,
    )
    print(f"  base loaded in {time.time()-t0:.1f}s", flush=True)

    if lora_path:
        from peft import PeftModel
        print(f"attaching LoRA adapter {lora_path}...", flush=True)
        model = PeftModel.from_pretrained(model, lora_path)

    model.eval()
    return tok, model


def generate(tok, model, question: str, max_new_tokens: int, temperature: float) -> str:
    import torch
    messages = [{"role": "user", "content": question}]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    enc = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **enc,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=True,
            top_p=0.95,
            pad_token_id=tok.pad_token_id,
        )
    gen_ids = out[0, enc["input_ids"].shape[1]:]
    return tok.decode(gen_ids, skip_special_tokens=False)


def parse_think(response: str) -> tuple[bool, int | None, str]:
    """Returns (has_think_block, n_tokens_in_block_approx, think_text).

    Picks the longest pair when multiple `<think>...</think>` blocks are emitted —
    R1-distill models occasionally false-start with an empty `<think></think>`
    before opening a real one. The non-greedy `.*?` regex would match the empty
    pair first and undercount the real chain (caught on smoke-step-200 row 14).
    """
    matches = THINK_RE.findall(response)
    if not matches:
        return False, None, ""
    think_text = max(matches, key=len).strip()
    if not think_text:
        return True, 0, ""
    n_tok = max(1, len(think_text) // 4)
    return True, n_tok, think_text


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"think_presence_rate": 0.0, "think_token_length": 0.0, "n": 0}
    has = [r for r in rows if r["has_think"] and r.get("think_text")]
    presence = len([r for r in rows if r["has_think"]]) / len(rows)
    mean_len = sum(r["think_n_tok"] for r in rows if r["has_think"]) / max(1, len([r for r in rows if r["has_think"]]))
    mean_space = sum(r.get("space_ratio", 0.0) for r in has) / max(1, len(has))
    return {
        "think_presence_rate": round(presence, 4),
        "think_token_length": round(mean_len, 1),
        "think_space_ratio": round(mean_space, 4),
        "n": len(rows),
    }


def main() -> int:
    args = parse_args()
    probe_set = load_probe_set(Path(args.probe_set))
    print(f"loaded {len(probe_set)} probe rows from {args.probe_set}", flush=True)

    tok, model = load_model(args.model, args.lora)

    rows = []
    t_start = time.time()
    for i, q in enumerate(probe_set, 1):
        print(f"[{i:2d}/{len(probe_set)}] qid={q['qid']} cat={q['category']}", flush=True)
        t0 = time.time()
        response = generate(tok, model, q["question"], args.max_new_tokens, args.temperature)
        has_think, n_tok, think_text = parse_think(response)
        rows.append({
            "qid": q["qid"],
            "category": q["category"],
            "response": response,
            "has_think": has_think,
            "think_n_tok": n_tok,
            "think_text": think_text,
            "space_ratio": round(think_space_ratio(think_text), 4),
            "wall_seconds": round(time.time() - t0, 2),
        })
        print(f"     wall={time.time()-t0:.1f}s  has_think={has_think}  n_tok={n_tok}", flush=True)

    overall = summarize(rows)
    by_category = {}
    for cat in sorted({r["category"] for r in rows}):
        by_category[cat] = summarize([r for r in rows if r["category"] == cat])

    out = {
        "model": args.model,
        "lora_path": args.lora,
        "step": args.step,
        "n_probe": len(rows),
        "max_new_tokens": args.max_new_tokens,
        "temperature": args.temperature,
        "overall": overall,
        "by_category": by_category,
        "raw_responses": rows,
        "wall_seconds": round(time.time() - t_start, 1),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nWrote {args.output}")
    print(f"  overall: {overall}")
    print(f"  total wall: {out['wall_seconds']}s")

    # Guard: spaceless-<think> generation (patent-strategist-v3 failure mode).
    # The corpus + tokenizers round-trip spaces cleanly, so this can only be
    # caught on generated output — here, before quantize + publish.
    sr = overall.get("think_space_ratio", 0.0)
    if overall.get("think_presence_rate", 0) > 0 and sr < MIN_THINK_SPACE_RATIO:
        print(
            f"\n  ⚠️  SPACELESS-THINK WARNING: mean <think> space ratio = {sr:.4f} "
            f"(< {MIN_THINK_SPACE_RATIO}). The model emits no-Ġ (spaceless) tokens "
            "in reasoning mode — degenerate generation. Do NOT quantize/publish; "
            "the fix is in the recipe/weights, not the data (see memory "
            "reference_r1_qwen3_gguf_detok_spaces).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
