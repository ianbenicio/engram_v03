from __future__ import annotations

import httpx

from engram.config import Config


class EmbeddingUnavailable(RuntimeError):
    pass


def get_embedding(text: str, config: Config) -> list[float]:
    try:
        resp = httpx.post(
            f"{config.ollama_endpoint}/api/embeddings",
            json={"model": config.embed_model, "prompt": text},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()["embedding"]
        raise EmbeddingUnavailable(f"Ollama status {resp.status_code}")
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise EmbeddingUnavailable(str(e)) from e


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
                  "stream": False, "options": {"num_predict": 600}},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()["response"]
        raise EmbeddingUnavailable(f"Ollama status {resp.status_code}")
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise EmbeddingUnavailable(str(e)) from e
