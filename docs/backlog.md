# Engram — Backlog (post-v3.0)

Ideas evaluated against priorities (efficiency > economy > structure) and the
curation-first essence (Engram stores distilled knowledge, NOT verbatim).
Source of inspiration: MemPalace (https://github.com/MemPalace/mempalace).

Rejected ideas and why:
- **Verbatim storage** — violates curation-first essence (noise + context pollution).
- **Temporal validity windows** — redundant with existing `supersedes`/`superseded_by` relations.
- **Palace metaphor (Wings/Rooms/Drawers)** — conceptual overhead; projetos/tags are more direct.
- **29 tools** — contradicts economy; 6 focused tools beat 29.
- **ChromaDB** — sqlite-vec suffices, fewer deps, and Obsidian markdown stays human-readable.

---

## BL-01: Hybrid retrieval — recency boost in Path A (HIGH) — ✅ DONE (commit 09a3f23)

**Why:** Path A currently orders by FTS5 `rank` only. Adding a recency boost
improves ranking quality deterministically (zero LLM), so the right notes
surface earlier. Better Path A results → fewer escalations to the heavier
Path B → token economy. Direct efficiency + structure win.

**Design:**
- Add an optional `recency_weight` (default ~0.2) to `path_a`.
- Final score = `fts_rank_score + recency_weight * recency_factor`, where
  `recency_factor` decays with age from `notes.updated` (e.g. exponential
  half-life of ~90 days).
- Pure Python post-sort on the FTS result rows; no schema change (uses
  existing `updated` column). Keep FTS `ORDER BY rank LIMIT k*3`, then
  re-sort the candidate window by combined score, return top-k.
- Config key: `[retrieval] recency_weight`, `recency_halflife_days`.

**Tests:** two notes equal FTS rank, newer one ranks first; `recency_weight=0`
reproduces current behavior (backward-compatible).

**Effort:** Low (1 task, ~1 file + tests). No new deps.

---

## BL-02: Cheap embedding rerank in Path B (MEDIUM-LOW) — ✅ DONE (commit pending)

**Why:** Path B orders by vector L2 distance from the KNN query. A rerank can
tighten precision of the top-7 sent to synthesis (less irrelevant context →
fewer wasted synth tokens). Must stay cheap: NO extra LLM call.

**Design:**
- After KNN returns top-N (e.g. N=20), re-score candidates with a cheap
  signal combo: vector similarity + FTS keyword overlap (already have FTS) +
  recency. Take top-7 by combined score into synthesis.
- Strictly local, deterministic, zero extra network/LLM cost.
- Optional `[retrieval] rerank=true` flag; default off to preserve current
  behavior until validated.

**Tests:** candidate with high vector sim but zero keyword overlap ranks below
one with both; flag off = current behavior.

**Effort:** Low-Medium. No new deps (reuses embeddings + FTS).

**Note:** MemPalace's LLM-rerank tier is explicitly NOT adopted — an extra LLM
call per query contradicts the economy priority. Only the keyword/recency
re-score is in scope.

---

## BL-03: Mining mode — retroactive import (MEDIUM) — ✅ DONE (commit pending)

**Why:** Engram captures knowledge on-the-fly during sessions. Mining lets a
user backfill an existing vault or import past Claude Code transcripts/files
as candidate notes — coverage/structure gain. Stays curation-first: mining
produces DRAFT notes for human/Claude review, never auto-commits verbatim.

**Design:**
- New CLI: `engram mine <path> [--mode files|convos] --project <slug>`.
- Parses source files / transcript JSONL, extracts candidate knowledge units,
  writes them as `status: draft`, `confidence: hypothesis` notes into a
  `_mined/` staging area (NOT the live folders).
- Human/Claude reviews, promotes (via `vault.update` status→active) or deletes.
- Never sends restricted content anywhere; mining is fully local.
- Reuses existing writer/validator/indexer pipeline.

**Tests:** mining a dir of N markdown files creates N draft notes in `_mined/`;
drafts excluded from default Path A/B queries (status filter); promote flow.

**Effort:** Medium (1-2 tasks). No new deps.

---

## BL-04: Benchmark suite (LOW / DEFER)

**Why:** No objective retrieval metric today. A benchmark (à la MemPalace's
LongMemEval R@5) would validate the dual-path router objectively. This is
quality-assurance, not an efficiency/structure improvement — defer until
core v3.0 is shipped and stable.

**Design (sketch):**
- Curated Q→expected-note-id dataset over a seeded test vault.
- Harness measures R@5 for Path A, Path B, and router choice accuracy.
- Reported as a CLI `engram bench` (dev-only, behind `[dev]` extra).

**Effort:** High. Defer to a post-v3.0 milestone.

---

## Suggested sequencing (after v3.0 F0–F5 complete)

1. BL-01 (recency boost) — highest value/effort ratio, pure efficiency.
2. BL-02 (cheap rerank) — builds on BL-01 scoring helpers.
3. BL-03 (mining) — coverage; independent.
4. BL-04 (benchmarks) — validate, once 1–3 land.

---

## Code-review follow-ups (from 2026-06-03 final review)

Minor findings deferred after the critical embedding-on-save bug was fixed
(commit `21ad813`). None blocking; logged for quality follow-through.

- **CR-01 (robustness):** `indexer.upsert_note` hard-subscripts `note["title"]`,
  `["type"]`, `["confidence"]`, `["created"]`, `["updated"]`. A note hand-edited
  in Obsidian that drops one of these keys raises `KeyError` from
  `vault_update`/`reindex_file` instead of a structured error. Add a
  required-key guard that returns `{"status":"error"}` (or skips with a warning
  during reindex).
- **CR-02 (hub accuracy):** `hubs.hub_notes` counts inbound wikilinks by raw
  `[[target]]` string matched against note `id`. Human-authored `[[Title]]`
  links (not `[[id]]`) are silently dropped from centrality. Resolve link
  targets through a title/path→id lookup before counting.
- **CR-03 (spec gap §5.4 step 7):** `module` is stored but never validated
  against the project `_index.md` declared modules (spec wanted a non-blocking
  warning). Implement `validate_module` and surface as a warning in `vault_save`.
- **CR-04 (cleanup):** drop the unused `import sqlite3` in `embeddings.py`
  (added during the fix; harmless but lint-noise).

Accepted (no action): FTS5 created as a normal table with `note_id UNINDEXED`
rather than `content=''` contentless — internally consistent (manual
DELETE+INSERT sync), so a deliberate deviation, not a bug. Clustering uses
cosine-threshold connected components instead of Leiden (intentional, see §7).
