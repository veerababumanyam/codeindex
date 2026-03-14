# MCP Tree-Sitter Feature Integration Plan

## Goal

Integrate high-value capabilities inspired by `wrale/mcp-server-tree-sitter` into CodeIndex Sync without copying the upstream application.

## Architecture

- Keep CodeIndex Sync as the single runtime and package.
- Add a dedicated analysis domain module: `codeindex/analysis.py`.
- Reuse the same config/project root/exclusion model already used by sync/query.
- Expose features on both existing interfaces:
  - CLI: `codeindex analyze <kind>`
  - HTTP server: `/analysis/*` endpoints
  - MCP JSON-RPC: `POST /mcp` with `tools/list` and `tools/call`

## Feature Mapping

- Upstream-style feature area: AST operations
  - Integrated feature: Python AST querying (`analyze ast`) and syntax validation (`analyze validate`)
- Upstream-style feature area: project and symbol navigation
  - Integrated feature: project file listing, file symbol extraction, project stats
- Upstream-style feature area: code intelligence analysis
  - Integrated feature: dependency analysis, complexity analysis, symbol usage lookup
- Upstream-style feature area: unified server tooling
  - Integrated feature: all analysis operations available through `codeindex serve`

## Design Decisions

- Additive integration only: search/index behavior remains stable.
- Parser strategy:
  - Python: `ast` for structured AST/dependency/complexity operations.
  - Other languages: optional Tree-sitter parser usage when available.
  - JS/TS: regex fallback extraction for dependency analysis.
  - Other text files fallback: lightweight bracket-balance validation and usage scanning.
- API shape:
  - JSON-first payloads, matching existing CLI/server response style.
- Performance:
  - Respect existing `excludes` patterns.
  - Bounded list results (`--limit`, query `limit`) to control response size.

## Implementation Plan

1. Add analysis module with reusable functions.
2. Add CLI command surface for all analysis operations.
3. Extend HTTP server with `/analysis/*` routes backed by the same functions.
4. Add tests for new CLI and server behavior.
5. Update README with architecture and usage examples.

## Status

Implemented in this repository.
