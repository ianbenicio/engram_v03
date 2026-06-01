from __future__ import annotations

import sqlite3
from pathlib import Path

from engram.config import Config
from engram.models import QueryRequest
from engram.core import embeddings
from engram.core.embeddings import EmbeddingUnavailable


def path_a(query: QueryRequest, conn: sqlite3.Connection) -> dict:
    safe = query.text.replace('"', '""')
    sql = (
        "SELECT n.id,n.type,n.title,n.tldr,n.status,n.project,n.updated,"
        "n.confidence FROM notes_fts f JOIN notes n ON f.note_id = n.id "
        "WHERE notes_fts MATCH ?"
    )
    params: list = [safe]
    if query.project:
        sql += " AND n.project = ?"; params.append(query.project)
    if query.status_filter:
        sql += " AND n.status = ?"; params.append(query.status_filter)
    else:
        sql += " AND n.status != 'archived'"
    if query.type_filter:
        sql += " AND n.type = ?"; params.append(query.type_filter)
    if not query.include_cold:
        sql += " AND n.file_path NOT LIKE '%/_cold/%'"
    sql += " ORDER BY rank LIMIT ?"; params.append(query.limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        rows = []

    results, lines = [], []
    for nid, ntype, title, tldr, status, project, updated, conf in rows:
        results.append({"id": nid, "type": ntype, "title": title,
                        "tldr": tldr, "confidence": conf, "project": project})
        lines.append(f"[{ntype}|{conf}] {tldr}")
    summary = "\n".join(lines) if lines else "No matches found."
    return {"path": "A", "results": results, "summary": summary,
            "match_count": len(results)}
