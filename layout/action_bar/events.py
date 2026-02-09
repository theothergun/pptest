from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, DefaultDict
from collections import defaultdict


Handler = Callable[..., None]


@dataclass
class EventBus:
    _handlers: DefaultDict[str, list[Handler]] = field(default_factory=lambda: defaultdict(list))

    def on(self, event: str, handler: Handler) -> None:
        self._handlers[event].append(handler)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        for h in list(self._handlers.get(event, [])):
            h(*args, **kwargs)
