import os
from engram.core.fsio import atomic_write, format_markdown, cleanup_stale_tmp

def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "sub" / "note.md"
    atomic_write(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"
    assert not (tmp_path / "sub" / "note.md.tmp").exists()

def test_atomic_write_overwrites(tmp_path):
    target = tmp_path / "n.md"
    atomic_write(target, "v1")
    atomic_write(target, "v2")
    assert target.read_text(encoding="utf-8") == "v2"

def test_format_markdown_has_frontmatter_and_body():
    note = {"id": "n1", "title": "T", "tldr": "x", "type": "decision",
            "confidence": "fact", "scope": "project", "status": "active",
            "created": "2026-06-01", "updated": "2026-06-01",
            "author": "claude", "tags": ["tipo/decision"]}
    md = format_markdown(note, "Body text here.")
    assert md.startswith("---\n")
    assert "confidence: fact" in md
    assert "Body text here." in md

def test_cleanup_stale_tmp(tmp_path):
    old = tmp_path / "a.md.tmp"
    old.write_text("x")
    os.utime(old, (0, 0))
    cleanup_stale_tmp(tmp_path, max_age_seconds=60)
    assert not old.exists()
