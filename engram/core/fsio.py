from __future__ import annotations

import os
import time
from pathlib import Path

import yaml

FRONTMATTER_ORDER = [
    "id", "title", "tldr", "type", "subtype", "parent", "confidence",
    "scope", "project", "module", "status", "created", "updated", "author",
    "tags", "related", "implements", "supersedes", "code_refs",
    "session_id", "confidentiality", "schema_version",
]


def atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)  # atomic on Windows + POSIX


def format_markdown(note: dict, body: str) -> str:
    fm = {}
    for key in FRONTMATTER_ORDER:
        val = note.get(key)
        if val is not None:
            fm[key] = val
    yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True,
                         sort_keys=False, width=120)
    return f"---\n{yaml_str}---\n\n{body}\n"


def cleanup_stale_tmp(root: Path, max_age_seconds: int = 60) -> int:
    removed = 0
    now = time.time()
    for tmp in root.rglob("*.tmp"):
        try:
            if now - tmp.stat().st_mtime > max_age_seconds:
                tmp.unlink()
                removed += 1
        except OSError:
            pass
    return removed
