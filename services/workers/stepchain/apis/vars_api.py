from __future__ import annotations

import copy
from typing import Any


class VarsApi:
    """Persistent per-chain variables for scripts."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def get(self, key: str, default: Any = None) -> Any:
        return self._ctx._vars.get(str(key), default)

    def set(self, key: str, value: Any) -> None:
        self._ctx._vars[str(key)] = value

    def has(self, key: str) -> bool:
        return str(key) in self._ctx._vars

    def pop(self, key: str, default: Any = None) -> Any:
        return self._ctx._vars.pop(str(key), default)

    def delete(self, key: str) -> None:
        self._ctx._vars.pop(str(key), None)

    def clear(self) -> None:
        self._ctx._vars.clear()

    def inc(self, key: str, amount: float = 1.0, default: float = 0.0) -> float:
        k = str(key)
        current = self._ctx._vars.get(k, default)
        try:
            next_value = float(current) + float(amount)
        except Exception:
            next_value = float(default) + float(amount)
        self._ctx._vars[k] = next_value
        return next_value

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._ctx._vars)
