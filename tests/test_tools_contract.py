import engram.server as srv
from engram.models import NoteData, NoteType, Confidence

def test_tool_save_and_query_roundtrip(config, db, monkeypatch):
    monkeypatch.setattr(srv, "_CONFIG", config)
    monkeypatch.setattr(srv, "_CONN", db)
    srv._RATE.__init__(max_calls=100, window_seconds=60)
    n = NoteData(title="Redis", tldr="cache decision", type=NoteType.DECISION,
                 confidence=Confidence.FACT, scope="project", project="proj",
                 tags=["tipo/decision","maturidade/stable","dominio/backend"])
    save_res = srv._save_impl(n, "Redis chosen.")
    assert save_res["status"] == "ok"
    q = srv._query_impl({"text": "redis", "project": "proj"})
    assert q["match_count"] >= 1

def test_rate_limit_enforced(config, db, monkeypatch):
    monkeypatch.setattr(srv, "_CONFIG", config)
    monkeypatch.setattr(srv, "_CONN", db)
    srv._RATE.__init__(max_calls=1, window_seconds=60)
    srv._query_impl({"text": "x"})
    q2 = srv._query_impl({"text": "x"})
    assert q2["status"] == "error"
    assert "rate" in q2["reason"].lower()
