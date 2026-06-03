#!/usr/bin/env python3
"""Ingest published nvidia-learn articles into pgvector's blog_chunks table.

Matches S2 chunking (900w, 150 overlap) so chunk_idx keys line up with the
S2 eval set in qa-eval.jsonl.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

EMBED_URL = os.environ.get("EMBED_URL", "http://localhost:8001/v1/embeddings")
EMBED_MODEL = "nvidia/llama-nemotron-embed-1b-v2"
EMBED_DIM = 1024

ARTICLES = Path("/home/nvidia/ainative-business.github.io/articles")
PSQL = ["docker", "exec", "-i", "pgvector",
        "psql", "-U", "spark", "-d", "vectors",
        "-v", "ON_ERROR_STOP=1"]


def strip_frontmatter(md: str) -> tuple[dict, str]:
    if md.startswith("---"):
        end = md.find("\n---", 3)
        fm_block = md[3:end]
        body = md[end + 4:]
        fm = {}
        for line in fm_block.strip().split("\n"):
            m = re.match(r"^(\w+):\s*(.*)$", line)
            if m:
                fm[m.group(1)] = m.group(2).strip().strip("'\"")
        return fm, body
    return {}, md


def chunks(text: str, words_per_chunk: int = 900, overlap: int = 150):
    words = text.split()
    i = 0
    while i < len(words):
        yield " ".join(words[i:i + words_per_chunk])
        i += words_per_chunk - overlap


def embed_passages(texts: list[str]) -> list[list[float]]:
    body = json.dumps({
        "model": EMBED_MODEL,
        "input": texts,
        "input_type": "passage",
        "encoding_format": "float",
        "truncate": "END",
        "dimensions": EMBED_DIM,
    }).encode()
    req = urllib.request.Request(
        EMBED_URL, data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return [d["embedding"] for d in json.loads(r.read())["data"]]


def sql(stmt: str, stdin: bytes = b""):
    r = subprocess.run(PSQL + ["-c", stmt], input=stdin, capture_output=True)
    if r.returncode:
        sys.stderr.write(r.stderr.decode())
        raise SystemExit(r.returncode)
    return r.stdout.decode()


def create_table():
    sql("""
        DROP TABLE IF EXISTS blog_chunks;
        CREATE TABLE blog_chunks (
            id        bigserial PRIMARY KEY,
            slug      text NOT NULL,
            chunk_idx int  NOT NULL,
            text      text NOT NULL,
            embedding vector(1024) NOT NULL,
            UNIQUE (slug, chunk_idx)
        );
    """)


def create_indexes():
    sql("""
        CREATE INDEX blog_chunks_hnsw
          ON blog_chunks USING hnsw (embedding vector_cosine_ops)
          WITH (m=16, ef_construction=64);
        CREATE INDEX blog_chunks_fts
          ON blog_chunks USING gin (to_tsvector('english', text));
        CREATE INDEX blog_chunks_slug_idx ON blog_chunks (slug);
    """)


def copy_rows(rows):
    """Bulk load via COPY FROM STDIN. Format: slug \t chunk_idx \t text \t vector."""
    lines = []
    for slug, idx, text, vec in rows:
        text_esc = (text.replace("\\", "\\\\")
                    .replace("\t", " ")
                    .replace("\n", "\\n")
                    .replace("\r", ""))
        vec_str = "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
        lines.append(f"{slug}\t{idx}\t{text_esc}\t{vec_str}")
    payload = ("\n".join(lines) + "\n").encode()
    r = subprocess.run(
        PSQL + ["-c",
                "COPY blog_chunks(slug, chunk_idx, text, embedding) "
                "FROM STDIN WITH (FORMAT text);"],
        input=payload, capture_output=True,
    )
    if r.returncode:
        sys.stderr.write(r.stderr.decode())
        raise SystemExit(r.returncode)


def main():
    print("creating table…", flush=True)
    create_table()

    slugs = sorted(
        d.name for d in ARTICLES.iterdir()
        if d.is_dir() and d.name != "_drafts"
        and (d / "article.md").exists()
    )

    all_chunks = []
    for slug in slugs:
        md = (ARTICLES / slug / "article.md").read_text()
        fm, body = strip_frontmatter(md)
        if fm.get("status") == "upcoming":
            continue
        for idx, passage in enumerate(list(chunks(body))):
            all_chunks.append((slug, idx, passage))

    print(f"chunks: {len(all_chunks)} across {len({c[0] for c in all_chunks})} articles", flush=True)

    BATCH = 16
    t0 = time.time()
    rows = []
    for i in range(0, len(all_chunks), BATCH):
        batch = all_chunks[i:i + BATCH]
        texts = [c[2] for c in batch]
        vecs = embed_passages(texts)
        for (slug, idx, text), vec in zip(batch, vecs):
            rows.append((slug, idx, text, vec))
        print(f"  embedded {i + len(batch)}/{len(all_chunks)}", flush=True)

    print("loading…", flush=True)
    copy_rows(rows)

    print("creating indexes…", flush=True)
    create_indexes()

    print(f"done in {time.time() - t0:.1f}s", flush=True)
    count = sql("SELECT COUNT(*) FROM blog_chunks;")
    print(count.strip())


if __name__ == "__main__":
    main()
