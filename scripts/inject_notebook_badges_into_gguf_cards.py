#!/usr/bin/env python3
"""Inject the notebooks-as-artifacts badge row into the 4 GGUF model READMEs.

Why this script (vs. republish_patent_strategist_readmes.py)
------------------------------------------------------------
The patent-strategist script REGENERATES each card from a hardcoded
positioning/drift/lane spec. The finance / legal / cyber / medical GGUF cards
were already published with authored positioning + bounded drift, so we don't
want to regenerate (that would re-author 4 verticals' copy and risk clobbering
live content). Instead this script does a SURGICAL injection: fetch each live
README, insert a `## Notebooks` section (a Builder/User table with Open-in-Colab
/ Open-in-Kaggle badges) just under the one-liner — above the first `## ` H2,
per NARRATIVE-CONTRACT Rule 8 — and re-upload README.md only. Idempotent: any
previously-injected on-ramp (the `## Notebooks` section, or the retired
single-line `**Notebooks —**` / `**Build it:**` / `**Use it:**` badge forms) is
refreshed in place.

The badge URLs are built by the SAME `fieldkit.notebook` helpers that wrote the
in-notebook badge rows, so the card and the notebook can't drift.

Usage
-----
    python scripts/inject_notebook_badges_into_gguf_cards.py --dry-run   # render to /tmp, review
    python scripts/inject_notebook_badges_into_gguf_cards.py             # push live (HF_TOKEN)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "fieldkit" / "src"))

from fieldkit.notebook import colab_url, kaggle_url, notebook_path  # noqa: E402
from fieldkit.publish import _render_notebook_section  # noqa: E402

# vertical (notebooks/<vertical>/) → live HF GGUF model repo.
VERTICALS = {
    "medical": "Orionfold/II-Medical-8B-GGUF",
    "finance": "Orionfold/finance-chat-GGUF",
    "legal": "Orionfold/Saul-7B-Instruct-v1-GGUF",
    "cyber": "Orionfold/SecurityLLM-GGUF",
}

SECTION_HEADING = "## Notebooks"
# Single-line badge forms we injected in earlier iterations — stripped on a
# re-run so older cards reformat cleanly into the `## Notebooks` section.
RETIRED_LINE_MARKERS = ("**Notebooks —**", "**Build it:**", "**Use it:**")


def notebook_section(vertical: str) -> str:
    """The `## Notebooks` section, rendered by the SAME
    `fieldkit.publish._render_notebook_section` the patent-strategist cards use —
    so the GGUF and patent-strategist surfaces can't drift."""
    notebooks = [
        {
            "label": label,
            "colab": colab_url(notebook_path(vertical, which)),
            "kaggle": kaggle_url(notebook_path(vertical, which)),
        }
        for label, which in (("Build it", "builder"), ("Use it", "user"))
    ]
    return "\n".join(_render_notebook_section(notebooks))


def _strip_existing(lines: list[str]) -> list[str]:
    """Remove any previously-injected on-ramp — both the retired single-line
    badge forms and a `## Notebooks` section (its heading through to the next
    `## ` H2) — so injection is idempotent."""
    lines = [ln for ln in lines if not ln.startswith(RETIRED_LINE_MARKERS)]
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].rstrip() == SECTION_HEADING:
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def inject(readme: str, vertical: str) -> str:
    """Insert (or refresh) the `## Notebooks` section between the one-liner and
    the first `## ` H2. Returns the modified README text."""
    block = notebook_section(vertical)
    lines = _strip_existing(readme.splitlines())

    # Find the first H2 — the section goes immediately above it.
    h2_idx = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), None)
    if h2_idx is None:
        raise SystemExit(f"{vertical}: no '## ' H2 found — refusing to guess insertion point")

    # Collapse the blank line(s) immediately above the H2 so we control spacing
    # exactly: one blank, the section, one blank, then the next H2.
    while h2_idx > 0 and lines[h2_idx - 1].strip() == "":
        del lines[h2_idx - 1]
        h2_idx -= 1
    block_lines = ["", *block.splitlines(), ""]
    new_lines = lines[:h2_idx] + block_lines + lines[h2_idx:]
    return "\n".join(new_lines) + "\n"


def _load_hf_token() -> str:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        return token
    env_local = REPO_ROOT / ".env.local"
    if env_local.exists():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("HF_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("HF_TOKEN not found — set the env var or add it to .env.local")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Render modified READMEs to --out-dir and exit without pushing.")
    ap.add_argument("--out-dir", default="/tmp/hf-notebook-badges")
    args = ap.parse_args()

    from huggingface_hub import HfApi
    token = _load_hf_token()
    api = HfApi(token=token)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rendered: dict[str, Path] = {}
    for vertical, repo in VERTICALS.items():
        cur = api.hf_hub_download(repo_id=repo, filename="README.md", repo_type="model")
        readme = Path(cur).read_text(encoding="utf-8")
        had = SECTION_HEADING in readme or any(m in readme for m in RETIRED_LINE_MARKERS)
        new = inject(readme, vertical)
        p = out_dir / f"{vertical}-README.md"
        p.write_text(new, encoding="utf-8")
        rendered[repo] = p
        print(f"  {repo}: {'refreshed' if had else 'injected'} ## Notebooks section → {p}  ({len(new)} bytes)")

    if args.dry_run:
        print("\nDry run complete. Review, then re-run without --dry-run.")
        return 0

    print("\nPushing README.md only to 4 Orionfold GGUF repos …")
    for repo, p in rendered.items():
        api.upload_file(
            path_or_fileobj=str(p), path_in_repo="README.md",
            repo_id=repo, repo_type="model",
            commit_message="Add a ## Notebooks section (Builder / User, Open in Colab / Kaggle)",
        )
        print(f"  pushed → https://huggingface.co/{repo}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
