# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""The **torch-bound** REINFORCE-with-KL step (`fieldkit[rl]`, RV-1).

This is the trainer half of the vendored `clawgym-on-spark-grpo` loop — the one
piece that genuinely needs the GPU stack (torch + peft + transformers +
safetensors). Importing this module *is* the `fieldkit[rl]` install gate:
:func:`fieldkit.rl.gpu_seams` imports it lazily and turns a missing-dependency
``ImportError`` into a friendly ``RLLoopError`` pointing at the extra. Plain
``import fieldkit.rl`` never reaches here, so it stays stdlib-cheap.

The math is faithful to the proven `grpo_train.py` (single-epoch, sequence-level
advantage):

    L = -A · mean_token(log π_θ(a_t | h_t))    over assistant tokens
        + β · mean_token(KL[π_θ || π_ref])      K3 estimator (Schulman 2020)

with ``A`` the group-relative advantage `fieldkit.reward.group_advantage` already
computed, and the **K3 KL** ``exp(-Δ) - (-Δ) - 1`` (Δ = log π_θ - log π_ref) for a
stable, non-negative, unbiased penalty against a **frozen reference snapshot**.
PPO clipping is a no-op (the rollout policy *is* the starting policy — ratio = 1
at single-epoch). Two faithful tricks carry over verbatim:

- **CPU-resident reference snapshot + swap-in forward** — sidesteps peft's
  multi-adapter meta-parameter bug under ``device_map="auto"`` (stash the
  trainable LoRA weights, copy the frozen snapshot in, forward under
  ``no_grad``, restore). Classic GRPO fixed-SFT-init: the reference is the
  step-0 adapter, frozen for the whole run.
- **assistant-token mask by prefix walk** — the chat template is applied
  incrementally so only the *response* tokens carry gradient.

Generalized from clawgym's multi-turn agentic trajectories to the **single-turn
QA** contract `fieldkit.reward` scores: the prompt is the bench question (the
sampler stored it on the rollout), the response is the policy's completion.

**Resident across steps (RV-10).** Unlike the original per-step CLI (which paid
the ~124 s base reload every step), this keeps the 7B base + policy LoRA +
optimizer + reference snapshot resident in a `_TrainerState`, so only the LoRA
weights move. One lane, trainer-resident, ~30 GiB margin — the 2026-04-22 OOM
envelope (`[[project_spark_unified_memory_oom]]`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from fieldkit._rl_gpu_serve import RLBackendConfig, VLLMLane

_ADV_EPS = 1e-6


def _per_token_logp(
    model: Any, input_ids: "torch.Tensor", attention_mask: "torch.Tensor"
) -> "torch.Tensor":
    """Per-token log-prob of the actually-emitted next token (shifted)."""
    out = model(input_ids=input_ids, attention_mask=attention_mask)
    logits = out.logits[:, :-1, :]
    targets = input_ids[:, 1:]
    log_probs = torch.log_softmax(logits.float(), dim=-1)
    return log_probs.gather(-1, targets.unsqueeze(-1)).squeeze(-1)


def _input_and_assistant_mask(
    messages: list[dict[str, str]], tokenizer: Any, max_length: int = 8192
) -> tuple[list[int], list[int]]:
    """Tokenize via the chat template + mark assistant-token positions by a
    prefix walk (the response tokens are the only ones that carry gradient)."""
    prev_len = 0
    assistant_mask: list[int] = []
    for i, m in enumerate(messages):
        partial = tokenizer.apply_chat_template(
            messages[: i + 1], tokenize=True, add_generation_prompt=False, return_dict=True
        )
        cur_len = len(partial["input_ids"])
        new_tokens = cur_len - prev_len
        assistant_mask.extend([1 if m["role"] == "assistant" else 0] * new_tokens)
        prev_len = cur_len
    full = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=False, return_dict=True
    )
    input_ids = full["input_ids"]
    while len(assistant_mask) < len(input_ids):
        assistant_mask.append(0)
    if len(input_ids) > max_length:
        input_ids = input_ids[:max_length]
        assistant_mask = assistant_mask[:max_length]
    return input_ids, assistant_mask


@dataclass
class _TrainerState:
    """Resident model + optimizer + frozen reference snapshot (load once)."""

    model: Any
    tokenizer: Any
    optimizer: Any
    ref_snapshot: dict[str, "torch.Tensor"] = field(default_factory=dict)
    device: Any = None


def _load_state(cfg: RLBackendConfig, grpo_config: Any) -> _TrainerState:
    if not cfg.adapter_init:
        raise RuntimeError(
            "FK_RL_ADAPTER_INIT is unset — the trainer needs the SFT-init LoRA "
            "to load + train as the policy (RV-1)."
        )
    base = AutoModelForCausalLM.from_pretrained(
        cfg.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="sdpa",
    )
    base.gradient_checkpointing_enable()
    if hasattr(base, "config"):
        base.config.use_cache = False
    model = PeftModel.from_pretrained(base, cfg.adapter_init, is_trainable=True)
    model.train()

    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    kl_beta = float(getattr(grpo_config, "kl_coef", 0.0))
    ref_snapshot: dict[str, torch.Tensor] = {}
    if kl_beta > 0:
        # Classic GRPO fixed-SFT-init reference: freeze the step-0 LoRA weights
        # as a CPU-resident snapshot for the whole run.
        for n, p in model.named_parameters():
            if p.requires_grad:
                ref_snapshot[n] = p.detach().clone().cpu()

    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=float(getattr(grpo_config, "lr", 1e-6)),
    )
    return _TrainerState(
        model=model,
        tokenizer=tokenizer,
        optimizer=optimizer,
        ref_snapshot=ref_snapshot,
        device=base.device,
    )


def make_trainer(cfg: RLBackendConfig, lane: VLLMLane, grpo_config: Any) -> Any:
    """Return the `trainer(rollouts, advantages, step)` seam (RV-1/RV-5).

    Lazily loads the resident `_TrainerState` on the first call (the 7B base +
    policy LoRA + optimizer + reference snapshot), then on every step applies one
    advantage-weighted REINFORCE-with-KL gradient step over the rollouts whose
    advantage is non-degenerate, saves the updated LoRA, and **kill-and-restarts
    the vLLM lane** so the next rollout samples the lifted policy. Returns the
    per-step metrics `RLLoop` records on its `Trial` (`loss` / `kl` /
    `checkpoint` / `train_s` / `total_s`).
    """
    state: dict[str, _TrainerState] = {}
    max_length = cfg.max_model_len
    kl_beta = float(getattr(grpo_config, "kl_coef", 0.0))

    def trainer(rollouts: Sequence[Any], advantages: Sequence[float], step: int) -> dict[str, Any]:
        if "s" not in state:
            state["s"] = _load_state(cfg, grpo_config)
        st = state["s"]
        model, tokenizer, optimizer = st.model, st.tokenizer, st.optimizer
        device = st.device

        t0 = time.time()
        model.train()
        optimizer.zero_grad(set_to_none=True)

        n_used = 0
        sum_loss = 0.0
        sum_kl = 0.0
        for rollout, adv in zip(rollouts, advantages, strict=True):
            if abs(adv) < _ADV_EPS:
                continue
            prompt = getattr(rollout, "prompt", "") or ""
            prediction = getattr(rollout, "prediction", "") or ""
            messages = [
                *cfg.messages_for(prompt),
                {"role": "assistant", "content": prediction},
            ]
            input_ids, assistant_mask = _input_and_assistant_mask(
                messages, tokenizer, max_length
            )
            if sum(assistant_mask) == 0 or len(input_ids) >= max_length:
                continue

            input_ids_t = torch.tensor([input_ids], dtype=torch.long, device=device)
            attn_t = torch.ones_like(input_ids_t)
            mask_shifted = torch.tensor(
                [assistant_mask[1:]], dtype=torch.bool, device=device
            )
            adv_t = torch.tensor(float(adv), dtype=torch.float32, device=device)

            pol_logp = _per_token_logp(model, input_ids_t, attn_t)
            pol_logp_a = pol_logp[mask_shifted]
            policy_loss = -adv_t * pol_logp_a.mean()

            if kl_beta > 0 and st.ref_snapshot:
                stash: dict[str, torch.Tensor] = {}
                with torch.no_grad():
                    for n, p in model.named_parameters():
                        if n in st.ref_snapshot:
                            stash[n] = p.data.clone()
                            p.data.copy_(st.ref_snapshot[n].to(p.device, dtype=p.dtype))
                with torch.no_grad():
                    ref_logp = _per_token_logp(model, input_ids_t, attn_t)
                with torch.no_grad():
                    for n, p in model.named_parameters():
                        if n in stash:
                            p.data.copy_(stash[n])
                ref_logp_a = ref_logp[mask_shifted]
                delta = pol_logp_a - ref_logp_a  # log π_pol − log π_ref
                kl_per_token = torch.exp(-delta) - (-delta) - 1.0  # K3 estimator
                kl_loss = kl_beta * kl_per_token.mean()
                loss = policy_loss + kl_loss
            else:
                kl_loss = torch.zeros((), device=device)
                loss = policy_loss

            loss.backward()
            n_used += 1
            sum_loss += float(loss.detach())
            sum_kl += float(kl_loss.detach())

        if n_used == 0:
            # Degenerate step — nothing to learn from. Keep the lane as-is.
            return {
                "loss": 0.0, "kl": 0.0, "checkpoint": "",
                "train_s": round(time.time() - t0, 1), "total_s": round(time.time() - t0, 1),
                "n_rollouts_used": 0,
            }

        for p in model.parameters():
            if p.grad is not None:
                p.grad /= n_used
        grad_norm = torch.nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], 1.0
        )
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        train_s = time.time() - t0

        out_dir = cfg.work_dir / f"step-{step:03d}" / "adapter"
        out_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(out_dir)
        tokenizer.save_pretrained(out_dir)

        # Swap the lane to the lifted policy (RV-5 — the eliminable ~3.5 min).
        lane.restart(str(out_dir))

        return {
            "loss": round(sum_loss / n_used, 4),
            "kl": round(sum_kl / n_used, 4),
            "checkpoint": str(out_dir),
            "grad_norm": round(float(grad_norm), 4),
            "n_rollouts_used": n_used,
            "train_s": round(train_s, 1),
            "total_s": round(time.time() - t0, 1),
        }

    return trainer
