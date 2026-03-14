# Structure

## Directory Layout

The repository is compact and organized around one Python package plus tests and docs.

- `codeindex/`: application package. All runtime logic lives here.
- `tests/`: pytest-based end-to-end coverage for CLI and HTTP behavior.
- `docs/`: sample configuration material, currently `docs/codeindex.example.yaml`.
- `.planning/codebase/`: generated repository mapping documents.
- `.codex/`: local workflow skills and automation metadata, not part of the shipped package.

Generated cache directories also appear during local runs:

- `codeindex/__pycache__/`
- `tests/__pycache__/`

These are runtime artifacts and should not drive architectural decisions.

## Package Layout

### `codeindex/`

Key files in descending size and architectural weight:

- `codeindex/cli.py` (204 lines): composition root, command surface, JSON response formatting, watch loop, and server startup.
- `codeindex/indexer.py` (196 lines): indexing workflow, file filtering, chunking, symbol extraction, and incremental sync logic.
- `codeindex/storage.py` (163 lines): SQLite schema, migrations, and persistence API.
- `codeindex/config.py` (149 lines): defaults, YAML load/save, fallback parser, and config mutation helpers.
- `codeindex/server.py` (77 lines): HTTP transport for `/search`.
- `codeindex/search.py` (67 lines): ranking pipeline and search metrics.
- `codeindex/embedding.py` (55 lines): tokenization, local embedding, similarity, and chunk splitting.
- `codeindex/__init__.py` (4 lines): package version export.

This layout shows one package with functional modules rather than subpackages. For the current size, that keeps navigation simple.

### `tests/`

- `tests/test_cli.py` (145 lines): subprocess-driven CLI workflow tests.
- `tests/test_server.py` (46 lines): subprocess + HTTP endpoint verification.

Tests mirror the public interfaces instead of the internal module layout.

### `docs/`

- `docs/codeindex.example.yaml` (36 lines): example config shape used as documentation, not as executable config in tests.

## Key Files And Their Roles

- `pyproject.toml`: package metadata, Python version floor, pytest config, and the `codeindex` console script.
- `README.md`: top-level product description, quickstart commands, and a high-level summary of storage and query behavior.
- `.gitignore`: minimal ignore list for repo hygiene.

The runtime assumes a user-managed config file, usually `codeindex.yaml`, and a generated SQLite store at ``.codeindex/index.db`` relative to the config directory. Those files are external to the tracked source layout but central to execution.

## Ownership Hotspots

Based on current file size and git churn, the main hotspots are:

- `codeindex/cli.py`: highest churn (`206`) and largest source file. It owns command UX plus orchestration, so feature work often lands here first.
- `codeindex/config.py`: high churn (`149`) because config shape affects nearly every command.
- `codeindex/storage.py`: high churn (`122`) because schema and query shape are foundational.
- `codeindex/indexer.py`: high logical complexity even with lower churn (`91`), since it crosses file system, parsing, embedding, and storage concerns.

Current git history indicates a single visible author, `Veera <veerababumanyam@gmail.com>`, so practical ownership is centralized rather than split by subsystem.

## Naming And Layout Conventions

The repository follows a few clear conventions:

- Flat package modules under `codeindex/` are named by responsibility: `cli`, `config`, `embedding`, `indexer`, `search`, `server`, `storage`.
- Public behavior is exposed through verb-oriented functions such as `sync_workspace`, `search_index`, `load_config`, and `serve`.
- Internal helpers are prefixed with `_`, for example `_run_sync_once`, `_build_record`, `_deep_merge`, and `_parse_simple_yaml`.
- Lightweight data carriers use `@dataclass`, for example `LoadedConfig`, `SyncStats`, `ChunkRecord`, and `SearchResult`.
- Tests use `test_<surface>.py` naming and exercise behavior through actual subprocess invocations instead of importing command handlers directly.

The codebase consistently uses standard-library-first dependencies. There is no framework-specific directory nesting, service layer package, or adapters folder.

## Structural Strengths

- The top-level layout is easy to scan because there is a single runtime package and two support directories.
- Module names closely match runtime responsibilities, which reduces discovery cost.
- Tests are colocated in one directory and validate the same entry points users interact with.

## Structural Weak Points

- `codeindex/cli.py` is accumulating multiple responsibilities: parser construction, config bootstrapping, workflow coordination, output shaping, and watch-loop control.
- `codeindex/indexer.py` is dense enough that future language support or richer parsing may justify splitting symbol extraction from sync orchestration.
- `docs/codeindex.example.yaml` documents options not implemented in `codeindex/config.py` consumers, so documentation structure is ahead of actual runtime structure.
- There is no dedicated separation between domain models and persistence DTOs; `ChunkRecord` serves both purposes from `codeindex/storage.py`.

## Suggested Navigation Order

For new contributors, the most efficient reading order is:

1. `README.md`
2. `pyproject.toml`
3. `codeindex/cli.py`
4. `codeindex/indexer.py`
5. `codeindex/storage.py`
6. `codeindex/search.py`
7. `tests/test_cli.py`
8. `tests/test_server.py`

That sequence follows the repository from public surface to internals to behavioral verification.
