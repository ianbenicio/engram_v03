import json

from engram.core.mining import mine_files, mine_convos, MINED_DIRNAME
from engram.core.writer import vault_update
from engram.core.reader import path_a
from engram.models import QueryRequest


def _src_dir(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "a.md").write_text("# Redis decision\n\nWe chose redis for caching.",
                            encoding="utf-8")
    (d / "b.txt").write_text("Postgres notes about redis replication.",
                             encoding="utf-8")
    return d


def test_mine_files_creates_drafts(db, vault, config, tmp_path):
    src = _src_dir(tmp_path)
    res = mine_files(src, "proj", config, db)
    assert res["created"] == 2
    mined = vault / MINED_DIRNAME
    assert mined.exists()
    assert len(list(mined.glob("*.md"))) == 2
    rows = db.execute("SELECT status, confidence, type FROM notes").fetchall()
    assert all(r == ("draft", "hypothesis", "context") for r in rows)


def test_drafts_excluded_from_default_query(db, vault, config, tmp_path):
    mine_files(_src_dir(tmp_path), "proj", config, db)
    res = path_a(QueryRequest(text="redis"), db)
    assert res["match_count"] == 0  # drafts hidden by default


def test_draft_visible_with_explicit_status_filter(db, vault, config, tmp_path):
    mine_files(_src_dir(tmp_path), "proj", config, db)
    res = path_a(QueryRequest(text="redis", status_filter="draft"), db)
    assert res["match_count"] >= 1


def test_promote_makes_draft_queryable(db, vault, config, tmp_path):
    mine_files(_src_dir(tmp_path), "proj", config, db)
    nid = db.execute("SELECT id FROM notes LIMIT 1").fetchone()[0]
    upd = vault_update(nid, {"status": "active"}, None, config, db)
    assert upd["status"] == "ok"
    res = path_a(QueryRequest(text="redis"), db)
    ids = {r["id"] for r in res["results"]}
    assert nid in ids


def test_mine_convos_one_draft_per_transcript(db, vault, config, tmp_path):
    d = tmp_path / "convos"
    d.mkdir()
    lines = [json.dumps({"content": "decided to use redis"}),
             json.dumps({"content": "redis ttl set to 3600"})]
    (d / "session1.jsonl").write_text("\n".join(lines), encoding="utf-8")
    res = mine_convos(d, "proj", config, db)
    assert res["created"] == 1
    row = db.execute("SELECT status FROM notes").fetchone()
    assert row[0] == "draft"
