"""Usage tracking — the LSTM-style 'reinforced retention' signal.

Reads the existing activity.jsonl. Retrieval events (action: "retrieve",
written by the reader) carry the note ids each query returned. A note that is
still being retrieved is *alive* — the GC must not consider it stale, no matter
its age. Memory that is used gets reinforced.

All parsing is defensive: a corrupt line never breaks the stats.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def log_retrieval(activity_log: Path, note_ids: list[str], path: str) -> None:
    """Append one retrieval event (single line for the whole query result)."""
    if not note_ids:
        return
    activity_log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": "retrieve",
        "note_ids": note_ids,
        "path": path,
    }
    with activity_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def access_stats(activity_log: Path) -> dict[str, dict]:
    """Aggregate retrieval events: {note_id: {count, last_access(iso str)}}."""
    stats: dict[str, dict] = {}
    if not activity_log.exists():
        return stats
    for line in activity_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("action") != "retrieve":
            continue
        ts = e.get("ts", "")
        for nid in e.get("note_ids", []):
            s = stats.setdefault(nid, {"count": 0, "last_access": ""})
            s["count"] += 1
            if ts > s["last_access"]:
                s["last_access"] = ts
    return stats


def days_since_access(stats: dict[str, dict], note_id: str) -> float | None:
    """Days since the note was last retrieved; None if never retrieved."""
    s = stats.get(note_id)
    if not s or not s.get("last_access"):
        return None
    try:
        ts = datetime.fromisoformat(s["last_access"])
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0)
