#!/usr/bin/env bash
# Scaffold a new article at articles/<slug>/.
# Usage: new_article.sh <slug>

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <slug>" >&2
  echo "Example: $0 nim-first-inference-dgx-spark" >&2
  exit 1
fi

SLUG="$1"

# Validate slug: kebab-case, lowercase, hyphens only
if ! [[ "$SLUG" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "ERROR: slug must be kebab-case (lowercase letters/digits, hyphens only). Got: $SLUG" >&2
  exit 1
fi

REPO="/home/nvidia/ainative-business.github.io"
ARTICLE_DIR="$REPO/articles/$SLUG"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/../assets/article-template.md"

if [ ! -d "$REPO/articles" ]; then
  echo "ERROR: $REPO/articles does not exist. Run init_blog.sh first." >&2
  exit 1
fi

if [ -d "$ARTICLE_DIR" ]; then
  echo "ERROR: $ARTICLE_DIR already exists. Pick a different slug or delete the existing folder." >&2
  exit 1
fi

if [ ! -f "$TEMPLATE" ]; then
  echo "ERROR: template missing at $TEMPLATE" >&2
  exit 1
fi

mkdir -p "$ARTICLE_DIR/screenshots" "$ARTICLE_DIR/assets"
cp "$TEMPLATE" "$ARTICLE_DIR/article.md"

# Fill in today's date
TODAY="$(date +%Y-%m-%d)"
sed -i "s/YYYY-MM-DD/$TODAY/" "$ARTICLE_DIR/article.md"

# Seed transcript.md with a stub header
cat > "$ARTICLE_DIR/transcript.md" <<EOF
# Source material: $SLUG

Cleaned session log and provenance for this article. Raw material that became evidence in article.md lives here.

_Populated on $TODAY._
EOF

echo "Scaffolded: $ARTICLE_DIR"
echo "  article.md         (template with TODOs — date filled to $TODAY)"
echo "  screenshots/"
echo "  transcript.md      (provenance stub)"
echo "  assets/"
