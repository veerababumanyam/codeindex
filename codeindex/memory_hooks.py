from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from .memory_models import HookEvent

HookCallback = Callable[[HookEvent], None]


class HookRegistry:
    def __init__(self) -> None:
        self._callbacks: dict[str, list[HookCallback]] = defaultdict(list)

    def register(self, event: str, callback: HookCallback) -> None:
        self._callbacks[event].append(callback)

    def dispatch(self, event: HookEvent) -> None:
        for callback in self._callbacks.get(event.event, []):
            callback(event)
