from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from engram.config import Config
from engram.core import indexer, fsio, paths

CONFIDENCE_MAP = {
    "EXTRACTED": "fact",
    "INFERRED": "inference",
    "AMBIGUOUS": "hypothesis",
}


def _slug(node_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", node_id).strip("-").lower()


def import_graph(graph_path: Path, project: str, config: Config,
                 conn: sqlite3.Connection) -> dict:
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e["source"], []).append(e["target"])

    now = datetime.now(timezone.utc).isoformat()
    created = 0
    for node in nodes:
        nid = node["id"]
        slug = _slug(nid)
        conf = CONFIDENCE_MAP.get(node.get("tag", "AMBIGUOUS"), "hypothesis")
        related = [f"[[{_slug(t)}]]" for t in adj.get(nid, [])]
        summary = node.get("summary", "")
        note = {
            "id": slug, "title": nid,
            "tldr": (summary[:100] or f"Imported node {nid}"),
            "type": "context", "confidence": conf, "scope": "project",
            "project": project, "status": "active", "created": now,
            "updated": now, "author": "graphify-import",
            "tags": ["tipo/context", "maturidade/experimental", "dominio/architecture"],
            "related": related, "confidentiality": "internal", "schema_version": 1,
        }
        body = (f"# {nid}\n\n{summary}\n\n## Connections\n" +
                ("\n".join(f"- [[{_slug(t)}]]" for t in adj.get(nid, []))
                 or "- (none)"))
        target = paths.target_path(config.vault_root, note)
        fsio.atomic_write(target, fsio.format_markdown(note, body))
        indexer.upsert_note(conn, note, indexer.compute_hash(body),
                            str(target), body)
        created += 1

    paths.log_activity(config.activity_log, "graphify_import", project,
                       {"created": created, "edges": len(edges)})
    return {"status": "ok", "created": created, "edges": len(edges)}
