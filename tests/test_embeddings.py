import httpx
import pytest
from engram.core.embeddings import get_embedding, EmbeddingUnavailable

def test_get_embedding_success(monkeypatch, config):
    def fake_post(url, json, timeout):
        class R:
            status_code = 200
            def json(self): return {"embedding": [0.1] * 1024}
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)
    assert len(get_embedding("hello", config)) == 1024

def test_get_embedding_offline_raises(monkeypatch, config):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(EmbeddingUnavailable):
        get_embedding("hello", config)
