#!/usr/bin/env python3
"""PreToolUse hook — context monitor. Reads {"tool_name","tool_input"} on stdin."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

FLAG_FILE = Path(tempfile.gettempdir()) / "engram_ctx_flag"
MODEL_LIMIT = 200_000
WARN_PCT = 35
CRIT_PCT = 50


def estimate_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return len(text) // 4


def compute_flag(prev_tokens: int, increment: int, limit: int) -> dict:
    tokens = prev_tokens + increment
    pct = tokens / limit * 100
    threshold = "normal" if pct < WARN_PCT else "warning" if pct < CRIT_PCT else "critical"
    return {"tokens": tokens, "pct": round(pct, 1), "threshold": threshold}


def main():
    # A context-monitor hook must NEVER block a tool call. Any failure
    # (malformed stdin, fs error, etc.) degrades to an empty no-op response.
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict):
            data = {}
        prev = 0
        if FLAG_FILE.exists():
            try:
                prev = json.loads(FLAG_FILE.read_text()).get("tokens", 0)
            except Exception:
                prev = 0
        inc = estimate_tokens(json.dumps(data.get("tool_input", {})))
        flag = compute_flag(prev, inc, MODEL_LIMIT)
        try:
            FLAG_FILE.write_text(json.dumps(flag))
        except OSError:
            pass
        pct = flag["pct"]
        if flag["threshold"] == "critical":
            print(json.dumps({"additionalContext":
                  f"[CONTEXT CRITICAL: {pct:.0f}%] Initiate handoff NOW via vault.handoff()."}))
        elif flag["threshold"] == "warning":
            print(json.dumps({"additionalContext":
                  f"[CONTEXT WARNING: {pct:.0f}%] Be concise; prepare handoff."}))
        else:
            print(json.dumps({}))
    except Exception:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
