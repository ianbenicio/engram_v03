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
