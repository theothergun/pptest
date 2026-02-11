from __future__ import annotations

import copy
from typing import Any


class ValuesApi:
    """Read-only access to latest bus values mirrored in context.data."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def source(self, source: str) -> dict[str, Any]:
        return copy.deepcopy(self._ctx.data.get(str(source), {}))

    def all(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._ctx.data)

    def last(self, source: str, default: Any = None) -> Any:
        src = str(source)
        source_data = self._ctx.data.get(src, {})
        last_id = self._ctx._last_seen_by_source.get(src, "")
        if last_id and last_id in source_data:
            return source_data[last_id]
        if source_data:
            # stable best-effort fallback
            any_key = next(iter(source_data))
            return source_data.get(any_key)
        return default

    def get(self, source: str, source_id: str, default: Any = None) -> Any:
        return self._ctx.data.get(str(source), {}).get(str(source_id), default)

    def by_key(self, key: str, default: Any = None) -> Any:
        target = str(key)
        # Search most recent payload per source first
        for source in list(self._ctx.data.keys()):
            payload = self.last(source, default=None)
            if isinstance(payload, dict) and payload.get("key") == target:
                return payload.get("value", default)

        # Fallback to full scan
        for source_data in self._ctx.data.values():
            for payload in source_data.values():
                if isinstance(payload, dict) and payload.get("key") == target:
                    return payload.get("value", default)
        return default


    def state(self, key: str, default: Any = None) -> Any:
        """Read one AppState value mirrored into the chain context."""
        return self._ctx._app_state.get(str(key), default)

    def state_all(self) -> dict[str, Any]:
        """Read full mirrored AppState snapshot."""
        return copy.deepcopy(self._ctx._app_state)
