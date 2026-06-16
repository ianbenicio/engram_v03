from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# PARA buckets within each project (Projects = time-bound, Areas = ongoing,
# Resources = permanent knowledge). Each maps type -> "{PARA}/{type-folder}".
# NOTE: "session" has a location override in target_path() (vault-root
# `sessoes/`), but its entry here is still used — moc.py derives the PARA
# bucket per type from this mapping (single source of truth).
# Archive is reserved for the deferred cold-storage tier.
TYPE_FOLDERS = {
    # Resources/ — permanent knowledge
    "decision": "Resources/decisoes",
    "pattern": "Resources/patterns",
    "concept": "Resources/concepts",
    # Areas/ — ongoing
    "context": "Areas/context",
    "runbook": "Areas/runbooks",
    "refactoring": "Areas/refactoring",
    "metric": "Areas/metrics",
    # Projects/ — time-bound
    "bug": "Projects/bugs",
    "post-mortem": "Projects/post-mortems",
    "experiment": "Projects/experiments",
    "session": "Projects/sessoes",
}


def target_path(vault_root: Path, note: dict) -> Path:
    ntype = note["type"]
    scope = note.get("scope", "project")
    project = note.get("project")
    slug = note.get("id", "unknown")
    folder = TYPE_FOLDERS.get(ntype, ntype)

    if ntype == "session":
        return vault_root / "sessoes" / f"handoff-{slug}.md"
    if scope in ("cross", "global") or not project:
        return vault_root / "global" / folder / f"{slug}.md"
    return vault_root / "projetos" / project / folder / f"{slug}.md"


def log_activity(activity_log: Path, action: str, note_id: str,
                 details: dict) -> None:
    activity_log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "note_id": note_id,
        **details,
    }
    with activity_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
