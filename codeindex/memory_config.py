from __future__ import annotations

from typing import Any


DEFAULT_MEMORY_CONFIG = {
    "enabled": True,
    "auto_capture": True,
    "inject_on_query": True,
    "inject_on_analyze": True,
    "inject_on_mcp": True,
    "project_local_only": True,
    "summary_budget_tokens": 600,
    "expanded_budget_tokens": 1800,
    "max_injected_observations": 8,
    "min_importance": 0.2,
    "worker": {
        "enabled": True,
        "poll_interval_ms": 500,
        "max_batch_size": 20,
        "max_retries": 3,
    },
    "viewer": {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 9090,
        "stream_buffer_size": 200,
    },
}


def validate_memory_config(memory: dict[str, Any]) -> dict[str, Any]:
    bool_keys = [
        "enabled",
        "auto_capture",
        "inject_on_query",
        "inject_on_analyze",
        "inject_on_mcp",
        "project_local_only",
    ]
    for key in bool_keys:
        if not isinstance(memory.get(key), bool):
            raise ValueError(f"Config key 'memory.{key}' must be a boolean")

    int_keys = [
        "summary_budget_tokens",
        "expanded_budget_tokens",
        "max_injected_observations",
    ]
    for key in int_keys:
        if not isinstance(memory.get(key), int) or int(memory[key]) <= 0:
            raise ValueError(f"Config key 'memory.{key}' must be a positive integer")

    if not isinstance(memory.get("min_importance"), (int, float)):
        raise ValueError("Config key 'memory.min_importance' must be numeric")

    if memory.get("project_local_only") is not True:
        raise ValueError("Config key 'memory.project_local_only' must be true in this phase")

    worker = memory.get("worker")
    if not isinstance(worker, dict):
        raise ValueError("Config key 'memory.worker' must be a mapping")
    for key in ("enabled",):
        if not isinstance(worker.get(key), bool):
            raise ValueError(f"Config key 'memory.worker.{key}' must be a boolean")
    for key in ("poll_interval_ms", "max_batch_size", "max_retries"):
        if not isinstance(worker.get(key), int) or int(worker[key]) <= 0:
            raise ValueError(f"Config key 'memory.worker.{key}' must be a positive integer")

    viewer = memory.get("viewer")
    if not isinstance(viewer, dict):
        raise ValueError("Config key 'memory.viewer' must be a mapping")
    if not isinstance(viewer.get("enabled"), bool):
        raise ValueError("Config key 'memory.viewer.enabled' must be a boolean")
    if not isinstance(viewer.get("host"), str):
        raise ValueError("Config key 'memory.viewer.host' must be a string")
    for key in ("port", "stream_buffer_size"):
        if not isinstance(viewer.get(key), int) or int(viewer[key]) <= 0:
            raise ValueError(f"Config key 'memory.viewer.{key}' must be a positive integer")

    return memory
