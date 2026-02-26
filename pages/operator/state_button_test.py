from __future__ import annotations

import json
from typing import Any

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from services.app_state import AppState
from services.i18n import t
from services.ui.registry import VIEW_ACTIONS, ViewName


def _to_text(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def render(container: ui.element, ctx: PageContext) -> None:
    state_rows: list[dict[str, str]] = []
    state_table_ref: dict[str, Any] = {"table": None}
    action_panel_ref: dict[str, Any] = {"container": None}
    selected_view_ref: dict[str, str] = {"value": ViewName.CONTAINER_MANAGEMENT.value}
    page_timers: list[Any] = []

    app_state_keys = list(AppState.__annotations__.keys())

    def add_timer(*args, **kwargs):
        timer = ui.timer(*args, **kwargs)
        page_timers.append(timer)
        return timer

    def cleanup() -> None:
        for timer in page_timers:
            try:
                timer.cancel()
            except Exception:
                pass
        page_timers[:] = []

    ctx.state._page_cleanup = cleanup
    ui.context.client.on_disconnect(cleanup)

    def refresh_state_table() -> None:
        rows: list[dict[str, str]] = []
        for key in app_state_keys:
            value = getattr(ctx.state, key, None)
            rows.append({"key": str(key), "value": _to_text(value)})
        state_rows[:] = rows
        table = state_table_ref.get("table")
        if table is not None:
            table.rows = list(state_rows)
            table.update()

    def get_button_state_map() -> dict[str, bool]:
        raw = getattr(ctx.state, "view_button_states", {}) or {}
        return dict(raw) if isinstance(raw, dict) else {}

    def get_button_visibility_map() -> dict[str, bool]:
        raw = getattr(ctx.state, "view_button_visibility", {}) or {}
        return dict(raw) if isinstance(raw, dict) else {}

    def set_button_state(key: str, enabled: bool) -> None:
        state = get_button_state_map()
        state[str(key)] = bool(enabled)
        ctx.set_state_and_publish("view_button_states", state)

    def set_button_visibility(key: str, visible: bool) -> None:
        vis = get_button_visibility_map()
        vis[str(key)] = bool(visible)
        ctx.set_state_and_publish("view_button_visibility", vis)

    def clear_button_overrides() -> None:
        ctx.set_state_and_publish("view_button_states", {})
        ctx.set_state_and_publish("view_button_visibility", {})
        rebuild_action_controls()

    def rebuild_action_controls() -> None:
        host = action_panel_ref.get("container")
        if host is None:
            return
        host.clear()
        view_name = str(selected_view_ref["value"] or ViewName.CONTAINER_MANAGEMENT.value)
        actions = VIEW_ACTIONS.get(ViewName(view_name), tuple())
        state = get_button_state_map()
        vis = get_button_visibility_map()

        with host:
            with ui.column().classes("w-full gap-2"):
                ui.label(
                    t("state_button_test.buttons_for_view", "Buttons for view: {view}", view=view_name)
                ).classes("text-sm font-semibold")

                for action in actions:
                    action_name = str(action.value)
                    full_key = f"{view_name}.{action_name}"
                    enabled_default = bool(state.get(full_key, True))
                    visible_default = bool(vis.get(full_key, True))
                    with ui.row().classes("w-full items-center gap-3 rounded border p-2"):
                        ui.label(action_name).classes("min-w-[180px] text-xs font-mono")
                        enabled_switch = ui.switch(
                            t("state_button_test.enabled", "Enabled"),
                            value=enabled_default,
                        )
                        visible_switch = ui.switch(
                            t("state_button_test.visible", "Visible"),
                            value=visible_default,
                        )
                        enabled_switch.on_value_change(
                            lambda e, k=full_key: set_button_state(k, bool(getattr(e, "value", False)))
                        )
                        visible_switch.on_value_change(
                            lambda e, k=full_key: set_button_visibility(k, bool(getattr(e, "value", False)))
                        )

    def build_content(_: ui.element) -> None:
        with ui.column().classes("w-full gap-3"):
            ui.label(
                t(
                    "state_button_test.subtitle",
                    "Test page for AppState values and button enabled/visible overrides.",
                )
            ).classes("text-sm text-gray-600")

            with ui.row().classes("w-full gap-3 items-start"):
                with ui.card().classes("w-[52%] p-3"):
                    with ui.row().classes("w-full items-center"):
                        ui.label(t("state_button_test.app_state", "AppState Variables")).classes("text-base font-bold")
                        ui.space()
                        ui.button(t("common.refresh", "Refresh"), on_click=refresh_state_table, icon="refresh").props("flat")

                    columns = [
                        {"name": "key", "label": "Key", "field": "key", "align": "left"},
                        {"name": "value", "label": "Value", "field": "value", "align": "left"},
                    ]
                    table = ui.table(
                        columns=columns,
                        rows=[],
                        row_key="key",
                        pagination={"rowsPerPage": 20},
                    ).classes("w-full text-xs")
                    table.props("dense bordered flat rows-per-page-options=[20,50,100]")
                    state_table_ref["table"] = table

                with ui.card().classes("w-[48%] p-3"):
                    with ui.column().classes("w-full gap-2"):
                        ui.label(t("state_button_test.button_controls", "Button Controls")).classes("text-base font-bold")
                        view_options = {v.value: v.value for v in ViewName}
                        view_select = ui.select(
                            options=view_options,
                            value=selected_view_ref["value"],
                            label=t("state_button_test.view", "View"),
                        ).classes("w-full")

                        def on_view_change(e: Any) -> None:
                            selected_view_ref["value"] = str(getattr(e, "value", ViewName.CONTAINER_MANAGEMENT.value))
                            rebuild_action_controls()

                        view_select.on_value_change(on_view_change)

                        with ui.row().classes("w-full gap-2"):
                            ui.button(
                                t("state_button_test.clear_overrides", "Clear Overrides"),
                                on_click=clear_button_overrides,
                                icon="clear_all",
                            ).props("outline")

                        action_panel_ref["container"] = ui.column().classes("w-full gap-2")
                        rebuild_action_controls()

    build_page(
        ctx,
        container,
        title=t("state_button_test.title", "State + Button Test"),
        content=build_content,
        show_action_bar=False,
    )

    add_timer(0.5, refresh_state_table)
    refresh_state_table()

