from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.ui.view_cmd import publish_view_cmd


@dataclass(frozen=True)
class StandardViewAction:
    name: str
    description: str
    icon: str
    event: str = "click"


STANDARD_ACTIONS: list[StandardViewAction] = [
    StandardViewAction(name="start", description="Start processing or cycle.", icon="play_arrow"),
    StandardViewAction(name="stop", description="Stop processing or cycle.", icon="stop"),
    StandardViewAction(name="reset", description="Reset local or process state.", icon="restart_alt"),
    StandardViewAction(name="refresh", description="Refresh data from backend.", icon="refresh"),
    StandardViewAction(name="search", description="Run the default search.", icon="search"),
    StandardViewAction(name="search_container", description="Search by container id.", icon="inventory"),
    StandardViewAction(name="search_serial", description="Search by serial number.", icon="qr_code_2"),
    StandardViewAction(name="activate", description="Activate selected record/container.", icon="toggle_on"),
    StandardViewAction(name="remove", description="Remove selected item.", icon="delete"),
    StandardViewAction(name="remove_serial", description="Remove selected serial.", icon="remove_circle"),
    StandardViewAction(name="remove_all", description="Remove all relevant items.", icon="delete_sweep"),
    StandardViewAction(name="new", description="Create a new item.", icon="add"),
    StandardViewAction(name="print", description="Print label or document.", icon="print"),
    StandardViewAction(name="unlock", description="Unlock station or flow.", icon="lock_open"),
    StandardViewAction(name="failure_catalogue", description="Open failure catalogue dialog.", icon="menu_book"),
    StandardViewAction(name="pass", description="Confirm pass result.", icon="task_alt"),
    StandardViewAction(name="fail", description="Confirm fail/recheck result.", icon="warning"),
    StandardViewAction(name="scrap", description="Confirm scrap result.", icon="delete_forever"),
]


def make_action_event(view: str, name: str, event: str = "click") -> dict[str, str]:
    return {
        "view": str(view),
        "name": str(name),
        "event": str(event),
    }


def publish_standard_view_action(
    *,
    worker_bus,
    view: str,
    cmd_key: str,
    name: str,
    event: str = "click",
    wait_key: str | None = None,
    open_wait=None,
    extra: dict[str, Any] | None = None,
    source_id: str | None = None,
) -> dict[str, str]:
    action = make_action_event(view=view, name=name, event=event)
    merged_extra = dict(extra or {})
    merged_extra.setdefault("action", action)

    publish_view_cmd(
        worker_bus=worker_bus,
        view=view,
        cmd_key=cmd_key,
        name=name,
        event=event,
        wait_key=wait_key,
        open_wait=open_wait,
        extra=merged_extra,
        source_id=source_id,
    )
    return action
