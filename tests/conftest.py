import pytest
from pathlib import Path
from engram.config import Config
from engram.core.db import connect, init_schema


@pytest.fixture
def vault(tmp_path) -> Path:
    """Empty vault with meta/tags.md vocabulary."""
    root = tmp_path / "vault"
    (root / "meta").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)
    (root / "meta" / "tags.md").write_text(
        "- tipo/decision\n- tipo/bug\n- tipo/pattern\n- tipo/context\n"
        "- tipo/session\n- maturidade/stable\n- maturidade/draft\n"
        "- maturidade/experimental\n- dominio/backend\n- dominio/frontend\n"
        "- dominio/infra\n- dominio/process\n- dominio/architecture\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def config(vault) -> Config:
    return Config(vault_root=vault)


@pytest.fixture
def db(config):
    conn = connect(config.db_path)
    init_schema(conn)
    yield conn
    conn.close()


class MockOllama:
    """Deterministic fake embeddings + synthesis."""
    def __init__(self, online=True):
        self.online = online

    def embed(self, text: str):
        if not self.online:
            raise RuntimeError("Ollama offline")
        h = sum(ord(c) for c in text)
        return [(h % 100) / 100.0] * 1024

    def synthesize(self, query: str, context: str) -> str:
        if not self.online:
            raise RuntimeError("Ollama offline")
        return f"SYNTH[{query[:20]}]: {len(context)} chars of context."


@pytest.fixture
def mock_ollama():
    return MockOllama(online=True)
