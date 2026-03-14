# Stack Evolution Research (Next Milestone)

## Goal
Evolve CodeIndex Sync’s stack for security, reliability, and predictable local performance without breaking the local-first/SQLite-first model.

## Recommended Stack/Dependency Strategy
- Keep Python modular monolith + SQLite as the core architecture for this milestone.
- Shift from "extensions-required" to "capability-optional" packaging:
  - Base install should run with pure-Python fallback paths.
  - Native SQLite/vector accelerators should be extras, not mandatory.
- Keep HTTP + MCP in-process, but harden exposure defaults and request-path behavior.
- Prioritize dependency changes that directly reduce current P0/P1 risks from `.planning/codebase/CONCERNS.md`.

## Specific Libraries/Tools

### Runtime and Packaging
- Python: `>=3.10,<3.13` (keep current floor; avoid broad runtime jump this milestone).
- Packaging backend: keep `setuptools` now.
- Core runtime deps:
  - `PyYAML>=6.0,<7`
- Vector/search extras (optional):
  - `sqlite-vec>=0.1.6,<0.2` (preferred accelerator)
  - `sqlite-vss>=0.1.2,<0.2` (legacy fallback only)
- Analysis extras:
  - `tree-sitter-languages>=1.10.2,<2`

### Reliability/Security Adjacent (low-friction additions)
- Auth token hashing/compare: stdlib `hmac`/`hashlib` (no extra dep needed).
- HTML sanitization for memory viewer: prefer no dependency and switch rendering to safe DOM text APIs; avoid sanitizer libs this milestone.

### Dev/Test Tooling
- `pytest>=8,<9`
- `pytest-xdist>=3.6,<4` (optional, for concurrency/perf regression checks)
- `httpx>=0.27,<0.29` (if adding cleaner API/integration-style tests)

## Rationale
- Optional native vector deps align packaging with existing runtime fallback design and reduce install failures.
- Keeping SQLite-first and stdlib server preserves operational simplicity and offline behavior.
- Avoiding framework migrations (FastAPI/ASGI, Postgres, Redis, external queues) keeps focus on high-impact hardening and correctness.
- tree-sitter remains the best incremental path to improve symbol quality across languages without changing system architecture.

## What Not To Adopt Now
- FastAPI/Starlette/uvicorn migration.
- External DB (Postgres) or message broker (Redis/RabbitMQ).
- External embedding providers as default path.
- Heavy observability stack (OpenTelemetry collector, Prometheus exporters) beyond lightweight logging/metrics improvements.
- Full-text engine replacement (Elasticsearch/OpenSearch).

## Confidence
- Optionalizing vector deps: **High** (directly supported by current fallback behavior).
- Security hardening with current stack: **High** (mostly code-path constraints/defaults).
- FTS fallback restructuring: **Medium** (requires careful schema/runtime branching).
- Major framework migration deferral: **High** (best cost/benefit for this milestone).

## Migration / Adoption Order
1. Packaging first:
- Move `sqlite-vec` and `sqlite-vss` from required deps to extras.
- Keep default install minimal and fully functional (python-cosine fallback).

2. Security defaults:
- Restrict analysis root override and enforce project-root boundaries.
- Add explicit remote-host opt-in + API token support for HTTP/MCP.
- Escape/safe-render memory viewer fields.

3. Reliability fallback paths:
- Make FTS5 truly optional at schema/runtime level.
- Add capability checks surfaced in `status`/health outputs.

4. Request-path performance:
- Remove per-request heavy initialization/sync work.
- Decouple memory worker from synchronous request completion.

5. Quality and test expansion:
- Strengthen non-Python symbol extraction path (tree-sitter where available).
- Add regression tests for security boundaries, no-FTS/no-vector envs, and concurrent latency behavior.

## Milestone Outcome Target
By milestone end, a fresh `pip install -e .` on a plain Python+SQLite environment should work reliably, secure defaults should protect local data exposure, and acceleration features should remain opt-in enhancements rather than install blockers.
