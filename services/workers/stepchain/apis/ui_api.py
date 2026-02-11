from __future__ import annotations

from typing import Any

from services.worker_topics import WorkerTopics
from services.worker_commands import ScriptWorkerCommands as Commands


class UiApi:
    """UI/log/event helpers exposed to scripts."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def set(self, key: str, value: Any) -> None:
        if not isinstance(self._ctx._ui_state, dict):
            self._ctx._ui_state = {}
        self._ctx._ui_state[str(key)] = value

    def merge(self, patch: dict[str, Any]) -> None:
        if not isinstance(patch, dict):
            return
        if not isinstance(self._ctx._ui_state, dict):
            self._ctx._ui_state = {}
        self._ctx._ui_state.update(patch)

    def clear(self) -> None:
        self._ctx._ui_state = {}

    def notify(self, message: str, type_: str = "info") -> None:
        try:
            self._ctx.bridge.emit_notify(str(message), str(type_))
        except Exception:
            pass

    def log(self, message: str, level: str = "info") -> None:
        payload = {
            "chain_key": self._ctx.chain_id,
            "step": int(self._ctx.step),
            "step_desc": str(self._ctx.step_desc or ""),
            "level": str(level or "info"),
            "message": str(message or ""),
        }
        try:
            self._ctx.worker_bus.publish(
                topic=WorkerTopics.VALUE_CHANGED,
                source="ScriptWorker",
                source_id=self._ctx.chain_id,
                key=Commands.UPDATE_LOG,
                value=payload,
            )
        except Exception:
            pass

    def event(self, name: str, **payload: Any) -> None:
        event_key = "script.event.%s" % str(name or "unnamed")
        try:
            self._ctx.worker_bus.publish(
                topic=WorkerTopics.VALUE_CHANGED,
                source="ScriptWorker",
                source_id=self._ctx.chain_id,
                key=event_key,
                value=dict(payload),
            )
        except Exception:
            pass
