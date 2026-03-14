# Architecture Map

## Pattern
- The project follows a modular monolith pattern centered on a shared SQLite persistence layer.
- Interfaces (CLI, HTTP, MCP) are thin adapters over the same service functions.
- Most business logic sits in plain modules under `codeindex/` rather than framework-specific classes.

## Runtime Layers
- Interface layer: `codeindex/cli.py` (argparse commands) and `codeindex/server.py` (`BaseHTTPRequestHandler` routes).
- Application/service layer: `codeindex/indexer.py`, `codeindex/search.py`, `codeindex/analysis.py`, `codeindex/memory_service.py`.
- Domain model layer: dataclasses in `codeindex/storage.py` (`ChunkRecord`) and `codeindex/memory_models.py`.
- Infrastructure layer: `codeindex/storage.py` + `codeindex/memory_storage.py` (SQLite schema, queries, queue tables, FTS).

## Core Abstractions
- `Storage` in `codeindex/storage.py` is the primary abstraction for index persistence and vector/backend fallback.
- `MemoryStorage` in `codeindex/memory_storage.py` isolates memory-specific tables and operations.
- `MemoryService` in `codeindex/memory_service.py` orchestrates session lifecycle, capture, injection, and worker processing.
- `search_index(...)` in `codeindex/search.py` is the canonical retrieval pipeline used by CLI and HTTP/MCP surfaces.
- `sync_workspace(...)` in `codeindex/indexer.py` is the canonical indexing pipeline.

## Entry Points
- Package CLI entry point is defined in `pyproject.toml` as `codeindex = "codeindex.cli:main"`.
- Direct CLI execution path: `python -m codeindex.cli` (tests use this path in `tests/test_cli.py`).
- Server startup command path: `codeindex serve` -> `cmd_serve` in `codeindex/cli.py` -> `serve(...)` in `codeindex/server.py`.
- MCP entry path is HTTP `POST /mcp` handled in `SearchHandler.do_POST` in `codeindex/server.py`.

## Data Flow: Index + Query
1. `CodeIndex` calls `cmd_sync` in `codeindex/cli.py`.
2. `cmd_sync` calls `_run_sync_once`, then `sync_workspace(...)` in `codeindex/indexer.py`.
3. `sync_workspace` scans files, chunks text via `chunk_text` in `codeindex/embedding.py`, generates embeddings via `embed_text`, extracts symbols, and writes through `Storage.replace_chunks`.
4. `Storage` persists rows in `files`/`chunks` tables and optional vector virtual tables in `codeindex/storage.py`.
5. `codeindex query` and `/search` call `search_index(...)` in `codeindex/search.py`.
6. Retrieval uses vector backend when available (`sqlite-vec`/`sqlite-vss`), else `_fallback_scan_top_k` cosine scan over streamed chunks.
7. Result payloads include snippet metadata and token-savings metrics before returning at interface layer.

## Data Flow: Memory
1. Interface code creates `MemoryService` via `_memory_service` in `codeindex/cli.py` or directly in `codeindex/server.py`.
2. A `MemoryContext` session is started (`start_session`) per command/request.
3. Events are captured through `capture_event`, converted with `build_raw_observation` in `codeindex/memory_capture.py`, queued in `memory_queue`.
4. `run_worker_once` calls `process_pending_observations` in `codeindex/memory_worker.py` to finalize summaries/citations.
5. Retrieval uses `compute_injection` (`codeindex/memory_injection.py`) and `search_memory` (`codeindex/memory_search.py`).

## Cross-Cutting Concerns
- Configuration is centralized in `codeindex/config.py` with deep merge + validation against `DEFAULT_CONFIG`.
- Optional capabilities are runtime-probed: YAML availability in `codeindex/config.py`, vector extensions in `codeindex/storage.py`, FTS5 in `codeindex/memory_storage.py`.
- Workspace isolation is enforced in both index search (`resolve_workspaces` in `codeindex/search.py`) and memory queries (`workspace`-scoped SQL in `codeindex/memory_storage.py`).

## Extension Seams
- Add new analysis operations by extending `codeindex/analysis.py` and wiring it in both `codeindex/cli.py` and `codeindex/server.py`.
- Add new MCP tools by extending `SearchHandler.MCP_TOOLS` and `do_POST` dispatch in `codeindex/server.py`.
- Swap or improve embedding behavior in `codeindex/embedding.py` without changing callers.
