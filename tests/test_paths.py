import json
from engram.core.paths import target_path, log_activity

def test_project_decision_path(vault):
    p = target_path(vault, {"type": "decision", "scope": "project",
                            "project": "proj", "id": "adr-1"})
    assert p == vault / "projetos" / "proj" / "Resources" / "decisoes" / "adr-1.md"

def test_global_pattern_path(vault):
    p = target_path(vault, {"type": "pattern", "scope": "global",
                            "project": None, "id": "pat-1"})
    assert p == vault / "global" / "Resources" / "patterns" / "pat-1.md"

def test_bug_goes_to_projects_bucket(vault):
    p = target_path(vault, {"type": "bug", "scope": "project",
                            "project": "proj", "id": "b-1"})
    assert p == vault / "projetos" / "proj" / "Projects" / "bugs" / "b-1.md"

def test_context_goes_to_areas_bucket(vault):
    p = target_path(vault, {"type": "context", "scope": "project",
                            "project": "proj", "id": "c-1"})
    assert p == vault / "projetos" / "proj" / "Areas" / "context" / "c-1.md"

def test_session_path(vault):
    p = target_path(vault, {"type": "session", "scope": "project",
                            "project": "proj", "id": "h-1"})
    assert p == vault / "sessoes" / "handoff-h-1.md"

def test_log_activity_appends_jsonl(config):
    log_activity(config.activity_log, "save", "n1", {"type": "decision"})
    log_activity(config.activity_log, "query", "n2", {"path": "A"})
    lines = config.activity_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["action"] == "save"
    assert json.loads(lines[1])["note_id"] == "n2"
