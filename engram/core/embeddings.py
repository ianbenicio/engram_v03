from __future__ import annotations

import httpx

from engram.config import Config


class EmbeddingUnavailable(RuntimeError):
    pass


def _error_detail(resp) -> str:
    """Ollama's error message from a non-200 response, so callers can surface
    the real cause (e.g. a crashed runner) instead of a bare status code."""
    try:
        return str(resp.json().get("error", ""))[:300]
    except ValueError:
        return ""


def get_embedding(text: str, config: Config) -> list[float]:
    # /api/embed (not the legacy /api/embeddings): truncates input to the
    # model context instead of failing with HTTP 500 on long notes, and
    # returns L2-normalized vectors.
    try:
        resp = httpx.post(
            f"{config.ollama_endpoint}/api/embed",
            json={"model": config.embed_model, "input": text,
                  "truncate": True, "keep_alive": config.keep_alive},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()["embeddings"][0]
        raise EmbeddingUnavailable(
            f"Ollama status {resp.status_code}: {_error_detail(resp)}")
    except httpx.HTTPError as e:
        raise EmbeddingUnavailable(str(e)) from e


def embed_and_store(conn, note_id: str, text: str, config: Config) -> bool:
    """Generate + store an embedding for a note. Returns True if stored,
    False if Ollama is offline (graceful skip — never raises)."""
    from sqlite_vec import serialize_float32
    try:
        vec = get_embedding(text, config)
    except EmbeddingUnavailable:
        return False
    conn.execute("DELETE FROM notes_vec WHERE note_id = ?", (note_id,))
    conn.execute(
        "INSERT INTO notes_vec(note_id, embedding) VALUES (?, ?)",
        (note_id, serialize_float32(vec)),
    )
    conn.commit()
    return True


def synthesize(query: str, context: str, config: Config) -> str:
    prompt = (
        "Synthesize the project notes to answer the query. Be concise (~400 "
        "words). Focus on decisions, rationale, status. Note each source's "
        "confidence (fact/inference/hypothesis). If notes conflict, mention "
        "both with dates.\n\nSintetize as notas para responder a query. Seja "
        "conciso (~400 palavras). Responda no mesmo idioma da query.\n\n"
        f"Query: {query}\n\nNotes:\n{context}\n\nSynthesis:"
    )
    try:
        resp = httpx.post(
            f"{config.ollama_endpoint}/api/generate",
            json={"model": config.synth_model, "prompt": prompt,
                  "stream": False, "keep_alive": config.keep_alive,
                  "options": {"num_predict": 600}},
            timeout=config.synth_timeout_seconds,
        )
        if resp.status_code == 200:
            return resp.json()["response"]
        raise EmbeddingUnavailable(
            f"Ollama status {resp.status_code}: {_error_detail(resp)}")
    except httpx.HTTPError as e:
        raise EmbeddingUnavailable(str(e)) from e
