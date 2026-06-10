"""Cross-project shared-knowledge detector (Canonical + Instances).

Scans embedding similarity across notes that live in DIFFERENT projects and
produces a *comparative context report*: for each shared element, it shows how
the same element is used in each project (convergence/divergence). The human/LLM
reads it to decide whether to promote the essence to a `global/` canonical and
link the project notes via `instance_of`.

Read-only. Reuses the cosine helpers from clustering. Degrades to an empty
report if there are no embeddings.
"""
from __future__ import annotations

import sqlite3

from engram.config import Config
from engram.core.clustering import _cosine, _deserialize


def _active_embeddings(conn: sqlite3.Connection) -> list[tuple]:
    rows = conn.execute(
        "SELECT n.id, n.title, n.tldr, n.project, v.embedding "
        "FROM notes n JOIN notes_vec v ON v.note_id = n.id "
        "WHERE n.status = 'active'"
    ).fetchall()
    return [(nid, title, tldr, project, _deserialize(emb))
            for nid, title, tldr, project, emb in rows]


def find_similar(conn: sqlite3.Connection, note_id: str,
                 threshold: float = 0.85, k: int = 4) -> list[dict]:
    """Contextual catalog gate (save-time): find existing active notes similar
    to `note_id`. Similar data is NOT bad — the same element can be wrong in
    one context and perfect in another. So this never blocks: it surfaces the
    similar notes so the writer can link them (related[]/instance_of) and
    contextualize each use. Returns [] if the note has no embedding."""
    row = conn.execute("SELECT embedding FROM notes_vec WHERE note_id = ?",
                       (note_id,)).fetchone()
    if not row:
        return []
    me = _deserialize(row[0])
    out = []
    for nid, title, tldr, project, vec in _active_embeddings(conn):
        if nid == note_id:
            continue
        sim = _cosine(me, vec)
        if sim >= threshold:
            out.append({"id": nid, "title": title, "tldr": tldr,
                        "project": project, "similarity": round(sim, 3)})
    out.sort(key=lambda x: x["similarity"], reverse=True)
    return out[:k]


def cross_project_report(conn: sqlite3.Connection, config: Config,
                         threshold: float = 0.85) -> list[dict]:
    """Group active notes from DIFFERENT projects whose embeddings are similar
    (cosine >= threshold). Returns a comparative report, one entry per group."""
    items = _active_embeddings(conn)
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if items[i][3] == items[j][3]:
                continue  # same project — not cross-project
            if _cosine(items[i][4], items[j][4]) >= threshold:
                parent[find(i)] = find(j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    report = []
    for members in groups.values():
        projects = {items[m][3] for m in members}
        if len(members) < 2 or len(projects) < 2:
            continue  # only genuine cross-project shared elements
        report.append({
            "projects": sorted(p for p in projects if p),
            "members": [
                {"project": items[m][3], "id": items[m][0],
                 "title": items[m][1], "tldr": items[m][2]}
                for m in members
            ],
        })
    return report
