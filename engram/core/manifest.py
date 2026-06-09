"""Project manifest (`projetos/{project}/_index.md`) — the context anchor.

The manifest drives data treatment per project via 4 directives:
  - enabled_types          : which note types are allowed
  - default_confidentiality: default confidentiality for new notes
  - domains[]              : extends the dominio/ tag vocabulary
  - retention_policy       : per-project GC tuning (stale_days, gc_level)

All loaders degrade gracefully: a missing manifest returns empty/None and the
caller falls back to global config.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def manifest_path(vault_root: Path, project: str) -> Path:
    return vault_root / "projetos" / project / "_index.md"


def load_manifest(vault_root: Path, project: str | None) -> dict:
    """Parse the project _index.md frontmatter. Returns {} if absent/malformed."""
    if not project:
        return {}
    path = manifest_path(vault_root, project)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def enabled_types(vault_root: Path, project: str | None,
                  fallback: list[str]) -> list[str]:
    """Per-project enabled_types override; falls back to global config list."""
    m = load_manifest(vault_root, project)
    val = m.get("enabled_types")
    return val if isinstance(val, list) and val else list(fallback)


def default_confidentiality(vault_root: Path, project: str | None) -> str | None:
    m = load_manifest(vault_root, project)
    val = m.get("default_confidentiality")
    return val if isinstance(val, str) else None


def domains(vault_root: Path, project: str | None) -> list[str]:
    """Project domain vocabulary — extends the dominio/ tags."""
    m = load_manifest(vault_root, project)
    val = m.get("domains")
    return val if isinstance(val, list) else []


def retention_policy(vault_root: Path, project: str | None) -> dict:
    """GC tuning for the project. Defaults: stale_days=365, gc_level=conservative."""
    m = load_manifest(vault_root, project)
    rp = m.get("retention_policy") or {}
    return {
        "stale_days": rp.get("stale_days", 365),
        "gc_level": rp.get("gc_level", "conservative"),
    }


MANIFEST_TEMPLATE = """---
# Layer 1 — Identity
project: {project}
display_name: "{project}"
description: "TODO: one-sentence description of the project."
archetype: web-app            # web-app | cli | library | service | data

# Layer 2 — Technical context
stack: []
modules: []
domains: []                   # extends dominio/ tag vocabulary
status: active

# Layer 3 — Treatment directives
enabled_types: [decision, bug, pattern, context, runbook, session, concept]
default_confidentiality: internal
retention_policy:
  stale_days: 365
  gc_level: conservative
shared_canonicals: []
---

# {project}

TODO: project overview. This manifest is read before writing/querying this
project and drives how its data is treated.
"""


def scaffold_manifest(vault_root: Path, project: str) -> dict:
    """Create projetos/{project}/_index.md from the template if absent."""
    path = manifest_path(vault_root, project)
    if path.exists():
        return {"status": "exists", "path": str(path)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MANIFEST_TEMPLATE.format(project=project), encoding="utf-8")
    return {"status": "created", "path": str(path)}
