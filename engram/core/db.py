from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

VEC_DIM = 1024  # bge-m3 embedding dimension

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    tldr TEXT,
    type TEXT NOT NULL,
    subtype TEXT,
    confidence TEXT NOT NULL,
    scope TEXT DEFAULT 'project',
    project TEXT,
    module TEXT,
    status TEXT DEFAULT 'active',
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    author TEXT DEFAULT 'claude',
    tags_json TEXT,
    content_hash TEXT,
    file_path TEXT,
    confidentiality TEXT DEFAULT 'internal',
    schema_version INTEGER DEFAULT 1
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    note_id UNINDEXED, title, tldr, tags_text, body_snippet
);

CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project);
CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(type);
CREATE INDEX IF NOT EXISTS idx_notes_status ON notes(status);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS notes_vec USING vec0("
        f"note_id TEXT PRIMARY KEY, embedding float[{VEC_DIM}])"
    )
    conn.commit()
