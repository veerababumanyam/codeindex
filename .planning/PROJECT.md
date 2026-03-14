# CodeIndex Sync

## What This Is

CodeIndex Sync is a local-first developer tool that indexes source code into SQLite and exposes semantic search, code analysis, and persistent project memory. It supports CLI, HTTP, and MCP interfaces so both humans and agents can query the same indexed knowledge. The project is for developers and agentic workflows that need fast, low-token retrieval and explainable code intelligence without depending on external embedding services.

## Core Value

Developers can reliably find relevant code context fast, locally, and with predictable costs.

## Requirements

### Validated

- ✓ Local workspace indexing into SQLite with incremental sync and deletion handling — existing (`codeindex/indexer.py`, `codeindex/storage.py`)
- ✓ Semantic retrieval across chunks/symbols/hybrid with token-aware output — existing (`codeindex/search.py`, `codeindex/cli.py`)
- ✓ Integrated code analysis commands and endpoints (symbols, AST, dependencies, complexity, usage, stats) — existing (`codeindex/analysis.py`, `codeindex/server.py`)
- ✓ Persistent memory sessions, observations, citations, and search/expand flows — existing (`codeindex/memory_service.py`, `codeindex/memory_storage.py`)
- ✓ CLI + HTTP + MCP tool surfaces over shared core services — existing (`codeindex/cli.py`, `codeindex/server.py`)

### Active

- [ ] Improve reliability and test coverage around edge-case indexing and memory workflows
- [ ] Tighten API/CLI contract consistency and documentation for MCP and memory endpoints
- [ ] Prioritize and execute highest-impact technical debt from `.planning/codebase/CONCERNS.md`

### Out of Scope

- Hosted multi-tenant SaaS deployment — project is local-first and single-workspace oriented
- Real-time collaborative editing features — not required for core retrieval and analysis value

## Context

This repository already implements the core system and has a recently refreshed codebase map in `.planning/codebase/`. The architecture is a Python modular monolith with shared SQLite persistence and optional vector backends (`sqlite-vec`, `sqlite-vss`) plus deterministic local embedding fallback. Tests exist (`tests/test_cli.py`, `tests/test_server.py`) and documentation is strong (`README.md`), but concern mapping highlights opportunities in reliability hardening, consistency checks, and debt reduction.

## Constraints

- **Tech Stack**: Python + SQLite-first implementation — preserve local-first operation and offline-friendly defaults
- **Interface Compatibility**: CLI, HTTP, and MCP behavior should remain aligned — avoid regressions across surfaces
- **Operational Simplicity**: Keep setup lightweight (`pip install -e .`) — avoid unnecessary infrastructure dependencies
- **Data Integrity**: Index and memory data live in local SQLite — schema and migration safety are required

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Treat repository as brownfield and initialize from existing capabilities | Core functionality already exists and is documented/mapped | ✓ Good |
| Default workflow to execution-first planning (YOLO + coarse phases) | User asked to proceed autonomously with momentum | — Pending |
| Keep planning docs tracked in git | Preserve project memory and traceable decisions | ✓ Good |

---
*Last updated: 2026-03-14 after initialization*
