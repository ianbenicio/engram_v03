#!/usr/bin/env python3
"""SessionStart hook — inject the active project's handoff and, only when
something is wrong, one Engram health line as additionalContext."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from engram.config import Config, load_config
from engram.core.handoff import find_latest_handoff


def _handoff_context(config: Config, project: str | None) -> str | None:
    # Without a project the latest handoff is from whatever project ran last;
    # find_latest_handoff also falls back to it when nothing matches.
    if not project:
        return None
    latest = find_latest_handoff(config.vault_root, project)
    if not latest:
        return None
    body = latest.read_text(encoding="utf-8")
    if f"project: {project}" not in body:
        return None
    return f"[ENGRAM HANDOFF — resume from previous session]\n\n{body}"


def _health_context(config: Config, timeout: float = 0.8) -> str | None:
    # Any failure of the checker itself stays silent: it must never get in
    # the way of starting a session.
    try:
        from engram.core.db import connect
        from engram.core.health import check_health, health_line
        if not config.db_path.exists():
            return None
        conn = connect(config.db_path)
        try:
            problems = check_health(conn, config, timeout)
        finally:
            conn.close()
        return health_line(problems) if problems else None
    except Exception:
        return None


def build_context(config: Config, project: str | None) -> str | None:
    parts = [p for p in (_handoff_context(config, project),
                         _health_context(config)) if p]
    return "\n\n".join(parts) or None


def main():
    # A SessionStart hook must never abort session start. Any failure
    # degrades to an empty no-op response.
    try:
        flag = Path(tempfile.gettempdir()) / "engram_ctx_flag"
        try:
            flag.write_text(json.dumps({"tokens": 0, "pct": 0.0, "threshold": "normal"}))
        except OSError:
            pass

        context = build_context(load_config(),
                                os.environ.get("ENGRAM_ACTIVE_PROJECT"))
        if not context:
            print(json.dumps({}))
            return
        # Claude Code only reads additionalContext inside hookSpecificOutput;
        # a top-level key is silently ignored.
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": context}}))
    except Exception:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
