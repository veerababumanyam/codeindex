# Technology Stack

## Overview
- Repository type: local-first Python application packaged as a CLI with an optional HTTP search server.
- Primary package: `codeindex/`
- Entry point: `codeindex` console script from `pyproject.toml`
- Tests: `tests/`

## Languages
- Python 3.10+ is the only implemented language runtime requirement in `pyproject.toml`.
- YAML is used for user configuration files such as `codeindex.yaml` and the sample at `docs/codeindex.example.yaml`.
- SQL is embedded as SQLite schema strings in `codeindex/storage.py`.

## Runtime And Execution Model
- CLI runtime is pure Python via `argparse` in `codeindex/cli.py`.
- HTTP serving uses the Python standard library `http.server.ThreadingHTTPServer` in `codeindex/server.py`.
- Persistent local storage uses `sqlite3` with a file database at `.codeindex/index.db`, created by `codeindex/storage.py`.
- File indexing walks local directories with `pathlib.Path.rglob()` in `codeindex/indexer.py`.
- Search and embedding are in-process and synchronous; there is no job queue, background worker, or async framework.

## Frameworks And Libraries
- Packaging backend: `setuptools.build_meta` from `pyproject.toml`.
- Test runner: `pytest` configured in `pyproject.toml`.
- Standard library modules provide most functionality: `argparse`, `json`, `sqlite3`, `http.server`, `urllib.parse`, `pathlib`, `ast`, `fnmatch`, `hashlib`, `re`, and `time`.
- Optional dependency: `PyYAML` if importable as `yaml` in `codeindex/config.py`.
- Fallback behavior: if `yaml` is unavailable, config parsing/writing falls back to a minimal in-repo YAML implementation in `codeindex/config.py`.

## Dependency Footprint
- Declared build dependency: `setuptools>=68` in `pyproject.toml`.
- No runtime dependencies are declared under `[project.dependencies]` in `pyproject.toml`.
- The repository intentionally runs without network-backed embedding or retrieval dependencies; embeddings are local hashed token vectors in `codeindex/embedding.py`.

## Packaging And Distribution
- Package name: `codeindex-sync` in `pyproject.toml`.
- Version source is duplicated as `0.1.0` in both `pyproject.toml` and `codeindex/__init__.py`.
- Console command: `codeindex = "codeindex.cli:main"` in `pyproject.toml`.
- The codebase is laid out as a single import package under `codeindex/` rather than a `src/` layout.

## Configuration Model
- Default configuration is defined in `codeindex/config.py` as `DEFAULT_CONFIG`.
- Runtime config file path defaults to `codeindex.yaml` and can be overridden with `--config` in `codeindex/cli.py`.
- Implemented config areas:
  - `workspace`
  - `paths.project_root`
  - `paths.global_docs`
  - `indexing.chunk_size`
  - `indexing.chunk_overlap`
  - `indexing.max_response_tokens`
  - `watch.enabled`
  - `watch.debounce_ms`
  - `excludes`
  - `query.top_k`
  - `query.include_global_docs`
  - `query.require_workspace`
  - `query.mode`
- Example-only config drift: `docs/codeindex.example.yaml` includes `llm.*`, `indexing.enable_ast_summaries`, and `indexing.compression_target_ratio`, but those keys are not used by the implemented Python modules.

## Key File Paths
- `pyproject.toml`: package metadata, Python requirement, console script, pytest config.
- `README.md`: product intent, commands, and storage model summary.
- `codeindex/cli.py`: command parsing and orchestration for `init`, `config`, `sync`, `query`, `status`, and `serve`.
- `codeindex/config.py`: config defaults, YAML load/save, dotted-key updates.
- `codeindex/indexer.py`: filesystem scan, chunking, symbol extraction, sync logic.
- `codeindex/embedding.py`: deterministic local embedding and cosine similarity.
- `codeindex/search.py`: workspace resolution, scoring, and retrieval metrics.
- `codeindex/storage.py`: SQLite schema, migrations, and persistence API.
- `codeindex/server.py`: HTTP `/search` endpoint.
- `docs/codeindex.example.yaml`: sample config with aspirational fields beyond current implementation.
- `tests/test_cli.py`: CLI integration tests over init/sync/query/status/global-docs/symbol-mode.
- `tests/test_server.py`: HTTP server integration test for `/search`.

## Notable Technical Characteristics
- Local-first by design: indexing, embeddings, search, and storage all run on the local machine.
- No typed validation framework such as `pydantic`, `dataclasses-json`, or `marshmallow`; config is plain nested dictionaries.
- No web framework such as FastAPI, Flask, or Django; the server surface is a minimal stdlib HTTP handler.
- No ORM or migration framework; schema management is hand-written SQL plus lightweight runtime column checks in `codeindex/storage.py`.
