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
    path = vault / "projetos" / "proj" / "Resources" / "decisoes" / f"{res['note_id']}.md"
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

def test_save_warns_unknown_module(config, db, vault):
    idx = vault / "projetos" / "proj" / "_index.md"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text("---\nproject: proj\nmodules:\n  - auth\n  - billing\n---\n\nx",
                   encoding="utf-8")
    n = _note()
    n.module = "nonexistent"
    res = vault_save(n, "body for module warn", config, db)
    assert res["status"] == "ok"
    assert any("nonexistent" in w for w in res["warnings"])

def test_save_no_warn_known_module(config, db, vault):
    idx = vault / "projetos" / "proj" / "_index.md"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text("---\nproject: proj\nmodules:\n  - auth\n---\n\nx",
                   encoding="utf-8")
    n = _note()
    n.module = "auth"
    res = vault_save(n, "body known module", config, db)
    assert res["status"] == "ok"
    assert not any("not in project" in w for w in res["warnings"])
