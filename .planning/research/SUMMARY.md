# Research Summary: CodeIndex

**Date:** 2026-03-14
**Project Context:** Brownfield hardening milestone for local-first semantic code indexing/search/analysis/memory tool.

## Recommended Stack Direction
- Keep the Python + SQLite modular monolith architecture for this milestone.
- Treat vector accelerators as optional enhancements, not install requirements.
- Prioritize secure-by-default service behavior and capability-based runtime fallbacks.
- Avoid major framework migrations (ASGI stack, external DB/queue) until hardening goals are complete.

## Table-Stakes to Protect
- Reliable incremental indexing and watch-mode correctness.
- Predictable retrieval quality and latency across available backend modes.
- Contract parity across CLI, HTTP, and MCP interfaces.
- Safe default service posture (loopback binding, path constraints, optional auth for remote use).
- Durable local persistence and graceful degradation in no-FTS/no-vector environments.

## Key Architecture Guidance
- Introduce a shared policy layer (path constraints, binding/auth policy, output sanitization).
- Move capability probing to startup and reuse a capability registry in request handling.
- Keep heavy work off request paths (no per-request setup/sync; background memory worker).
- Strengthen retrieval and sync correctness with targeted fallback/guard strategies.

## Critical Pitfalls to Address Early
1. File exposure via unsafe analysis root/path handling.
2. Unauthenticated HTTP/MCP access when bound remotely.
3. Stored XSS risk in memory viewer rendering.
4. Runtime fallback mismatch (optional features treated as required).
5. Request-path latency/lock contention from heavy initialization.

## Scope Guidance for Next Milestone
- Phase order should be: security foundation -> capability resilience -> request-path performance -> indexing/retrieval quality -> regression safety net.
- v1 should focus on risk reduction and operational trust, not feature-surface expansion.
- Maintain CLI/HTTP/MCP parity as a release gate for all core workflow changes.

## Confidence Summary
- Security hardening in current stack: High.
- Optional capability packaging/runtime path alignment: High.
- Performance and fallback tuning without architecture migration: Medium-High.
- Deferring major platform migrations this milestone: High.

---
*Last updated: 2026-03-14 after research synthesis*
