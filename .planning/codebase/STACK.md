# Technology Stack Map

## Languages and Runtime
- Primary language: Python 3.10+ (`pyproject.toml`, `codeindex/*.py`).
- Runtime model: local CLI + local HTTP server (`codeindex/cli.py`, `codeindex/server.py`).
- Targeted source-language analysis coverage includes `.py`, `.js/.jsx`, `.ts/.tsx`, `.go`, `.rs`, `.java`, `.c/.cpp` (`codeindex/analysis.py`, `codeindex/indexer.py`).

## Packaging and Build System
- Build backend: setuptools (`pyproject.toml` `[build-system]`).
- Package metadata entrypoint: `codeindex-sync` (`pyproject.toml` `[project]`).
- Console script: `codeindex` mapped to `codeindex.cli:main` (`pyproject.toml` `[project.scripts]`).
- Editable install workflow documented in `README.md` (`pip install -e .`).

## Core Frameworks and Standard Libraries
- CLI framework: stdlib `argparse` (`codeindex/cli.py`).
- HTTP framework: stdlib `http.server` with `ThreadingHTTPServer` (`codeindex/server.py`).
- Data storage layer: stdlib `sqlite3` with custom schema + migrations (`codeindex/storage.py`, `codeindex/memory_storage.py`).
- JSON-RPC handling: custom implementation over `POST /mcp` (`codeindex/server.py`).

## Dependencies
- Required runtime deps (`pyproject.toml`):
- `PyYAML>=6.0` for config load/save (`codeindex/config.py`).
- `sqlite-vec>=0.1.6` optional-preferred vector extension (`codeindex/storage.py`).
- `sqlite-vss>=0.1.2` optional fallback vector extension (`codeindex/storage.py`).
- Optional extra `analysis`: `tree-sitter-languages>=1.10.2` (`pyproject.toml`, `codeindex/analysis.py`).
- No network SDK dependency for embeddings; embeddings are deterministic/local (`codeindex/embedding.py`).

## Configuration Surface
- Primary config file: `codeindex.yaml` (sample: `docs/codeindex.example.yaml`).
- Config schema and validation live in `codeindex/config.py` and `codeindex/memory_config.py`.
- Key groups: `workspace`, `paths`, `indexing`, `watch`, `excludes`, `query`, `analysis`, `memory` (`codeindex/config.py`).
- Default DB path is generated as `.codeindex/index.db` relative to config directory (`codeindex/cli.py`).

## Data and Indexing Internals
- Core relational tables: `files`, `chunks` (`codeindex/storage.py`).
- Memory subsystem tables + FTS5 table: `memory_*`, `memory_observation_fts` (`codeindex/memory_storage.py`).
- Vector backend selection order: `sqlite-vec` -> `sqlite-vss` -> python cosine fallback (`codeindex/storage.py`).

## Interfaces and Tooling
- CLI commands: `init`, `config`, `sync`, `query`, `status`, `serve`, `analyze`, `memory ...` (`codeindex/cli.py`).
- HTTP endpoints: `/search`, `/analysis/*`, `/memory/*` (`codeindex/server.py`, `README.md`).
- MCP JSON-RPC endpoint: `/mcp` with tool discovery and tool calls (`codeindex/server.py`).

## Testing and Dev Tooling
- Test runner config: `pytest` (`pyproject.toml` `[tool.pytest.ini_options]`).
- Test coverage files: `tests/test_cli.py`, `tests/test_server.py`.
- Concurrency behavior in server tests uses multiple requests and thread pool (`tests/test_server.py`).

## Practical Example
- Initialize project config: `codeindex init --path /myproject --workspace myapp` (`README.md`, `codeindex/cli.py`).
- Build local index: `CodeIndex`.
- Start service: `codeindex serve --host 127.0.0.1 --port 9090`.
