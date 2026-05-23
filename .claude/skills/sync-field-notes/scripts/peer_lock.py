#!/usr/bin/env python3
"""
Peer-writer heartbeat for /sync-field-notes.

Why this exists. The repo at /Volumes/home/ai-field-notes/ is a single physical
checkout on the Spark, accessed from the Mac over `smbfs` (TCP 445 / WiFi).
Bulk writes from concurrent Mac processes (sync-field-notes, the source-side
notebook-author / notebook-snapshot pipeline) hit the same raw bytes with no
conflict mediation. On 2026-05-23 a concurrent bulk write corrupted 5 notebook
.py files (RECONCILE-SPARK-MAC.md). The fix from that postmortem: drop a
heartbeat file at the repo root, write at the start of any bulk write, check
on entry, delete on exit.

Convention (agreed across Mac↔Spark). All bulk writers touching the shared
tree must:
  1. acquire(tool_name) before starting; if it returns None, abort.
  2. release() in a finally: clause.

The heartbeat is /Volumes/home/ai-field-notes/.sync-active and is JSON:
  {"pid": 12345, "tool": "sync_articles.py", "started": "2026-05-23T13:55:00",
   "host": "<hostname>"}

A heartbeat older than 5 minutes is treated as a leaked lock and overwritten.
That window is generous on purpose — a real /sync-field-notes run takes seconds,
so 300s of staleness almost certainly means a crashed writer.

CLI for SKILL.md Step 1 (callable from Bash):
  python3 peer_lock.py check          # exit 0 = free, exit 1 = peer active
  python3 peer_lock.py acquire <tool> # exit 0 = lock taken, exit 1 = peer active
  python3 peer_lock.py release        # always exit 0
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

LOCK_PATH = Path("/Volumes/home/ai-field-notes/.sync-active")
STALE_SECONDS = 300


def _peer_info() -> dict:
    """Return the active-writer dict if a fresh heartbeat is present, else {}.

    A stale heartbeat (>STALE_SECONDS old) is treated as no peer — the prior
    writer leaked it. Returning {} lets acquire() overwrite without blocking.
    """
    if not LOCK_PATH.exists():
        return {}
    try:
        age = time.time() - LOCK_PATH.stat().st_mtime
        if age > STALE_SECONDS:
            return {}
        return json.loads(LOCK_PATH.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError):
        return {}


def acquire(tool: str) -> bool:
    """Claim the heartbeat for this writer. Returns True on success.

    Writes <lock>.tmp then os.replace() so an interrupted flush over smbfs
    can't leave a half-file at the lock path — same atomic pattern this skill
    recommends for source-side article writes.
    """
    peer = _peer_info()
    if peer:
        print(
            f"[peer_lock] another writer is active on the shared tree:\n"
            f"            pid={peer.get('pid')} tool={peer.get('tool')} "
            f"started={peer.get('started')} host={peer.get('host')}\n"
            f"            wait for it to finish or delete {LOCK_PATH} "
            f"manually if you're sure it's stale.",
            file=sys.stderr,
        )
        return False
    payload = json.dumps(
        {
            "pid": os.getpid(),
            "tool": tool,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "host": socket.gethostname(),
        }
    )
    tmp = LOCK_PATH.with_suffix(LOCK_PATH.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf8")
    os.replace(tmp, LOCK_PATH)
    return True


def release() -> None:
    """Best-effort delete of the heartbeat. Never raises."""
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _cli() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        info = _peer_info()
        if info:
            print(json.dumps(info))
            return 1
        return 0
    if cmd == "acquire":
        tool = sys.argv[2] if len(sys.argv) > 2 else "manual-sync"
        return 0 if acquire(tool) else 1
    if cmd == "release":
        release()
        return 0
    print(f"Usage: {sys.argv[0]} (check | acquire <tool> | release)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
