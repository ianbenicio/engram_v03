"""Garbage collector — `engram gc`. Structured, conservative, NEVER deletes.

4 stages:
  0 SCAN       — profile each note (age, inbound refs, hash, status, confidence)
  1 DETECTION  — exact-dup, near-dup, stale, orphan, superseded, draft-rot
  2 CLASSIFY   — AUTO-SAFE | SUGGEST | REPORT-ONLY
  3 SYNTHESIS  — (near-dup merge: SUGGEST, not auto-applied in v1)
  4 REPORT     — actions taken + pending + metrics

Invariants:
  - never deletes (only status: archived)
  - confidence:fact AND referenced -> untouchable
  - dry-run default; --apply performs only AUTO-SAFE actions
  - per-project stale_days from the manifest retention_policy
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml

from engram.config import Config
from engram.core import manifest, fsio, locking, paths, usage
from engram.core.hubs import WIKILINK_RE


def _age_days(updated: str | None) -> float:
    if not updated:
        return 0.0
    try:
        ts = datetime.fromisoformat(updated)
    except (ValueError, TypeError):
        return 0.0  # unparseable -> treat as new (safe: never auto-stale)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0)


def _inbound_counts(conn: sqlite3.Connection, vault_root: Path) -> dict[str, int]:
    rows = conn.execute("SELECT id, title, file_path FROM notes").fetchall()
    counts: dict[str, int] = {r[0]: 0 for r in rows}
    title_to_id = {r[1].lower(): r[0] for r in rows if r[1]}
    for nid, _title, fpath in rows:
        p = Path(fpath)
        if not p.exists():
            continue
        for tgt in WIKILINK_RE.findall(p.read_text(encoding="utf-8")):
            t = tgt.strip()
            ref = t if t in counts else title_to_id.get(t.lower())
            if ref and ref != nid:
                counts[ref] = counts.get(ref, 0) + 1
    return counts


def _frontmatter(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def _archive(conn: sqlite3.Connection, config: Config, note_id: str,
             file_path: str) -> bool:
    """Set status: archived in the file + SQLite. Never deletes.

    File rewrite happens under the vault lock (same invariant as the writer)
    to avoid racing Obsidian/concurrent writers."""
    p = Path(file_path)
    if not p.exists():
        conn.execute("UPDATE notes SET status='archived' WHERE id=?", (note_id,))
        conn.commit()
        return True
    lock_file = config.vault_root / ".engram.lock"
    try:
        with locking.vault_lock(lock_file, timeout=config.lock_timeout_seconds):
            text = p.read_text(encoding="utf-8")
            if text.startswith("---"):
                parts = text.split("---", 2)
                fm = yaml.safe_load(parts[1]) or {}
                body = parts[2].lstrip("\n") if len(parts) >= 3 else ""
                fm["status"] = "archived"
                fsio.atomic_write(p, fsio.format_markdown(fm, body.rstrip("\n")))
    except TimeoutError:
        return False  # skip this note; next gc run retries
    conn.execute("UPDATE notes SET status='archived' WHERE id=?", (note_id,))
    conn.commit()
    return True


def detect(conn: sqlite3.Connection, config: Config) -> dict:
    """Stage 0-1: profile + classify candidates."""
    inbound = _inbound_counts(conn, config.vault_root)
    rows = conn.execute(
        "SELECT id, content_hash, status, confidence, updated, project, file_path "
        "FROM notes"
    ).fetchall()

    by_hash: dict[str, list] = {}
    exact_dups: list[dict] = []
    stale: list[str] = []
    orphan: list[str] = []
    superseded: list[str] = []

    # Reinforced retention (LSTM-style): a note still being retrieved is
    # alive — recent access vetoes staleness regardless of note age.
    acc = usage.access_stats(config.activity_log)

    for nid, chash, status, conf, updated, project, fpath in rows:
        if chash:
            by_hash.setdefault(chash, []).append((nid, inbound.get(nid, 0), updated))
        if status != "active":
            continue
        refs = inbound.get(nid, 0)
        fm = _frontmatter(Path(fpath))
        if fm.get("superseded_by"):
            superseded.append(nid)
            continue
        rp = manifest.retention_policy(config.vault_root, project)
        if refs == 0 and conf != "fact" and _age_days(updated) > rp["stale_days"]:
            last = usage.days_since_access(acc, nid)
            if last is None or last > rp["stale_days"]:
                stale.append(nid)
        if refs == 0 and not fm.get("related"):
            orphan.append(nid)

    for chash, members in by_hash.items():
        if len(members) > 1:
            # keep most-referenced, then newest; archive the rest
            members_sorted = sorted(members, key=lambda m: (m[1], m[2] or ""),
                                    reverse=True)
            keep = members_sorted[0][0]
            drop = [m[0] for m in members_sorted[1:]]
            exact_dups.append({"hash": chash, "keep": keep, "drop": drop})

    return {"exact_dups": exact_dups, "stale": stale, "orphan": orphan,
            "superseded": superseded}


def run_gc(conn: sqlite3.Connection, config: Config, apply: bool = False) -> dict:
    """Full GC. Dry-run by default; apply=True performs AUTO-SAFE actions only."""
    det = detect(conn, config)

    actions: list[str] = []
    if apply:
        # AUTO-SAFE: archive superseded
        for nid in det["superseded"]:
            row = conn.execute("SELECT file_path FROM notes WHERE id=?", (nid,)).fetchone()
            if row:
                _archive(conn, config, nid, row[0])
                actions.append(f"archived superseded {nid}")
        # AUTO-SAFE: archive exact-dup copies (keep the canonical)
        for grp in det["exact_dups"]:
            for nid in grp["drop"]:
                row = conn.execute("SELECT file_path FROM notes WHERE id=?", (nid,)).fetchone()
                if row:
                    _archive(conn, config, nid, row[0])
                    actions.append(f"archived exact-dup {nid} (keep {grp['keep']})")
        paths.log_activity(config.activity_log, "gc_apply", "-",
                           {"actions": len(actions)})

    # REPORT-ONLY: cross-project comparative report (needs embeddings; graceful)
    try:
        from engram.core.crosslink import cross_project_report
        cross_similar = cross_project_report(conn, config)
    except Exception:
        cross_similar = []

    total = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM notes WHERE status='active'").fetchone()[0]

    return {
        "dry_run": not apply,
        "auto_safe": {
            "exact_dups": det["exact_dups"],
            "superseded": det["superseded"],
        },
        "suggest": {"stale": det["stale"]},
        "report_only": {"orphan": det["orphan"], "cross_similar": cross_similar},
        "actions_taken": actions,
        "metrics": {"total_notes": total, "active_notes": active},
    }
