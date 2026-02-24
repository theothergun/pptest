from __future__ import annotations

import random
import string

from nicegui import ui
from layout.context import PageContext
from layout.page_scaffold import build_page
from layout.action_bar import Action
from layout.errors_state import (get_active_errors, upsert_error,
                resolve_error, clear_all_errors, get_error_count)
from services.i18n import t
from loguru import logger


def _random_id(prefix: str) -> str:
    tail = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}:{tail}"

def render(container: ui.element, ctx: PageContext) -> None:
    logger.debug(f"[render] - errors_page_render")
    #update button state according to the error list
    def sync_actions() -> None:
        if not ctx.action_bar:
            return
        has_errors = get_error_count() > 0
        ctx.action_bar.set_enabled("clear_all", has_errors)

    # ---- refreshable list so it updates immediately ----
    @ui.refreshable
    def error_list() -> None:
        errors = get_active_errors()
        if not errors:
            ui.label(t("errors.none", "No active errors 🎉")).classes("mt-4 text-green-600")
            return

        # show newest first
        items = sorted(errors.items(), key=lambda kv: kv[1]["ts"], reverse=True)

        for error_id, e in items:
            with ui.card().props("flat bordered").classes("w-full p-2"):
                # top row: meta + resolve
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(f"{e['level'].upper()} · {e['source']} · {e['ts']}").classes("text-xs text-gray-500")
                    ui.button(
                        icon="done",
                        on_click=lambda eid=error_id: (resolve_error(ctx, eid), error_list.refresh(), sync_actions()),
                    ).props("dense round flat").classes("text-xs").tooltip(t("errors.tooltip.resolve", "Resolve this error"))

                # message line: clickable expansion only if details exist
                details = (e.get("details") or "").strip()
                if details:
                    with ui.expansion(e["message"]).props("dense").classes("mt-1"):
                        ui.label(details).classes("text-xs whitespace-pre-wrap")
                else:
                    ui.label(e["message"]).classes("text-sm font-medium leading-tight mt-1")

    # ---- action handlers ----
    def on_action_clicked(action_id: str, action: Action) -> None:
        if action_id == "clear_all":
            clear_all_errors(ctx)     # updates badge
            error_list.refresh()      # updates list immediately
            sync_actions()
            logger.info(f"[on_action_clicked] - clear_all_errors")
            ui.notify(t("errors.notify.cleared", "Cleared all errors"))
            return

        if action_id == "add_random":
            # create a random "active error" (stable id per new item)
            # pick a “category”
            kind = random.choice(["device", "conn", "backend"])
            if kind == "device":
                error_id = _random_id("device:cam")
                upsert_error(
                    ctx,
                    error_id,
                    source="device",
                    message=t("errors.device_offline", "Device offline"),
                    details=t("errors.heartbeat_timeout", "Heartbeat timeout"),
                )
            elif kind == "conn":
                error_id = _random_id("conn:mqtt")
                upsert_error(
                    ctx,
                    error_id,
                    source="connection",
                    message=t("errors.mqtt_disconnected", "MQTT disconnected"),
                    details=t("errors.retrying", "Retrying…"),
                    level="warning",
                )
            else:
                error_id = _random_id("backend:job")
                upsert_error(
                    ctx,
                    error_id,
                    source="backend",
                    message=t("errors.backend_failed", "Backend job failed"),
                    details=t("errors.http503", "HTTP 503 from upstream"),
                )

            error_list.refresh()
            sync_actions()
            logger.info(f"[on_action_clicked] - add_random_error - kind={kind}")
            ui.notify(t("errors.notify.random_added", "Random error added"))
            return


    def build_content(_parent: ui.element) ->None:
        sync_actions()
        error_list()

    build_page(ctx,container, title=t("errors.title", "Errors"), content= build_content,
               show_action_bar=True, on_action_clicked=on_action_clicked)

