from engram.core.moc import generate_moc, BUCKET
from engram.core.writer import vault_save
from engram.models import NoteData, NoteType, Confidence


def _save(config, db, title, ntype, tags_dom, body):
    n = NoteData(title=title, tldr=f"tldr for {title}", type=ntype,
                 confidence=Confidence.FACT, scope="project", project="proj",
                 tags=["tipo/" + ntype.value, "maturidade/stable", "dominio/" + tags_dom])
    return vault_save(n, body, config, db)["note_id"]


def test_bucket_mapping():
    assert BUCKET["decision"] == "Resources"
    assert BUCKET["context"] == "Areas"
    assert BUCKET["bug"] == "Projects"


def test_generate_moc_groups_by_para(config, db, vault):
    _save(config, db, "Use Redis", NoteType.DECISION, "backend", "redis decision body")
    _save(config, db, "Auth bug", NoteType.BUG, "backend", "jwt bug body")
    _save(config, db, "Module context", NoteType.CONTEXT, "backend", "context body")
    res = generate_moc(db, config, "proj")
    assert res["status"] == "ok"
    assert res["note_count"] == 3
    txt = (vault / "projetos" / "proj" / "MOC-proj.md").read_text(encoding="utf-8")
    assert "# MOC — proj" in txt
    assert "## Resources" in txt and "Use Redis" in txt
    assert "## Areas" in txt and "Module context" in txt
    assert "## Projects" in txt and "Auth bug" in txt
    # wikilinks present
    assert "[[" in txt


def test_moc_excludes_drafts(config, db, vault):
    _save(config, db, "Active note", NoteType.DECISION, "backend", "active body")
    # a draft-status note should not appear
    db.execute("INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
               "status,created,updated,file_path) VALUES "
               "('d1','Draft note','x','decision','fact','project','proj','draft',"
               "'c','u','/v/d1.md')")
    db.commit()
    res = generate_moc(db, config, "proj")
    txt = (vault / "projetos" / "proj" / "MOC-proj.md").read_text(encoding="utf-8")
    assert "Active note" in txt
    assert "Draft note" not in txt
    assert res["note_count"] == 1
