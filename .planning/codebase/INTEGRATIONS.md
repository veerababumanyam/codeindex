# Integration Map

## External APIs and Services
- No mandatory outbound third-party API integration is implemented in runtime code.
- Embedding generation is local/deterministic (`codeindex/embedding.py`), so search works offline.
- Config sample includes an `llm` section (`docs/codeindex.example.yaml`), but current runtime modules do not consume it (`codeindex/config.py`, `codeindex/cli.py`, `codeindex/server.py`).

## HTTP Service Exposure (Inbound)
- Built-in HTTP server exposes local endpoints via `ThreadingHTTPServer` (`codeindex/server.py`).
- Search API: `GET /search` for semantic retrieval (`codeindex/server.py`, `README.md`).
- Analysis APIs: `GET /analysis/files|symbols|ast|validate|dependencies|complexity|usage|stats` (`codeindex/server.py`).
- Memory APIs: `GET /memory/status|search|observations/<id>|sessions|citations/<id>|viewer|stream` (`codeindex/server.py`).

## MCP / Agent Integration
- MCP-compatible JSON-RPC endpoint: `POST /mcp` (`codeindex/server.py`, `README.md`).
- Supported tool names: `codeindex_search`, `codeindex_analyze`, `codeindex_memory_search`, `codeindex_memory_expand`, `codeindex_memory_session_list`, `codeindex_memory_session_show`, `codeindex_memory_status` (`codeindex/server.py`).
- Protocol methods implemented: `initialize`, `tools/list`, `tools/call` (`codeindex/server.py`).

## Databases and Storage
- Primary database: SQLite file `.codeindex/index.db` (`codeindex/cli.py`, `codeindex/storage.py`).
- Core indexing data stored in `files` and `chunks` tables (`codeindex/storage.py`).
- Memory subsystem persists to `memory_sessions`, `memory_observations`, `memory_citations`, `memory_queue`, `memory_injection_log`, `memory_capabilities` (`codeindex/memory_storage.py`).
- Full-text search for memory uses SQLite FTS5 virtual table `memory_observation_fts` when available (`codeindex/memory_storage.py`, `codeindex/memory_service.py`).

## Vector Search Backends
- Optional SQLite extension integration:
- `sqlite-vec` loaded dynamically and used for `chunk_vec` virtual table (`codeindex/storage.py`).
- `sqlite-vss` fallback and used for `chunk_vss` virtual table (`codeindex/storage.py`).
- Final fallback is in-process cosine ranking when no extension is available (`codeindex/storage.py`, `codeindex/search.py`).

## Auth Providers
- No auth providers (OAuth/OIDC/SAML/etc.) are integrated.
- HTTP and MCP endpoints are exposed without built-in authentication middleware (`codeindex/server.py`).

## Webhooks and Eventing
- No external webhook receiver/sender exists.
- Internal event capture exists for memory lifecycle (`capture_event`, queued processing) (`codeindex/memory_service.py`, `codeindex/memory_worker.py`).
- Real-time memory updates are delivered to browser clients via SSE at `GET /memory/stream` (`codeindex/server.py`, `codeindex/memory_viewer.py`).

## Message Queues
- No external broker (RabbitMQ/Kafka/SQS/NATS) is used.
- Internal lightweight queue is SQLite-backed table `memory_queue` with state transitions (`codeindex/memory_storage.py`, `codeindex/memory_worker.py`).

## Practical Integration Examples
- MCP tool discovery call: `{"jsonrpc":"2.0","id":1,"method":"tools/list"}` (`README.md`, `codeindex/server.py`).
- Memory stream consumer in UI: browser `EventSource('/memory/stream?...')` (`codeindex/memory_viewer.py`).
- Local vector backend capability reporting appears in query metrics (`codeindex/search.py`, `tests/test_cli.py`, `tests/test_server.py`).
