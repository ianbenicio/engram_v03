#!/usr/bin/env python3
"""Migrate v2.2 vault notes to v3.0: backfill confidence field.

Usage: python scripts/migrate_v2_to_v3.py /path/to/vault [--apply]
Default is dry-run (prints what would change). Pass --apply to write.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml


def infer_confidence(fm: dict) -> str:
    ntype = fm.get("type", "")
    status = fm.get("status", "active")
    if status in ("draft", "proposed", "open"):
        return "hypothesis"
    if ntype in ("decision", "bug", "runbook", "session"):
        return "fact"
    if ntype in ("pattern", "concept", "context"):
        return "inference"
    return "hypothesis"


def migrate_note_text(text: str) -> tuple[str, bool]:
    if not text.startswith("---"):
        return text, False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text, False
    fm = yaml.safe_load(parts[1]) or {}
    if fm.get("confidence"):
        return text, False
    fm["confidence"] = infer_confidence(fm)
    new_fm = yaml.dump(fm, default_flow_style=False, allow_unicode=True,
                       sort_keys=False, width=120)
    return f"---\n{new_fm}---{parts[2]}", True


def main():
    if len(sys.argv) < 2:
        print("Usage: migrate_v2_to_v3.py <vault> [--apply]")
        sys.exit(1)
    vault = Path(sys.argv[1])
    apply = "--apply" in sys.argv
    changed = 0
    for md in vault.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        new_text, did = migrate_note_text(text)
        if did:
            changed += 1
            print(f"{'WRITE' if apply else 'DRY'}: {md} -> confidence added")
            if apply:
                md.write_text(new_text, encoding="utf-8")
    print(f"\n{changed} notes {'migrated' if apply else 'would change'}.")


if __name__ == "__main__":
    main()
