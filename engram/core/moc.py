"""MOC (Map of Content) generator — an LLM/human entry point per project.

A MOC is a living index: hub notes first (the most-referenced anchors), then
all active notes grouped by PARA bucket and type, each as a wikilink with its
TL;DR and confidence. An LLM entering the vault reads the MOC and has the
module's map in seconds, without scanning file-by-file.

The MOC is a generated index (no frontmatter id) — it is not indexed as a note.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from engram.config import Config
from engram.core.hubs import hub_notes

# type -> PARA bucket (mirrors paths.TYPE_FOLDERS grouping)
BUCKET = {
    "decision": "Resources", "pattern": "Resources", "concept": "Resources",
    "context": "Areas", "runbook": "Areas", "refactoring": "Areas", "metric": "Areas",
    "bug": "Projects", "post-mortem": "Projects", "experiment": "Projects",
    "session": "Projects",
}
BUCKET_ORDER = ["Resources", "Areas", "Projects", "Other"]


def generate_moc(conn: sqlite3.Connection, config: Config, project: str) -> dict:
    rows = conn.execute(
        "SELECT id, title, tldr, type, confidence FROM notes "
        "WHERE project = ? AND status NOT IN ('archived','draft') "
        "ORDER BY type, updated DESC",
        (project,),
    ).fetchall()

    project_ids = {r[0] for r in rows}
    hubs = [h for h in hub_notes(conn, config.vault_root, top=20)
            if h["id"] in project_ids][:8]

    groups: dict[str, dict[str, list]] = {}
    for nid, title, tldr, ntype, conf in rows:
        bucket = BUCKET.get(ntype, "Other")
        groups.setdefault(bucket, {}).setdefault(ntype, []).append(
            (nid, title, tldr, conf))

    now = datetime.now(timezone.utc).isoformat()[:16]
    lines = [f"# MOC — {project}", "",
             f"> Map of Content. {len(rows)} active notes. Generated {now}.", ""]

    if hubs:
        lines.append("## Hub notes (most referenced)")
        for h in hubs:
            lines.append(f"- [[{h['id']}]] {h['title']} ({h['inbound']} refs)")
        lines.append("")

    for bucket in BUCKET_ORDER:
        if bucket not in groups:
            continue
        lines.append(f"## {bucket}")
        for ntype, items in groups[bucket].items():
            lines.append(f"### {ntype}")
            for nid, title, tldr, conf in items:
                lines.append(f"- [[{nid}]] **{title}** — {tldr} `{conf}`")
            lines.append("")

    out = config.vault_root / "projetos" / project / f"MOC-{project}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "path": str(out), "note_count": len(rows),
            "hubs": len(hubs)}
