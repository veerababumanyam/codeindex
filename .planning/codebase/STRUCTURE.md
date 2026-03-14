# Repository Structure

## Top-Level Layout
- `codeindex/`: application package with CLI, server, indexing, search, analysis, and memory subsystems.
- `tests/`: end-to-end style tests for CLI and HTTP/MCP behavior.
- `docs/`: user-facing design/usage docs and config examples.
- `.planning/codebase/`: generated mapping outputs (including this file).
- `pyproject.toml`: package metadata, dependencies, and CLI script registration.
- `README.md`: feature overview, usage commands, API endpoints.

## Package Layout (`codeindex/`)
- `codeindex/cli.py`: argparse command tree, command handlers, and shared command lifecycle.
- `codeindex/server.py`: threaded HTTP server, REST route handlers, and MCP JSON-RPC tool dispatch.
- `codeindex/config.py`: default config, YAML load/save, validation, dotted-key updates.
- `codeindex/storage.py`: primary SQLite schema and vector/index persistence APIs.
- `codeindex/indexer.py`: file scan rules, chunking pipeline, symbol extraction, sync stats.
- `codeindex/search.py`: query mode validation, workspace resolution, vector/fallback ranking.
- `codeindex/analysis.py`: static analysis operations (files/symbols/AST/dependencies/complexity/usage/stats).

## Memory Subsystem Files
- `codeindex/memory_service.py`: orchestration facade for sessions, capture, inject, search, status.
- `codeindex/memory_storage.py`: memory schema (`memory_*` tables), queue, FTS search, citation/session queries.
- `codeindex/memory_worker.py`: queue processor that transitions observations to processed state.
- `codeindex/memory_search.py`: layered disclosure payloads (`summary`, `expanded`, `full`).
- `codeindex/memory_injection.py`: query-time injection selection and audit logging.
- `codeindex/memory_capture.py`, `codeindex/memory_hooks.py`, `codeindex/memory_models.py`, `codeindex/memory_config.py`, `codeindex/memory_viewer.py`: capture model, hooks, config, and UI rendering support.

## Tests and Coverage Shape
- `tests/test_cli.py` validates init/sync/query/status, analyze commands, and memory CLI workflows.
- `tests/test_server.py` validates `/search`, `/analysis/*`, `/memory/*`, and `/mcp` including concurrent requests.
- Tests invoke module entry points (`python -m codeindex.cli`) instead of importing private internals directly.

## Docs and Config Artifacts
- `docs/codeindex.example.yaml` provides config template structure.
- `docs/mcp_tree_sitter_integration.md` documents analysis integration intent and feature mapping.
- `README.md` is the operational quick-start and endpoint contract reference.

## Naming and Organization Patterns
- Module names are domain-first and snake_case (example: `memory_injection.py`, `memory_worker.py`).
- Public payloads are plain dictionaries; rich state objects use dataclasses (`MemorySession`, `ChunkRecord`).
- CLI command handlers follow `cmd_<name>` naming in `codeindex/cli.py`.
- Helper internals commonly use `_` prefix (`_run_sync_once`, `_analysis_payload`, `_fallback_scan_top_k`).
- Search modes and capability toggles are centralized constants (`MODE_TO_KINDS`, `DEFAULT_CONFIG`).

## Important Runtime Paths
- Local index DB path convention: `.codeindex/index.db` (computed by `db_path` in `codeindex/cli.py`).
- Config default location: `codeindex.yaml` in current working directory.
- Server default bind: `127.0.0.1:9090` via `codeindex serve` in `codeindex/cli.py`.

## Practical Navigation Tips
- Start feature tracing from interface adapters: `codeindex/cli.py` or `codeindex/server.py`.
- For query relevance issues, inspect `codeindex/search.py` then `codeindex/storage.py` vector backend behavior.
- For sync/index correctness, inspect `codeindex/indexer.py` and `codeindex/embedding.py`.
- For memory behavior, follow `codeindex/memory_service.py` -> `codeindex/memory_storage.py` -> `codeindex/memory_worker.py`.
