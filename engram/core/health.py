"""Cheap Engram health check (no LLM) for the SessionStart hook.

Reports only problems, so a healthy vault costs zero context tokens.
"""
from __future__ import annotations

import sqlite3

import httpx

from engram.config import Config
from engram.core.embeddings import _error_detail

_MISSING_EMBEDDINGS_SQL = (
    "SELECT COUNT(*) FROM notes WHERE status NOT IN ('archived','draft') "
    "AND id NOT IN (SELECT note_id FROM notes_vec)")


def count_missing_embeddings(conn: sqlite3.Connection) -> int:
    """Active notes with no stored vector (invisible to semantic search)."""
    return conn.execute(_MISSING_EMBEDDINGS_SQL).fetchone()[0]


def check_ollama(config: Config, timeout: float = 0.8) -> str | None:
    """Probe the embedding endpoint. A read timeout is not a problem: a cold
    bge-m3 load takes ~5s (and Ollama cancels it when we hang up). A connect
    timeout is: a listening local Ollama accepts in milliseconds, while a
    refused port on Windows only fails after ~2s of SYN retries."""
    try:
        resp = httpx.post(
            f"{config.ollama_endpoint}/api/embed",
            json={"model": config.embed_model, "input": "ping",
                  "truncate": True, "keep_alive": config.keep_alive},
            timeout=httpx.Timeout(timeout, connect=0.5),
        )
    except httpx.ReadTimeout:
        return None
    except httpx.HTTPError as e:
        return (f"Ollama não responde em {config.ollama_endpoint} "
                f"({type(e).__name__})")
    if resp.status_code != 200:
        detail = _error_detail(resp)[:120]
        return f"embedding falha no Ollama (HTTP {resp.status_code}: {detail})"
    return None


def check_health(conn: sqlite3.Connection, config: Config,
                 timeout: float = 0.8) -> list[str]:
    """List of problems; empty means healthy."""
    problems = []
    ollama = check_ollama(config, timeout)
    if ollama:
        problems.append(ollama)
    missing = count_missing_embeddings(conn)
    if missing:
        problems.append(f"{missing} nota(s) ativa(s) sem vetor — rode "
                        "`python -m engram.cli reindex`")
    return problems


def health_line(problems: list[str]) -> str:
    return ("[ENGRAM SAÚDE] " + "; ".join(problems)
            + ". A busca semântica cai no FTS até corrigir.")
