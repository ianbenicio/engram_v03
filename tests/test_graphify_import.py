import json
from engram.importers.graphify import import_graph

def _graph(tmp_path):
    g = {
        "nodes": [
            {"id": "AuthService", "type": "module",
             "summary": "Handles authentication", "tag": "EXTRACTED"},
            {"id": "Database", "type": "module",
             "summary": "Postgres store", "tag": "INFERRED"},
        ],
        "edges": [
            {"source": "AuthService", "target": "Database", "tag": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(g), encoding="utf-8")
    return p

def test_import_creates_context_notes(config, db, vault, tmp_path):
    res = import_graph(_graph(tmp_path), project="proj", config=config, conn=db)
    assert res["created"] == 2
    types = {r[0] for r in db.execute("SELECT type FROM notes").fetchall()}
    assert types == {"context"}

def test_confidence_mapping(config, db, vault, tmp_path):
    import_graph(_graph(tmp_path), project="proj", config=config, conn=db)
    confs = dict(db.execute("SELECT title, confidence FROM notes").fetchall())
    assert confs["AuthService"] == "fact"
    assert confs["Database"] == "inference"

def test_edges_become_related(config, db, vault, tmp_path):
    import_graph(_graph(tmp_path), project="proj", config=config, conn=db)
    row = db.execute("SELECT file_path FROM notes WHERE title='AuthService'").fetchone()
    assert "database" in open(row[0], encoding="utf-8").read().lower()
