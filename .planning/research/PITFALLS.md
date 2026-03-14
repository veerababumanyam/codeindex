# CodeIndex Sync Hardening Pitfalls

Scope: practical risks when expanding and hardening local-first indexing, search, analysis, and memory surfaces.

Phase labels used below:
- Phase 1: Security hardening (path constraints, auth, safe rendering)
- Phase 2: Runtime/packaging resilience (capability fallback correctness)
- Phase 3: Request-path performance and concurrency hardening
- Phase 4: Index/search correctness and quality improvements
- Phase 5: Test and regression safety net expansion

## 1) Local file exposure through analysis root/path input
- Why it happens in this domain: developer tools often expose flexible file inspection APIs; convenience parameters (`root`, `path`) can bypass intended workspace boundaries.
- Early warning signs: requests for files outside project root succeed; absolute paths accepted; server bound to non-loopback with analysis endpoints enabled.
- Prevention strategy: enforce canonical root boundary checks on every file read, ignore/deny untrusted root overrides by default, require explicit allowlist for remote access.
- Which phase should address it first: Phase 1.

## 2) Unauthenticated API/MCP access leaks code and memory
- Why it happens in this domain: local-first tools frequently assume trusted localhost usage, but users later expose ports for remote/agent workflows.
- Early warning signs: service started on `0.0.0.0`; no token/API key gate; memory/session endpoints readable without credentials.
- Prevention strategy: default-loopback binding, opt-in remote flag, token middleware for HTTP/MCP, clear startup warnings when insecure mode is enabled.
- Which phase should address it first: Phase 1.

## 3) Stored XSS in memory viewer from captured command/query text
- Why it happens in this domain: memory systems intentionally store raw developer text and render it back in HTML UIs.
- Early warning signs: use of `innerHTML` with memory-derived fields; viewer can execute pasted script-like payloads.
- Prevention strategy: render untrusted fields with `textContent`, sanitize any rich content pipeline, add regression tests with script payload fixtures.
- Which phase should address it first: Phase 1.

## 4) Capability mismatch: FTS/vector treated as optional but required at init/install
- Why it happens in this domain: fallback paths are added incrementally while schema and packaging still assume advanced SQLite features exist everywhere.
- Early warning signs: fresh install/init fails on machines lacking FTS5 or vector extensions; docs claim fallback but runtime exits early.
- Prevention strategy: capability probe before schema creation, dual-path schema/query logic, move advanced extensions to optional extras, test "minimal environment" explicitly.
- Which phase should address it first: Phase 2.

## 5) Per-request heavy initialization causes latency and lock contention
- Why it happens in this domain: server wrappers around CLI-era components often recreate storage/index sync logic per call.
- Early warning signs: p95 latency rises with QPS; request profiling shows repeated DB setup/sync work; intermittent SQLite busy/lock errors.
- Prevention strategy: long-lived storage objects per process/worker, move sync/rebuild tasks to indexing/migration stages, add lightweight health checks instead of full sync in hot path.
- Which phase should address it first: Phase 3.

## 6) Memory worker on user request path inflates tail latency
- Why it happens in this domain: memory capture is valuable, so teams run it inline to guarantee persistence, coupling UX to queue backlog.
- Early warning signs: slow responses correlate with memory queue depth; command/API latency spikes after heavy activity.
- Prevention strategy: background worker loop with bounded flush on request completion, explicit backpressure metrics, graceful degradation when queue is saturated.
- Which phase should address it first: Phase 3.

## 7) Incremental sync misses real file changes
- Why it happens in this domain: filesystem metadata (`mtime`, `size`) is fast but not always reliable for rapid rewrites/coarse timestamp filesystems.
- Early warning signs: edited file content not reflected in search results; "no changes" reported after rapid save operations.
- Prevention strategy: content hashing when metadata is ambiguous, optional inode/change-token tracking, targeted revalidation in watch mode for recent writes.
- Which phase should address it first: Phase 4.

## 8) Fallback semantic search degrades badly on larger repos
- Why it happens in this domain: when vector extensions are unavailable, Python cosine over many chunks becomes CPU-bound and blocks service threads.
- Early warning signs: high CPU during query bursts; query time scales roughly with corpus size; server responsiveness drops in fallback mode.
- Prevention strategy: lexical prefilter (FTS/BM25) before embedding scoring, strict candidate caps, telemetry by backend mode to detect degraded operation quickly.
- Which phase should address it first: Phase 4 (with guardrail tests in Phase 5).

## 9) Cross-surface contract drift (CLI vs HTTP vs MCP)
- Why it happens in this domain: three interfaces share core behavior but evolve with separate parameter parsing and response shaping.
- Early warning signs: same query yields different defaults/fields/errors across surfaces; docs and actual behavior diverge.
- Prevention strategy: shared contract layer for validation/serialization, golden compatibility tests across all interfaces, versioned API notes for breaking changes.
- Which phase should address it first: Phase 5 (after Phase 1 security controls stabilize external behavior).

## 10) Hardening changes regress core workflows without fast detection
- Why it happens in this domain: security/performance refactors touch central paths (`search`, `analysis`, `memory`) and can silently break edge cases.
- Early warning signs: post-change failures in watch sync, memory expansion, MCP tool calls, or fallback backend selection.
- Prevention strategy: expand tests for negative/security/degradation paths, add matrix runs for backend capability combinations, require smoke suite before phase completion.
- Which phase should address it first: Phase 5.
