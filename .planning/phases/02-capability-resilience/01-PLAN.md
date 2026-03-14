---
phase: 02
plan_id: 01-PLAN
title: Optional Capability Fallbacks and Visible Runtime Modes
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - codeindex/storage.py
  - codeindex/memory_storage.py
  - codeindex/memory_service.py
  - codeindex/cli.py
  - codeindex/server.py
  - tests/test_memory_storage.py
  - tests/test_cli.py
  - tests/test_server.py
autonomous: true
requirements:
  - CAP-01
  - CAP-02
  - CAP-03
---

# Phase 2 Plan 01: Optional Capability Fallbacks and Visible Runtime Modes

<goal>
Make baseline CodeIndex workflows install and run predictably without optional SQLite accelerators, while exposing the active degraded or accelerated capability mode consistently across CLI, HTTP, and MCP.
</goal>

<must_haves>
- Default package installation succeeds without `sqlite-vec` or `sqlite-vss`.
- Query flows remain functional and explicitly report the active vector backend when extensions are absent.
- Memory initialization, processing, and search continue to work when SQLite lacks FTS5.
- Capability state is centralized in storage or service code and exposed in machine-readable status payloads.
- Tests independently cover no-vector and no-FTS degradation paths rather than relying on one mixed fallback scenario.
</must_haves>

<scope>
- Move vector accelerators off the required dependency path in `pyproject.toml` while preserving existing runtime probing in `codeindex/storage.py`.
- Refactor `codeindex/memory_storage.py` so required schema setup is separate from optional FTS objects and degraded search remains functional.
- Adjust `codeindex/memory_service.py` capability reporting so fallback mode is deterministic and testable.
- Extend `codeindex/cli.py` and `codeindex/server.py` to surface consistent capability summaries without transport-specific duplication.
- Add regression coverage in `tests/test_cli.py` and `tests/test_server.py` for fallback query, memory search, and status parity.
</scope>

<tasks>
  <task id="02-01-01" requirement="CAP-01">
    <objective>Make vector extensions optional at install time while keeping fallback query behavior first-class.</objective>
    <implementation>
      - Move `sqlite-vec` and `sqlite-vss` out of required dependencies in `pyproject.toml` and into an optional extra so `pip install -e .` works in a plain Python + SQLite environment.
      - Preserve the existing runtime fallback order in `codeindex/storage.py`, but add a small capability summary helper if needed so the active backend can be reused by status surfaces without re-deriving it elsewhere.
      - Keep `python-cosine` as the deterministic baseline backend when extension imports or loading fail.
    </implementation>
    <files>pyproject.toml, codeindex/storage.py, tests/test_cli.py, tests/test_server.py</files>
    <verification>
      - `python -m pip install -e .`
      - `pytest tests/test_cli.py tests/test_server.py -q -k "query or status"`
      - Add a direct install-path verification that proves editable install succeeds after vector packages move behind an optional extra.
      - Add monkeypatched no-vector coverage that proves CLI and HTTP query flows still succeed and report `python-cosine`.
    </verification>
  </task>

  <task id="02-01-02" requirement="CAP-02">
    <objective>Keep memory workflows degraded but operational when FTS5 is unavailable.</objective>
    <implementation>
      - Split `codeindex/memory_storage.py` schema setup into required tables and optional FTS objects so initialization does not fail on SQLite builds without FTS5.
      - Persist an instance-level FTS capability flag and use it to guard both FTS maintenance writes in `mark_processed()` and query behavior in `search_observations()`.
      - Implement a simple deterministic fallback search path over `memory_observations` for non-empty queries, while preserving the existing recent-items path for empty queries.
      - Make `codeindex/memory_service.py` refresh or recompute capability state deterministically so fallback tests do not depend on stale global cache state.
    </implementation>
    <files>codeindex/memory_storage.py, codeindex/memory_service.py, tests/test_memory_storage.py, tests/test_cli.py, tests/test_server.py</files>
    <verification>
      - `pytest tests/test_memory_storage.py tests/test_cli.py tests/test_server.py -q -k "memory or fts"`
      - Add focused storage-level tests for no-FTS initialization, guarded `mark_processed()` writes, and fallback `search_observations()` behavior.
      - Add no-FTS integration coverage that proves memory init succeeds, processed observations are still searchable, and degraded mode does not attempt FTS table writes.
    </verification>
  </task>

  <task id="02-01-03" requirement="CAP-03">
    <objective>Expose one consistent capability summary across status surfaces.</objective>
    <implementation>
      - Extend `codeindex/cli.py` `status` output to include additive `capabilities` data for vector and memory mode without removing existing count fields.
      - Expand `codeindex/memory_storage.py` and `codeindex/memory_service.py` status payloads so memory status reports effective backend, FTS availability, and degraded state in machine-readable fields.
      - Reuse the same status structures in `codeindex/server.py` for HTTP `/memory/status` and MCP `codeindex_memory_status`, preserving transport parity by delegating to shared domain logic.
      - Add regression assertions that accelerated and degraded modes are both visible and deterministic in CLI, HTTP, and MCP responses.
    </implementation>
    <files>codeindex/cli.py, codeindex/memory_storage.py, codeindex/memory_service.py, codeindex/server.py, tests/test_cli.py, tests/test_server.py</files>
    <verification>
      - `pytest tests/test_cli.py tests/test_server.py -q -k "status or memory_status"`
      - Assert matching capability keys and degraded flags across CLI `status`, CLI `memory status`, HTTP `/memory/status`, and MCP `codeindex_memory_status`.
      - Add accelerated-mode assertions for the default-capable path so status outputs prove both accelerated and degraded reporting behavior.
    </verification>
  </task>
</tasks>

<execution_order>
- Complete packaging and vector capability plumbing first so fallback query behavior has a stable baseline for later status assertions.
- Refactor memory schema and degraded search next, because capability visibility is only meaningful once no-FTS operation is real rather than theoretical.
- Finalize shared status payloads after both fallback paths exist so CLI, HTTP, and MCP can all reuse the same effective capability picture.
- Keep capability computation centralized in `Storage`, `MemoryStorage`, and `MemoryService` rather than branching per interface.
</execution_order>

<acceptance_criteria>
- A fresh default install no longer requires SQLite vector extension packages.
- CLI and HTTP query flows succeed when vector extensions are unavailable and report `python-cosine` as the active backend.
- Editable install succeeds after vector extensions move to an optional dependency path.
- Memory storage initialization succeeds when FTS5 is unavailable, and memory capture, processing, status, and search continue to function in degraded mode.
- Storage-level tests prove no-FTS initialization, writes, and search behavior independently of transport integration coverage.
- `status` and memory status payloads expose explicit vector and memory capability data with deterministic backend names and degraded booleans.
- CLI, HTTP, and MCP report the same effective memory capability mode without transport-specific divergence.
- Regression tests independently prove accelerated and fallback behavior for vector and memory capability reporting.
</acceptance_criteria>

<handoff>
This single wave-1 plan covers the full Phase 2 scope defined in the roadmap and matches the validation contract in `02-VALIDATION.md`. After execution, Phase 2 should be ready for verification against CAP-01 through CAP-03 before moving on to the latency-focused work in Phase 3.
</handoff>
