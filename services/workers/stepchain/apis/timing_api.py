from __future__ import annotations

from typing import Any


class TimingApi:
    """Cycle and timeout helpers."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def set_cycle_time(self, seconds: float) -> None:
        try:
            val = float(seconds)
        except Exception:
            val = 0.1
        if val <= 0:
            val = 0.001
        self._ctx.cycle_time = val

    def step_seconds(self) -> float:
        try:
            return max(0.0, float(self._ctx.step_elapsed_s))
        except Exception:
            return 0.0

    def timeout(self, seconds: float) -> bool:
        try:
            target = float(seconds)
        except Exception:
            return False
        if target <= 0:
            return True
        return self.step_seconds() >= target
