from __future__ import annotations

import hashlib
import json
import sqlite3


def compute_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


def upsert_note(conn: sqlite3.Connection, note: dict, content_hash: str,
                file_path: str, body: str) -> None:
    tags = note.get("tags", [])
    conn.execute(
        """INSERT OR REPLACE INTO notes
           (id,title,tldr,type,subtype,confidence,scope,project,module,
            status,created,updated,author,tags_json,content_hash,file_path,
            confidentiality,schema_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            note["id"], note["title"], note.get("tldr", ""), note["type"],
            note.get("subtype"), note["confidence"],
            note.get("scope", "project"), note.get("project"),
            note.get("module"), note.get("status", "active"),
            note["created"], note["updated"], note.get("author", "claude"),
            json.dumps(tags), content_hash, file_path,
            note.get("confidentiality", "internal"),
            note.get("schema_version", 1),
        ),
    )
    conn.execute("DELETE FROM notes_fts WHERE note_id = ?", (note["id"],))
    conn.execute(
        "INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet) "
        "VALUES (?,?,?,?,?)",
        (note["id"], note["title"], note.get("tldr", ""),
         " ".join(tags), body[:500]),
    )
    conn.commit()


def check_duplicate(conn: sqlite3.Connection, content_hash: str) -> str | None:
    row = conn.execute(
        "SELECT id, title FROM notes WHERE content_hash = ?", (content_hash,)
    ).fetchone()
    return f"{row[0]} ({row[1]})" if row else None
