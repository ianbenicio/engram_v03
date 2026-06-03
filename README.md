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

To use an existing vault:
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
engram cluster proj --threshold 0.75  # cluster notes -> _clusters.md
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
