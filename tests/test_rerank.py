from datetime import datetime, timezone

from sqlite_vec import serialize_float32

from engram.models import QueryRequest
from engram.core.reader import path_b, _keyword_overlap, _rerank_score


def _now():
    return datetime.now(timezone.utc).isoformat()


def _seed(db, vault):
    # nB: identical to query vector (distance 0), NO keyword overlap.
    # nA: slightly farther vector, strong keyword overlap with "redis".
    notes = {
        "nA": ("Redis cache", "redis caching layer", [0.9, 0.1] + [0.0] * 1022),
        "nB": ("Postgres store", "sql database", [1.0, 0.0] + [0.0] * 1022),
    }
    for nid, (title, tldr, vec) in notes.items():
        p = vault / f"{nid}.md"
        p.write_text(f"---\nid: {nid}\n---\n\nBody of {title}.", encoding="utf-8")
        db.execute(
            "INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
            "status,created,updated,file_path,confidentiality) VALUES "
            "(?,?,?, 'decision','fact','project','proj','active','c',?,?,'internal')",
            (nid, title, tldr, _now(), str(p)))
        db.execute("INSERT INTO notes_vec(note_id,embedding) VALUES (?,?)",
                   (nid, serialize_float32(vec)))
    db.commit()


def _query_vec():
    return [1.0, 0.0] + [0.0] * 1022


# --- unit ---

def test_keyword_overlap_full():
    assert _keyword_overlap("redis caching", "Redis caching layer", "x") == 1.0

def test_keyword_overlap_partial():
    # only 'redis' present; 'cache' != substring of 'caching'
    assert _keyword_overlap("redis cache", "Redis caching layer", "x") == 0.5

def test_keyword_overlap_zero():
    assert _keyword_overlap("redis", "Postgres store", "sql") == 0.0

def test_rerank_score_keyword_beats_distance():
    # nA: dist 0.3 + keyword; nB: dist 0.0 no keyword
    sa = _rerank_score("redis", 0.3, "Redis cache", "redis", _now(), 90)
    sb = _rerank_score("redis", 0.0, "Postgres", "sql", _now(), 90)
    assert sa > sb


# --- path_b integration ---

def test_rerank_off_orders_by_distance(db, vault, config, monkeypatch):
    _seed(db, vault)
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: _query_vec())
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize",
                        lambda q, ctx, c: "S")
    config.rerank = False
    res = path_b(QueryRequest(text="redis"), db, config)
    assert res["sources"][0]["id"] == "nB"  # closest vector wins

def test_rerank_on_promotes_keyword_match(db, vault, config, monkeypatch):
    _seed(db, vault)
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: _query_vec())
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize",
                        lambda q, ctx, c: "S")
    config.rerank = True
    res = path_b(QueryRequest(text="redis"), db, config)
    assert res["sources"][0]["id"] == "nA"  # keyword overlap beats slight distance
