from engram.core.handoff import vault_handoff, find_latest_handoff

def test_handoff_creates_session_note(config, db, vault):
    res = vault_handoff(
        {"project": "proj", "decisions": ["use redis"],
         "files": ["app/x.py"], "next_steps": ["write tests"],
         "branch": "main"}, config, db)
    assert res["status"] == "ok"
    p = vault / "sessoes" / f"handoff-{res['note_id']}.md"
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    assert "use redis" in txt
    assert "type: session" in txt

def test_find_latest_handoff(config, db, vault):
    r1 = vault_handoff({"project": "proj", "decisions": [], "files": [],
                        "next_steps": [], "branch": "main"}, config, db)
    latest = find_latest_handoff(vault, project="proj")
    assert latest is not None
    assert r1["note_id"] in str(latest)
