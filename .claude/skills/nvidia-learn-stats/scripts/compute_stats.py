#!/usr/bin/env python3
"""Compute project-level stats for nvidia-learn and write src/data/field-notes/project-stats.json.

Run from the repo root:
    python3 ~/.claude/skills/nvidia-learn-stats/scripts/compute_stats.py [--repo /path/to/nvidia-learn]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Detection lists — edit here when a new product or model enters the arc.
# ---------------------------------------------------------------------------

PRODUCTS = [
    # (canonical_id, display_label, list_of_case_insensitive_search_terms)
    ("nim",             "NVIDIA NIM",            [r"\bNIM\b", r"NIM microservice"]),
    ("nemo-retriever",  "NeMo Retriever",        [r"Nemo[ -]?Retriever", r"Nemotron[ -]?Retriever"]),
    ("nemo-guardrails", "NeMo Guardrails",       [r"Nemo[ -]?Guardrails"]),
    ("nemoclaw",        "NemoClaw",              [r"NemoClaw"]),
    ("openclaw",        "OpenClaw",              [r"OpenClaw"]),
    ("nemo",            "NeMo Framework",        [r"\bNeMo\b(?! Retriever| Guardrails| Framework)?", r"NeMo Framework"]),
    ("tensorrt-llm",    "TensorRT-LLM",          [r"TensorRT[ -]?LLM", r"TRT[ -]?LLM"]),
    ("triton",          "Triton Inference Server", [r"\bTriton\b"]),
    ("dgx-spark",       "DGX Spark",             [r"DGX[ -]Spark"]),
    ("pgvector",        "pgvector",              [r"\bpgvector\b"]),
    ("ollama",          "Ollama",                [r"\bOllama\b"]),
]

MODELS = [
    ("llama-3.1-8b-instruct",      "Llama 3.1 8B Instruct",    [r"Llama[ -]?3\.1[ -]?8B", r"llama-3\.1-8b"]),
    ("llama-3.3-70b-instruct",     "Llama 3.3 70B Instruct",   [r"Llama[ -]?3\.3[ -]?70B", r"llama-3\.3-70b"]),
    ("nemotron-super-49b",         "Nemotron Super 49B",       [r"Nemotron[ -]?Super[ -]?49B", r"nemotron-super-49b"]),
    ("nemotron-nano-9b",           "Nemotron Nano 9B v2",      [r"Nemotron[ -]?Nano[ -]?9B", r"nemotron-nano-9b"]),
    ("nemotron-embed-1b-v2",       "Nemotron Embed 1B v2",     [r"Nemotron[ -]?Embed[ -]?1B", r"nv-embed", r"nemotron-embed"]),
    ("nemotron-reranker-1b",       "Nemotron Reranker 1B",     [r"Nemotron[ -]?Rerank", r"nv-rerankqa", r"rerankqa-1b"]),
    # Non-NVIDIA bases that occasionally land in a LoRA / fine-tuning article —
    # include the size + "B" suffix so we don't catch unrelated Qwen mentions.
    ("qwen-2.5-3b-instruct",       "Qwen2.5 3B Instruct",      [r"Qwen\s?2\.5[ -]?3B", r"qwen2\.5-3b"]),
    ("qwen-2.5-7b-instruct",       "Qwen2.5 7B Instruct",      [r"Qwen\s?2\.5[ -]?7B", r"qwen2\.5-7b"]),
]

# Metric patterns. Each entry: (category, regex, normalizer).
# The regex captures the numeric + unit; we surround it with ±40 chars context for a label.
METRIC_PATTERNS = [
    ("latency",    re.compile(r"\b(\d+(?:\.\d+)?)\s?(ms|milliseconds)\b", re.I)),
    ("latency",    re.compile(r"\b(\d+(?:\.\d+)?)\s?(µs|microseconds)\b", re.I)),
    ("throughput", re.compile(r"\b(\d+(?:\.\d+)?)\s?(tok(?:ens)?/s|t/s|tokens per second)\b", re.I)),
    ("throughput", re.compile(r"\b(\d+(?:\.\d+)?)\s?(req(?:uests)?/s|qps)\b", re.I)),
    ("accuracy",   re.compile(r"(recall@\d+|precision@\d+|ndcg@\d+|mrr@\d+)\s*[:=]?\s*(\d+(?:\.\d+)?%?)", re.I)),
    ("accuracy",   re.compile(r"\b(\d+(?:\.\d+)?)\s?%\s*(recall|precision|accuracy|hit[- ]rate|f1)\b", re.I)),
]

# File extension → language bucket. Only "code" extensions contribute to LOC totals.
# Data formats (json, yaml, toml) are tracked in by_language for transparency but
# excluded from total_loc — benchmark/config dumps aren't code.
LANG_BUCKETS = {
    ".py":     "python",
    ".sh":     "shell",
    ".sql":    "sql",
    ".js":     "javascript",
    ".mjs":    "javascript",
    ".ts":     "typescript",
    ".tsx":    "typescript",
    ".astro":  "astro",
    ".css":    "css",
    ".html":   "html",
}
DATA_BUCKETS = {
    ".json":   "json",
    ".yaml":   "yaml",
    ".yml":    "yaml",
    ".toml":   "toml",
}

# Directories / files to skip when counting LOC under articles/*/evidence/ and fieldkit/.
# `_webui` is the baked Arena web bundle (gitignored build artifact written by
# `fieldkit arena build`, not source) — it lives under fieldkit/src/.../arena/_webui/
# and would otherwise add ~9k lines of generated HTML/JS/CSS to the fieldkit LOC.
SKIP_DIR_NAMES = {
    "node_modules", ".astro", "dist", ".git", "_webui",
    "__pycache__", ".venv", ".pytest_cache", ".ruff_cache",
}
# Substring marker for vendored third-party snapshots under evidence/.
# Frontier-Scout articles drop a full upstream repo at
# articles/<slug>/evidence/repo-snapshot/ for study; that code is not
# original to this project and must be excluded from the LOC headline.
VENDORED_MARKER = "/repo-snapshot/"
# Fieldkit subtrees that constitute "code written for this project".
# docs/ is prose (excluded by extension); dist/ is built artifacts (skipped above).
FIELDKIT_SUBDIRS = ("src", "tests", "samples", "scripts")


@dataclass
class ArticleInfo:
    slug: str
    title: str
    stage: str
    also_stages: list
    status: str
    product: str
    tags: list
    word_count: int
    path: Path


def parse_frontmatter(text: str) -> dict:
    """Parse a YAML-ish frontmatter block into a dict. Handles the subset used in this repo."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm_text = text[4:end]
    out = {}
    for line in fm_text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\w[\w-]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        # Strip surrounding quotes
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        # Parse YAML flow list
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            val = [v.strip().strip('"').strip("'") for v in inner.split(",") if v.strip()]
        out[key] = val
    return out


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4 :]
    return text


def strip_nonprose(text: str) -> str:
    """Remove code fences, HTML/SVG blocks, and markdown images. Used before word counting and metric extraction."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    # Drop entire SVG / figure / pre blocks (including their inner text, which often contains stray numbers).
    text = re.sub(r"<svg\b.*?</svg>",       " ", text, flags=re.S | re.I)
    text = re.sub(r"<figure\b.*?</figure>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<pre\b.*?</pre>",       " ", text, flags=re.S | re.I)
    # Then strip any remaining tags.
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)          # images
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)        # links → anchor text
    return text


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", strip_nonprose(text)))


def count_loc_in_file(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    # Count non-blank, non-pure-whitespace lines.
    return sum(1 for line in text.splitlines() if line.strip())


def walk_code(root: Path, exclude_substrings: tuple = ()) -> tuple[int, Counter, Counter, int]:
    """Return (code_loc, by_lang, data_by_lang, excluded_loc) under `root`.

    code_loc sums LANG_BUCKETS extensions; data_by_lang tracks DATA_BUCKETS separately;
    excluded_loc accumulates LANG_BUCKETS lines from paths matching any substring in
    `exclude_substrings` (so callers can report a vendored-share figure without a
    second walk).
    """
    by_lang = Counter()
    data_by_lang = Counter()
    code_total = 0
    excluded_total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        ext = path.suffix.lower()
        is_excluded = any(sub in str(path) for sub in exclude_substrings)
        if ext in LANG_BUCKETS:
            n = count_loc_in_file(path)
            if is_excluded:
                excluded_total += n
            else:
                by_lang[LANG_BUCKETS[ext]] += n
                code_total += n
        elif ext in DATA_BUCKETS and not is_excluded:
            n = count_loc_in_file(path)
            data_by_lang[DATA_BUCKETS[ext]] += n
    return code_total, by_lang, data_by_lang, excluded_total


def detect_hits(text: str, entries: list) -> set:
    """Return set of canonical IDs whose patterns match anywhere in `text`."""
    hits = set()
    for cid, _label, patterns in entries:
        for pat in patterns:
            if re.search(pat, text, re.I):
                hits.add(cid)
                break
    return hits


UNIT_SHORTHAND = [
    (re.compile(r"\bmilliseconds?\b", re.I),          "ms"),
    (re.compile(r"\bmicroseconds?\b", re.I),          "µs"),
    (re.compile(r"\btokens per second\b", re.I),      "tok/s"),
    (re.compile(r"\btokens?/second\b", re.I),         "tok/s"),
    (re.compile(r"\btokens?/s\b", re.I),              "tok/s"),
    (re.compile(r"\btok/s\b", re.I),                  "tok/s"),
    (re.compile(r"\brequests per second\b", re.I),    "req/s"),
    (re.compile(r"\brequests?/s\b", re.I),            "req/s"),
]


def shorten_units(value: str) -> str:
    """Collapse long unit spellings to their short forms (milliseconds → ms).
    Also tidies whitespace around the number so "80 ms" reads cleanly."""
    out = value
    for pat, repl in UNIT_SHORTHAND:
        out = pat.sub(repl, out)
    # Ensure a single space between the number and the unit.
    out = re.sub(r"(\d(?:\.\d+)?)\s*(ms|µs|tok/s|req/s|qps)\b", r"\1 \2", out)
    return out.strip()


def extract_metrics(text: str, slug: str, max_per_category: int = 4) -> dict:
    """Extract up to max_per_category representative metrics per category from article text."""
    found = defaultdict(list)
    for category, pat in METRIC_PATTERNS:
        for m in pat.finditer(text):
            start, end = m.span()
            # ±40 char context for a short label
            ctx_start = max(0, start - 60)
            ctx_end = min(len(text), end + 20)
            context = text[ctx_start:ctx_end].replace("\n", " ").strip()
            value = shorten_units(m.group(0).strip())
            # Short label: the sentence fragment before the number, up to ~6 words.
            prefix = text[max(0, start - 80) : start].replace("\n", " ")
            words = re.findall(r"\b[\w'-]+\b", prefix)[-5:]
            label = " ".join(words).lower() if words else "metric"
            found[category].append({"label": label, "value": value, "article_slug": slug})
    # Dedupe by (value, slug) and cap
    out = {}
    for cat, items in found.items():
        seen = set()
        dedup = []
        for it in items:
            key = (it["value"].lower(), it["label"])
            if key in seen:
                continue
            seen.add(key)
            dedup.append(it)
            if len(dedup) >= max_per_category:
                break
        out[cat] = dedup
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None, help="Path to nvidia-learn repo (defaults to CWD)")
    ap.add_argument("--out", default=None, help="Output JSON path (defaults to <repo>/src/data/field-notes/project-stats.json)")
    args = ap.parse_args()

    repo = Path(args.repo) if args.repo else Path.cwd()
    articles_dir = repo / "articles"
    src_dir = repo / "src"
    fieldkit_dir = repo / "fieldkit"
    out_path = Path(args.out) if args.out else src_dir / "data" / "field-notes" / "project-stats.json"

    if not articles_dir.is_dir() or not src_dir.is_dir():
        print(f"error: {repo} does not look like the ai-field-notes repo (missing articles/ or src/)", file=sys.stderr)
        sys.exit(1)

    # ---- articles ----
    all_articles: list[ArticleInfo] = []
    drafts = 0
    all_metrics = defaultdict(list)
    product_article_counts = Counter()
    model_article_counts = Counter()

    for article_md in sorted(articles_dir.glob("*/article.md")):
        slug = article_md.parent.name
        if slug.startswith("_"):
            continue
        raw = article_md.read_text(encoding="utf-8", errors="ignore")
        fm = parse_frontmatter(raw)
        body = strip_frontmatter(raw)
        words = count_words(body)
        status = fm.get("status", "published") or "published"
        also = fm.get("also_stages", []) if isinstance(fm.get("also_stages", []), list) else []
        tags = fm.get("tags", []) if isinstance(fm.get("tags", []), list) else []
        all_articles.append(
            ArticleInfo(
                slug=slug,
                title=fm.get("title", slug),
                stage=fm.get("stage", "foundations"),
                also_stages=also,
                status=status,
                product=fm.get("product", ""),
                tags=tags,
                word_count=words,
                path=article_md,
            )
        )
        # Upcoming articles are placeholders — exclude from word/product/model/metric
        # stats so the infographic reflects what's actually shipped.
        if status == "upcoming":
            continue
        haystack = body + " " + fm.get("product", "") + " " + " ".join(tags)
        for pid in detect_hits(haystack, PRODUCTS):
            product_article_counts[pid] += 1
        for mid in detect_hits(haystack, MODELS):
            model_article_counts[mid] += 1
        prose_body = strip_nonprose(body)
        for cat, items in extract_metrics(prose_body, slug).items():
            all_metrics[cat].extend(items)

    published = [a for a in all_articles if a.status == "published"]
    upcoming = [a for a in all_articles if a.status == "upcoming"]

    drafts_dir = articles_dir / "_drafts"
    if drafts_dir.is_dir():
        drafts = sum(1 for _ in drafts_dir.glob("*/article.md"))

    # ---- stages ----
    # Count by effective membership: primary stage + any also_stages entries.
    # So a foundations article with also_stages=[dev-tools] contributes to both.
    stages_published = Counter()
    stages_upcoming = Counter()
    for a in published:
        stages_published[a.stage] += 1
        for s in a.also_stages or []:
            stages_published[s] += 1
    for a in upcoming:
        stages_upcoming[a.stage] += 1
        for s in a.also_stages or []:
            stages_upcoming[s] += 1
    CANONICAL_STAGES = (
        "foundations", "training", "fine-tuning", "inference",
        "deployment", "agentic", "observability", "dev-tools",
    )
    for s in CANONICAL_STAGES:
        stages_published.setdefault(s, 0)
        stages_upcoming.setdefault(s, 0)

    # ---- code ----
    # Count "code written for this project" only:
    #   1. articles/*/evidence/  (excluding /repo-snapshot/ vendored upstream code)
    #   2. fieldkit/{src,tests,samples,scripts}/
    # The Astro site under src/ is infrastructure, not the deliverable, and is
    # not counted toward total_loc.
    evidence_total = 0
    evidence_by_lang = Counter()
    evidence_data_lang = Counter()
    vendored_total = 0
    for ev_dir in articles_dir.glob("*/evidence"):
        if not ev_dir.is_dir():
            continue
        n, by_lang, data_lang, excluded = walk_code(ev_dir, exclude_substrings=(VENDORED_MARKER,))
        evidence_total += n
        evidence_by_lang.update(by_lang)
        evidence_data_lang.update(data_lang)
        vendored_total += excluded

    fieldkit_total = 0
    fieldkit_by_lang = Counter()
    fieldkit_data_lang = Counter()
    if fieldkit_dir.is_dir():
        for sub in FIELDKIT_SUBDIRS:
            root = fieldkit_dir / sub
            if not root.is_dir():
                continue
            n, by_lang, data_lang, _ = walk_code(root)
            fieldkit_total += n
            fieldkit_by_lang.update(by_lang)
            fieldkit_data_lang.update(data_lang)

    by_language = Counter()
    by_language.update(evidence_by_lang)
    by_language.update(fieldkit_by_lang)
    data_by_lang = Counter()
    data_by_lang.update(evidence_data_lang)
    data_by_lang.update(fieldkit_data_lang)

    # ---- word stats ----
    total_words = sum(a.word_count for a in published)
    longest = max(published, key=lambda a: a.word_count) if published else None
    mean_words = (total_words // len(published)) if published else 0

    # ---- rank and cap metrics ----
    # Put the "most complete" entries first (those whose value contains both a number
    # and a unit/operator). The home page infographic shows items[0] as the headline.
    # Common English connectors — prose has them, benchmark-table rows don't.
    PROSE_STOPWORDS = {
        "the", "a", "an", "in", "on", "at", "of", "to", "by", "for", "with",
        "is", "are", "was", "were", "be", "been", "has", "have", "had",
        "and", "or", "but", "that", "this", "it", "its", "as", "from",
        "about", "under", "over", "within", "roughly", "around", "nearly",
        "runs", "streams", "returns", "finishes", "answers", "costs", "takes",
    }
    # The site's thesis is local inference on the DGX Spark, so a headline
    # metric that reads "a cloud api answers in 200 ms" is the wrong flag to
    # plant. Demote labels that reference cloud/hosted endpoints so the
    # local-model measurements in earlier articles surface first.
    CLOUD_HINTS = {"cloud", "hosted", "api", "openai", "anthropic", "remote"}

    def metric_rank(item):
        val = item["value"]
        label = item["label"]
        has_number = bool(re.search(r"\d", val))
        has_operator = any(tok in val for tok in ("=", "%"))
        tokens = label.lower().split()
        stop_hits = sum(1 for t in tokens if t in PROSE_STOPWORDS)
        digit_tokens = sum(1 for t in tokens if any(c.isdigit() for c in t))
        cloud_hit = 1 if any(t in CLOUD_HINTS for t in tokens) else 0
        # Primary: value completeness. Secondary: local-vs-cloud (local wins).
        # Tertiary: prose-ness. Quaternary: penalize digit-heavy benchmark rows.
        completeness = 0 if (has_number and has_operator) else 1 if has_number else 2
        return (completeness, cloud_hit, -stop_hits, digit_tokens, len(label))

    metric_caps = {"latency": 4, "throughput": 4, "accuracy": 4}
    capped_metrics = {}
    for cat, items in all_metrics.items():
        items_sorted = sorted(items, key=metric_rank)
        capped_metrics[cat] = items_sorted[:metric_caps.get(cat, 4)]

    # ---- build payload ----
    label_lookup_products = {pid: label for pid, label, _ in PRODUCTS}
    label_lookup_models = {mid: label for mid, label, _ in MODELS}

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "articles": {
            "total": len(published),
            "published": len(published),
            "upcoming": len(upcoming),
            "drafts": drafts,
        },
        "words": {
            "total": total_words,
            "mean_per_article": mean_words,
            "longest": (
                {"slug": longest.slug, "title": longest.title, "words": longest.word_count}
                if longest
                else None
            ),
        },
        "code": {
            "evidence_loc": evidence_total,
            "fieldkit_loc": fieldkit_total,
            "vendored_loc": vendored_total,
            "total_loc": evidence_total + fieldkit_total,
            "by_language": dict(sorted(by_language.items(), key=lambda kv: -kv[1])),
            "data_lines": dict(sorted(data_by_lang.items(), key=lambda kv: -kv[1])),
        },
        "stages": {s: stages_published.get(s, 0) for s in CANONICAL_STAGES},
        "stages_upcoming": {s: stages_upcoming.get(s, 0) for s in CANONICAL_STAGES},
        "models": [
            {"id": mid, "label": label_lookup_models[mid], "articles": count}
            for mid, count in model_article_counts.most_common()
        ],
        "products": [
            {"id": pid, "label": label_lookup_products[pid], "articles": count}
            for pid, count in product_article_counts.most_common()
        ],
        "metrics": capped_metrics,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # ---- human-readable summary ----
    try:
        shown = out_path.relative_to(repo)
    except ValueError:
        shown = out_path
    print(f"Wrote {shown}")
    print(f"  articles:  {payload['articles']['total']}  (upcoming: {payload['articles']['upcoming']}, drafts: {payload['articles']['drafts']})")
    print(f"  words:     {total_words:,}  (mean {mean_words:,}/article; longest: {longest.slug if longest else '—'} @ {longest.word_count if longest else 0:,})")
    print(f"  code:      {payload['code']['total_loc']:,} LOC  (evidence {evidence_total:,} · fieldkit {fieldkit_total:,} · vendored excluded {vendored_total:,})")
    top_langs = list(payload["code"]["by_language"].items())[:5]
    print(f"             languages: " + ", ".join(f"{l}={n}" for l, n in top_langs))
    print(f"  stages:    " + ", ".join(f"{k}={v}" for k, v in payload["stages"].items() if v))
    print(f"  products:  " + ", ".join(f"{p['label']}({p['articles']})" for p in payload["products"][:5]))
    print(f"  models:    " + ", ".join(f"{m['label']}({m['articles']})" for m in payload["models"][:5]))
    print(f"  metrics:   " + ", ".join(f"{k}={len(v)}" for k, v in payload["metrics"].items()))


if __name__ == "__main__":
    main()
