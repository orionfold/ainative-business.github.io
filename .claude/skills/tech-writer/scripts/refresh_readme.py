#!/usr/bin/env python3
"""Regenerate the top-level README.md for ai-field-notes.

The README mirrors the homepage's editorial layout — masthead headline,
"At a glance" stats, stage + product tables, and an article index grouped
by primary stage. It pulls live numbers from src/data/project-stats.json
(written by the nvidia-learn-stats skill) and frontmatter from each
articles/<slug>/article.md.

Invoked by the tech-writer skill on draft, upcoming, polish, and publish
flows so the README never drifts behind the site.

Usage:
    python3 refresh_readme.py [--repo PATH]

Defaults to /home/nvidia/ainative-business.github.io. Writes README.md in place.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

LIVE_BASE = "https://ainative.business/field-notes"
REPO_HTTPS = "https://github.com/manavsehgal/ai-field-notes"

STAGE_ORDER = [
    ("foundations",   "Foundations"),
    ("training",      "Training"),
    ("fine-tuning",   "Fine-tuning"),
    ("inference",     "Inference"),
    ("deployment",    "Deployment"),
    ("agentic",       "Agentic"),
    ("observability", "Observability"),
    ("dev-tools",     "Dev-tools"),
]


def parse_frontmatter(article_path: Path) -> dict:
    """Read YAML frontmatter from an article.md. Returns {} if missing."""
    text = article_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        print(f"warn: {article_path} frontmatter parse error: {e}", file=sys.stderr)
        return {}
    return data


def load_articles(repo: Path) -> list[dict]:
    out = []
    for sub in sorted((repo / "articles").iterdir()):
        if not sub.is_dir() or sub.name.startswith("_"):
            continue
        article_md = sub / "article.md"
        if not article_md.exists():
            continue
        fm = parse_frontmatter(article_md)
        if not fm:
            continue
        fm["slug"] = sub.name
        out.append(fm)
    return out


def fmt_date(d) -> str:
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    if hasattr(d, "isoformat"):
        return d.isoformat()
    return str(d) if d else ""


def article_link(slug: str) -> str:
    return f"{LIVE_BASE}/articles/{slug}/"


def stage_link(stage_id: str) -> str:
    return f"{LIVE_BASE}/stage/{stage_id}/"


def render_volume_label(stats: dict) -> str:
    raw = stats.get("generated_at", "")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%b %Y")
    except Exception:
        return datetime.now().strftime("%b %Y")


def render_stages_table(stats: dict) -> str:
    pub = stats.get("stages", {})
    upc = stats.get("stages_upcoming", {})
    rows = ["| Stage | Published | Upcoming |", "|---|:-:|:-:|"]
    for sid, label in STAGE_ORDER:
        p = pub.get(sid, 0)
        u = upc.get(sid, 0)
        p_cell = str(p) if p else "—"
        u_cell = str(u) if u else "—"
        rows.append(f"| [{label}]({stage_link(sid)}) | {p_cell} | {u_cell} |")
    return "\n".join(rows)


def render_products_table(stats: dict) -> str:
    products = stats.get("products", [])
    if not products:
        return "_No products yet._"
    rows = ["| Product | Articles |", "|---|:-:|"]
    for p in products:
        rows.append(f"| {p['label']} | {p['articles']} |")
    return "\n".join(rows)


def render_models_table(stats: dict) -> str:
    models = stats.get("models", [])
    if not models:
        return "_No models yet._"
    rows = ["| Model | Articles |", "|---|:-:|"]
    for m in models:
        rows.append(f"| {m['label']} | {m['articles']} |")
    return "\n".join(rows)


def group_articles_by_stage(articles: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """Group by primary stage; within each, split published vs upcoming."""
    groups: dict[str, dict[str, list[dict]]] = {
        sid: {"published": [], "upcoming": []} for sid, _ in STAGE_ORDER
    }
    for art in articles:
        stage = art.get("stage")
        if stage not in groups:
            continue
        bucket = "upcoming" if art.get("status") == "upcoming" else "published"
        groups[stage][bucket].append(art)
    # newest first by date within each bucket
    for sid in groups:
        for bucket in groups[sid]:
            groups[sid][bucket].sort(
                key=lambda a: (fmt_date(a.get("date", "")), a["slug"]),
                reverse=True,
            )
    return groups


def render_article_index(articles: list[dict]) -> str:
    groups = group_articles_by_stage(articles)
    out: list[str] = []
    for sid, label in STAGE_ORDER:
        pub = groups[sid]["published"]
        upc = groups[sid]["upcoming"]
        if not pub and not upc:
            continue
        out.append(f"### {label}")
        out.append("")
        for art in pub:
            title = art.get("title", art["slug"])
            summary = art.get("summary", "").strip()
            out.append(f"- **[{title}]({article_link(art['slug'])})** — {summary}")
        for art in upc:
            title = art.get("title", art["slug"])
            summary = art.get("summary", "").strip()
            planned = fmt_date(art.get("date", ""))
            planned_label = f" *(planned {planned})*" if planned else " *(upcoming)*"
            out.append(f"- 🔜 **[{title}]({article_link(art['slug'])})**{planned_label} — {summary}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_readme(stats: dict, articles: list[dict]) -> str:
    counts = stats.get("articles", {})
    words = stats.get("words", {})
    code = stats.get("code", {})
    n_pub = counts.get("published", len([a for a in articles if a.get("status") != "upcoming"]))
    n_upc = counts.get("upcoming", len([a for a in articles if a.get("status") == "upcoming"]))
    n_words = words.get("total", 0)
    n_loc = code.get("total_loc", 0)
    n_models = len(stats.get("models", []))
    n_products = len(stats.get("products", []))
    vol_label = render_volume_label(stats)

    upc_suffix = f" *(+{n_upc} upcoming)*" if n_upc else ""

    parts = [
        f'<p align="center">',
        f'  <a href="{LIVE_BASE}/"><img src="public/og-image.png" alt="AI Field Notes — field notes on the DGX Spark" width="100%" /></a>',
        f'</p>',
        '',
        f'<p align="center">',
        f'  <a href="{LIVE_BASE}/"><b>Live site</b></a>',
        f'  &nbsp;·&nbsp;',
        f'  <a href="#articles">Articles</a>',
        f'  &nbsp;·&nbsp;',
        f'  <a href="#at-a-glance">At a glance</a>',
        f'  &nbsp;·&nbsp;',
        f'  <a href="#run-locally">Run locally</a>',
        f'</p>',
        '',
        f'<sub>Vol. 01 &nbsp;·&nbsp; ai-field-notes &nbsp;·&nbsp; {vol_label}</sub>',
        '',
        '# Field notes on the *DGX Spark*.',
        '',
        '> One builder maximising the NVIDIA DGX Spark as a personal AI power user and edge AI rig. Every article is a session transcript turned into a deep-dive essay.',
        '',
        f'<sub><b>{n_pub} articles published</b> &nbsp;·&nbsp; Apache 2.0 &nbsp;·&nbsp; by <a href="https://github.com/manavsehgal">Manav Sehgal</a></sub>',
        '',
        '---',
        '',
        '## At a glance',
        '',
        '| Articles | Words | Lines of code | Models | NVIDIA products |',
        '|:-:|:-:|:-:|:-:|:-:|',
        f'| **{n_pub}**{upc_suffix} | **{n_words:,}** | **{n_loc:,}** | **{n_models}** | **{n_products}** |',
        '',
        '### Stages',
        '',
        render_stages_table(stats),
        '',
        '### Products & frameworks',
        '',
        render_products_table(stats),
        '',
        '### Models',
        '',
        render_models_table(stats),
        '',
        '---',
        '',
        '## Articles',
        '',
        'Each article is a deep-dive essay grown from a single session transcript on the Spark. Click through for the full piece on the live site.',
        '',
        render_article_index(articles),
        '---',
        '',
        '## Run locally',
        '',
        '```bash',
        'npm install        # one-time',
        'npm run dev        # dev server: http://localhost:4321/',
        '                   #              http://<spark-lan-ip>:4321/',
        'npm run build      # static build to dist/ (uses /field-notes/ base)',
        'npm run preview    # preview the production build',
        '```',
        '',
        'The dev server binds to all interfaces (`server.host: true` in `astro.config.mjs`), so the site is reachable on the LAN or tailnet, not just on the Spark itself.',
        '',
        '## Authoring articles',
        '',
        'Articles live at `articles/<slug>/article.md`. Each folder also holds `screenshots/`, `transcript.md` (source provenance), and `assets/`.',
        '',
        'Voice, structure, frontmatter schema, screenshot workflow, and privacy scrub are handled by the **tech-writer** Claude Code skill — invoke it from inside Claude Code to draft, polish, or publish an article. The skill keeps this README in sync by calling `~/.claude/skills/tech-writer/scripts/refresh_readme.py` whenever an article is created or its frontmatter changes.',
        '',
        '## Design',
        '',
        'The site is an editorial research-index — dark-first OKLCH palette at hue 250 (indigo-blue accent), **Geist Sans** for display and body, **Geist Mono** for metadata and code. Tokens and component styles live in `src/styles/global.css`.',
        '',
        'The **Marked Field** logo is a custom geometric mark: three nodes on an implied 3×3 graph-paper grid with a glowing spark in the bottom-right. See `src/components/Logo.astro`. The favicon, Apple touch icon, and 1200×630 social card live in `public/`.',
        '',
        '## License',
        '',
        f'Apache 2.0 &nbsp;·&nbsp; by [Manav Sehgal]({REPO_HTTPS.replace("/ai-field-notes","")})',
        '',
        '<sub>Generated by `~/.claude/skills/tech-writer/scripts/refresh_readme.py` from `src/data/project-stats.json` and per-article frontmatter. Do not hand-edit — rerun the script.</sub>',
        '',
    ]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo",
        default="/home/nvidia/ainative-business.github.io",
        help="path to the ai-field-notes repo (default: /home/nvidia/ainative-business.github.io)",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    stats_path = repo / "src" / "data" / "project-stats.json"
    if not stats_path.exists():
        print(f"error: stats not found at {stats_path} — run nvidia-learn-stats first", file=sys.stderr)
        return 1

    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    articles = load_articles(repo)
    body = render_readme(stats, articles)
    (repo / "README.md").write_text(body, encoding="utf-8")
    print(f"wrote {repo / 'README.md'} ({len(body)} bytes, {len(articles)} articles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
