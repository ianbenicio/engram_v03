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
