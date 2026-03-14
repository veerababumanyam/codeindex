from __future__ import annotations

import copy
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from .memory_config import DEFAULT_MEMORY_CONFIG, validate_memory_config

try:
    import yaml  # type: ignore
except Exception as exc:  # pragma: no cover - import is environment-dependent
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None

DEFAULT_CONFIG = {
    "workspace": "default",
    "paths": {"project_root": ".", "global_docs": []},
    "server": {
        "host": "127.0.0.1",
        "port": 9090,
        "allow_remote": False,
        "auth_token": None,
        "auth_token_header": "X-CodeIndex-Token",
    },
    "indexing": {
        "chunk_size": 800,
        "chunk_overlap": 120,
        "max_response_tokens": 2000,
    },
    "watch": {"enabled": False, "debounce_ms": 250},
    "excludes": [".git/**", "node_modules/**", "build/**", "dist/**", ".cache/**"],
    "query": {"top_k": 5, "include_global_docs": True, "require_workspace": True, "mode": "hybrid"},
    "analysis": {"prefer_tree_sitter": True},
    "memory": DEFAULT_MEMORY_CONFIG,
}


@dataclass
class LoadedConfig:
    path: Path
    data: dict[str, Any]


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _default_config_copy() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def _require_yaml() -> Any:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to load or save config files. Install it with `python -m pip install pyyaml`."
        ) from YAML_IMPORT_ERROR
    return yaml


def _expect_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Config key '{path}' must be a mapping")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Config key '{path}' must be a list")
    return value


def validate_config(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Config file must deserialize to a mapping")

    if not isinstance(data.get("workspace"), str):
        raise ValueError("Config key 'workspace' must be a string")

    paths = _expect_mapping(data.get("paths"), "paths")
    if not isinstance(paths.get("project_root"), str):
        raise ValueError("Config key 'paths.project_root' must be a string")
    for item in _expect_list(paths.get("global_docs"), "paths.global_docs"):
        if not isinstance(item, str):
            raise ValueError("Config key 'paths.global_docs' must contain only strings")

    server = _expect_mapping(data.get("server"), "server")
    host = server.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("Config key 'server.host' must be a non-empty string")
    if not isinstance(server.get("port"), int) or int(server["port"]) <= 0:
        raise ValueError("Config key 'server.port' must be a positive integer")
    if not isinstance(server.get("allow_remote"), bool):
        raise ValueError("Config key 'server.allow_remote' must be a boolean")
    auth_token = server.get("auth_token")
    if auth_token is not None:
        if not isinstance(auth_token, str):
            raise ValueError("Config key 'server.auth_token' must be a string or null")
        if not auth_token.strip():
            raise ValueError("Config key 'server.auth_token' must not be empty when provided")
    auth_token_header = server.get("auth_token_header")
    if not isinstance(auth_token_header, str) or not auth_token_header.strip():
        raise ValueError("Config key 'server.auth_token_header' must be a non-empty string")

    indexing = _expect_mapping(data.get("indexing"), "indexing")
    for key in ("chunk_size", "chunk_overlap", "max_response_tokens"):
        if not isinstance(indexing.get(key), int):
            raise ValueError(f"Config key 'indexing.{key}' must be an integer")

    watch = _expect_mapping(data.get("watch"), "watch")
    if not isinstance(watch.get("enabled"), bool):
        raise ValueError("Config key 'watch.enabled' must be a boolean")
    if not isinstance(watch.get("debounce_ms"), int):
        raise ValueError("Config key 'watch.debounce_ms' must be an integer")

    for item in _expect_list(data.get("excludes"), "excludes"):
        if not isinstance(item, str):
            raise ValueError("Config key 'excludes' must contain only strings")

    query = _expect_mapping(data.get("query"), "query")
    if not isinstance(query.get("top_k"), int):
        raise ValueError("Config key 'query.top_k' must be an integer")
    if not isinstance(query.get("include_global_docs"), bool):
        raise ValueError("Config key 'query.include_global_docs' must be a boolean")
    if not isinstance(query.get("require_workspace"), bool):
        raise ValueError("Config key 'query.require_workspace' must be a boolean")
    if query.get("mode") not in {"chunks", "symbols", "hybrid"}:
        raise ValueError("Config key 'query.mode' must be one of: chunks, symbols, hybrid")

    analysis = _expect_mapping(data.get("analysis"), "analysis")
    if not isinstance(analysis.get("prefer_tree_sitter"), bool):
        raise ValueError("Config key 'analysis.prefer_tree_sitter' must be a boolean")

    memory = _expect_mapping(data.get("memory"), "memory")
    validate_memory_config(memory)

    return data


def load_config(path: Path) -> LoadedConfig:
    if not path.exists():
        return LoadedConfig(path=path, data=validate_config(_default_config_copy()))

    text = path.read_text(encoding="utf-8")
    yaml_module = _require_yaml()
    loaded_raw = yaml_module.safe_load(text) or {}

    if not isinstance(loaded_raw, dict):
        raise ValueError(f"Config file must deserialize to a mapping: {path}")

    data = validate_config(_deep_merge(_default_config_copy(), loaded_raw))
    return LoadedConfig(path=path, data=data)


def save_config(path: Path, data: dict[str, Any]) -> None:
    yaml_module = _require_yaml()
    path.write_text(yaml_module.safe_dump(validate_config(data), sort_keys=False), encoding="utf-8")


def set_config_value(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    keys = dotted_key.split(".")
    cur = data
    for key in keys[:-1]:
        if key not in cur:
            raise KeyError(f"Unknown config key '{dotted_key}'")
        if not isinstance(cur[key], dict):
            raise KeyError(f"Config key '{'.'.join(keys[:-1])}' is not a mapping")
        cur = cur[key]
    if keys[-1] not in cur:
        raise KeyError(f"Unknown config key '{dotted_key}'")
    cur[keys[-1]] = value
    validate_config(data)


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False
