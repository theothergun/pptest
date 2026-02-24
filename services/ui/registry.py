from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class StrEnum(str, Enum):
    pass


class ViewName(StrEnum):
    CONTAINER_MANAGEMENT = "container_management"
    PACKAGING = "packaging"
    PACKAGING_NOX = "packaging_nox"
    VI_HOME = "vi_home"
    VI_FAILURE_CATALOGUE = "vi_failure_catalogue"
    VIEW_ACTION_EXAMPLE = "view_action_example"


class UiEvent(StrEnum):
    CLICK = "click"
    LOAD = "load"
    REFRESH = "refresh"
    SUBMIT = "submit"
    CHANGE = "change"


class UiActionName(StrEnum):
    ACTIVATE = "activate"
    DELETE = "delete"
    SAVE = "save"
    START = "start"
    STOP = "stop"
    RESET = "reset"
    REFRESH = "refresh"
    SEARCH = "search"
    SEARCH_CONTAINER = "search_container"
    SEARCH_SERIAL = "search_serial"
    REMOVE = "remove"
    REMOVE_SERIAL = "remove_serial"
    REMOVE_ALL = "remove_all"
    NEW = "new"
    PRINT = "print"
    UNLOCK = "unlock"
    FAILURE_CATALOGUE = "failure_catalogue"
    PASS = "pass"
    FAIL = "fail"
    SCRAP = "scrap"
    START_STOP = "start_stop"
    LTC_STATUS = "ltc_status"
    VC_STATUS = "vc_status"
    REFRESH_CATALOGUE = "refresh_catalogue"


VIEW_ACTIONS: dict[ViewName, tuple[UiActionName, ...]] = {
    ViewName.CONTAINER_MANAGEMENT: (
        UiActionName.SEARCH,
        UiActionName.REFRESH,
        UiActionName.SEARCH_CONTAINER,
        UiActionName.SEARCH_SERIAL,
        UiActionName.ACTIVATE,
        UiActionName.REMOVE_SERIAL,
        UiActionName.REMOVE_ALL,
    ),
    ViewName.PACKAGING: (
        UiActionName.REMOVE,
        UiActionName.PRINT,
        UiActionName.NEW,
        UiActionName.REFRESH,
        UiActionName.RESET,
    ),
    ViewName.PACKAGING_NOX: (
        UiActionName.START,
        UiActionName.STOP,
        UiActionName.REFRESH,
        UiActionName.RESET,
    ),
    ViewName.VI_HOME: (
        UiActionName.START_STOP,
        UiActionName.LTC_STATUS,
        UiActionName.VC_STATUS,
        UiActionName.FAILURE_CATALOGUE,
        UiActionName.UNLOCK,
    ),
    ViewName.VI_FAILURE_CATALOGUE: (
        UiActionName.REFRESH_CATALOGUE,
        UiActionName.PASS,
        UiActionName.FAIL,
        UiActionName.SCRAP,
    ),
    ViewName.VIEW_ACTION_EXAMPLE: tuple(a for a in UiActionName),
}


VIEW_EVENTS: dict[ViewName, tuple[UiEvent, ...]] = {
    ViewName.CONTAINER_MANAGEMENT: (UiEvent.CLICK,),
    ViewName.PACKAGING: (UiEvent.CLICK,),
    ViewName.PACKAGING_NOX: (UiEvent.CLICK,),
    ViewName.VI_HOME: (UiEvent.CLICK,),
    ViewName.VI_FAILURE_CATALOGUE: (UiEvent.CLICK, UiEvent.SUBMIT),
    ViewName.VIEW_ACTION_EXAMPLE: tuple(e for e in UiEvent),
}


class ViewRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ViewActionRef:
    view: ViewName
    name: UiActionName
    event: UiEvent = UiEvent.CLICK

    @property
    def wait_modal_key(self) -> str:
        return view_wait_key(self.view)

    def to_legacy_dict(self) -> dict[str, str]:
        return {
            "view": self.view.value,
            "name": self.name.value,
            "event": self.event.value,
        }


def _enum_from_value(enum_cls, value: Any, field_name: str):
    raw = str(value or "").strip()
    try:
        return enum_cls(raw)
    except Exception:
        raise ViewRegistryError("unknown %s '%s'" % (field_name, raw))


def parse_view_action(*, view: Any, name: Any, event: Any = UiEvent.CLICK) -> ViewActionRef:
    view_name = _enum_from_value(ViewName, view, "view")
    action_name = _enum_from_value(UiActionName, name, "action")
    event_name = _enum_from_value(UiEvent, event, "event")

    if action_name not in VIEW_ACTIONS.get(view_name, ()):  # explicit non-reflective validation
        raise ViewRegistryError(
            "invalid action '%s' for view '%s'" % (action_name.value, view_name.value)
        )
    if event_name not in VIEW_EVENTS.get(view_name, ()):  # explicit non-reflective validation
        raise ViewRegistryError(
            "invalid event '%s' for view '%s'" % (event_name.value, view_name.value)
        )
    return ViewActionRef(view=view_name, name=action_name, event=event_name)


def from_view_command(cmd: Any) -> ViewActionRef:
    action = getattr(cmd, "action", None)
    if action is None:
        raise ViewRegistryError("command missing action")
    return parse_view_action(
        view=getattr(action, "view", ""),
        name=getattr(action, "name", ""),
        event=getattr(action, "event", UiEvent.CLICK.value),
    )


def to_view_action(*, view: ViewName, action: UiActionName, event: UiEvent = UiEvent.CLICK) -> dict[str, str]:
    ref = parse_view_action(view=view, name=action, event=event)
    return ref.to_legacy_dict()


def view_wait_key(view: ViewName | str) -> str:
    return "view.wait.%s" % str(getattr(view, "value", view) or "").strip()


def list_registry() -> dict[str, Any]:
    return {
        "views": [v.value for v in ViewName],
        "events": [e.value for e in UiEvent],
        "actions": {
            view.value: [a.value for a in VIEW_ACTIONS.get(view, tuple())]
            for view in ViewName
        },
    }
