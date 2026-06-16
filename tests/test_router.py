from engram.models import QueryRequest
from engram.core.router import route_query, has_semantic_intent

def test_explicit_deep_is_heavy(db):
    assert route_query(QueryRequest(text="x", depth="deep"), db) == "heavy"

def test_multi_project_is_heavy(db):
    assert route_query(QueryRequest(text="x", projects=["a","b"]), db) == "heavy"

def test_wildcard_is_heavy(db):
    assert route_query(QueryRequest(text="x", projects=["*"]), db) == "heavy"

def test_semantic_pt_is_heavy(db):
    assert route_query(QueryRequest(text="qual o impacto de migrar Redis"), db) == "heavy"

def test_semantic_en_is_heavy(db):
    assert route_query(QueryRequest(text="what is the impact of migrating"), db) == "heavy"

def test_simple_query_is_lightweight(db):
    assert route_query(QueryRequest(text="rate limit config"), db) == "lightweight"

def test_many_matches_is_heavy(db):
    for i in range(6):
        db.execute(
            "INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet) "
            "VALUES (?,?,?,?,?)", (f"n{i}", "redis cache", "x", "", "redis"))
    db.commit()
    assert route_query(QueryRequest(text="redis"), db) == "heavy"

def test_has_semantic_intent_bilingual():
    assert has_semantic_intent("comparar duas opcoes")
    assert has_semantic_intent("compare two options")
    assert not has_semantic_intent("redis timeout value")

def test_fts_query_quotes_each_term():
    from engram.core.router import fts_query
    # Hyphenated terms must be quoted so FTS5 treats '-' literally (no operator).
    assert fts_query("claude-mem token") == '"claude-mem" "token"'
    assert fts_query("radar") == '"radar"'
    assert fts_query("") == ""
