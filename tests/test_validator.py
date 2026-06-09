from engram.core.validator import (
    validate_required_fields, validate_tags, load_tags_vocab,
    validate_tag_prefixes, validate_wikilinks,
)

def test_missing_confidence_flagged():
    note = {"id": "1", "title": "t", "tldr": "x", "type": "decision",
            "status": "active", "created": "c", "updated": "u",
            "author": "claude", "scope": "project", "tags": ["tipo/decision"]}
    assert "confidence" in validate_required_fields(note)

def test_all_present_no_missing():
    note = {"id": "1", "title": "t", "tldr": "x", "type": "decision",
            "confidence": "fact", "status": "active", "created": "c",
            "updated": "u", "author": "claude", "scope": "project",
            "tags": ["tipo/decision"]}
    assert validate_required_fields(note) == []

def test_load_vocab_and_validate_tags(vault):
    vocab = load_tags_vocab(vault)
    assert "tipo/decision" in vocab
    assert validate_tags(["tipo/decision", "tipo/nonexistent"], vocab) == ["tipo/nonexistent"]

def test_projeto_tags_always_valid(vault):
    vocab = load_tags_vocab(vault)
    assert validate_tags(["projeto/anything"], vocab) == []

def test_missing_prefixes():
    missing = validate_tag_prefixes(["tipo/decision"])
    assert "maturidade/" in missing
    assert "dominio/" in missing
    assert "tipo/" not in missing

def test_wikilinks_broken_detected(db, vault):
    assert validate_wikilinks(["[[does-not-exist]]"], db, vault) == ["[[does-not-exist]]"]

def test_wikilinks_resolved_via_sqlite(db, vault):
    db.execute(
        "INSERT INTO notes (id,title,type,confidence,created,updated,file_path) "
        "VALUES ('adr-1','t','decision','fact','c','u','/v/adr-1.md')"
    )
    db.commit()
    assert validate_wikilinks(["[[adr-1]]"], db, vault) == []


from engram.core.validator import validate_lifecycle

def test_lifecycle_valid_on_decision():
    assert validate_lifecycle({"type": "decision", "lifecycle": "accepted"}) is None

def test_lifecycle_invalid_value():
    err = validate_lifecycle({"type": "decision", "lifecycle": "bogus"})
    assert err is not None and "bogus" in err

def test_lifecycle_rejected_on_non_decision():
    err = validate_lifecycle({"type": "bug", "lifecycle": "accepted"})
    assert err is not None and "decision" in err

def test_lifecycle_absent_is_ok():
    assert validate_lifecycle({"type": "bug"}) is None
