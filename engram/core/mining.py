"""Retroactive mining (BL-03): import source files / chat transcripts as
DRAFT candidate notes into a `_mined/` staging area. Curation-first — drafts
are `status: draft`, `confidence: hypothesis`, excluded from default queries,
and meant for human/Claude review before promotion. Zero LLM, fully local.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from engram.config import Config
from engram.core import indexer, fsio, paths

MINED_DIRNAME = "_mined"
DRAFT_TAGS = ["tipo/context", "maturidade/experimental", "dominio/mined"]


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower()
    return s or "untitled"


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _title_from(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or fallback
        if line:
            return line[:80]
    return fallback


def _tldr_from(text: str, fallback: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("---"):
            return s[:100]
    return fallback


def _make_draft(title: str, tldr: str, body: str, project: str,
                source: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    slug = f"mined-{_slug(title)[:40]}-{_short_hash(body)}"
    return {
        "id": slug,
        "title": title,
        "tldr": tldr,
        "type": "context",
        "confidence": "hypothesis",
        "scope": "project",
        "project": project,
        "status": "draft",
        "created": now,
        "updated": now,
        "author": "mining",
        "tags": list(DRAFT_TAGS),
        "confidentiality": "internal",
        "schema_version": 1,
        "_source": source,
    }


def _write_draft(note: dict, body: str, config: Config,
                 conn: sqlite3.Connection) -> None:
    mined_dir = config.vault_root / MINED_DIRNAME
    target = mined_dir / f"{note['id']}.md"
    full_body = f"> Mined from: {note.pop('_source', 'unknown')}\n\n{body}"
    fsio.atomic_write(target, fsio.format_markdown(note, full_body))
    indexer.upsert_note(conn, note, indexer.compute_hash(body), str(target), body)


def mine_files(directory: Path, project: str, config: Config,
               conn: sqlite3.Connection) -> dict:
    """Mine *.md and *.txt under `directory` into draft notes."""
    directory = Path(directory)
    created = 0
    for src in sorted(directory.rglob("*")):
        if src.suffix.lower() not in (".md", ".txt") or not src.is_file():
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        title = _title_from(text, src.stem)
        tldr = _tldr_from(text, f"Mined from {src.name}")
        note = _make_draft(title, tldr, text, project, str(src))
        _write_draft(note, text, config, conn)
        created += 1
    paths.log_activity(config.activity_log, "mine_files", project,
                       {"created": created, "dir": str(directory)})
    return {"status": "ok", "created": created,
            "path": str(config.vault_root / MINED_DIRNAME)}


def mine_convos(directory: Path, project: str, config: Config,
                conn: sqlite3.Connection) -> dict:
    """Mine *.jsonl chat transcripts into one draft note per transcript.
    Each line is a JSON object; text is pulled from a 'content'/'text'/'message'
    field if present, else the whole line."""
    directory = Path(directory)
    created = 0
    for src in sorted(directory.rglob("*.jsonl")):
        if not src.is_file():
            continue
        chunks = []
        for line in src.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                txt = (obj.get("content") or obj.get("text")
                       or obj.get("message") or json.dumps(obj, ensure_ascii=False))
            except json.JSONDecodeError:
                txt = line
            chunks.append(str(txt))
        if not chunks:
            continue
        body = "\n\n".join(chunks)
        title = f"Transcript {src.stem}"
        tldr = f"Mined transcript {src.name} ({len(chunks)} messages)"
        note = _make_draft(title, tldr, body, project, str(src))
        _write_draft(note, body, config, conn)
        created += 1
    paths.log_activity(config.activity_log, "mine_convos", project,
                       {"created": created, "dir": str(directory)})
    return {"status": "ok", "created": created,
            "path": str(config.vault_root / MINED_DIRNAME)}
