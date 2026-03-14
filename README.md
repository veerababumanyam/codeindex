# CodeIndex Sync

Local-first semantic code search, code intelligence analysis, and persistent project memory for AI-assisted development.

`CodeIndex Sync` helps you index a repository into SQLite, run low-token semantic retrieval, analyze code structure (AST, symbols, dependencies, complexity, usage), and expose everything via CLI, HTTP, and MCP JSON-RPC tools.

## Why CodeIndex Sync

- Local-first: works without external embedding APIs by default.
- Incremental indexing: only re-indexes changed files.
- Workspace isolation: query one project while optionally including shared global docs.
- Token efficiency: retrieval returns compact snippets plus token metrics.
- Persistent memory: captures prior sessions and supports progressive disclosure (`summary`, `expanded`, `full`).
- Multiple interfaces: CLI + REST endpoints + MCP tools for agent workflows.

## Core Features

### 1) Semantic Code Search

- Indexes text chunks and lightweight symbols.
- Supports `chunks`, `symbols`, and `hybrid` retrieval modes.
- Returns ranked snippets with file path, line range, symbol metadata, and token counts.

### 2) Incremental Sync + Watch Mode

- Tracks file hash + mtime in SQLite.
- Handles file additions, updates, and deletions.
- `--watch` mode continuously polls and re-indexes deltas.

### 3) Integrated Code Analysis

`codeindex analyze` supports:

- `files`: list project files.
- `symbols`: extract symbols for a file.
- `ast`: query Python AST nodes.
- `validate`: syntax validation.
- `dependencies`: import/dependency analysis.
- `complexity`: function/file complexity metrics.
- `usage`: symbol reference scanning.
- `stats`: project-level language/line/symbol summary.

### 4) Persistent Memory for Dev Workflows

- Auto-captures sync/query/analyze/MCP events.
- Stores sessions, observations, citations, and stream events.
- Supports progressive disclosure and stable IDs (`obs_...`, `cit_...`).
- Includes memory viewer and stream endpoints.

### 5) API + MCP Server

- HTTP search and analysis endpoints.
- Memory API endpoints.
- MCP-compatible `POST /mcp` with tools for search, analysis, and memory retrieval.

## Architecture (High Level)

- Storage: SQLite at `.codeindex/index.db`.
- Vector search backend order:
  - `sqlite-vec` (preferred)
  - `sqlite-vss` (fallback)
  - in-process cosine search (final fallback)
- Embeddings: deterministic local embedding (no network required).
- Isolation:
  - workspace-specific index
  - optional `global` workspace for shared docs
  - project-local persistent memory.

## Install

### Requirements

- Python `>=3.10`
- `pip`

### Setup

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

pip install -e .
```

Optional analysis parsers:

```bash
pip install -e ".[analysis]"
```

## Quick Start

```bash
codeindex init --path /myproject --workspace myapp --global-docs /shared
codeindex sync
codeindex query "find auth logic" --workspace myapp --top-k 5 --include-global --mode hybrid
codeindex status
```

Run continuous sync:

```bash
codeindex sync --watch --interval 2
```

Serve locally by default:

```bash
codeindex serve
```

Remote binds require an explicit opt-in:

```bash
codeindex serve --host 0.0.0.0 --port 9090 --allow-remote
```

To protect HTTP and MCP routes, set `server.auth_token` in `codeindex.yaml` or pass `--auth-token` and send the same value in the `X-CodeIndex-Token` header.

## CLI Commands

### Project + Search

- `codeindex init`
- `codeindex config <key> <value>`
- `codeindex sync [--watch]`
- `codeindex query "<text>" [--mode chunks|symbols|hybrid]`
- `codeindex status`

### Analysis

- `codeindex analyze files --limit 100`
- `codeindex analyze symbols --path src/auth.py`
- `codeindex analyze ast --path src/auth.py --node-type FunctionDef --name-contains login`
- `codeindex analyze validate --path src/auth.py`
- `codeindex analyze dependencies --path src/auth.py`
- `codeindex analyze complexity --path src/auth.py`
- `codeindex analyze usage --symbol login_user --limit 25`
- `codeindex analyze stats`

### Memory

- `codeindex memory status`
- `codeindex memory search "auth failure" --workspace myapp --layer summary`
- `codeindex memory expand obs_123456789abc`
- `codeindex memory session list --workspace myapp`
- `codeindex memory session show <session_id>`
- `codeindex memory citations <target_id>`
- `codeindex memory viewer`

## HTTP API

Start server:

```bash
codeindex serve --host 127.0.0.1 --port 9090
```

By default the server only allows loopback hosts (`127.0.0.1`, `localhost`, `::1`). Binding to a non-loopback address such as `0.0.0.0` fails unless `server.allow_remote: true` or `--allow-remote` is supplied intentionally.

Remote exposure is loopback-only by default. Binding to `0.0.0.0`, a LAN IP, or any non-loopback host requires an explicit opt-in:

```bash
codeindex serve --host 0.0.0.0 --port 9090 --allow-remote
```

Optional API token protection applies to both HTTP and MCP routes. Set `server.auth_token` in `codeindex.yaml` or pass `--auth-token` when starting the server, then include that value in the `X-CodeIndex-Token` header on each request.

Main endpoints:

- `GET /search?query=...&workspace=...&top_k=5&include_global=true&mode=hybrid`
- `GET /analysis/files`
- `GET /analysis/symbols?path=src/auth.py`
- `GET /analysis/ast?path=src/auth.py&node_type=FunctionDef`
- `GET /analysis/validate?path=src/auth.py`
- `GET /analysis/dependencies?path=src/auth.py`
- `GET /analysis/complexity?path=src/auth.py`
- `GET /analysis/usage?symbol=login_user`
- `GET /analysis/stats`
- `GET /memory/status?workspace=myapp`
- `GET /memory/search?workspace=myapp&query=auth&layer=summary&budget=600`
- `GET /memory/observations/<observation_id>`
- `GET /memory/sessions?workspace=myapp`
- `GET /memory/sessions/<session_id>`
- `GET /memory/citations/<target_id>`
- `GET /memory/viewer`
- `GET /memory/stream?workspace=myapp`

## MCP Integration

Endpoint:

```http
POST /mcp
```

Supported tools:

- `codeindex_search`
- `codeindex_analyze`
- `codeindex_memory_search`
- `codeindex_memory_expand`
- `codeindex_memory_session_list`
- `codeindex_memory_session_show`
- `codeindex_memory_status`

Example:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

## Configuration

Config file: `codeindex.yaml`  
Sample: `docs/codeindex.example.yaml`

Key sections:

- `workspace`
- `paths.project_root`
- `paths.global_docs`
- `server.host`
- `server.port`
- `server.allow_remote`
- `server.auth_token`
- `indexing.*`
- `excludes`
- `query.*`
- `analysis.prefer_tree_sitter`
- `server.host`
- `server.port`
- `server.allow_remote`
- `server.auth_token`
- `server.auth_token_header`
- `memory.*`

## SEO/GEO Notes for GitHub Discoverability

This README is intentionally optimized for:

- GitHub search keywords: `semantic code search`, `local-first`, `SQLite vector search`, `MCP server`, `code intelligence`, `AST analysis`, `developer memory`.
- AI answer engines (GEO): clear feature headings, explicit command examples, endpoint lists, and architecture terms aligned with common developer queries.

## Testing

Run test suite:

```bash
pytest
```

Current tests cover:

- CLI flows (`init/sync/query/status`)
- incremental sync behavior
- analysis commands
- server search + analysis endpoints
- MCP tool listing and calls
- memory CLI + HTTP + MCP paths

## Roadmap Ideas

- Native filesystem event watcher (non-polling).
- Additional language parsers and richer symbol extraction.
- Optional external embedding providers.
- Advanced ranking and reranking controls.

## License

No license file is currently present in this repository. Add one (for example `MIT`) before public distribution.
