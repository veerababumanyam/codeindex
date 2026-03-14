---
phase: 02
plan: 01
title: Optional Capability Fallbacks and Visible Runtime Modes
status: complete
requirements:
  - CAP-01
  - CAP-02
  - CAP-03
key_files:
  - pyproject.toml
  - codeindex/storage.py
  - codeindex/memory_storage.py
  - codeindex/memory_service.py
  - codeindex/cli.py
  - codeindex/search.py
  - tests/test_memory_storage.py
  - tests/test_cli.py
  - tests/test_server.py
completed: 2026-03-14
---

# Phase 02 Plan 01 Summary

Optional SQLite accelerators are now off the default install path, degraded memory mode works without FTS5, and capability reporting is explicit across CLI, HTTP, and MCP surfaces.

## What Changed

- Moved `sqlite-vec` and `sqlite-vss` from required dependencies into an optional `vectors` extra and constrained setuptools package discovery to `codeindex*` so editable installs succeed in this workspace.
- Added centralized vector capability reporting in `codeindex/storage.py` and surfaced it through CLI query metrics and `status` output.
- Split memory storage schema into required tables plus conditional FTS setup, guarded FTS maintenance writes, and added deterministic SQL-like fallback search for no-FTS environments.
- Removed stale global memory capability caching and made memory capability reporting recompute deterministically per service instance.
- Added focused no-FTS storage tests plus CLI/server degraded-mode regression coverage using runtime capability disable flags for subprocess verification.

## Decisions Made

- Kept the existing runtime vector fallback order and made packaging match it instead of redesigning retrieval.
- Treated no-FTS mode as degraded-but-functional rather than disabling memory search outright.
- Used additive machine-readable capability fields so later contract-parity work can build on stable payloads.

## Verification

- `python -m pytest tests/test_memory_storage.py tests/test_cli.py tests/test_server.py -q -k "status or memory or query or fts or vector"`
- `python -m pytest -q`
- `python -m pip install -e .`

## Deviations from Plan

- Added setuptools package discovery constraints in `pyproject.toml` after install verification exposed a workspace-layout packaging failure unrelated to the vector fallback logic.

## Self-Check: PASSED

- Verified editable install succeeds after the packaging changes.
- Verified focused capability tests and the full test suite pass on the final tree.
