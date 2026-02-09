from __future__ import annotations

from typing import Any

from nicegui import ui

from layout.context import PageContext
from pages.visual_inspection.failure_catalogue import FailureCatalogue, ErrorWeight


catalogue = FailureCatalogue()

FAILURE_COLUMNS = [
    {"name": "weight", "label": "Weight", "field": "weight", "align": "left"},
    {"name": "code", "label": "Code", "field": "code", "align": "left"},
    {"name": "description", "label": "Description", "field": "description", "align": "left"},
]

IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
PDF_EXT = {'.pdf'}

def register_dialog_css() -> None:
    """Call once (e.g. in main.py) to enable slide-in/out animation."""
    ui.add_css("""
        /* Make NiceGUI dialog container truly fullscreen without padding */
        .q-dialog__inner--maximized > div {
          padding: 0 !important;
        }
       /* Hide the auto-width selection column (the checkbox column) */
        .q-table--selection th.q-table--col-auto-width,
        .q-table--selection td.q-table--col-auto-width {
        display: none !important;
        }
    
        .q-table--selection colgroup col:first-child {
        width: 0 !important;
        }
        
        /* Make row clearly clickable */
        .q-table tbody tr { cursor: pointer; }
        /* Optional: highlight selected row a bit more */
        
        .q-table tbody tr.bg-blue-1,
        .q-table tbody tr.q-tr--selected {
        font-weight: 600;
        }
        
        /* Hide the "x rows selected" hint/bottom selection banner */
        .q-table__bottom .q-table__control,
        .q-table__bottom .q-table__separator,
        .q-table__bottom .q-table__selected-rows,
        .q-table__bottom--nodata {
        display: none !important;
        }
        """)


def create_failure_catalogue_dialog(ctx:PageContext) -> tuple[ui.dialog, callable]:
    """ Returns:(dialog, open_fn)
    open_fn(sn: str = '', pn: str = '') opens it and sets header values.
    """
    state: dict[str, Any] = {
        "sn": "",
        "pn": "",
        "selected_group": None,
        "selected_failure": None,
        "viewer_url": None,
        "viewer_type": None,
    }


    dialog = ui.dialog().props("maximized persistent")  # persistent: click outside won't close

    # wrapper for slide animation
    with dialog:
        panel = ui.element("div").classes("vi-panel flex flex-col bg-gray-100")

        # ---------------- header ----------------
        with panel:
            with ui.element("div").classes("w-full bg-primary text-white px-4 py-2 flex items-center justify-between"):
                # left
                with ui.row().classes("items-center gap-4"):
                    ui.icon("fact_check").classes("text-white text-2xl")
                    ui.label("Visual Inspection").classes("text-xl font-bold")

                    with ui.row().classes("items-center gap-2"):
                        ui.label("S/N:").classes("font-semibold")
                        sn_value = ui.label("").classes("min-w-[160px]")
                        sn_value.bind_text_from(state, "sn")

                    with ui.row().classes("items-center gap-2"):
                        ui.label("P/N:").classes("font-semibold")
                        pn_value = ui.label("").classes("min-w-[160px]")
                        pn_value.bind_text_from(state, "pn")

                # right + close
                with ui.row().classes("items-center gap-4"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("assignment_late").classes("text-white text-2xl")
                        ui.label("Assigned Failures").classes("text-lg font-semibold")

                    ui.button(icon="refresh", on_click = lambda: (refresh_catalogue(),
                        )).props("flat round dense").classes(
                        "text-white")

            # ---------------- content ----------------
            with ui.element("div").classes("flex-1 w-full flex overflow-hidden gap-2 p-2"):

                # group table
                with ui.card().classes("w-[24%] h-full overflow-hidden"):
                    ui.label("Groups").classes("px-3 pt-3 text-sm text-gray-600")
                    ui.separator()
                    with ui.element("div").classes("h-full w-full overflow-auto p-2"):
                        group_table = ui.table(
                            columns=[
                                {"name": "group", "label": "Group", "field": "group"},
                                {"name": "description", "label": "Description", "field": "description"},
                            ],
                            rows= catalogue.group_rows(),
                            row_key="group",
                            selection="single",
                        ).classes("w-full").props("flat")

                # failure table
                with ui.card().classes("w-[40%] h-full overflow-hidden"):
                    ui.label("Failures").classes("px-3 pt-3 text-sm text-gray-600")
                    ui.separator()
                    with ui.element("div").classes("h-full w-full overflow-auto p-2"):
                        failures_table = ui.table(
                            columns=FAILURE_COLUMNS,
                            rows=[],
                            row_key="code",
                            selection="single",
                        ).classes("w-full").props("flat")

                # right viewer
                with ui.card().classes("flex-1 h-full overflow-hidden"):
                    ui.label("Viewer").classes("px-3 pt-3 text-sm text-gray-600")
                    ui.separator()

                    with ui.element("div").classes("h-full w-full overflow-hidden bg-white"):
                        viewer_iframe = ui.html('', sanitize=False).classes("w-full h-full").style('height:80vh')

            # ---------------- bottom bar ----------------
            with ui.element("div").classes("w-full"):
                with ui.row().classes("w-full gap-0"):
                    btn_pass = ui.button("PASS", on_click=lambda: on_action_click('btn_pass')).props("unelevated").classes(
                        "w-1/3 h-20 text-2xl font-bold bg-green-8 text-white rounded-none"
                    )
                    btn_fail = ui.button("FAIL", on_click=lambda: on_action_click('btn_fail')).props("unelevated").classes(
                        "w-1/3 h-20 text-2xl font-bold bg-orange-8 text-white rounded-none"
                    )
                    btn_scrap = ui.button("SCRAP", on_click=lambda: on_action_click('btn_scrap')).props("unelevated").classes(
                        "w-1/3 h-20 text-2xl font-bold bg-red-8 text-white rounded-none"
                    )

    # ---------- behavior ----------
    def sync_action_buttons() -> None:
        failure = state["selected_failure"]
        if failure is None:
            weight = 1
        else:
            weight = (ErrorWeight.SCRAP if failure["weight"] in
                [ErrorWeight.SCRAP, ErrorWeight.NOT_SET, ErrorWeight.SAFE_LAUNCH] else failure["weight"])

        btn_pass.set_enabled(weight == ErrorWeight.PASS)
        btn_fail.set_enabled(failure and weight < ErrorWeight.SCRAP)
        btn_scrap.set_enabled(failure is not None)

    def on_action_click(btn_id: str):
        #TO DO make the booking
        status = 1 if btn_id == "btn_pass" else 2 if btn_id == "btn_fail" else 3
        result = "PASS" if btn_id == "btn_pass" else "RECHECK" if btn_id == "btn_fail" else "SCRAP"
        ctx.set_state_many_and_publish(vc_error_status = status, vc_result = result)
        close()

    def render_iframe(url: str) -> str:
        return f'''<iframe src ="{url}" style ="width:100%; height:100%; border:none; background:white;"></iframe>'''

    def set_viewer(url: str | None) -> None:
        state["viewer_url"] = url
        if not url:
            viewer_iframe.content = """<div style="padding:12px; color:gray;">
                No document / image loaded </div>"""
            return
        viewer_iframe.content = render_iframe(url)

    def handle_group_selected(row: dict | None) -> None:
        if not row:
            state["selected_group"] = None
            failures_table.rows = []
            failures_table.update()
            state["selected_failure"] = None
            set_viewer(None)
            sync_action_buttons()
            return

        group_key = row["group"]
        state["selected_group"] = group_key

        failures_table.rows = catalogue.failure_rows(group_key)
        failures_table.update()

        _reset_error_selection()

    def on_group_selected(e) -> None:
        rows = e.args.get("rows", [])
        handle_group_selected(rows[0] if rows else None)

    def clicked_row_from_event(e) -> dict:
        # Some NiceGUI versions: e.args is list/tuple -> [row, index] or [row]
        if isinstance(e.args, (list, tuple)):
            return e.args[1]
        # Other versions: e.args is dict -> {"row": row, ...}
        return e.args.get("row")

    def on_group_row_clicked(e) -> None:
        # Set selection (must match row_key)
        row = clicked_row_from_event(e)
        group_table.selected = [row]
        group_table.update()
        handle_group_selected(row)

    def handle_failure_selected(row: dict | None) -> None:
        if not row:
            state["selected_failure"] = None
            set_viewer(None)
            sync_action_buttons()
            return

        state["selected_failure"] = row

        set_viewer(row["document_url"])

        sync_action_buttons()

    def on_failure_selected(e) -> None:
        selected = e.args.get("rows", [])
        row = selected[0] if selected else None
        if row  == state["selected_failure"]:
            row = None
        handle_failure_selected(row)

    def on_failure_row_clicked(e) -> None:
        row = clicked_row_from_event(e)
        failures_table.selected = [row]
        failures_table.update()
        handle_failure_selected(row)

    group_table.on("selection", on_group_selected)
    group_table.on('rowClick', on_group_row_clicked)

    failures_table.on("selection", on_failure_selected)
    failures_table.on('rowClick', on_failure_row_clicked)

    def refresh_catalogue() -> None:
        """Force reload catalogue data and refresh UI tables + selections."""
        ui.notify("refresh catalogue starting ...")
        # 1) reload cached catalogue data
        catalogue.refresh()

        # 2) repopulate left table (groups)
        group_table.rows = catalogue.group_rows()
        group_table.update()

        # 3) clear selections and dependent UI
        state["selected_group"] = None
        state["selected_failure"] = None

        # clear selection highlights in tables (NiceGUI/Quasar)
        group_table.props('selection="single"')  # keeps selection mode
        failures_table.props('selection="single"')

        # 4) clear middle table (no group selected)
        failures_table.rows = []
        failures_table.update()

        # 5) clear right viewer
        set_viewer(None)

        # 6) update action buttons
        sync_action_buttons()

        ui.notify("Catalogue reloaded", type="positive")


    def _reset_error_selection():
        failures_table.selected = []
        failures_table.update()
        handle_failure_selected(None)

    def open_(sn: str = "", pn: str = "") -> None:
        state["sn"] = sn
        state["pn"] = pn
        _reset_error_selection()
        if not catalogue.loaded:
            register_dialog_css()
        catalogue.load_once()
        group_table.rows = catalogue.group_rows()
        group_table.update()


        # open dialog then trigger slide-in (next tick)
        dialog.open()

        # ensure buttons correct
        sync_action_buttons()

    def close() -> None:
        # slide out then close dialog
        def _do_close() -> None:
            dialog.close()
        ui.timer(0.26, _do_close, once=True)

    # return the dialog and open function
    return dialog, open_