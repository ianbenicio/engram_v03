from engram.core.writer import vault_save
from engram.core.reader import path_b
from engram.models import NoteData, NoteType, Confidence

def _note():
    return NoteData(title="Redis cache", tldr="Use Redis for caching",
                    type=NoteType.DECISION, confidence=Confidence.FACT,
                    scope="project", project="proj",
                    tags=["tipo/decision","maturidade/stable","dominio/backend"])

def test_save_stores_embedding_and_path_b_finds_it(config, db, vault, monkeypatch):
    vec = [0.42] * 1024
    monkeypatch.setattr("engram.core.embeddings.get_embedding", lambda t, c: vec)
    res = vault_save(_note(), "Redis chosen for low latency.", config, db)
    assert res["status"] == "ok"
    cnt = db.execute("SELECT COUNT(*) FROM notes_vec WHERE note_id=?",
                     (res["note_id"],)).fetchone()[0]
    assert cnt == 1
    monkeypatch.setattr("engram.core.reader.embeddings.get_embedding", lambda t, c: vec)
    monkeypatch.setattr("engram.core.reader.embeddings.synthesize", lambda q, ctx, c: "SYNTH")
    out = path_b(_note_query(), db, config)
    assert out["path"] == "B"
    assert out["sources"][0]["id"] == res["note_id"]

def _note_query():
    from engram.models import QueryRequest
    return QueryRequest(text="why redis")

def test_save_succeeds_when_ollama_offline(config, db, vault, monkeypatch):
    from engram.core.embeddings import EmbeddingUnavailable
    def boom(t, c): raise EmbeddingUnavailable("offline")
    monkeypatch.setattr("engram.core.embeddings.get_embedding", boom)
    res = vault_save(_note(), "body offline case", config, db)
    assert res["status"] == "ok"  # save still succeeds, embedding skipped
    cnt = db.execute("SELECT COUNT(*) FROM notes_vec").fetchone()[0]
    assert cnt == 0
