# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `fieldkit.publish`.

Covers:
- ModelCard.render() frontmatter + body sections.
- ArtifactManifest schema → dict / YAML round-trip.
- write_artifact_manifest disk writes.
- HFHubAdapter dry-run staging + push_folder logging.
- HFHubAdapter token resolution order.
- publish_quant orchestrator end-to-end (dry-run).
- _render_yaml_scalar edge cases.

Pure-stdlib module — runs offline, no `--spark` gate, no HF network access.
The live HF push path is exercised only behind `dry_run=False` and skipped
unless `huggingface_hub` is importable, which is left to integration runs.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from fieldkit.publish import (
    ARTIFACT_KINDS,
    ArtifactManifest,
    HFAuthError,
    HFHubAdapter,
    HFHubNotAvailable,
    ModelCard,
    ORIONFOLD_BRAND,
    ORIONFOLD_HF_HANDLE,
    PublishError,
    PublishResult,
    publish_quant,
    write_artifact_manifest,
)
from fieldkit.publish import _default_variant_recommendation, _render_yaml_scalar


# ---------------- constants ------------------------------------------------


def test_constants_are_locked_in() -> None:
    assert ORIONFOLD_BRAND == "Orionfold LLC"
    assert ORIONFOLD_HF_HANDLE == "Orionfold"


def test_artifact_kinds_are_the_canonical_set() -> None:
    assert ARTIFACT_KINDS == (
        "quant",
        "lora",
        "adapter",
        "dataset",
        "bench",
        "notebook",
        "harness",  # Harnesses content line (_SPECS/hermes-harness-v1.md)
        "skill",
    )


def test_manifest_known_drift_renders_structured() -> None:
    """known_drift (list-of-dict) must emit structured YAML mappings, not the
    Python repr of each dict — the destination Zod schema needs item/bound keys."""
    m = ArtifactManifest(
        slug="x", kind="harness", artifact_class="agent-harness",
        base_model="b", hf_repo="Orionfold/x",
        known_drift=({"item": "Tool-call sample size", "bound": "8 tasks/lane"},),
    )
    y = m.to_yaml()
    assert "  - item: Tool-call sample size" in y
    assert "    bound: 8 tasks/lane" in y
    assert "{'item'" not in y  # never the Python repr
    # round-trips through a YAML parser back to the structured shape
    import yaml
    parsed = yaml.safe_load(y)
    assert parsed["known_drift"] == [{"item": "Tool-call sample size", "bound": "8 tasks/lane"}]


# ---------------- ModelCard ------------------------------------------------


def test_model_card_frontmatter_has_canonical_fields() -> None:
    card = ModelCard(
        title="Foo-30B-GGUF",
        one_liner="Quants of Foo-30B.",
        base_model="nvidia/Foo-30B",
    )
    out = card.render()
    head, _, _ = out.partition("---\n\n")
    # Frontmatter delimited by --- ... ---
    assert out.startswith("---\n")
    assert "license: apache-2.0" in head
    assert "base_model: nvidia/Foo-30B" in head
    assert "library_name: gguf" in head
    assert "pipeline_tag: text-generation" in head
    assert "model_creator:" in head


def test_model_card_spark_tested_block_renders_with_measurements() -> None:
    card = ModelCard(
        title="Foo-30B-GGUF",
        one_liner="Quants.",
        base_model="nvidia/Foo-30B",
        variants=(
            {"name": "Q4_K_M", "size": "18.0 GB", "recommended": "Default."},
            {"name": "Q8_0", "size": "31.5 GB", "recommended": "Lossless-ish."},
        ),
        perplexity={"Q4_K_M": 7.123, "Q8_0": 6.901},
        tokens_per_sec={"Q4_K_M": 24.5, "Q8_0": 12.1},
        sustained_load_minutes=42.0,
    )
    out = card.render()
    assert "## Spark-tested" in out
    assert "| Variant | Size | Perplexity (wikitext-2) | tok/s on Spark |" in out
    assert "| Q4_K_M | 18.0 GB | 7.123 | 24.5 |" in out
    assert "| Q8_0 | 31.5 GB | 6.901 | 12.1 |" in out
    assert "sustained-load minutes" in out
    assert "**42 min**" in out


def test_model_card_renders_vertical_eval_column_when_provided() -> None:
    card = ModelCard(
        title="finance-Llama3-8B-GGUF",
        one_liner="Vertical-curator quants.",
        base_model="instruction-pretrain/finance-Llama3-8B",
        variants=(
            {"name": "Q4_K_M", "size": "4.6 GB", "recommended": "Default."},
            {"name": "Q8_0", "size": "8.5 GB", "recommended": "Lossless-ish."},
        ),
        perplexity={"Q4_K_M": 8.4, "Q8_0": 8.1},
        tokens_per_sec={"Q4_K_M": 72.3, "Q8_0": 45.1},
        sustained_load_minutes=18.0,
        vertical_eval={"Q4_K_M": 0.62, "Q8_0": 0.66},
        vertical_eval_name="FinanceBench (n=50, numeric_match)",
    )
    out = card.render()
    assert "## Spark-tested" in out
    # Header now has the 5th column
    assert (
        "| Variant | Size | Perplexity (wikitext-2) | tok/s on Spark"
        " | FinanceBench (n=50, numeric_match) |"
    ) in out
    # Each row carries the percentage-formatted accuracy
    assert "| Q4_K_M | 4.6 GB | 8.400 | 72.3 | 62.0% |" in out
    assert "| Q8_0 | 8.5 GB | 8.100 | 45.1 | 66.0% |" in out
    # The intro copy switches to "measurement quad"
    assert "measurement quad" in out
    assert "FinanceBench (n=50, numeric_match)" in out


def test_model_card_skips_vertical_column_when_eval_empty() -> None:
    card = ModelCard(
        title="Foo-GGUF",
        one_liner="x",
        base_model="x/y",
        variants=({"name": "Q4_K_M", "size": "4 GB", "recommended": "x"},),
        perplexity={"Q4_K_M": 7.0},
        tokens_per_sec={"Q4_K_M": 60.0},
        sustained_load_minutes=10.0,
        # vertical_eval intentionally omitted
    )
    out = card.render()
    # Falls back to 4-column header (no vertical column)
    assert "| Variant | Size | Perplexity (wikitext-2) | tok/s on Spark |" in out
    assert "measurement triple" in out


def test_model_card_skips_spark_tested_block_without_measurements() -> None:
    card = ModelCard(
        title="Foo-30B-GGUF",
        one_liner="Quants.",
        base_model="nvidia/Foo-30B",
    )
    out = card.render()
    assert "## Spark-tested" not in out


def test_model_card_renders_variants_table() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        variants=(
            {"name": "Q4_K_M", "size": "", "recommended": "Default pick."},
        ),
    )
    out = card.render()
    assert "## Variants" in out
    assert "| Q4_K_M | Default pick. |" in out


def test_model_card_renders_run_instructions() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        ollama_pull_handle="Orionfold/foo",
        transformers_snippet="from transformers import AutoModel\nmodel = AutoModel.from_pretrained('Orionfold/foo')",
    )
    out = card.render()
    assert "## How to run" in out
    assert "ollama pull Orionfold/foo" in out
    assert "from transformers import AutoModel" in out


def test_model_card_renders_default_gguf_run_snippets_when_hf_repo_set() -> None:
    """Card with no explicit ollama/transformers handle should still get a real
    ## How to run body — llama-server + llama-cpp-python templated from hf_repo.

    Regression test for the v0.4.x dry-run bug on `Orionfold/finance-chat-GGUF`
    where `## How to run` rendered as a header with no body."""
    card = ModelCard(
        title="finance-chat-GGUF",
        one_liner="x",
        base_model="AdaptLLM/finance-chat",
        quant_format="gguf",
        hf_repo="Orionfold/finance-chat-GGUF",
        chat_format="llama-2",
        variants=(
            {"name": "Q4_K_M", "size": "3.8 GB", "recommended": "Default."},
            {"name": "Q5_K_M", "size": "4.5 GB", "recommended": "Balanced."},
        ),
    )
    out = card.render()
    assert "## How to run" in out
    # huggingface-cli pull line uses the repo + a featured variant
    assert "huggingface-cli download Orionfold/finance-chat-GGUF model-Q5_K_M.gguf" in out
    assert "--local-dir ./models/finance-chat" in out
    # llama-server snippet
    assert "llama-server -m ./models/finance-chat/model-Q5_K_M.gguf" in out
    # llama-cpp-python snippet with chat_format threaded through
    assert "from llama_cpp import Llama" in out
    assert 'chat_format="llama-2"' in out


def test_model_card_default_run_snippet_picks_first_variant_without_q5_k_m() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        quant_format="gguf",
        hf_repo="Orionfold/Foo-GGUF",
        variants=(
            {"name": "Q4_K_M", "size": "3 GB", "recommended": "x"},
            {"name": "Q8_0", "size": "7 GB", "recommended": "x"},
        ),
    )
    out = card.render()
    # Falls back to first listed variant when Q5_K_M is absent
    assert "model-Q4_K_M.gguf" in out


def test_model_card_recommended_variant_override_respected() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        quant_format="gguf",
        hf_repo="Orionfold/Foo-GGUF",
        recommended_variant="Q8_0",
        variants=(
            {"name": "Q4_K_M", "size": "3 GB", "recommended": "x"},
            {"name": "Q5_K_M", "size": "4 GB", "recommended": "x"},
            {"name": "Q8_0", "size": "7 GB", "recommended": "x"},
        ),
    )
    out = card.render()
    assert "model-Q8_0.gguf" in out
    # Should NOT default to Q5_K_M when override is set
    assert "model-Q5_K_M.gguf" not in out


def test_model_card_skips_how_to_run_section_entirely_when_nothing_to_render() -> None:
    """No ollama_pull_handle, no transformers_snippet, no hf_repo → no section."""
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        # Note: no hf_repo, no ollama_pull_handle, no transformers_snippet
    )
    out = card.render()
    assert "## How to run" not in out


def test_model_card_license_overridable_for_non_apache_models() -> None:
    """HF frontmatter `license:` must reflect the upstream model's actual
    license, not the apache-2.0 default. Regression for the finance-chat
    `license: apache-2.0` bug (model is actually Llama-2 Community License)."""
    card = ModelCard(
        title="finance-chat-GGUF",
        one_liner="x",
        base_model="AdaptLLM/finance-chat",
        license="llama2",
    )
    out = card.render()
    head, _, _ = out.partition("---\n\n")
    assert "license: llama2" in head
    assert "license: apache-2.0" not in head


def test_model_card_renders_lineage_when_provided() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        lineage_prompt="## LEADERBOARD.md\n- baseline: ppl=7.5",
    )
    out = card.render()
    assert "## Lineage" in out
    assert "## LEADERBOARD.md" in out


def test_model_card_renders_methods_link_when_article_provided() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        article_slug="becoming-a-gguf-publisher-on-spark",
        article_title="Becoming a GGUF publisher on the Spark",
    )
    out = card.render()
    assert (
        "[Becoming a GGUF publisher on the Spark]"
        "(https://ainative.business/field-notes/becoming-a-gguf-publisher-on-spark/)"
        in out
    )


def test_model_card_footer_always_includes_orionfold_attribution() -> None:
    card = ModelCard(title="x", one_liner="y", base_model="z")
    out = card.render()
    assert "Published by **Orionfold LLC**" in out
    assert "[orionfold.com](https://orionfold.com)" in out


def test_model_card_frontmatter_carries_tags() -> None:
    card = ModelCard(
        title="x",
        one_liner="y",
        base_model="z",
        tags=("gguf", "spark-tested", "orionfold"),
    )
    out = card.render()
    head, _, _ = out.partition("---\n\n")
    assert "- gguf" in head
    assert "- spark-tested" in head
    assert "- orionfold" in head


# ---------------- _render_yaml_scalar -------------------------------------


def test_render_yaml_scalar_handles_primitives() -> None:
    assert _render_yaml_scalar(True) == "true"
    assert _render_yaml_scalar(False) == "false"
    assert _render_yaml_scalar(None) == "null"
    assert _render_yaml_scalar(7) == "7"
    assert _render_yaml_scalar(7.5) == "7.5"


def test_render_yaml_scalar_quotes_special_chars() -> None:
    assert _render_yaml_scalar("hello") == "hello"
    assert _render_yaml_scalar("with: colon").startswith('"')
    assert _render_yaml_scalar("") == '""'
    assert _render_yaml_scalar("- leading-dash").startswith('"')


# ---------------- ArtifactManifest ----------------------------------------


def test_artifact_manifest_dict_renames_class_field() -> None:
    m = ArtifactManifest(
        slug="foo-30b-gguf",
        kind="quant",
        artifact_class="gguf",
        base_model="nvidia/Foo-30B",
        hf_repo="Orionfold/Foo-30B-GGUF",
        variants=("Q4_K_M", "Q8_0"),
    )
    d = m.to_dict()
    assert d["class"] == "gguf"
    assert "artifact_class" not in d
    assert d["slug"] == "foo-30b-gguf"
    assert d["variants"] == ["Q4_K_M", "Q8_0"]


def test_artifact_manifest_elides_optional_fields_when_unset() -> None:
    m = ArtifactManifest(
        slug="s",
        kind="quant",
        artifact_class="gguf",
        base_model="b",
        hf_repo="Orionfold/x",
    )
    d = m.to_dict()
    assert "civitai_id" not in d
    assert "download_count" not in d
    assert "perplexity" not in d
    assert "spark_tokens_per_sec" not in d
    assert "sustained_load_minutes" not in d
    assert "vertical_eval" not in d
    assert "vertical_eval_name" not in d


def test_artifact_manifest_includes_optional_fields_when_set() -> None:
    m = ArtifactManifest(
        slug="s",
        kind="quant",
        artifact_class="gguf",
        base_model="b",
        hf_repo="Orionfold/x",
        perplexity={"Q4_K_M": 7.0},
        spark_tokens_per_sec={"Q4_K_M": 24.0},
        sustained_load_minutes=40.0,
        civitai_id=1234,
        download_count=99,
        license_commercial_tier="orionfold-pro",
    )
    d = m.to_dict()
    assert d["perplexity"] == {"Q4_K_M": 7.0}
    assert d["spark_tokens_per_sec"] == {"Q4_K_M": 24.0}
    assert d["sustained_load_minutes"] == 40.0
    assert d["civitai_id"] == 1234
    assert d["download_count"] == 99
    assert d["license"] == {"tier": "free", "commercial_tier": "orionfold-pro"}


def test_artifact_manifest_emits_model_license_under_license_block() -> None:
    """`model_license` lives alongside `tier` in the manifest's `license:` block."""
    m = ArtifactManifest(
        slug="finance",
        kind="quant",
        artifact_class="gguf",
        base_model="AdaptLLM/finance-chat",
        hf_repo="Orionfold/finance-chat-GGUF",
        model_license="llama2",
    )
    d = m.to_dict()
    assert d["license"] == {"tier": "free", "model": "llama2"}
    yaml_text = m.to_yaml()
    assert "  model: llama2" in yaml_text


def test_artifact_manifest_omits_model_license_when_unset() -> None:
    m = ArtifactManifest(
        slug="s", kind="quant", artifact_class="gguf",
        base_model="b", hf_repo="Orionfold/x",
    )
    d = m.to_dict()
    assert d["license"] == {"tier": "free"}
    assert "model" not in d["license"]


def test_artifact_manifest_carries_vertical_eval_when_set() -> None:
    m = ArtifactManifest(
        slug="finance",
        kind="quant",
        artifact_class="gguf",
        base_model="instruction-pretrain/finance-Llama3-8B",
        hf_repo="Orionfold/finance-Llama3-8B-GGUF",
        variants=("Q4_K_M", "Q8_0"),
        vertical_eval={"Q4_K_M": 0.62, "Q8_0": 0.66},
        vertical_eval_name="FinanceBench (n=50, numeric_match)",
    )
    d = m.to_dict()
    assert d["vertical_eval"] == {"Q4_K_M": 0.62, "Q8_0": 0.66}
    assert d["vertical_eval_name"] == "FinanceBench (n=50, numeric_match)"
    # And the YAML output carries them too
    yaml_text = m.to_yaml()
    assert "vertical_eval:" in yaml_text
    assert "vertical_eval_name:" in yaml_text


def test_artifact_manifest_carries_recommended_variant_when_set() -> None:
    m = ArtifactManifest(
        slug="securityllm-gguf",
        kind="quant",
        artifact_class="gguf",
        base_model="ZySec-AI/SecurityLLM",
        hf_repo="Orionfold/SecurityLLM-GGUF",
        variants=("Q4_K_M", "Q5_K_M"),
        recommended_variant="Q4_K_M",
    )
    d = m.to_dict()
    assert d["recommended_variant"] == "Q4_K_M"
    yaml_text = m.to_yaml()
    assert "recommended_variant: Q4_K_M" in yaml_text


def test_artifact_manifest_omits_recommended_variant_when_unset() -> None:
    m = ArtifactManifest(
        slug="s", kind="quant", artifact_class="gguf",
        base_model="b", hf_repo="Orionfold/x",
    )
    d = m.to_dict()
    assert "recommended_variant" not in d
    assert "recommended_variant" not in m.to_yaml()


def test_artifact_manifest_yaml_is_parseable_round_trip() -> None:
    yaml_text = ArtifactManifest(
        slug="s",
        kind="quant",
        artifact_class="gguf",
        base_model="nvidia/Foo-30B",
        hf_repo="Orionfold/Foo-GGUF",
        variants=("Q4_K_M",),
        perplexity={"Q4_K_M": 7.0},
    ).to_yaml()
    # We do not depend on pyyaml; just check key lines are present.
    assert "slug: s" in yaml_text
    assert "kind: quant" in yaml_text
    assert "class: gguf" in yaml_text
    assert "hf_repo: Orionfold/Foo-GGUF" in yaml_text
    assert "- Q4_K_M" in yaml_text
    assert "  Q4_K_M: 7.0" in yaml_text  # nested under perplexity


def test_write_artifact_manifest_creates_dir_and_writes_file(tmp_path: Path) -> None:
    m = ArtifactManifest(
        slug="foo-gguf",
        kind="quant",
        artifact_class="gguf",
        base_model="nvidia/Foo",
        hf_repo="Orionfold/Foo-GGUF",
    )
    out = write_artifact_manifest(m, artifacts_dir=tmp_path / "src" / "content" / "artifacts")
    assert out.exists()
    assert out.name == "foo-gguf.yaml"
    assert out.parent.is_dir()


# ---------------- HFHubAdapter --------------------------------------------


def test_hf_adapter_repo_id_qualifies_bare_names(tmp_path: Path) -> None:
    a = HFHubAdapter(staging_dir=tmp_path)
    assert a.repo_id("Foo-GGUF") == "Orionfold/Foo-GGUF"
    assert a.repo_id("custom-org/Foo-GGUF") == "custom-org/Foo-GGUF"


def test_hf_adapter_stage_text_and_stage_file(tmp_path: Path) -> None:
    a = HFHubAdapter(staging_dir=tmp_path / "stage")
    p1 = a.stage_text("hello world", "README.md")
    assert p1.read_text() == "hello world"
    src = tmp_path / "src.bin"
    src.write_bytes(b"\x00\x01\x02")
    p2 = a.stage_file(src, "subdir/dest.bin")
    assert p2.read_bytes() == b"\x00\x01\x02"


def test_hf_adapter_push_folder_dry_run_logs_call(tmp_path: Path) -> None:
    a = HFHubAdapter(staging_dir=tmp_path / "stage", dry_run=True)
    a.stage_text("# card", "README.md")
    a.stage_text("x", "subdir/file.gguf")
    result = a.push_folder(repo_name="Foo-GGUF")
    assert result.dry_run is True
    assert result.hf_repo == "Orionfold/Foo-GGUF"
    assert "README.md" in result.files_uploaded
    assert "subdir/file.gguf" in result.files_uploaded
    assert len(a.logged_calls) == 1
    call = a.logged_calls[0]
    assert call["method"] == "upload_folder"
    assert call["repo_id"] == "Orionfold/Foo-GGUF"
    assert call["private"] is False


def test_hf_adapter_resolves_token_explicit_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "from-env")
    a = HFHubAdapter(staging_dir=tmp_path, token="explicit")
    assert a._resolve_token() == "explicit"


def test_hf_adapter_resolves_token_falls_back_to_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "from-env")
    a = HFHubAdapter(staging_dir=tmp_path)
    assert a._resolve_token() == "from-env"


def test_hf_adapter_resolves_token_returns_none_without_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    a = HFHubAdapter(staging_dir=tmp_path)
    assert a._resolve_token() is None


def test_hf_adapter_live_push_without_dep_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = HFHubAdapter(staging_dir=tmp_path / "stage", dry_run=False)
    a.stage_text("x", "README.md")
    # Force the lazy import to fail by hiding huggingface_hub from sys.modules
    import sys
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    with pytest.raises(HFHubNotAvailable):
        a.push_folder(repo_name="Foo")


# ---------------- publish_quant -------------------------------------------


def _stub_quant_report(tmp_path: Path) -> SimpleNamespace:
    # Create stub variant files so stage_file copies something real
    tmp_path.mkdir(parents=True, exist_ok=True)
    f4 = tmp_path / "model-Q4_K_M.gguf"
    f8 = tmp_path / "model-Q8_0.gguf"
    f4.write_bytes(b"q4")
    f8.write_bytes(b"q8")
    return SimpleNamespace(
        format="gguf",
        variants=("Q4_K_M", "Q8_0"),
        variant_files={
            "Q4_K_M": {"path": str(f4), "rel": "model-Q4_K_M.gguf", "size": "18 GB"},
            "Q8_0": {"path": str(f8), "rel": "model-Q8_0.gguf", "size": "31 GB"},
        },
        perplexity={"Q4_K_M": 7.1, "Q8_0": 6.9},
        tokens_per_sec={"Q4_K_M": 24.0, "Q8_0": 12.0},
        sustained_load_minutes=42.0,
    )


def test_publish_quant_dry_run_end_to_end(tmp_path: Path) -> None:
    qr = _stub_quant_report(tmp_path / "source")
    result = publish_quant(
        quant_report=qr,
        base_model="nvidia/Foo-30B",
        repo_name="Foo-30B-GGUF",
        staging_dir=tmp_path / "stage",
        artifacts_dir=tmp_path / "content" / "artifacts",
        article_slug="becoming-a-gguf-publisher-on-spark",
        article_title="Becoming a GGUF publisher on the Spark",
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.hf_repo == "Orionfold/Foo-30B-GGUF"
    assert result.card_path is not None
    assert result.card_path.exists()
    assert result.manifest_path is not None
    assert result.manifest_path.exists()
    # Card contains the expected blocks
    card = result.card_path.read_text()
    assert "## Spark-tested" in card
    assert "Q4_K_M" in card and "Q8_0" in card
    assert "becoming-a-gguf-publisher-on-spark" in card
    assert "Orionfold LLC" in card
    # Manifest contains the right slug/hf_repo
    manifest = result.manifest_path.read_text()
    assert "slug: foo-30b-gguf" in manifest
    assert "hf_repo: Orionfold/Foo-30B-GGUF" in manifest


def test_publish_quant_threads_vertical_eval_into_card_and_manifest(
    tmp_path: Path,
) -> None:
    qr = _stub_quant_report(tmp_path / "source")
    result = publish_quant(
        quant_report=qr,
        base_model="instruction-pretrain/finance-Llama3-8B",
        repo_name="finance-Llama3-8B-GGUF",
        staging_dir=tmp_path / "stage",
        artifacts_dir=tmp_path / "content" / "artifacts",
        article_slug="becoming-a-gguf-publisher-on-spark",
        vertical_eval={"Q4_K_M": 0.62, "Q8_0": 0.66},
        vertical_eval_name="FinanceBench (n=50, numeric_match)",
        dry_run=True,
    )
    card = result.card_path.read_text()
    # Card surfaces the 5th column with percentage formatting
    assert "FinanceBench (n=50, numeric_match)" in card
    assert "62.0%" in card and "66.0%" in card
    assert "measurement quad" in card
    # Manifest YAML carries vertical_eval fields
    manifest = result.manifest_path.read_text()
    assert "vertical_eval:" in manifest
    assert "vertical_eval_name:" in manifest


def test_publish_quant_reads_vertical_eval_from_quant_report_duck_typed(
    tmp_path: Path,
) -> None:
    # When kwargs are not supplied, the duck-typed report's vertical_eval
    # attributes flow through automatically.
    qr = _stub_quant_report(tmp_path / "source")
    qr.vertical_eval = {"Q4_K_M": 0.55, "Q8_0": 0.60}
    qr.vertical_eval_name = "LegalBench (mini)"
    result = publish_quant(
        quant_report=qr,
        base_model="x/y",
        repo_name="y-GGUF",
        staging_dir=tmp_path / "stage",
        dry_run=True,
    )
    card = result.card_path.read_text()
    assert "LegalBench (mini)" in card
    assert "55.0%" in card and "60.0%" in card


def test_publish_quant_threads_recommended_variant_into_card_and_manifest(
    tmp_path: Path,
) -> None:
    """`recommended_variant` kwarg flows to the README's How-to-run snippets
    AND to the manifest YAML so the destination catalog pins the same pick."""
    qr = _stub_quant_report(tmp_path / "source")
    result = publish_quant(
        quant_report=qr,
        base_model="ZySec-AI/SecurityLLM",
        repo_name="SecurityLLM-GGUF",
        staging_dir=tmp_path / "stage",
        artifacts_dir=tmp_path / "content" / "artifacts",
        recommended_variant="Q4_K_M",
        dry_run=True,
    )
    card = result.card_path.read_text()
    # The default How-to-run snippet templates against the recommended variant
    assert "Q4_K_M" in card
    # Manifest YAML carries the recommended_variant field
    manifest = result.manifest_path.read_text()
    assert "recommended_variant: Q4_K_M" in manifest


def test_publish_quant_threads_model_license_into_card_and_manifest(
    tmp_path: Path,
) -> None:
    """`model_license` kwarg flows to README frontmatter AND to manifest YAML."""
    qr = _stub_quant_report(tmp_path / "source")
    result = publish_quant(
        quant_report=qr,
        base_model="AdaptLLM/finance-chat",
        repo_name="finance-chat-GGUF",
        staging_dir=tmp_path / "stage",
        artifacts_dir=tmp_path / "content" / "artifacts",
        model_license="llama2",
        dry_run=True,
    )
    card = result.card_path.read_text()
    head, _, _ = card.partition("---\n\n")
    assert "license: llama2" in head
    assert "license: apache-2.0" not in head
    manifest = result.manifest_path.read_text()
    assert "  model: llama2" in manifest


def test_publish_quant_default_license_is_apache_2_0_when_unspecified(
    tmp_path: Path,
) -> None:
    qr = _stub_quant_report(tmp_path / "source")
    result = publish_quant(
        quant_report=qr,
        base_model="x/y",
        repo_name="y-GGUF",
        staging_dir=tmp_path / "stage",
        dry_run=True,
    )
    card = result.card_path.read_text()
    head, _, _ = card.partition("---\n\n")
    assert "license: apache-2.0" in head


def test_publish_quant_renders_default_how_to_run_with_hf_repo(
    tmp_path: Path,
) -> None:
    """publish_quant fills in hf_repo on the card so the default ## How to run
    body templates against it — no caller plumbing required."""
    qr = _stub_quant_report(tmp_path / "source")
    result = publish_quant(
        quant_report=qr,
        base_model="AdaptLLM/finance-chat",
        repo_name="finance-chat-GGUF",
        staging_dir=tmp_path / "stage",
        chat_format="llama-2",
        dry_run=True,
    )
    card = result.card_path.read_text()
    assert "## How to run" in card
    assert "huggingface-cli download Orionfold/finance-chat-GGUF" in card
    assert "llama-server -m" in card
    assert 'chat_format="llama-2"' in card


def test_publish_quant_reads_model_license_from_quant_report_duck_typed(
    tmp_path: Path,
) -> None:
    qr = _stub_quant_report(tmp_path / "source")
    qr.model_license = "cc-by-nc-4.0"
    result = publish_quant(
        quant_report=qr,
        base_model="x/y",
        repo_name="y-GGUF",
        staging_dir=tmp_path / "stage",
        dry_run=True,
    )
    card = result.card_path.read_text()
    head, _, _ = card.partition("---\n\n")
    assert "license:" in head
    # cc-by-nc-4.0 contains hyphens; YAML emitter should leave bare scalar
    assert "license: cc-by-nc-4.0" in head


def test_publish_quant_lineage_store_duck_typed(tmp_path: Path) -> None:
    qr = _stub_quant_report(tmp_path / "source")

    class _Snapshot:
        rendered_markdown = "## LEADERBOARD.md\n- best: ppl=7.0"

    class _Store:
        def render_prompt(self) -> _Snapshot:  # noqa: D401
            return _Snapshot()

    result = publish_quant(
        quant_report=qr,
        base_model="nvidia/Foo-30B",
        repo_name="Foo-30B-GGUF",
        staging_dir=tmp_path / "stage",
        lineage_store=_Store(),
        dry_run=True,
    )
    card = result.card_path.read_text()
    assert "## Lineage" in card
    assert "## LEADERBOARD.md" in card


def test_publish_quant_handles_missing_lineage_gracefully(tmp_path: Path) -> None:
    qr = _stub_quant_report(tmp_path / "source")

    class _BadStore:
        def render_prompt(self) -> Any:  # type: ignore[name-defined]
            raise RuntimeError("boom")

    result = publish_quant(
        quant_report=qr,
        base_model="nvidia/Foo-30B",
        repo_name="Foo-30B-GGUF",
        staging_dir=tmp_path / "stage",
        lineage_store=_BadStore(),
        dry_run=True,
    )
    card = result.card_path.read_text()
    assert "## Lineage" not in card  # silent fallback


def test_publish_quant_without_artifacts_dir_skips_manifest(tmp_path: Path) -> None:
    qr = _stub_quant_report(tmp_path / "source")
    result = publish_quant(
        quant_report=qr,
        base_model="nvidia/Foo-30B",
        repo_name="Foo-30B-GGUF",
        staging_dir=tmp_path / "stage",
        dry_run=True,
    )
    assert result.manifest_path is None
    assert result.card_path is not None


# ---------------- variant recommendation table ----------------------------


def test_default_variant_recommendation_table_covers_canonical_set() -> None:
    for v in ("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16", "AWQ-int4", "GPTQ-int4", "EXL3", "MLX-4bit", "NVFP4"):
        assert _default_variant_recommendation(v) != "Variant-specific use case TBD."


def test_default_variant_recommendation_unknown_returns_placeholder() -> None:
    assert _default_variant_recommendation("Q3_K_S") == "Variant-specific use case TBD."


# ---------------- error classes ------------------------------------------


def test_error_class_hierarchy() -> None:
    assert issubclass(HFHubNotAvailable, PublishError)
    assert issubclass(HFAuthError, PublishError)
    assert issubclass(HFHubNotAvailable, ImportError)
