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
