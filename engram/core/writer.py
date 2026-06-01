from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ulid import ULID

from engram.config import Config
from engram.models import NoteData
from engram.core import indexer, validator, fsio, paths, locking


def vault_save(note: NoteData, body: str, config: Config,
               conn: sqlite3.Connection) -> dict:
    data = note.model_dump(mode="json", exclude_none=False)
    warnings: list[str] = []

    if not data.get("id"):
        data["id"] = str(ULID())
    now = datetime.now(timezone.utc).isoformat()
    data["created"] = data.get("created") or now
    data["updated"] = now

    if data["type"] not in config.enabled_types:
        return {"status": "error",
                "reason": f"Type '{data['type']}' not enabled in config"}

    missing = validator.validate_required_fields(data)
    if missing:
        return {"status": "error", "reason": f"Missing required fields: {missing}"}

    missing_prefix = validator.validate_tag_prefixes(data["tags"])
    if missing_prefix:
        return {"status": "error",
                "reason": f"Missing required tag prefix: {missing_prefix}"}

    vocab = validator.load_tags_vocab(config.vault_root)
    invalid = validator.validate_tags(data["tags"], vocab)
    if invalid:
        return {"status": "error", "reason": f"Invalid tags: {invalid}",
                "valid_sample": sorted(vocab)[:30]}

    if len(data["tldr"].split()) > 20:
        warnings.append(f"TL;DR has {len(data['tldr'].split())} words (max 20)")

    content_hash = indexer.compute_hash(body)
    dup = indexer.check_duplicate(conn, content_hash)
    if dup:
        return {"status": "error", "reason": f"Duplicate detected: {dup}"}

    broken = validator.validate_wikilinks(data.get("related", []), conn,
                                          config.vault_root)
    if broken:
        warnings.append(f"Broken wikilinks: {broken}")

    target = paths.target_path(config.vault_root, data)
    markdown = fsio.format_markdown(data, body)

    lock_file = config.vault_root / ".engram.lock"
    try:
        with locking.vault_lock(lock_file, timeout=config.lock_timeout_seconds):
            fsio.atomic_write(target, markdown)
    except TimeoutError as e:
        return {"status": "error", "reason": str(e)}

    indexer.upsert_note(conn, data, content_hash, str(target), body)
    paths.log_activity(config.activity_log, "save", data["id"],
                       {"type": data["type"], "project": data.get("project")})

    return {"status": "ok", "note_id": data["id"], "path": str(target),
            "warnings": warnings}
