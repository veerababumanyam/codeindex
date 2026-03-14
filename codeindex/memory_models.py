from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CapabilitySnapshot:
    fts5_available: bool
    yaml_available: bool
    checked_at: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookEvent:
    event: str
    timestamp: str
    workspace: str
    session_id: str
    actor_surface: str
    command_name: str | None
    arguments_summary: str
    result_summary: str
    error_summary: str | None = None
    token_metrics: dict[str, int | str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemorySession:
    session_id: str
    workspace: str
    project_root: str
    started_at: str
    ended_at: str | None
    trigger_kind: str
    command_name: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryObservation:
    observation_id: str
    session_id: str
    workspace: str
    kind: str
    source: str
    title: str
    body: str
    summary: str
    token_count: int
    importance: float
    created_at: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryCitation:
    citation_id: str
    observation_id: str
    session_id: str
    workspace: str
    snippet: str
    created_at: str


@dataclass
class MemorySearchHit:
    observation: MemoryObservation
    citation_id: str | None
    relevance: float
    expand_token_cost: int


@dataclass
class InjectionDecision:
    event: str
    session_id: str
    workspace: str
    query: str
    selected_layer: str
    budget_limit: int
    estimated_tokens: int
    selected_observation_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
