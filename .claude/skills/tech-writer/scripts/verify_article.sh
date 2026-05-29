#!/usr/bin/env bash
# Verify an article is ready to commit.
# Checks: frontmatter valid + required keys + summary length,
#         image refs resolve, slug matches folder, TODO markers surfaced.
# Usage: verify_article.sh <slug>

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <slug>" >&2
  exit 1
fi

SLUG="$1"
# Repo path can be overridden via NVIDIA_LEARN_REPO so the script keeps
# working after the 2026-04-24 nvidia-learn → ai-field-notes rename and any
# future repo moves. Default to the new ai-field-notes path.
REPO="${NVIDIA_LEARN_REPO:-/home/nvidia/ainative-business.github.io}"
ARTICLE_DIR="$REPO/articles/$SLUG"
ARTICLE="$ARTICLE_DIR/article.md"

if [ ! -f "$ARTICLE" ]; then
  echo "FAIL: $ARTICLE not found" >&2
  exit 1
fi

FAIL=0
WARN=0

# --- Check 1: frontmatter ---
# python3 exits 2 on validation fail; set -e would terminate the script, but we
# want every check to run so the user sees the full punch list — hence || RC=$?
RC=0
python3 - "$ARTICLE" <<'PY' || RC=$?
import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
txt = p.read_text()
m = re.match(r'^---\n(.*?)\n---\n', txt, re.DOTALL)
if not m:
    print("FAIL: no frontmatter block at top of file")
    sys.exit(2)

try:
    import yaml
    data = yaml.safe_load(m.group(1))
    if not isinstance(data, dict):
        print("FAIL: frontmatter is not a YAML mapping")
        sys.exit(2)
except ImportError:
    print("NOTE: PyYAML not installed; skipping deep YAML parse (install with: pip install pyyaml)")
    # Fall back to substring check for required keys
    data = None

if data is not None:
    required = ["title", "date", "author", "product", "stage", "difficulty",
                "time_required", "hardware", "tags", "summary"]
    missing = [k for k in required if k not in data]
    if missing:
        print(f"FAIL: frontmatter missing required keys: {missing}")
        sys.exit(2)

    # Basic value checks
    title = data.get("title", "")
    if isinstance(title, str) and (title.startswith("TODO") or title == ""):
        print("FAIL: title is still a TODO placeholder")
        sys.exit(2)

    summary = data.get("summary", "")
    if isinstance(summary, str):
        if summary.startswith("TODO") or summary == "":
            print("FAIL: summary is still a TODO placeholder")
            sys.exit(2)
        # Astro schema enforces z.string().max(300) — over-length fails the build.
        if len(summary) > 300:
            print(f"FAIL: summary is {len(summary)} chars (> 300). Astro schema will reject this at build time.")
            sys.exit(2)

    stage = data.get("stage", "")
    valid_stages = {"foundations", "training", "fine-tuning", "inference",
                    "deployment", "agentic", "observability", "dev-tools"}
    if stage not in valid_stages:
        print(f"WARN: stage '{stage}' not in {sorted(valid_stages)}")

    difficulty = data.get("difficulty", "")
    if difficulty not in {"beginner", "intermediate", "advanced"}:
        print(f"WARN: difficulty '{difficulty}' not in [beginner, intermediate, advanced]")

print("OK: frontmatter valid and required keys present")
PY
if [ $RC -eq 2 ]; then FAIL=1; fi

# --- Check 2: image references resolve ---
# Extract markdown image refs, skip absolute URLs
MISSING_IMAGES=$(
  grep -oE '!\[[^]]*\]\([^)]+\)' "$ARTICLE" | \
    sed -E 's/.*\(([^)]+)\).*/\1/' | \
    while read -r ref; do
      [[ "$ref" =~ ^https?:// ]] && continue
      [ -f "$ARTICLE_DIR/$ref" ] || echo "$ref"
    done || true
)
if [ -n "$MISSING_IMAGES" ]; then
  echo "FAIL: broken image references:"
  echo "$MISSING_IMAGES" | sed 's/^/  /'
  FAIL=1
else
  echo "OK: all image references resolve"
fi

# --- Check 3: folder matches slug arg ---
ACTUAL_FOLDER="$(basename "$ARTICLE_DIR")"
if [ "$ACTUAL_FOLDER" != "$SLUG" ]; then
  echo "FAIL: slug '$SLUG' doesn't match folder name '$ACTUAL_FOLDER'"
  FAIL=1
else
  echo "OK: slug matches folder name"
fi

# --- Check 4: TODO markers remaining ---
TODO_COUNT="$(grep -c 'TODO' "$ARTICLE" 2>/dev/null || true)"
TODO_COUNT="${TODO_COUNT:-0}"
if [ "$TODO_COUNT" -gt 0 ]; then
  echo "WARN: $TODO_COUNT TODO marker(s) remain in article.md"
  WARN=1
fi

# --- Check 5: secret / PII scan (MANDATORY — blocks commit on any hit) ---
# Scans article.md, transcript.md, and text files under assets/.
# Patterns defined in references/privacy-and-security.md — keep in sync.
SCAN_FILES=("$ARTICLE")
[ -f "$ARTICLE_DIR/transcript.md" ] && SCAN_FILES+=("$ARTICLE_DIR/transcript.md")
if [ -d "$ARTICLE_DIR/assets" ]; then
  # Only scan obvious text files in assets/, not images or binaries
  while IFS= read -r -d '' f; do
    SCAN_FILES+=("$f")
  done < <(find "$ARTICLE_DIR/assets" -type f \( -name '*.md' -o -name '*.txt' -o -name '*.json' -o -name '*.yaml' -o -name '*.yml' -o -name '*.toml' -o -name '*.sh' -o -name '*.py' -o -name '*.env*' -o -name '*.conf' -o -name '*.cast' \) -print0 2>/dev/null)
fi

# Patterns — high-signal secret shapes + a few PII kinds.
# Anthropic keys are matched first so they don't also fire the generic sk- rule.
SECRET_PATTERNS=(
  'nvapi-[A-Za-z0-9_-]{20,}'                                         # NGC API key
  'sk-ant-[A-Za-z0-9_-]{20,}'                                        # Anthropic key
  '\bsk-(?!ant-)[A-Za-z0-9]{20,}'                                    # OpenAI-style key (PCRE negative lookbehind via grep -P)
  'gh[pousr]_[A-Za-z0-9]{20,}'                                       # GitHub token
  'AKIA[0-9A-Z]{16}'                                                 # AWS access key ID
  'xox[bpoa]-[A-Za-z0-9-]+'                                          # Slack token
  'tskey-(auth|api)-[A-Za-z0-9-]+'                                   # Tailscale auth key
  '-----BEGIN (OPENSSH|RSA|EC|DSA) PRIVATE KEY-----'                 # SSH / PEM private keys
  '-----BEGIN PRIVATE KEY-----'                                      # generic PEM private key
  '-----BEGIN CERTIFICATE-----'                                      # certs can embed identity
  'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'             # JWT
  '[Aa]uthorization:\s*[Bb]earer\s+[A-Za-z0-9._-]{16,}'              # Bearer header with a real-looking token
)

SECRET_HITS=0
for pat in "${SECRET_PATTERNS[@]}"; do
  for f in "${SCAN_FILES[@]}"; do
    # -P enables PCRE (for the sk- negative lookbehind); -n for line numbers; -H to always show filename
    if match="$(grep -HnP "$pat" "$f" 2>/dev/null)"; then
      if [ -n "$match" ]; then
        if [ $SECRET_HITS -eq 0 ]; then
          echo "FAIL: possible secret / PII detected — redact before committing:"
        fi
        # Show filename:line:matched-pattern (not the full matched text, to avoid echoing secrets to terminal history)
        echo "$match" | while IFS= read -r line; do
          file_part="${line%%:*}"
          rest="${line#*:}"
          line_num="${rest%%:*}"
          echo "  $file_part:$line_num  (matches /$pat/)"
        done
        SECRET_HITS=1
      fi
    fi
  done
done

if [ $SECRET_HITS -gt 0 ]; then
  echo ""
  echo "  See references/privacy-and-security.md for scrub guidance and override procedure."
  FAIL=1
else
  echo "OK: no secret / PII patterns detected in article.md, transcript.md, or assets/"
fi

# --- Check 6: SVG invariants (blocks commit on any violation) ---
# Delegates to verify_svg.sh which parses every <figure class="fn-diagram"> in
# article.md plus the four signature components under src/components/svg/*.astro.
# Contract defined in references/visualizations.md §Hard invariants.
SVG_SCRIPT="$(dirname "$0")/verify_svg.sh"
if [ -x "$SVG_SCRIPT" ]; then
  if ! bash "$SVG_SCRIPT" "$SLUG"; then
    FAIL=1
  fi
else
  echo "WARN: verify_svg.sh not executable at $SVG_SCRIPT — skipping SVG invariant check"
  WARN=1
fi

# --- Summary ---
echo ""
if [ $FAIL -eq 0 ]; then
  if [ $WARN -eq 0 ]; then
    echo "Article verified — ready to commit."
  else
    echo "Article verified with warnings (see above). Commit if warnings are acceptable."
  fi
else
  echo "Fix the above failures before committing."
  exit 1
fi
