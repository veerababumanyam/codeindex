---
phase: 01
plan_id: 01-PLAN
title: Remote Exposure and Unified Access Control
wave: 1
depends_on: []
files_modified:
  - codeindex/cli.py
  - codeindex/config.py
  - codeindex/server.py
  - README.md
  - docs/codeindex.example.yaml
  - tests/test_cli.py
  - tests/test_server.py
autonomous: true
requirements:
  - SEC-01
  - SEC-02
---

# Phase 1 Plan 01: Remote Exposure and Unified Access Control

<goal>
Deliver safe-by-default server startup and optional token enforcement across HTTP and MCP surfaces without degrading loopback-first local workflows.
</goal>

<must_haves>
- Loopback remains the default bind behavior for server entrypoints.
- Non-loopback binding fails clearly unless an explicit remote opt-in is present.
- One token-based auth mechanism applies uniformly to HTTP and MCP routes.
- Auth remains optional; when no token is configured, local workflows keep working.
- Config and CLI flags are aligned so operators can intentionally enable remote access and auth.
</must_haves>

<scope>
- Add or validate server security config in `codeindex/config.py`.
- Add CLI/config plumbing for remote exposure opt-in and token settings.
- Enforce host exposure policy during startup in `codeindex/server.py`.
- Add a shared request auth gate for HTTP and MCP handling in `codeindex/server.py`.
- Document the remote opt-in behavior in user-facing docs and sample config.
- Add focused tests for startup policy, auth rejection, and auth success paths.
</scope>

<tasks>
  <task id="1-01-01" requirement="SEC-01">
    <objective>Define explicit remote exposure configuration and CLI inputs.</objective>
    <implementation>
      - Add a validated `server` configuration surface with loopback-safe defaults for host/port plus remote opt-in and token-related settings.
      - Extend server-facing CLI entrypoints so remote exposure can only be enabled intentionally.
      - Preserve existing loopback local workflows when no new options are supplied.
    </implementation>
    <files>codeindex/config.py, codeindex/cli.py, tests/test_cli.py</files>
    <verification>
      - `pytest tests/test_cli.py -q`
      - Config validation covers accepted defaults and invalid server security values.
    </verification>
  </task>

  <task id="1-01-02" requirement="SEC-01">
    <objective>Reject unsafe remote binds unless the operator explicitly opts in.</objective>
    <implementation>
      - Add a startup-time host policy helper in `codeindex/server.py`.
      - Treat only loopback hosts as safe by default.
      - Raise a clear validation error when a non-loopback host is requested without the explicit opt-in flag/config.
      - Apply the same policy path to all server surfaces created through the shared serve flow.
    </implementation>
    <files>codeindex/server.py, tests/test_server.py</files>
    <verification>
      - `pytest tests/test_server.py -q -k remote`
      - Include one failure case for `0.0.0.0` without opt-in and one success case with opt-in.
    </verification>
  </task>

  <task id="1-01-03" requirement="SEC-02">
    <objective>Require a configured API token for remote HTTP and MCP requests.</objective>
    <implementation>
      - Add a shared auth check near request dispatch in `codeindex/server.py`.
      - Use a header-based token comparison only; do not accept query-parameter auth.
      - Apply the check consistently to HTTP JSON routes, memory routes, and `/mcp`.
      - Return explicit `401` responses for missing or invalid credentials.
    </implementation>
    <files>codeindex/server.py, tests/test_server.py</files>
    <verification>
      - `pytest tests/test_server.py -q -k auth`
      - Cover unauthenticated rejection and authenticated success for both a standard HTTP route and `/mcp`.
    </verification>
  </task>

  <task id="1-01-04" requirement="SEC-01">
    <objective>Document how remote exposure is intentionally enabled.</objective>
    <implementation>
      - Update `README.md` to describe loopback-default serving, explicit remote opt-in, and optional token usage.
      - Update `docs/codeindex.example.yaml` to show the new server config shape and safe defaults.
      - Keep the documentation aligned with the CLI/config names chosen during implementation.
    </implementation>
    <files>README.md, docs/codeindex.example.yaml</files>
    <verification>
      - `pytest tests/test_cli.py -q`
      - Documentation and sample config reflect the implemented remote-access behavior and defaults.
    </verification>
  </task>
</tasks>

<execution_order>
- Complete config and CLI plumbing before startup/auth enforcement.
- Land remote bind enforcement before token tests that rely on deterministic startup behavior.
- Keep auth handling centralized in the server boundary layer rather than duplicating checks per endpoint.
</execution_order>

<acceptance_criteria>
- Starting the server with default settings binds to loopback successfully with no extra flags.
- Starting the server with a non-loopback host and no explicit remote opt-in fails before the server begins serving.
- When a token is configured, requests without the configured header receive `401`.
- When the correct header is supplied, protected HTTP routes, memory routes, and MCP operations succeed.
- Remote opt-in behavior is documented in the README and sample configuration.
- Existing loopback tests continue to work when auth is not configured.
</acceptance_criteria>

<handoff>
This plan produces the security controls that all later server-surface work assumes. Path-boundary enforcement and viewer hardening are handled in a separate Phase 1 plan and should be executed in the same wave once server startup/auth coverage is in place.
</handoff>
