# Codebase Conventions

## Scope

This repository is a small Python CLI and HTTP service package centered on `codeindex/` with tests in `tests/`. The dominant conventions are simple stdlib-first implementation, typed public functions, dataclass-based value objects, and JSON-oriented CLI/API outputs.

## Style

- Files in `codeindex/` use `from __future__ import annotations` consistently.
- Imports are grouped as: stdlib first, then local package imports. This pattern appears in `codeindex/cli.py`, `codeindex/config.py`, `codeindex/server.py`, `codeindex/storage.py`, `codeindex/indexer.py`, `codeindex/search.py`, and `codeindex/embedding.py`.
- Functions are short and procedural. Most modules keep logic at module scope rather than introducing extra classes.
- Type hints are used broadly on public functions and dataclass fields. Examples: `codeindex/cli.py`, `codeindex/config.py`, `codeindex/search.py`, and `codeindex/storage.py`.
- Dataclasses are the primary structured-data pattern for in-memory models: `LoadedConfig` in `codeindex/config.py`, `ChunkRecord` in `codeindex/storage.py`, `SyncStats` in `codeindex/indexer.py`, and `SearchResult` in `codeindex/search.py`.
- Comments are sparse and usually reserved for clarifying non-obvious behavior, such as the YAML fallback comment in `codeindex/config.py`.
- String formatting uses f-strings throughout.

## Naming

- Module names are lowercase nouns or verbs: `config.py`, `storage.py`, `search.py`, `indexer.py`, `embedding.py`, `server.py`, `cli.py`.
- Public function names are snake_case and descriptive: `load_config`, `save_config`, `search_index`, `sync_workspace`, `chunk_text`.
- Internal helpers are marked with a leading underscore: `_run_sync_once`, `_deep_merge`, `_default_config_copy`, `_parse_scalar`, `_parse_simple_yaml`, `_to_simple_yaml`, `_build_record`, `_migrate_schema`.
- Constants are uppercase: `DEFAULT_CONFIG`, `SCHEMA`, `TEXT_EXTS`, `SYMBOL_PATTERNS`, `MODE_TO_KINDS`, `TOKEN_RE`.
- CLI command handlers follow the `cmd_<subcommand>` pattern in `codeindex/cli.py`: `cmd_init`, `cmd_config`, `cmd_sync`, `cmd_query`, `cmd_status`, `cmd_serve`.
- Tests follow `test_<behavior>` naming in `tests/test_cli.py` and `tests/test_server.py`.

## Module Patterns

- `codeindex/cli.py` is the orchestration layer. It parses args, loads config, instantiates `Storage`, calls core functions, prints JSON or human-readable status, and returns integer exit codes.
- `codeindex/config.py` owns config defaults, load/save behavior, and dotted-path mutation. It also contains a fallback YAML parser/writer when `yaml` is unavailable.
- `codeindex/storage.py` is the persistence boundary. It encapsulates SQLite schema creation, lightweight migrations, CRUD helpers, counts, and transaction commits.
- `codeindex/indexer.py` handles filesystem traversal, exclusion filtering, chunking, symbol extraction, hashing, and incremental sync bookkeeping.
- `codeindex/search.py` is a pure scoring layer over stored chunks. It resolves workspace scope, computes scores, and derives retrieval metrics.
- `codeindex/server.py` is intentionally thin. It adapts query parameters from `BaseHTTPRequestHandler` to `search_index`.
- `codeindex/embedding.py` is a pure utility module with deterministic local embedding and chunking helpers.

## Error Handling

- CLI-facing validation typically returns status code `1` and prints a plain message instead of raising custom exceptions. Examples: `cmd_init` and `cmd_query` in `codeindex/cli.py`.
- HTTP validation uses `self.send_error(...)` with `400` or `404` in `codeindex/server.py`.
- Lower-level utility functions raise `ValueError` on invalid input, for example `chunk_text` in `codeindex/embedding.py` and `cosine_similarity` in `codeindex/embedding.py`.
- Syntax failures while extracting Python symbols are treated as non-fatal and collapse to an empty list in `extract_python_symbols` in `codeindex/indexer.py`.
- Config loading tolerates absent files by returning defaults in `load_config` in `codeindex/config.py`.
- Optional dependency handling is permissive: `codeindex/config.py` catches any exception while importing `yaml` and falls back to a minimal internal parser.

## CLI And API Conventions

- CLI entrypoint is the `codeindex` console script defined in `pyproject.toml` and implemented by `codeindex.cli:main`.
- CLI subcommands are noun/verb oriented: `init`, `config`, `sync`, `query`, `status`, `serve`.
- Machine-readable output is preferred for steady-state commands. `sync`, `query`, and `status` print JSON payloads from `codeindex/cli.py`.
- Human-readable output is still used for lifecycle/status lines such as initialization, config mutation, and watch/server startup in `codeindex/cli.py`.
- The HTTP API exposes a single GET endpoint, `/search`, in `codeindex/server.py`.
- API responses mirror CLI query payload shape: `query`, `workspace`, `metrics`, and `results`.
- Boolean query parameters are passed as lowercase strings and normalized manually in `codeindex/server.py`.
- Search modes are constrained to `"chunks"`, `"symbols"`, or `"hybrid"` in both CLI argument parsing and server validation.

## Consistency Issues

- Scalar parsing is duplicated. `parse_value` in `codeindex/cli.py` and `_parse_scalar` in `codeindex/config.py` do nearly the same job, but only `parse_value` lowercases booleans first.
- Resource cleanup is inconsistent. `cmd_query` and `cmd_status` close `Storage` after successful work, but do not use `try/finally`, so unexpected exceptions can leak the connection. `cmd_serve` intentionally keeps the DB open for server lifetime.
- Output format is mixed. Some commands print plain text (`init`, `config`, watch status, serve startup) while others print JSON. That is workable, but not uniformly automation-friendly.
- Test helpers are duplicated instead of shared. `run_cmd` appears in both `tests/test_cli.py` and `tests/test_server.py`.
- The repository is typed but does not show formatter, linter, or type-checker configuration in `pyproject.toml`. Conventions are implicit rather than enforced by tooling.
- `codeindex/server.py` uses the `BaseHTTPRequestHandler` method name `do_GET` and suppresses naming lint with `# noqa: N802`; this is correct for the framework but breaks the otherwise consistent snake_case naming style.
- `codeindex/config.py` catches broad `Exception` during YAML import. It supports the fallback story, but it also hides unexpected import-time failures.

## Practical Takeaways

- New code should stay stdlib-first, typed, and procedural unless complexity clearly justifies extra abstraction.
- Data passed across module boundaries should continue to use dataclasses or plain dict payloads rather than ad hoc tuples where possible.
- CLI additions should preserve the current pattern: parser setup in `build_parser`, work in `cmd_<name>`, integer return code, and JSON output when results are intended for automation.
- If the project grows, the first consistency wins would be centralizing scalar parsing, introducing shared test helpers, and adding explicit lint/format/type tooling to `pyproject.toml`.
