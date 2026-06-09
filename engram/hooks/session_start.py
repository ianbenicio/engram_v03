#!/usr/bin/env python3
"""SessionStart hook — inject latest handoff as additionalContext."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from engram.config import load_config
from engram.core.handoff import find_latest_handoff


def main():
    # A SessionStart hook must never abort session start. Any failure
    # degrades to an empty no-op response.
    try:
        flag = Path(tempfile.gettempdir()) / "engram_ctx_flag"
        try:
            flag.write_text(json.dumps({"tokens": 0, "pct": 0.0, "threshold": "normal"}))
        except OSError:
            pass

        config = load_config()
        project = os.environ.get("ENGRAM_ACTIVE_PROJECT")
        latest = find_latest_handoff(config.vault_root, project)
        if not latest:
            print(json.dumps({}))
            return
        body = latest.read_text(encoding="utf-8")
        print(json.dumps({"additionalContext":
              f"[ENGRAM HANDOFF — resume from previous session]\n\n{body}"}))
    except Exception:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
