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
