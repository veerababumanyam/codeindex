from __future__ import annotations

import hashlib
import json

from .memory_models import HookEvent, MemoryObservation


def build_raw_observation(event: HookEvent, observation_id: str) -> MemoryObservation:
    body_payload = {
        "event": event.event,
        "arguments_summary": event.arguments_summary,
        "result_summary": event.result_summary,
        "error_summary": event.error_summary,
        "token_metrics": event.token_metrics,
        "metadata": event.metadata,
    }
    body = json.dumps(body_payload, sort_keys=True)
    summary = event.result_summary or event.arguments_summary or event.event
    if len(summary) > 220:
        summary = summary[:217] + "..."
    digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]
    importance = 0.9 if event.error_summary else 0.6
    if event.event in {"query_executed", "analysis_executed", "mcp_tool_called"}:
        importance = max(importance, 0.7)
    return MemoryObservation(
        observation_id=observation_id,
        session_id=event.session_id,
        workspace=event.workspace,
        kind=event.event,
        source=event.actor_surface,
        title=f"{event.event}:{event.command_name or 'unknown'}:{digest}",
        body=body,
        summary=summary or event.event,
        token_count=max(1, len(body.split())),
        importance=importance,
        created_at=event.timestamp,
        status="raw",
        metadata=event.metadata,
    )
