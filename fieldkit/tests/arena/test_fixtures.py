# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""Demo-fixture recorder gates — sanitizer, host-path scrubber, overlay merge.

The fixture bundle ships on the PUBLIC web preview, so it inherits the
mirror's leak discipline: no host paths, no local ports/base URLs, no
``config_*`` host metadata. The new feature-pane stubs (jobs, standup,
sft-progress, reward-signal, …) carry paths in two sneaky places the plain
key-dropper misses — *string values* (``model``) and *strings inside
strings* (``result_json`` embedded JSON, ``lineage_card`` markdown) — which
is exactly what ``_scrub_str`` exists for.
"""

from __future__ import annotations

import json
import re

import pytest

from fieldkit.arena.fixtures import (
    FIXTURE_SCHEMA_VERSION,
    _FORBIDDEN_STUB_KEYS,
    _STUB_ENDPOINTS,
    _apply_overlay,
    _sanitize,
    _scrub_str,
)

# The serialized fixture must never contain any of these (same regex family
# the deploy verifier greps for).
LEAK_RE = re.compile(r"/home/|/Users/|\.hermes/|:7866|:8080|config_mtime|config_path")


# --------------------------------------------------------------------------- #
# _scrub_str
# --------------------------------------------------------------------------- #

def test_scrub_str_reduces_host_path_to_basename():
    s = "/home/nvidia/data/astro-train-lora/p65-nemo/merged-hf-bf16-fixed"
    assert _scrub_str(s) == "merged-hf-bf16-fixed"


def test_scrub_str_handles_embedded_json_strings():
    # jobs/standup carry result_json as a STRING containing paths.
    result_json = json.dumps(
        {
            "base": "/home/nvidia/data/astro-train-lora/p65-nemo/merged-hf-bf16-fixed",
            "kind": "rl_run",
            "heldout_scores": {"0": 0.958333},
        }
    )
    out = _scrub_str(result_json)
    assert "/home/" not in out
    assert "merged-hf-bf16-fixed" in out
    assert "rl_run" in out  # non-path content untouched


def test_scrub_str_handles_markdown_blobs():
    card = "# Session start\nbase: /home/nvidia/data/x/y/model-dir\nbest: 0.958"
    out = _scrub_str(card)
    assert "/home/" not in out
    assert "model-dir" in out
    assert "best: 0.958" in out


def test_scrub_str_leaves_plain_text_alone():
    s = "Kepler's third law gives T = 97.0 minutes (a = 7000 km)."
    assert _scrub_str(s) == s


# --------------------------------------------------------------------------- #
# _sanitize
# --------------------------------------------------------------------------- #

def test_sanitize_drops_forbidden_keys_recursively():
    payload = {
        "active": {
            "id": "resident-brain",
            "base_url": "http://127.0.0.1:8080/v1",
            "port": 8080,
            "config_path": "/home/nvidia/.hermes/config.yaml",
            "config_mtime": 1779938812.07,
            "hermes_hint": {
                "base_url": "http://127.0.0.1:8080/v1",
                "model": "Qwen3-30B-A3B-Q4_K_M",
            },
        }
    }
    out = _sanitize(payload)
    flat = json.dumps(out)
    for key in ("base_url", "config_path", "config_mtime"):
        assert key not in flat
    assert '"port"' not in flat
    assert out["active"]["hermes_hint"]["model"] == "Qwen3-30B-A3B-Q4_K_M"


def test_sanitize_scrubs_string_values_everywhere():
    payload = {
        "jobs": [
            {
                "kind": "rl_run",
                "result_json": json.dumps(
                    {"base": "/home/nvidia/data/lora/merged-hf-bf16-fixed"}
                ),
                "model": "/home/nvidia/data/astro/merged-hf-bf16-fixed",
            }
        ]
    }
    flat = json.dumps(_sanitize(payload))
    assert "/home/" not in flat
    assert "merged-hf-bf16-fixed" in flat


def test_sanitized_feature_stub_passes_leak_gate():
    # A representative slice of the real /api/standup + /api/active-lane shapes.
    payload = {
        "generated_at": "2026-06-07T07:36:43Z",
        "ran": [
            {
                "id": "35ed71b905694958ac1cd4fc47604553",
                "kind": "rl_run",
                "result_json": '{"base": "/home/nvidia/data/astro-train-lora/x", '
                '"lineage_card": "# Session\\nbase /home/nvidia/data/y"}',
            }
        ],
        "active": {
            "base_url": "http://127.0.0.1:8080/v1",
            "port": 8080,
            "config_path": "/home/nvidia/.hermes/config.yaml",
            "config_mtime": 1.0,
            "model": "Qwen3-30B-A3B-Q4_K_M",
        },
    }
    flat = json.dumps(_sanitize(payload))
    assert not LEAK_RE.search(flat), LEAK_RE.search(flat)


# --------------------------------------------------------------------------- #
# Overlay merge
# --------------------------------------------------------------------------- #

def test_overlay_stubs_merge_per_endpoint():
    payload = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "stubs": {"/api/jobs": {"jobs": ["recorded"]}, "/healthz": {"ok": True}},
    }
    overlay = {"stubs": {"/api/jobs": {"jobs": ["showcase"]}}}
    _apply_overlay(payload, overlay)
    assert payload["stubs"]["/api/jobs"] == {"jobs": ["showcase"]}  # replaced
    assert payload["stubs"]["/healthz"] == {"ok": True}  # untouched


def test_overlay_top_level_keys_replace():
    payload = {"schema_version": FIXTURE_SCHEMA_VERSION, "stubs": {}}
    overlay = {"knowledge": {"before": {}, "after": {}, "queries": []}, "note": "simulated"}
    _apply_overlay(payload, overlay)
    assert payload["knowledge"] == overlay["knowledge"]
    assert payload["note"] == "simulated"
    assert payload["schema_version"] == FIXTURE_SCHEMA_VERSION


# --------------------------------------------------------------------------- #
# Contract pins
# --------------------------------------------------------------------------- #

def test_schema_version_unchanged():
    # boot.js tolerates additive stubs; a version bump would force a client
    # contract change for no benefit. Pin it.
    assert FIXTURE_SCHEMA_VERSION == 1


@pytest.mark.parametrize(
    "endpoint",
    [
        "api/build",
        "api/sft-progress",
        "api/reward-signal",
        "api/standup",
        "api/jobs",
        "api/leaderboard/live",
        "api/active-lane",
        "api/lane-recipes",
        "api/guardrail-config",
        "api/prices",
        "api/corpus-progress",
        "api/runtimes",
    ],
)
def test_feature_pane_endpoints_are_recorded(endpoint):
    assert endpoint in _STUB_ENDPOINTS


def test_forbidden_keys_cover_host_metadata():
    for key in ("base_url", "config_path", "config_mtime", "port", "db", "db_path"):
        assert key in _FORBIDDEN_STUB_KEYS
