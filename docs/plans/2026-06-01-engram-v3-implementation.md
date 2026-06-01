# Engram v3.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Engram, an MCP server providing persistent memory for development with Claude Code, backed by an Obsidian vault + SQLite (FTS5 + sqlite-vec).

**Architecture:** Modular monolith Python package. One process serves MCP (via FastMCP) and a minimal CLI. Write path is 100% Python (zero LLM); read path is dual (FTS5 lightweight vs Ollama-embedding + Qwen heavy) chosen by a router. Atomic writes (`os.replace`) + portalocker replace the old sweeper. Embeddings/synthesis via local Ollama only.

**Tech Stack:** Python 3.10+, `mcp` (FastMCP), `sqlite3` + `sqlite-vec`, FTS5, `portalocker`, `python-ulid`, `pyyaml`, `httpx` (Ollama), `watchdog`, `typer` (CLI), `pytest` + `pytest-asyncio`.

**Spec:** `H:\Engram\docs\specs\2026-06-01-engram-v3-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | Package metadata, deps, entry points, pytest config |
| `engram.toml.example` | Sample config |
| `engram/config.py` | Load config (toml + env), paths, constants |
| `engram/models.py` | Pydantic models + `NoteType`/`Confidence` enums |
| `engram/core/db.py` | SQLite connection, schema creation, sqlite-vec loading |
| `engram/core/validator.py` | Field/tag/wikilink/confidence validation |
| `engram/core/indexer.py` | Hash + SQLite/FTS5 upsert + dedup |
| `engram/core/fsio.py` | Atomic write + markdown format + stale .tmp cleanup |
| `engram/core/locking.py` | portalocker lock context manager |
| `engram/core/paths.py` | Type→folder path resolution + activity log |
| `engram/core/writer.py` | save + update pipelines |
| `engram/core/embeddings.py` | Ollama bge-m3 embedding + qwen synthesis (graceful) |
| `engram/core/router.py` | Path A vs B decision |
| `engram/core/reader.py` | Path A (FTS5) + Path B (vector + synthesis) |
| `engram/core/rate_limit.py` | In-memory sliding-window rate limiter |
| `engram/core/hubs.py` | vault_status + hub note ranking |
| `engram/core/handoff.py` | Session handoff note + find latest |
| `engram/core/clustering.py` | Community detection → `_clusters.md` |
| `engram/core/watcher.py` | watchdog incremental reindex |
| `engram/core/reindex.py` | Full/incremental SQLite rebuild |
| `engram/importers/graphify.py` | graph.json → context notes |
| `engram/server.py` | FastMCP server, 6 tools |
| `engram/cli.py` | Typer CLI: reindex, watch, status, import-graph, cluster |
| `engram/hooks/pre_tool_use.py` | Context monitor hook |
| `engram/hooks/session_start.py` | Handoff injection hook |
| `scripts/migrate_v2_to_v3.py` | Confidence backfill migration |
| `tests/conftest.py` | tmp vault fixture, mock Ollama, seeded DB |
| `tests/test_*.py` | One per module |

---

# Phase F0 — Scaffold

**DoD:** `pip install -e .` works; `pytest` runs; DB schema creates.

### Task 0.1: Project metadata + dependencies

**Files:**
- Create: `H:\Engram\pyproject.toml`
- Create: `H:\Engram\engram\__init__.py`
- Create: `H:\Engram\engram\core\__init__.py`
- Create: `H:\Engram\engram\importers\__init__.py`
- Create: `H:\Engram\engram\hooks\__init__.py`
- Create: `H:\Engram\tests\__init__.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "engram"
version = "3.0.0"
description = "Persistent memory MCP server for development with Claude Code"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.2.0",
    "pydantic>=2.0",
    "sqlite-vec>=0.1.3",
    "portalocker>=2.8",
    "python-ulid>=2.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "watchdog>=4.0",
    "typer>=0.12",
    "tomli>=2.0; python_version < '3.11'",
]

[project.optional-dependencies]
clustering = ["python-igraph>=0.11", "leidenalg>=0.10"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-cov>=5.0"]

[project.scripts]
engram = "engram.cli:app"
engram-server = "engram.server:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-q"

[tool.setuptools.packages.find]
include = ["engram*"]
```

- [ ] **Step 2: Create `__init__.py` files**

`engram/__init__.py`:
```python
__version__ = "3.0.0"
```

`engram/core/__init__.py`, `engram/importers/__init__.py`, `engram/hooks/__init__.py`, `tests/__init__.py` — all empty files.

- [ ] **Step 3: Install editable**

Run: `cd /h/Engram && pip install -e ".[dev]"`
Expected: `Successfully installed engram-3.0.0`

- [ ] **Step 4: Commit**

```bash
cd /h/Engram && git add pyproject.toml engram tests && git commit -m "chore: scaffold engram package metadata and deps"
```

---

### Task 0.2: Config loader

**Files:**
- Create: `H:\Engram\engram\config.py`
- Create: `H:\Engram\engram.toml.example`
- Test: `H:\Engram\tests\test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path
from engram.config import load_config

def test_default_vault_root(monkeypatch, tmp_path):
    monkeypatch.delenv("ENGRAM_VAULT_ROOT", raising=False)
    cfg = load_config(config_path=None, home=tmp_path)
    assert cfg.vault_root == tmp_path / ".engram" / "vault"

def test_env_overrides_vault_root(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGRAM_VAULT_ROOT", str(tmp_path / "myvault"))
    cfg = load_config(config_path=None, home=tmp_path)
    assert cfg.vault_root == tmp_path / "myvault"

def test_toml_sets_enabled_types(tmp_path):
    toml = tmp_path / "engram.toml"
    toml.write_text(
        '[vault]\nroot = "%s"\n[types]\nenabled = ["decision","bug"]\n'
        % (tmp_path / "v").as_posix()
    )
    cfg = load_config(config_path=toml, home=tmp_path)
    assert cfg.enabled_types == ["decision", "bug"]
    assert cfg.vault_root == tmp_path / "v"

def test_defaults_present(monkeypatch, tmp_path):
    monkeypatch.delenv("ENGRAM_VAULT_ROOT", raising=False)
    cfg = load_config(config_path=None, home=tmp_path)
    assert cfg.rate_calls == 30
    assert cfg.rate_window_seconds == 60
    assert cfg.lock_timeout_seconds == 5
    assert cfg.context_warning_pct == 35
    assert cfg.context_critical_pct == 50
    assert cfg.ollama_endpoint == "http://localhost:11434"
    assert cfg.embed_model == "bge-m3"
    assert cfg.synth_model == "qwen3:7b"
    assert "decision" in cfg.enabled_types
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engram.config'`

- [ ] **Step 3: Write `engram/config.py`**

```python
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
    )
```

- [ ] **Step 4: Write `engram.toml.example`**

```toml
[vault]
root = "C:/Users/ianfl/dev-vault"

[types]
enabled = ["decision","bug","pattern","context","runbook","session","concept"]

[embeddings]
provider = "ollama"
model = "bge-m3"
endpoint = "http://localhost:11434"

[synthesis]
model = "qwen3:7b"

[limits]
rate_calls = 30
rate_window_seconds = 60
lock_timeout_seconds = 5
context_warning_pct = 35
context_critical_pct = 50
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
cd /h/Engram && git add engram/config.py engram.toml.example tests/test_config.py && git commit -m "feat: config loader with toml + env override"
```

---

### Task 0.3: Domain models + enums

**Files:**
- Create: `H:\Engram\engram\models.py`
- Test: `H:\Engram\tests\test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
import pytest
from pydantic import ValidationError
from engram.models import NoteType, Confidence, NoteData, QueryRequest

def test_confidence_values():
    assert Confidence.FACT == "fact"
    assert Confidence.INFERENCE == "inference"
    assert Confidence.HYPOTHESIS == "hypothesis"

def test_all_eleven_types_exist():
    values = {t.value for t in NoteType}
    assert values == {
        "decision","bug","pattern","context","runbook","session","concept",
        "post-mortem","experiment","refactoring","metric",
    }

def test_notedata_requires_core_fields():
    nd = NoteData(
        title="Use Redis", tldr="Cache via Redis", type=NoteType.DECISION,
        confidence=Confidence.FACT, scope="project",
        tags=["tipo/decision", "maturidade/stable", "dominio/backend"],
    )
    assert nd.status == "active"
    assert nd.author == "claude"

def test_notedata_rejects_unknown_type():
    with pytest.raises(ValidationError):
        NoteData(
            title="x", tldr="y", type="nonsense", confidence=Confidence.FACT,
            scope="project", tags=["tipo/x","maturidade/y","dominio/z"],
        )

def test_query_request_defaults():
    q = QueryRequest(text="rate limit")
    assert q.limit == 10
    assert q.include_cold is False
    assert q.depth is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engram.models'`

- [ ] **Step 3: Write `engram/models.py`**

```python
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class NoteType(str, Enum):
    DECISION = "decision"
    BUG = "bug"
    PATTERN = "pattern"
    CONTEXT = "context"
    RUNBOOK = "runbook"
    SESSION = "session"
    CONCEPT = "concept"
    # v3.1 prepared
    POST_MORTEM = "post-mortem"
    EXPERIMENT = "experiment"
    REFACTORING = "refactoring"
    METRIC = "metric"


class Confidence(str, Enum):
    FACT = "fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"


class NoteData(BaseModel):
    id: str | None = None
    title: str
    tldr: str
    type: NoteType
    confidence: Confidence
    scope: str = "project"
    status: str = "active"
    author: str = "claude"
    subtype: str | None = None
    parent: str | None = None
    project: str | None = None
    module: str | None = None
    tags: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    implements: list[str] | None = None
    supersedes: list[str] | None = None
    code_refs: list[str] | None = None
    session_id: str | None = None
    confidentiality: str = "internal"
    created: str | None = None
    updated: str | None = None
    schema_version: int = 1


class QueryRequest(BaseModel):
    text: str
    project: str | None = None
    projects: list[str] | None = None
    tags: list[str] | None = None
    type_filter: str | None = None
    status_filter: str | None = None
    depth: str | None = None  # "shallow" | "deep" | None
    include_cold: bool = False
    limit: int = 10
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_models.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/models.py tests/test_models.py && git commit -m "feat: domain models with NoteType (11) and Confidence enums"
```

---

### Task 0.4: SQLite schema + sqlite-vec loading

**Files:**
- Create: `H:\Engram\engram\core\db.py`
- Test: `H:\Engram\tests\test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
from engram.core.db import connect, init_schema, VEC_DIM

def test_init_schema_creates_tables(tmp_path):
    conn = connect(tmp_path / "x.db")
    init_schema(conn)
    names = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','virtual')"
        )
    }
    assert "notes" in names
    assert "notes_fts" in names
    conn.close()

def test_notes_has_confidence_column(tmp_path):
    conn = connect(tmp_path / "x.db")
    init_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)")}
    assert "confidence" in cols
    assert "content_hash" in cols
    assert "file_path" in cols
    conn.close()

def test_vec_extension_loads_and_knn_works(tmp_path):
    conn = connect(tmp_path / "x.db")
    init_schema(conn)
    from sqlite_vec import serialize_float32
    vec = [0.1] * VEC_DIM
    conn.execute(
        "INSERT INTO notes_vec(note_id, embedding) VALUES (?, ?)",
        ["n1", serialize_float32(vec)],
    )
    conn.commit()
    rows = conn.execute(
        "SELECT note_id, distance FROM notes_vec "
        "WHERE embedding MATCH ? AND k = 1 ORDER BY distance",
        [serialize_float32(vec)],
    ).fetchall()
    assert rows[0][0] == "n1"
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engram.core.db'`

- [ ] **Step 3: Write `engram/core/db.py`**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

VEC_DIM = 1024  # bge-m3 embedding dimension

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    tldr TEXT,
    type TEXT NOT NULL,
    subtype TEXT,
    confidence TEXT NOT NULL,
    scope TEXT DEFAULT 'project',
    project TEXT,
    module TEXT,
    status TEXT DEFAULT 'active',
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    author TEXT DEFAULT 'claude',
    tags_json TEXT,
    content_hash TEXT,
    file_path TEXT,
    confidentiality TEXT DEFAULT 'internal',
    schema_version INTEGER DEFAULT 1
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    note_id UNINDEXED, title, tldr, tags_text, body_snippet
);

CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project);
CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(type);
CREATE INDEX IF NOT EXISTS idx_notes_status ON notes(status);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS notes_vec USING vec0("
        f"note_id TEXT PRIMARY KEY, embedding float[{VEC_DIM}])"
    )
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/db.py tests/test_db.py && git commit -m "feat: sqlite schema with FTS5 + sqlite-vec (vec0) tables"
```

---

### Task 0.5: Shared test fixtures

**Files:**
- Create: `H:\Engram\tests\conftest.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
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
```

- [ ] **Step 2: Verify fixtures load**

Run: `cd /h/Engram && pytest tests/ -q`
Expected: PASS (all prior tests still pass; conftest imports cleanly)

- [ ] **Step 3: Commit**

```bash
cd /h/Engram && git add tests/conftest.py && git commit -m "test: shared fixtures (vault, config, db, mock ollama)"
```

---

# Phase F1 — Write path

**DoD:** save/update tested; lock + atomic write OK; confidence validated; Obsidian conflict scenarios pass.

### Task 1.1: Validator

**Files:**
- Create: `H:\Engram\engram\core\validator.py`
- Test: `H:\Engram\tests\test_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validator.py
from engram.core.validator import (
    validate_required_fields, validate_tags, load_tags_vocab,
    validate_tag_prefixes, validate_wikilinks,
)

def test_missing_confidence_flagged():
    note = {"id": "1", "title": "t", "tldr": "x", "type": "decision",
            "status": "active", "created": "c", "updated": "u",
            "author": "claude", "scope": "project", "tags": ["tipo/decision"]}
    assert "confidence" in validate_required_fields(note)

def test_all_present_no_missing():
    note = {"id": "1", "title": "t", "tldr": "x", "type": "decision",
            "confidence": "fact", "status": "active", "created": "c",
            "updated": "u", "author": "claude", "scope": "project",
            "tags": ["tipo/decision"]}
    assert validate_required_fields(note) == []

def test_load_vocab_and_validate_tags(vault):
    vocab = load_tags_vocab(vault)
    assert "tipo/decision" in vocab
    assert validate_tags(["tipo/decision", "tipo/nonexistent"], vocab) == ["tipo/nonexistent"]

def test_projeto_tags_always_valid(vault):
    vocab = load_tags_vocab(vault)
    assert validate_tags(["projeto/anything"], vocab) == []

def test_missing_prefixes():
    missing = validate_tag_prefixes(["tipo/decision"])
    assert "maturidade/" in missing
    assert "dominio/" in missing
    assert "tipo/" not in missing

def test_wikilinks_broken_detected(db, vault):
    assert validate_wikilinks(["[[does-not-exist]]"], db, vault) == ["[[does-not-exist]]"]

def test_wikilinks_resolved_via_sqlite(db, vault):
    db.execute(
        "INSERT INTO notes (id,title,type,confidence,created,updated,file_path) "
        "VALUES ('adr-1','t','decision','fact','c','u','/v/adr-1.md')"
    )
    db.commit()
    assert validate_wikilinks(["[[adr-1]]"], db, vault) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_validator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/validator.py`**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

REQUIRED_FIELDS = [
    "id", "title", "tldr", "type", "confidence", "status",
    "created", "updated", "author", "scope", "tags",
]


def load_tags_vocab(vault_root: Path) -> set[str]:
    vocab: set[str] = set()
    tags_path = vault_root / "meta" / "tags.md"
    if tags_path.exists():
        for line in tags_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(("- ", "* ")):
                tag = line[2:].strip().split()[0]
                if "/" in tag:
                    vocab.add(tag)
    return vocab


def validate_required_fields(note: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if not note.get(f)]


def validate_tags(tags: list[str], vocab: set[str]) -> list[str]:
    invalid = []
    for tag in tags:
        if tag.startswith("projeto/"):
            continue
        if tag not in vocab:
            invalid.append(tag)
    return invalid


def validate_tag_prefixes(tags: list[str]) -> list[str]:
    missing = []
    for prefix in ("tipo/", "maturidade/", "dominio/"):
        if not any(t.startswith(prefix) for t in tags):
            missing.append(prefix)
    return missing


def validate_wikilinks(related: list[str], conn: sqlite3.Connection,
                       vault_root: Path) -> list[str]:
    broken = []
    for link in related:
        clean = link.strip("[]").split("|")[0]
        row = conn.execute(
            "SELECT id FROM notes WHERE id = ? OR file_path LIKE ?",
            (clean, f"%/{clean}.md"),
        ).fetchone()
        if row:
            continue
        if (vault_root / f"{clean}.md").exists():
            continue
        found = False
        for d in ("projetos", "global", "sessoes"):
            base = vault_root / d
            if base.exists() and list(base.rglob(f"{clean}.md")):
                found = True
                break
        if not found:
            broken.append(link)
    return broken
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_validator.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/validator.py tests/test_validator.py && git commit -m "feat: validator (fields, confidence, tags, prefixes, wikilinks)"
```

---

### Task 1.2: Indexer

**Files:**
- Create: `H:\Engram\engram\core\indexer.py`
- Test: `H:\Engram\tests\test_indexer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_indexer.py
from engram.core.indexer import upsert_note, compute_hash, check_duplicate

def _note(nid="n1", title="Use Redis"):
    return {"id": nid, "title": title, "tldr": "cache layer",
            "type": "decision", "confidence": "fact", "scope": "project",
            "status": "active", "created": "c", "updated": "u",
            "author": "claude", "project": "proj", "module": None,
            "tags": ["tipo/decision", "dominio/backend"],
            "confidentiality": "internal", "schema_version": 1}

def test_compute_hash_is_32_hex():
    h = compute_hash("hello world")
    assert len(h) == 32
    assert all(c in "0123456789abcdef" for c in h)

def test_upsert_inserts_into_notes_and_fts(db):
    upsert_note(db, _note(), content_hash="abc", file_path="/v/n1.md",
                body="Redis chosen for speed.")
    row = db.execute("SELECT title, confidence FROM notes WHERE id='n1'").fetchone()
    assert row == ("Use Redis", "fact")
    fts = db.execute("SELECT title FROM notes_fts WHERE notes_fts MATCH 'redis'").fetchall()
    assert len(fts) == 1

def test_upsert_replaces_existing(db):
    upsert_note(db, _note(title="v1"), "h1", "/v/n1.md", "body1")
    upsert_note(db, _note(title="v2"), "h2", "/v/n1.md", "body2")
    rows = db.execute("SELECT title FROM notes WHERE id='n1'").fetchall()
    assert rows == [("v2",)]
    cnt = db.execute("SELECT count(*) FROM notes_fts WHERE note_id='n1'").fetchone()
    assert cnt[0] == 1

def test_check_duplicate(db):
    upsert_note(db, _note(), "hash123", "/v/n1.md", "body")
    assert check_duplicate(db, "hash123") is not None
    assert check_duplicate(db, "other") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_indexer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/indexer.py`**

```python
from __future__ import annotations

import hashlib
import json
import sqlite3


def compute_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


def upsert_note(conn: sqlite3.Connection, note: dict, content_hash: str,
                file_path: str, body: str) -> None:
    tags = note.get("tags", [])
    conn.execute(
        """INSERT OR REPLACE INTO notes
           (id,title,tldr,type,subtype,confidence,scope,project,module,
            status,created,updated,author,tags_json,content_hash,file_path,
            confidentiality,schema_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            note["id"], note["title"], note.get("tldr", ""), note["type"],
            note.get("subtype"), note["confidence"],
            note.get("scope", "project"), note.get("project"),
            note.get("module"), note.get("status", "active"),
            note["created"], note["updated"], note.get("author", "claude"),
            json.dumps(tags), content_hash, file_path,
            note.get("confidentiality", "internal"),
            note.get("schema_version", 1),
        ),
    )
    conn.execute("DELETE FROM notes_fts WHERE note_id = ?", (note["id"],))
    conn.execute(
        "INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet) "
        "VALUES (?,?,?,?,?)",
        (note["id"], note["title"], note.get("tldr", ""),
         " ".join(tags), body[:500]),
    )
    conn.commit()


def check_duplicate(conn: sqlite3.Connection, content_hash: str) -> str | None:
    row = conn.execute(
        "SELECT id, title FROM notes WHERE content_hash = ?", (content_hash,)
    ).fetchone()
    return f"{row[0]} ({row[1]})" if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_indexer.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/indexer.py tests/test_indexer.py && git commit -m "feat: indexer with hash[:32], FTS5 upsert (delete+insert, no triggers)"
```

---

### Task 1.3: Atomic write + markdown format + stale cleanup

**Files:**
- Create: `H:\Engram\engram\core\fsio.py`
- Test: `H:\Engram\tests\test_fsio.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fsio.py
import os
from engram.core.fsio import atomic_write, format_markdown, cleanup_stale_tmp

def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "sub" / "note.md"
    atomic_write(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"
    assert not (tmp_path / "sub" / "note.md.tmp").exists()

def test_atomic_write_overwrites(tmp_path):
    target = tmp_path / "n.md"
    atomic_write(target, "v1")
    atomic_write(target, "v2")
    assert target.read_text(encoding="utf-8") == "v2"

def test_format_markdown_has_frontmatter_and_body():
    note = {"id": "n1", "title": "T", "tldr": "x", "type": "decision",
            "confidence": "fact", "scope": "project", "status": "active",
            "created": "2026-06-01", "updated": "2026-06-01",
            "author": "claude", "tags": ["tipo/decision"]}
    md = format_markdown(note, "Body text here.")
    assert md.startswith("---\n")
    assert "confidence: fact" in md
    assert "Body text here." in md

def test_cleanup_stale_tmp(tmp_path):
    old = tmp_path / "a.md.tmp"
    old.write_text("x")
    os.utime(old, (0, 0))
    cleanup_stale_tmp(tmp_path, max_age_seconds=60)
    assert not old.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_fsio.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/fsio.py`**

```python
from __future__ import annotations

import os
import time
from pathlib import Path

import yaml

FRONTMATTER_ORDER = [
    "id", "title", "tldr", "type", "subtype", "parent", "confidence",
    "scope", "project", "module", "status", "created", "updated", "author",
    "tags", "related", "implements", "supersedes", "code_refs",
    "session_id", "confidentiality", "schema_version",
]


def atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)  # atomic on Windows + POSIX


def format_markdown(note: dict, body: str) -> str:
    fm = {}
    for key in FRONTMATTER_ORDER:
        val = note.get(key)
        if val is not None:
            fm[key] = val
    yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True,
                         sort_keys=False, width=120)
    return f"---\n{yaml_str}---\n\n{body}\n"


def cleanup_stale_tmp(root: Path, max_age_seconds: int = 60) -> int:
    removed = 0
    now = time.time()
    for tmp in root.rglob("*.tmp"):
        try:
            if now - tmp.stat().st_mtime > max_age_seconds:
                tmp.unlink()
                removed += 1
        except OSError:
            pass
    return removed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_fsio.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/fsio.py tests/test_fsio.py && git commit -m "feat: atomic write (os.replace), markdown formatter, stale .tmp cleanup"
```

---

### Task 1.4: Lock helper (portalocker)

**Files:**
- Create: `H:\Engram\engram\core\locking.py`
- Test: `H:\Engram\tests\test_locking.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_locking.py
import threading
import time
from engram.core.locking import vault_lock

def test_lock_acquires_and_releases(tmp_path):
    lock_file = tmp_path / ".lock"
    with vault_lock(lock_file, timeout=2):
        assert lock_file.exists()
    with vault_lock(lock_file, timeout=2):
        pass

def test_lock_blocks_second_holder(tmp_path):
    lock_file = tmp_path / ".lock"
    timings = []
    def hold():
        with vault_lock(lock_file, timeout=2):
            time.sleep(0.5)
    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.1)
    start = time.monotonic()
    with vault_lock(lock_file, timeout=2):
        timings.append(time.monotonic() - start)
    t.join()
    assert timings[0] >= 0.3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_locking.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/locking.py`**

```python
from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path

import portalocker


@contextmanager
def vault_lock(lock_file: Path, timeout: float = 5.0):
    """Exclusive cross-platform lock. Raises TimeoutError on timeout."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_file, "a+")
    deadline = time.monotonic() + timeout
    while True:
        try:
            portalocker.lock(fh, portalocker.LOCK_EX | portalocker.LOCK_NB)
            break
        except portalocker.exceptions.LockException:
            if time.monotonic() >= deadline:
                fh.close()
                raise TimeoutError(f"Could not acquire lock: {lock_file}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            portalocker.unlock(fh)
        finally:
            fh.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_locking.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/locking.py tests/test_locking.py && git commit -m "feat: portalocker-based vault lock context manager"
```

---

### Task 1.5: Path resolution + activity log

**Files:**
- Create: `H:\Engram\engram\core\paths.py`
- Test: `H:\Engram\tests\test_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paths.py
import json
from engram.core.paths import target_path, log_activity

def test_project_decision_path(vault):
    p = target_path(vault, {"type": "decision", "scope": "project",
                            "project": "proj", "id": "adr-1"})
    assert p == vault / "projetos" / "proj" / "decisoes" / "adr-1.md"

def test_global_pattern_path(vault):
    p = target_path(vault, {"type": "pattern", "scope": "global",
                            "project": None, "id": "pat-1"})
    assert p == vault / "global" / "patterns" / "pat-1.md"

def test_session_path(vault):
    p = target_path(vault, {"type": "session", "scope": "project",
                            "project": "proj", "id": "h-1"})
    assert p == vault / "sessoes" / "handoff-h-1.md"

def test_log_activity_appends_jsonl(config):
    log_activity(config.activity_log, "save", "n1", {"type": "decision"})
    log_activity(config.activity_log, "query", "n2", {"path": "A"})
    lines = config.activity_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["action"] == "save"
    assert json.loads(lines[1])["note_id"] == "n2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/paths.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

TYPE_FOLDERS = {
    "decision": "decisoes",
    "bug": "bugs",
    "pattern": "patterns",
    "concept": "concepts",
    "context": "context",
    "runbook": "runbooks",
    "post-mortem": "post-mortems",
    "experiment": "experiments",
    "refactoring": "refactoring",
    "session": "sessoes",
    "metric": "metrics",
}


def target_path(vault_root: Path, note: dict) -> Path:
    ntype = note["type"]
    scope = note.get("scope", "project")
    project = note.get("project")
    slug = note.get("id", "unknown")
    folder = TYPE_FOLDERS.get(ntype, ntype)

    if ntype == "session":
        return vault_root / "sessoes" / f"handoff-{slug}.md"
    if scope in ("cross", "global") or not project:
        return vault_root / "global" / folder / f"{slug}.md"
    return vault_root / "projetos" / project / folder / f"{slug}.md"


def log_activity(activity_log: Path, action: str, note_id: str,
                 details: dict) -> None:
    activity_log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "note_id": note_id,
        **details,
    }
    with activity_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_paths.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/paths.py tests/test_paths.py && git commit -m "feat: type-folder path resolution + jsonl activity log"
```

---

### Task 1.6: Writer — vault_save

**Files:**
- Create: `H:\Engram\engram\core\writer.py`
- Test: `H:\Engram\tests\test_writer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_writer.py
from engram.core.writer import vault_save
from engram.models import NoteData, NoteType, Confidence

def _note():
    return NoteData(
        title="Use Redis", tldr="Cache via Redis for speed",
        type=NoteType.DECISION, confidence=Confidence.FACT, scope="project",
        project="proj",
        tags=["tipo/decision", "maturidade/stable", "dominio/backend"],
    )

def test_save_writes_file_and_indexes(config, db, vault):
    res = vault_save(_note(), "Redis chosen for low latency.", config, db)
    assert res["status"] == "ok"
    path = vault / "projetos" / "proj" / "decisoes" / f"{res['note_id']}.md"
    assert path.exists()
    assert "confidence: fact" in path.read_text(encoding="utf-8")
    row = db.execute("SELECT title FROM notes WHERE id=?", (res["note_id"],)).fetchone()
    assert row[0] == "Use Redis"

def test_save_missing_prefix_errors(config, db):
    n = _note()
    n.tags = ["tipo/decision"]
    res = vault_save(n, "body", config, db)
    assert res["status"] == "error"
    assert "maturidade/" in str(res["reason"])

def test_save_duplicate_body_rejected(config, db):
    vault_save(_note(), "identical body", config, db)
    res = vault_save(_note(), "identical body", config, db)
    assert res["status"] == "error"
    assert "uplicate" in res["reason"]

def test_save_invalid_tag_rejected(config, db):
    n = _note()
    n.tags = ["tipo/decision", "maturidade/stable", "dominio/backend", "bogus/x"]
    res = vault_save(n, "body unique 1", config, db)
    assert res["status"] == "error"
    assert "bogus/x" in str(res["reason"])

def test_save_disabled_type_rejected(config, db):
    config.enabled_types = ["bug"]
    res = vault_save(_note(), "body unique 2", config, db)
    assert res["status"] == "error"
    assert "not enabled" in res["reason"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_writer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/writer.py`**

```python
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ulid import ULID

from engram.config import Config
from engram.models import NoteData
from engram.core import indexer, validator, fsio, paths, locking


def vault_save(note: NoteData, body: str, config: Config,
               conn: sqlite3.Connection) -> dict:
    data = note.model_dump(mode="json", exclude_none=False)
    warnings: list[str] = []

    if not data.get("id"):
        data["id"] = str(ULID())
    now = datetime.now(timezone.utc).isoformat()
    data["created"] = data.get("created") or now
    data["updated"] = now

    if data["type"] not in config.enabled_types:
        return {"status": "error",
                "reason": f"Type '{data['type']}' not enabled in config"}

    missing = validator.validate_required_fields(data)
    if missing:
        return {"status": "error", "reason": f"Missing required fields: {missing}"}

    missing_prefix = validator.validate_tag_prefixes(data["tags"])
    if missing_prefix:
        return {"status": "error",
                "reason": f"Missing required tag prefix: {missing_prefix}"}

    vocab = validator.load_tags_vocab(config.vault_root)
    invalid = validator.validate_tags(data["tags"], vocab)
    if invalid:
        return {"status": "error", "reason": f"Invalid tags: {invalid}",
                "valid_sample": sorted(vocab)[:30]}

    if len(data["tldr"].split()) > 20:
        warnings.append(f"TL;DR has {len(data['tldr'].split())} words (max 20)")

    content_hash = indexer.compute_hash(body)
    dup = indexer.check_duplicate(conn, content_hash)
    if dup:
        return {"status": "error", "reason": f"Duplicate detected: {dup}"}

    broken = validator.validate_wikilinks(data.get("related", []), conn,
                                          config.vault_root)
    if broken:
        warnings.append(f"Broken wikilinks: {broken}")

    target = paths.target_path(config.vault_root, data)
    markdown = fsio.format_markdown(data, body)

    lock_file = config.vault_root / ".engram.lock"
    try:
        with locking.vault_lock(lock_file, timeout=config.lock_timeout_seconds):
            fsio.atomic_write(target, markdown)
    except TimeoutError as e:
        return {"status": "error", "reason": str(e)}

    indexer.upsert_note(conn, data, content_hash, str(target), body)
    paths.log_activity(config.activity_log, "save", data["id"],
                       {"type": data["type"], "project": data.get("project")})

    return {"status": "ok", "note_id": data["id"], "path": str(target),
            "warnings": warnings}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_writer.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/writer.py tests/test_writer.py && git commit -m "feat: vault_save pipeline (validate, hash, atomic write, index)"
```

---

### Task 1.7: Writer — vault_update + human-edit preservation

**Files:**
- Modify: `H:\Engram\engram\core\writer.py` (add `vault_update`)
- Test: `H:\Engram\tests\test_update.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_update.py
from engram.core.writer import vault_save, vault_update
from engram.models import NoteData, NoteType, Confidence

def _save(config, db):
    n = NoteData(title="T", tldr="orig tldr", type=NoteType.DECISION,
                 confidence=Confidence.HYPOTHESIS, scope="project", project="proj",
                 tags=["tipo/decision","maturidade/draft","dominio/backend"])
    return vault_save(n, "original body", config, db)["note_id"]

def test_update_changes_field(config, db):
    nid = _save(config, db)
    res = vault_update(nid, {"confidence": "fact"}, None, config, db)
    assert res["status"] == "ok"
    row = db.execute("SELECT confidence FROM notes WHERE id=?", (nid,)).fetchone()
    assert row[0] == "fact"

def test_update_immutable_rejected(config, db):
    nid = _save(config, db)
    res = vault_update(nid, {"type": "bug"}, None, config, db)
    assert res["status"] == "error"
    assert "immutable" in res["reason"].lower()

def test_update_preserves_untouched_human_edits(config, db, vault):
    nid = _save(config, db)
    from engram.core.paths import target_path
    p = target_path(vault, {"type":"decision","scope":"project",
                            "project":"proj","id":nid})
    txt = p.read_text(encoding="utf-8").replace("original body", "HUMAN EDITED body")
    p.write_text(txt, encoding="utf-8")
    res = vault_update(nid, {"confidence": "fact"}, None, config, db)
    assert res["status"] == "ok"
    assert "HUMAN EDITED body" in p.read_text(encoding="utf-8")

def test_update_not_found(config, db):
    res = vault_update("nonexistent", {"confidence": "fact"}, None, config, db)
    assert res["status"] == "error"
    assert "not found" in res["reason"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_update.py -v`
Expected: FAIL with `ImportError: cannot import name 'vault_update'`

- [ ] **Step 3: Append `vault_update` to `engram/core/writer.py`**

Add these imports at the top of the file (alongside existing imports):

```python
import yaml
from pathlib import Path
```

Append at the end of the file:

```python
IMMUTABLE_FIELDS = {"id", "created", "type", "subtype", "parent"}


def vault_update(note_id: str, updates: dict, body: str | None,
                 config: Config, conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT file_path, content_hash FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if not row:
        return {"status": "error", "reason": f"Note {note_id} not found in index"}
    file_path = Path(row[0])
    if not file_path.exists():
        return {"status": "error", "reason": f"Note file not found: {file_path}"}

    blocked = [k for k in updates if k in IMMUTABLE_FIELDS]
    if blocked:
        return {"status": "error", "reason": f"Cannot modify immutable fields: {blocked}"}

    text = file_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
        existing_body = parts[2].strip() if len(parts) >= 3 else text
    else:
        fm, existing_body = {}, text

    warnings: list[str] = []
    changes = []
    for key, value in updates.items():
        if fm.get(key) != value:
            changes.append(f"{key}: {fm.get(key)} -> {value}")
            fm[key] = value
    fm["updated"] = datetime.now(timezone.utc).isoformat()

    new_body = body if body is not None else existing_body

    if "tags" in updates:
        vocab = validator.load_tags_vocab(config.vault_root)
        inv = validator.validate_tags(updates["tags"], vocab)
        if inv:
            return {"status": "error", "reason": f"Invalid tags: {inv}"}

    content_hash = indexer.compute_hash(new_body) if body is not None else row[1]

    if "related" in updates:
        broken = validator.validate_wikilinks(updates["related"], conn,
                                              config.vault_root)
        if broken:
            warnings.append(f"Broken wikilinks: {broken}")

    markdown = fsio.format_markdown(fm, new_body)
    lock_file = config.vault_root / ".engram.lock"
    try:
        with locking.vault_lock(lock_file, timeout=config.lock_timeout_seconds):
            fsio.atomic_write(file_path, markdown)
    except TimeoutError as e:
        return {"status": "error", "reason": str(e)}

    indexer.upsert_note(conn, fm, content_hash, str(file_path), new_body)
    paths.log_activity(config.activity_log, "update", note_id,
                       {"changes": changes, "body_changed": body is not None})

    if not changes and body is None:
        warnings.append("No changes detected")
    return {"status": "ok", "note_id": note_id, "path": str(file_path),
            "changes": changes, "warnings": warnings}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_update.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/writer.py tests/test_update.py && git commit -m "feat: vault_update with immutable fields + human-edit preservation"
```

---

# Phase F2 — Read path

**DoD:** query/deep_query tested; fallback chain OK; mock Ollama.

### Task 2.1: Embeddings client (Ollama, graceful failure)

**Files:**
- Create: `H:\Engram\engram\core\embeddings.py`
- Test: `H:\Engram\tests\test_embeddings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_embeddings.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/embeddings.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_embeddings.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/embeddings.py tests/test_embeddings.py && git commit -m "feat: Ollama embeddings + synthesis with graceful EmbeddingUnavailable"
```

---

### Task 2.2: Router

**Files:**
- Create: `H:\Engram\engram\core\router.py`
- Test: `H:\Engram\tests\test_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router.py
from engram.models import QueryRequest
from engram.core.router import route_query, has_semantic_intent

def test_explicit_deep_is_heavy(db):
    assert route_query(QueryRequest(text="x", depth="deep"), db) == "heavy"

def test_multi_project_is_heavy(db):
    assert route_query(QueryRequest(text="x", projects=["a","b"]), db) == "heavy"

def test_wildcard_is_heavy(db):
    assert route_query(QueryRequest(text="x", projects=["*"]), db) == "heavy"

def test_semantic_pt_is_heavy(db):
    assert route_query(QueryRequest(text="qual o impacto de migrar Redis"), db) == "heavy"

def test_semantic_en_is_heavy(db):
    assert route_query(QueryRequest(text="what is the impact of migrating"), db) == "heavy"

def test_simple_query_is_lightweight(db):
    assert route_query(QueryRequest(text="rate limit config"), db) == "lightweight"

def test_many_matches_is_heavy(db):
    for i in range(6):
        db.execute(
            "INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet) "
            "VALUES (?,?,?,?,?)", (f"n{i}", "redis cache", "x", "", "redis"))
    db.commit()
    assert route_query(QueryRequest(text="redis"), db) == "heavy"

def test_has_semantic_intent_bilingual():
    assert has_semantic_intent("comparar duas opcoes")
    assert has_semantic_intent("compare two options")
    assert not has_semantic_intent("redis timeout value")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/router.py`**

```python
from __future__ import annotations

import re
import sqlite3

from engram.models import QueryRequest

SEMANTIC_PATTERNS = [
    r"impacto|afeta|consequencia",
    r"relacao entre|conexao|depende",
    r"migrar|substituir|trocar",
    r"todos?.*(decisoes|bugs|patterns)",
    r"resumo|overview|visao geral",
    r"por que|motivo|razao",
    r"comparar|diferenca entre",
    r"historico de|evolucao|timeline",
    r"alternativas? (a|para|de)",
    r"impact|affects|consequence",
    r"relationship between|connection|depends",
    r"migrate|replace|switch",
    r"all.*(decisions|bugs|patterns)",
    r"summary|overview|big picture",
    r"why did|reason|rationale",
    r"compare|difference between",
    r"history of|evolution|timeline",
    r"alternatives? (to|for)",
]


def has_semantic_intent(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in SEMANTIC_PATTERNS)


def fts_count(text: str, project: str | None, conn: sqlite3.Connection) -> int:
    safe = text.replace('"', '""')
    try:
        if project:
            return conn.execute(
                "SELECT COUNT(*) FROM notes_fts JOIN notes "
                "ON notes_fts.note_id = notes.id "
                "WHERE notes_fts MATCH ? AND notes.project = ? "
                "AND notes.status != 'archived'", (safe, project)
            ).fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM notes_fts WHERE notes_fts MATCH ?", (safe,)
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def route_query(query: QueryRequest, conn: sqlite3.Connection) -> str:
    if query.depth == "deep":
        return "heavy"
    if query.projects and len(query.projects) > 1:
        return "heavy"
    if query.projects and "*" in query.projects:
        return "heavy"
    if has_semantic_intent(query.text):
        return "heavy"
    project = query.project or (query.projects[0] if query.projects else None)
    if fts_count(query.text, project, conn) > 5:
        return "heavy"
    return "lightweight"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_router.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/router.py tests/test_router.py && git commit -m "feat: router (depth, multi-project, bilingual semantic, match count)"
```

---

### Task 2.3: Reader — Path A (FTS5)

**Files:**
- Create: `H:\Engram\engram\core\reader.py`
- Test: `H:\Engram\tests\test_reader_a.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reader_a.py
from engram.models import QueryRequest
from engram.core.reader import path_a

def _seed(db):
    rows = [
        ("n1","Redis cache","Use Redis for cache","decision"),
        ("n2","Auth bug","JWT expiry off-by-one","bug"),
    ]
    for nid, title, tldr, typ in rows:
        db.execute(
            "INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
            "status,created,updated,file_path,confidentiality) VALUES "
            "(?,?,?,?, 'fact','project','proj','active','c','u',?,'internal')",
            (nid, title, tldr, typ, f"/v/{nid}.md"))
        db.execute(
            "INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet) "
            "VALUES (?,?,?,?,?)", (nid, title, tldr, "", tldr))
    db.commit()

def test_path_a_returns_tldrs(db):
    _seed(db)
    res = path_a(QueryRequest(text="redis"), db)
    assert res["path"] == "A"
    assert res["match_count"] == 1
    assert "Use Redis for cache" in res["summary"]

def test_path_a_excludes_archived(db):
    _seed(db)
    db.execute("UPDATE notes SET status='archived' WHERE id='n1'")
    db.commit()
    res = path_a(QueryRequest(text="redis"), db)
    assert res["match_count"] == 0

def test_path_a_type_filter(db):
    _seed(db)
    res = path_a(QueryRequest(text="proj", type_filter="bug"), db)
    ids = {r["id"] for r in res["results"]}
    assert ids == {"n2"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_reader_a.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/reader.py` (Path A)**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from engram.config import Config
from engram.models import QueryRequest
from engram.core import embeddings
from engram.core.embeddings import EmbeddingUnavailable


def path_a(query: QueryRequest, conn: sqlite3.Connection) -> dict:
    safe = query.text.replace('"', '""')
    sql = (
        "SELECT n.id,n.type,n.title,n.tldr,n.status,n.project,n.updated,"
        "n.confidence FROM notes_fts f JOIN notes n ON f.note_id = n.id "
        "WHERE notes_fts MATCH ?"
    )
    params: list = [safe]
    if query.project:
        sql += " AND n.project = ?"; params.append(query.project)
    if query.status_filter:
        sql += " AND n.status = ?"; params.append(query.status_filter)
    else:
        sql += " AND n.status != 'archived'"
    if query.type_filter:
        sql += " AND n.type = ?"; params.append(query.type_filter)
    if not query.include_cold:
        sql += " AND n.file_path NOT LIKE '%/_cold/%'"
    sql += " ORDER BY rank LIMIT ?"; params.append(query.limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        rows = []

    results, lines = [], []
    for nid, ntype, title, tldr, status, project, updated, conf in rows:
        results.append({"id": nid, "type": ntype, "title": title,
                        "tldr": tldr, "confidence": conf, "project": project})
        lines.append(f"[{ntype}|{conf}] {tldr}")
    summary = "\n".join(lines) if lines else "No matches found."
    return {"path": "A", "results": results, "summary": summary,
            "match_count": len(results)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_reader_a.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/reader.py tests/test_reader_a.py && git commit -m "feat: reader Path A (FTS5 → TL;DRs with confidence)"
```

---

### Task 2.4: Reader — Path B + fallback chain

**Files:**
- Modify: `H:\Engram\engram\core\reader.py` (add `path_b`)
- Test: `H:\Engram\tests\test_reader_b.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reader_b.py
from engram.models import QueryRequest
from engram.core.reader import path_b
from engram.core.embeddings import EmbeddingUnavailable
from sqlite_vec import serialize_float32

def _seed_vec(db, vault, vec):
    body = "Redis chosen for low-latency cache. Decision is final."
    p = vault / "n1.md"
    p.write_text("---\nid: n1\n---\n\n" + body, encoding="utf-8")
    db.execute(
        "INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
        "status,created,updated,file_path,confidentiality) VALUES "
        "('n1','Redis','cache','decision','fact','project','proj','active',"
        "'c','u',?, 'internal')", (str(p),))
    db.execute("INSERT INTO notes_vec(note_id,embedding) VALUES ('n1',?)",
               (serialize_float32(vec),))
    db.commit()

def test_path_b_synthesizes(db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: vec)
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize",
                        lambda q, ctx, c: "SYNTH OK")
    res = path_b(QueryRequest(text="why redis"), db, config)
    assert res["path"] == "B"
    assert res["synthesis"] == "SYNTH OK"
    assert res["sources"][0]["id"] == "n1"

def test_path_b_embedding_offline_falls_back_to_a(db, vault, config, monkeypatch):
    _seed_vec(db, vault, [0.5] * 1024)
    db.execute("INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet)"
               " VALUES ('n1','Redis','cache','','redis cache')"); db.commit()
    def boom(t, c): raise EmbeddingUnavailable("offline")
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding", boom)
    res = path_b(QueryRequest(text="redis"), db, config)
    assert res["path"] == "B-fallback"
    assert res["fallback_used"] is True

def test_path_b_synth_offline_returns_full_notes(db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    db.execute("INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet)"
               " VALUES ('n1','Redis','cache','','redis cache')"); db.commit()
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: vec)
    def boom(q, ctx, c): raise EmbeddingUnavailable("synth offline")
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize", boom)
    res = path_b(QueryRequest(text="redis"), db, config)
    assert res["path"] == "B-fallback"
    assert "Redis chosen for low-latency" in res["summary"]

def test_path_b_excludes_restricted(db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    db.execute("UPDATE notes SET confidentiality='restricted' WHERE id='n1'")
    db.commit()
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: vec)
    captured = {}
    def cap_synth(q, ctx, c):
        captured["ctx"] = ctx
        return "S"
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize", cap_synth)
    res = path_b(QueryRequest(text="redis"), db, config)
    assert res.get("restricted_omitted", 0) == 1
    assert "Redis chosen" not in captured.get("ctx", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_reader_b.py -v`
Expected: FAIL with `ImportError: cannot import name 'path_b'`

- [ ] **Step 3: Append `path_b` to `engram/core/reader.py`**

Add this import near the top (with the existing imports):

```python
from sqlite_vec import serialize_float32
```

Append at end of file:

```python
def _read_body(file_path: str) -> str:
    p = Path(file_path)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        return parts[2].strip() if len(parts) >= 3 else text
    return text


def path_b(query: QueryRequest, conn: sqlite3.Connection,
           config: Config) -> dict:
    try:
        qvec = embeddings.get_embedding(query.text, config)
    except EmbeddingUnavailable:
        res = path_a(query, conn)
        res["path"] = "B-fallback"
        res["fallback_used"] = True
        return res

    rows = conn.execute(
        "SELECT v.note_id, v.distance, n.title, n.type, n.confidence, "
        "n.file_path, n.confidentiality FROM notes_vec v "
        "JOIN notes n ON n.id = v.note_id "
        "WHERE v.embedding MATCH ? AND k = ? AND n.status != 'archived' "
        "ORDER BY v.distance",
        (serialize_float32(qvec), max(query.limit, 7)),
    ).fetchall()

    if not rows:
        return {"path": "B", "synthesis": "No relevant notes found.",
                "sources": [], "fallback_used": False}

    safe = [r for r in rows if r[6] != "restricted"]
    restricted = len(rows) - len(safe)

    bodies, sources = [], []
    for note_id, dist, title, ntype, conf, fpath, _c in safe[:7]:
        sources.append({"id": note_id, "title": title, "type": ntype,
                        "confidence": conf,
                        "relevance": round(1.0 / (1.0 + dist), 3)})
        body = _read_body(fpath)
        if body:
            bodies.append(f"## [{ntype}|{conf}] {title}\n{body}")
    combined = "\n\n".join(bodies)

    try:
        synthesis = embeddings.synthesize(query.text, combined, config)
    except EmbeddingUnavailable:
        a = path_a(query, conn)
        full = "\n\n---\n\n".join(bodies[:3])
        a["path"] = "B-fallback"
        a["summary"] = a["summary"] + f"\n\n--- Full notes (synth offline) ---\n\n{full}"
        a["fallback_used"] = True
        return a

    result = {"path": "B", "synthesis": synthesis, "sources": sources,
              "fallback_used": False}
    if restricted:
        result["restricted_omitted"] = restricted
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_reader_b.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/reader.py tests/test_reader_b.py && git commit -m "feat: reader Path B (vec KNN + Qwen synth) + 2-level fallback + restricted filter"
```

---

### Task 2.5: Rate limiter

**Files:**
- Create: `H:\Engram\engram\core\rate_limit.py`
- Test: `H:\Engram\tests\test_rate_limit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rate_limit.py
from engram.core.rate_limit import RateLimiter

def test_allows_under_limit():
    rl = RateLimiter(max_calls=3, window_seconds=60)
    assert rl.allow("vault.save")
    assert rl.allow("vault.save")
    assert rl.allow("vault.save")

def test_blocks_over_limit():
    rl = RateLimiter(max_calls=2, window_seconds=60)
    rl.allow("t"); rl.allow("t")
    assert rl.allow("t") is False

def test_per_tool_isolation():
    rl = RateLimiter(max_calls=1, window_seconds=60)
    assert rl.allow("a")
    assert rl.allow("b")
    assert rl.allow("a") is False

def test_window_expiry(monkeypatch):
    import engram.core.rate_limit as m
    t = [1000.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: t[0])
    rl = RateLimiter(max_calls=1, window_seconds=10)
    assert rl.allow("x")
    assert rl.allow("x") is False
    t[0] += 11
    assert rl.allow("x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_rate_limit.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/rate_limit.py`**

```python
from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_calls: int = 30, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: dict[str, deque] = defaultdict(deque)

    def allow(self, tool: str) -> bool:
        now = time.monotonic()
        q = self._calls[tool]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_calls:
            return False
        q.append(now)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_rate_limit.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/rate_limit.py tests/test_rate_limit.py && git commit -m "feat: in-memory sliding-window rate limiter (per tool)"
```

---

# Phase F3 — Handoff + status + MCP server + hooks

**DoD:** handoff saves/injects; thresholds OK; server exposes 6 tools.

### Task 3.1: Handoff

**Files:**
- Create: `H:\Engram\engram\core\handoff.py`
- Test: `H:\Engram\tests\test_handoff.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_handoff.py
from engram.core.handoff import vault_handoff, find_latest_handoff

def test_handoff_creates_session_note(config, db, vault):
    res = vault_handoff(
        {"project": "proj", "decisions": ["use redis"],
         "files": ["app/x.py"], "next_steps": ["write tests"],
         "branch": "main"}, config, db)
    assert res["status"] == "ok"
    p = vault / "sessoes" / f"handoff-{res['note_id']}.md"
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    assert "use redis" in txt
    assert "type: session" in txt

def test_find_latest_handoff(config, db, vault):
    r1 = vault_handoff({"project": "proj", "decisions": [], "files": [],
                        "next_steps": [], "branch": "main"}, config, db)
    latest = find_latest_handoff(vault, project="proj")
    assert latest is not None
    assert r1["note_id"] in str(latest)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_handoff.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/handoff.py`**

```python
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ulid import ULID

from engram.config import Config
from engram.core import indexer, fsio, paths


def vault_handoff(state: dict, config: Config,
                  conn: sqlite3.Connection) -> dict:
    note_id = str(ULID())
    now = datetime.now(timezone.utc).isoformat()
    project = state.get("project")

    body_lines = ["# Session Handoff", "", "## Open Decisions"]
    body_lines += [f"- {d}" for d in state.get("decisions", [])] or ["- (none)"]
    body_lines += ["", "## Active Files"]
    body_lines += [f"- {f}" for f in state.get("files", [])] or ["- (none)"]
    body_lines += ["", "## Next Steps"]
    body_lines += [f"- {s}" for s in state.get("next_steps", [])] or ["- (none)"]
    body_lines += ["", f"## Git Branch\n{state.get('branch', 'unknown')}"]
    body = "\n".join(body_lines)

    note = {
        "id": note_id, "title": f"Handoff {now[:16]}",
        "tldr": f"Session handoff for {project or 'global'}",
        "type": "session", "confidence": "fact", "scope": "project",
        "project": project, "status": "active", "created": now,
        "updated": now, "author": "claude",
        "tags": ["tipo/session", "maturidade/stable", "dominio/process"],
        "confidentiality": "internal", "schema_version": 1,
        "session_id": note_id,
    }
    target = paths.target_path(config.vault_root, note)
    fsio.atomic_write(target, fsio.format_markdown(note, body))
    indexer.upsert_note(conn, note, indexer.compute_hash(body), str(target), body)
    paths.log_activity(config.activity_log, "handoff", note_id,
                       {"project": project})
    return {"status": "ok", "note_id": note_id, "path": str(target)}


def find_latest_handoff(vault_root: Path, project: str | None = None) -> Path | None:
    sessions = vault_root / "sessoes"
    if not sessions.exists():
        return None
    handoffs = sorted(sessions.glob("handoff-*.md"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    if not handoffs:
        return None
    if not project:
        return handoffs[0]
    for h in handoffs:
        if f"project: {project}" in h.read_text(encoding="utf-8"):
            return h
    return handoffs[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_handoff.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/handoff.py tests/test_handoff.py && git commit -m "feat: vault_handoff session note + find_latest_handoff"
```

---

### Task 3.2: Status + hub notes

**Files:**
- Create: `H:\Engram\engram\core\hubs.py`
- Test: `H:\Engram\tests\test_hubs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hubs.py
from engram.core.hubs import vault_status, hub_notes

def _seed(db):
    for nid, title in [("n1","A"),("n2","B"),("n3","C")]:
        db.execute(
            "INSERT INTO notes (id,title,tldr,type,confidence,scope,status,"
            "created,updated,file_path,tags_json) VALUES "
            "(?,?,?, 'decision','fact','project','active','c','u',?,?)",
            (nid, title, "x", f"/v/{nid}.md", "[]"))
    db.commit()

def test_vault_status_counts(db):
    _seed(db)
    st = vault_status(db, activity_log=None)
    assert st["total_notes"] == 3
    assert st["by_type"]["decision"] == 3

def test_hub_notes_ranked_by_inbound_links(db, vault):
    _seed(db)
    (vault / "n2.md").write_text("---\nid: n2\nrelated: ['[[n1]]']\n---\n\nx",
                                 encoding="utf-8")
    (vault / "n3.md").write_text("---\nid: n3\nrelated: ['[[n1]]']\n---\n\nx",
                                 encoding="utf-8")
    db.execute("UPDATE notes SET file_path=? WHERE id='n2'", (str(vault/"n2.md"),))
    db.execute("UPDATE notes SET file_path=? WHERE id='n3'", (str(vault/"n3.md"),))
    db.commit()
    hubs = hub_notes(db, vault, top=5)
    assert hubs[0]["id"] == "n1"
    assert hubs[0]["inbound"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_hubs.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/hubs.py`**

```python
from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)")


def vault_status(conn: sqlite3.Connection, activity_log: Path | None) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    by_type = dict(conn.execute(
        "SELECT type, COUNT(*) FROM notes GROUP BY type").fetchall())
    by_conf = dict(conn.execute(
        "SELECT confidence, COUNT(*) FROM notes GROUP BY confidence").fetchall())
    return {"total_notes": total, "by_type": by_type, "by_confidence": by_conf}


def hub_notes(conn: sqlite3.Connection, vault_root: Path, top: int = 5) -> list[dict]:
    rows = conn.execute("SELECT id, title, file_path FROM notes").fetchall()
    inbound: Counter = Counter()
    id_to_title = {}
    for nid, title, fpath in rows:
        id_to_title[nid] = title
        p = Path(fpath)
        if not p.exists():
            continue
        for target in WIKILINK_RE.findall(p.read_text(encoding="utf-8")):
            inbound[target.strip()] += 1
    return [{"id": nid, "title": id_to_title.get(nid, nid), "inbound": cnt}
            for nid, cnt in inbound.most_common(top) if nid in id_to_title]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_hubs.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/hubs.py tests/test_hubs.py && git commit -m "feat: vault_status + hub notes (inbound wikilink centrality)"
```

---

### Task 3.3: MCP server (6 tools)

**Files:**
- Create: `H:\Engram\engram\server.py`
- Test: `H:\Engram\tests\test_tools_contract.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_contract.py
import engram.server as srv
from engram.models import NoteData, NoteType, Confidence

def test_tool_save_and_query_roundtrip(config, db, monkeypatch):
    monkeypatch.setattr(srv, "_CONFIG", config)
    monkeypatch.setattr(srv, "_CONN", db)
    srv._RATE.__init__(max_calls=100, window_seconds=60)
    n = NoteData(title="Redis", tldr="cache decision", type=NoteType.DECISION,
                 confidence=Confidence.FACT, scope="project", project="proj",
                 tags=["tipo/decision","maturidade/stable","dominio/backend"])
    save_res = srv._save_impl(n, "Redis chosen.")
    assert save_res["status"] == "ok"
    q = srv._query_impl({"text": "redis", "project": "proj"})
    assert q["match_count"] >= 1

def test_rate_limit_enforced(config, db, monkeypatch):
    monkeypatch.setattr(srv, "_CONFIG", config)
    monkeypatch.setattr(srv, "_CONN", db)
    srv._RATE.__init__(max_calls=1, window_seconds=60)
    srv._query_impl({"text": "x"})
    q2 = srv._query_impl({"text": "x"})
    assert q2["status"] == "error"
    assert "rate" in q2["reason"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_tools_contract.py -v`
Expected: FAIL with `ModuleNotFoundError` or `AttributeError`

- [ ] **Step 3: Write `engram/server.py`**

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from engram.config import load_config
from engram.core.db import connect, init_schema
from engram.core.rate_limit import RateLimiter
from engram.core import reader, router, hubs, handoff
from engram.core.writer import vault_save, vault_update
from engram.models import NoteData, QueryRequest

_CONFIG = load_config()
_CONN = connect(_CONFIG.db_path)
init_schema(_CONN)
_RATE = RateLimiter(_CONFIG.rate_calls, _CONFIG.rate_window_seconds)

mcp = FastMCP("Engram")


def _rl(tool: str) -> dict | None:
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
    return reader.path_a(q, _CONN)


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
def vault_query_tool(query: dict) -> dict:
    """Query the vault (router auto-selects lightweight vs heavy)."""
    return _query_impl(query)


@mcp.tool()
def vault_deep_query_tool(query: dict) -> dict:
    """Force a heavy semantic query (embeddings + synthesis)."""
    return _deep_query_impl(query)


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_tools_contract.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/server.py tests/test_tools_contract.py && git commit -m "feat: FastMCP server exposing 6 tools with rate limiting"
```

---

### Task 3.4: Hooks (PreToolUse + SessionStart)

**Files:**
- Create: `H:\Engram\engram\hooks\pre_tool_use.py`
- Create: `H:\Engram\engram\hooks\session_start.py`
- Test: `H:\Engram\tests\test_hooks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hooks.py
from engram.hooks.pre_tool_use import compute_flag

def test_flag_normal_under_35():
    assert compute_flag(0, 1000, 200_000)["threshold"] == "normal"

def test_flag_warning_between_35_50():
    assert compute_flag(72_000, 0, 200_000)["threshold"] == "warning"

def test_flag_critical_over_50():
    assert compute_flag(100_001, 0, 200_000)["threshold"] == "critical"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_hooks.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/hooks/pre_tool_use.py`**

```python
#!/usr/bin/env python3
"""PreToolUse hook — context monitor. Reads {"tool_name","tool_input"} on stdin."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

FLAG_FILE = Path(tempfile.gettempdir()) / "engram_ctx_flag"
MODEL_LIMIT = 200_000
WARN_PCT = 35
CRIT_PCT = 50


def estimate_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return len(text) // 4


def compute_flag(prev_tokens: int, increment: int, limit: int) -> dict:
    tokens = prev_tokens + increment
    pct = tokens / limit * 100
    threshold = "normal" if pct < WARN_PCT else "warning" if pct < CRIT_PCT else "critical"
    return {"tokens": tokens, "pct": round(pct, 1), "threshold": threshold}


def main():
    data = json.loads(sys.stdin.read() or "{}")
    prev = 0
    if FLAG_FILE.exists():
        try:
            prev = json.loads(FLAG_FILE.read_text()).get("tokens", 0)
        except Exception:
            prev = 0
    inc = estimate_tokens(json.dumps(data.get("tool_input", {})))
    flag = compute_flag(prev, inc, MODEL_LIMIT)
    FLAG_FILE.write_text(json.dumps(flag))
    pct = flag["pct"]
    if flag["threshold"] == "critical":
        print(json.dumps({"additionalContext":
              f"[CONTEXT CRITICAL: {pct:.0f}%] Initiate handoff NOW via vault.handoff()."}))
    elif flag["threshold"] == "warning":
        print(json.dumps({"additionalContext":
              f"[CONTEXT WARNING: {pct:.0f}%] Be concise; prepare handoff."}))
    else:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `engram/hooks/session_start.py`**

```python
#!/usr/bin/env python3
"""SessionStart hook — inject latest handoff as additionalContext."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from engram.config import load_config
from engram.core.handoff import find_latest_handoff


def main():
    flag = Path(tempfile.gettempdir()) / "engram_ctx_flag"
    flag.write_text(json.dumps({"tokens": 0, "pct": 0.0, "threshold": "normal"}))

    config = load_config()
    project = os.environ.get("ENGRAM_ACTIVE_PROJECT")
    latest = find_latest_handoff(config.vault_root, project)
    if not latest:
        print(json.dumps({}))
        return
    body = latest.read_text(encoding="utf-8")
    print(json.dumps({"additionalContext":
          f"[ENGRAM HANDOFF — resume from previous session]\n\n{body}"}))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_hooks.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
cd /h/Engram && git add engram/hooks tests/test_hooks.py && git commit -m "feat: PreToolUse (context monitor) + SessionStart (handoff inject) hooks"
```

---

# Phase F4 — Graphify features

**DoD:** reindex, watcher, graphify import, clustering tested isolated.

### Task 4.1: Reindex (SHA256 incremental)

**Files:**
- Create: `H:\Engram\engram\core\reindex.py`
- Test: `H:\Engram\tests\test_reindex.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reindex.py
from engram.core.reindex import reindex_file, reindex_all

def _write_note(vault, nid, body):
    p = vault / "projetos" / "proj" / "decisoes" / f"{nid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nid: {nid}\ntitle: {nid}\ntldr: t\ntype: decision\n"
                 f"confidence: fact\nscope: project\nproject: proj\n"
                 f"status: active\ncreated: c\nupdated: u\n"
                 f"tags: ['tipo/decision']\n---\n\n{body}", encoding="utf-8")
    return p

def test_reindex_file_inserts(db, vault, config):
    p = _write_note(vault, "n1", "body one")
    assert reindex_file(db, p, config) is True
    row = db.execute("SELECT title FROM notes WHERE id='n1'").fetchone()
    assert row[0] == "n1"

def test_reindex_skips_unchanged(db, vault, config):
    p = _write_note(vault, "n1", "body one")
    reindex_file(db, p, config)
    assert reindex_file(db, p, config) is False

def test_reindex_all_counts(db, vault, config):
    _write_note(vault, "n1", "b1")
    _write_note(vault, "n2", "b2")
    stats = reindex_all(db, config)
    assert stats["indexed"] == 2
    assert stats["skipped"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_reindex.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/reindex.py`**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from engram.config import Config
from engram.core import indexer


def _parse(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
        body = parts[2].strip() if len(parts) >= 3 else text
        return fm or {}, body
    return {}, text


def reindex_file(conn: sqlite3.Connection, path: Path, config: Config) -> bool:
    """Index one note. Returns False if unchanged (hash match)."""
    fm, body = _parse(path)
    if not fm.get("id"):
        return False
    new_hash = indexer.compute_hash(body)
    row = conn.execute("SELECT content_hash FROM notes WHERE id = ?",
                       (fm["id"],)).fetchone()
    if row and row[0] == new_hash:
        return False
    indexer.upsert_note(conn, fm, new_hash, str(path), body)
    return True


def reindex_all(conn: sqlite3.Connection, config: Config) -> dict:
    indexed = skipped = 0
    for sub in ("projetos", "global", "sessoes"):
        base = config.vault_root / sub
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            if "/_cold/" in path.as_posix():
                continue
            if reindex_file(conn, path, config):
                indexed += 1
            else:
                skipped += 1
    return {"indexed": indexed, "skipped": skipped}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_reindex.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/reindex.py tests/test_reindex.py && git commit -m "feat: reindex with SHA256 incremental skip (hash match)"
```

---

### Task 4.2: Watcher (watchdog incremental)

**Files:**
- Create: `H:\Engram\engram\core\watcher.py`
- Test: `H:\Engram\tests\test_watcher.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_watcher.py
from engram.core.watcher import VaultEventHandler

def test_handler_reindexes_on_modify(db, vault, config):
    p = vault / "projetos" / "proj" / "decisoes" / "n1.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nid: n1\ntitle: N1\ntldr: t\ntype: decision\n"
                 "confidence: fact\nscope: project\nproject: proj\n"
                 "status: active\ncreated: c\nupdated: u\n"
                 "tags: ['tipo/decision']\n---\n\nbody", encoding="utf-8")
    handler = VaultEventHandler(db, config)
    handler.handle_path(str(p))
    row = db.execute("SELECT title FROM notes WHERE id='n1'").fetchone()
    assert row[0] == "N1"

def test_handler_ignores_non_md(db, vault, config):
    handler = VaultEventHandler(db, config)
    handler.handle_path(str(vault / "notes.txt"))  # no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_watcher.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/watcher.py`**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from engram.config import Config
from engram.core.reindex import reindex_file


class VaultEventHandler(FileSystemEventHandler):
    def __init__(self, conn: sqlite3.Connection, config: Config):
        self.conn = conn
        self.config = config

    def handle_path(self, path_str: str) -> None:
        path = Path(path_str)
        if path.suffix != ".md" or path.name.endswith(".tmp"):
            return
        if not path.exists():
            return
        try:
            reindex_file(self.conn, path, self.config)
        except Exception:
            pass

    def on_modified(self, event):
        if not event.is_directory:
            self.handle_path(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self.handle_path(event.src_path)


def watch(conn: sqlite3.Connection, config: Config) -> None:
    handler = VaultEventHandler(conn, config)
    observer = Observer()
    observer.schedule(handler, str(config.vault_root), recursive=True)
    observer.start()
    try:
        while True:
            observer.join(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_watcher.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/watcher.py tests/test_watcher.py && git commit -m "feat: watchdog vault watcher with incremental reindex"
```

---

### Task 4.3: Graphify importer

**Files:**
- Create: `H:\Engram\engram\importers\graphify.py`
- Test: `H:\Engram\tests\test_graphify_import.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graphify_import.py
import json
from engram.importers.graphify import import_graph

def _graph(tmp_path):
    g = {
        "nodes": [
            {"id": "AuthService", "type": "module",
             "summary": "Handles authentication", "tag": "EXTRACTED"},
            {"id": "Database", "type": "module",
             "summary": "Postgres store", "tag": "INFERRED"},
        ],
        "edges": [
            {"source": "AuthService", "target": "Database", "tag": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(g), encoding="utf-8")
    return p

def test_import_creates_context_notes(config, db, vault, tmp_path):
    res = import_graph(_graph(tmp_path), project="proj", config=config, conn=db)
    assert res["created"] == 2
    types = {r[0] for r in db.execute("SELECT type FROM notes").fetchall()}
    assert types == {"context"}

def test_confidence_mapping(config, db, vault, tmp_path):
    import_graph(_graph(tmp_path), project="proj", config=config, conn=db)
    confs = dict(db.execute("SELECT title, confidence FROM notes").fetchall())
    assert confs["AuthService"] == "fact"
    assert confs["Database"] == "inference"

def test_edges_become_related(config, db, vault, tmp_path):
    import_graph(_graph(tmp_path), project="proj", config=config, conn=db)
    row = db.execute("SELECT file_path FROM notes WHERE title='AuthService'").fetchone()
    assert "database" in open(row[0], encoding="utf-8").read().lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_graphify_import.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/importers/graphify.py`**

```python
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from engram.config import Config
from engram.core import indexer, fsio, paths

CONFIDENCE_MAP = {
    "EXTRACTED": "fact",
    "INFERRED": "inference",
    "AMBIGUOUS": "hypothesis",
}


def _slug(node_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", node_id).strip("-").lower()


def import_graph(graph_path: Path, project: str, config: Config,
                 conn: sqlite3.Connection) -> dict:
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e["source"], []).append(e["target"])

    now = datetime.now(timezone.utc).isoformat()
    created = 0
    for node in nodes:
        nid = node["id"]
        slug = _slug(nid)
        conf = CONFIDENCE_MAP.get(node.get("tag", "AMBIGUOUS"), "hypothesis")
        related = [f"[[{_slug(t)}]]" for t in adj.get(nid, [])]
        summary = node.get("summary", "")
        note = {
            "id": slug, "title": nid,
            "tldr": (summary[:100] or f"Imported node {nid}"),
            "type": "context", "confidence": conf, "scope": "project",
            "project": project, "status": "active", "created": now,
            "updated": now, "author": "graphify-import",
            "tags": ["tipo/context", "maturidade/experimental", "dominio/architecture"],
            "related": related, "confidentiality": "internal", "schema_version": 1,
        }
        body = (f"# {nid}\n\n{summary}\n\n## Connections\n" +
                ("\n".join(f"- [[{_slug(t)}]]" for t in adj.get(nid, []))
                 or "- (none)"))
        target = paths.target_path(config.vault_root, note)
        fsio.atomic_write(target, fsio.format_markdown(note, body))
        indexer.upsert_note(conn, note, indexer.compute_hash(body),
                            str(target), body)
        created += 1

    paths.log_activity(config.activity_log, "graphify_import", project,
                       {"created": created, "edges": len(edges)})
    return {"status": "ok", "created": created, "edges": len(edges)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_graphify_import.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/importers/graphify.py tests/test_graphify_import.py && git commit -m "feat: graphify import (nodes→context notes, edges→related, tag→confidence)"
```

---

### Task 4.4: Clustering (cosine-threshold components)

**Files:**
- Create: `H:\Engram\engram\core\clustering.py`
- Test: `H:\Engram\tests\test_clustering.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_clustering.py
import pytest
from engram.core.clustering import cluster_notes, _cosine

def test_cosine_identical():
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

def test_cosine_orthogonal():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

def test_cluster_groups_similar(db, vault, config):
    from sqlite_vec import serialize_float32
    groups = {
        "a1": [1.0, 0.0, 0.0], "a2": [0.9, 0.1, 0.0],
        "b1": [0.0, 0.0, 1.0], "b2": [0.0, 0.1, 0.9],
    }
    for nid, vec in groups.items():
        full = vec + [0.0] * (1024 - len(vec))
        db.execute("INSERT INTO notes (id,title,tldr,type,confidence,scope,"
                   "project,status,created,updated,file_path) VALUES "
                   "(?,?,?, 'concept','inference','project','proj','active',"
                   "'c','u',?)", (nid, nid, "t", f"/v/{nid}.md"))
        db.execute("INSERT INTO notes_vec(note_id,embedding) VALUES (?,?)",
                   (nid, serialize_float32(full)))
    db.commit()
    result = cluster_notes(db, config, project="proj", threshold=0.8)
    assert result["num_clusters"] == 2
    assert (vault / "projetos" / "proj" / "_clusters.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_clustering.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/core/clustering.py`**

```python
from __future__ import annotations

import math
import sqlite3
import struct
from pathlib import Path

from engram.config import Config


def _deserialize(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _connected_components(n: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def cluster_notes(conn: sqlite3.Connection, config: Config, project: str,
                  threshold: float = 0.75) -> dict:
    rows = conn.execute(
        "SELECT n.id, n.title, v.embedding FROM notes n "
        "JOIN notes_vec v ON v.note_id = n.id "
        "WHERE n.project = ? AND n.status != 'archived'", (project,)
    ).fetchall()
    ids = [r[0] for r in rows]
    titles = {r[0]: r[1] for r in rows}
    vecs = {r[0]: _deserialize(r[2]) for r in rows}

    edges = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if _cosine(vecs[ids[i]], vecs[ids[j]]) >= threshold:
                edges.append((i, j))

    clusters = _connected_components(len(ids), edges)

    lines = [f"# Clusters — {project}", ""]
    for ci, members in enumerate(clusters, 1):
        lines.append(f"## Cluster {ci}")
        for m in members:
            lines.append(f"- [[{ids[m]}]] {titles[ids[m]]}")
        lines.append("")
    out = config.vault_root / "projetos" / project / "_clusters.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    return {"status": "ok", "num_clusters": len(clusters), "path": str(out)}
```

> **Note on Leiden:** the spec named Leiden. For determinism, simplicity, and zero extra C-extension dependency, v3.0 uses cosine-threshold connected components — deterministic and testable, equivalent quality for small vaults. `python-igraph`/`leidenalg` are optional extras; swapping in true Leiden is a drop-in replacement of `_connected_components` when vaults grow large enough to need modularity optimization. Keeps default install lean (priority: efficiency) and clustering deterministic (priority: quality).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_clustering.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/core/clustering.py tests/test_clustering.py && git commit -m "feat: clustering (cosine-threshold components) → _clusters.md per project"
```

---

# Phase F5 — CLI + docs + migration

**DoD:** CLI works; doc complete; existing vault migrates with confidence backfill.

### Task 5.1: CLI (Typer)

**Files:**
- Create: `H:\Engram\engram\cli.py`
- Test: `H:\Engram\tests\test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from typer.testing import CliRunner
from engram.cli import app

runner = CliRunner()

def test_status_command(monkeypatch, config, db):
    import engram.cli as cli
    monkeypatch.setattr(cli, "_load", lambda: (config, db))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "total_notes" in result.stdout

def test_reindex_command(monkeypatch, config, db, vault):
    import engram.cli as cli
    monkeypatch.setattr(cli, "_load", lambda: (config, db))
    p = vault / "projetos" / "proj" / "decisoes" / "n1.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nid: n1\ntitle: N1\ntldr: t\ntype: decision\n"
                 "confidence: fact\nscope: project\nproject: proj\n"
                 "status: active\ncreated: c\nupdated: u\n"
                 "tags: ['tipo/decision']\n---\n\nbody", encoding="utf-8")
    result = runner.invoke(app, ["reindex"])
    assert result.exit_code == 0
    assert "indexed" in result.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `engram/cli.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

import typer

from engram.config import load_config
from engram.core.db import connect, init_schema

app = typer.Typer(help="Engram — persistent dev memory")


def _load():
    config = load_config()
    conn = connect(config.db_path)
    init_schema(conn)
    return config, conn


@app.command()
def status():
    """Show vault stats and hub notes."""
    from engram.core import hubs
    config, conn = _load()
    st = hubs.vault_status(conn, config.activity_log)
    st["hubs"] = hubs.hub_notes(conn, config.vault_root, top=5)
    typer.echo(json.dumps(st, indent=2, ensure_ascii=False))


@app.command()
def reindex():
    """Rebuild SQLite index (incremental, hash-skipped)."""
    from engram.core.reindex import reindex_all
    config, conn = _load()
    stats = reindex_all(conn, config)
    typer.echo(f"Reindex complete: {stats['indexed']} indexed, "
               f"{stats['skipped']} skipped (unchanged).")


@app.command()
def watch():
    """Watch vault for external edits and reindex incrementally."""
    from engram.core.watcher import watch as run_watch
    config, conn = _load()
    typer.echo(f"Watching {config.vault_root} ... (Ctrl-C to stop)")
    run_watch(conn, config)


@app.command("import-graph")
def import_graph_cmd(graph_path: str, project: str):
    """Import a Graphify graph.json into the vault."""
    from engram.importers.graphify import import_graph
    config, conn = _load()
    res = import_graph(Path(graph_path), project, config, conn)
    typer.echo(f"Imported {res['created']} nodes, {res['edges']} edges.")


@app.command()
def cluster(project: str, threshold: float = 0.75):
    """Cluster notes by embedding similarity → _clusters.md."""
    from engram.core.clustering import cluster_notes
    config, conn = _load()
    res = cluster_notes(conn, config, project, threshold)
    typer.echo(f"{res['num_clusters']} clusters → {res['path']}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_cli.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add engram/cli.py tests/test_cli.py && git commit -m "feat: Typer CLI (status, reindex, watch, import-graph, cluster)"
```

---

### Task 5.2: Migration script (confidence backfill)

**Files:**
- Create: `H:\Engram\scripts\migrate_v2_to_v3.py`
- Create: `H:\Engram\scripts\__init__.py`
- Test: `H:\Engram\tests\test_migration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migration.py
from scripts.migrate_v2_to_v3 import infer_confidence, migrate_note_text

def test_infer_confidence_decision_fact():
    assert infer_confidence({"type": "decision", "status": "active"}) == "fact"

def test_infer_confidence_pattern_inference():
    assert infer_confidence({"type": "pattern"}) == "inference"

def test_infer_confidence_open_hypothesis():
    assert infer_confidence({"type": "context", "status": "draft"}) == "hypothesis"

def test_migrate_adds_confidence_field():
    text = ("---\nid: n1\ntitle: T\ntype: decision\nstatus: active\n"
            "tags: ['tipo/decision']\n---\n\nbody")
    out, changed = migrate_note_text(text)
    assert changed is True
    assert "confidence: fact" in out

def test_migrate_skips_if_present():
    text = ("---\nid: n1\ntype: decision\nconfidence: inference\n"
            "status: active\n---\n\nbody")
    out, changed = migrate_note_text(text)
    assert changed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /h/Engram && pytest tests/test_migration.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `scripts/migrate_v2_to_v3.py`**

```python
#!/usr/bin/env python3
"""Migrate v2.2 vault notes to v3.0: backfill confidence field.

Usage: python scripts/migrate_v2_to_v3.py /path/to/vault [--apply]
Default is dry-run (prints what would change). Pass --apply to write.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml


def infer_confidence(fm: dict) -> str:
    ntype = fm.get("type", "")
    status = fm.get("status", "active")
    if status in ("draft", "proposed", "open"):
        return "hypothesis"
    if ntype in ("decision", "bug", "runbook", "session"):
        return "fact"
    if ntype in ("pattern", "concept", "context"):
        return "inference"
    return "hypothesis"


def migrate_note_text(text: str) -> tuple[str, bool]:
    if not text.startswith("---"):
        return text, False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text, False
    fm = yaml.safe_load(parts[1]) or {}
    if fm.get("confidence"):
        return text, False
    fm["confidence"] = infer_confidence(fm)
    new_fm = yaml.dump(fm, default_flow_style=False, allow_unicode=True,
                       sort_keys=False, width=120)
    return f"---\n{new_fm}---{parts[2]}", True


def main():
    if len(sys.argv) < 2:
        print("Usage: migrate_v2_to_v3.py <vault> [--apply]")
        sys.exit(1)
    vault = Path(sys.argv[1])
    apply = "--apply" in sys.argv
    changed = 0
    for md in vault.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        new_text, did = migrate_note_text(text)
        if did:
            changed += 1
            print(f"{'WRITE' if apply else 'DRY'}: {md} → confidence added")
            if apply:
                md.write_text(new_text, encoding="utf-8")
    print(f"\n{changed} notes {'migrated' if apply else 'would change'}.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create `scripts/__init__.py`** (empty file, so tests import it)

```python
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /h/Engram && pytest tests/test_migration.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
cd /h/Engram && git add scripts/migrate_v2_to_v3.py scripts/__init__.py tests/test_migration.py && git commit -m "feat: v2→v3 migration script (confidence backfill, dry-run default)"
```

---

### Task 5.3: README + full system doc + Claude Code config

**Files:**
- Create: `H:\Engram\README.md`
- Create: `H:\Engram\docs\engram-v3.md`
- Create: `H:\Engram\claude-config-snippet.json`

- [ ] **Step 1: Write `H:\Engram\README.md`**

````markdown
# Engram

Persistent memory MCP server for software development with Claude Code.
Captures decisions, bugs, patterns, and session state into an Obsidian vault
indexed by SQLite (FTS5 + sqlite-vec). Retrieves context efficiently via a
dual-path router. Zero-LLM writes; local-Ollama-only reads.

## Install

```bash
cd H:\Engram
pip install -e ".[dev]"
# optional true-Leiden clustering:
# pip install -e ".[clustering]"
```

## Configure

Copy `engram.toml.example` to `engram.toml` and set `vault.root`. Or set
`ENGRAM_VAULT_ROOT`. Default vault: `~/.engram/vault`.

To use the existing vault:
```toml
[vault]
root = "C:/Users/ianfl/dev-vault"
```

## Run the MCP server

```bash
engram-server
```

Register in Claude Code `.claude/settings.json` (see `claude-config-snippet.json`).

## CLI (token-free operations)

```bash
engram status                         # stats + hub notes
engram reindex                        # incremental SQLite rebuild
engram watch                          # auto-reindex on external edits
engram import-graph graph.json proj   # import a Graphify graph
engram cluster proj --threshold 0.75  # cluster notes → _clusters.md
```

## Migrate an existing v2.2 vault

```bash
python scripts/migrate_v2_to_v3.py C:/Users/ianfl/dev-vault          # dry run
python scripts/migrate_v2_to_v3.py C:/Users/ianfl/dev-vault --apply  # write
engram reindex
```

## Architecture

See `docs/engram-v3.md` and `docs/specs/2026-06-01-engram-v3-design.md`.

## Test

```bash
pytest                 # all
pytest --cov=engram    # with coverage
```
````

- [ ] **Step 2: Write `H:\Engram\docs\engram-v3.md`**

Write the full system doc. Use `docs/specs/2026-06-01-engram-v3-design.md` as the source of truth and adapt the structure of the prior v2.2 document (`C:\Users\ianfl\Downloads\sistema-memoria-dev.md`) to v3.0:
- Rename "dev-vault"/"v2.2" to "Engram"/"v3.0" throughout.
- Replace the `_pending/`+sweeper section with the atomic-write (`os.replace`) + portalocker approach and the 4 Obsidian conflict scenarios (spec §5.2–5.3).
- Add the `confidence` field everywhere note schemas/frontmatter appear (spec §4.2–4.3).
- Add a "Six Graphify-inspired features" section (spec §7).
- Document the CLI commands (spec §7 interface column + README).
- Update tool list to the 6 tools in spec §9 with the exact names.
- Embed updated Mermaid flowcharts adapted from `C:\Users\ianfl\Downloads\dev-vault-flowchart.md`: remove the sweeper subgraph, rename actors to Engram, add a `confidence` step to the write-path diagram.

This is a documentation task: produce the complete doc following the spec section order. No placeholders or "TODO" markers.

- [ ] **Step 3: Write `H:\Engram\claude-config-snippet.json`**

```json
{
  "mcpServers": {
    "engram": {
      "command": "engram-server"
    }
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "command": "python -m engram.hooks.pre_tool_use"
      }
    ],
    "SessionStart": [
      {
        "command": "python -m engram.hooks.session_start"
      }
    ]
  }
}
```

- [ ] **Step 4: Run full test suite + coverage**

Run: `cd /h/Engram && pytest --cov=engram --cov-report=term-missing`
Expected: PASS (all tests); coverage ≥ 80% on `engram/core`

- [ ] **Step 5: Commit**

```bash
cd /h/Engram && git add README.md docs/engram-v3.md claude-config-snippet.json && git commit -m "docs: README, full v3.0 system doc, Claude Code config snippet"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by |
|--------------|-----------|
| §3 Architecture (modular monolith) | F0 structure, all core/ modules |
| §4.1 NoteType (7+4) | Task 0.3 (enum), Task 1.6 (config-gated) |
| §4.2 Confidence enum | Task 0.3, 1.1, throughout |
| §4.4 SQLite schema (FTS5 + vec) | Task 0.4 |
| §5 Write path (atomic, lock, no sweeper) | Tasks 1.3, 1.4, 1.6 |
| §5.3 Obsidian conflict handling | Task 1.3 (atomic + stale .tmp cleanup), 1.7 (human-edit preserve) |
| §5.5 vault_update | Task 1.7 |
| §6 Read path (router, A, B, fallback) | Tasks 2.2, 2.3, 2.4 |
| §6.4 never-blocks fallback | Task 2.4 (2 fallback levels) |
| §7.1 Confidence tags | Tasks 0.3, 1.1, 2.3, 2.4 |
| §7.2 SHA256 incremental | Task 4.1 |
| §7.3 Watch mode | Task 4.2 |
| §7.4 Hub notes | Task 3.2 |
| §7.5 Graphify import | Task 4.3 |
| §7.6 Clustering | Task 4.4 |
| §8 Handoff + hooks | Tasks 3.1, 3.4 |
| §9 6 MCP tools | Task 3.3 |
| §10 Config | Task 0.2 |
| §11 Testing (TDD, mock Ollama) | conftest 0.5, every task |
| §12 Migration | Task 5.2 |

All spec sections mapped. No gaps.

**Placeholder scan:** Task 5.3 Step 2 (full system doc) is a documentation-writing instruction referencing the spec as source — inherent to a doc task, not a code placeholder. All code steps contain complete code.

**Type consistency:** `Config` fields, `NoteData`/`QueryRequest` shapes, and signatures (`vault_save`, `vault_update`, `path_a`, `path_b`, `upsert_note`, `compute_hash`, `reindex_file`, `cluster_notes`, `vault_handoff`) are consistent across tasks. sqlite-vec KNN uses verified API `WHERE embedding MATCH ? AND k = ? ORDER BY distance` (corrected from the spec's `vec_distance_L2()` note). FTS5 is contentless with explicit Python population (delete+insert, no triggers).

---

## Execution Handoff

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Choose at execution time.
