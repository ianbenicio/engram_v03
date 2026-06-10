from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml

from engram.config import Config
from engram.models import NoteData
from engram.core import indexer, validator, fsio, paths, locking
from engram.core import embeddings, manifest, naming


def vault_save(note: NoteData, body: str, config: Config,
               conn: sqlite3.Connection) -> dict:
    data = note.model_dump(mode="json", exclude_none=False)
    warnings: list[str] = []
    project = data.get("project")

    if not data.get("id"):
        # Readable slug id: doubles as filename + wikilink target, so it must
        # be human-readable in Obsidian's graph (not an opaque ULID).
        data["id"] = naming.unique_id(data.get("title", ""), body, conn)
    now = datetime.now(timezone.utc).isoformat()
    data["created"] = data.get("created") or now
    data["updated"] = now

    # Manifest directive: default_confidentiality (apply if note left the default)
    if data.get("confidentiality", "internal") == "internal":
        mdc = manifest.default_confidentiality(config.vault_root, project)
        if mdc:
            data["confidentiality"] = mdc

    # Manifest directive: enabled_types (per-project override of global config)
    eff_types = manifest.enabled_types(config.vault_root, project,
                                       config.enabled_types)
    if data["type"] not in eff_types:
        return {"status": "error",
                "reason": f"Type '{data['type']}' not enabled for project "
                          f"'{project}' (enabled: {eff_types})"}

    missing = validator.validate_required_fields(data)
    if missing:
        return {"status": "error", "reason": f"Missing required fields: {missing}"}

    missing_prefix = validator.validate_tag_prefixes(data["tags"])
    if missing_prefix:
        return {"status": "error",
                "reason": f"Missing required tag prefix: {missing_prefix}"}

    # Manifest directive: domains[] extend the dominio/ tag vocabulary
    vocab = validator.load_tags_vocab(config.vault_root)
    for dom in manifest.domains(config.vault_root, project):
        vocab.add(f"dominio/{dom}")
    invalid = validator.validate_tags(data["tags"], vocab)
    if invalid:
        return {"status": "error", "reason": f"Invalid tags: {invalid}",
                "valid_sample": sorted(vocab)[:30]}

    mod_warn = validator.validate_module(data.get("module"), data.get("project"),
                                         config.vault_root)
    if mod_warn:
        warnings.append(mod_warn)

    if len(data["tldr"].split()) > 20:
        warnings.append(f"TL;DR has {len(data['tldr'].split())} words (max 20)")

    lc_err = validator.validate_lifecycle(data)
    if lc_err:
        return {"status": "error", "reason": lc_err}

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
    embeddings.embed_and_store(conn, data["id"], f"{data['title']}\n{data['tldr']}\n{body}", config)
    paths.log_activity(config.activity_log, "save", data["id"],
                       {"type": data["type"], "project": data.get("project")})

    return {"status": "ok", "note_id": data["id"], "path": str(target),
            "warnings": warnings}


IMMUTABLE_FIELDS = {"id", "created", "type", "subtype", "parent"}


def vault_update(note_id: str, updates: dict, body: str | None,
                 config: Config, conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT file_path, content_hash FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if not row:
        return {"status": "error", "reason": f"Note {note_id} not found in index"}
    file_path = Path(row[0])
    if not file_path.exists():
        return {"status": "error", "reason": f"Note file not found: {file_path}"}

    blocked = [k for k in updates if k in IMMUTABLE_FIELDS]
    if blocked:
        return {"status": "error", "reason": f"Cannot modify immutable fields: {blocked}"}

    text = file_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
        existing_body = parts[2].strip() if len(parts) >= 3 else text
    else:
        fm, existing_body = {}, text

    warnings: list[str] = []
    changes = []
    for key, value in updates.items():
        if fm.get(key) != value:
            changes.append(f"{key}: {fm.get(key)} -> {value}")
            fm[key] = value
    fm["updated"] = datetime.now(timezone.utc).isoformat()

    new_body = body if body is not None else existing_body

    if "tags" in updates:
        vocab = validator.load_tags_vocab(config.vault_root)
        inv = validator.validate_tags(updates["tags"], vocab)
        if inv:
            return {"status": "error", "reason": f"Invalid tags: {inv}"}

    content_hash = indexer.compute_hash(new_body) if body is not None else row[1]

    if "related" in updates:
        broken = validator.validate_wikilinks(updates["related"], conn,
                                              config.vault_root)
        if broken:
            warnings.append(f"Broken wikilinks: {broken}")

    markdown = fsio.format_markdown(fm, new_body)
    lock_file = config.vault_root / ".engram.lock"
    try:
        with locking.vault_lock(lock_file, timeout=config.lock_timeout_seconds):
            fsio.atomic_write(file_path, markdown)
    except TimeoutError as e:
        return {"status": "error", "reason": str(e)}

    indexer.upsert_note(conn, fm, content_hash, str(file_path), new_body)
    embeddings.embed_and_store(conn, note_id, f"{fm.get('title','')}\n{fm.get('tldr','')}\n{new_body}", config)
    paths.log_activity(config.activity_log, "update", note_id,
                       {"changes": changes, "body_changed": body is not None})

    if not changes and body is None:
        warnings.append("No changes detected")
    return {"status": "ok", "note_id": note_id, "path": str(file_path),
            "changes": changes, "warnings": warnings}
