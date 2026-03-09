from __future__ import annotations

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from services.i18n import t
from services.route_settings import get_route_settings
from services.ui.registry import UiActionName, UiEvent, ViewName, view_wait_key
from services.ui.view_action import publish_standard_view_action
from services.ui.view_cmd import install_wait_dialog
from ui.components import action_button, panel, page_container

PACKAGING_CMD_KEY = "packaging.cmd"
PACKAGING_NOX_VIEW = ViewName.PACKAGING_NOX
PACKAGING_NOX_WAIT_MODAL_KEY = view_wait_key(PACKAGING_NOX_VIEW)


def render(container: ui.element, ctx: PageContext) -> None:
    build_page(
        ctx,
        container,
        title=t("packaging.title", "Packaging Station"),
        content=lambda _parent: _build_content(ctx),
        show_action_bar=False,
    )


def _build_content(ctx: PageContext) -> None:
    route_settings = get_route_settings(ctx.current_route_key or "pack_nox")
    wait_dialog = install_wait_dialog(
        ctx=ctx,
        worker_bus=ctx.workers.worker_bus,
        wait_key=PACKAGING_NOX_WAIT_MODAL_KEY,
        title=t("packaging.wait_title", "Please wait"),
        message=t("packaging.working", "Working ..."),
        add_timer=lambda *a, **k: ui.timer(*a, **k),
    )

    def send(cmd: UiActionName | str) -> None:
        publish_standard_view_action(
            worker_bus=ctx.workers.worker_bus,
            view=PACKAGING_NOX_VIEW,
            cmd_key=PACKAGING_CMD_KEY,
            name=cmd,
            event=UiEvent.CLICK,
            wait_key=PACKAGING_NOX_WAIT_MODAL_KEY,
            open_wait=wait_dialog["open"],
            source_id=PACKAGING_NOX_VIEW.value,
        )

    with page_container():
        with panel(t("packaging.title", "Packaging Station"), t("packaging.current_step", "Current step"), icon="ti-building-factory"):
            ui.label(f"Scanner worker: {route_settings.get('scanner_worker', '-')}").classes("text-sm text-muted")
            ui.label(f"PLC worker: {route_settings.get('plc_worker', '-')}").classes("text-sm text-muted")
            ui.label(f"Printer worker: {route_settings.get('printer_worker', '-')}").classes("text-sm text-muted")

        with panel(t("packaging.container_number", "Containernumber"), icon="ti-package"):
            ui.label().bind_text_from(ctx.state, "container_number", backward=lambda n: str(n or "-"))
            ui.label().bind_text_from(ctx.state, "part_number", backward=lambda n: str(n or "-"))
            ui.label().bind_text_from(ctx.state, "description", backward=lambda n: str(n or "-"))

        with panel(t("packaging.instruction_for_worker", "Instruction for worker"), icon="ti-info-circle"):
            ui.label().bind_text_from(ctx.state, "work_instruction", backward=lambda n: str(n or ""))
            ui.label().bind_text_from(ctx.state, "work_feedback", backward=lambda n: str(n or ""))
            with ui.row().classes("w-full gap-2"):
                action_button(t("common.start", "Start"), lambda: send(UiActionName.START), icon="play_arrow")
                action_button(t("common.stop", "Stop"), lambda: send(UiActionName.STOP), icon="stop", tone="button-danger")
                action_button(t("common.reset", "Reset"), lambda: send(UiActionName.RESET), icon="restart_alt", tone="button-secondary")
                action_button(t("common.refresh", "Refresh"), lambda: send(UiActionName.REFRESH), icon="refresh", tone="button-outline")
