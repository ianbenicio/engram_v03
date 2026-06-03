import pytest
from engram.core.clustering import cluster_notes, _cosine

def test_cosine_identical():
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

def test_cosine_orthogonal():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

def test_cluster_groups_similar(db, vault, config):
    from sqlite_vec import serialize_float32
    groups = {
        "a1": [1.0, 0.0, 0.0], "a2": [0.9, 0.1, 0.0],
        "b1": [0.0, 0.0, 1.0], "b2": [0.0, 0.1, 0.9],
    }
    for nid, vec in groups.items():
        full = vec + [0.0] * (1024 - len(vec))
        db.execute("INSERT INTO notes (id,title,tldr,type,confidence,scope,"
                   "project,status,created,updated,file_path) VALUES "
                   "(?,?,?, 'concept','inference','project','proj','active',"
                   "'c','u',?)", (nid, nid, "t", f"/v/{nid}.md"))
        db.execute("INSERT INTO notes_vec(note_id,embedding) VALUES (?,?)",
                   (nid, serialize_float32(full)))
    db.commit()
    result = cluster_notes(db, config, project="proj", threshold=0.8)
    assert result["num_clusters"] == 2
    assert (vault / "projetos" / "proj" / "_clusters.md").exists()
