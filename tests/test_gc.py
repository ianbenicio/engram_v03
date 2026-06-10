from datetime import datetime, timedelta, timezone

from engram.core.gc import run_gc, detect, _age_days


def _old(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _seed_note(db, vault, nid, title, body, conf="inference", status="active",
               updated=None, project="proj", related=None, superseded_by=None):
    folder = vault / "projetos" / project / "Resources" / "decisoes"
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{nid}.md"
    fm = [f"id: {nid}", f"title: {title}", "type: decision",
          f"confidence: {conf}", "scope: project", f"project: {project}",
          f"status: {status}", "created: c", f"updated: {updated or 'u'}"]
    if related:
        fm.append(f"related: {related}")
    if superseded_by:
        fm.append(f"superseded_by: {superseded_by}")
    p.write_text("---\n" + "\n".join(fm) + "\n---\n\n" + body, encoding="utf-8")
    db.execute(
        "INSERT INTO notes (id,title,tldr,type,confidence,scope,project,status,"
        "created,updated,content_hash,file_path) VALUES "
        "(?,?,?, 'decision',?, 'project',?,?, 'c',?,?,?)",
        (nid, title, "t", conf, project, status, updated or "u",
         f"hash-{nid}", str(p)))
    db.commit()
    return p


def test_age_days_unparseable_is_zero():
    assert _age_days("u") == 0.0
    assert _age_days(None) == 0.0


def test_detect_exact_dup(db, vault, config):
    _seed_note(db, vault, "a", "A", "body")
    _seed_note(db, vault, "b", "B", "body")
    db.execute("UPDATE notes SET content_hash='same' WHERE id IN ('a','b')")
    db.commit()
    det = detect(db, config)
    assert len(det["exact_dups"]) == 1
    grp = det["exact_dups"][0]
    assert grp["keep"] in ("a", "b") and len(grp["drop"]) == 1


def test_detect_stale(db, vault, config):
    _seed_note(db, vault, "old", "Old", "body", conf="inference",
               updated=_old(500))
    det = detect(db, config)
    assert "old" in det["stale"]


def test_fact_not_stale(db, vault, config):
    _seed_note(db, vault, "f", "Fact", "body", conf="fact", updated=_old(500))
    det = detect(db, config)
    assert "f" not in det["stale"]


def test_detect_superseded(db, vault, config):
    _seed_note(db, vault, "s", "Superseded", "body",
               superseded_by="['[[newer]]']")
    det = detect(db, config)
    assert "s" in det["superseded"]


def test_apply_archives_superseded_never_deletes(db, vault, config):
    p = _seed_note(db, vault, "s", "Superseded", "body",
                   superseded_by="['[[newer]]']")
    res = run_gc(db, config, apply=True)
    assert any("archived superseded s" in a for a in res["actions_taken"])
    # file still exists (NOT deleted), status archived
    assert p.exists()
    assert "status: archived" in p.read_text(encoding="utf-8")
    row = db.execute("SELECT status FROM notes WHERE id='s'").fetchone()
    assert row[0] == "archived"


def test_dry_run_takes_no_action(db, vault, config):
    _seed_note(db, vault, "s", "Superseded", "body",
               superseded_by="['[[newer]]']")
    res = run_gc(db, config, apply=False)
    assert res["dry_run"] is True
    assert res["actions_taken"] == []
    row = db.execute("SELECT status FROM notes WHERE id='s'").fetchone()
    assert row[0] == "active"  # untouched
