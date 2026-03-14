# Architecture

## System Pattern

This repository is a small local-first Python application built as a layered monolith. The runtime is split into thin interfaces in `codeindex/cli.py` and `codeindex/server.py`, with shared domain logic in `codeindex/indexer.py`, `codeindex/search.py`, `codeindex/embedding.py`, `codeindex/config.py`, and `codeindex/storage.py`.

The dominant pattern is:

1. Load configuration from `codeindex.yaml` through `codeindex/config.py`.
2. Open a SQLite-backed repository via `codeindex/storage.py`.
3. Run an indexing or search workflow through `codeindex/indexer.py` or `codeindex/search.py`.
4. Return JSON through either the CLI in `codeindex/cli.py` or the HTTP endpoint in `codeindex/server.py`.

There is no dependency injection framework, service container, or plugin system. Composition is direct and explicit at call sites, mostly in `codeindex/cli.py`.

## Module Boundaries

### Interface Layer

- `codeindex/cli.py`: primary entry point for operators. Owns argument parsing, command routing, config bootstrap, and JSON/stdout responses.
- `codeindex/server.py`: secondary entry point for machine consumers. Exposes a single `GET /search` endpoint backed by the same search path as the CLI.

These files should stay thin. They currently construct `Storage` directly and call into lower-level modules without additional adapters.

### Application / Workflow Layer

- `codeindex/indexer.py`: orchestrates repository scanning, incremental change detection, chunk generation, symbol extraction, embedding generation, and persistence.
- `codeindex/search.py`: orchestrates workspace resolution, scoring, ranking, and result metrics.

This layer contains the use-case logic. It coordinates lower-level helpers but does not own process startup or transport-specific concerns.

### Domain Utility Layer

- `codeindex/embedding.py`: deterministic local tokenization, vector generation, cosine similarity, and chunk windowing.
- `codeindex/config.py`: default config schema, YAML parsing fallback, deep merge behavior, and dotted-key mutation.

These modules are stateless helper libraries. Their functions are reused across indexing and query flows.

### Persistence Layer

- `codeindex/storage.py`: SQLite schema definition, schema migration, CRUD methods for `files` and `chunks`, and aggregate counters.

`Storage` is the only persistence abstraction. Other modules do not execute SQL directly.

## Core Data Model

Two persisted entities define the indexing model:

- `files` table in `codeindex/storage.py`: tracks `(workspace, path)` plus `content_hash` and `mtime` for incremental sync.
- `chunks` table in `codeindex/storage.py`: stores chunk or symbol payloads, line ranges, token counts, and serialized embedding vectors.

In-memory transfer objects are also simple:

- `ChunkRecord` in `codeindex/storage.py`: canonical record shape exchanged between index/search/storage code.
- `SyncStats` in `codeindex/indexer.py`: reports scan/index/delete counters.
- `SearchResult` in `codeindex/search.py`: couples a score with a `ChunkRecord`.
- `LoadedConfig` in `codeindex/config.py`: binds a path to merged config data.

## Entry Points

### CLI

`codeindex/cli.py:main()` builds an `argparse` parser and dispatches subcommands:

- `init`: writes a config file and creates `.codeindex/index.db`.
- `config`: mutates config keys using dotted paths.
- `sync`: runs one indexing pass, optionally polling forever in watch mode.
- `query`: returns ranked results as JSON.
- `status`: reports file/chunk/symbol/workspace counts.
- `serve`: starts the HTTP server.

The package entry point is also registered in `pyproject.toml` as `codeindex = "codeindex.cli:main"`.

### HTTP

`codeindex/server.py:serve()` wraps `ThreadingHTTPServer` with `SearchHandler`. The handler validates query parameters, calls `search_index(...)`, and emits a JSON payload with the same result shape used by the CLI.

## Data Flow

### Indexing Flow

1. `codeindex/cli.py:_run_sync_once()` loads config and resolves workspace, paths, excludes, and chunk settings.
2. It opens `Storage(db_path(...))` from `codeindex/storage.py`.
3. `codeindex/indexer.py:sync_workspace()` walks `root.rglob("*")`, filters by extension and glob excludes, and reads file contents.
4. Content hashes are checked through `Storage.file_hash(...)` to skip unchanged files.
5. `codeindex/embedding.py:chunk_text()` splits large files into overlapping text windows.
6. `codeindex/indexer.py:extract_symbols()` derives symbol snippets using Python AST parsing or regex patterns for other languages.
7. `codeindex/indexer.py:_build_record()` computes token estimates and embeddings via `embed_text(...)`.
8. `Storage.upsert_file(...)` and `Storage.replace_chunks(...)` persist the new state.
9. `Storage.delete_missing_files(...)` removes rows for paths no longer present.

The optional global-doc indexing path is not a separate subsystem; `codeindex/cli.py:_run_sync_once()` simply reuses `sync_workspace(...)` with the reserved workspace name ``global``.

### Query Flow

1. `codeindex/cli.py:cmd_query()` or `codeindex/server.py:SearchHandler.do_GET()` gathers query parameters.
2. Both create or reuse `Storage` and call `codeindex/search.py:search_index(...)`.
3. `search_index(...)` resolves candidate workspaces using `resolve_workspaces(...)`.
4. It embeds the query with `embed_text(...)`.
5. It loads candidate records through `Storage.all_chunks(...)`.
6. It computes cosine similarity, then applies symbol bonuses for `symbol` records and query/symbol-name term overlap.
7. It sorts results, trims to `top_k`, and computes token-savings metrics using `Storage.workspace_token_count(...)`.
8. The caller serializes `ChunkRecord` fields into JSON.

## Important Abstractions

### `Storage`

`Storage` in `codeindex/storage.py` is the architectural anchor. It hides schema setup, incremental metadata lookup, chunk replacement, deletion of missing files, and query-time record hydration. Both indexing and search are tightly coupled to this API.

### Workspace Isolation

Workspace names are plain strings propagated through all layers. Isolation is enforced by SQL filtering in `Storage` and by `resolve_workspaces(...)` in `codeindex/search.py`. The reserved ``global`` workspace is a convention, not a separate schema.

### Chunk vs Symbol Dual Index

The search model depends on two record kinds stored in the same `chunks` table:

- `chunk`: broader retrieval context from sliding windows.
- `symbol`: smaller, high-precision snippets extracted from AST or regex heuristics.

`codeindex/search.py` uses `MODE_TO_KINDS` to switch between `chunks`, `symbols`, and `hybrid` retrieval without changing the storage model.

### Deterministic Local Embeddings

`codeindex/embedding.py` deliberately avoids external model calls. Embeddings are hashed token-frequency vectors, which keeps the system offline and reproducible but also means retrieval quality depends heavily on token overlap rather than richer semantics.

## Boundary Tensions And Architectural Risks

- `codeindex/cli.py` is the composition root and the largest file at 204 lines, so transport concerns and workflow orchestration are starting to mix there.
- `codeindex/indexer.py` combines file-system traversal, content chunking, symbol extraction, embedding, and persistence. That makes it the main change hotspot for indexing behavior.
- `codeindex/server.py` keeps a shared `Storage` instance on the handler class. That is simple, but concurrency semantics depend on SQLite behavior and `check_same_thread=False`.
- `docs/codeindex.example.yaml` contains fields such as `llm` and `enable_ast_summaries` that are not consumed by the current implementation, so the documented architecture is broader than the shipped one.

## Test Coverage Shape

Architecture is verified mostly through end-to-end tests:

- `tests/test_cli.py` covers `init`, `sync`, `query`, `status`, global-doc inclusion, and symbol mode.
- `tests/test_server.py` covers the HTTP search endpoint through a spawned subprocess.

There are no unit tests per module, so integration behavior is covered better than internal edge cases.
