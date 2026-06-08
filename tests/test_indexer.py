from engram.core.indexer import upsert_note, compute_hash, check_duplicate

def _note(nid="n1", title="Use Redis"):
    return {"id": nid, "title": title, "tldr": "cache layer",
            "type": "decision", "confidence": "fact", "scope": "project",
            "status": "active", "created": "c", "updated": "u",
            "author": "claude", "project": "proj", "module": None,
            "tags": ["tipo/decision", "dominio/backend"],
            "confidentiality": "internal", "schema_version": 1}

def test_compute_hash_is_32_hex():
    h = compute_hash("hello world")
    assert len(h) == 32
    assert all(c in "0123456789abcdef" for c in h)

def test_upsert_inserts_into_notes_and_fts(db):
    upsert_note(db, _note(), content_hash="abc", file_path="/v/n1.md",
                body="Redis chosen for speed.")
    row = db.execute("SELECT title, confidence FROM notes WHERE id='n1'").fetchone()
    assert row == ("Use Redis", "fact")
    fts = db.execute("SELECT title FROM notes_fts WHERE notes_fts MATCH 'redis'").fetchall()
    assert len(fts) == 1

def test_upsert_replaces_existing(db):
    upsert_note(db, _note(title="v1"), "h1", "/v/n1.md", "body1")
    upsert_note(db, _note(title="v2"), "h2", "/v/n1.md", "body2")
    rows = db.execute("SELECT title FROM notes WHERE id='n1'").fetchall()
    assert rows == [("v2",)]
    cnt = db.execute("SELECT count(*) FROM notes_fts WHERE note_id='n1'").fetchone()
    assert cnt[0] == 1

def test_check_duplicate(db):
    upsert_note(db, _note(), "hash123", "/v/n1.md", "body")
    assert check_duplicate(db, "hash123") is not None
    assert check_duplicate(db, "other") is None

import pytest

def test_upsert_missing_required_key_raises_valueerror(db):
    bad = {"id": "x1", "title": "T", "type": "decision",
           "created": "c", "updated": "u"}  # missing 'confidence'
    with pytest.raises(ValueError) as exc:
        upsert_note(db, bad, "h", "/v/x1.md", "body")
    assert "confidence" in str(exc.value)
