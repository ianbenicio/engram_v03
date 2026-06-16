from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from engram.config import load_config
from engram.core.db import connect, init_schema
from engram.core.rate_limit import RateLimiter
from engram.core import reader, router, hubs, handoff
from engram.core.writer import vault_save, vault_update
from engram.models import NoteData, QueryRequest

# Lazy globals: config/DB are initialized on first tool use (not at import),
# so editing engram.toml takes effect on the next server start without
# import-time side effects, and importing this module stays cheap.
_CONFIG = None
_CONN = None
_RATE = RateLimiter()

mcp = FastMCP("Engram")


def _ensure() -> None:
    """Initialize config/conn on first use. No-op if already set (tests
    inject _CONFIG/_CONN directly)."""
    global _CONFIG, _CONN, _RATE
    if _CONFIG is None:
        _CONFIG = load_config()
        _RATE = RateLimiter(_CONFIG.rate_calls, _CONFIG.rate_window_seconds)
    if _CONN is None:
        _CONN = connect(_CONFIG.db_path)
        init_schema(_CONN)


def _rl(tool: str) -> dict | None:
    _ensure()
    if not _RATE.allow(tool):
        return {"status": "error", "reason": f"Rate limit exceeded for {tool}"}
    return None


def _save_impl(note: NoteData, body: str) -> dict:
    blocked = _rl("vault.save")
    return blocked or vault_save(note, body, _CONFIG, _CONN)


def _update_impl(note_id: str, updates: dict, body: str | None) -> dict:
    blocked = _rl("vault.update")
    return blocked or vault_update(note_id, updates, body, _CONFIG, _CONN)


def _query_impl(query: dict) -> dict:
    blocked = _rl("vault.query")
    if blocked:
        return blocked
    q = QueryRequest(**query)
    if router.route_query(q, _CONN) == "heavy":
        return reader.path_b(q, _CONN, _CONFIG)
    return reader.path_a(q, _CONN, _CONFIG)


def _deep_query_impl(query: dict) -> dict:
    blocked = _rl("vault.deep_query")
    if blocked:
        return blocked
    q = QueryRequest(**{**query, "depth": "deep"})
    return reader.path_b(q, _CONN, _CONFIG)


def _status_impl() -> dict:
    blocked = _rl("vault.status")
    if blocked:
        return blocked
    st = hubs.vault_status(_CONN, _CONFIG.activity_log)
    st["hubs"] = hubs.hub_notes(_CONN, _CONFIG.vault_root, top=5)
    return st


def _handoff_impl(state: dict) -> dict:
    blocked = _rl("vault.handoff")
    return blocked or handoff.vault_handoff(state, _CONFIG, _CONN)


@mcp.tool()
def vault_save_tool(note: NoteData, body: str) -> dict:
    """Save a new note to the vault."""
    return _save_impl(note, body)


@mcp.tool()
def vault_update_tool(note_id: str, updates: dict, body: str | None = None) -> dict:
    """Partially update an existing note."""
    return _update_impl(note_id, updates, body)


@mcp.tool()
def vault_query_tool(query: QueryRequest) -> dict:
    """Query the vault (router auto-selects lightweight vs heavy).

    Fields: text (required), project, projects, tags, type_filter,
    status_filter, depth ('deep' forces semantic), limit (default 10)."""
    return _query_impl(query.model_dump(exclude_none=True))


@mcp.tool()
def vault_deep_query_tool(query: QueryRequest) -> dict:
    """Force a heavy semantic query (embeddings + synthesis).

    Fields: text (required), project, projects, limit (default 10)."""
    return _deep_query_impl(query.model_dump(exclude_none=True))


@mcp.tool()
def vault_status_tool() -> dict:
    """Return vault statistics and hub notes."""
    return _status_impl()


@mcp.tool()
def vault_handoff_tool(state: dict) -> dict:
    """Save session state as a handoff note."""
    return _handoff_impl(state)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
