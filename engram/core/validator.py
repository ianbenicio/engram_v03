from __future__ import annotations

import sqlite3
from pathlib import Path

REQUIRED_FIELDS = [
    "id", "title", "tldr", "type", "confidence", "status",
    "created", "updated", "author", "scope", "tags",
]

VALID_LIFECYCLE = {"proposed", "accepted", "superseded", "deprecated"}


def validate_lifecycle(note: dict) -> str | None:
    """ADR lifecycle is only meaningful on decisions and, if present, must be a
    known value. Returns an error string or None."""
    lc = note.get("lifecycle")
    if lc is None:
        return None
    if note.get("type") != "decision":
        return f"lifecycle is only valid on 'decision' notes (got type '{note.get('type')}')"
    if lc not in VALID_LIFECYCLE:
        return f"Invalid lifecycle '{lc}'. Valid: {sorted(VALID_LIFECYCLE)}"
    return None


def load_tags_vocab(vault_root: Path) -> set[str]:
    vocab: set[str] = set()
    tags_path = vault_root / "meta" / "tags.md"
    if tags_path.exists():
        for line in tags_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(("- ", "* ")):
                tag = line[2:].strip().split()[0]
                if "/" in tag:
                    vocab.add(tag)
    return vocab


def validate_required_fields(note: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if not note.get(f)]


def validate_tags(tags: list[str], vocab: set[str]) -> list[str]:
    invalid = []
    for tag in tags:
        if tag.startswith("projeto/"):
            continue
        if tag not in vocab:
            invalid.append(tag)
    return invalid


def validate_tag_prefixes(tags: list[str]) -> list[str]:
    missing = []
    for prefix in ("tipo/", "maturidade/", "dominio/"):
        if not any(t.startswith(prefix) for t in tags):
            missing.append(prefix)
    return missing


def validate_wikilinks(related: list[str], conn: sqlite3.Connection,
                       vault_root: Path) -> list[str]:
    broken = []
    for link in related:
        clean = link.strip("[]").split("|")[0]
        row = conn.execute(
            "SELECT id FROM notes WHERE id = ? OR file_path LIKE ?",
            (clean, f"%/{clean}.md"),
        ).fetchone()
        if row:
            continue
        if (vault_root / f"{clean}.md").exists():
            continue
        found = False
        for d in ("projetos", "global", "sessoes"):
            base = vault_root / d
            if base.exists() and list(base.rglob(f"{clean}.md")):
                found = True
                break
        if not found:
            broken.append(link)
    return broken


def validate_module(module: str | None, project: str | None,
                    vault_root: Path) -> str | None:
    """Check module is declared in project _index.md. Returns a warning
    string if not declared, else None. Missing _index.md or module = no warning."""
    if not module or not project:
        return None
    import yaml
    idx = vault_root / "projetos" / project / "_index.md"
    if not idx.exists():
        return None
    text = idx.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    fm = yaml.safe_load(parts[1]) or {}
    declared = fm.get("modules", [])
    if declared and module not in declared:
        return f"Module '{module}' not in project '{project}' declared modules: {declared}"
    return None
