#!/usr/bin/env python3
"""Salvage already-generated keeper batches from the G4 cache.

Usage: salvage_g4.py [KEEPER_DIR] [OUT_JSONL]
"""
import json
import re
import sys
from pathlib import Path

KEEPER_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/root/.cache/distilabel/pipelines/patent-corpus-v2-full-5000/steps_data/keeper_3b5354b10bcbd1c566314ac976bde84e2472ec12')
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/home/nvidia/data/aifn-corpus-v2/salvaged-128/out.jsonl')


def split_think(raw):
    if not raw:
        return ('', '')
    s = raw
    s = re.sub(r'^\s*<think>\s*', '', s)
    if '</think>' in s:
        chain, _, answer = s.partition('</think>')
        answer = re.sub(r'<think>.*?</think>', '', answer, flags=re.DOTALL).strip()
        answer = re.sub(r'<>\s*', '', answer).strip()
        return (chain.strip(), answer)
    return ('', s.strip())


def main():
    batches = sorted(KEEPER_DIR.glob('batch_*.json'),
                     key=lambda p: int(p.stem.split('_')[1]))
    print(f'Found {len(batches)} keeper batch files', flush=True)
    rows_written = 0
    non_empty = 0
    row_ids = []
    with OUT.open('w') as fout:
        for bf in batches:
            d = json.load(bf.open())
            for grp in d.get('data', []):
                for row in grp:
                    raw = row.get('generation') or ''
                    chain, answer = split_think(raw)
                    rec = {
                        'row_idx': row.get('row_idx'),
                        'family': row.get('family'),
                        'prompt': row.get('prompt'),
                        'mpep_context': row.get('mpep_context'),
                        'chain': chain,
                        'answer': answer,
                        'answer_chars': len(answer),
                        'chain_chars': len(chain),
                    }
                    fout.write(json.dumps(rec) + '\n')
                    rows_written += 1
                    if answer.strip():
                        non_empty += 1
                    row_ids.append(row.get('row_idx'))
    print(f'Salvaged {rows_written} rows to {OUT}', flush=True)
    print(f'Non-empty answers: {non_empty}/{rows_written}', flush=True)
    print(f'row_idx range: {min(row_ids)}..{max(row_ids)}', flush=True)
    print(f'unique row_idx: {len(set(row_ids))}', flush=True)


if __name__ == '__main__':
    main()
