from engram.core import manifest
from engram.core.writer import vault_save
from engram.models import NoteData, NoteType, Confidence


def _write_manifest(vault, project, body):
    p = vault / "projetos" / project / "_index.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{body}\n---\n\n# {project}", encoding="utf-8")
    return p


def test_load_manifest_absent_returns_empty(vault, config):
    assert manifest.load_manifest(config.vault_root, "nope") == {}


def test_enabled_types_override(vault, config):
    _write_manifest(vault, "proj", "project: proj\nenabled_types: [bug]")
    assert manifest.enabled_types(config.vault_root, "proj", ["decision"]) == ["bug"]


def test_enabled_types_fallback(vault, config):
    assert manifest.enabled_types(config.vault_root, "proj", ["decision"]) == ["decision"]


def test_default_confidentiality_and_domains_and_retention(vault, config):
    _write_manifest(vault, "proj",
        "project: proj\ndefault_confidentiality: restricted\n"
        "domains: [vision-llm, whatsapp]\n"
        "retention_policy:\n  stale_days: 180\n  gc_level: aggressive")
    assert manifest.default_confidentiality(config.vault_root, "proj") == "restricted"
    assert "vision-llm" in manifest.domains(config.vault_root, "proj")
    rp = manifest.retention_policy(config.vault_root, "proj")
    assert rp["stale_days"] == 180 and rp["gc_level"] == "aggressive"


def test_scaffold_manifest(vault, config):
    res = manifest.scaffold_manifest(config.vault_root, "newproj")
    assert res["status"] == "created"
    assert (vault / "projetos" / "newproj" / "_index.md").exists()
    again = manifest.scaffold_manifest(config.vault_root, "newproj")
    assert again["status"] == "exists"


# --- writer integration: directives applied ---

def _note(dom="backend"):
    return NoteData(title="T", tldr="x", type=NoteType.DECISION,
                    confidence=Confidence.FACT, scope="project", project="proj",
                    tags=["tipo/decision", "maturidade/stable", "dominio/" + dom])


def test_manifest_enabled_types_blocks_in_save(config, db, vault):
    _write_manifest(vault, "proj", "project: proj\nenabled_types: [bug]")
    res = vault_save(_note(), "body para enabled types", config, db)
    assert res["status"] == "error"
    assert "not enabled for project" in res["reason"]


def test_manifest_domain_extends_vocab(config, db, vault):
    _write_manifest(vault, "proj", "project: proj\ndomains: [vision-llm]")
    # dominio/vision-llm is NOT in meta/tags.md but IS in manifest domains
    res = vault_save(_note(dom="vision-llm"), "body domain vocab", config, db)
    assert res["status"] == "ok"


def test_manifest_default_confidentiality_applied(config, db, vault):
    _write_manifest(vault, "proj", "project: proj\ndefault_confidentiality: restricted")
    res = vault_save(_note(), "body restricted default", config, db)
    assert res["status"] == "ok"
    row = db.execute("SELECT confidentiality FROM notes WHERE id=?",
                     (res["note_id"],)).fetchone()
    assert row[0] == "restricted"
