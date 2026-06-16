from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlite_vec import serialize_float32

from engram.config import Config
from engram.models import QueryRequest
from engram.core import embeddings, usage
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


def _keyword_overlap(query_text: str, *fields: str) -> float:
    """Fraction of query tokens (len>=2) present in the given fields. [0,1]."""
    tokens = {t for t in re.split(r"[^a-z0-9]+", query_text.lower()) if len(t) >= 2}
    if not tokens:
        return 0.0
    hay = " ".join(f.lower() for f in fields if f)
    return sum(1 for t in tokens if t in hay) / len(tokens)


def _rerank_score(query_text: str, dist: float, title: str, tldr: str,
                  updated: str | None, halflife_days: int) -> float:
    """Cheap deterministic rerank: vector similarity + keyword overlap +
    recency. Zero LLM. Returns a blended score (higher = better)."""
    vec_sim = 1.0 / (1.0 + dist)
    kw = _keyword_overlap(query_text, title, tldr)
    rec = _recency_factor(updated, halflife_days)
    return 0.5 * vec_sim + 0.3 * kw + 0.2 * rec


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
        sql += " AND n.status NOT IN ('archived','draft')"
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

    # Usage signal (reinforced retention): record which notes this query
    # surfaced. Never fails the query.
    if config and results:
        try:
            usage.log_retrieval(config.activity_log,
                                [r["id"] for r in results], "A")
        except OSError:
            pass

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

    knn_k = max(query.limit, 20) if config.rerank else max(query.limit, 7)
    rows = conn.execute(
        "SELECT v.note_id, v.distance, n.title, n.type, n.confidence, "
        "n.file_path, n.confidentiality, n.tldr, n.updated FROM notes_vec v "
        "JOIN notes n ON n.id = v.note_id "
        "WHERE v.embedding MATCH ? AND k = ? "
        "AND n.status NOT IN ('archived','draft') "
        "ORDER BY v.distance",
        (serialize_float32(qvec), knn_k),
    ).fetchall()

    if not rows:
        return {"path": "B", "synthesis": "No relevant notes found.",
                "sources": [], "fallback_used": False}

    safe = [r for r in rows if r[6] != "restricted"]
    restricted = len(rows) - len(safe)

    # BL-02: cheap deterministic rerank (vec sim + keyword overlap + recency),
    # zero LLM. Default off (config.rerank) -> pure KNN distance order.
    if config.rerank and safe:
        hl = config.recency_halflife_days
        safe.sort(
            key=lambda r: _rerank_score(query.text, r[1], r[2], r[7], r[8], hl),
            reverse=True,
        )

    bodies, sources = [], []
    for row in safe[:7]:
        note_id, dist, title, ntype, conf, fpath = (
            row[0], row[1], row[2], row[3], row[4], row[5])
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
        # Synthesis (LLM) offline but vector retrieval succeeded: return the
        # KNN-matched notes raw instead of re-running FTS, which often matches
        # nothing for a natural-language query and would mislead with
        # match_count 0 despite relevant notes being found.
        results = [{"id": r[0], "type": r[3], "title": r[2],
                    "confidence": r[4],
                    "relevance": round(1.0 / (1.0 + r[1]), 3)}
                   for r in safe[:7]]
        full = "\n\n---\n\n".join(bodies[:3])
        return {"path": "B-fallback", "results": results,
                "summary": full or "No relevant notes found.",
                "match_count": len(results), "fallback_used": True}

    # Usage signal (reinforced retention)
    if sources:
        try:
            usage.log_retrieval(config.activity_log,
                                [s["id"] for s in sources], "B")
        except OSError:
            pass

    result = {"path": "B", "synthesis": synthesis, "sources": sources,
              "fallback_used": False}
    if restricted:
        result["restricted_omitted"] = restricted
    return result
