from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ulid import ULID

from engram.config import Config
from engram.core import indexer, fsio, paths


def vault_handoff(state: dict, config: Config,
                  conn: sqlite3.Connection) -> dict:
    note_id = str(ULID())
    now = datetime.now(timezone.utc).isoformat()
    project = state.get("project")

    body_lines = ["# Session Handoff", "", "## Open Decisions"]
    body_lines += [f"- {d}" for d in state.get("decisions", [])] or ["- (none)"]
    body_lines += ["", "## Active Files"]
    body_lines += [f"- {f}" for f in state.get("files", [])] or ["- (none)"]
    body_lines += ["", "## Next Steps"]
    body_lines += [f"- {s}" for s in state.get("next_steps", [])] or ["- (none)"]
    body_lines += ["", f"## Git Branch\n{state.get('branch', 'unknown')}"]
    body = "\n".join(body_lines)

    note = {
        "id": note_id, "title": f"Handoff {now[:16]}",
        "tldr": f"Session handoff for {project or 'global'}",
        "type": "session", "confidence": "fact", "scope": "project",
        "project": project, "status": "active", "created": now,
        "updated": now, "author": "claude",
        "tags": ["tipo/session", "maturidade/stable", "dominio/process"],
        "confidentiality": "internal", "schema_version": 1,
        "session_id": note_id,
    }
    target = paths.target_path(config.vault_root, note)
    fsio.atomic_write(target, fsio.format_markdown(note, body))
    indexer.upsert_note(conn, note, indexer.compute_hash(body), str(target), body)
    paths.log_activity(config.activity_log, "handoff", note_id,
                       {"project": project})
    return {"status": "ok", "note_id": note_id, "path": str(target)}


def find_latest_handoff(vault_root: Path, project: str | None = None) -> Path | None:
    sessions = vault_root / "sessoes"
    if not sessions.exists():
        return None
    handoffs = sorted(sessions.glob("handoff-*.md"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    if not handoffs:
        return None
    if not project:
        return handoffs[0]
    for h in handoffs:
        if f"project: {project}" in h.read_text(encoding="utf-8"):
            return h
    return handoffs[0]
