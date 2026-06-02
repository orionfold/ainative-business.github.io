# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the v0.5.x positioning + lane + drift render blocks.

Covers the four model-card sections added after the 2026-05-22 patent-strategist
publish landed cards with `## Known issues` as the first H2 — see
`[[hf-readme-positioning-first]]` memory + `hf-publisher/references/card-polish.md`
§0 (section order), §6 (drift rules), §7 (lane differentiation).
"""

from __future__ import annotations

from fieldkit.publish import ArtifactManifest, ModelCard


# ---------------- ## What this model does ---------------------------------


def test_positioning_block_renders_with_problem_use_cases_and_audience() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        positioning={
            "headline": "Offline patent reasoning",
            "problem": "Patent prosecution work happens behind firewalls.",
            "use_cases": ["Claim construction", "MPEP citation"],
            "audience": "Patent attorneys on Spark-class hardware.",
        },
    )
    out = card.render()
    assert "## What this model does" in out
    assert "**Offline patent reasoning**" in out
    assert "Patent prosecution work happens behind firewalls." in out
    assert "- Claim construction" in out
    assert "- MPEP citation" in out
    assert "**Who this is for:** Patent attorneys on Spark-class hardware." in out


def test_positioning_block_skipped_when_unset() -> None:
    card = ModelCard(title="x", one_liner="y", base_model="z")
    out = card.render()
    assert "## What this model does" not in out


def test_positioning_block_leads_above_spark_tested() -> None:
    """Per `[[hf-readme-positioning-first]]`: positioning above measurement."""
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        positioning={"problem": "P", "use_cases": ["uc"]},
        variants=({"name": "Q4_K_M", "size": "1 GB", "recommended": "r"},),
        perplexity={"Q4_K_M": 7.0},
        tokens_per_sec={"Q4_K_M": 20.0},
    )
    out = card.render()
    pos_at = out.index("## What this model does")
    spark_at = out.index("## Spark-tested")
    assert pos_at < spark_at, "positioning must come before Spark-tested"


# ---------------- Notebook badge row (notebooks-as-artifacts v1) ----------


def test_notebook_section_renders_table_with_colab_and_kaggle_links() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        notebooks=(
            {"label": "Build it", "colab": "https://colab/builder", "kaggle": "https://kaggle/builder"},
            {"label": "Use it", "colab": "https://colab/user", "kaggle": "https://kaggle/user"},
        ),
    )
    out = card.render()
    assert "colab-badge.svg" in out
    assert "open-in-kaggle.svg" in out
    assert "(https://colab/builder)" in out
    assert "(https://kaggle/user)" in out
    # Titled section + a table, one row per notebook (Build it → Builder, etc.).
    assert "## Notebooks" in out
    assert "| Notebook | What it does | Open |" in out
    assert "| **Builder** |" in out
    assert "| **User** |" in out
    # The retired single-line / two-row badge forms must be gone.
    assert "**Notebooks —**" not in out
    assert "**Build it:**" not in out
    assert "**Use it:**" not in out


def test_notebook_section_skipped_when_unset() -> None:
    card = ModelCard(title="x", one_liner="y", base_model="z")
    out = card.render()
    assert "colab-badge.svg" not in out
    assert "## Notebooks" not in out


def test_notebook_section_skips_entry_with_no_urls() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        notebooks=({"label": "empty"}, {"colab": "https://colab/only"}),
    )
    out = card.render()
    # The url-less entry contributes no row; the colab-only entry renders one badge.
    assert "colab-badge.svg" in out
    assert "open-in-kaggle.svg" not in out
    assert out.count("| **") == 1  # exactly one notebook row


def test_notebook_section_sits_after_positioning() -> None:
    """Per _GUIDES/NARRATIVE-CONTRACT.md Rule 8 the runnable on-ramp is its own
    `## Notebooks` section placed AFTER the positioning lead — positioning is
    the first prose the reader meets, then the on-ramp."""
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        positioning={"problem": "P", "use_cases": ["uc"]},
        notebooks=({"label": "Use it", "colab": "https://colab/user"},),
    )
    out = card.render()
    pos_at = out.index("## What this model does")
    nb_at = out.index("## Notebooks")
    assert pos_at < nb_at, "notebooks section must sit after positioning"


# ---------------- ## Choosing this lane -----------------------------------


def test_lane_summary_renders_when_provided_explicitly() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        lane_summary="**NeMo lane.** Pick this for production.",
    )
    out = card.render()
    assert "## Choosing this lane" in out
    assert "**NeMo lane.** Pick this for production." in out


def test_lane_summary_defaults_keyed_off_stack_origin_for_gguf() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        stack_origin="nemo",
        quant_format="gguf",
    )
    out = card.render()
    assert "## Choosing this lane" in out
    assert "llama.cpp" in out
    assert "NEMO" in out or "nemo" in out.lower()


def test_lane_summary_defaults_keyed_off_stack_origin_for_bf16() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        stack_origin="unsloth",
        quant_format="safetensors",
    )
    out = card.render()
    assert "## Choosing this lane" in out
    assert "Unsloth" in out
    assert "continued fine-tuning" in out or "continue" in out


def test_lane_block_skipped_when_no_stack_origin_and_no_summary() -> None:
    card = ModelCard(title="x", one_liner="y", base_model="z")
    out = card.render()
    assert "## Choosing this lane" not in out


def test_stack_origin_adds_trained_with_tag_to_frontmatter() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        stack_origin="nemo",
        tags=("gguf", "spark-tested"),
    )
    out = card.render()
    assert "- trained-with-nemo" in out


def test_stack_origin_does_not_duplicate_existing_trained_with_tag() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        stack_origin="unsloth",
        tags=("gguf", "spark-tested", "trained-with-unsloth"),
    )
    out = card.render()
    assert out.count("- trained-with-unsloth") == 1


# ---------------- ## Known drift ------------------------------------------


def test_known_drift_block_renders_each_entry_as_bounded_bullet() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        known_drift=(
            {"item": "thing-A", "bound": "2 of 200 bench Qs"},
            {"item": "thing-B", "bound": "<1% of probe answers"},
        ),
    )
    out = card.render()
    assert "## Known drift" in out
    assert "- **thing-A**" in out
    assert "2 of 200 bench Qs" in out
    assert "- **thing-B**" in out
    assert "<1% of probe answers" in out


def test_known_drift_block_skipped_when_unset() -> None:
    card = ModelCard(title="x", one_liner="y", base_model="z")
    out = card.render()
    assert "## Known drift" not in out


def test_known_drift_block_lives_below_methods_not_above_fold() -> None:
    """The whole point of v0.5.x repolish — drift goes AFTER Methods."""
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        positioning={"problem": "P"},
        known_drift=({"item": "thing", "bound": "scope"},),
        article_slug="some-article",
    )
    out = card.render()
    pos_at = out.index("## What this model does")
    methods_at = out.index("## Methods")
    drift_at = out.index("## Known drift")
    assert pos_at < methods_at < drift_at, (
        "drift block must come AFTER Methods, never above-the-fold"
    )


def test_known_drift_does_not_render_any_forward_looking_roadmap_copy() -> None:
    """READMEs ship current truth only — no `fix_eta`, no 'v4 will fix this'."""
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        # Even if a caller smuggles a fix_eta-shaped key, the renderer must
        # not surface it. This guards against future regressions.
        known_drift=(
            {"item": "thing", "bound": "scope", "fix_eta": "v4 will fix this"},
        ),
    )
    out = card.render()
    assert "v4 will fix this" not in out
    assert "Fix:" not in out
    assert "roadmap" not in out.lower()


def test_known_drift_skips_entries_with_empty_item() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        known_drift=(
            {"item": "", "bound": "x"},
            {"item": "real-thing", "bound": "scope"},
        ),
    )
    out = card.render()
    assert "- **real-thing**" in out
    assert "- ****" not in out


# ---------------- ## Other Orionfold variants -----------------------------


def test_siblings_block_renders_cross_link_table() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        siblings=(
            {"hf_repo": "Orionfold/foo-GGUF", "lane": "Unsloth", "format": "GGUF"},
            {"hf_repo": "Orionfold/foo", "lane": "Unsloth", "format": "BF16"},
        ),
    )
    out = card.render()
    assert "## Other Orionfold variants" in out
    assert "[`Orionfold/foo-GGUF`](https://huggingface.co/Orionfold/foo-GGUF)" in out
    assert "[`Orionfold/foo`](https://huggingface.co/Orionfold/foo)" in out


def test_siblings_block_skipped_when_unset() -> None:
    card = ModelCard(title="x", one_liner="y", base_model="z")
    out = card.render()
    assert "## Other Orionfold variants" not in out


# ---------------- Section ordering contract -------------------------------


def test_canonical_section_order_when_all_blocks_present() -> None:
    """The full v0.5.x section order — positioning first, drift last."""
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        positioning={"problem": "P", "use_cases": ["uc"]},
        variants=({"name": "Q4_K_M", "size": "1 GB", "recommended": "r"},),
        perplexity={"Q4_K_M": 7.0},
        tokens_per_sec={"Q4_K_M": 20.0},
        stack_origin="nemo",
        quant_format="gguf",
        lane_summary="Lane copy.",
        hf_repo="Orionfold/x-GGUF",
        article_slug="art",
        known_drift=({"item": "thing", "bound": "scope"},),
        siblings=({"hf_repo": "Orionfold/sib", "lane": "lane", "format": "fmt"},),
        notebooks=({"label": "Use it", "colab": "https://colab/user"},),
    )
    out = card.render()
    order = [
        "## What this model does",
        "## Notebooks",
        "## Spark-tested",
        "## Variants",
        "## Choosing this lane",
        "## How to run",
        "## Methods",
        "## Known drift",
        "## Other Orionfold variants",
    ]
    positions = [out.index(h) for h in order]
    assert positions == sorted(positions), (
        f"section order violated: {list(zip(order, positions))}"
    )
    # The Notebooks on-ramp section sits after positioning, before Spark-tested.
    assert out.index("## What this model does") < out.index("## Notebooks") < out.index("## Spark-tested")


# ---------------- ArtifactManifest mirror ---------------------------------


def test_artifact_manifest_carries_positioning_when_set() -> None:
    m = ArtifactManifest(
        slug="s",
        kind="quant",
        artifact_class="gguf",
        base_model="b",
        hf_repo="Orionfold/x",
        positioning={"problem": "P", "use_cases": ["uc"]},
    )
    d = m.to_dict()
    assert d["positioning"] == {"problem": "P", "use_cases": ["uc"]}


def test_artifact_manifest_carries_stack_origin_when_set() -> None:
    m = ArtifactManifest(
        slug="s",
        kind="quant",
        artifact_class="gguf",
        base_model="b",
        hf_repo="Orionfold/x",
        stack_origin="nemo",
    )
    d = m.to_dict()
    assert d["stack_origin"] == "nemo"


def test_artifact_manifest_carries_known_drift_when_set() -> None:
    m = ArtifactManifest(
        slug="s",
        kind="quant",
        artifact_class="gguf",
        base_model="b",
        hf_repo="Orionfold/x",
        known_drift=({"item": "thing", "bound": "scope"},),
    )
    d = m.to_dict()
    assert d["known_drift"] == [{"item": "thing", "bound": "scope"}]


def test_artifact_manifest_carries_notebooks_when_set() -> None:
    m = ArtifactManifest(
        slug="s",
        kind="notebook",
        artifact_class="ipynb",
        base_model="b",
        hf_repo="Orionfold/x",
        notebooks=(
            {"label": "Build it", "colab": "https://colab/b", "kaggle": "https://kaggle/b"},
            {"label": "Use it", "colab": "https://colab/u", "kaggle": "https://kaggle/u"},
        ),
    )
    d = m.to_dict()
    assert d["notebooks"] == [
        {"label": "Build it", "colab": "https://colab/b", "kaggle": "https://kaggle/b"},
        {"label": "Use it", "colab": "https://colab/u", "kaggle": "https://kaggle/u"},
    ]


def test_artifact_manifest_notebook_kind_is_valid() -> None:
    """The 6th kind round-trips through the manifest."""
    from fieldkit.publish import ARTIFACT_KINDS

    assert "notebook" in ARTIFACT_KINDS
    m = ArtifactManifest(
        slug="patent-strategist-notebooks",
        kind="notebook",
        artifact_class="ipynb",
        base_model="b",
        hf_repo="Orionfold/patent-strategist-v3-unsloth-GGUF",
        variants=("builder", "user"),
    )
    d = m.to_dict()
    assert d["kind"] == "notebook"
    assert d["class"] == "ipynb"
    assert d["variants"] == ["builder", "user"]


def test_artifact_manifest_omits_new_fields_when_unset() -> None:
    m = ArtifactManifest(
        slug="s",
        kind="quant",
        artifact_class="gguf",
        base_model="b",
        hf_repo="Orionfold/x",
    )
    d = m.to_dict()
    assert "positioning" not in d
    assert "stack_origin" not in d
    assert "known_drift" not in d
    assert "notebooks" not in d
