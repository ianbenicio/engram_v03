from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlite_vec import serialize_float32

from engram.config import Config
from engram.models import QueryRequest
from engram.core import embeddings
from engram.core.embeddings import EmbeddingUnavailable


def _recency_factor(updated: str | None, halflife_days: int) -> float:
    """Exponential decay in [0,1] from the note's `updated` timestamp.
    Returns 0.0 for unparseable/missing timestamps (treated as old)."""
    if not updated:
        return 0.0
    try:
        ts = datetime.fromisoformat(updated)
    except (ValueError, TypeError):
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
    if age_days < 0:
        age_days = 0.0
    return 0.5 ** (age_days / max(halflife_days, 1))


def path_a(query: QueryRequest, conn: sqlite3.Connection,
           config: Config | None = None) -> dict:
    """Lightweight FTS5 read path.

    When `config` is provided and `config.recency_weight > 0`, candidates are
    over-fetched (limit*3), re-scored by a blend of normalized FTS rank and a
    recency factor, then trimmed to `query.limit`. With `config=None` or
    `recency_weight == 0`, behavior is pure FTS rank order (backward-compatible).
    """
    recency_weight = config.recency_weight if config else 0.0
    halflife = config.recency_halflife_days if config else 90
    use_recency = recency_weight > 0

    safe = query.text.replace('"', '""')
    sql = (
        "SELECT n.id,n.type,n.title,n.tldr,n.status,n.project,n.updated,"
        "n.confidence, f.rank FROM notes_fts f JOIN notes n ON f.note_id = n.id "
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
    sql += " ORDER BY rank LIMIT ?"
    params.append(query.limit * 3 if use_recency else query.limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        rows = []

    if use_recency and rows:
        # FTS `rank` is bm25 (lower = better). Normalize -rank within the
        # candidate window to [0,1]; blend with recency factor.
        fts_scores = [-r[8] for r in rows]
        lo, hi = min(fts_scores), max(fts_scores)
        span = (hi - lo) or 1.0
        scored = []
        for r, fts in zip(rows, fts_scores):
            fts_norm = (fts - lo) / span
            rec = _recency_factor(r[6], halflife)
            combined = (1.0 - recency_weight) * fts_norm + recency_weight * rec
            scored.append((combined, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        rows = [r for _, r in scored[:query.limit]]

    results, lines = [], []
    for row in rows:
        nid, ntype, title, tldr, status, project, updated, conf = row[:8]
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
        res = path_a(query, conn, config)
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
        a = path_a(query, conn, config)
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
