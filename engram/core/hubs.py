from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)")


def vault_status(conn: sqlite3.Connection, activity_log: Path | None) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    by_type = dict(conn.execute(
        "SELECT type, COUNT(*) FROM notes GROUP BY type").fetchall())
    by_conf = dict(conn.execute(
        "SELECT confidence, COUNT(*) FROM notes GROUP BY confidence").fetchall())
    return {"total_notes": total, "by_type": by_type, "by_confidence": by_conf}


def hub_notes(conn: sqlite3.Connection, vault_root: Path, top: int = 5) -> list[dict]:
    rows = conn.execute("SELECT id, title, file_path FROM notes").fetchall()
    id_to_title = {}
    title_to_id = {}
    for nid, title, fpath in rows:
        id_to_title[nid] = title
        if title:
            title_to_id[title.lower()] = nid
    inbound: Counter = Counter()
    for nid, title, fpath in rows:
        p = Path(fpath)
        if not p.exists():
            continue
        for target in WIKILINK_RE.findall(p.read_text(encoding="utf-8")):
            t = target.strip()
            if t in id_to_title:
                inbound[t] += 1
            elif t.lower() in title_to_id:
                inbound[title_to_id[t.lower()]] += 1
    return [{"id": nid, "title": id_to_title.get(nid, nid), "inbound": cnt}
            for nid, cnt in inbound.most_common(top) if nid in id_to_title]
