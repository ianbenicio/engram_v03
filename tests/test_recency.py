from datetime import datetime, timedelta, timezone

from engram.models import QueryRequest
from engram.core.reader import path_a, _recency_factor


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _seed(db, updated_map):
    """updated_map: {id: (title, tldr, updated_iso)}."""
    for nid, (title, tldr, updated) in updated_map.items():
        db.execute(
            "INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
            "status,created,updated,file_path,confidentiality) VALUES "
            "(?,?,?, 'decision','fact','project','proj','active','c',?,?,'internal')",
            (nid, title, tldr, updated, f"/v/{nid}.md"))
        db.execute(
            "INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet) "
            "VALUES (?,?,?,?,?)", (nid, title, tldr, "", tldr))
    db.commit()


# --- _recency_factor unit ---

def test_recency_factor_recent_near_one():
    assert _recency_factor(_iso(0), 90) > 0.99

def test_recency_factor_halflife_is_half():
    assert abs(_recency_factor(_iso(90), 90) - 0.5) < 0.02

def test_recency_factor_unparseable_is_zero():
    assert _recency_factor("u", 90) == 0.0
    assert _recency_factor(None, 90) == 0.0


# --- path_a recency behavior ---

def test_recency_off_preserves_fts_order(db, config):
    # config=None => pure FTS order (backward-compatible)
    _seed(db, {
        "old": ("Redis cache", "redis redis redis", _iso(400)),
        "new": ("Redis", "redis", _iso(1)),
    })
    res_none = path_a(QueryRequest(text="redis"), db)
    # 'old' has more term frequency -> better bm25 -> first under pure FTS
    assert res_none["results"][0]["id"] == "old"

def test_recency_on_promotes_newer(db, config):
    _seed(db, {
        "old": ("Redis cache", "redis redis redis", _iso(400)),
        "new": ("Redis", "redis", _iso(1)),
    })
    config.recency_weight = 0.9  # recency dominates
    res = path_a(QueryRequest(text="redis"), db, config)
    assert res["results"][0]["id"] == "new"

def test_recency_weight_zero_equals_off(db, config):
    _seed(db, {
        "old": ("Redis cache", "redis redis redis", _iso(400)),
        "new": ("Redis", "redis", _iso(1)),
    })
    config.recency_weight = 0.0
    res = path_a(QueryRequest(text="redis"), db, config)
    assert res["results"][0]["id"] == "old"  # same as pure FTS
