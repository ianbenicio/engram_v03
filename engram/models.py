from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class NoteType(str, Enum):
    DECISION = "decision"
    BUG = "bug"
    PATTERN = "pattern"
    CONTEXT = "context"
    RUNBOOK = "runbook"
    SESSION = "session"
    CONCEPT = "concept"
    # v3.1 prepared
    POST_MORTEM = "post-mortem"
    EXPERIMENT = "experiment"
    REFACTORING = "refactoring"
    METRIC = "metric"


class Confidence(str, Enum):
    FACT = "fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"


class NoteData(BaseModel):
    id: str | None = None
    title: str
    tldr: str
    type: NoteType
    confidence: Confidence
    scope: str = "project"
    status: str = "active"
    author: str = "claude"
    subtype: str | None = None
    parent: str | None = None
    project: str | None = None
    module: str | None = None
    tags: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    implements: list[str] | None = None
    supersedes: list[str] | None = None
    superseded_by: list[str] | None = None
    instance_of: str | None = None   # project instance -> global canonical (cross-project)
    code_refs: list[str] | None = None
    session_id: str | None = None
    confidentiality: str = "internal"
    lifecycle: str | None = None     # decision ADR lifecycle: proposed|accepted|superseded|deprecated
    created: str | None = None
    updated: str | None = None
    schema_version: int = 1


class QueryRequest(BaseModel):
    text: str
    project: str | None = None
    projects: list[str] | None = None
    tags: list[str] | None = None
    type_filter: str | None = None
    status_filter: str | None = None
    depth: str | None = None  # "shallow" | "deep" | None
    include_cold: bool = False
    limit: int = 10
