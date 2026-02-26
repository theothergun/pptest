from __future__ import annotations

from nicegui import ui

from layout.context import PageContext
from layout.app_style import button_classes, button_props
from services.app_config import (
    WORKER_SCRIPT,
    WORKER_TCP,
    WORKER_REST,
    WORKER_TWINCAT,
    WORKER_ITAC,
    WORKER_COM_DEVICE,
    WORKER_OPCUA,
    get_app_config,
    save_app_config,
)


WORKER_OPTIONS: list[tuple[str, str]] = [
    (WORKER_SCRIPT, "Script Worker"),
    (WORKER_TCP, "TCP Client"),
    (WORKER_REST, "REST API"),
    (WORKER_TWINCAT, "TwinCAT"),
    (WORKER_ITAC, "iTAC"),
    (WORKER_COM_DEVICE, "COM Device"),
    (WORKER_OPCUA, "OPC UA"),
]

DEFAULT_WORKER_CONFIGS: dict[str, dict] = {
    WORKER_SCRIPT: {"auto_start_chains": []},
    WORKER_TCP: {"clients": []},
    WORKER_REST: {"endpoints": []},
    WORKER_TWINCAT: {"plc_endpoints": []},
    WORKER_ITAC: {"endpoints": []},
    WORKER_COM_DEVICE: {"devices": []},
    WORKER_OPCUA: {"endpoints": []},
}


def render(container: ui.element, _ctx: PageContext) -> None:
    with container.classes("w-full"):
        with ui.card().classes("app-panel w-full p-4"):
            ui.label("Enabled Workers").classes("text-xl font-semibold text-[var(--text-primary)]")
            ui.label("Select which workers are started at app startup.").classes("text-sm text-[var(--text-secondary)]")

            cfg = get_app_config()
            enabled = set(cfg.workers.enabled_workers or [])
            checkboxes: dict[str, ui.checkbox] = {}

            with ui.grid(columns=2).classes("w-full gap-2 mt-3"):
                for worker_key, label in WORKER_OPTIONS:
                    checkboxes[worker_key] = ui.checkbox(label, value=(worker_key in enabled)).props("color=primary")

            def save_enabled_workers() -> None:
                selected = [key for key, _label in WORKER_OPTIONS if bool(checkboxes[key].value)]
                cfg_local = get_app_config()
                cfg_local.workers.enabled_workers = selected
                cfg_local.workers.configs = cfg_local.workers.configs or {}
                for worker_key in selected:
                    cfg_local.workers.configs.setdefault(worker_key, dict(DEFAULT_WORKER_CONFIGS.get(worker_key, {})))
                save_app_config(cfg_local)
                ui.notify("Enabled workers updated.", type="positive")

            with ui.row().classes("w-full justify-end mt-3"):
                ui.button("Save enabled workers", on_click=save_enabled_workers).props(button_props("primary")).classes(
                    button_classes()
                )
