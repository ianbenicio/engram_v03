from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path

import yaml

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
        text = p.read_text(encoding="utf-8")
        targets: list = []
        body = text
        # Count structured frontmatter edges (related[]/instance_of) — most
        # notes link via frontmatter ids, not body [[wikilinks]]. Scan the body
        # separately so a related: ['[[x]]'] isn't double-counted.
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    fm = {}
                rel = fm.get("related") or []
                if isinstance(rel, list):
                    targets.extend(str(r) for r in rel)
                if fm.get("instance_of"):
                    targets.append(str(fm["instance_of"]))
                body = parts[2]
        targets.extend(WIKILINK_RE.findall(body))
        for target in targets:
            t = target.strip().strip("[]").split("|")[0].strip()
            if t in id_to_title:
                inbound[t] += 1
            elif t.lower() in title_to_id:
                inbound[title_to_id[t.lower()]] += 1
    return [{"id": nid, "title": id_to_title.get(nid, nid), "inbound": cnt}
            for nid, cnt in inbound.most_common(top) if nid in id_to_title]
