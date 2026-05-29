#!/usr/bin/env bash
# Scaffold a product-launch article folder under products/<slug>/.
#
# Product articles are a distinct content type from the deep-dive essays the
# tech-writer skill produces — they live in their own collection so the
# destination site can render them with a launch layout (hero, build-metrics
# infographic, feature-tour gallery) instead of the article reading layout.
# See PRODUCT-ARTICLES.md at the repo root for the destination-repo contract.
set -euo pipefail

REPO="${REPO:-/home/nvidia/ainative-business.github.io}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

slug="${1:-}"
if [[ -z "$slug" ]]; then
  echo "usage: new_product_article.sh <slug>" >&2
  echo "  slug: kebab-case, lowercase, hyphens only (e.g. orionfold-arena)" >&2
  exit 2
fi
if [[ ! "$slug" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "error: slug must be kebab-case lowercase (got: $slug)" >&2
  exit 2
fi

dest="$REPO/products/$slug"
if [[ -e "$dest" ]]; then
  echo "error: $dest already exists — pick a different slug or polish in place" >&2
  exit 1
fi

mkdir -p "$dest/screenshots" "$dest/assets"
cp "$SKILL_DIR/assets/product-article-template.md" "$dest/product.md"
sed -i "s/__SLUG__/$slug/g" "$dest/product.md"

echo "Scaffolded $dest"
echo "  product.md      — fill from the template (frontmatter + sections)"
echo "  screenshots/    — NN-feature.png feature-tour captures"
echo "  assets/         — build-metrics.json, diagrams, snippets"
echo ""
echo "Next: mine metrics into assets/build-metrics.json, then write product.md."
