from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, MutableMapping


class EmitDict(MutableMapping[str, Any]):
    """
    Dict-like state store for worker thread.

    - Normal writes (scripts) emit bridge.emit_patch(key, value) if the value changed.
    - apply_snapshot/apply_change update local data WITHOUT emitting
      (used for inbound updates from UI subscriptions).
    """

    def __init__(self, *, bridge) -> None:
        self._data: dict[str, Any] = {}
        self._bridge = bridge
        self._emit_enabled = True

    @contextmanager
    def suspend_emit(self):
        prev = self._emit_enabled
        self._emit_enabled = False
        try:
            yield
        finally:
            self._emit_enabled = prev

    # --- dict API ---
    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        old = self._data.get(key, None)
        self._data[key] = value
        if self._emit_enabled and old != value:
            self._bridge.emit_patch(key, value)

    def __delitem__(self, key: str) -> None:
        existed = key in self._data
        if existed:
            del self._data[key]
            if self._emit_enabled:
                self._bridge.emit_patch(key, None)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    # --- inbound update helpers (NO emits) ---
    def apply_snapshot(self, snapshot: dict[str, Any]) -> bool:
        """Replace local data with snapshot WITHOUT emitting. Returns True if changed."""
        with self.suspend_emit():
            changed = (self._data != snapshot)
            self._data.clear()
            self._data.update(snapshot)
        return changed

    def apply_change(self, key: str, value: Any) -> bool:
        """
        Apply a single field update WITHOUT emitting. Returns True if changed.
        Useful for 'state.*' subscription messages.
        """
        with self.suspend_emit():
            old = self._data.get(key, None)
            if old == value:
                return False
            self._data[key] = value
            return True

    # --- script-facing helper (WILL emit per key) ---
    def set_many(self, **values: Any) -> bool:
        """Normal batch update (emits for changed keys)."""
        changed = False
        for k, v in values.items():
            old = self._data.get(k, None)
            if old != v:
                self[k] = v  # emits via __setitem__
                changed = True
        return changed

    def snapshot(self) -> dict[str, Any]:
        return dict(self._data)
