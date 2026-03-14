from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .memory_capture import build_raw_observation
from .memory_hooks import HookRegistry
from .memory_injection import compute_injection
from .memory_models import CapabilitySnapshot, HookEvent, MemorySession
from .memory_search import expand_memory, search_memory
from .memory_storage import MemoryStorage, fts5_available, utc_now
from .memory_worker import process_pending_observations

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


@dataclass
class MemoryContext:
    session_id: str
    workspace: str
    project_root: str
    actor_surface: str
    command_name: str


_CAPABILITY_CACHE: CapabilitySnapshot | None = None


class MemoryService:
    def __init__(self, storage, config: dict[str, Any], hook_registry: HookRegistry | None = None) -> None:
        self.storage = storage
        self.config = config
        self.memory = MemoryStorage(storage.conn)
        self.hooks = hook_registry or HookRegistry()

    def _memory_cfg(self) -> dict[str, Any]:
        return dict(self.config.get("memory", {}))

    def enabled(self) -> bool:
        return bool(self._memory_cfg().get("enabled", False))

    def capabilities(self) -> CapabilitySnapshot:
        global _CAPABILITY_CACHE
        if _CAPABILITY_CACHE is None:
            _CAPABILITY_CACHE = CapabilitySnapshot(
                fts5_available=fts5_available(self.storage.conn),
                yaml_available=yaml is not None,
                checked_at=utc_now(),
                details={"sqlite_version": self.storage.conn.execute("select sqlite_version()").fetchone()[0]},
            )
        self.memory.record_capability(_CAPABILITY_CACHE)
        self.storage.commit()
        return _CAPABILITY_CACHE

    def start_session(self, workspace: str, project_root: Path, actor_surface: str, command_name: str, trigger_kind: str) -> MemoryContext:
        session = MemorySession(
            session_id=f"sess_{uuid.uuid4().hex[:12]}",
            workspace=workspace,
            project_root=str(project_root),
            started_at=utc_now(),
            ended_at=None,
            trigger_kind=trigger_kind,
            command_name=command_name,
            metadata={"actor_surface": actor_surface},
        )
        self.memory.create_session(session)
        self.storage.commit()
        return MemoryContext(
            session_id=session.session_id,
            workspace=session.workspace,
            project_root=session.project_root,
            actor_surface=actor_surface,
            command_name=command_name,
        )

    def end_session(self, context: MemoryContext) -> None:
        self.memory.end_session(context.session_id, utc_now())
        self.storage.commit()

    def capture_event(
        self,
        context: MemoryContext,
        event_name: str,
        arguments_summary: str,
        result_summary: str,
        error_summary: str | None = None,
        token_metrics: dict[str, int | str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event = HookEvent(
            event=event_name,
            timestamp=utc_now(),
            workspace=context.workspace,
            session_id=context.session_id,
            actor_surface=context.actor_surface,
            command_name=context.command_name,
            arguments_summary=arguments_summary,
            result_summary=result_summary,
            error_summary=error_summary,
            token_metrics=token_metrics or {},
            metadata=metadata or {},
        )
        self.hooks.dispatch(event)
        observation = build_raw_observation(event, observation_id=f"obs_{uuid.uuid4().hex[:12]}")
        self.memory.add_observation(observation)
        self.memory.enqueue_observation(observation.observation_id, event.timestamp)
        self.storage.commit()
        return observation.observation_id

    def run_worker_once(self) -> dict[str, int]:
        cfg = self._memory_cfg()
        worker_cfg = cfg.get("worker", {})
        if not worker_cfg.get("enabled", True):
            return {"processed": 0, "failed": 0, "claimed": 0}
        return process_pending_observations(
            storage=self.memory,
            max_batch_size=int(worker_cfg.get("max_batch_size", 20)),
            max_retries=int(worker_cfg.get("max_retries", 3)),
        )

    def inject(self, context: MemoryContext, event: str, query_text: str) -> dict[str, Any]:
        cfg = self._memory_cfg()
        if not self.enabled():
            return {"results": []}
        return compute_injection(
            storage=self.memory,
            session_id=context.session_id,
            workspace=context.workspace,
            event=event,
            query_text=query_text,
            summary_budget_tokens=int(cfg.get("summary_budget_tokens", 600)),
            max_injected_observations=int(cfg.get("max_injected_observations", 8)),
            min_importance=float(cfg.get("min_importance", 0.2)),
        )

    def search(self, workspace: str, query: str, layer: str, budget_tokens: int | None = None, max_results: int = 8) -> dict[str, Any]:
        cfg = self._memory_cfg()
        budget = budget_tokens if budget_tokens is not None else int(cfg.get("summary_budget_tokens", 600))
        return search_memory(
            storage=self.memory,
            query=query,
            workspace=workspace,
            layer=layer,
            budget_tokens=budget,
            max_results=max_results,
            min_importance=float(cfg.get("min_importance", 0.2)),
        )

    def expand(self, observation_id: str) -> dict[str, Any]:
        return expand_memory(self.memory, observation_id)

    def list_sessions(self, workspace: str) -> list[dict[str, Any]]:
        return [
            {
                "session_id": item.session_id,
                "workspace": item.workspace,
                "project_root": item.project_root,
                "started_at": item.started_at,
                "ended_at": item.ended_at,
                "trigger_kind": item.trigger_kind,
                "command_name": item.command_name,
                "metadata": item.metadata,
            }
            for item in self.memory.list_sessions(workspace)
        ]

    def get_session(self, session_id: str) -> dict[str, Any]:
        item = self.memory.get_session(session_id)
        if item is None:
            raise ValueError(f"Unknown session id: {session_id}")
        return {
            "session_id": item.session_id,
            "workspace": item.workspace,
            "project_root": item.project_root,
            "started_at": item.started_at,
            "ended_at": item.ended_at,
            "trigger_kind": item.trigger_kind,
            "command_name": item.command_name,
            "metadata": item.metadata,
        }

    def citations(self, target_id: str) -> dict[str, Any]:
        return {
            "target_id": target_id,
            "citations": [
                {
                    "citation_id": item.citation_id,
                    "observation_id": item.observation_id,
                    "session_id": item.session_id,
                    "workspace": item.workspace,
                    "snippet": item.snippet,
                    "created_at": item.created_at,
                }
                for item in self.memory.list_citations(target_id)
            ],
        }

    def status(self, workspace: str) -> dict[str, Any]:
        self.capabilities()
        return self.memory.status(workspace)

    def recent_stream_events(self, workspace: str, limit: int) -> list[dict[str, Any]]:
        return self.memory.recent_stream_events(workspace, limit=limit)
