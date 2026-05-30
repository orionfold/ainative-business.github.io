#!/usr/bin/env python3
"""G5 — cross-slice cosine-similarity audit for the patent-strategist v2 corpus.

Embeds each answer with BAAI/bge-base-en-v1.5, then for each family computes
mean + max pairwise cosine similarity. Flag families with mean cos > 0.7.
Also reports the K most-similar answer pairs per family for manual review.

Usage:
    python3 scripts/g5_corpus_audit.py [SRC_JSONL] [REPORT_JSON]

Defaults:
    SRC_JSONL   /home/nvidia/data/aifn-corpus-v2/merged-clean.jsonl
    REPORT_JSON /home/nvidia/data/aifn-corpus-v2/g5-cosine-audit.json
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

os.environ.setdefault('HF_HUB_CACHE', '/home/nvidia/data/.hf-cache/hub')
os.environ.setdefault('HF_HOME', '/home/nvidia/data/.hf-cache')

from sentence_transformers import SentenceTransformer  # noqa: E402

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/home/nvidia/data/aifn-corpus-v2/merged-clean.jsonl')
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/home/nvidia/data/aifn-corpus-v2/g5-cosine-audit.json')

# Threshold for flagging a family as over-similar.
FLAG_MEAN_COS = 0.70
TOP_K_PAIRS = 5  # most-similar pairs per family to surface for manual review


def main() -> int:
    print(f'loading rows from {SRC}', flush=True)
    rows = [json.loads(l) for l in SRC.open()]
    print(f'rows: {len(rows)}', flush=True)

    print('loading BAAI/bge-base-en-v1.5 (CPU)…', flush=True)
    model = SentenceTransformer('BAAI/bge-base-en-v1.5', device='cpu')

    texts = [r['answer'] for r in rows]
    print(f'embedding {len(texts)} answers (batch=32)…', flush=True)
    embs = model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    print(f'embeddings shape: {embs.shape}', flush=True)

    # Bucket indices by family
    by_fam: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_fam[r['family']].append(i)

    report = {
        'src': str(SRC),
        'n_rows': len(rows),
        'embedder': 'BAAI/bge-base-en-v1.5',
        'flag_threshold_mean_cos': FLAG_MEAN_COS,
        'families': {},
    }

    print()
    print(f'{"family":8s} {"n":>5s} {"mean_cos":>10s} {"median_cos":>12s} {"max_cos":>9s} {"p95_cos":>9s}  flag')

    for fam, idxs in sorted(by_fam.items()):
        sub = embs[idxs]
        # n×n cosine similarity (sub is normalized → dot product is cosine)
        sim = sub @ sub.T
        n = len(idxs)
        # Upper triangle, excluding diagonal
        iu = np.triu_indices(n, k=1)
        pair_cos = sim[iu]

        mean_cos = float(pair_cos.mean())
        median_cos = float(np.median(pair_cos))
        max_cos = float(pair_cos.max())
        p95_cos = float(np.percentile(pair_cos, 95))
        flag = mean_cos > FLAG_MEAN_COS

        # Top-K most-similar pairs (for manual eyeball)
        top_k = []
        if n > 1:
            flat = np.argsort(-pair_cos)[:TOP_K_PAIRS]
            for f_pos in flat:
                a, b = iu[0][f_pos], iu[1][f_pos]
                row_a = rows[idxs[a]]
                row_b = rows[idxs[b]]
                top_k.append({
                    'cos': float(pair_cos[f_pos]),
                    'a_row_idx': row_a['row_idx'],
                    'b_row_idx': row_b['row_idx'],
                    'a_prompt': row_a['prompt'][:160],
                    'b_prompt': row_b['prompt'][:160],
                })

        flag_marker = ' ⚠ FLAG' if flag else ''
        print(f'{fam:8s} {n:5d} {mean_cos:10.4f} {median_cos:12.4f} {max_cos:9.4f} {p95_cos:9.4f}{flag_marker}')

        report['families'][fam] = {
            'n': n,
            'mean_cos': mean_cos,
            'median_cos': median_cos,
            'max_cos': max_cos,
            'p95_cos': p95_cos,
            'flagged': flag,
            'top_k_pairs': top_k,
        }

    # Global mean (over ALL pairs, not just within-family)
    print()
    print('computing global cross-family similarity sample…', flush=True)
    # Full 1691×1691 is fine (~22 MB). Skip computing all pairs (too much), just sample.
    rng = np.random.default_rng(seed=42)
    sample_n = min(2000, len(rows))
    sample_idx = rng.choice(len(rows), size=sample_n, replace=False)
    sub = embs[sample_idx]
    sim = sub @ sub.T
    iu = np.triu_indices(len(sample_idx), k=1)
    global_pair_cos = sim[iu]
    print(f'global pairwise (sample={sample_n}): mean={global_pair_cos.mean():.4f} max={global_pair_cos.max():.4f}')
    report['global_sampled_pairwise'] = {
        'sample_n': int(sample_n),
        'mean_cos': float(global_pair_cos.mean()),
        'median_cos': float(np.median(global_pair_cos)),
        'max_cos': float(global_pair_cos.max()),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w') as o:
        json.dump(report, o, indent=2)
    print(f'\nwrote report to {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
