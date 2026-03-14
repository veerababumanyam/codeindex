# Testing Guide

## Frameworks and Tooling
- Test runner is `pytest` (configured in `pyproject.toml` under `[tool.pytest.ini_options]` with `testpaths = ["tests"]`).
- Tests use Python stdlib helpers for integration behavior:
- `subprocess` for CLI process invocation in `tests/test_cli.py`.
- `urllib.request` for HTTP and JSON-RPC calls in `tests/test_server.py`.
- `concurrent.futures.ThreadPoolExecutor` for basic concurrency checks in `tests/test_server.py`.
- Target executable path is `python -m codeindex.cli` to validate real CLI wiring, not function-level mocks.

## Test Structure
- Test files are grouped by surface:
- `tests/test_cli.py` validates end-to-end CLI flows (`init`, `sync`, `query`, `status`, `analyze`, `memory ...`).
- `tests/test_server.py` validates HTTP `/search`, `/analysis/*`, `/memory/*`, and MCP `POST /mcp` behaviors.
- Typical test lifecycle pattern:
- Create isolated temp workspace with `tmp_path`.
- Write minimal fixture files into that temp project.
- Run `init` + `sync` via subprocess.
- Assert JSON payload shape and key invariants (counts, mode, backends, required fields).
- For server tests: spawn CLI `serve` in a subprocess, sleep briefly, hit endpoints, then terminate process in `finally`.

## Mocking and Isolation Strategy
- Primary strategy is "real process, temp filesystem" instead of deep mocking.
- Explicit monkeypatching is used only where external capability should be simulated:
- `tests/test_cli.py::test_load_config_requires_pyyaml_when_config_exists` monkeypatches `codeindex.config.yaml` and `YAML_IMPORT_ERROR`.
- Network is local-only (`127.0.0.1`), and persistent state is isolated to per-test temp configs/databases.
- No heavy service mocks for storage/vector backends; tests accept backend variability by asserting membership in `{sqlite-vec, sqlite-vss, python-cosine}`.

## Assertion Patterns
- Prefer behavior/assertion over internal implementation checks.
- Representative assertions:
- Query includes ranked `results` and `metrics` (`tests/test_cli.py`, `tests/test_server.py`).
- Symbol mode emits symbol hits (`tests/test_cli.py::test_symbol_mode_prefers_indexed_symbols`).
- Incremental sync handles deletes and binary-like files (`tests/test_cli.py`).
- MCP returns tool list and tool-call payload text (`tests/test_server.py::test_mcp_jsonrpc_tools_list_and_call`).
- Memory endpoints return session/observation/citation data (`tests/test_cli.py`, `tests/test_server.py`).

## Coverage Signals
- Strong integration coverage for transport layers:
- CLI command matrix and happy-path JSON outputs in `tests/test_cli.py`.
- HTTP + MCP protocol-level behavior in `tests/test_server.py`.
- Important resilience signals covered:
- malformed config handling,
- invalid query mode handling,
- concurrent request handling,
- memory workflow round-trip (status/search/expand/session/viewer/stream).

## Gaps and Risk Areas
- Limited direct unit coverage for core algorithm internals:
- ranking/scoring branches in `codeindex/search.py` (symbol overlap boosts, fallback scan behavior),
- chunk/symbol extraction edge cases in `codeindex/indexer.py` (regex patterns across languages),
- AST/dependency/complexity branch matrix in `codeindex/analysis.py`.
- Failure-path coverage is partial for server internals:
- not many explicit tests for invalid MCP argument shapes and non-JSON request bodies in `codeindex/server.py`.
- Memory worker behavior (`codeindex/memory_worker.py`) and retry/error accounting appears lightly exercised indirectly, not directly asserted.
- No explicit coverage threshold enforcement is present in `pyproject.toml` (no `--cov`/fail-under policy).

## Practical Additions (High Value)
- Add focused unit tests for `codeindex/search.py::search_index` and `_fallback_scan_top_k` using deterministic chunk fixtures.
- Add table-driven tests for `codeindex/indexer.py::extract_regex_symbols` and `extract_symbols` per suffix.
- Add negative protocol tests for `codeindex/server.py` (`/mcp` invalid params, unknown methods/tools).
- Add worker-specific tests around `codeindex/memory_worker.py` retry transitions and failed queue handling.
- Add optional coverage reporting (e.g., pytest-cov) to track regression risk on core logic, not only end-to-end flows.
