import httpx
import pytest
from engram.core.embeddings import get_embedding, synthesize, EmbeddingUnavailable

def test_get_embedding_success(monkeypatch, config):
    def fake_post(url, json, timeout):
        class R:
            status_code = 200
            def json(self): return {"embeddings": [[0.1] * 1024]}
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)
    assert len(get_embedding("hello", config)) == 1024

def test_get_embedding_sends_keep_alive(monkeypatch, config):
    captured = {}
    def fake_post(url, json, timeout):
        captured.update(json=json, timeout=timeout)
        class R:
            status_code = 200
            def json(self): return {"embeddings": [[0.1] * 1024]}
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)
    get_embedding("hello", config)
    assert captured["json"]["keep_alive"] == config.keep_alive

def test_synthesize_uses_config_timeout_and_keep_alive(monkeypatch, config):
    captured = {}
    def fake_post(url, json, timeout):
        captured.update(json=json, timeout=timeout)
        class R:
            status_code = 200
            def json(self): return {"response": "ok"}
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)
    assert synthesize("q", "ctx", config) == "ok"
    assert captured["timeout"] == config.synth_timeout_seconds
    assert captured["json"]["keep_alive"] == config.keep_alive

def test_get_embedding_offline_raises(monkeypatch, config):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(EmbeddingUnavailable):
        get_embedding("hello", config)

def test_get_embedding_uses_embed_endpoint_with_truncate(monkeypatch, config):
    # /api/embed truncates long notes; legacy /api/embeddings returned HTTP 500
    # ("input length exceeds the context length") and the note was never embedded.
    captured = {}
    def fake_post(url, json, timeout):
        captured.update(url=url, json=json)
        class R:
            status_code = 200
            def json(self): return {"embeddings": [[0.1] * 1024]}
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)
    get_embedding("hello", config)
    assert captured["url"].endswith("/api/embed")
    assert captured["json"]["input"] == "hello"
    assert captured["json"]["truncate"] is True

def test_get_embedding_error_carries_ollama_message(monkeypatch, config):
    # A crashed runner answers HTTP 500 with the cause in the body; the cause
    # must reach the caller instead of a bare status code.
    def fake_post(url, json, timeout):
        class R:
            status_code = 500
            def json(self): return {"error": "llama-server process has terminated"}
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(EmbeddingUnavailable,
                       match="500: llama-server process has terminated"):
        get_embedding("hello", config)

def test_get_embedding_other_http_errors_raise_unavailable(monkeypatch, config):
    def fake_post(url, json, timeout):
        raise httpx.RemoteProtocolError("server disconnected")
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(EmbeddingUnavailable):
        get_embedding("hello", config)
