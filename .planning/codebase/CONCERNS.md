# Codebase Concerns

## Overall Risk Profile

This repository is a compact prototype, but several core behaviors are implemented in ways that will become fragile quickly under larger datasets, concurrent usage, or less controlled input. The dominant risks are:

- Search and sync paths scale linearly with corpus size and rely on full in-memory materialization.
- The HTTP server shares a single SQLite connection across threads without explicit concurrency controls.
- Configuration parsing and mutation are intentionally minimal, which makes malformed or richer YAML inputs risky.
- Test coverage validates the happy path only and leaves error handling, concurrency, and scale characteristics mostly unverified.

## Technical Debt And Fragile Design

### 1. Search is full-scan, in-process, and memory-heavy

Files involved: `codeindex/search.py`, `codeindex/storage.py`

- `codeindex/search.py` iterates over every returned chunk from `storage.all_chunks(...)` and scores each one in Python (`codeindex/search.py:42-52`).
- `codeindex/storage.py` loads all matching rows into Python objects before ranking (`codeindex/storage.py:119-145`).
- There is no candidate pruning, no pagination, no approximate nearest-neighbor index, and no SQL-side narrowing beyond workspace and source kind.

Practical impact:

- Query latency will grow roughly with total indexed chunk count.
- Memory use grows with result corpus size because the entire candidate set is materialized before sorting.
- Larger repos or inclusion of shared `global` docs will degrade both CLI queries and `/search` server responsiveness.

Maintenance risk:

- Any future move to larger workspaces will require redesign, not tuning.
- The current API shape hides this cost, so downstream callers may assume queries are cheap when they are not.

### 2. Sync always reads full file contents and recomputes embeddings

Files involved: `codeindex/indexer.py`, `codeindex/embedding.py`

- `sync_workspace(...)` walks the entire tree with `root.rglob("*")` (`codeindex/indexer.py:150`) and reads every eligible file as text (`codeindex/indexer.py:159`) before deciding whether content changed.
- Change detection is based on a SHA-256 of the full file content, not a cheaper stat-first fast path (`codeindex/indexer.py:160-163`).
- Re-indexing rebuilds all chunks and embeddings for any changed file (`codeindex/indexer.py:165-191`).

Practical impact:

- Poll-based watch mode in `codeindex/cli.py` (`codeindex/cli.py:94-103`) repeatedly rescans the entire project, which will waste I/O on medium or large repos.
- Large single-file edits trigger full re-chunking and re-embedding of that file rather than incremental updates.

Maintenance risk:

- The prototype behavior is acceptable for demos but becomes operational debt once users expect near-real-time indexing.

### 3. The fallback YAML parser is intentionally incomplete and easy to break

Files involved: `codeindex/config.py`, `codeindex/cli.py`

- If `PyYAML` is unavailable, `load_config(...)` falls back to `_parse_simple_yaml(...)` (`codeindex/config.py:118-126`).
- That parser only supports a very narrow subset of YAML and infers list-vs-dict structure from hardcoded keys (`codeindex/config.py:86-94`).
- Scalars are parsed with simplistic rules, including only lowercase `true`/`false` booleans (`codeindex/config.py:46-54`).
- `codeindex cli config` writes arbitrary dotted keys back into the structure (`codeindex/cli.py:81-85`, `codeindex/config.py:142-149`), which can create shapes the fallback parser was never designed to read safely.

Practical impact:

- A user can produce a syntactically valid config that works with PyYAML installed but fails or changes meaning in environments using the fallback parser.
- Config portability across machines is fragile.

Maintenance risk:

- Every config schema expansion increases the chance of parser drift because the fallback parser is schema-coupled.

### 4. Invalid config modes silently degrade instead of failing fast

Files involved: `codeindex/search.py`, `codeindex/cli.py`, `codeindex/server.py`

- The CLI and HTTP layer validate `mode` when it comes from command arguments or query params (`codeindex/cli.py:178-183`, `codeindex/server.py:34-35`).
- `search_index(...)` still silently falls back to `hybrid` for unknown modes via `MODE_TO_KINDS.get(mode, MODE_TO_KINDS["hybrid"])` (`codeindex/search.py:37`).

Practical impact:

- A malformed value stored in config can produce behavior that contradicts reported intent, because metrics still echo the invalid `mode` string (`codeindex/search.py:59-66`).
- Debugging relevance issues becomes harder because the system can claim one mode while executing another.

Maintenance risk:

- Silent fallback hides configuration errors that should be surfaced early.

## Security Concerns

### 5. Threaded HTTP serving uses a shared SQLite connection

Files involved: `codeindex/server.py`, `codeindex/storage.py`, `codeindex/cli.py`

- `serve(...)` uses `ThreadingHTTPServer` (`codeindex/server.py:73`).
- All handler instances share the same `Storage` instance through a class attribute (`codeindex/server.py:68-73`).
- `Storage` creates a single SQLite connection with `check_same_thread=False` (`codeindex/storage.py:55`), but there is no explicit locking, connection pool, or per-request connection strategy.

Practical impact:

- Concurrent requests can interleave operations on one SQLite connection in undefined ways.
- Even if current usage is mostly reads, future write endpoints or background sync integrations would make this substantially riskier.

Security and reliability angle:

- Concurrency bugs in persistence layers often surface as intermittent corruption, locked-database errors, or partial responses that are difficult to reproduce.

### 6. The server can expose indexed source and docs with no authentication

Files involved: `codeindex/server.py`, `codeindex/cli.py`, `README.md`

- `/search` returns file paths, line numbers, symbol names, and source snippets (`codeindex/server.py:40-58`).
- `codeindex serve` allows arbitrary host binding (`codeindex/cli.py:189-191`), even though the default is localhost.

Practical impact:

- If an operator binds to `0.0.0.0` or otherwise exposes the port, the service becomes a plaintext code/document retrieval endpoint.
- Shared `global` docs make this risk broader than just project source.

Maintenance risk:

- The repo currently has no guardrails, warnings, auth, TLS story, or request logging to support safer deployment.

## Performance Concerns

### 7. Embeddings are stored as JSON text blobs in SQLite

Files involved: `codeindex/storage.py`

- Each chunk embedding is serialized to JSON text on insert (`codeindex/storage.py:90-106`) and parsed back on every query (`codeindex/storage.py:131-145`).

Practical impact:

- Storage size is larger than needed.
- Query cost includes repeated JSON decoding for every candidate vector.

Maintenance risk:

- This is fine for a prototype but adds avoidable overhead that compounds with the full-scan search design.

### 8. Search sorts the full scored list even when only top-k is needed

Files involved: `codeindex/search.py`

- After scoring every candidate, the code sorts the entire list (`codeindex/search.py:52`) and only then slices `[:top_k]` (`codeindex/search.py:54`).

Practical impact:

- This adds unnecessary `O(N log N)` work when a bounded heap or selection algorithm would suffice.

## Testing And Maintenance Gaps

### 9. Tests cover only happy paths and miss major operational risks

Files involved: `tests/test_cli.py`, `tests/test_server.py`

- Existing tests prove init/sync/query/status and a basic server response (`tests/test_cli.py:11-145`, `tests/test_server.py:13-46`).
- There are no tests for malformed configs, YAML fallback behavior, invalid persisted `mode`, binary or non-UTF8 edge cases, large corpus behavior, concurrent HTTP access, watch mode lifecycle, or workspace deletion cleanup.

Practical impact:

- The code can appear stable while the highest-risk behaviors remain unexercised.

Maintenance risk:

- Refactors in `codeindex/config.py`, `codeindex/storage.py`, and `codeindex/search.py` will be high-anxiety because regression detection is weak outside the happy path.

### 10. Resource lifecycle handling is inconsistent

Files involved: `codeindex/cli.py`

- `cmd_query(...)`, `cmd_status(...)`, and `_run_sync_once(...)` close `Storage` manually after the main work path (`codeindex/cli.py:56`, `codeindex/cli.py:136`, `codeindex/cli.py:143`).
- `cmd_serve(...)` opens storage and never explicitly closes it around server shutdown (`codeindex/cli.py:148-152`).
- None of these use `try/finally` or a context manager, so exceptions during search/sync can leak open connections.

Practical impact:

- This is unlikely to matter in short-lived CLI runs, but it is a fragile pattern that becomes more error-prone as commands gain complexity.

## Highest-Value Follow-Up Work

1. Replace the shared threaded SQLite connection with a safer access model before expanding server usage.
2. Introduce candidate pruning and top-k selection to stop full-corpus query scans from becoming the default architecture.
3. Remove or harden the fallback YAML parser so config behavior is deterministic across environments.
4. Add tests for concurrency, config parsing edge cases, and failure paths before making feature additions on top of the current prototype.
