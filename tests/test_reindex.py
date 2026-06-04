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
