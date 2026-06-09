# Engram — Data-Processing Methodology Spec

**Date:** 2026-06-09
**Status:** Draft for review
**Builds on:** Engram v3.0 (PARA layout, MOC, dual-path retrieval, 6 MCP tools, 123 tests)
**Defines:** the *process/methodology* layer — how each data format is collected,
interpreted, processed, and returned as information; how knowledge is categorized,
related, cleaned, and shared across projects.

---

## 1. Purpose

Engram already has the storage + retrieval engine. This spec defines the
**methodology on top**: a repeatable process for every note type, the tag
taxonomy and its relationships, the project manifest as the context anchor, a
structured garbage collector, and cross-project shared-knowledge handling.

Two simultaneous consumers shape every decision: **humans** (browse, audit) and
**LLMs** (navigate in ≤3 hops, reuse prior knowledge). The methodology serves
both: PARA gives location, `related[]`/`instance_of` give connection, MOCs +
structured frontmatter give navigability.

**Priorities:** efficiency → economy → quality. Curation-first (distilled, not
verbatim).

---

## 2. Per-type playbooks (the core)

### 2.1 Playbook framework — 7 dimensions

Every note type is defined by a 7-dimension playbook. Playbooks are **guidance**
(live in `meta/playbooks.md`, the LLM reads them as context and follows them).
Only the **frontmatter** is hard-enforced by the validator; the body schema is
recommended, not rejected.

| # | Dimension | Answers |
|---|-----------|---------|
| 1 | **Trigger** | When to create this note |
| 2 | **Intake** | What data goes in |
| 3 | **Frontmatter** | Required fields beyond the base (enforced) |
| 4 | **Body schema** | Recommended section structure |
| 5 | **Relations** | Expected links (`related[]`, `instance_of`, `supersedes`...) |
| 6 | **Retrieval** | How/where it is surfaced (Path A/B, MOC bucket) |
| 7 | **Lifecycle** | How it evolves / when it expires / GC retention |

### 2.2 The 11 playbooks

Base required frontmatter (all types): `id, title, tldr, type, confidence,
status, created, updated, author, scope, tags` + tag prefixes `tipo/`,
`maturidade/`, `dominio/`.

---

#### decision (ADR) — PARA: Resources

1. **Trigger:** an architectural/technical choice is made (or proposed for debate).
2. **Intake:** the choice, the context/forces, alternatives considered, rationale, consequences.
3. **Frontmatter:** `lifecycle: proposed|accepted|superseded|deprecated` (default `accepted`); `supersedes`/`superseded_by` when it replaces/was replaced.
4. **Body:** `## Context` / `## Decision` / `## Alternatives` / `## Consequences`.
5. **Relations:** `related[]` → the bug/context that motivated it; `instance_of` → a global canonical decision if it's a project instance of a shared pattern.
6. **Retrieval:** Path A on "decisão sobre X"; Path B on "por que escolhemos X". MOC → Resources/decision. Filterable by `lifecycle: accepted`.
7. **Lifecycle:** `proposed` → `accepted` → (`superseded`|`deprecated`). Never stale while referenced or `confidence: fact`.

#### bug — PARA: Projects

1. **Trigger:** a bug is resolved with root cause identified.
2. **Intake:** symptom, root cause, fix, affected files, prevention.
3. **Frontmatter:** `code_refs[]` (affected files).
4. **Body:** `## Symptom` / `## Root cause` / `## Fix` / `## Prevention`.
5. **Relations:** `related[]` → the `decision` that caused it; → `pattern` if it became a recurring class.
6. **Retrieval:** Path A on the symptom/keywords. MOC → Projects/bug.
7. **Lifecycle:** active → archived when the module is deprecated. Stale-eligible if 0 refs + old + not `fact`.

#### pattern — PARA: Resources

1. **Trigger:** a reusable code/design pattern is identified (≥2 uses).
2. **Intake:** the pattern, when to apply, when NOT to, example.
3. **Frontmatter:** —
4. **Body:** `## Pattern` / `## When to use` / `## When not to` / `## Example`.
5. **Relations:** `related[]` → the `concept`s that ground it; `instance_of` → global canonical if shared across projects.
6. **Retrieval:** Path B on "como costumamos fazer X". MOC → Resources/pattern. High promote-to-global candidate.
7. **Lifecycle:** permanent knowledge; rarely stale. Superseded by a better pattern via `superseded_by`.

#### concept — PARA: Resources

1. **Trigger:** a domain term/concept needs a canonical definition.
2. **Intake:** definition, why it matters, related terms.
3. **Frontmatter:** `aliases[]` (synonyms).
4. **Body:** `## Definition` / `## Why it matters` / `## See also`.
5. **Relations:** `related[]` → concepts it connects to; strong `instance_of`/global candidate (concepts are often cross-project).
6. **Retrieval:** Path A on the term. MOC → Resources/concept. Glossary anchor.
7. **Lifecycle:** permanent. Deprecated only if the term falls out of use.

#### context — PARA: Areas

1. **Trigger:** a project/module's situational context must be captured (spec, scope, constraints).
2. **Intake:** what the module is, its boundaries, constraints, current state.
3. **Frontmatter:** `module`.
4. **Body:** `## Overview` / `## Boundaries` / `## Constraints` / `## Current state`.
5. **Relations:** `related[]` → decisions/runbooks for the module.
6. **Retrieval:** Path B on "o que é o módulo X". MOC → Areas/context. Often an MOC seed.
7. **Lifecycle:** ongoing; `updated` refreshed as the module evolves. Archived when module retired.

#### runbook — PARA: Areas

1. **Trigger:** an operational procedure must be repeatable (setup, deploy, recovery).
2. **Intake:** prerequisites, ordered steps, verification, rollback.
3. **Frontmatter:** `runbook_type` (setup|deploy|recovery|...).
4. **Body:** `## Prerequisites` / `## Steps` / `## Verify` / `## Rollback`.
5. **Relations:** `related[]` → context of the system it operates.
6. **Retrieval:** Path A on "como fazer X". MOC → Areas/runbook.
7. **Lifecycle:** ongoing; updated when the procedure changes. `last_executed`/`last_outcome` optional.

#### session — PARA: Projects (stored at vault-root `sessoes/`)

1. **Trigger:** context ≥ 50% or end of a work session (`vault.handoff`).
2. **Intake:** open decisions, active files, next steps, git branch.
3. **Frontmatter:** `session_id`.
4. **Body:** `## Open Decisions` / `## Active Files` / `## Next Steps` / `## Git Branch`.
5. **Relations:** `related[]` → the notes touched this session.
6. **Retrieval:** SessionStart hook injects the latest per project. Not a knowledge note.
7. **Lifecycle:** ephemeral; GC archives sessions older than the retention window once a newer one exists.

#### post-mortem *(v3.1)* — PARA: Projects

1. **Trigger:** an incident/failure is analyzed after the fact.
2. **Intake:** timeline, impact, root cause, what worked, action items.
3. **Body:** `## Timeline` / `## Impact` / `## Root Cause` / `## Action Items`.
4. **Relations:** `related[]` → the bug/decision involved.
5. **Retrieval:** Path B on "o que deu errado com X". MOC → Projects/post-mortem.
6. **Lifecycle:** permanent record; never auto-stale.

#### experiment *(v3.1)* — PARA: Projects

1. **Trigger:** a hypothesis is tested.
2. **Intake:** hypothesis, method, result, conclusion.
3. **Frontmatter:** `confidence` typically `hypothesis`→`fact` on conclusion; `outcome`.
4. **Relations:** `related[]` → the decision it informs.
5. **Lifecycle:** archived once concluded and its decision is recorded.

#### refactoring *(v3.1)* — PARA: Areas

1. **Trigger:** a tech-debt item or refactor is planned/done.
2. **Frontmatter:** `debt_level`, `debt_status`.
3. **Lifecycle:** active while debt open; archived when resolved.

#### metric *(v3.1)* — PARA: Areas

1. **Trigger:** a tracked measurement.
2. **Frontmatter:** `metric_name`, `unit`, `series`.
3. **Lifecycle:** ongoing; old series points are GC-compactable.

---

## 3. Tag taxonomy + relationships

Three required prefixes, each one dimension:

- **`tipo/`** — mirrors `type` (redundant-by-design for FTS; lets keyword search hit type).
- **`maturidade/`** — lifecycle of *confidence in the note's content*: `draft → stable → deprecated` (+ `experimental`). Orthogonal to `status` (storage) and `confidence` (epistemic).
- **`dominio/`** — the domain/area: `backend`, `frontend`, `infra`, `database`, `auth`, `architecture`, `process`, `mined`, ... (extended per project via the manifest's `domains[]`).

**How they combine in retrieval:** queries filter by any prefix. `tipo/` narrows type, `dominio/` narrows area, `maturidade/stable` excludes drafts/experiments. The router + Path A use these as cheap structured filters before semantic work.

**Relationship to confidence:** `maturidade/` = how mature the *note* is; `confidence` = how verified the *claim* is. A `maturidade/stable` note can still be `confidence: inference`.

---

## 4. Project manifest — the context anchor

Each project has `projetos/{project}/_index.md`. It is read by the LLM **before**
writing or querying that project, and it **drives data treatment**. Three layers:

```yaml
---
# Layer 1 — Identity
project: nexa-avaliacao
display_name: "NEXA Avaliação"
description: "Extrai notas de provas fotografadas via Vision LLM e envia aos responsáveis via WhatsApp."
archetype: web-app            # web-app | cli | library | service | data

# Layer 2 — Technical context
stack: [python, fastapi, supabase, anthropic]
modules: [vision-extraction, student-management, notification-dispatch, admin-panel]
domains: [backend, vision-llm, whatsapp, education]   # extends dominio/ vocab
status: active

# Layer 3 — Treatment directives (drives the process)
enabled_types: [decision, bug, pattern, context, runbook, session]
default_confidentiality: internal     # sensitive project -> restricted
retention_policy:
  stale_days: 365                     # GC override for this project
  gc_level: conservative              # conservative | aggressive
shared_canonicals: []                 # global canonicals this project instantiates
---
```

**The 4 treatment directives (all confirmed):**

1. **`enabled_types`** — which note types make sense here (a library has no `session`). Validator rejects disabled types (already implemented).
2. **`retention_policy`** — per-project GC tuning (`stale_days`, `gc_level`).
3. **`default_confidentiality`** — a sensitive project defaults notes to `restricted` (never sent to external LLM).
4. **`domains[]`** — extends the `dominio/` tag vocabulary and guides categorization + tag validation for this project.

`engram init-project <slug>` scaffolds a manifest from a template.

---

## 5. General vault + cross-project shared knowledge

### 5.1 One general vault

KingVault is **the** vault. All projects live under `projetos/{project}/` (PARA
buckets within). Project-agnostic shared knowledge lives under `global/` (same
PARA buckets). One index, one retrieval engine, scoped by the `project` field.

### 5.2 Canonical + Instances

When the same element (pattern, concept, decision) recurs across projects:

```
global/Resources/patterns/sliding-window-ratelimit.md     <- CANONICAL (scope: cross)
        ^ instance_of                       ^ instance_of
projetos/engram/.../rate_limit.md      projetos/nexa/.../throttle.md
  (contextualizes Engram's use)          (contextualizes NEXA's use)
```

- **Canonical** in `global/` holds the project-agnostic essence.
- **Instances** in each project contextualize *their* use, linked via a new
  frontmatter field **`instance_of: [[canonical-id]]`**.
- No duplication of the essence; each project keeps its context.

### 5.3 Cross-project comparative report

A detector scans embedding similarity **across different projects** (cosine >
threshold, different `project`). Instead of just flagging duplicates, it
produces a **comparative context report**: for each shared element, it shows
*how the same element is used in each project* (convergence/divergence of
application). Output: a report the human/LLM reads to decide whether to promote
the essence to a `global/` canonical and link both as instances.

This runs as a **REPORT tier of `engram gc`** (reuses the similarity engine).

---

## 6. Garbage Collector — `engram gc`

Manual command. Structured, 4-stage, conservative, **never deletes**.

### 6.1 Stages

```
Stage 0 — SCAN: profile each note (age, inbound refs, hash, embedding, status, confidence).

Stage 1 — DETECTION:
  - exact-dup     : identical content_hash
  - near-dup      : cosine similarity > 0.92 (same project)
  - cross-similar : cosine > threshold across DIFFERENT projects  (section 5.3 report)
  - stale         : updated > retention.stale_days AND 0 inbound refs
                    AND confidence != fact AND status active
  - orphan        : no related[] AND no inbound refs
  - superseded    : active but has superseded_by -> should be archived
  - draft-rot     : _mined draft, no promotion > 90d

Stage 2 — CLASSIFICATION into safety tiers:
  AUTO-SAFE   (apply on --apply, no prompt):
      exact-dup -> keep most-referenced/newest, archive the copy
      superseded -> status: archived
      draft-rot  -> move to _mined/_stale/
  SUGGEST     (needs human approval even with --apply):
      near-dup merge (synthesis, section 6.2)
      archive stale
  REPORT-ONLY (never auto-acts):
      orphans (suggest related[])
      cross-similar comparative report (section 5.3)
      god-nodes (suggest promoting to MOC)

Stage 3 — SYNTHESIS (approved near-dup groups only):
  read the N notes -> synthesize 1 consolidated note -> inherits the LOWEST
  confidence of the group -> union of related[] -> old notes get
  superseded_by -> new; old notes -> archived (NOT deleted).

Stage 4 — REPORT: actions taken + pending approvals + metrics (count before/after,
  orphans, dup groups).
```

### 6.2 Safety invariants (non-negotiable)

- **Never deletes.** Only `status: archived` or move to `_cold/`/`_stale/`. Reversible.
- `confidence: fact` **and** referenced → untouchable.
- `restricted` notes never sent to the LLM during synthesis.
- Everything logged to `activity.jsonl`.
- **Dry-run by default**; `--apply` to act. AUTO-SAFE applies; SUGGEST still prompts.
- Per-project thresholds come from the manifest `retention_policy`.

---

## 7. ADR lifecycle field (light)

New **optional** frontmatter field on `decision` notes only:

```yaml
lifecycle: proposed | accepted | superseded | deprecated   # default: accepted
```

Orthogonal to `status` (storage lifecycle) and `confidence` (epistemic). Lets the
LLM filter to `accepted` decisions and trace a decision's evolution. Migration
backfills existing decisions to `accepted`.

---

## 8. What is code vs convention

| Piece | Code | Convention/Doc |
|-------|------|----------------|
| Playbooks (7-dim, 11 types) | frontmatter enforcement (exists) | `meta/playbooks.md` (guidance, LLM reads) |
| Tag taxonomy | tag validation (exists) | `meta/tags.md` (extended) |
| Project manifest | `engram init-project`, manifest reader, directive enforcement | `_index.md` template |
| `instance_of` relation | model field + validator + MOC display | usage convention |
| Cross-project report | `engram gc` REPORT tier (similarity cross-project) | — |
| Garbage collector | `engram gc` (4-stage, tiers, synthesis) | invariants doc |
| ADR lifecycle | model field + validator + migration | — |

---

## 9. Implementation plan (order: Playbooks -> Manifesto -> GC -> cross-link)

1. **Playbooks** — write `meta/playbooks.md` in KingVault (11 playbooks, 7 dims). Extend `meta/tags.md` with relationship notes. *(Mostly doc; no risky code.)*
2. **Manifesto** — manifest template + `engram init-project` + reader that applies the 4 directives (enabled_types already enforced; add retention_policy, default_confidentiality, domains->tag vocab). Backfill `_index.md` for engram + nexa. ADR `lifecycle` field rides here (model + validator + migration).
3. **GC** — `engram gc` with Stages 0–4, tiers, synthesis, invariants. Dry-run default. TDD.
4. **Cross-link** — `instance_of` field + MOC display + the cross-project comparative report tier in `gc`.

Each step: TDD, branch, merge, push.

---

## 10. Open questions

None blocking. All major decisions resolved:
- Playbooks = guidance + frontmatter enforced
- Cross-project = Canonical + Instances (`instance_of`) + comparative report
- Manifest controls all 4 treatment directives
- GC = manual, 4-stage, conservative tiers, never deletes
- ADR = light `lifecycle` field
- Order = Playbooks -> Manifesto -> GC -> cross-link
