"""Human-readable note ids (slugs).

The note `id` doubles as the filename and the wikilink target, so it must be
readable in Obsidian's graph + file list. We derive a slug from the title.
Type is NOT prefixed — it is already encoded by the PARA folder and the `tipo/`
tag, so a prefix would be redundant and longer.

The id is immutable after creation, so a title-derived slug stays stable.
Collisions get a short deterministic content-hash suffix.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3

MAX_SLUG = 60


def slugify(text: str, maxlen: int = MAX_SLUG) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    s = s[:maxlen].strip("-")
    return s or "note"


def unique_id(title: str, body: str, conn: sqlite3.Connection) -> str:
    """Readable slug id, unique within the vault. On collision, append a short
    content-hash suffix (then a counter for the rare double collision)."""
    base = slugify(title)
    if not conn.execute("SELECT 1 FROM notes WHERE id = ?", (base,)).fetchone():
        return base
    suffix = hashlib.sha256(body.encode("utf-8")).hexdigest()[:4]
    cand = f"{base}-{suffix}"
    i = 2
    while conn.execute("SELECT 1 FROM notes WHERE id = ?", (cand,)).fetchone():
        cand = f"{base}-{suffix}-{i}"
        i += 1
    return cand
