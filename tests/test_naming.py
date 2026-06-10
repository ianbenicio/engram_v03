from engram.core.naming import slugify, unique_id
from engram.core.writer import vault_save
from engram.models import NoteData, NoteType, Confidence


def test_slugify_basic():
    assert slugify("Use Redis for Caching") == "use-redis-for-caching"

def test_slugify_special_chars():
    assert slugify("Auth: JWT + Refresh (v2)!") == "auth-jwt-refresh-v2"

def test_slugify_empty_fallback():
    assert slugify("") == "note"
    assert slugify("???") == "note"

def test_slugify_truncates():
    assert len(slugify("x" * 200)) <= 60


def test_unique_id_collision_gets_hash_suffix(db):
    db.execute("INSERT INTO notes (id,title,type,confidence,created,updated) "
               "VALUES ('setup','Setup','decision','fact','c','u')")
    db.commit()
    nid = unique_id("Setup", "different body", db)
    assert nid.startswith("setup-") and len(nid) > len("setup-")


def test_save_generates_readable_id(config, db, vault):
    n = NoteData(title="Use Redis for Caching", tldr="cache",
                 type=NoteType.DECISION, confidence=Confidence.FACT,
                 scope="project", project="proj",
                 tags=["tipo/decision", "maturidade/stable", "dominio/backend"])
    res = vault_save(n, "redis body for slug test", config, db)
    assert res["status"] == "ok"
    assert res["note_id"] == "use-redis-for-caching"
    assert res["path"].endswith("use-redis-for-caching.md")
