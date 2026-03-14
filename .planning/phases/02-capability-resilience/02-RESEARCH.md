# Phase 2 Research: Capability Resilience

**Date:** 2026-03-14
**Scope:** CAP-01, CAP-02, CAP-03
**Codebase:** `codeindex-sync`

## Phase Intent

Phase 2 should make the repository install and run predictably in a plain Python + SQLite environment while keeping optional accelerators available when the host supports them. The code already has the right broad direction for vector fallback in [`codeindex/storage.py`](/c:/Users/admin/Desktop/CodeSync/codeindex/storage.py), but packaging, memory schema creation, and operator-visible capability reporting are still inconsistent with that intent.

The implementation should preserve three guarantees:

1. `pip install -e .` succeeds without vector extension wheels.
2. `codeindex init`, `sync`, `query`, and memory workflows continue to work when vector search is unavailable.
3. Memory initialization and search continue to work when SQLite lacks FTS5, with degraded behavior made explicit in every operator-facing status surface.

## Current Repository Reality

## CAP-01: Packaging and Default Install Behavior

- [`pyproject.toml`](/c:/Users/admin/Desktop/CodeSync/pyproject.toml) currently hard-requires `sqlite-vec` and `sqlite-vss`, which directly contradicts the existing runtime fallback path in [`codeindex/storage.py`](/c:/Users/admin/Desktop/CodeSync/codeindex/storage.py).
- [`Storage._try_enable_vector_extension()`](/c:/Users/admin/Desktop/CodeSync/codeindex/storage.py) already falls back deterministically from `sqlite-vec` to `sqlite-vss` to `python-cosine`.
- Existing query tests already accept all three backends in both CLI and HTTP flows, which is a strong sign that the codebase is already designed for optional vector acceleration.

Implication: CAP-01 is primarily a packaging and verification problem, not a search-architecture rewrite.

## CAP-02: Memory Degradation When FTS5 Is Missing

- [`codeindex/memory_storage.py`](/c:/Users/admin/Desktop/CodeSync/codeindex/memory_storage.py) probes FTS5 with `fts5_available()`, but `MemoryStorage.__init__()` still unconditionally runs `CREATE VIRTUAL TABLE ... USING fts5(...)`.
- `mark_processed()` unconditionally writes to `memory_observation_fts`.
- `search_observations()` unconditionally queries `memory_observation_fts` with `bm25(...)`.
- [`MemoryService.capabilities()`](/c:/Users/admin/Desktop/CodeSync/codeindex/memory_service.py) already records an FTS5 capability snapshot, so the reporting path exists, but the storage/search implementation does not honor it yet.

Implication: CAP-02 needs a real storage-level bifurcation between accelerated FTS search and degraded SQL/Python text search. The degradation decision should live in `MemoryStorage`, not in CLI/server handlers.

## CAP-03: Capability Visibility

- Query responses already expose `metrics.vector_backend` from [`codeindex/search.py`](/c:/Users/admin/Desktop/CodeSync/codeindex/search.py).
- [`cmd_status()`](/c:/Users/admin/Desktop/CodeSync/codeindex/cli.py) currently returns only index counts, so the main CLI status surface hides the active vector mode.
- Memory status already returns a `capabilities` list from [`MemoryStorage.status()`](/c:/Users/admin/Desktop/CodeSync/codeindex/memory_storage.py), but it only contains `name`, `available`, and `checked_at`, not the effective search mode or degraded reason.
- HTTP `/memory/status` and MCP `codeindex_memory_status` mirror the same storage payload via [`codeindex/server.py`](/c:/Users/admin/Desktop/CodeSync/codeindex/server.py), so CAP-03 can be solved centrally if the status payload is improved in `Storage` and `MemoryStorage`.

Implication: the missing work is not transport parity. The missing work is a normalized capability summary produced once in domain/storage code and reused everywhere.

## Recommended Implementation Approach

## Standard Stack

- Keep SQLite as the only required database dependency.
- Keep `sqlite-vec` and `sqlite-vss` as optional accelerators only.
- Keep the existing pure-Python cosine fallback in [`codeindex/search.py`](/c:/Users/admin/Desktop/CodeSync/codeindex/search.py).
- Implement FTS degradation with plain SQLite table scans and `LIKE` filters inside [`MemoryStorage.search_observations()`](/c:/Users/admin/Desktop/CodeSync/codeindex/memory_storage.py).
- Keep capability computation local to `Storage` and `MemoryService` rather than adding new config switches.

## Architecture Patterns

### 1. Make capability detection authoritative at the storage/service layer

Add explicit capability-summary helpers rather than reconstructing state in each interface:

- `Storage.capabilities()` or `Storage.status_summary()`
- `MemoryStorage.capabilities()` or an expanded `MemoryStorage.status()`
- `MemoryService.status()` should merge memory counts with the effective memory-search mode

Recommended payload shape:

```json
{
  "vector": {
    "backend": "python-cosine",
    "accelerated": false,
    "available_backends": ["python-cosine"],
    "degraded": true
  },
  "memory": {
    "search_backend": "sql-like",
    "fts5_available": false,
    "degraded": true
  }
}
```

This fits current JSON-returning patterns without forcing transport-specific logic.

### 2. Split memory schema into required tables and optional FTS objects

Do not keep a single `MEMORY_SCHEMA` string that always creates the FTS table. That is the current failure source.

Recommended refactor:

- Keep base tables/indexes in one schema string that always executes.
- Probe FTS5 once during `MemoryStorage.__init__()`.
- If FTS5 is available, create `memory_observation_fts`.
- If FTS5 is unavailable, skip virtual table creation and record capability details immediately.

This avoids schema init failure during `codeindex init`, `status`, `query`, HTTP boot, and memory viewer boot.

### 3. Keep degraded memory search inside `MemoryStorage.search_observations()`

The CLI, HTTP, and MCP surfaces already call `MemoryService.search()`, which delegates to `search_memory()`, which delegates to `MemoryStorage.search_observations()`. That is the correct seam for fallback behavior.

Recommended degraded search logic:

- Empty query: keep the existing recent-processed-observations path unchanged.
- Non-empty query with FTS5:
  - Keep current FTS `MATCH` + `bm25(...)` path.
- Non-empty query without FTS5:
  - Tokenize terms with the current regex.
  - Query `memory_observations` directly with `LOWER(title) LIKE ? OR LOWER(body) LIKE ? OR LOWER(summary) LIKE ?`.
  - Restrict to `workspace`, `status='processed'`, and `importance >= ?`.
  - Rank in Python with a simple deterministic score:
    - title match bonus
    - summary match bonus
    - body match bonus
    - recency tiebreaker by `created_at DESC`

This is enough for CAP-02 because the phase requirement is degraded usefulness, not equivalent retrieval quality.

### 4. Guard FTS maintenance writes

[`mark_processed()`](/c:/Users/admin/Desktop/CodeSync/codeindex/memory_storage.py) must not touch `memory_observation_fts` when the virtual table does not exist. That write path should check an instance-level capability flag computed at initialization.

Without this guard, memory processing will still fail later even if schema init is fixed.

### 5. Expose capability mode consistently

Recommended surfaces:

- `codeindex query`
  - Keep `metrics.vector_backend`.
  - Add a small `metrics.vector_accelerated` boolean if needed for easier assertions.
- `codeindex status`
  - Expand current counts payload to include a `capabilities` object with vector and memory summaries.
- `codeindex memory status`
  - Replace or augment the current `capabilities` list with explicit effective mode fields:
    - `memory_search_backend`
    - `fts5_available`
    - `degraded`
- HTTP `/memory/status` and MCP `codeindex_memory_status`
  - Reuse exactly the same structure as CLI `memory status`.

For this repo, prefer additive changes over replacing fields outright, because tests and future compatibility work in Phase 5 will benefit from stable existing keys.

## Don’t Hand-Roll

- Do not add a new search subsystem or external text index just for memory degradation.
- Do not duplicate capability computation in CLI, HTTP, and MCP handlers.
- Do not disable the memory subsystem entirely when FTS5 is missing; the phase context explicitly rejects that behavior.
- Do not make vector capability configurable in YAML when runtime probing already determines it correctly.
- Do not make default install depend on wheel availability for optional extensions.

## Sequencing

Recommended order for this repository:

1. Packaging first.
   Move `sqlite-vec` and `sqlite-vss` out of `[project].dependencies` and into a new optional extra such as `vectors`.
2. Storage/status plumbing second.
   Add storage-level capability summary helpers for vector and memory modes.
3. Memory schema split third.
   Refactor `MemoryStorage` initialization so base schema always succeeds and FTS objects are conditional.
4. Memory degraded search fourth.
   Implement `search_observations()` fallback and guard `mark_processed()`.
5. Surface reporting fifth.
   Update `cmd_status()`, `cmd_memory_status()`, `/memory/status`, and MCP status output to show effective modes.
6. Regression tests last, but in the same phase.
   Add missing-backend tests for both vector and FTS degradation separately.

This sequence reduces risk because packaging and schema initialization are the blockers that currently prevent degraded behavior from existing at all.

## Test Strategy

## Unit/Focused Coverage

Add targeted tests around the actual degradation seams instead of only end-to-end process tests.

Recommended new tests:

- `tests/test_cli.py`
  - `status` includes vector and memory capability summary.
  - default install path behavior is represented by monkeypatching `codeindex.storage.sqlite_vec = None` and `sqlite_vss = None`, then asserting query still succeeds and reports `python-cosine`.
  - `memory status` reports degraded mode when FTS5 probe is forced false.
- New or existing focused tests for `MemoryStorage`
  - init succeeds when FTS5 creation is unavailable.
  - `mark_processed()` does not attempt FTS writes in degraded mode.
  - `search_observations()` returns results through fallback SQL path.

## Integration Coverage

Extend current CLI/server integration style rather than introducing a new test harness.

Recommended integration cases:

- CLI flow with missing vector extensions:
  - `init`
  - `sync`
  - `query`
  - assert `metrics.vector_backend == "python-cosine"`
- CLI flow with missing FTS5:
  - capture/query to create memory observations
  - `memory search`
  - `memory status`
  - assert search still returns hits and status reports degraded backend
- HTTP flow with missing FTS5:
  - `/memory/status`
  - `/memory/search`
  - assert parity with CLI payload
- MCP flow with missing FTS5:
  - `codeindex_memory_status`
  - ensure the same capability fields are present

## How to Simulate Missing Capabilities in Tests

For this codebase, prefer monkeypatching over relying on a special SQLite build:

- vector absence:
  - monkeypatch `codeindex.storage.sqlite_vec = None`
  - monkeypatch `codeindex.storage.sqlite_vss = None`
- FTS5 absence:
  - monkeypatch `codeindex.memory_storage.fts5_available` to return `False`
  - if needed, monkeypatch connection execution paths that create or write to the FTS table to fail if reached, proving the fallback path is actually used

This is more deterministic than depending on CI SQLite compilation flags.

## Common Pitfalls

- `MemoryService.capabilities()` currently caches results in module-global `_CAPABILITY_CACHE`. If one test or process computes `fts5_available=True`, later tests may observe stale state even when patched false. Phase 2 should either remove the global cache, key it per connection/runtime, or provide a deterministic refresh path.
- `Storage.__init__()` still calls `_sync_vec_index()` on every open. That is not in scope for Phase 2, but any status/capability refactor must avoid making this path heavier.
- Changing `cmd_status()` output shape too aggressively can break existing consumers. Add capability fields without removing counts.
- The current `memory_capabilities` table stores generic `details_json`, but `MemoryStorage.status()` discards those details. If richer status is required, make sure the read side exposes the effective backend and reason, not just raw availability rows.
- Server handlers instantiate `Storage` per request. Capability reporting must therefore be cheap and deterministic.
- If fallback search ranking is too clever, the implementation will drift into retrieval-quality work that belongs to later phases. Keep it simple and predictable.

## Concrete Planning Guidance

### CAP-01

- Change default dependency set to pure-Python-safe:
  - keep `PyYAML` in required dependencies
  - move `sqlite-vec` and `sqlite-vss` to an extra such as `[project.optional-dependencies].vectors`
- Update docs/sample install guidance later if planning requires it, but code changes should not depend on docs first.
- Preserve runtime probing exactly as-is unless a capability summary helper needs to expose attempted backends.

### CAP-02

- Refactor `codeindex/memory_storage.py` to:
  - separate base schema from optional FTS schema
  - persist an instance flag like `self._fts5_enabled`
  - use that flag in both `mark_processed()` and `search_observations()`
- Keep the `memory_capabilities` table and use it to expose degraded mode details instead of adding a separate status table.
- Ensure `MemoryService.status()` always records and returns current capability state before responding.

### CAP-03

- Add a storage capability summary to CLI `status`.
- Keep query `metrics.vector_backend` as the canonical query-time vector signal.
- Normalize memory capability fields so HTTP and MCP do not need transport-specific transformation.
- Prefer machine-readable booleans and backend names over prose-only strings.

## Validation Architecture

Nyquist validation for this phase should be derived from three independent fault domains, each with direct assertions.

### Domain A: Default Install / No Vector Extensions

Validate:

- `Storage` initialization succeeds when both vector modules are unavailable.
- CLI `query` returns results and reports `python-cosine`.
- HTTP `/search` returns results and reports `python-cosine`.

Evidence:

- monkeypatched module absence tests
- CLI integration assertion on `metrics.vector_backend`
- HTTP integration assertion on `metrics.vector_backend`

### Domain B: No FTS5

Validate:

- `MemoryStorage` initialization succeeds when FTS5 is unavailable.
- memory processing does not attempt FTS writes in degraded mode.
- CLI/HTTP/MCP memory search still return best-effort results from processed observations.

Evidence:

- focused storage tests for init and `mark_processed()`
- CLI `memory search` integration test
- HTTP `/memory/search` integration test
- MCP `codeindex_memory_search` integration test

### Domain C: Capability Visibility / Parity

Validate:

- CLI `status` reports vector and memory capability summary.
- CLI `memory status`, HTTP `/memory/status`, and MCP `codeindex_memory_status` report the same effective memory-search mode.
- degraded flags and backend names are deterministic and machine-readable.

Evidence:

- payload shape assertions in CLI tests
- HTTP and MCP parity assertions against the same expected keys
- explicit degraded-mode assertions under monkeypatched no-vector and no-FTS configurations

## Code Examples

Minimal design target for memory status:

```json
{
  "sessions": 3,
  "observations": 12,
  "citations": 12,
  "queue": {"processed": 12},
  "capabilities": {
    "memory_search_backend": "sql-like",
    "fts5_available": false,
    "degraded": true
  }
}
```

Minimal design target for general status:

```json
{
  "files": 10,
  "chunks": 44,
  "symbols": 9,
  "workspaces": 1,
  "capabilities": {
    "vector": {
      "backend": "python-cosine",
      "accelerated": false,
      "degraded": true
    },
    "memory": {
      "search_backend": "sql-like",
      "fts5_available": false,
      "degraded": true
    }
  }
}
```

## Confidence

- CAP-01 packaging direction: High
- CAP-02 schema/fallback design: High
- CAP-03 surface/reporting approach: High
- Exact final JSON key names: Medium
- Whether `_CAPABILITY_CACHE` should be removed entirely versus refreshed per process: Medium
