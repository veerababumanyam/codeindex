# Testing Patterns

## Framework

- The test suite is built around `pytest`, configured via `[tool.pytest.ini_options]` in `pyproject.toml`.
- `testpaths = ["tests"]` makes `tests/` the single discovery root.
- There is no sign of `unittest.TestCase`, `tox`, `nox`, `coverage`, or plugin-specific configuration in `pyproject.toml`.
- I could not execute the suite in this environment because `pytest` is not installed, so the notes below describe the repository's current testing shape from source inspection.

## Test Layout

- Tests live in two files: `tests/test_cli.py` and `tests/test_server.py`.
- The suite is organized by interface boundary rather than by internal module.
- `tests/test_cli.py` covers the end-to-end CLI flows for `init`, `sync`, `query`, and `status`, plus behavior around global docs and symbol mode.
- `tests/test_server.py` covers the HTTP search endpoint by starting the CLI server and calling it over `urllib`.
- There is no `tests/conftest.py`, no shared fixture module, and no split between unit and integration directories.

## Test Style

- Tests are integration-heavy. They exercise the installed module via `python -m codeindex.cli` subprocesses instead of calling command handlers directly.
- Assertions focus on externally visible behavior: config file contents, JSON payload fields, result presence, workspace routing, and symbol preference.
- Temporary filesystems are created with the built-in `tmp_path` fixture in every test.
- Test data is created inline with minimal source files such as `app.py`, `main.py`, `service.py`, and `auth.py`.
- JSON outputs are parsed with `json.loads(...)` and then asserted field-by-field.
- `tests/test_server.py` uses a fixed sleep (`time.sleep(0.8)`) to wait for the server to boot, which is simple but timing-sensitive.

## Fixtures And Helpers

- The only pytest fixture visibly used is `tmp_path`.
- Both `tests/test_cli.py` and `tests/test_server.py` define the same local helper:
  - `run_cmd(cmd, cwd)` wraps `subprocess.run(..., capture_output=True, text=True, check=True)`.
- There are no reusable fixtures for:
  - repo root resolution
  - config creation
  - project scaffolding
  - server startup/teardown
  - seeded storage instances
- Because helpers are local to each file, reuse is low and future test expansion will likely repeat setup logic unless a `conftest.py` is introduced.

## Mocking And Stubbing Patterns

- There is effectively no mocking in the current suite.
- The tests prefer real subprocess execution, real filesystem I/O, real SQLite database creation, and a real HTTP server process.
- This means the suite currently behaves more like black-box acceptance testing than isolated unit testing.
- No `unittest.mock`, monkeypatching, fake storage objects, or stub embeddings are present in `tests/test_cli.py` or `tests/test_server.py`.

## Coverage Shape

- Covered paths:
  - CLI initialization and config file creation through `tests/test_cli.py`
  - Workspace sync and query happy paths through `tests/test_cli.py`
  - Inclusion of global docs in query results through `tests/test_cli.py`
  - Symbol-biased retrieval mode through `tests/test_cli.py`
  - HTTP `/search` endpoint happy path through `tests/test_server.py`
- Covered user-facing payload expectations:
  - `metrics.mode`
  - `estimated_tokens_saved`
  - presence of `results`
  - symbol metadata in results
  - status counts such as `files` and `symbols`
- Lightly or not covered from current tests:
  - `codeindex/config.py` internals such as `_deep_merge`, `_parse_simple_yaml`, `_to_simple_yaml`, and `set_config_value`
  - `codeindex/embedding.py` validation and math behavior, including invalid chunk sizes and dimension mismatch handling
  - `codeindex/storage.py` migration logic, deletion behavior, counts edge cases, and workspace token counting
  - `codeindex/indexer.py` exclusion handling, unchanged-file skipping, deletion detection, regex symbol extraction for non-Python files, and syntax-error tolerance
  - `codeindex/search.py` workspace resolution, scoring details, and mode fallback behavior
  - `codeindex/server.py` negative paths such as missing params, invalid `top_k`, invalid `mode`, and unknown routes
  - `codeindex/cli.py` negative paths such as missing workspace requirements, `init` overwrite refusal, and watch mode behavior

## Reliability Characteristics

- The current approach gives decent confidence that the main product flows work together end to end.
- The suite is likely slower than necessary as it repeatedly shells out to Python and creates fresh storage for each test.
- Failure localization is weaker than with unit tests because multiple layers are exercised at once.
- The fixed port in `tests/test_server.py` (`9134`) can conflict with other processes.
- The startup wait in `tests/test_server.py` can create flaky behavior on slower machines or CI runners.

## Practical Gaps

- Add unit tests for pure helpers in `codeindex/embedding.py`, `codeindex/config.py`, and `codeindex/search.py`.
- Add storage-focused tests around `codeindex/storage.py`, especially schema migration and deletion behavior.
- Add indexer tests for `should_exclude`, symbol extraction across suffixes, and unchanged/deleted file bookkeeping in `codeindex/indexer.py`.
- Add negative-path server tests for bad query strings in `codeindex/server.py`.
- Add CLI tests for failure exit codes and human-readable error messages in `codeindex/cli.py`.
- Centralize subprocess and temp-project setup in `tests/conftest.py` or a shared helper module.
- Replace fixed sleeps and fixed ports in `tests/test_server.py` with readiness polling and ephemeral port allocation.

## Recommended Testing Direction

- Keep the current integration tests because they validate the repository's primary interfaces well.
- Layer in small unit tests for pure logic so regressions are caught closer to the source.
- Introduce shared fixtures once more test cases are added; the duplicated setup is manageable now but will become noise quickly.
- If CI is added or expanded, include explicit coverage reporting so the current "happy-path heavy" shape becomes measurable instead of inferred.
