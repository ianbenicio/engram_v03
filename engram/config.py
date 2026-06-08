from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_ENABLED_TYPES = [
    "decision", "bug", "pattern", "context", "runbook", "session", "concept",
]
ALL_TYPES = DEFAULT_ENABLED_TYPES + ["post-mortem", "experiment", "refactoring", "metric"]


@dataclass
class Config:
    vault_root: Path
    enabled_types: list[str] = field(default_factory=lambda: list(DEFAULT_ENABLED_TYPES))
    ollama_endpoint: str = "http://localhost:11434"
    embed_model: str = "bge-m3"
    synth_model: str = "qwen3:7b"
    rate_calls: int = 30
    rate_window_seconds: int = 60
    lock_timeout_seconds: int = 5
    context_warning_pct: int = 35
    context_critical_pct: int = 50
    recency_weight: float = 0.2
    recency_halflife_days: int = 90
    rerank: bool = False

    @property
    def db_path(self) -> Path:
        return self.vault_root / ".engram.db"

    @property
    def activity_log(self) -> Path:
        return self.vault_root / "logs" / "activity.jsonl"


def find_config_file(home: Path) -> Path | None:
    for candidate in (Path.cwd() / "engram.toml", home / ".engram" / "engram.toml"):
        if candidate.exists():
            return candidate
    return None


def load_config(config_path: Path | None = None, home: Path | None = None) -> Config:
    home = home or Path.home()
    data: dict = {}
    if config_path is None:
        config_path = find_config_file(home)
    if config_path and config_path.exists():
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    vault = data.get("vault", {})
    types = data.get("types", {})
    embeddings = data.get("embeddings", {})
    synthesis = data.get("synthesis", {})
    limits = data.get("limits", {})
    retrieval = data.get("retrieval", {})

    env_root = os.environ.get("ENGRAM_VAULT_ROOT")
    if env_root:
        vault_root = Path(env_root)
    elif vault.get("root"):
        vault_root = Path(vault["root"])
    else:
        vault_root = home / ".engram" / "vault"

    endpoint = os.environ.get("ENGRAM_OLLAMA_ENDPOINT") or embeddings.get(
        "endpoint", "http://localhost:11434"
    )

    return Config(
        vault_root=vault_root,
        enabled_types=types.get("enabled", list(DEFAULT_ENABLED_TYPES)),
        ollama_endpoint=endpoint,
        embed_model=embeddings.get("model", "bge-m3"),
        synth_model=synthesis.get("model", "qwen3:7b"),
        rate_calls=limits.get("rate_calls", 30),
        rate_window_seconds=limits.get("rate_window_seconds", 60),
        lock_timeout_seconds=limits.get("lock_timeout_seconds", 5),
        context_warning_pct=limits.get("context_warning_pct", 35),
        context_critical_pct=limits.get("context_critical_pct", 50),
        recency_weight=retrieval.get("recency_weight", 0.2),
        recency_halflife_days=retrieval.get("recency_halflife_days", 90),
        rerank=retrieval.get("rerank", False),
    )
