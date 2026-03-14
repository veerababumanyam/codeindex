# Proposed Improvements for CodeSync

This document outlines architectural recommendations and feature enhancements for the CodeSync (CodeIndex) project based on a comprehensive review of the v0.0.3 codebase.

## 1. Advanced Semantic Retrieval
Currently, the system uses a 64-dimensional hashing-based embedding (`embedding.py`). While efficient and dependency-free, it lacks true semantic understanding.
- **Proposal**: Introduce an optional "Advanced Mode" using a local transformer model (e.g., `all-MiniLM-L6-v2` via `fastembed`).
- **Benefit**: Significantly improves search quality for conceptual queries that do not share exact keywords.

## 2. Unified Symbol Extraction
`analysis.py` already supports Tree-sitter, but the primary indexing pass in `indexer.py` still uses regex for several languages.
- **Proposal**: Standardize the entire indexing pipeline on Tree-sitter.
- **Benefit**: More robust symbol extraction, better handling of complex syntax, and consistent behavior across all supported languages.

## 3. Knowledge Distillation in Memory
The memory subsystem currently acts as a high-fidelity event log.
- **Proposal**: Implement "Insight Extraction." When an LLM is available, the `MemoryWorker` should synthesize raw session events into structured observations.
- **Benefit**: Transitions the memory from a historical log into an actionable, high-level knowledge base.

## 4. Parallelized Indexing
`sync_workspace` currently operates sequentially, which can be slow for large repositories.
- **Proposal**: Use a process pool to parallelize file scanning, hashing, and embedding generation.
- **Benefit**: Drastically reduces indexing time on multi-core systems.

## 5. Search Re-ranking
Vector similarity can sometimes be "noisy," pulling in irrelevant snippets that happen to have similar hashed profiles.
- **Proposal**: Implement a secondary re-ranking step using BM25 or keyword density on the top-N results.
- **Benefit**: Ensures the most contextually relevant snippets are prioritized for the LLM.

## 6. System Health & Diagnostics
With multiple optional dependencies (`sqlite-vec`, `tree-sitter`), it can be unclear to the user if they are running in an optimized state.
- **Proposal**: Add a `codeindex doctor` command to verify hardware acceleration, language parsers, and environment health.
- **Benefit**: Improves developer experience and troubleshooting.

## 7. Async Server Infrastructure
The current `ThreadingHTTPServer` is stable but limited in performance and modern feature support.
- **Proposal**: Migrate the server to FastAPI or Starlette.
- **Benefit**: Better alignment with Phase 3 (Performance) goals, improved MCP integration, and asynchronous request handling.

## 8. Interactive Memory Management
The memory viewer is currently a read-only dashboard.
- **Proposal**: Allow users to "star," "edit," or "delete" observations directly from the UI.
- **Benefit**: Enables human-in-the-loop prioritization of critical project context.
