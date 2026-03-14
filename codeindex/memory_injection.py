from __future__ import annotations

from typing import Any

from .memory_models import InjectionDecision
from .memory_search import search_memory
from .memory_storage import MemoryStorage


async def compute_injection(
    storage: MemoryStorage,
    session_id: str,
    workspace: str,
    event: str,
    query_text: str,
    summary_budget_tokens: int,
    max_injected_observations: int,
    min_importance: float,
) -> dict[str, Any]:
    payload = await search_memory(
        storage=storage,
        query=query_text,
        workspace=workspace,
        layer="summary",
        budget_tokens=summary_budget_tokens,
        max_results=max_injected_observations,
        min_importance=min_importance,
    )
    selected = payload["results"]
    estimated_tokens = sum(max(1, len(str(item["summary"]).split())) for item in selected)
    decision = InjectionDecision(
        event=event,
        session_id=session_id,
        workspace=workspace,
        query=query_text,
        selected_layer="summary",
        budget_limit=summary_budget_tokens,
        estimated_tokens=estimated_tokens,
        selected_observation_ids=[item["observation_id"] for item in selected],
        reasons=["relevance", "recency", "importance", "workspace_match"],
    )
    await storage.record_injection(
        session_id=decision.session_id,
        workspace=decision.workspace,
        event=decision.event,
        query_text=decision.query,
        selected_layer=decision.selected_layer,
        budget_limit=decision.budget_limit,
        estimated_tokens=decision.estimated_tokens,
        selected_observation_ids=decision.selected_observation_ids,
        reasons=decision.reasons,
    )
    return {
        "selected_layer": decision.selected_layer,
        "budget_limit": decision.budget_limit,
        "estimated_tokens": decision.estimated_tokens,
        "selected_observation_ids": decision.selected_observation_ids,
        "results": selected,
    }
