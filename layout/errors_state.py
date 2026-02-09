# layout/errors_state.py
from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict, Dict

from nicegui import app
from layout.context import PageContext

Level = Literal["error", "warning", "info"]

class ActiveError(TypedDict):
    ts: str
    level: Level
    source: str
    message: str
    details: str


def refresh_errors_count(ctx: PageContext) -> None:
    """Recompute derived count from the persistent error store."""
    if ctx.state is None:
        return
    ctx.state.error_count = len(app.storage.user.get("errors_active", {}))


def upsert_error(
    ctx: PageContext,
    error_id: str,
    *,
    message: str,
    details: str = "",
    source: str = "backend",
    level: Level = "error",
) -> None:
    errors = _get_active_errors()
    errors[error_id] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "level": level,
        "source": source,
        "message": message,
        "details": details,
    }
    refresh_errors_count(ctx)


def resolve_error(ctx: PageContext, error_id: str) -> None:
    errors = _get_active_errors()
    if error_id in errors:
        del errors[error_id]
    refresh_errors_count(ctx)


def clear_all_errors(ctx: PageContext) -> None:
    app.storage.user["errors_active"] = {}
    refresh_errors_count(ctx)


def get_active_errors() -> Dict[str, ActiveError]:
    return dict(_get_active_errors())

def get_error_count() -> int:
    return len(_get_active_errors())

def _get_active_errors() -> Dict[str, ActiveError]:
    return app.storage.user.setdefault("errors_active", {})