# Phase 2: Capability Resilience - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Make optional acceleration features non-blocking so a plain Python + SQLite environment can install, initialize, query, and use memory features predictably even when vector extensions or FTS5 are unavailable.

</domain>

<decisions>
## Implementation Decisions

### Baseline installation path
- Default installation must succeed without `sqlite-vec` or `sqlite-vss` being installed.
- Vector extensions should move off the required dependency path and remain optional accelerators.
- Runtime behavior should preserve functional search using the existing Python cosine fallback when vector extensions are absent.

### Memory degradation behavior
- Memory schema initialization must not fail when FTS5 is unavailable.
- Memory features should stay enabled in degraded mode rather than turning into hard errors.
- Degraded memory mode should preserve core workflows first: session capture, status, expand, and best-effort search over stored observations.

### Capability visibility
- Active capability mode should be visible in operator-facing outputs, not hidden in internals.
- CLI `status` and memory status output should identify vector and memory-search capability state explicitly.
- HTTP and MCP memory status surfaces should expose the same capability picture so all interfaces agree on degradation state.

### Test posture
- Phase 2 must add regression coverage for both accelerated and fallback paths.
- Tests should exercise missing vector extensions and missing FTS5 independently, because they degrade different subsystems.

### Claude's Discretion
- Exact JSON field names for capability summaries.
- Whether degraded memory search uses a direct SQL scan, Python filtering, or another simple local fallback.
- Whether capability metadata is computed lazily per process or refreshed on each status call, as long as outputs stay accurate and deterministic.

</decisions>

<specifics>
## Specific Ideas

- Prefer "degraded but working" over "feature silently disabled" anywhere the existing data model can still support useful behavior.
- Keep fallback behavior explicit in responses so plain-environment users understand why performance or ranking changed.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `codeindex/storage.py`: already implements deterministic vector backend fallback order ending in `python-cosine`.
- `codeindex/memory_service.py`: already records capability snapshots and exposes them through `status()`.
- `codeindex/memory_storage.py`: already has `fts5_available()` probing and a capability table that can carry richer degraded-mode signals.
- `tests/test_cli.py` and `tests/test_server.py`: existing CLI and HTTP integration coverage can be extended for fallback-mode assertions.

### Established Patterns
- Optional runtime features are guarded with `try/except` imports and explicit capability checks.
- CLI and HTTP/MCP surfaces all serialize machine-readable JSON payloads, which is the right place to expose capability mode.
- Memory lifecycle logic flows through `MemoryService`, so resilience changes should stay centralized there rather than being duplicated per surface.

### Integration Points
- Packaging changes touch `pyproject.toml` and user-facing installation/config docs.
- Vector capability work centers on `Storage` initialization and status output in CLI/server payloads.
- Memory FTS fallback work centers on `MemoryStorage`, `MemoryService`, and the memory status/search endpoints.

</code_context>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 02-capability-resilience*
*Context gathered: 2026-03-14*
