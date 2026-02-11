from __future__ import annotations

from typing import Any


class FlowApi:
    """Step-flow operations (goto/fail/pause)."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def goto(self, step: int, desc: str = "") -> None:
        try:
            target = int(step)
        except Exception:
            target = 0

        if target != self._ctx.step:
            self._ctx._step_started_ts = 0.0

        self._ctx.next_step = target
        if desc:
            self._ctx.step_desc = str(desc)

    def fail(self, message: str) -> None:
        self._ctx.error_flag = True
        self._ctx.error_message = str(message or "")

    def clear_error(self) -> None:
        self._ctx.error_flag = False
        self._ctx.error_message = ""

    def pause(self) -> None:
        self._ctx.paused = True

    def resume(self) -> None:
        self._ctx.paused = False
