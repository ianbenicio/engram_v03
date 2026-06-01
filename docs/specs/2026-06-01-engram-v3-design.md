# Engram v3.0 — Design Spec

**Date:** 2026-06-01
**Status:** Draft for review
**Supersedes:** dev-vault memory system v2.2 (`C:\Users\ianfl\Downloads\sistema-memoria-dev.md`)
**Project root:** `H:\Engram\`

---

## 1. Purpose

Engram is an MCP server providing persistent, continuous memory for software development with Claude Code. It solves the loss of context between development sessions: decisions made, bugs solved, patterns identified, and architecture defined are captured during development, organized semantically, and retrieved efficiently — instead of being rebuilt from scratch each session (costly in tokens, slow, inconsistent).

Engram is a ground-up rebuild based on a critical analysis of the prior dev-vault v2.2 design, keeping what proved valuable, cutting over-engineered components, and adding six features inspired by Graphify.

**Priorities (in order):** efficiency → processing economy → quality.

### Name

"Engram" = the physical trace a memory leaves in the brain. Precise metaphor: notes are persistent memory traces of the development process.

---

## 2. Scope

### In scope (v3.0)

- MCP server (stdio) consumed by Claude Code
- Minimal CLI for token-free operations (reindex, watch, status, import, cluster)
- Write path: 100% Python, zero LLM
- Read path: dual-path (FTS5 lightweight vs embeddings+Qwen heavy) with intelligent router
- Session handoff (context monitoring at 35%/50% thresholds)
- 6 Graphify-inspired features (see §7)
- Configurable vault location (backward-compatible with existing `C:\Users\ianfl\dev-vault`)
- Embeddings: Ollama local only (bge-m3)

### Out of scope (deferred)

- Cold storage tier (schema prepared, implementation deferred until vault > ~500 notes)
- 4 of 11 note types (prepared via extensible enum, activated in v3.1)
- API embedding fallback (Ollama-only by decision)
- Web UI / dashboard (over-engineering for current scale)
- `_pending/` + sweeper daemon (cut — see §5)

---

## 3. Architecture

### 3.1 Approach: Monólito Modular

Single Python package. One process serves both MCP and CLI. Shared state (SQLite connection, config) via core modules. Chosen over microkernel/layered approaches because: project is 1-2 devs, efficiency is the priority (fewer abstractions = less overhead), and YAGNI (refactor to plugin/layered later if it grows).

### 3.2 Directory structure

```
H:\Engram\
├── engram/
│   ├── __init__.py
│   ├── config.py         # ENGRAM_VAULT_ROOT, settings, constants
│   ├── models.py         # Pydantic: NoteData, QueryRequest, Confidence enum, NoteType enum
│   ├── server.py         # MCP server (stdio) — entry point
│   ├── cli.py            # CLI: reindex, watch, status, import-graph, cluster
│   ├── core/
│   │   ├── __init__.py
│   │   ├── db.py         # SQLite conn, schema, FTS5, sqlite-vec
│   │   ├── validator.py  # tags, fields, confidence, wikilinks (SQLite-first)
│   │   ├── writer.py     # save + update (lock, hash, atomic write, format)
│   │   ├── router.py     # Path A vs B decision
│   │   ├── reader.py     # Path A (FTS5) + Path B (embed + Qwen)
│   │   ├── embeddings.py # Ollama bge-m3 (local only)
│   │   ├── rate_limit.py # in-memory 30/60s per tool
│   │   ├── hubs.py       # hub notes (degree centrality + query frequency)
│   │   ├── clustering.py # Leiden community detection
│   │   └── watcher.py    # watchdog incremental reindex
│   ├── importers/
│   │   ├── __init__.py
│   │   └── graphify.py   # graph.json → context notes
│   └── hooks/
│       ├── pre_tool_use.py
│       └── session_start.py
├── tests/
│   ├── conftest.py       # tmp vault fixture, mock Ollama
│   ├── test_validator.py
│   ├── test_writer.py
│   ├── test_router.py
│   ├── test_reader.py
│   ├── test_hubs.py
│   ├── test_clustering.py
│   ├── test_watcher.py
│   ├── test_graphify_import.py
│   └── test_tools_contract.py
├── docs/
│   ├── specs/
│   │   └── 2026-06-01-engram-v3-design.md
│   └── engram-v3.md      # full system doc (rebrand of v2.2)
├── pyproject.toml
├── engram.toml.example
└── README.md
```

**Module principle:** each `core/` module = one responsibility, independently testable, < 300 lines. All share `db.py` (connection) and `config.py` (settings).

### 3.3 Actors

| Actor | Role |
|-------|------|
| Claude Code | Orchestrator. Decides when to save/query. Synthesizes notes with full conversation context. |
| Engram MCP Server (Python) | Interface between Claude Code and vault. 6 tools. Write 100% Python; read routes Path A/B. Rate-limited. |
| Ollama (local) | bge-m3 (embeddings) + qwen3 (synthesis). Optional — system degrades to Path A if offline. |
| Obsidian Vault | Persistent markdown store. Human-navigable (Graph View). Notes never deleted (`status: archived` filters). |
| SQLite + FTS5 + sqlite-vec | Search index. Metadata + full-text + vector search. Invisible to user. |

---

## 4. Data model

### 4.1 Note types (7 active, 11 prepared)

```python
class NoteType(str, Enum):
    # v3.0 active
    DECISION = "decision"
    BUG = "bug"
    PATTERN = "pattern"
    CONTEXT = "context"
    RUNBOOK = "runbook"
    SESSION = "session"
    CONCEPT = "concept"
    # v3.1 prepared (folder mapping + templates exist; disabled in config)
    POST_MORTEM = "post-mortem"
    EXPERIMENT = "experiment"
    REFACTORING = "refactoring"
    METRIC = "metric"
```

Active types are config-driven (`engram.toml` → `enabled_types`), not hardcoded. Activating the 4 remaining = add to the list. Type→folder mapping includes all 11. Templates for all 11 already exist in the vault (`meta/templates/`).

### 4.2 Confidence enum (NEW — from Graphify)

```python
class Confidence(str, Enum):
    FACT = "fact"             # verified: test passed, decision made (~ Graphify EXTRACTED)
    INFERENCE = "inference"   # derived through analysis        (~ Graphify INFERRED)
    HYPOTHESIS = "hypothesis" # unconfirmed                     (~ Graphify AMBIGUOUS)
```

Required frontmatter field. Path B surfaces confidence on sources. Lets retrieval distinguish verified facts from guesses.

### 4.3 Frontmatter schema

Required: `id, title, tldr, type, confidence, status, created, updated, author, scope, tags`.
Tag prefixes required: `tipo/`, `maturidade/`, `dominio/`.
Optional: `subtype, parent, project, module, related[], implements, supersedes, code_refs, session_id`.

### 4.4 SQLite schema

```sql
CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    tldr TEXT,
    type TEXT NOT NULL,
    subtype TEXT,
    confidence TEXT NOT NULL,        -- NEW
    scope TEXT DEFAULT 'project',
    project TEXT,
    module TEXT,
    status TEXT DEFAULT 'active',    -- supports 'archived' (cold storage future)
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    author TEXT DEFAULT 'claude',
    tags_json TEXT,
    content_hash TEXT,               -- SHA-256[:32]
    file_path TEXT,                  -- any path (cold storage future = path change)
    confidentiality TEXT DEFAULT 'internal',
    schema_version INTEGER DEFAULT 1
);

CREATE VIRTUAL TABLE notes_fts USING fts5(
    title, tldr, tags_text, body_snippet,
    content=''                        -- contentless, populated via Python (no triggers)
);

-- notes_vec: sqlite-vec virtual table for embeddings (bge-m3, 1024-dim)
-- created at runtime after load_extension('vec0')
```

Cold storage future-proofing: `status` already supports `archived`; `file_path` accepts any path. Moving to cold = path update + filter, no schema change.

---

## 5. Write path (simplified — sweeper cut)

### 5.1 Decision: cut `_pending/` + sweeper daemon

The v2.2 sweeper wrote to `_pending/`, ran a daemon thread checking every 5s if Obsidian was idle, then moved files to the final folder. **Cut.** It solved a rare problem (simultaneous Obsidian edit of the exact note Claude is writing) with high cost (extra thread, race conditions, .meta.json bookkeeping, 5s latency, deferred SQLite consistency).

### 5.2 Replacement: atomic write + lock

The real risk (concurrent/partial write) is fully covered by two cheap mechanisms:

1. **portalocker** — exclusive cross-platform lock during write.
2. **Atomic write** — write to `.tmp`, then `os.replace()` (atomic on Windows + POSIX). Obsidian never sees a partial file. A crash mid-write leaves the `.tmp`, never a corrupt target.

```python
tmp = target.with_suffix(target.suffix + ".tmp")
tmp.write_text(markdown, encoding="utf-8")
os.replace(tmp, target)   # atomic
```

### 5.3 Obsidian conflict handling (worked-through)

| Scenario | Handling |
|----------|----------|
| Obsidian has note X open, Engram updates X | `os.replace` writes complete file. Obsidian detects external change and reloads (its native behavior). No corruption. |
| Human edits X in Obsidian while Engram writes X | portalocker serializes. Last writer wins at file level. Mitigated: `vault.update` reads current file before writing, preserving human edits to other fields; only changed fields overwritten. |
| Crash mid-write | `.tmp` orphan left; target untouched. Startup cleanup removes stale `.tmp` files older than 60s. |
| Concurrent Engram writes (multi-agent future) | portalocker exclusive lock serializes. Each acquires, writes, releases. |

**Trade-off acknowledged:** if the future brings multiple agents writing concurrently *plus* a human editing the same notes live, a queue/sweeper may return. Not the current case (YAGNI). Schema and lock design do not block re-adding it.

### 5.4 vault_save() pipeline (zero LLM)

```
Claude → vault.save(note_data, body)
  1. rate_limit check (30/60s)
  2. generate ULID if no id
  3. set timestamps + defaults (confidence required, no silent default)
  4. validate required fields (incl. confidence)
  5. validate tags against vocab (meta/tags.md + project custom_tags)
  6. validate required tag prefixes (tipo/, maturidade/, dominio/)
  7. validate module against project _index.md (warning, non-blocking)
  8. validate tldr length (≤ 20 words, warning)
  9. compute SHA-256[:32] hash + duplicate check
  10. validate wikilinks in related[] (SQLite-first, fs fallback)
  11. determine target path (type → folder mapping)
  12. format markdown (YAML frontmatter + body)
  13. acquire lock → atomic write (.tmp → os.replace) → release lock
  14. insert SQLite + FTS5 (Python) + embedding (if Ollama on)
  15. log activity.jsonl
  16. return {note_id, path, warnings}
```

### 5.5 vault_update() — partial edit

Immutable fields: `id, created, type, subtype, parent`. Reads existing note, applies field updates, preserves untouched fields, recomputes hash only if body changed, re-validates changed tags/wikilinks, atomic write, updates SQLite.

---

## 6. Read path (dual-path + router)

### 6.1 Router decision

```
depth == "deep"              → Path B
multi-project or "*"         → Path B
semantic intent (18 regex)   → Path B   (bilingual PT + EN)
FTS5 match_count > 5         → Path B
else                         → Path A
```

### 6.2 Path A (lightweight, ~70% queries)

FTS5 search by tags + project + keywords. Returns concatenated TL;DRs. Zero LLM. ~200 tokens. Filters: status (excludes archived), type, project, tags. Cold exclusion future-proofed.

### 6.3 Path B (heavy, ~30% queries)

```
1. get embedding (Ollama bge-m3)
   └─ Ollama off → full fallback to Path A
2. sqlite-vec search: vec_distance_L2()
3. filter confidentiality: restricted (never sent to external LLM)
4. read top-7 note bodies
5. Qwen synthesis (~400 words, bilingual prompt, shows confidence per source)
   └─ Qwen off → fallback: Path A + top-3 full notes (~800-1500 tokens)
```

### 6.4 Error handling — never blocks

| Failure | Behavior |
|---------|----------|
| Ollama embeddings off | Path A pure |
| Qwen synthesis off | Path A + top-3 full notes |
| Lock timeout (5s) | Explicit error, Claude retries |
| Validation fail | Structured error + vocab sample |
| Embedding fail on save | Note saved without vector; FTS5 still works |

---

## 7. Six Graphify-inspired features

| # | Feature | Integration | Interface |
|---|---------|-------------|-----------|
| 1 | **Confidence tags** | `confidence` enum in frontmatter + SQLite. Validator requires it. Path B surfaces it. | MCP (save/update) |
| 2 | **SHA256 incremental** | `reindex.py` + `watcher.py` compare file hash vs SQLite; skip if equal. Zero wasted reprocessing. | CLI |
| 3 | **Watch mode** | watchdog monitors vault; manual Obsidian edits trigger single-file reindex (hash-checked). | CLI (`engram watch`) |
| 4 | **Hub notes** | `hubs.py` = degree centrality (wikilinks in+out) + query frequency (activity.jsonl). | MCP (`vault.status`) |
| 5 | **Graphify import** | `engram import-graph graph.json` → context notes; edges → related[]; Graphify tags → confidence. | CLI |
| 6 | **Community clustering** | `clustering.py` Leiden over embedding similarity graph → `_clusters.md` per project. On-demand (CPU cost). | CLI (`engram cluster`) |

CLI-first for features 2,3,5,6 — they don't need Claude, so they cost zero tokens (priority: economy).

---

## 8. Session management & handoff

```
PreToolUse hook (every tool call):
  read flag from tempdir → estimate incremental tokens → accumulate → write flag
  < 35%   normal
  35-50%  warning: "be concise, prepare handoff"
  ≥ 50%   critical: "initiate handoff NOW" → Claude calls vault.handoff()

vault.handoff(): generates type:session note (open decisions, active files,
  next steps, git branch) → saves to sessoes/handoff-{id}.md

New session:
  SessionStart hook → finds latest handoff (by project, by mtime)
    → injects via additionalContext → Claude starts ~8% context vs ~50% at close
```

Thresholds 35%/50% (Claude reasoning degrades ~40%). Exiting early with clean context beats squeezing until incoherent.

---

## 9. MCP tools (6)

| Tool | Purpose | Path |
|------|---------|------|
| `vault.save` | Create note | Write |
| `vault.update` | Partial edit | Write |
| `vault.query` | Default query (router decides A/B) | Read |
| `vault.deep_query` | Force Path B | Read |
| `vault.status` | Vault stats + hub notes | Read |
| `vault.handoff` | Save session state | Write |

---

## 10. Configuration

```toml
# engram.toml
[vault]
root = "C:/Users/ianfl/dev-vault"   # default ~/.engram/vault ; backward-compatible

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

Override via env: `ENGRAM_VAULT_ROOT`, `ENGRAM_OLLAMA_ENDPOINT`, etc.

---

## 11. Testing strategy (spec-driven, TDD)

- **TDD per module** — tests written before implementation.
- `pytest` + `pytest-asyncio`. Temp vault via `tmp_path` fixture. Mock Ollama (no external dep in CI).
- Coverage: ≥ 80% core/, 100% validator + router (critical logic).
- Each MCP tool: contract test (input/output schema).
- Parametrized type tests cover all 11 (4 marked `@pytest.mark.skip(reason="v3.1")`).
- Feature test matrix: confidence enum, incremental hash skip, hub ranking, cluster determinism, graphify import roundtrip, atomic write crash safety, Obsidian conflict scenarios.

---

## 12. Phased execution plan

| Phase | Deliverable | Depends on | Definition of Done |
|-------|-------------|-----------|--------------------|
| **F0: Scaffold** | pyproject, config, models, db schema, CI, conftest | — | `pip install -e .` works; schema creates; tests run |
| **F1: Write path** | validator + writer + save/update tools | F0 | save/update tested; lock + atomic write OK; confidence validated; Obsidian conflict scenarios pass |
| **F2: Read path** | router + reader Path A + embeddings + Path B | F1 | query/deep_query tested; fallback chain OK; mock Ollama |
| **F3: Hooks + handoff** | pre_tool_use, session_start, handoff tool | F1 | handoff saves/injects; thresholds OK |
| **F4: Graphify features** | hubs, clustering, watcher, graphify import | F2 | 4 features tested isolated |
| **F5: CLI + docs + migration** | cli.py, README, engram-v3.md, vault migration | F1-F4 | CLI works; doc complete; existing vault (28 notes) migrates with confidence backfill |

**Critical path:** F0→F1→F2 (core value). F3 parallel to F2. F4 after F2 (needs embeddings). F5 closes.

**Per phase:** spec → TDD → implementation → QA gate → commit.

### Migration note (F5)

Existing 28 notes in `C:\Users\ianfl\dev-vault` lack the `confidence` field. Migration script backfills: `decision`/`bug` with verified outcome → `fact`; `pattern`/`concept` → `inference`; open items → `hypothesis`. Human reviews before commit.

---

## 13. Open questions

None blocking. All major decisions resolved:
- Sweeper cut, atomic write + lock chosen ✓
- 7 types active, 11 prepared ✓
- Cold storage deferred, schema prepared ✓
- Ollama local only ✓
- MCP + minimal CLI ✓
- Configurable vault, backward-compatible ✓
