from __future__ import annotations

from nicegui import ui

from layout.context import PageContext
from services.barfi_bridge import BARFI_BRIDGE


def render(container: ui.element, ctx: PageContext) -> None:
    with container:
        ui.label("Barfi Visual Builder").classes("text-h6")
        ui.label(
            "Run a Barfi canvas in an embedded Streamlit app, then export script stubs that can call ctx.ui.* APIs."
        ).classes("text-sm text-gray-600")

        frame_host = ui.column().classes("w-full")

        def refresh_frame() -> None:
            frame_host.clear()
            if BARFI_BRIDGE.is_running():
                with frame_host:
                    ui.html(
                        f'<iframe src="{BARFI_BRIDGE.get_url()}" style="width:100%;height:75vh;border:1px solid #ddd;border-radius:8px;"></iframe>'
                    )
            else:
                with frame_host:
                    ui.label("Barfi is not running.").classes("text-sm text-gray-500")

        with ui.row().classes("items-center gap-2 my-3"):
            ui.button("Start Barfi", on_click=lambda: (_start(), refresh_frame())).props("color=primary")
            ui.button("Stop Barfi", on_click=lambda: (_stop(), refresh_frame())).props("color=negative")
            ui.button("Refresh", on_click=refresh_frame).props("outline")

        def _start() -> None:
            url = BARFI_BRIDGE.start()
            ui.notify(f"Barfi started at {url}", type="positive")

        def _stop() -> None:
            BARFI_BRIDGE.stop()
            ui.notify("Barfi stopped", type="info")

        ui.markdown(
            """
            **Setup notes**
            - Requires Python packages: `streamlit` and `barfi`.
            - Install with: `pip install streamlit barfi`.
            - Exported scripts are written to `scripts/barfi_generated/`.
            """
        )

        refresh_frame()
