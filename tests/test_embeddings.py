import httpx
import pytest
from engram.core.embeddings import get_embedding, synthesize, EmbeddingUnavailable

def test_get_embedding_success(monkeypatch, config):
    def fake_post(url, json, timeout):
        class R:
            status_code = 200
            def json(self): return {"embedding": [0.1] * 1024}
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)
    assert len(get_embedding("hello", config)) == 1024

def test_get_embedding_sends_keep_alive(monkeypatch, config):
    captured = {}
    def fake_post(url, json, timeout):
        captured.update(json=json, timeout=timeout)
        class R:
            status_code = 200
            def json(self): return {"embedding": [0.1] * 1024}
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
