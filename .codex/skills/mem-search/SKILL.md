---
name: "mem-search"
description: "Search built-in persistent memory with progressive disclosure and stable citations"
metadata:
  short-description: "Query CodeIndex memory before expanding full observations"
---

## When to use

Use this skill when you need project history, prior observations, earlier command outcomes, or cited context from persistent memory.

## Workflow

1. Start with summary-layer retrieval through the built-in memory surface.
2. Inspect token-cost metadata before expanding results.
3. Expand only the observation IDs that materially help answer the task.
4. Cite prior observations by stable `obs_...` or `cit_...` IDs.

## Preferred interfaces

- CLI:
  - `python -m codeindex.cli --config codeindex.yaml memory search "<query>" --layer summary`
  - `python -m codeindex.cli --config codeindex.yaml memory expand <observation_id>`
- MCP:
  - `codeindex_memory_search`
  - `codeindex_memory_expand`

## Rules

- Do not reimplement ranking or disclosure logic in the skill.
- Treat the app's summary layer as the default.
- Prefer citation IDs in final references when available.
- Expand the fewest observations necessary.
