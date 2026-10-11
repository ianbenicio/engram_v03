from engram.hooks.pre_tool_use import compute_flag


def test_flag_normal_under_35():
    assert compute_flag(0, 1000, 200_000)["threshold"] == "normal"


def test_flag_warning_between_35_50():
    assert compute_flag(72_000, 0, 200_000)["threshold"] == "warning"


def test_flag_critical_over_50():
    assert compute_flag(100_001, 0, 200_000)["threshold"] == "critical"


# --- SessionStart: health line + handoff -------------------------------------

import json

import httpx

from engram.core import health
from engram.hooks import session_start


class _Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


def _ollama(monkeypatch, result):
    def fake_post(*a, **k):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr("engram.core.health.httpx.post", fake_post)


def _add_note(db, nid, status="active", vector=False):
    from sqlite_vec import serialize_float32
    db.execute("INSERT INTO notes(id,title,type,confidence,status,created,"
               "updated) VALUES (?,?,'decision','fact',?,'c','u')",
               (nid, nid, status))
    if vector:
        db.execute("INSERT INTO notes_vec(note_id,embedding) VALUES (?,?)",
                   (nid, serialize_float32([0.1] * 1024)))
    db.commit()


def test_ollama_ok_is_silent(config, monkeypatch):
    _ollama(monkeypatch, _Resp(200, {"embeddings": [[0.0]]}))
    assert health.check_ollama(config) is None


def test_ollama_read_timeout_is_silent(config, monkeypatch):
    # Cold model load (~5s) must not raise a false alarm.
    _ollama(monkeypatch, httpx.ReadTimeout("slow"))
    assert health.check_ollama(config) is None


def test_ollama_down_is_reported(config, monkeypatch):
    _ollama(monkeypatch, httpx.ConnectError("refused"))
    assert "não responde" in health.check_ollama(config)


def test_ollama_connect_timeout_is_reported(config, monkeypatch):
    _ollama(monkeypatch, httpx.ConnectTimeout("no listener"))
    assert "não responde" in health.check_ollama(config)


def test_ollama_http_error_is_reported(config, monkeypatch):
    _ollama(monkeypatch, _Resp(500, {"error": "runner aborted"}))
    msg = health.check_ollama(config)
    assert "HTTP 500" in msg and "runner aborted" in msg


def test_missing_embeddings_counts_only_active(db):
    _add_note(db, "a", vector=True)
    _add_note(db, "b")
    _add_note(db, "c", status="archived")
    assert health.count_missing_embeddings(db) == 1


def test_check_health_lists_both_problems(db, config, monkeypatch):
    _ollama(monkeypatch, httpx.ConnectError("refused"))
    _add_note(db, "b")
    problems = health.check_health(db, config)
    assert len(problems) == 2
    assert "1 nota(s)" in problems[1]


def _healthy(monkeypatch):
    monkeypatch.setattr(session_start, "_health_context",
                        lambda config, timeout=0.8: None)


def _handoff_file(vault, project):
    s = vault / "sessoes"
    s.mkdir(exist_ok=True)
    (s / f"handoff-{project}.md").write_text(
        f"---\nproject: {project}\n---\nnext: x", encoding="utf-8")


def test_healthy_without_project_injects_nothing(config, monkeypatch):
    _healthy(monkeypatch)
    _handoff_file(config.vault_root, "other")
    assert session_start.build_context(config, None) is None


def test_handoff_of_other_project_is_not_injected(config, monkeypatch):
    _healthy(monkeypatch)
    _handoff_file(config.vault_root, "other")
    assert session_start.build_context(config, "mine") is None


def test_handoff_of_active_project_is_injected(config, monkeypatch):
    _healthy(monkeypatch)
    _handoff_file(config.vault_root, "mine")
    assert "project: mine" in session_start.build_context(config, "mine")


def test_health_problem_injects_one_line(db, config, monkeypatch):
    _ollama(monkeypatch, httpx.ConnectError("refused"))
    ctx = session_start.build_context(config, None)
    assert ctx.startswith("[ENGRAM SAÚDE]") and "\n" not in ctx


def test_health_checker_failure_is_silent(db, config, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("checker bug")
    monkeypatch.setattr("engram.core.health.check_health", boom)
    assert session_start._health_context(config) is None


def test_main_uses_hook_specific_output(config, monkeypatch, capsys):
    monkeypatch.setattr(session_start, "load_config", lambda: config)
    monkeypatch.setattr(session_start, "build_context", lambda c, p: "LINE")
    session_start.main()
    out = json.loads(capsys.readouterr().out)
    assert out == {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                          "additionalContext": "LINE"}}


def test_main_healthy_prints_empty_object(config, monkeypatch, capsys):
    monkeypatch.setattr(session_start, "load_config", lambda: config)
    monkeypatch.setattr(session_start, "build_context", lambda c, p: None)
    session_start.main()
    assert json.loads(capsys.readouterr().out) == {}
