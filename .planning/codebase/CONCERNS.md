# Codebase Concerns

## Priority Summary
- P0: Lock down filesystem exposure and basic service hardening in `codeindex/server.py` and `codeindex/analysis.py`.
- P1: Fix install/runtime fragility around SQLite extensions in `codeindex/storage.py`, `codeindex/memory_storage.py`, and `pyproject.toml`.
- P1: Remove high-latency request-path work in `codeindex/server.py` and `codeindex/storage.py`.
- P2: Improve indexing correctness and symbol quality in `codeindex/indexer.py`.
- P2: Add tests for security and degradation paths in `tests/test_server.py` and `tests/test_cli.py`.

## Security Risks

### 1) Arbitrary local file read via analysis root override (P0)
- `codeindex/server.py` accepts `root` from `/analysis/*` query params and resolves it directly in `_analysis_payload`.
- `codeindex/analysis.py` then reads files under that root (`_resolve_file`, `_read_text`) without constraining to configured project root.
- If server is bound beyond loopback (`codeindex serve --host 0.0.0.0`), this becomes remote arbitrary local file read for text files.
- Suggested fix: ignore user-supplied root in HTTP/MCP by default, or enforce `resolved_root.is_relative_to(default_root)`.

### 2) No auth/authorization on HTTP + MCP endpoints (P0)
- `codeindex/server.py` exposes `/search`, `/analysis/*`, `/memory/*`, and `/mcp` with no auth checks.
- Exposed memory endpoints leak prior command/query metadata from `memory_observations` in `codeindex/memory_storage.py`.
- Suggested fix: add optional API token middleware and default deny non-loopback host unless `--allow-remote` is explicitly set.

### 3) Stored XSS risk in memory viewer (P1)
- `codeindex/memory_viewer.py` uses `innerHTML` in `renderCard` with unescaped `title`/`summary`/`snippet` from memory records.
- These fields are derived from command/query text (`codeindex/memory_capture.py`) and can include attacker-controlled content.
- Suggested fix: switch to `textContent` for user-derived fields, or sanitize before HTML insertion.

## Reliability and Correctness

### 4) FTS5 treated as optional but schema requires it (P1)
- `codeindex/memory_storage.py` unconditionally executes `CREATE VIRTUAL TABLE ... USING fts5(...)`.
- `fts5_available()` implies optional capability, but init will fail entirely if FTS5 is unavailable.
- Suggested fix: probe before schema creation and fall back to non-FTS search mode.

### 5) Dependency declaration conflicts with fallback design (P1)
- `pyproject.toml` requires `sqlite-vec` and `sqlite-vss`, but `codeindex/storage.py` has runtime fallback to `python-cosine` when extensions are missing.
- This blocks install in environments where extension wheels are unavailable even though code can operate without them.
- Suggested fix: move both vector extensions to optional extras and keep pure-Python default install path.

### 6) Incremental sync can miss content changes (P2)
- `codeindex/indexer.py` skips re-read when `mtime` and `size` match previous state.
- On coarse timestamp filesystems or rapid rewrites with same size, content changes can be missed.
- Suggested fix: optionally hash when mtime delta is below a threshold, or persist inode/change-counter where available.

## Performance Risks

### 7) Expensive per-request DB initialization path (P1)
- Every HTTP request opens `Storage(...)` in `codeindex/server.py`.
- `Storage.__init__` runs `_sync_vec_index()` in `codeindex/storage.py`, which compares counts and may rebuild vector rows.
- Under load, this adds unnecessary startup cost and lock contention risk.
- Suggested fix: long-lived storage pool (or one per worker thread), and run vec sync only during indexing/migration steps.

### 8) Memory worker runs synchronously on user-facing request path (P1)
- `codeindex/server.py` and `codeindex/cli.py` call `memory_service.run_worker_once()` inline after command/request completion.
- This can inflate tail latency and couples UX latency to queue backlog.
- Suggested fix: background worker loop/process and bounded async flush in request path.

### 9) Fallback search degrades to full scan over embeddings (P2)
- `codeindex/search.py` `_fallback_scan_top_k` streams all matching chunks and computes cosine similarity in Python.
- For medium/large repos this becomes CPU-heavy and can block server threads.
- Suggested fix: add coarse lexical pre-index (BM25/FTS) before embedding scoring in fallback mode.

## Fragile Areas / Technical Debt

### 10) Memory capability cache is global and not synchronized (P2)
- `codeindex/memory_service.py` uses module-global `_CAPABILITY_CACHE` across sessions/threads.
- In threaded server mode this is shared mutable state without locking.
- Suggested fix: compute once at startup or protect with a lock; avoid hidden global state.

### 11) SSE endpoint is snapshot-style, not durable stream semantics (P3)
- `codeindex/server.py` `/memory/stream` returns one payload with `Content-Length`, then closes.
- `EventSource` in `codeindex/memory_viewer.py` will reconnect repeatedly; behavior is brittle and can duplicate rendering.
- Suggested fix: either implement true streaming with periodic flush and no content-length, or replace with polling endpoint explicitly.

### 12) Symbol extraction quality is regex-heavy for non-Python (P3)
- `codeindex/indexer.py` uses heuristic regex patterns for JS/TS/Go symbols.
- This misses many declarations and can create false positives, reducing retrieval relevance.
- Suggested fix: use tree-sitter extraction for indexed symbol records where available, not just analysis commands.

## Testing Gaps
- `tests/test_server.py` and `tests/test_cli.py` cover happy paths well, but there are no tests for:
- Path escape attempts through `root` on `/analysis/*`.
- Memory viewer HTML/script injection behavior.
- No-FTS5 environments and no-vector-extension environments at install/runtime boundaries.
- High-concurrency request latency/regression checks with non-trivial corpus sizes.

## Suggested Execution Order
1. Security hardening: root/path constraints + auth/token + viewer escaping.
2. Packaging/runtime stabilization: optionalize vector deps + true FTS fallback.
3. Request-path performance: stop per-request vec sync + move worker off critical path.
4. Indexing/search quality: sync invalidation improvements + stronger symbol extraction + fallback ranking improvements.
5. Test expansion for all above regression paths.
