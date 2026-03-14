---
phase: 01
plan: 01
title: Remote Exposure and Unified Access Control
status: complete
requirements:
  - SEC-01
  - SEC-02
key_files:
  - codeindex/config.py
  - codeindex/cli.py
  - codeindex/server.py
  - tests/test_cli.py
  - tests/test_server.py
completed: 2026-03-14
---

# Phase 01 Plan 01 Summary

Loopback-only serving is now the default, non-loopback binds require explicit opt-in, and one header-based token gate protects HTTP and MCP routes when configured.

## What Changed

- Added `server.host`, `server.port`, `server.allow_remote`, `server.auth_token`, and `server.auth_token_header` to config validation and defaults.
- Updated `codeindex serve` to honor config-backed server settings and expose explicit `--allow-remote` and `--auth-token` overrides.
- Hardened `serve()` startup to reject non-loopback hosts unless remote access is intentionally enabled.
- Added one shared auth check for `/search`, `/analysis/*`, `/memory/*`, and `/mcp`.
- Documented remote opt-in and token header usage in the README and sample config.
- Added CLI and server tests for config validation, remote bind rejection, remote bind success, and auth enforcement.

## Decisions Made

- Kept authentication optional so existing loopback local workflows continue to work without extra setup.
- Standardized on a header-only token check via `X-CodeIndex-Token` by default.
- Enforced remote bind policy centrally in `serve()` so HTTP and memory viewer surfaces share the same safety rule.

## Verification

- `python -m pytest tests/test_cli.py -q`
- `python -m pytest tests/test_server.py -q -k "remote or auth"`

## Deviations from Plan

None.

## Self-Check: PASSED

- Verified key files exist on disk.
- Verified targeted CLI and server tests passed after implementation.
