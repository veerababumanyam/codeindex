from __future__ import annotations

from typing import Any

from .memory_storage import MemoryStorage


LAYER_MULTIPLIERS = {
    "summary": 1,
    "expanded": 2,
    "full": 4,
}


def search_memory(
    storage: MemoryStorage,
    query: str,
    workspace: str,
    layer: str,
    budget_tokens: int,
    max_results: int,
    min_importance: float,
) -> dict[str, Any]:
    selected_layer = layer if layer in LAYER_MULTIPLIERS else "summary"
    hits = storage.search_observations(
        query=query,
        workspace=workspace,
        limit=max_results,
        min_importance=min_importance,
    )

    results = []
    estimated_summary = 0
    estimated_expanded = 0
    estimated_full = 0
    for hit in hits:
        summary_tokens = max(1, len(hit.observation.summary.split()))
        expanded_text = str(hit.observation.metadata.get("expanded_summary", hit.observation.summary))
        expanded_tokens = max(summary_tokens, len(expanded_text.split()))
        full_tokens = max(expanded_tokens, hit.observation.token_count)
        estimated_summary += summary_tokens
        estimated_expanded += expanded_tokens
        estimated_full += full_tokens
        results.append(
            {
                "observation_id": hit.observation.observation_id,
                "citation_id": hit.citation_id,
                "session_id": hit.observation.session_id,
                "kind": hit.observation.kind,
                "source": hit.observation.source,
                "title": hit.observation.title,
                "summary": hit.observation.summary,
                "expanded_summary": expanded_text if selected_layer in {"expanded", "full"} else None,
                "relevance": round(hit.relevance, 4),
                "importance": round(hit.observation.importance, 4),
                "created_at": hit.observation.created_at,
                "expand_token_cost": hit.expand_token_cost,
                "body": hit.observation.body if selected_layer == "full" else None,
            }
        )

    selected_estimate = {
        "summary": estimated_summary,
        "expanded": estimated_expanded,
        "full": estimated_full,
    }[selected_layer]
    return {
        "query": query,
        "workspace": workspace,
        "layer": selected_layer,
        "budget_tokens": budget_tokens,
        "estimated_tokens_summary": estimated_summary,
        "estimated_tokens_expanded": estimated_expanded,
        "estimated_tokens_full": estimated_full,
        "estimated_tokens_saved": max(0, estimated_full - min(selected_estimate, budget_tokens)),
        "selected_layer": selected_layer,
        "budget_limit": budget_tokens,
        "expansion_available": bool(results),
        "results": results,
    }


def expand_memory(storage: MemoryStorage, observation_id: str) -> dict[str, Any]:
    observation = storage.get_observation(observation_id)
    if observation is None:
        raise ValueError(f"Unknown observation id: {observation_id}")
    citations = storage.list_citations(observation_id)
    return {
        "observation_id": observation.observation_id,
        "session_id": observation.session_id,
        "citation_ids": [item.citation_id for item in citations],
        "title": observation.title,
        "summary": observation.summary,
        "body": observation.body,
        "metadata": observation.metadata,
        "token_count": observation.token_count,
    }
