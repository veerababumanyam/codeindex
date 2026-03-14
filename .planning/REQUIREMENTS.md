# Requirements: CodeIndex Sync

**Defined:** 2026-03-14
**Core Value:** Developers can reliably find relevant code context fast, locally, and with predictable costs.

## v1 Requirements

### Security and Policy

- [x] **SEC-01**: HTTP server binds to loopback by default and requires explicit opt-in for remote exposure.
- [x] **SEC-02**: Remote HTTP/MCP access can be protected with an API token check.
- [x] **SEC-03**: Analysis file access is constrained to canonical workspace/project boundaries.
- [x] **SEC-04**: Memory viewer renders untrusted content safely without script execution.

### Runtime Capability and Packaging

- [ ] **CAP-01**: Fresh install works without sqlite vector extensions and still supports functional query fallback.
- [ ] **CAP-02**: Memory subsystem degrades gracefully when FTS5 is unavailable.
- [ ] **CAP-03**: Runtime exposes active capability mode (vector/fts/fallback) in status outputs.

### Performance and Concurrency

- [ ] **PERF-01**: Query request path avoids per-request heavy storage initialization and vector maintenance work.
- [ ] **PERF-02**: Memory processing is decoupled from synchronous request completion via a background worker loop.
- [ ] **PERF-03**: Under concurrent usage, p95 latency remains stable relative to current baseline and avoids SQLite lock spikes.

### Index and Retrieval Correctness

- [ ] **IDX-01**: Incremental sync detects rapid same-size rewrites and reindexes changed files reliably.
- [ ] **IDX-02**: Fallback retrieval path uses candidate prefiltering to reduce corpus-scale latency degradation.
- [ ] **IDX-03**: Non-Python symbol extraction quality improves for at least one additional major language path.

### Interface Contract and Regression Safety

- [ ] **API-01**: CLI, HTTP, and MCP use aligned parameter/default semantics for equivalent operations.
- [ ] **API-02**: Core workflows have compatibility tests that assert equivalent output contracts across surfaces.
- [ ] **QA-01**: Regression tests cover security controls, no-FTS/no-vector fallback paths, and high-risk memory flows.

## v2 Requirements

### Enhancements

- **RERK-01**: Optional advanced reranking configuration for retrieval quality tuning.
- **OBS-01**: Extended operational telemetry and exportable metrics integration.
- **LANG-01**: Broader parser/symbol support across additional non-Python languages.
- **UX-01**: Richer local diagnostics UI beyond essential memory/status views.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-tenant cloud SaaS | Conflicts with local-first focus for current roadmap |
| Real-time collaboration features | Not needed to deliver core retrieval value |
| Mandatory external embedding provider | Violates offline/predictable-cost value proposition |
| Full framework migration (e.g., ASGI stack) | High churn with low near-term risk reduction return |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEC-01 | Phase 1 | Complete |
| SEC-02 | Phase 1 | Complete |
| SEC-03 | Phase 1 | Complete |
| SEC-04 | Phase 1 | Complete |
| CAP-01 | Phase 2 | Pending |
| CAP-02 | Phase 2 | Pending |
| CAP-03 | Phase 2 | Pending |
| PERF-01 | Phase 3 | Pending |
| PERF-02 | Phase 3 | Pending |
| PERF-03 | Phase 3 | Pending |
| IDX-01 | Phase 4 | Pending |
| IDX-02 | Phase 4 | Pending |
| IDX-03 | Phase 4 | Pending |
| API-01 | Phase 5 | Pending |
| API-02 | Phase 5 | Pending |
| QA-01 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0

---
*Requirements defined: 2026-03-14*
*Last updated: 2026-03-14 after Phase 1 execution and validation*
