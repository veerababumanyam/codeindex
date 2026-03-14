# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `codeindex/`. Keep CLI entrypoints in `codeindex/cli.py`, HTTP and MCP handlers in `codeindex/server.py`, indexing and search logic in `indexer.py`, `search.py`, and `storage.py`, and memory-related features in the `memory_*` modules. Tests live in `tests/` and currently cover CLI flows and server endpoints. Reference material and sample config files belong in `docs/`, including `docs/codeindex.example.yaml`.

## Build, Test, and Development Commands
Create an environment and install the package locally:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
pip install -e ".[analysis]"
```

Run the full test suite with `pytest`. Use `python -m codeindex.cli --help` to inspect CLI options. Typical local workflow:

```bash
python -m codeindex.cli init --path . --workspace demo
python -m codeindex.cli sync
python -m codeindex.cli query "auth flow" --workspace demo
python -m codeindex.cli serve --host 127.0.0.1 --port 9090
```

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and explicit type hints where practical. Keep modules focused by responsibility; new memory features should extend the existing `memory_*` pattern instead of adding unrelated utilities to `cli.py` or `server.py`. Prefer standard library solutions first. No formatter or linter is configured in `pyproject.toml`, so match the surrounding style closely and keep imports grouped and stable.

## Testing Guidelines
Use `pytest` for all tests. Add new tests under `tests/` with filenames like `test_<area>.py` and functions named `test_<behavior>()`. Follow the current pattern of using `tmp_path` to build isolated sample projects and validating JSON payloads from CLI or HTTP responses. Cover both happy paths and config or input validation failures when behavior changes.

## Commit & Pull Request Guidelines
Recent commits use short, imperative summaries such as `docs: map existing codebase` and `Improve config loading fallback and verify HTTP search endpoint`. Keep commit subjects concise, specific, and scoped when helpful. Pull requests should describe the user-visible change, list verification steps run locally, and include sample CLI output or request examples when API behavior changes.

## Configuration & Data Notes
Do not commit generated `.codeindex/` databases or local workspace artifacts. Treat `codeindex.yaml` as local configuration unless the change is to the documented sample in `docs/`.
