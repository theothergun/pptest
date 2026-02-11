from __future__ import annotations

import queue

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from services.app_config import get_app_config
from services.worker_commands import ScriptWorkerCommands as ScriptCommands
from services.worker_topics import ScriptWorkerTopics as ScriptTopics
from services.i18n import t


def render(container: ui.element, ctx: PageContext) -> None:
    worker_registry = ctx.workers
    bus = ctx.worker_bus
    config = get_app_config()
    enabled_workers = list(config.workers.enabled_workers or [])

    script_handle = worker_registry.get("script_worker") if worker_registry else None

    page_timers: list = []
    page_subs: list = []

    def add_timer(*args, **kwargs):
        timer = ui.timer(*args, **kwargs)
        page_timers.append(timer)
        return timer

    def cleanup() -> None:
        for sub in page_subs:
            try:
                sub.close()
            except Exception:
                pass
        page_subs[:] = []

        for timer in page_timers:
            try:
                timer.cancel()
            except Exception:
                pass
        page_timers[:] = []

    ctx.state._page_cleanup = cleanup
    ui.context.client.on_disconnect(cleanup)

    @ui.refreshable
    def workers_list() -> None:
        if not enabled_workers:
            ui.label(t("summary.no_workers", "No workers are enabled.")).classes("text-sm text-gray-500")
            return

        with ui.column().classes("w-full gap-2"):
            for name in enabled_workers:
                handle = worker_registry.get(name) if worker_registry else None
                is_alive = bool(handle and handle.is_alive())
                status = t("summary.connected", "Connected") if is_alive else t("summary.disconnected", "Disconnected")
                icon = "check_circle" if is_alive else "highlight_off"
                color = "text-green-600" if is_alive else "text-red-500"

                with ui.row().classes("w-full items-center justify-between"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon(icon).classes(color)
                        ui.label(name).classes("font-medium")
                    ui.label(status).classes("text-sm text-gray-500")

    chains_state: dict[str, list[dict]] = {"value": []}

    @ui.refreshable
    def chains_list() -> None:
        if not script_handle:
            ui.label(t("summary.script_worker_not_running", "Script worker is not running.")).classes("text-sm text-gray-500")
            return

        chains = chains_state["value"]
        if not chains:
            ui.label(t("summary.no_running_scripts", "No running scripts.")).classes("text-sm text-gray-500")
            return

        with ui.column().classes("w-full gap-2"):
            for chain in chains:
                active = bool(chain.get("active"))
                paused = bool(chain.get("paused"))
                if not active:
                    state = t("summary.state_stopped", "Stopped")
                    icon = "highlight_off"
                    color = "text-red-500"
                elif paused:
                    state = t("summary.state_paused", "Paused")
                    icon = "pause_circle"
                    color = "text-amber-500"
                else:
                    state = t("summary.state_running", "Running")
                    icon = "play_circle"
                    color = "text-green-600"

                script_name = chain.get("script", "?")
                instance = chain.get("instance", "default")
                step = chain.get("step", "?")
                cycle_count = chain.get("cycle_count", "?")

                with ui.card().props("flat bordered").classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon(icon).classes(color)
                            ui.label(f"{script_name} ({instance})").classes("font-medium")
                        ui.label(state).classes("text-sm text-gray-500")

                    with ui.row().classes("w-full text-xs text-gray-500 gap-4"):
                        ui.label(t("summary.step", "Step: {step}", step=step))
                        ui.label(t("summary.cycles", "Cycles: {count}", count=cycle_count))

    def build_content(_parent: ui.element) -> None:
        with ui.column().classes("w-full gap-4"):
            with ui.card().classes("w-full"):
                ui.label(t("summary.workers", "Workers")).classes("text-lg font-bold")
                workers_list()

            with ui.card().classes("w-full"):
                ui.label(t("summary.script_chains", "Script Chains")).classes("text-lg font-bold")
                chains_list()

    if bus:
        sub_chains = bus.subscribe(ScriptTopics.CHAINS_LIST)
        page_subs.append(sub_chains)

        def drain_chains() -> None:
            updated = False
            while True:
                try:
                    msg = sub_chains.queue.get_nowait()
                except queue.Empty:
                    break
                chains_state["value"] = msg.payload.get("chains", []) or []
                updated = True
            if updated:
                chains_list.refresh()

        add_timer(0.2, drain_chains)

    if script_handle:
        script_handle.send(ScriptCommands.LIST_CHAINS)

    add_timer(1.0, workers_list.refresh)

    build_page(ctx, container, title=t("summary.title", "Summary"), content=build_content, show_action_bar=False)
