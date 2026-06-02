#!/usr/bin/env python3
"""Repolish + repush the four patent-strategist v3 HF READMEs.

Why this script exists
----------------------
The 2026-05-22 Phase 6.5 bakeoff publish landed four cards with
`## Known issues with the v3 corpus` as the first H2 after the title — no
positioning, no value-prop, no audience. A HF visitor's first impression
was that the model hallucinates. This script rebuilds each card via
`fieldkit.publish.ModelCard.render()` (extended in v0.5.x with
positioning / lane / drift blocks) so the section order is:

    What this model does → Spark-tested → Variants → Choosing this lane
    → How to run → Methods → Known drift → Other Orionfold variants

…and uploads README.md ONLY to each of the four repos via
`huggingface_hub.upload_file` (no weights re-uploaded).

Usage
-----
    # 1. Render the four READMEs to /tmp/hf-readme-revise/<slug>/ — review them.
    python scripts/republish_patent_strategist_readmes.py --dry-run

    # 2. Push live (reads HF_TOKEN from .env.local or env).
    python scripts/republish_patent_strategist_readmes.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "fieldkit" / "src"))

from fieldkit.publish import ModelCard  # noqa: E402


BASE_MODEL = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
ARTICLE_SLUG = "patent-strategist-bakeoff-unsloth-vs-nemo-framework"
ARTICLE_TITLE = "Two paths to the same chain — Unsloth vs NeMo Framework on Spark"

POSITIONING = {
    "headline": "Offline patent-prosecution reasoning on Spark-class hardware",
    "problem": (
        "Patent prosecution work — claim construction, MPEP-grounded "
        "office-action responses, Markush analysis, doctrine-of-equivalents "
        "reasoning — happens inside firms that can't ship privileged client "
        "text to a hosted frontier API. This release distills DeepSeek-R1's "
        "chain-of-thought reasoning onto a 5,000-row synthetic patent-"
        "reasoning corpus so a single Spark-class box can run the workflow "
        "offline, with full IRAC-shaped reasoning chains."
    ),
    "use_cases": [
        "Claim construction (Markush groups, doctrine of equivalents)",
        "MPEP-grounded office-action argument drafting",
        "Prior-art relevance + non-obviousness reasoning chains",
        "Patent-licensing scenario analysis (most-favored-licensee, FTO)",
    ],
    "audience": (
        "Patent attorneys, prosecution-team engineers, and IP-strategy teams "
        "running privileged workflows offline on Spark-class hardware (GB10, "
        "128 GB unified memory) or comparable edge devices."
    ),
}

KNOWN_DRIFT = (
    {
        "item": '"metes-and-times" terminology',
        "bound": (
            "Two known terminology drifts inherited from the v3 synthetic "
            "corpus; balance of probe answers (~99%) cite real MPEP sections. "
            "Correct legal term in claim construction is *metes and bounds*."
        ),
    },
    {
        "item": "Fabricated MPEP §2163.05(s) citation",
        "bound": (
            "Same scope — corpus-generator artifact, not a model-wide "
            "hallucination pattern. Real §2163.05 has subsections (a)–(f) on "
            "written-description support; subsection (s) does not exist."
        ),
    },
)

# Only the NeMo Framework lane is published. The Unsloth lane was the bakeoff's
# comparison baseline (its numbers are documented in the article) but its repos
# were unpublished 2026-05-24 — it generated spaceless `<think>` text that the
# nemo lane, on the identical recipe, does not. So the cards cross-link only the
# two live NeMo siblings.
SIBLINGS = (
    {"hf_repo": "Orionfold/patent-strategist-v3-nemo", "lane": "NeMo Framework", "format": "BF16 (transformers)"},
    {"hf_repo": "Orionfold/patent-strategist-v3-nemo-GGUF", "lane": "NeMo Framework", "format": "GGUF (llama.cpp)"},
)

# Runnable on-ramps (notebooks-as-artifacts T6) — the builder + user notebook
# pair targets the NeMo lane, so every card carries the identical
# badge row directly under the one-liner (NARRATIVE-CONTRACT Rule 8: a
# navigation aid, not a claim — positioning still leads). Colab/Kaggle open the
# committed `.ipynb` from `main`. See _SPECS/notebooks-as-artifacts-v1.md §8.3.
# URLs are built by the SAME fieldkit helpers that wrote the in-notebook badge
# row (colab path is `/github/owner/...`, kaggle is `?src=https://github.com/...`)
# so the two surfaces can't drift.
from fieldkit.notebook import colab_url, kaggle_url, notebook_path  # noqa: E402
NOTEBOOKS = tuple(
    {
        "label": label,
        "colab": colab_url(notebook_path("patent-strategist", which)),
        "kaggle": kaggle_url(notebook_path("patent-strategist", which)),
    }
    for label, which in (("Build it", "builder"), ("Use it", "user"))
)

GGUF_VARIANT_FILES = {
    "Q4_K_M": {"size": "4.68 GB"},
    "Q5_K_M": {"size": "5.45 GB"},
    "Q6_K": {"size": "6.26 GB"},
    "Q8_0": {"size": "8.11 GB"},
}

UNSLOTH_GGUF_PPL = {"Q4_K_M": 11.2987, "Q5_K_M": 10.9716, "Q6_K": 10.8737, "Q8_0": 10.8446}
UNSLOTH_GGUF_TPS = {"Q4_K_M": 41.041447, "Q5_K_M": 32.473199, "Q6_K": 30.785894, "Q8_0": 26.560534}

NEMO_GGUF_PPL = {"Q4_K_M": 10.2415, "Q5_K_M": 10.0436, "Q6_K": 9.9624, "Q8_0": 9.9288}
NEMO_GGUF_TPS = {"Q4_K_M": 39.565688, "Q5_K_M": 35.003921, "Q6_K": 30.658167, "Q8_0": 26.512266}

LLAMA_CPP_EXAMPLE = (
    "A licensee under a non-exclusive patent license discovers the licensor "
    "has signed a more favorable royalty rate with a later licensee. The "
    "agreement contains a most-favored-licensee clause requiring rate parity. "
    "Walk through the legal and commercial steps the original licensee should "
    "take to enforce parity, including notice requirements and remedies."
)

BF16_TRANSFORMERS_SNIPPET_TEMPLATE = '''from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

model_id = "Orionfold/{slug}"
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id, torch_dtype=torch.bfloat16, device_map="auto"
)

prompt = (
    "<｜User｜>A patent claim recites \\"a fastener selected from the group consisting "
    "of bolts, screws, and rivets.\\" Walk through the Markush-group construction "
    "and explain how doctrine of equivalents applies to a magnetic snap.<｜Assistant｜>"
)
inputs = tok(prompt, return_tensors="pt").to(model.device)
out = model.generate(**inputs, max_new_tokens=1024, temperature=0.6, top_p=0.95)
print(tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True))'''


# Per-slug lane copy — this is where the artifact-by-artifact differentiation
# lives. The renderer's default lane copy keys off stack_origin alone; here we
# inject lane summaries that name the bakeoff trade-off explicitly.
LANE_SUMMARY = {
    "patent-strategist-v3-unsloth": (
        "**Unsloth-trained BF16 merged weights.** Pick this lane if you want "
        "to continue training in Unsloth's 4-bit QLoRA workflow or if you "
        "need transformers-format weights for inference paths outside "
        "`llama.cpp`. The bakeoff measured 7h 34m training wall on this lane "
        "(vs 5h 38m on NeMo Framework) at probe think rate 0.80 / mean chain "
        "916 tokens. For pure inference on Spark-class hardware, the GGUF "
        "sibling is faster; for the bakeoff-winning checkpoint, see the NeMo "
        "lane."
    ),
    "patent-strategist-v3-unsloth-GGUF": (
        "**`llama.cpp`-quantized variants of the Unsloth-trained checkpoint.** "
        "Sustained 32.5 tok/s on Spark at Q5_K_M, perplexity 10.97. Pick this "
        "lane if you've benchmarked the Unsloth path elsewhere and want "
        "consistency with that lineage — otherwise the [NeMo Framework "
        "sibling](https://huggingface.co/Orionfold/patent-strategist-v3-nemo-GGUF) "
        "is the bakeoff winner on the same recipe (-11.5% perplexity, +7.7% "
        "tok/s, +44% mean reasoning-chain length)."
    ),
    "patent-strategist-v3-nemo": (
        "**NeMo Framework-trained BF16 merged weights — the bakeoff-winning "
        "lane.** Pick this for production-grade inference via "
        "Triton / TensorRT-LLM, for continued fine-tuning in NeMo's PEFT "
        "recipe stack, or to export to other quantization paths. The bakeoff "
        "measured 5h 38m training wall on this lane (-26% vs the Unsloth "
        "baseline on the same recipe) at probe think rate 0.80 / mean chain "
        "1,320 tokens (+44% reasoning depth over the Unsloth baseline). For "
        "pure inference on Spark-class hardware, the GGUF sibling is faster."
    ),
    "patent-strategist-v3-nemo-GGUF": (
        "**`llama.cpp`-quantized variants of the NeMo Framework-trained "
        "checkpoint — the bakeoff-winning lane.** Sustained 35.0 tok/s on "
        "Spark at Q5_K_M, perplexity 10.04 (-11.5% vs the Unsloth baseline on "
        "the same recipe), mean reasoning chain 1,320 tokens (+44%). Default "
        "pick for Spark-class offline patent reasoning — and the only "
        "published lane: the Unsloth baseline was measured for the bakeoff "
        "(see the article) but is not published as a downloadable artifact."
    ),
}


def _spark_block_for_bf16(lane: str) -> str:
    """The BF16 cards ship a different measurement triple (train wall + probe
    think rate + mean chain length) than the GGUF cards (perplexity + tok/s).
    The renderer's auto Spark-tested block keys off perplexity/tokens_per_sec,
    so for BF16 we splice in this hand-written table via the `lane_summary`
    free-form copy after the lane intro."""
    if lane == "unsloth":
        return (
            "\n\n**Spark measurements (BF16 merged):**\n\n"
            "| Variant | Size | Train wall | Probe think rate | Mean chain |\n"
            "|---|---|---|---|---|\n"
            "| BF16 | 15.26 GB | 7h 34m | 0.80 | 916 tok |\n"
        )
    return (
        "\n\n**Spark measurements (BF16 merged):**\n\n"
        "| Variant | Size | Train wall | Probe think rate | Mean chain |\n"
        "|---|---|---|---|---|\n"
        "| BF16 | 15.26 GB | 5h 38m | 0.80 | 1,320 tok |\n"
    )


def build_card(slug: str) -> ModelCard:
    is_gguf = slug.endswith("-GGUF") or slug.endswith("-gguf")
    is_nemo = "nemo" in slug
    stack = "nemo" if is_nemo else "unsloth"
    title_lane = "NeMo Framework lane" if is_nemo else "Unsloth lane"
    title_fmt = "GGUF" if is_gguf else "BF16 HF"
    title = f"patent-strategist v3 — {title_lane} ({title_fmt})"

    if is_gguf:
        one_liner = (
            f"`GGUF` quantizations of `{BASE_MODEL}`, fine-tuned on the v3 "
            f"synthetic patent-reasoning corpus and verified end-to-end on "
            f"the NVIDIA DGX Spark (GB10, 128 GB unified memory)."
        )
    else:
        one_liner = (
            f"`safetensors` BF16 merged weights of a LoRA fine-tune of "
            f"`{BASE_MODEL}` on a 5,000-row synthetic patent-reasoning corpus, "
            f"trained with **{('NeMo Framework' if is_nemo else 'Unsloth')}** "
            f"on a NVIDIA DGX Spark (GB10, 128 GB unified memory)."
        )

    tags = [
        "spark-tested",
        "orionfold",
        f"base_model:{BASE_MODEL}",
        "patent",
        "patent-strategist",
        "reasoning",
        "lora-finetune",
        "bakeoff",
        "r1-distill",
    ]
    if is_gguf:
        tags.insert(0, "gguf")
        library_name = "gguf"
        quant_format = "gguf"
    else:
        tags.insert(0, "transformers")
        tags.insert(1, "safetensors")
        tags.insert(2, "bf16")
        library_name = "transformers"
        quant_format = "safetensors"

    perplexity: dict = {}
    tokens_per_sec: dict = {}
    variants: tuple = ()
    recommended_variant = None
    if is_gguf:
        ppl = NEMO_GGUF_PPL if is_nemo else UNSLOTH_GGUF_PPL
        tps = NEMO_GGUF_TPS if is_nemo else UNSLOTH_GGUF_TPS
        perplexity = ppl
        tokens_per_sec = tps
        variants = tuple(
            {
                "name": v,
                "size": GGUF_VARIANT_FILES[v]["size"],
                "recommended": _gguf_rec(v),
            }
            for v in ("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0")
        )
        recommended_variant = "Q5_K_M"

    lane_summary = LANE_SUMMARY[slug]
    if not is_gguf:
        lane_summary = lane_summary + _spark_block_for_bf16(stack)

    return ModelCard(
        title=title,
        one_liner=one_liner,
        base_model=BASE_MODEL,
        library_name=library_name,
        quant_format=quant_format,
        tags=tuple(tags),
        variants=variants,
        perplexity=perplexity,
        tokens_per_sec=tokens_per_sec,
        recommended_variant=recommended_variant,
        hf_repo=f"Orionfold/{slug}",
        llama_cpp_example_prompt=LLAMA_CPP_EXAMPLE if is_gguf else None,
        transformers_snippet=(
            BF16_TRANSFORMERS_SNIPPET_TEMPLATE.format(slug=slug) if not is_gguf else None
        ),
        article_slug=ARTICLE_SLUG,
        article_title=ARTICLE_TITLE,
        positioning=POSITIONING,
        stack_origin=stack,
        lane_summary=lane_summary,
        known_drift=KNOWN_DRIFT,
        siblings=SIBLINGS,
        notebooks=NOTEBOOKS,
    )


def _gguf_rec(name: str) -> str:
    table = {
        "Q4_K_M": "Smallest footprint with workable quality — fits on a 6 GB GPU; pick this for tightest RAM budgets.",
        "Q5_K_M": "**Recommended** — best quality/throughput balance on Spark (32–35 tok/s, perplexity within 2% of Q8_0).",
        "Q6_K": "Near-lossless quality with modest size bump; pick if you have headroom.",
        "Q8_0": "Effectively lossless; reach for this when reasoning-chain fidelity matters more than throughput.",
    }
    return table[name]


def render_all(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, Path] = {}
    for slug in (
        "patent-strategist-v3-nemo",
        "patent-strategist-v3-nemo-GGUF",
    ):
        card = build_card(slug)
        body = card.render()
        slug_dir = out_dir / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        readme_path = slug_dir / "README.md"
        readme_path.write_text(body, encoding="utf-8")
        rendered[slug] = readme_path
        print(f"  rendered → {readme_path}  ({len(body)} bytes)")
    return rendered


def push_all(rendered: dict[str, Path], token: str) -> None:
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    for slug, readme_path in rendered.items():
        print(f"  uploading README to Orionfold/{slug} …")
        api.upload_file(
            path_or_fileobj=str(readme_path),
            path_in_repo="README.md",
            repo_id=f"Orionfold/{slug}",
            repo_type="model",
            commit_message=(
                "Drop Unsloth sibling cross-links — the Unsloth lane was "
                "unpublished (spaceless-think artifact absent from this NeMo "
                "lane); cards now cross-link only the live NeMo siblings."
            ),
        )
        print(f"  pushed → https://huggingface.co/Orionfold/{slug}")


def _load_hf_token() -> str:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        return token
    env_local = REPO_ROOT / ".env.local"
    if env_local.exists():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("HF_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(
        "HF_TOKEN not found — set the env var or add it to .env.local"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render to /tmp/hf-readme-revise/<slug>/README.md and exit without pushing.",
    )
    parser.add_argument(
        "--out-dir",
        default="/tmp/hf-readme-revise",
        help="Directory to render READMEs into (default: /tmp/hf-readme-revise)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    print(f"Rendering {len(SIBLINGS)} READMEs to {out_dir}/")
    rendered = render_all(out_dir)
    if args.dry_run:
        print("\nDry run complete. Review the rendered files, then re-run without --dry-run.")
        return 0

    token = _load_hf_token()
    print(f"\nPushing README.md only to {len(rendered)} Orionfold repos …")
    push_all(rendered, token)
    print("\nDone. Verify via:")
    for slug in rendered:
        print(f"  curl -s https://huggingface.co/Orionfold/{slug}/raw/main/README.md | head -30")
    return 0


if __name__ == "__main__":
    sys.exit(main())
