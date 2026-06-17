from sqlite_vec import serialize_float32

from engram.core.crosslink import cross_project_report


def _seed(db, nid, project, vec):
    full = vec + [0.0] * (1024 - len(vec))
    db.execute(
        "INSERT INTO notes (id,title,tldr,type,confidence,scope,project,status,"
        "created,updated,file_path) VALUES "
        "(?,?,?, 'pattern','inference','project',?,'active','c','u',?)",
        (nid, nid, f"tldr {nid}", project, f"/v/{nid}.md"))
    db.execute("INSERT INTO notes_vec(note_id,embedding) VALUES (?,?)",
               (nid, serialize_float32(full)))
    db.commit()


def test_no_embeddings_empty_report(db, config):
    assert cross_project_report(db, config) == []


def test_cross_project_similar_grouped(db, config):
    # same vector, DIFFERENT projects -> grouped
    _seed(db, "a", "engram", [1.0, 0.0, 0.0])
    _seed(db, "b", "nexa", [1.0, 0.0, 0.0])
    rep = cross_project_report(db, config, threshold=0.9)
    assert len(rep) == 1
    assert set(rep[0]["projects"]) == {"engram", "nexa"}
    assert {m["id"] for m in rep[0]["members"]} == {"a", "b"}


def test_same_project_not_reported(db, config):
    # same vector, SAME project -> not a cross-project group
    _seed(db, "a", "engram", [1.0, 0.0, 0.0])
    _seed(db, "b", "engram", [1.0, 0.0, 0.0])
    assert cross_project_report(db, config, threshold=0.9) == []


def test_below_threshold_not_grouped(db, config):
    _seed(db, "a", "engram", [1.0, 0.0, 0.0])
    _seed(db, "b", "nexa", [0.0, 1.0, 0.0])  # orthogonal -> cosine 0
    assert cross_project_report(db, config, threshold=0.9) == []

def test_default_threshold_from_config(db, config):
    # cosine([1,0,0],[0.8,0.6,0]) = 0.8: above config default 0.65, below old 0.85.
    _seed(db, "a", "engram", [1.0, 0.0, 0.0])
    _seed(db, "b", "nexa", [0.8, 0.6, 0.0])
    rep = cross_project_report(db, config)  # no explicit threshold -> config 0.65
    assert len(rep) == 1
    assert cross_project_report(db, config, threshold=0.85) == []
