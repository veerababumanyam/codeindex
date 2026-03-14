# External Integrations

## Overview
- The implemented repository has very few true external integrations.
- Its main boundaries are the local filesystem, a local SQLite database, and an optional local HTTP server.
- There are no implemented outbound SaaS, cloud, or LLM API calls in the current code.

## Filesystem Boundaries
- Project content is read from `paths.project_root` configured through `codeindex.yaml`, loaded in `codeindex/config.py`, and traversed in `codeindex/indexer.py`.
- Optional shared documentation directories are read from `paths.global_docs` and indexed into the `global` workspace in `codeindex/cli.py`.
- Local index state is created under ``<config dir>\.codeindex\index.db`` via `db_path()` in `codeindex/cli.py`.
- The indexer reads text-like source and document formats only, based on extension allowlisting in `codeindex/indexer.py` (`.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.toml`, `.rs`, `.go`, `.java`, `.c`, `.h`, `.cpp`, `.hpp`, `.rb`, `.php`, `.cs`).
- Exclusion patterns are applied with `fnmatch` against relative paths in `codeindex/indexer.py`.

## Database Integration
- Database engine: SQLite through Python `sqlite3` in `codeindex/storage.py`.
- Database file: `.codeindex/index.db` relative to the selected config directory in `codeindex/cli.py`.
- Tables:
  - `files` tracks `workspace`, `path`, `content_hash`, and `mtime`.
  - `chunks` stores chunk payloads, symbol metadata, token counts, and serialized embeddings.
- Schema migration strategy is in-process and minimal: `codeindex/storage.py` checks `PRAGMA table_info(chunks)` and adds missing columns with `ALTER TABLE`.
- There is no integration with Postgres, MySQL, Redis, vector databases, or hosted search services.

## HTTP And API Surface
- Inbound API only: `GET /search` served by `ThreadingHTTPServer` in `codeindex/server.py`.
- Default bind target is `127.0.0.1:9090` from `codeindex/cli.py`, which keeps the service loopback-only unless the operator passes a different `--host`.
- Query parameters accepted by `codeindex/server.py`:
  - `query`
  - `workspace`
  - `include_global`
  - `mode`
  - `top_k`
- Response format is JSON with `metrics` and `results`, produced in both `codeindex/server.py` and the CLI query command in `codeindex/cli.py`.
- There are no POST endpoints, webhooks, SSE streams, WebSockets, gRPC services, or message-bus integrations.

## Auth And Identity
- No authentication or authorization layer exists in the HTTP server in `codeindex/server.py`.
- No user model, session store, API keys, OAuth flow, JWT handling, or RBAC logic is implemented anywhere under `codeindex/`.
- The `workspace` query parameter is a logical content-isolation mechanism, not an identity or permission system.

## External Providers And APIs
- Implemented outbound providers: none.
- Embeddings are generated locally by `embed_text()` in `codeindex/embedding.py`; there is no OpenAI, Ollama, Hugging Face, Azure, or other model provider call path.
- The sample config at `docs/codeindex.example.yaml` includes `llm.provider`, `llm.model`, `llm.embedding_model`, and `llm.api_key_env`, but no production code reads or uses those values.
- This means the repository currently exposes an interface for future provider integration in docs only, not in executable code.

## Symbol And Language Parsing Integrations
- Python symbol extraction uses the built-in `ast` module in `codeindex/indexer.py`.
- JS/TS/Go symbol extraction uses regex heuristics in `codeindex/indexer.py`.
- There is no tree-sitter, LSP, ctags, ripgrep subprocess, or compiler-backed parser integration.

## Network Boundaries
- Inbound network boundary: optional HTTP listener started by `codeindex serve` in `codeindex/cli.py`.
- Outbound network boundary: none in the implemented application code.
- Test-only local network usage exists in `tests/test_server.py`, which issues a loopback request with `urllib.request` to the temporary local server process.

## Webhooks And Eventing
- No webhook producers or consumers exist.
- Watch mode in `codeindex/cli.py` is polling-based with `time.sleep()`, not OS file watching and not an integration with external event systems.
- There is no Kafka, RabbitMQ, SQS, Pub/Sub, cron service, or background scheduler integration.

## Notable Absences
- No remote artifact storage for the index.
- No cloud deployment descriptors or container configuration.
- No secrets manager integration; the current runtime does not require secrets for implemented features.
- No telemetry, logging backend, tracing, or metrics exporter beyond CLI/stdout JSON responses.
- No CORS handling, TLS termination, reverse-proxy awareness, or request authentication on the HTTP endpoint.
