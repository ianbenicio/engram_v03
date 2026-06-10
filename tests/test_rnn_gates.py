"""Tests for the two RNN-inspired gates:
- BL-05 usage-reinforced retention (forget gate aware of use)
- BL-06 contextual catalog gate (input gate that links, never blocks)
"""
from datetime import datetime, timedelta, timezone

from sqlite_vec import serialize_float32

from engram.core.usage import log_retrieval, access_stats, days_since_access
from engram.core.crosslink import find_similar
from engram.core.gc import detect
from engram.core.reader import path_a
from engram.core.writer import vault_save
from engram.models import NoteData, NoteType, Confidence, QueryRequest


def _old(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# --- usage.py unit ---

def test_log_and_stats(config):
    log_retrieval(config.activity_log, ["n1", "n2"], "A")
    log_retrieval(config.activity_log, ["n1"], "B")
    stats = access_stats(config.activity_log)
    assert stats["n1"]["count"] == 2
    assert stats["n2"]["count"] == 1
    assert days_since_access(stats, "n1") is not None
    assert days_since_access(stats, "never") is None


def test_corrupt_lines_ignored(config):
    config.activity_log.parent.mkdir(parents=True, exist_ok=True)
    config.activity_log.write_text("not json\n", encoding="utf-8")
    log_retrieval(config.activity_log, ["n1"], "A")
    assert access_stats(config.activity_log)["n1"]["count"] == 1


# --- reader logs retrievals ---

def test_path_a_logs_retrieval(db, config):
    db.execute("INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
               "status,created,updated,file_path) VALUES "
               "('n1','Redis','cache','decision','fact','project','proj',"
               "'active','c','u','/v/n1.md')")
    db.execute("INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet)"
               " VALUES ('n1','Redis','cache','','redis cache')")
    db.commit()
    path_a(QueryRequest(text="redis"), db, config)
    stats = access_stats(config.activity_log)
    assert stats["n1"]["count"] == 1


# --- GC: recent access vetoes stale ---

def _seed_old_note(db, vault, nid):
    folder = vault / "projetos" / "proj" / "Resources" / "decisoes"
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{nid}.md"
    p.write_text(f"---\nid: {nid}\ntitle: {nid}\ntype: decision\n"
                 f"confidence: inference\nstatus: active\n---\n\nbody",
                 encoding="utf-8")
    db.execute("INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
               "status,created,updated,content_hash,file_path) VALUES "
               "(?,?,?, 'decision','inference','project','proj','active','c',?,?,?)",
               (nid, nid, "t", _old(500), f"h-{nid}", str(p)))
    db.commit()


def test_gc_stale_vetoed_by_recent_access(db, vault, config):
    _seed_old_note(db, vault, "oldused")
    log_retrieval(config.activity_log, ["oldused"], "A")  # accessed NOW
    det = detect(db, config)
    assert "oldused" not in det["stale"]


def test_gc_stale_when_never_accessed(db, vault, config):
    _seed_old_note(db, vault, "oldcold")
    det = detect(db, config)
    assert "oldcold" in det["stale"]


# --- contextual catalog gate ---

def _seed_vec_note(db, nid, project, vec, title=None):
    full = vec + [0.0] * (1024 - len(vec))
    db.execute("INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
               "status,created,updated,file_path) VALUES "
               "(?,?,?, 'pattern','fact','project',?,'active','c','u',?)",
               (nid, title or nid, f"tldr {nid}", project, f"/v/{nid}.md"))
    db.execute("INSERT INTO notes_vec(note_id,embedding) VALUES (?,?)",
               (nid, serialize_float32(full)))
    db.commit()


def test_find_similar_surfaces_neighbors(db, config):
    _seed_vec_note(db, "a", "proj", [1.0, 0.0])
    _seed_vec_note(db, "b", "other", [1.0, 0.05])  # near-identical
    sim = find_similar(db, "a", threshold=0.85)
    assert sim and sim[0]["id"] == "b"
    assert sim[0]["similarity"] >= 0.85


def test_find_similar_no_embedding_empty(db, config):
    assert find_similar(db, "ghost") == []


def test_save_returns_similar_notes_never_blocks(db, config, vault, monkeypatch):
    vec = [1.0, 0.0] + [0.0] * 1022
    _seed_vec_note(db, "existing", "proj", [1.0, 0.0], title="Existing pattern")
    monkeypatch.setattr("engram.core.embeddings.get_embedding", lambda t, c: vec)
    n = NoteData(title="New similar pattern", tldr="x", type=NoteType.PATTERN,
                 confidence=Confidence.FACT, scope="project", project="proj",
                 tags=["tipo/pattern", "maturidade/stable", "dominio/backend"])
    res = vault_save(n, "body of the similar pattern", config, db)
    assert res["status"] == "ok"  # NEVER blocks
    assert any(s["id"] == "existing" for s in res["similar_notes"])
    assert any("instance_of" in w for w in res["warnings"])
