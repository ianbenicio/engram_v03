from engram.models import QueryRequest
from engram.core.reader import path_b
from engram.core.embeddings import EmbeddingUnavailable
from sqlite_vec import serialize_float32

def _seed_vec(db, vault, vec):
    body = "Redis chosen for low-latency cache. Decision is final."
    p = vault / "n1.md"
    p.write_text("---\nid: n1\n---\n\n" + body, encoding="utf-8")
    db.execute(
        "INSERT INTO notes (id,title,tldr,type,confidence,scope,project,"
        "status,created,updated,file_path,confidentiality) VALUES "
        "('n1','Redis','cache','decision','fact','project','proj','active',"
        "'c','u',?, 'internal')", (str(p),))
    db.execute("INSERT INTO notes_vec(note_id,embedding) VALUES ('n1',?)",
               (serialize_float32(vec),))
    db.commit()

def test_path_b_synthesizes(db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: vec)
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize",
                        lambda q, ctx, c: "SYNTH OK")
    res = path_b(QueryRequest(text="why redis"), db, config)
    assert res["path"] == "B"
    assert res["synthesis"] == "SYNTH OK"
    assert res["sources"][0]["id"] == "n1"

def test_path_b_embedding_offline_falls_back_to_a(db, vault, config, monkeypatch):
    _seed_vec(db, vault, [0.5] * 1024)
    db.execute("INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet)"
               " VALUES ('n1','Redis','cache','','redis cache')"); db.commit()
    def boom(t, c): raise EmbeddingUnavailable("offline")
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding", boom)
    res = path_b(QueryRequest(text="redis"), db, config)
    assert res["path"] == "B-fallback"
    assert res["fallback_used"] is True

def test_path_b_synth_offline_returns_full_notes(db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    db.execute("INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet)"
               " VALUES ('n1','Redis','cache','','redis cache')"); db.commit()
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: vec)
    def boom(q, ctx, c): raise EmbeddingUnavailable("synth offline")
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize", boom)
    res = path_b(QueryRequest(text="redis"), db, config)
    assert res["path"] == "B-fallback"
    assert "Redis chosen for low-latency" in res["summary"]

def test_path_b_excludes_restricted(db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    db.execute("UPDATE notes SET confidentiality='restricted' WHERE id='n1'")
    db.commit()
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: vec)
    captured = {}
    def cap_synth(q, ctx, c):
        captured["ctx"] = ctx
        return "S"
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize", cap_synth)
    res = path_b(QueryRequest(text="redis"), db, config)
    assert res.get("restricted_omitted", 0) == 1
    assert "Redis chosen" not in captured.get("ctx", "")

def test_path_b_embedding_offline_reports_reason_and_matches_any_term(
        db, vault, config, monkeypatch):
    # Regression (D7): a natural-language query fell back to FTS with implicit
    # AND across every word -> zero hits, and the cause was never reported.
    _seed_vec(db, vault, [0.5] * 1024)
    db.execute("INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet)"
               " VALUES ('n1','Redis','cache','','redis cache')"); db.commit()
    def boom(t, c): raise EmbeddingUnavailable("Ollama status 500: CUDA error")
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding", boom)
    res = path_b(QueryRequest(text="why did we choose redis for this"), db, config)
    assert res["path"] == "B-fallback"
    assert res["match_count"] == 1
    assert "CUDA error" in res["fallback_reason"]

def test_path_b_embedding_offline_logs_fallback_path(db, vault, config, monkeypatch):
    _seed_vec(db, vault, [0.5] * 1024)
    db.execute("INSERT INTO notes_fts (note_id,title,tldr,tags_text,body_snippet)"
               " VALUES ('n1','Redis','cache','','redis cache')"); db.commit()
    def boom(t, c): raise EmbeddingUnavailable("offline")
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding", boom)
    logged = []
    monkeypatch.setattr("engram.core.reader.usage.log_retrieval",
                        lambda log, ids, path: logged.append(path))
    path_b(QueryRequest(text="redis"), db, config)
    assert logged == ["B-fallback"]

def test_path_b_synth_offline_reports_reason(db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: vec)
    def boom(q, ctx, c): raise EmbeddingUnavailable("timed out")
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize", boom)
    res = path_b(QueryRequest(text="redis"), db, config)
    assert res["fallback_reason"] == "synthesis unavailable: timed out"


def _no_synth(monkeypatch, vec):
    calls = []
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding",
                        lambda t, c: vec)
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize",
                        lambda q, ctx, c: calls.append(q) or "SYNTH OK")
    return calls


def test_path_b_synthesis_disabled_returns_tldr_and_excerpt(
        db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    calls = _no_synth(monkeypatch, vec)
    config.synthesis_enabled = False
    res = path_b(QueryRequest(text="redis"), db, config)
    assert calls == []
    assert res["path"] == "B" and res["fallback_used"] is False
    assert res["synthesis_skipped"] is True
    assert "synthesis" not in res
    src = res["sources"][0]
    assert src["id"] == "n1" and src["tldr"] == "cache"
    assert src["excerpt"].startswith("Redis chosen for low-latency")


def test_path_b_excerpt_is_capped(db, vault, config, monkeypatch):
    from engram.core.reader import EXCERPT_CHARS
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    (vault / "n1.md").write_text("---\nid: n1\n---\n\n" + "x" * 2000,
                                 encoding="utf-8")
    _no_synth(monkeypatch, vec)
    config.synthesis_enabled = False
    res = path_b(QueryRequest(text="redis"), db, config)
    assert len(res["sources"][0]["excerpt"]) == EXCERPT_CHARS


def test_path_b_synthesize_on_request_overrides_disabled_config(
        db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    calls = _no_synth(monkeypatch, vec)
    config.synthesis_enabled = False
    res = path_b(QueryRequest(text="redis", synthesize=True), db, config)
    assert calls == ["redis"] and res["synthesis"] == "SYNTH OK"


def test_path_b_synthesize_false_overrides_enabled_config(
        db, vault, config, monkeypatch):
    vec = [0.5] * 1024
    _seed_vec(db, vault, vec)
    calls = _no_synth(monkeypatch, vec)
    res = path_b(QueryRequest(text="redis", synthesize=False), db, config)
    assert calls == [] and res["synthesis_skipped"] is True
