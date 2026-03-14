from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    yaml = None

DEFAULT_CONFIG = {
    "workspace": "default",
    "paths": {"project_root": ".", "global_docs": []},
    "indexing": {
        "chunk_size": 800,
        "chunk_overlap": 120,
        "max_response_tokens": 2000,
    },
    "watch": {"enabled": False, "debounce_ms": 250},
    "excludes": [".git/**", "node_modules/**", "build/**", "dist/**", ".cache/**"],
    "query": {"top_k": 5, "include_global_docs": True, "require_workspace": True},
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


def _parse_scalar(raw: str) -> Any:
    if raw in {"true", "false"}:
        return raw == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(0, root)]

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()

        container = stack[-1][1]
        if content.startswith("- "):
            if not isinstance(container, list):
                raise ValueError("Invalid YAML list placement")
            container.append(_parse_scalar(content[2:].strip()))
            continue

        if ":" not in content:
            raise ValueError(f"Invalid YAML line: {content}")

        key, value = content.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value == "":
            # minimal list-key inference for our schema
            if key in {"global_docs", "excludes"}:
                node: Any = []
                container[key] = node
            else:
                node = {}
                container[key] = node
            stack.append((indent + 2, node))
        else:
            container[key] = _parse_scalar(value)

    return root


def _to_simple_yaml(data: Any, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(_to_simple_yaml(value, indent + 2))
            else:
                sval = "true" if value is True else "false" if value is False else str(value)
                lines.append(f"{pad}{key}: {sval}")
        return "\n".join(lines)
    if isinstance(data, list):
        return "\n".join(f"{pad}- {item}" for item in data)
    return f"{pad}{data}"


def load_config(path: Path) -> LoadedConfig:
    if not path.exists():
        return LoadedConfig(path=path, data=_default_config_copy())

    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        loaded_raw = yaml.safe_load(text) or {}
    else:
        loaded_raw = _parse_simple_yaml(text)

    if not isinstance(loaded_raw, dict):
        raise ValueError(f"Config file must deserialize to a mapping: {path}")

    data = _deep_merge(_default_config_copy(), loaded_raw)
    return LoadedConfig(path=path, data=data)


def save_config(path: Path, data: dict[str, Any]) -> None:
    if yaml is not None:
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    else:
        path.write_text(_to_simple_yaml(data) + "\n", encoding="utf-8")


def set_config_value(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    keys = dotted_key.split(".")
    cur = data
    for key in keys[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    cur[keys[-1]] = value
