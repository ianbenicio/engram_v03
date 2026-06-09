"""BL-04 retrieval benchmark harness (dev-only).

Seeds an ephemeral vault with known notes, then measures:
- Path A Recall@5 (FTS lightweight)
- Path B Recall@5 (embeddings + KNN) — skipped if Ollama offline
- Router accuracy (deterministic, no LLM)

Run via `engram bench`. Zero external services required for Path A + router;
Path B is reported as skipped when no embedding provider is reachable.
"""
from __future__ import annotations

import sqlite3

from engram.config import Config
from engram.models import NoteData, NoteType, Confidence, QueryRequest
from engram.core import embeddings, router, reader
from engram.core.embeddings import EmbeddingUnavailable
from engram.core.writer import vault_save


# Seed notes: explicit ids so the dataset can reference them directly.
_SEED = [
    ("redis", "Redis caching", "Use Redis for the caching layer",
     "We chose Redis for low-latency caching of hot keys."),
    ("jwt", "JWT authentication", "JWT tokens for auth",
     "Authentication uses short-lived JWT access tokens plus refresh tokens."),
    ("docker", "Docker setup", "Docker compose for local dev",
     "Local development runs via docker compose with hot reload."),
    ("ratelimit", "Rate limiting", "Sliding-window rate limiter",
     "API rate limiting uses an in-memory sliding window of 30 calls per minute."),
]

# Each: (query, expected_note_id, expected_route)
BENCH_DATASET = [
    ("redis caching layer", "redis", "lightweight"),
    ("jwt access tokens", "jwt", "lightweight"),
    ("docker compose local", "docker", "lightweight"),
    ("sliding window rate limiter", "ratelimit", "lightweight"),
    ("why did we choose redis", "redis", "heavy"),          # semantic: "why did"
    ("compare jwt and docker auth", "jwt", "heavy"),         # semantic: "compare"
]


def seed_bench_vault(config: Config, conn: sqlite3.Connection) -> None:
    for nid, title, tldr, body in _SEED:
        note = NoteData(
            id=nid, title=title, tldr=tldr, type=NoteType.DECISION,
            confidence=Confidence.FACT, scope="project", project="bench",
            tags=["tipo/decision", "maturidade/stable", "dominio/backend"],
        )
        vault_save(note, body, config, conn)


def _embeddings_available(config: Config) -> bool:
    try:
        embeddings.get_embedding("probe", config)
        return True
    except EmbeddingUnavailable:
        return False


def run_bench(config: Config, conn: sqlite3.Connection) -> dict:
    seed_bench_vault(config, conn)
    total = len(BENCH_DATASET)

    # Path A recall is measured only over the queries Path A is designed for
    # (lightweight/keyword). Semantic queries (heavy) deliberately fail FTS's
    # implicit-AND and are Path B's job; including them here would conflate
    # "Path A is weak on semantic" with "retrieval is broken".
    a_hits = a_total = 0
    route_hits = 0
    for query, expect_id, expect_route in BENCH_DATASET:
        if expect_route == "lightweight":
            a_total += 1
            res_a = reader.path_a(QueryRequest(text=query, limit=5), conn, config)
            if expect_id in {r["id"] for r in res_a["results"]}:
                a_hits += 1
        if router.route_query(QueryRequest(text=query), conn) == expect_route:
            route_hits += 1

    result = {
        "total_queries": total,
        "path_a_recall_at_5": round(a_hits / a_total, 3) if a_total else None,
        "path_a_queries": a_total,
        "router_accuracy": round(route_hits / total, 3),
        "path_b_recall_at_5": None,
        "path_b_status": "skipped (Ollama offline)",
    }

    if _embeddings_available(config):
        b_hits = 0
        for query, expect_id, _ in BENCH_DATASET:
            res_b = reader.path_b(QueryRequest(text=query, limit=5), conn, config)
            ids = {s["id"] for s in res_b.get("sources", [])}
            if expect_id in ids:
                b_hits += 1
        result["path_b_recall_at_5"] = round(b_hits / total, 3)
        result["path_b_status"] = "ok"

    return result
