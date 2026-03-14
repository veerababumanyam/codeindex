# CodeIndex Feature Research

## Goal
Define practical feature scope for near-term requirements in the CodeIndex domain (local-first indexing, retrieval, analysis, and memory across CLI/HTTP/MCP).

## Table Stakes (Must-Have)
- Reliable local indexing and sync: initial sync, incremental updates, deletion handling, and watch mode that does not silently miss common changes.
- Fast, useful retrieval: `chunks`/`symbols`/`hybrid` modes with predictable relevance, stable metadata, and token-aware responses.
- Interface parity: equivalent behavior and semantics across CLI, HTTP, and MCP for core sync/query/analyze/memory operations.
- Safe-by-default local service: loopback-first exposure, path-root constraints for analysis, and optional auth when remote access is enabled.
- Robust local persistence: schema/migration safety for index and memory tables, clear degradation when vector/FTS capabilities are unavailable.
- Core analysis coverage: files, symbols, AST, dependencies, complexity, usage, stats with deterministic output contracts.
- Basic operational trust: clear status/health signals, actionable errors, and test coverage for critical paths and degradation modes.

## Differentiators (Competitive Value)
- Offline-first semantic search with deterministic local embeddings and no mandatory external API dependencies.
- Unified developer surface area: one local knowledge substrate exposed through CLI + REST + MCP.
- Integrated code intelligence and memory: retrieval + structural analysis + session memory/citations in one toolchain.
- Progressive memory disclosure (`summary`/`expanded`/`full`) for low-token agent workflows.
- Workspace isolation with optional shared global docs, enabling multi-repo/local-context workflows without SaaS overhead.

## Anti-Features (Explicitly Avoid for Now)
- Multi-tenant hosted SaaS, centralized cloud indexing, or account/org management.
- Real-time collaborative editing/annotation or shared live cursors.
- Heavy distributed infrastructure (external queues, mandatory remote vector DB, service mesh) for core functionality.
- Advanced ML/reranking stacks that require online model serving as a baseline.
- Broad plugin marketplace/platform work before reliability/security/performance table stakes are hardened.
- Expanding non-core UI surfaces beyond pragmatic diagnostics (avoid full productized web app scope).

## Feature Groups: Complexity and Dependencies
| Feature Group | Scope (Near-Term) | Complexity | Key Dependencies | Major Risks / Notes |
|---|---|---|---|---|
| Indexing & Sync Correctness | Harden incremental invalidation, deletion consistency, and watch-mode reliability | Medium | `codeindex/indexer.py`, `codeindex/storage.py`, file metadata/hash strategy, tests | Missed updates on coarse timestamp filesystems; requires edge-case fixtures |
| Retrieval Quality & Performance | Preserve fast top-k relevance across backends; improve fallback behavior for larger repos | Medium-High | `codeindex/search.py`, `codeindex/storage.py`, sqlite-vec/vss optional paths, cosine fallback | Fallback full-scan CPU cost; backend capability drift |
| Analysis Safety & Utility | Keep current analysis breadth but enforce safe root constraints and contract consistency | Medium | `codeindex/analysis.py`, `codeindex/server.py`, CLI/server schema alignment | Current root override is a security exposure; must not break existing scripts |
| Memory Reliability & UX Contracts | Stabilize capture/search/expand/session flows and reduce request-path latency impact | Medium | `codeindex/memory_service.py`, `codeindex/memory_storage.py`, `codeindex/memory_worker.py`, SSE/viewer | Inline worker execution affects latency; FTS availability assumptions |
| Service Hardening (HTTP/MCP) | Default-safe local operation, optional token auth, consistent error model | Medium | `codeindex/server.py`, config/CLI flags, MCP method/tool handlers | Breaking behavior for users relying on remote binding without controls |
| Dependency & Packaging Resilience | Make optional capabilities truly optional and preserve functional fallback install path | Low-Medium | `pyproject.toml`, runtime capability probes in storage/memory modules | Install friction blocks adoption despite runtime fallbacks |
| Interface Contract Consistency | Normalize CLI/HTTP/MCP parameter names, defaults, and response envelopes | Medium | `codeindex/cli.py`, `codeindex/server.py`, MCP handlers, docs/tests | Regressions from subtle contract changes; requires fixture-based compatibility tests |
| Verification & Regression Net | Add tests for security paths, no-FTS/no-vector degradation, and latency-sensitive flows | Medium | `tests/test_cli.py`, `tests/test_server.py`, synthetic corpora | Coverage gaps currently hide high-impact failures |

## Practical Scoping Guidance
- Prioritize in this order: service safety -> persistence/dependency resilience -> sync correctness -> request-path performance -> interface parity -> retrieval/analysis quality enhancements.
- Treat CLI/HTTP/MCP parity as a release gate for any core feature change.
- Require degradation-path tests (no vector extension, no FTS, large-repo fallback) before marking feature groups complete.
