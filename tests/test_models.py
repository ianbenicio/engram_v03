import pytest
from pydantic import ValidationError
from engram.models import NoteType, Confidence, NoteData, QueryRequest

def test_confidence_values():
    assert Confidence.FACT == "fact"
    assert Confidence.INFERENCE == "inference"
    assert Confidence.HYPOTHESIS == "hypothesis"

def test_all_eleven_types_exist():
    values = {t.value for t in NoteType}
    assert values == {
        "decision","bug","pattern","context","runbook","session","concept",
        "post-mortem","experiment","refactoring","metric",
    }

def test_notedata_requires_core_fields():
    nd = NoteData(
        title="Use Redis", tldr="Cache via Redis", type=NoteType.DECISION,
        confidence=Confidence.FACT, scope="project",
        tags=["tipo/decision", "maturidade/stable", "dominio/backend"],
    )
    assert nd.status == "active"
    assert nd.author == "claude"

def test_notedata_rejects_unknown_type():
    with pytest.raises(ValidationError):
        NoteData(
            title="x", tldr="y", type="nonsense", confidence=Confidence.FACT,
            scope="project", tags=["tipo/x","maturidade/y","dominio/z"],
        )

def test_query_request_defaults():
    q = QueryRequest(text="rate limit")
    assert q.limit == 10
    assert q.include_cold is False
    assert q.depth is None
