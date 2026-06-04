from scripts.migrate_v2_to_v3 import infer_confidence, migrate_note_text


def test_infer_confidence_decision_fact():
    assert infer_confidence({"type": "decision", "status": "active"}) == "fact"


def test_infer_confidence_pattern_inference():
    assert infer_confidence({"type": "pattern"}) == "inference"


def test_infer_confidence_open_hypothesis():
    assert infer_confidence({"type": "context", "status": "draft"}) == "hypothesis"


def test_migrate_adds_confidence_field():
    text = ("---\nid: n1\ntitle: T\ntype: decision\nstatus: active\n"
            "tags: ['tipo/decision']\n---\n\nbody")
    out, changed = migrate_note_text(text)
    assert changed is True
    assert "confidence: fact" in out


def test_migrate_skips_if_present():
    text = ("---\nid: n1\ntype: decision\nconfidence: inference\n"
            "status: active\n---\n\nbody")
    out, changed = migrate_note_text(text)
    assert changed is False
