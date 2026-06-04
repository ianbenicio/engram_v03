from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlite_vec import serialize_float32

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


def _read_body(file_path: str) -> str:
    p = Path(file_path)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        return parts[2].strip() if len(parts) >= 3 else text
    return text


def path_b(query: QueryRequest, conn: sqlite3.Connection,
           config: Config) -> dict:
    try:
        qvec = embeddings.get_embedding(query.text, config)
    except EmbeddingUnavailable:
        res = path_a(query, conn)
        res["path"] = "B-fallback"
        res["fallback_used"] = True
        return res

    rows = conn.execute(
        "SELECT v.note_id, v.distance, n.title, n.type, n.confidence, "
        "n.file_path, n.confidentiality FROM notes_vec v "
        "JOIN notes n ON n.id = v.note_id "
        "WHERE v.embedding MATCH ? AND k = ? AND n.status != 'archived' "
        "ORDER BY v.distance",
        (serialize_float32(qvec), max(query.limit, 7)),
    ).fetchall()

    if not rows:
        return {"path": "B", "synthesis": "No relevant notes found.",
                "sources": [], "fallback_used": False}

    safe = [r for r in rows if r[6] != "restricted"]
    restricted = len(rows) - len(safe)

    bodies, sources = [], []
    for note_id, dist, title, ntype, conf, fpath, _c in safe[:7]:
        sources.append({"id": note_id, "title": title, "type": ntype,
                        "confidence": conf,
                        "relevance": round(1.0 / (1.0 + dist), 3)})
        body = _read_body(fpath)
        if body:
            bodies.append(f"## [{ntype}|{conf}] {title}\n{body}")
    combined = "\n\n".join(bodies)

    try:
        synthesis = embeddings.synthesize(query.text, combined, config)
    except EmbeddingUnavailable:
        a = path_a(query, conn)
        full = "\n\n---\n\n".join(bodies[:3])
        a["path"] = "B-fallback"
        a["summary"] = a["summary"] + f"\n\n--- Full notes (synth offline) ---\n\n{full}"
        a["fallback_used"] = True
        return a

    result = {"path": "B", "synthesis": synthesis, "sources": sources,
              "fallback_used": False}
    if restricted:
        result["restricted_omitted"] = restricted
    return result
