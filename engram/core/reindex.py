from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from engram.config import Config
from engram.core import indexer
from engram.core import embeddings


def _parse(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
        body = parts[2].strip() if len(parts) >= 3 else text
        return fm or {}, body
    return {}, text


def reindex_file(conn: sqlite3.Connection, path: Path, config: Config) -> bool:
    """Index one note. Returns False if unchanged (hash match)."""
    fm, body = _parse(path)
    if not fm.get("id"):
        return False
    new_hash = indexer.compute_hash(body)
    row = conn.execute("SELECT content_hash FROM notes WHERE id = ?",
                       (fm["id"],)).fetchone()
    if row and row[0] == new_hash:
        # Unchanged content, but backfill the embedding if it was never stored
        # (note saved while Ollama was offline — embed_and_store skips silently,
        # and the hash-skip would otherwise never recover it).
        if not conn.execute("SELECT 1 FROM notes_vec WHERE note_id = ?",
                            (fm["id"],)).fetchone():
            embeddings.embed_and_store(
                conn, fm["id"],
                f"{fm.get('title','')}\n{fm.get('tldr','')}\n{body}", config)
        return False
    try:
        indexer.upsert_note(conn, fm, new_hash, str(path), body)
    except ValueError:
        return False
    embeddings.embed_and_store(conn, fm["id"], f"{fm.get('title','')}\n{fm.get('tldr','')}\n{body}", config)
    return True


def reindex_all(conn: sqlite3.Connection, config: Config) -> dict:
    indexed = skipped = 0
    for sub in ("projetos", "global", "sessoes"):
        base = config.vault_root / sub
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            if "/_cold/" in path.as_posix():
                continue
            if reindex_file(conn, path, config):
                indexed += 1
            else:
                skipped += 1
    return {"indexed": indexed, "skipped": skipped}
