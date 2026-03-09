from __future__ import annotations

from typing import Any

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from services.i18n import t
from services.ui.registry import UiActionName, UiEvent, ViewName, view_wait_key
from services.ui.view_action import publish_standard_view_action
from services.ui.view_cmd import install_wait_dialog
from services.route_settings import get_route_settings
from ui.components import action_button, panel, page_container, table_container

CONTAINER_MGMT_CMD_KEY = "container_management.cmd"
CONTAINER_MGMT_VIEW = ViewName.CONTAINER_MANAGEMENT
CONTAINER_MGMT_WAIT_MODAL_KEY = view_wait_key(CONTAINER_MGMT_VIEW)


def render(container: ui.element, ctx: PageContext) -> None:
    build_page(
        ctx,
        container,
        title=t("container_management.title", "Container Management"),
        content=lambda _parent: _build_content(ctx),
        show_action_bar=False,
    )


def _build_content(ctx: PageContext) -> None:
    route_settings = get_route_settings(ctx.current_route_key or "Container Managemet")
    wait_dialog = install_wait_dialog(
        ctx=ctx,
        worker_bus=ctx.workers.worker_bus,
        wait_key=CONTAINER_MGMT_WAIT_MODAL_KEY,
        title=t("packaging.wait_title", "Please wait"),
        message=t("packaging.working", "Working ..."),
        add_timer=lambda *a, **k: ui.timer(*a, **k),
    )

    def send(cmd: UiActionName | str, **extra: Any) -> None:
        publish_standard_view_action(
            worker_bus=ctx.workers.worker_bus,
            view=CONTAINER_MGMT_VIEW,
            cmd_key=CONTAINER_MGMT_CMD_KEY,
            name=cmd,
            event=UiEvent.CLICK,
            wait_key=CONTAINER_MGMT_WAIT_MODAL_KEY,
            open_wait=wait_dialog["open"],
            extra=extra,
            source_id=CONTAINER_MGMT_VIEW.value,
        )

    rows: list[dict[str, Any]] = []
    serial_rows: list[dict[str, Any]] = []
    with page_container():
        top = panel(
            t("container_management.title", "Container Management"),
            t("container_management.subtitle", "Search, activate, and maintain container serials"),
            icon="ti-package",
        )
        with top:
            ui.label(f"Scanner worker: {route_settings.get('scanner_worker', '-')}").classes("text-sm text-muted")
            with ui.row().classes("w-full gap-2"):
                search_input = ui.input(placeholder=t("container_management.search_by_container", "Search by container")).props("outlined dense").classes("w-full")
                action_button(t("common.search", "Search"), lambda: send(UiActionName.SEARCH, value=search_input.value), icon="search")
                action_button(t("container_management.activate", "Activate"), lambda: send(UiActionName.ACTIVATE), icon="check_circle", tone="button-secondary")

        with ui.row().classes("w-full gap-3"):
            with panel(t("container_management.container_results", "Container Results"), icon="ti-list-details"):
                table_container(
                    [{"name": "material_bin", "label": "Container", "field": "material_bin"}],
                    rows,
                    row_key="material_bin",
                )
            with panel(t("container_management.serials", "Container Serials"), icon="ti-barcode"):
                table_container(
                    [{"name": "serial_number", "label": "Serial", "field": "serial_number"}],
                    serial_rows,
                    row_key="serial_number",
                )
                with ui.row().classes("w-full gap-2"):
                    action_button(t("container_management.remove_serial", "Remove Serial"), lambda: send(UiActionName.REMOVE_SERIAL), icon="remove")
                    action_button(t("container_management.remove_all", "Remove All"), lambda: send(UiActionName.REMOVE_ALL), icon="delete", tone="button-danger")
