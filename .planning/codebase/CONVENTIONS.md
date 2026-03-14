# Repository Conventions

## Scope and Sources
- This document reflects conventions observed in `codeindex/` and usage in `tests/`.
- Primary entry points are `codeindex/cli.py` (CLI), `codeindex/server.py` (HTTP + MCP), and `codeindex/indexer.py` (indexing flow).

## Style
- Language target is Python 3.10+ with modern typing (`dict[str, Any]`, `str | None`) across files like `codeindex/cli.py` and `codeindex/memory_service.py`.
- Use `from __future__ import annotations` consistently (present in core modules such as `codeindex/storage.py`, `codeindex/search.py`, `codeindex/config.py`).
- Prefer small helper functions for repeated logic, e.g. `_start_memory_context` and `_finish_memory_context` in `codeindex/cli.py`.
- Keep JSON output machine-readable via explicit payload dicts and one print boundary (`_json_print` in `codeindex/cli.py`).
- Keep module-level constants uppercase and explicit (`DEFAULT_CONFIG` in `codeindex/config.py`, `MODE_TO_KINDS` in `codeindex/search.py`, `TEXT_EXTS` in `codeindex/indexer.py`).

## Naming
- Functions and variables: `snake_case` (`sync_workspace`, `extract_python_symbols`, `validate_mode`).
- Dataclasses: `PascalCase` nouns for structured records (`SyncStats`, `ChunkRecord`, `MemoryContext`, `SearchResult`).
- Internal-only helpers: leading underscore (`_analysis_payload`, `_memory_cfg`, `_deep_merge`).
- CLI subcommands map 1:1 to `cmd_*` handlers in `codeindex/cli.py`.
- Query/analyze "kind" strings are normalized as lower-case enums (`chunks|symbols|hybrid`, `ast|validate|...`) in `codeindex/search.py`, `codeindex/cli.py`, and `codeindex/server.py`.

## Design Patterns
- Layered architecture:
- IO surfaces in `codeindex/cli.py` and `codeindex/server.py`.
- Domain logic in `codeindex/search.py`, `codeindex/indexer.py`, `codeindex/analysis.py`, `codeindex/memory_service.py`.
- Persistence in `codeindex/storage.py` and `codeindex/memory_storage.py`.
- Resource lifecycle uses context managers for DB safety (`with Storage(...) as storage:` in CLI/server).
- Capability fallback pattern is explicit:
- Optional imports guarded with `try/except` in `codeindex/storage.py`, `codeindex/analysis.py`, `codeindex/config.py`.
- Runtime fallback order is deterministic (`sqlite-vec` -> `sqlite-vss` -> `python-cosine`) in `codeindex/storage.py`.
- Response shaping is consistent: user-facing payloads include explicit `metrics`, `results`, and optional `memory` blocks in `codeindex/cli.py` and `codeindex/server.py`.

## Error Handling
- Validate early and fail with typed exceptions (`ValueError`, `KeyError`, `RuntimeError`) in `codeindex/config.py`, `codeindex/search.py`, `codeindex/server.py`.
- Boundary layers translate exceptions to user-safe outputs:
- CLI: `main()` catches `(RuntimeError, ValueError)` and returns exit code `1` in `codeindex/cli.py`.
- HTTP: `do_GET` returns 400 for `ValueError`; JSON-RPC maps errors to protocol codes in `codeindex/server.py`.
- Keep defensive `except Exception` only for optional capability detection or guarded shutdown paths (see comments in `codeindex/storage.py`, `codeindex/analysis.py`, `codeindex/server.py`).
- Config validation should include precise key paths in error text (pattern used heavily in `codeindex/config.py` and `codeindex/memory_config.py`).

## Logging and Observability
- Traditional `logging` module is currently not used; CLI-visible output is via `print(...)` in `codeindex/cli.py`.
- Structured observability is implemented through persistent memory events rather than log sinks:
- Session/event capture in `codeindex/memory_service.py` (`start_session`, `capture_event`, `run_worker_once`, `end_session`).
- Stream/view surfaces in `codeindex/server.py` (`/memory/stream`, `/memory/viewer`).
- Conventions for new diagnostics:
- Prefer adding structured fields to event metadata in `codeindex/memory_service.py` call sites.
- Keep stdout focused on command results and operator messages (e.g. watch mode notices in `codeindex/cli.py`).

## Practical Example
- Good pattern: validate inputs at boundary (`codeindex/server.py` checks required query params) and return normalized payload.
- Good pattern: keep ranking logic pure and side-effect free (`search_index` in `codeindex/search.py`), then add transport-specific wrapping in CLI/server.
