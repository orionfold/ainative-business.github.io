---
title: "Field-Fixing the Hermes Harness on a DGX Spark — When the NIM Won't Stream Tool Calls, and Other Rough Edges"
date: 2026-05-29
author: Manav Sehgal
product: Foundation
stage: agentic
difficulty: intermediate
time_required: "planned ~2 hours"
hardware: "NVIDIA DGX Spark"
tags: [hermes, agentic, nim, tool-calling, streaming, vllm, nemotron, local-first, dgx-spark]
summary: "Fifth in the Harnesses series: the field fixes that take a fresh Hermes agent on a local NIM from 'mostly works' to 'just works.' Leads with the one that bit hardest — the Spark NIM ships a non-streaming tool parser, fixed by bind-mounting NVIDIA's own streaming parser."
status: upcoming
series: Harnesses
also_stages: [inference]
fieldkit_modules: [harness]
---

The Harnesses series already has, by [its keystone](/field-notes/hermes-drives-the-spark-via-fieldkit-mcp/), a Hermes agent that installs clean, serves from a [local lane](/field-notes/hermes-serving-lane-on-spark/), survives a [hostile-tool-call battery](/field-notes/hardening-the-hermes-harness-on-spark/), and drives a curated slice of `fieldkit` over MCP. What it does *not* have yet is an honest account of the rough edges between "installed" and "actually pleasant to drive" — the small, infuriating mismatches you only hit when you sit down and use the thing against a real NVIDIA NIM on the box.

This article collects them. The lead fix is the one that bit hardest: the DGX-Spark build of the Nemotron-Nano-9B-v2 NIM ships a *deliberately* non-streaming tool parser, so vLLM raises `NotImplementedError("Tool calling is not supported in streaming mode!")` the instant an agent sends `stream=true` alongside tools — which Hermes does on every first tool-bearing turn. Three blind alleys precede the real fix (the misleading `display.streaming` config, the top-level `streaming` block, a Hermes source path that hardcodes the streaming probe), and the real fix turns out to be a one-line bind-mount: NVIDIA publishes a fully-implemented streaming parser in the same model repo, registered under the same module name, so overlaying it onto the path the NIM already loads makes streaming tool calls just work — no edit to the NIM image, no patch to Hermes.

More fixes will land here as the harness gets desk time: the reasoning-model output-token trap that silently truncates `<think>` before the answer, the config keys whose names lie about what they gate, and whatever the next session surfaces. Think of it as the field-repair log for running an agent harness on a single Spark — the entries that are too sharp-edged to belong in any of the first four articles, but too useful to lose.
