from __future__ import annotations

import heapq
from dataclasses import dataclass

from .embedding import cosine_similarity, embed_text
from .storage import ChunkRecord, Storage


MODE_TO_KINDS = {
    "chunks": ["chunk"],
    "symbols": ["symbol"],
    "hybrid": ["symbol", "chunk"],
}


@dataclass
class SearchResult:
    score: float
    chunk: ChunkRecord


def resolve_workspaces(workspace: str, include_global: bool) -> list[str]:
    workspaces = [workspace]
    if include_global and workspace != "global":
        workspaces.append("global")
    return workspaces


def validate_mode(mode: str) -> list[str]:
    if mode not in MODE_TO_KINDS:
        valid = ", ".join(sorted(MODE_TO_KINDS))
        raise ValueError(f"Invalid query mode '{mode}'. Expected one of: {valid}")
    return MODE_TO_KINDS[mode]


def search_index(
    storage: Storage,
    query: str,
    workspace: str,
    include_global: bool,
    top_k: int,
    mode: str,
) -> tuple[list[str], list[SearchResult], dict[str, int | str]]:
    source_kinds = validate_mode(mode)
    workspaces = resolve_workspaces(workspace, include_global)
    query_terms = {
        part.lower()
        for part in query.replace(":", " ").split()
        if part and any(ch.isalnum() for ch in part)
    }
    narrowed_terms = sorted(term for term in query_terms if len(term) >= 3)[:6]
    q_emb = embed_text(query)

    if storage.supports_vector_search():
        candidate_k = max(top_k * 8, top_k)
        nearest = storage.vector_search(
            workspaces=workspaces,
            source_kinds=source_kinds,
            query_embedding=q_emb,
            top_k=candidate_k,
            query_terms=narrowed_terms or None,
        )
        if not nearest and narrowed_terms:
            nearest = storage.vector_search(
                workspaces=workspaces,
                source_kinds=source_kinds,
                query_embedding=q_emb,
                top_k=candidate_k,
                query_terms=None,
            )
        scored_vec: list[SearchResult] = []
        for chunk, distance in nearest:
            score = -distance
            if chunk.source_kind == "symbol":
                score += 0.05
                if chunk.symbol_name:
                    symbol_terms = {part.lower() for part in chunk.symbol_name.replace(":", " ").split() if part}
                    overlap = len(query_terms & symbol_terms)
                    if overlap:
                        score += 0.2 * overlap
            scored_vec.append(SearchResult(score=score, chunk=chunk))
        selected = sorted(scored_vec, key=lambda item: item.score, reverse=True)[:top_k]
    else:
        selected = _fallback_scan_top_k(storage, workspaces, source_kinds, q_emb, query_terms, narrowed_terms, top_k)

    vector_backend = storage.vector_backend_name()
    context_tokens = sum(item.chunk.token_count for item in selected)
    full_tokens = storage.workspace_token_count(workspaces)
    savings = max(0, full_tokens - context_tokens)
    savings_pct = 0 if full_tokens == 0 else round((savings / full_tokens) * 100)
    metrics: dict[str, int | str] = {
        "mode": mode,
        "vector_backend": vector_backend,
        "result_count": len(selected),
        "context_tokens": context_tokens,
        "estimated_full_workspace_tokens": full_tokens,
        "estimated_tokens_saved": savings,
        "estimated_savings_percent": savings_pct,
    }
    return workspaces, selected, metrics


def _fallback_scan_top_k(
    storage: Storage,
    workspaces: list[str],
    source_kinds: list[str],
    q_emb: list[float],
    query_terms: set[str],
    narrowed_terms: list[str],
    top_k: int,
) -> list[SearchResult]:
    heap: list[tuple[float, int, SearchResult]] = []
    seen = 0

    def score_candidates(use_prefilter: bool) -> None:
        nonlocal seen
        for chunk in storage.stream_chunks(
            workspaces,
            source_kinds=source_kinds,
            query_terms=narrowed_terms if use_prefilter else None,
        ):
            seen += 1
            score = cosine_similarity(q_emb, chunk.embedding)
            if chunk.source_kind == "symbol":
                score += 0.05
                if chunk.symbol_name:
                    symbol_terms = {part.lower() for part in chunk.symbol_name.replace(":", " ").split() if part}
                    overlap = len(query_terms & symbol_terms)
                    if overlap:
                        score += 0.2 * overlap
            result = SearchResult(score=score, chunk=chunk)
            if len(heap) < top_k:
                heapq.heappush(heap, (score, seen, result))
                continue
            if score > heap[0][0]:
                heapq.heapreplace(heap, (score, seen, result))

    score_candidates(use_prefilter=bool(narrowed_terms))
    if not heap and narrowed_terms:
        score_candidates(use_prefilter=False)
    return [item[2] for item in sorted(heap, key=lambda item: item[0], reverse=True)]
