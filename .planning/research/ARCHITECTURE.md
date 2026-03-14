# Architecture Research: Next Milestone (CodeIndex)

## Recommended Component Boundaries

### 1) Interface Gateway (`cli.py`, `server.py`)
- Responsibility: input parsing, auth/binding policy, request/response mapping, error normalization.
- Must not perform heavy work (no sync checks, no queue draining, no index mutation beyond explicit sync commands).
- Unify parameter contracts for CLI/HTTP/MCP through shared request models and validators.

### 2) Application Orchestrators (`indexer.py`, `search.py`, `analysis.py`, `memory_service.py`)
- Responsibility: compose use-cases (`sync`, `query`, `analyze`, `memory-search`), enforce workspace scoping and budgets.
- Keep deterministic execution paths and explicit fallbacks (vector -> lexical+vector fallback).
- Expose stable service methods consumed by all interfaces.

### 3) Storage Adapters (`storage.py`, `memory_storage.py`)
- Responsibility: schema lifecycle, query primitives, transaction boundaries, capability detection.
- Move extension/feature probes and schema compatibility decisions to startup-time capability registry.
- Separate "data operations" from "maintenance operations" (e.g., vec index sync, migrations, vacuum/rebuild).

### 4) Background Processing (`memory_worker.py` + worker runner)
- Responsibility: async observation processing and stream event production.
- Interface paths should enqueue + optionally bounded flush only; background runner owns backlog processing.
- Define explicit worker health signals (queue depth, oldest pending age).

### 5) Security/Policy Module (new shared policy layer)
- Responsibility: root/path constraints, host exposure policy, token auth checks, output sanitization policies.
- Used by server + MCP + analysis path resolution to prevent drift and path escape regressions.

## Data Flow and Control Flow Implications

### Index + Query flow
1. Startup: capability registry probes (fts5, sqlite-vec/vss) once and stores effective mode.
2. Sync path: `sync_workspace` performs scan/chunk/embed/write, then optional maintenance step (vec sync) in same control plane.
3. Query path: read-only flow chooses retrieval strategy from capability registry; no startup probes/rebuilds on request path.

Implication: lower p95 latency and fewer SQLite lock/contention events under concurrent HTTP requests.

### Memory flow
1. Request path captures observation and enqueues.
2. Request returns without full queue drain.
3. Background worker processes queue and publishes stream state.
4. Memory search/injection reads only committed observation/citation tables.

Implication: predictable user-facing latency and cleaner failure isolation between interaction and enrichment.

### Analysis flow
1. Interface-level policy resolves allowed root/workspace.
2. Analysis functions receive already-authorized root and normalized path.
3. File access remains local-only within enforced boundaries.

Implication: closes current path override vulnerability and aligns CLI/HTTP/MCP behavior.

## Reliability and Performance Seams

### Reliability seams to harden first
- Capability seam: FTS/vector availability must degrade cleanly without schema/init failure.
- Policy seam: centralize auth + root constraints to remove per-endpoint security drift.
- Contract seam: shared request/response schemas for CLI/HTTP/MCP to avoid behavior mismatches.
- Consistency seam: incremental sync change detection should have robust fallback (mtime/size + optional fast hash guard).

### Performance seams to optimize
- Remove per-request `Storage` heavy initialization and vec sync work.
- Introduce long-lived storage handles per process (or per thread) with explicit maintenance windows.
- Improve fallback retrieval by adding lexical pre-filter before Python cosine scoring.
- Keep memory worker off critical path; expose queue metrics for tuning.

## Suggested Build Order for Phased Execution

### Phase A: Security and Policy Foundation (highest risk)
- Add shared policy module for host exposure, token auth, and allowed root enforcement.
- Wire policy checks into HTTP + MCP + analysis entrypoints.
- Fix memory viewer rendering to avoid unescaped HTML injection.

### Phase B: Runtime Capability Stabilization
- Implement startup capability registry for FTS/vector features.
- Make vector extensions optional at packaging/runtime while preserving fallback behavior.
- Add true non-FTS memory fallback path.

### Phase C: Request-Path Latency and Concurrency
- Remove per-request heavy storage initialization/vec sync.
- Introduce managed storage lifecycle and explicit maintenance hooks.
- Move memory queue processing to background worker loop with bounded request-path flush.

### Phase D: Retrieval/Indexing Quality
- Improve incremental sync correctness guard for rapid same-size rewrites.
- Add lexical pre-filter + embedding rerank for fallback mode.
- Strengthen non-Python symbol extraction quality (incremental parser-based improvements where practical).

### Phase E: Regression Coverage and Operational Confidence
- Add tests for path escapes, auth gating, stored-XSS prevention, no-FTS/no-vector runtime, and latency-sensitive flows.
- Add basic operational diagnostics (capability mode, queue depth, fallback mode indicators) to status endpoints.

## Milestone Outcome Target
- Keep modular monolith shape, but make control planes explicit:
  - Request plane: fast, read-focused, policy-enforced.
  - Maintenance plane: sync/migration/index maintenance.
  - Background plane: memory enrichment and streaming updates.
- This structure directly reduces P0/P1 risks while preserving local-first simplicity and interface compatibility.
