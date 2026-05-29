#!/usr/bin/env bash
# Initialize the articles/ tree in the ai-field-notes repo.
# Idempotent — safe to run multiple times.

set -euo pipefail

REPO="/home/nvidia/ainative-business.github.io"
ARTICLES="$REPO/articles"

if [ ! -d "$REPO" ]; then
  echo "ERROR: $REPO does not exist. Set up the repo first." >&2
  exit 1
fi

mkdir -p "$ARTICLES/_drafts"

if [ ! -f "$ARTICLES/README.md" ]; then
  cat > "$ARTICLES/README.md" <<'EOF'
# ai-field-notes — articles

A deep-dive notebook on **maximizing the NVIDIA DGX Spark as a personal AI power user and edge AI builder**.

Each article is an essay, not a tutorial. The uber theme threads through every piece: what does this one machine let one individual do in training, inference, and agentic workloads at the edge?

## Articles

<!--
  Articles get listed here, newest first within each stage.
  The `tech-writer` skill regenerates this section on request.
-->

_No articles yet — check back soon._

## Reading by stage

- **foundations** — setup, drivers, environment, mental models
- **inference** — serving models on-device (NIM, Triton, TensorRT-LLM)
- **fine-tuning** — adapting models locally (NeMo, LoRA, full-parameter)
- **training** — when and how the Spark trains or continues pre-training
- **agentic** — multi-agent orchestration on a single machine
- **deployment** — packaging, shipping, operating in the real world
- **observability** — measuring what's happening on your GPUs
- **dev-tools** — Nsight, CUDA tooling, editor integrations

---

_Built with [Claude Code](https://claude.com/claude-code) as a companion writer._
EOF
  echo "Created: $ARTICLES/README.md"
else
  echo "Exists:  $ARTICLES/README.md"
fi

if [ ! -f "$ARTICLES/_drafts/.gitkeep" ]; then
  touch "$ARTICLES/_drafts/.gitkeep"
  echo "Created: $ARTICLES/_drafts/.gitkeep"
fi

echo ""
echo "articles/ tree ready at: $ARTICLES"
ls -la "$ARTICLES"
