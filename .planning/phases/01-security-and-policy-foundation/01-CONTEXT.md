# Phase 1: Security and Policy Foundation - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase makes the existing HTTP, MCP, analysis, and memory viewer surfaces safe by default without changing the product's local-first nature. It covers remote exposure policy, optional auth behavior, server-side path boundaries, and safe rendering for memory-derived text.

</domain>

<decisions>
## Implementation Decisions

### Remote Access Policy
- Server should remain loopback-only by default.
- Remote exposure should require a dedicated explicit opt-in flag in addition to a non-loopback host value.
- If a user passes a remote host without the explicit opt-in flag, startup should fail clearly rather than warn or silently coerce behavior.
- The remote-exposure rule should apply uniformly across all HTTP and MCP surfaces.

### Optional API Auth
- API token auth is not mandatory by default because the tool is local-first and commonly used in local Docker, venv, or app-development environments.
- When enabled, token auth should apply uniformly across HTTP and MCP endpoints rather than protecting only one surface.
- Token transport should use a request header rather than query parameters.
- If auth is configured and the token is missing or invalid, the server should return a clear `401` response.

### Server Path Boundaries
- HTTP and MCP analysis should stay inside the configured project root only.
- Server-side analysis should not accept arbitrary caller-supplied root overrides.
- Requests for paths outside the allowed boundary should be rejected with a clear error.
- This strict boundary is required for server surfaces; local CLI behavior can remain more flexible.

### Viewer Safety
- Memory-derived viewer content should render as plain escaped text rather than trusting inline HTML.
- Simplicity and predictable safety matter more than rich formatting in this phase.
- The same safe-text rule should apply to both the HTML viewer and the live event stream presentation.

### Claude's Discretion
- Exact CLI/config naming for remote opt-in and auth flags can follow existing command/config conventions.
- Exact header name for token auth can follow common patterns as long as HTTP and MCP use the same mechanism.
- Error message wording can be implementation-driven as long as boundary and auth failures are explicit.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `codeindex/server.py`: centralizes HTTP route handling, MCP dispatch, and current root resolution behavior.
- `codeindex/analysis.py`: provides the file/path resolution helpers that boundary checks should constrain for server use.
- `codeindex/memory_viewer.py`: contains the current `innerHTML` rendering path that should be replaced with safe text rendering.
- `codeindex/config.py`: likely home for any new config-backed flags or defaults.

### Established Patterns
- The codebase favors boundary-layer validation in CLI/server modules with domain logic delegated to service modules.
- Runtime behavior is local-first with lightweight stdlib HTTP serving and explicit configuration defaults.
- Error handling already prefers clear `ValueError`-style validation translated at interface boundaries.

### Integration Points
- Remote access policy should integrate with server startup and request handling in `codeindex/server.py`.
- Optional token checks should live near HTTP/MCP boundary handling so they apply uniformly before route logic.
- Path boundary enforcement should apply before analysis operations call into `codeindex/analysis.py`.
- Viewer rendering changes should be isolated to `codeindex/memory_viewer.py` and any related stream payload presentation.

</code_context>

<specifics>
## Specific Ideas

- Local-first convenience should remain the default experience.
- Users may run the app in Docker or a virtual environment and connect it to local app-development workflows.
- Security hardening should avoid making normal local development cumbersome.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 01-security-and-policy-foundation*
*Context gathered: 2026-03-14*
