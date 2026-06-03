from __future__ import annotations

import math
import sqlite3
import struct
from pathlib import Path

from engram.config import Config


def _deserialize(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _connected_components(n: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def cluster_notes(conn: sqlite3.Connection, config: Config, project: str,
                  threshold: float = 0.75) -> dict:
    rows = conn.execute(
        "SELECT n.id, n.title, v.embedding FROM notes n "
        "JOIN notes_vec v ON v.note_id = n.id "
        "WHERE n.project = ? AND n.status != 'archived'", (project,)
    ).fetchall()
    ids = [r[0] for r in rows]
    titles = {r[0]: r[1] for r in rows}
    vecs = {r[0]: _deserialize(r[2]) for r in rows}

    edges = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if _cosine(vecs[ids[i]], vecs[ids[j]]) >= threshold:
                edges.append((i, j))

    clusters = _connected_components(len(ids), edges)

    lines = [f"# Clusters — {project}", ""]
    for ci, members in enumerate(clusters, 1):
        lines.append(f"## Cluster {ci}")
        for m in members:
            lines.append(f"- [[{ids[m]}]] {titles[ids[m]]}")
        lines.append("")
    out = config.vault_root / "projetos" / project / "_clusters.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    return {"status": "ok", "num_clusters": len(clusters), "path": str(out)}
