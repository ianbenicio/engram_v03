from engram.models import QueryRequest
from engram.core.reader import path_a

def _seed(db):
    rows = [
        ("n1","Redis cache","Use Redis for cache","decision"),
        ("n2","Auth bug","JWT expiry off-by-one","bug"),
    ]
    for nid, title, tldr, typ in rows:
        db.execute(
            "INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
            "status,created,updated,file_path,confidentiality) VALUES "
            "(?,?,?,?, 'fact','project','proj','active','c','u',?,'internal')",
            (nid, title, tldr, typ, f"/v/{nid}.md"))
        db.execute(
            "INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet) "
            "VALUES (?,?,?,?,?)", (nid, title, tldr, "proj", tldr))
    db.commit()

def test_path_a_returns_tldrs(db):
    _seed(db)
    res = path_a(QueryRequest(text="redis"), db)
    assert res["path"] == "A"
    assert res["match_count"] == 1
    assert "Use Redis for cache" in res["summary"]

def test_path_a_excludes_archived(db):
    _seed(db)
    db.execute("UPDATE notes SET status='archived' WHERE id='n1'")
    db.commit()
    res = path_a(QueryRequest(text="redis"), db)
    assert res["match_count"] == 0

def test_path_a_type_filter(db):
    _seed(db)
    res = path_a(QueryRequest(text="proj", type_filter="bug"), db)
    ids = {r["id"] for r in res["results"]}
    assert ids == {"n2"}

def test_path_a_hyphenated_term_no_silent_empty(db):
    # Regression: a hyphen in a query term ('claude-mem') made FTS5 raise
    # OperationalError, swallowed into an empty result. fts_query quotes each
    # term so the hyphen is literal and the note is found.
    db.execute(
        "INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
        "status,created,updated,file_path,confidentiality) VALUES "
        "('n3','claude-mem consumo','claude-mem injeta tokens no contexto',"
        "'context','fact','project','proj','active','c','u','/v/n3.md','internal')")
    db.execute(
        "INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet) "
        "VALUES ('n3','claude-mem consumo','claude-mem injeta tokens no contexto',"
        "'proj','claude-mem injeta tokens')")
    db.commit()
    res = path_a(QueryRequest(text="claude-mem tokens"), db)
    assert res["match_count"] == 1
    assert res["results"][0]["id"] == "n3"
