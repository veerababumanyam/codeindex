# Roadmap: CodeIndex Sync

**Created:** 2026-03-14
**Source Requirements:** `.planning/REQUIREMENTS.md`
**Granularity:** coarse

## Phase Overview

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | Security and Policy Foundation | Make service and analysis flows safe by default | SEC-01, SEC-02, SEC-03, SEC-04 | 4 |
| 2 | Capability Resilience | Ensure optional feature availability does not break baseline behavior | CAP-01, CAP-02, CAP-03 | 4 |
| 3 | Request-Path Performance | Reduce latency contention and decouple background work | PERF-01, PERF-02, PERF-03 | 4 |
| 4 | Index and Retrieval Correctness | Improve sync reliability and fallback search quality | IDX-01, IDX-02, IDX-03 | 4 |
| 5 | Contract Parity and Regression Net | Lock down interface consistency and high-risk regression coverage | API-01, API-02, QA-01 | 4 |

## Phase Details

### Phase 1: Security and Policy Foundation
**Goal:** Eliminate known high-impact security risks in current local service and analysis surfaces.

**Requirements:** SEC-01, SEC-02, SEC-03, SEC-04

**Success criteria:**
1. Server defaults to loopback binding and documents explicit remote opt-in behavior.
2. Token-based protection is available and enforced for remote HTTP/MCP access.
3. Analysis requests outside allowed workspace/project roots are blocked with clear errors.
4. Memory viewer safely renders stored content without executable injection vectors.

**Status:** Complete on 2026-03-14

### Phase 2: Capability Resilience
**Goal:** Make fallback paths first-class so plain environments remain functional and predictable.

**Requirements:** CAP-01, CAP-02, CAP-03

**Success criteria:**
1. Baseline install/run succeeds without sqlite vector extensions.
2. Memory features run in a degraded but functional mode when FTS5 is absent.
3. Capability mode is visible to users through status/health output.
4. Capability-dependent behavior has tests for both accelerated and fallback modes.

### Phase 3: Request-Path Performance
**Goal:** Remove avoidable hot-path work and stabilize latency under concurrency.

**Requirements:** PERF-01, PERF-02, PERF-03

**Success criteria:**
1. Query request handling no longer performs expensive repeated setup/maintenance work.
2. Memory enrichment runs through a background worker path with bounded request impact.
3. Concurrency tests demonstrate reduced lock contention and improved tail latency stability.
4. Operational diagnostics expose queue/backlog and request-path performance signals.

### Phase 4: Index and Retrieval Correctness
**Goal:** Improve correctness and quality in edge cases without changing core architecture.

**Requirements:** IDX-01, IDX-02, IDX-03

**Success criteria:**
1. Rapid same-size file rewrites are detected and correctly reindexed.
2. Fallback retrieval mode scales better via candidate prefiltering.
3. Non-Python symbol extraction quality improves for at least one additional language.
4. Correctness and quality improvements are covered by deterministic tests.

### Phase 5: Contract Parity and Regression Net
**Goal:** Ensure consistent behavior across CLI/HTTP/MCP and protect hardened behavior over time.

**Requirements:** API-01, API-02, QA-01

**Success criteria:**
1. Equivalent operations across CLI/HTTP/MCP share aligned defaults and response semantics.
2. Compatibility tests catch cross-surface drift before release.
3. Security and fallback-path regression tests are part of the standard test suite.
4. Final milestone verification confirms 100% v1 requirement coverage.

## Requirement Coverage Validation

- Total v1 requirements: 16
- Covered by roadmap phases: 16
- Uncovered requirements: 0

Coverage is complete. Each v1 requirement maps to exactly one phase.

---
*Last updated: 2026-03-14 after Phase 1 execution and validation*
