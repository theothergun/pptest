from __future__ import annotations

import json
from typing import Any

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from services.ui.view_action import STANDARD_ACTIONS, make_action_event, publish_standard_view_action
from services.ui.registry import UiActionName, UiEvent, ViewName, view_wait_key


EXAMPLE_VIEW = ViewName.VIEW_ACTION_EXAMPLE
EXAMPLE_CMD_KEY = "example.actions"
EXAMPLE_WAIT_KEY = view_wait_key(EXAMPLE_VIEW)


def render(container: ui.element, ctx: PageContext) -> None:
    last_event: dict[str, Any] = {}
    publish_to_worker = {"value": False}

    @ui.refreshable
    def event_preview() -> None:
        with ui.card().classes("w-full p-3"):
            ui.label("Last Event Payload").classes("text-sm font-semibold")
            text = json.dumps(last_event, indent=2) if last_event else "{}"
            ui.code(text).classes("w-full")

    def on_action(name: str) -> None:
        action_event = make_action_event(view=EXAMPLE_VIEW, name=UiActionName(str(name)), event=UiEvent.CLICK)
        last_event.clear()
        last_event.update(action_event)
        event_preview.refresh()

        if publish_to_worker["value"] and ctx.workers is not None:
            publish_standard_view_action(
                worker_bus=ctx.workers.worker_bus,
                view=EXAMPLE_VIEW,
                cmd_key=EXAMPLE_CMD_KEY,
                name=UiActionName(str(name)),
                event=UiEvent.CLICK,
                wait_key=EXAMPLE_WAIT_KEY,
                source_id=EXAMPLE_VIEW.value,
                extra={"note": "developer example page"},
            )

    def content(_parent: ui.element) -> None:
        with ui.column().classes("w-full h-full gap-3"):
            with ui.card().classes("w-full p-3"):
                ui.label("View Action Standard").classes("text-lg font-semibold")
                ui.label(
                    "Every button emits one action payload with view, name, event. "
                    "Use publish_standard_view_action(...) in production pages."
                ).classes("text-sm text-gray-600")
                ui.switch(
                    "Also publish to worker bus (example.actions)",
                    value=publish_to_worker["value"],
                    on_change=lambda e: publish_to_worker.__setitem__("value", bool(e.value)),
                )

            with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"):
                for spec in STANDARD_ACTIONS:
                    with ui.card().classes("p-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon(spec.icon)
                            ui.label(spec.name).classes("font-semibold")
                        ui.label(spec.description).classes("text-xs text-gray-600 min-h-[36px]")
                        ui.label(f"event: {spec.event}").classes("text-[11px] text-gray-500")
                        ui.button(
                            f"Emit {spec.name}",
                            icon=spec.icon,
                            on_click=lambda _=None, n=spec.name: on_action(n),
                        ).props("outline").classes("w-full mt-2")

            event_preview()

    build_page(
        ctx,
        container,
        title="View Action Example",
        content=content,
        show_action_bar=False,
    )
