from __future__ import annotations

from typing import Callable
from nicegui import ui


def create_add_rest_endpoint_dialog(
    *,
    on_add: Callable[[dict], bool],
) -> tuple[ui.dialog, Callable[[], None]]:
    dialog = ui.dialog()

    with dialog:
        with ui.card().classes("w-[min(860px,95vw)] p-0 overflow-hidden"):
            with ui.row().classes("w-full h-10 items-center px-4 bg-primary text-white"):
                ui.label("Add REST endpoint").classes("text-base font-semibold")

            with ui.column().classes("w-full p-4 gap-4"):
                name_input = ui.input("Name").classes("w-full")
                base_url_input = ui.input("Base URL").classes("w-full")
                headers_input = ui.textarea("Headers (JSON)", value="{}").classes("w-full")
                timeout_input = ui.input("Timeout (s)", value="10").classes("w-full")
                verify_ssl_input = ui.switch("Verify SSL", value=True)

                def clear() -> None:
                    name_input.value = ""
                    base_url_input.value = ""
                    headers_input.value = "{}"
                    timeout_input.value = "10"
                    verify_ssl_input.value = True

                def handle_add() -> None:
                    payload = {
                        "name": name_input.value,
                        "base_url": base_url_input.value,
                        "headers_raw": headers_input.value,
                        "timeout_s": timeout_input.value,
                        "verify_ssl": verify_ssl_input.value,
                    }
                    ok = on_add(payload)
                    if not ok:
                        return
                    clear()
                    dialog.close()

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button("Add endpoint", on_click=handle_add).props("color=primary")

    def open_dialog() -> None:
        dialog.open()

    return dialog, open_dialog
