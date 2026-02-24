from __future__ import annotations

from typing import Any

from nicegui import ui

from layout.main_area import PageContext
from layout.page_scaffold import build_page
from services.i18n import (
    SUPPORTED_LANGUAGES,
    export_rows,
    import_rows,
    save_translations,
    bootstrap_defaults,
)

_LANG_TABLE_CSS_ADDED = False


def render(container: ui.element, _ctx: PageContext) -> None:
    global _LANG_TABLE_CSS_ADDED
    if not _LANG_TABLE_CSS_ADDED:
        ui.add_css(
            """
            .lang-table-sticky {
                height: 100%;
            }
            .lang-table-sticky .q-table__top,
            .lang-table-sticky .q-table__bottom,
            .lang-table-sticky thead tr:first-child th {
                background: var(--surface) !important;
                color: var(--text-primary) !important;
            }
            .lang-table-sticky thead tr th {
                position: sticky;
                z-index: 2;
                top: 0;
            }
            """
        )
        _LANG_TABLE_CSS_ADDED = True

    bootstrap_defaults()

    def build_content(_parent: ui.element) -> None:
        with ui.column().classes("w-full h-full min-h-0 gap-3 flex flex-col"):
            ui.label("Create key/value translations for all supported languages.").classes(
                "text-sm text-gray-500"
            )

            all_rows = export_rows()
            columns = [{"name": "key", "label": "Key", "field": "key", "align": "left"}]
            for lang in SUPPORTED_LANGUAGES:
                code = lang["code"]
                columns.append({"name": code, "label": lang["label"], "field": code, "align": "left"})

            selected_row: dict[str, Any] = {"key": ""}

            with ui.row().classes("w-full gap-2 items-center"):
                filter_input = ui.input("Filter keys", placeholder="type key fragment...").classes("min-w-[260px]")
                text_filter_input = ui.input(
                    "Filter translated text",
                    placeholder="type text fragment in any language...",
                ).classes("min-w-[320px]")

                def apply_filter() -> None:
                    key_query = str(filter_input.value or "").strip().lower()
                    text_query = str(text_filter_input.value or "").strip().lower()

                    def _row_matches(row: dict[str, Any]) -> bool:
                        if key_query and key_query not in str(row.get("key", "")).lower():
                            return False
                        if text_query:
                            for lang in SUPPORTED_LANGUAGES:
                                code = lang["code"]
                                if text_query in str(row.get(code, "")).lower():
                                    return True
                            return False
                        return True

                    table.rows[:] = [row for row in all_rows if _row_matches(row)]
                    table.update()

                filter_input.on("keydown.enter", lambda _e: apply_filter())
                text_filter_input.on("keydown.enter", lambda _e: apply_filter())

                def open_add_dialog() -> None:
                    d = ui.dialog()
                    with d, ui.card().classes("w-[960px] max-w-[95vw]"):
                        ui.label("Add Translation Key").classes("text-lg font-semibold")
                        key_input = ui.input("Key", placeholder="example.page.title").classes("w-full")
                        editors: dict[str, ui.textarea] = {}
                        with ui.grid(columns=2).classes("w-full gap-2"):
                            for lang in SUPPORTED_LANGUAGES:
                                code = lang["code"]
                                ed = ui.textarea(label=lang["label"]).props("autogrow outlined")
                                ed.classes("w-full")
                                editors[code] = ed

                        def do_add() -> None:
                            key = str(key_input.value or "").strip()
                            if not key:
                                ui.notify("Please enter a translation key.", type="negative")
                                return
                            if any(row.get("key") == key for row in all_rows):
                                ui.notify(f"Key '{key}' already exists.", type="warning")
                                return
                            new_row: dict[str, str] = {"key": key}
                            for lang in SUPPORTED_LANGUAGES:
                                code = lang["code"]
                                new_row[code] = str(editors[code].value or "")
                            all_rows.append(new_row)
                            all_rows.sort(key=lambda item: str(item.get("key", "")))
                            apply_filter()
                            ui.notify(f"Added: {key}", type="positive")
                            d.close()

                        with ui.row().classes("w-full justify-end gap-2"):
                            ui.button("Cancel", on_click=d.close).props("flat")
                            ui.button("Add", on_click=do_add).props("color=primary")
                    d.open()

                def open_edit_dialog(row_override: dict[str, Any] | None = None) -> None:
                    active_row = row_override or selected_row
                    key = str(active_row.get("key") or "").strip()
                    if not key:
                        ui.notify("Select a key in table first.", type="warning")
                        return
                    row = next((r for r in all_rows if str(r.get("key")) == key), None)
                    if not row:
                        ui.notify("Selected key not found.", type="negative")
                        return

                    d = ui.dialog()
                    with d, ui.card().classes("w-[960px] max-w-[95vw]"):
                        ui.label("Edit Translations").classes("text-lg font-semibold")
                        ui.input("Key", value=key).props("readonly outlined").classes("w-full")
                        editors: dict[str, ui.textarea] = {}
                        with ui.grid(columns=2).classes("w-full gap-2"):
                            for lang in SUPPORTED_LANGUAGES:
                                code = lang["code"]
                                ed = ui.textarea(label=lang["label"], value=str(row.get(code, ""))).props("autogrow outlined")
                                ed.classes("w-full")
                                editors[code] = ed

                        def do_apply() -> None:
                            for lang in SUPPORTED_LANGUAGES:
                                code = lang["code"]
                                row[code] = str(editors[code].value or "")
                            apply_filter()
                            selected_row.update(row)
                            selected_key.set_text(f"Selected: {key}")
                            ui.notify(f"Updated: {key}", type="positive")
                            d.close()

                        with ui.row().classes("w-full justify-end gap-2"):
                            ui.button("Cancel", on_click=d.close).props("flat")
                            ui.button("Apply", on_click=do_apply).props("color=primary")
                    d.open()

                ui.button("Filter", on_click=apply_filter).props("flat")
                ui.button(
                    "Clear filter",
                    on_click=lambda: (
                        setattr(filter_input, "value", ""),
                        setattr(text_filter_input, "value", ""),
                        apply_filter(),
                    ),
                ).props("flat")
                ui.button("Add key", on_click=open_add_dialog).props("color=primary")
                ui.button("Edit selected", on_click=open_edit_dialog).props("flat color=primary")

            with ui.card().classes("w-full flex-1 min-h-0 flex flex-col"):
                ui.label("Translations").classes("font-semibold")
                with ui.element("div").classes("w-full flex-1 min-h-0 overflow-hidden"):
                    table = ui.table(columns=columns, rows=list(all_rows), row_key="key").props(
                        "dense separator=cell flat virtual-scroll"
                    ).classes("w-full h-full lang-table-sticky")

            selected_key = ui.label("No key selected").classes("text-sm text-gray-500")

            def bind_selected(row: dict[str, Any] | None) -> None:
                if not row:
                    selected_row.clear()
                    selected_row["key"] = ""
                    selected_key.set_text("No key selected")
                    return
                selected_row.clear()
                selected_row.update(row)
                selected_key.set_text(f"Selected: {row.get('key', '')}")

            table.on("rowClick", lambda e: bind_selected(e.args[1]))
            table.on("rowDblclick", lambda e: open_edit_dialog(e.args[1] if len(e.args) > 1 else None))

            def persist_all() -> None:
                payload = import_rows(all_rows)
                save_translations(payload)
                ui.notify("Translations saved.", type="positive")

            with ui.row().classes("justify-end w-full gap-2"):
                ui.button("Save all", on_click=persist_all).props("color=primary")

    build_page(
        _ctx,
        container,
        title="Language manager",
        content=build_content,
        show_action_bar=False,
    )
