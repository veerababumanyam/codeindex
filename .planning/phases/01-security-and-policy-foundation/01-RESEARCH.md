# Phase 1 Research: Security and Policy Foundation

## Objective and Scope

Phase 1 should deliver the four security requirements in `.planning/REQUIREMENTS.md` without changing the local-first UX for CLI workflows:
- `SEC-01`: keep HTTP/MCP loopback-only by default and require explicit remote opt-in.
- `SEC-02`: add optional token auth that applies uniformly to HTTP and MCP surfaces.
- `SEC-03`: constrain server-side analysis to the configured project root.
- `SEC-04`: render memory-derived viewer content as plain text.

Out of scope for this phase:
- changing CLI-local `analyze --root` flexibility
- performance work around per-request `Storage(...)`
- packaging/runtime capability fixes in `pyproject.toml`

## Existing Code Touchpoints

- `codeindex/server.py`
  - `serve()` currently binds any requested host with no policy check.
  - `do_GET()` and `do_POST()` expose `/search`, `/analysis/*`, `/memory/*`, `/memory/viewer`, `/memory/stream`, and `/mcp` with no auth layer.
  - `_analysis_payload()` trusts `root` from request params/MCP arguments and resolves it directly.
- `codeindex/analysis.py`
  - `_resolve_file()` validates existence only; it does not verify that the resolved file stays under an allowed root.
  - `iter_text_files()` and all analysis entrypoints assume the supplied root is already trusted.
- `codeindex/memory_viewer.py`
  - `renderCard()` builds DOM with `innerHTML` from memory-derived `title`, `summary`, and `snippet`.
  - `render_viewer_page()` already escapes the workspace label server-side with `html.escape`.
- `codeindex/cli.py`
  - `cmd_serve()` and `cmd_memory_viewer()` pass host/port through directly.
  - CLI parser currently has no `--allow-remote` or auth-related server options.
  - CLI `analyze` uses `--root`; this should remain local-only.
- `codeindex/config.py`
  - no server policy/auth config exists yet; validation will need new config keys.
- `tests/test_server.py`
  - has happy-path coverage for HTTP, MCP, and memory routes, but no negative security tests.
- `tests/test_cli.py`
  - has config validation patterns that can be copied for new server config validation.
- `pyproject.toml`
  - no phase-specific dependency changes appear necessary; Phase 1 can stay stdlib-only.

## Recommended Implementation Approach

### 1. Add explicit server security config

Add a new top-level `server` config block in `codeindex/config.py`, validated similarly to `query` and `analysis`:
- `host`: default `127.0.0.1`
- `port`: default `9090`
- `allow_remote`: default `False`
- `api_token`: default empty string or `None`
- `auth_header`: default `X-CodeIndex-Token`

Keep `memory.viewer` host/port as-is for now unless the planner wants one shared server block for both `serve` and `memory viewer`. The lower-risk approach is to use the same enforcement helper in both commands even if config keys remain split.

### 2. Enforce remote exposure at startup, not per request

In `codeindex/server.py`, add a small startup validator used by `serve()`:
- resolve whether `host` is loopback (`127.0.0.1`, `localhost`, `::1`)
- if non-loopback and `allow_remote` is false, raise `ValueError` with a clear message
- apply this uniformly for the main server and memory viewer server because both call `serve()`

In `codeindex/cli.py`:
- add `--allow-remote` to `serve`
- either add the same flag to `memory viewer` or have that command inherit config-only behavior
- prefer CLI flag override over config to preserve explicit operator intent

This matches the phase decision to fail clearly rather than warn or silently coerce.

### 3. Add one shared auth gate for HTTP and MCP

In `SearchHandler`, add a helper that runs before route logic in both `do_GET()` and `do_POST()`:
- read configured token from `config_data["server"]`
- if no token is configured, allow request
- otherwise require the configured header to equal the configured token
- on failure, return `401` JSON for JSON endpoints and a simple `401` error for other responses

Recommended detail:
- exempt neither `/mcp` nor `/memory/*`; the context explicitly requires uniform coverage
- avoid query-param tokens entirely
- keep the implementation in `server.py` rather than pushing auth into `MemoryService` or analysis code

### 4. Remove caller-controlled analysis roots on server surfaces

Server surfaces should use exactly one canonical root: `self.default_root.resolve()`.

Implementation shape:
- in `server.py`, remove `root` from effective HTTP/MCP analysis handling
- optionally keep `root` in MCP schema temporarily for compatibility, but ignore it server-side and document that behavior; stricter alternative is to reject any supplied `root` with `400`
- `_analysis_payload()` should derive `root` from `self.default_root` only
- for file-scoped operations, validate `path` as a relative path and reject absolute paths

Defense in depth in `analysis.py`:
- harden `_resolve_file()` to reject resolved targets outside `root` using canonical path comparison
- use the same root-boundary helper for any future server-side file operations

This preserves local CLI override behavior in `codeindex/cli.py` while making HTTP/MCP safe by default.

### 5. Replace viewer HTML injection with explicit text nodes

In `codeindex/memory_viewer.py`, change client rendering so user-derived fields are assigned via `textContent` on created elements instead of interpolated into `innerHTML`.

Practical shape:
- create `<strong>`, metadata `<div>`, and body `<div>` nodes individually
- set `textContent` for `title`, `kind`, `observation_id`, `created_at`, `citation_id`, `summary`, and `snippet`
- keep existing layout/CSS unchanged

This should cover both `/memory/viewer` search results and `/memory/stream` event presentation because both reuse `renderCard()`.

## Risks and Sequencing

Recommended sequence:
1. Config + CLI surface for remote policy and auth.
2. `serve()` startup validation for remote exposure.
3. Shared request auth helper in `server.py`.
4. Server analysis root hardening in `server.py`, then defense-in-depth in `analysis.py`.
5. Viewer rendering fix in `memory_viewer.py`.
6. Add negative tests before any cleanup/refactor.

Key risks:
- Existing tests start servers with explicit `--host 127.0.0.1`; those should continue to pass, but startup messaging may change.
- Adding required auth to all routes can break current tests unless helpers add the header conditionally.
- Rejecting `root` outright in MCP/HTTP is safest, but may be a contract change; ignoring `root` is the lower-friction path if compatibility matters.
- `Path.is_relative_to()` is Python 3.9+, so it is safe under the current `>=3.10` requirement in `pyproject.toml`.

## Test Strategy

Primary additions belong in `tests/test_server.py`:
- startup fails when server is launched on `0.0.0.0` without explicit remote opt-in
- startup succeeds on `0.0.0.0` with explicit remote opt-in
- HTTP endpoint returns `401` when token auth is configured and header is missing
- HTTP endpoint succeeds when the correct auth header is supplied
- MCP `/mcp` returns auth failure without token and succeeds with token
- `/analysis/*` ignores or rejects supplied `root` overrides outside the configured project
- absolute `path` / traversal attempts fail with `400`
- viewer output does not execute or embed raw attacker HTML from memory records; assert escaped text is present and raw dangerous markup is absent from rendered DOM payload where practical

Supporting additions in `tests/test_cli.py`:
- config validation accepts the new `server` block defaults/overrides
- malformed `server.allow_remote`, `server.host`, `server.port`, `server.auth_header`, or `server.api_token` values fail fast

Implementation note for tests:
- add request helpers that can send optional headers for both `urllib.request.urlopen` GET and JSON POST so auth coverage stays concise
- keep viewer-safety tests deterministic by inserting a known memory record containing `<script>` or `<img onerror>`-style text and asserting it is rendered as text, not markup

## Validation Architecture

A later `VALIDATION.md` should verify each requirement with explicit evidence paths.

### Requirement Mapping

- `SEC-01`
  - Validate startup behavior for loopback default, remote bind rejection without opt-in, and remote bind acceptance with opt-in.
  - Evidence: server CLI tests and startup error messages.
- `SEC-02`
  - Validate one auth mechanism protects `/search`, `/analysis/*`, `/memory/*`, and `/mcp`.
  - Evidence: HTTP GET and MCP POST tests with missing, invalid, and valid headers.
- `SEC-03`
  - Validate analysis cannot escape the configured root via `root`, absolute paths, or traversal sequences.
  - Evidence: negative tests against `/analysis/symbols`, `/analysis/dependencies`, `/analysis/validate`, and MCP `codeindex_analyze`.
- `SEC-04`
  - Validate memory viewer treats untrusted fields as literal text in both search results and stream-fed cards.
  - Evidence: viewer rendering test plus direct inspection of generated HTML/JS behavior.

### Test Layers

- Unit-level
  - config validation for new `server` keys
  - path-boundary helper in `analysis.py`
  - host-policy helper in `server.py`
- Integration-level
  - live server process tests for HTTP/MCP auth and remote-bind policy
  - analysis boundary tests through real endpoints
  - memory viewer rendering test through `/memory/viewer` and `/memory/stream`
- Regression-level
  - existing happy-path server tests still pass on loopback without auth configured
  - existing CLI `analyze --root` behavior remains unchanged

### Suggested Validation Cases

- `V1`: `serve --host 127.0.0.1` works with no extra flags.
- `V2`: `serve --host 0.0.0.0` fails unless `--allow-remote` or config opt-in is set.
- `V3`: token-configured server rejects unauthenticated `/search` and `/mcp` requests with `401`.
- `V4`: authenticated `/search`, `/memory/status`, and MCP tool calls succeed with the configured header.
- `V5`: `/analysis/*?root=<outside>` cannot read files outside project root.
- `V6`: `/analysis/*?path=../secret.py` and absolute-path inputs fail clearly.
- `V7`: memory viewer renders `<script>alert(1)</script>` as text content, not executable markup.

### Evidence Expectations

Validation output should capture:
- exact commands used to start the server
- exact request forms including auth headers
- status codes and key response bodies for rejection paths
- file/route references for the enforcement points
- confirmation that no dependency changes were needed for this phase
