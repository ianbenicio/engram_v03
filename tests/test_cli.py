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

def test_save_command(monkeypatch, config, db, vault, tmp_path):
    import engram.cli as cli
    monkeypatch.setattr(cli, "_load", lambda: (config, db))
    # No Ollama dependency in tests: skip the embedding step.
    monkeypatch.setattr("engram.core.writer.embeddings.embed_and_store",
                        lambda *a, **k: False)
    note = tmp_path / "note.md"
    note.write_text(
        "---\ntitle: Codex test note\ntldr: codex writes via CLI\n"
        "type: decision\nconfidence: fact\nproject: proj\n"
        "tags: ['tipo/decision', 'dominio/backend', 'maturidade/stable']\n---\n\nBody content.",
        encoding="utf-8")
    result = runner.invoke(app, ["save", str(note)])
    assert result.exit_code == 0, result.stdout
    assert '"status": "ok"' in result.stdout
    # author defaults to 'codex' on the CLI write path
    row = db.execute(
        "SELECT author FROM notes WHERE title='Codex test note'").fetchone()
    assert row[0] == "codex"

def test_save_rejects_missing_frontmatter(monkeypatch, config, db, tmp_path):
    import engram.cli as cli
    monkeypatch.setattr(cli, "_load", lambda: (config, db))
    note = tmp_path / "bad.md"
    note.write_text("no frontmatter here", encoding="utf-8")
    result = runner.invoke(app, ["save", str(note)])
    assert result.exit_code == 1
    assert "frontmatter" in result.stdout.lower()
