from __future__ import annotations

import re
import sqlite3

from engram.models import QueryRequest

SEMANTIC_PATTERNS = [
    r"impacto|afeta|consequencia",
    r"relacao entre|conexao|depende",
    r"migrar|substituir|trocar",
    r"todos?.*(decisoes|bugs|patterns)",
    r"resumo|overview|visao geral",
    r"por que|motivo|razao",
    r"comparar|diferenca entre",
    r"historico de|evolucao|timeline",
    r"alternativas? (a|para|de)",
    r"impact|affects|consequence",
    r"relationship between|connection|depends",
    r"migrate|replace|switch",
    r"all.*(decisions|bugs|patterns)",
    r"summary|overview|big picture",
    r"why did|reason|rationale",
    r"compare|difference between",
    r"history of|evolution|timeline",
    r"alternatives? (to|for)",
]


def has_semantic_intent(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in SEMANTIC_PATTERNS)


def fts_count(text: str, project: str | None, conn: sqlite3.Connection) -> int:
    safe = text.replace('"', '""')
    try:
        if project:
            return conn.execute(
                "SELECT COUNT(*) FROM notes_fts JOIN notes "
                "ON notes_fts.note_id = notes.id "
                "WHERE notes_fts MATCH ? AND notes.project = ? "
                "AND notes.status != 'archived'", (safe, project)
            ).fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM notes_fts WHERE notes_fts MATCH ?", (safe,)
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def route_query(query: QueryRequest, conn: sqlite3.Connection) -> str:
    if query.depth == "deep":
        return "heavy"
    if query.projects and len(query.projects) > 1:
        return "heavy"
    if query.projects and "*" in query.projects:
        return "heavy"
    if has_semantic_intent(query.text):
        return "heavy"
    project = query.project or (query.projects[0] if query.projects else None)
    if fts_count(query.text, project, conn) > 5:
        return "heavy"
    return "lightweight"
