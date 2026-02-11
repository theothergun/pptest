from __future__ import annotations

from nicegui import ui

from layout.main_area import PageContext
from services.i18n import (
    SUPPORTED_LANGUAGES,
    export_rows,
    import_rows,
    save_translations,
    bootstrap_defaults,
)


def render(container: ui.element, _ctx: PageContext) -> None:
    bootstrap_defaults()

    with container:
        ui.label("Language manager").classes("text-xl font-semibold")
        ui.label("Create key/value translations for all supported languages.").classes(
            "text-sm text-gray-500"
        )

        all_rows = export_rows()
        columns = [{"name": "key", "label": "Key", "field": "key", "align": "left"}]
        for lang in SUPPORTED_LANGUAGES:
            code = lang["code"]
            columns.append({"name": code, "label": lang["label"], "field": code, "align": "left"})

        selected_row: dict[str, str] = {"key": ""}
        editors: dict[str, ui.textarea] = {}

        with ui.row().classes("w-full gap-2 items-center"):
            filter_input = ui.input("Filter keys", placeholder="type key fragment...").classes("min-w-[260px]")
            key_input = ui.input("New key", placeholder="example.page.title").classes("min-w-[260px]")

            def apply_filter() -> None:
                query = str(filter_input.value or "").strip().lower()
                if not query:
                    table.rows[:] = all_rows
                else:
                    table.rows[:] = [row for row in all_rows if query in str(row.get("key", "")).lower()]
                table.update()

            def add_row() -> None:
                key = str(key_input.value or "").strip()
                if not key:
                    ui.notify("Please enter a translation key.", type="negative")
                    return
                if any(row.get("key") == key for row in all_rows):
                    ui.notify(f"Key '{key}' already exists.", type="warning")
                    return
                new_row = {"key": key}
                for lang in SUPPORTED_LANGUAGES:
                    new_row[lang["code"]] = ""
                all_rows.append(new_row)
                all_rows.sort(key=lambda item: str(item.get("key", "")))
                apply_filter()
                key_input.value = ""
                ui.notify(f"Added: {key}", type="positive")

            ui.button("Filter", on_click=apply_filter).props("flat")
            ui.button("Add key", on_click=add_row).props("color=primary")

        with ui.card().classes("w-full"):
            ui.label("Translations").classes("font-semibold")
            with ui.element("div").classes("w-full max-h-[40vh] overflow-auto"):
                table = ui.table(columns=columns, rows=list(all_rows), row_key="key").props(
                    "dense separator=cell flat virtual-scroll"
                ).classes("w-full")

        with ui.card().classes("w-full"):
            ui.label("Edit selected phrase").classes("font-semibold")
            selected_key = ui.label("No key selected").classes("text-sm text-gray-500")

            def bind_selected(row: dict[str, str] | None) -> None:
                if not row:
                    selected_key.set_text("No key selected")
                    selected_row.clear()
                    selected_row["key"] = ""
                    for editor in editors.values():
                        editor.value = ""
                    return

                selected_row.clear()
                selected_row.update(row)
                selected_key.set_text(f"Editing: {row.get('key', '')}")
                for lang in SUPPORTED_LANGUAGES:
                    code = lang["code"]
                    editors[code].value = row.get(code, "")

            table.on("rowClick", lambda e: bind_selected(e.args[1]))

            with ui.element("div").classes("w-full max-h-[32vh] overflow-auto pr-1"):
                with ui.grid(columns=2).classes("w-full gap-2"):
                    for lang in SUPPORTED_LANGUAGES:
                        code = lang["code"]
                        editor = ui.textarea(label=lang["label"]).props("autogrow outlined")
                        editor.classes("w-full")
                        editors[code] = editor

            def save_row_changes() -> None:
                key = str(selected_row.get("key") or "")
                if not key:
                    ui.notify("Select a key in table first.", type="warning")
                    return
                for row in all_rows:
                    if row.get("key") == key:
                        for lang in SUPPORTED_LANGUAGES:
                            code = lang["code"]
                            row[code] = str(editors[code].value or "")
                        break
                apply_filter()
                ui.notify(f"Updated: {key}", type="positive")

            def persist_all() -> None:
                payload = import_rows(all_rows)
                save_translations(payload)
                ui.notify("Translations saved.", type="positive")

            with ui.row().classes("justify-end w-full gap-2"):
                ui.button("Apply row", on_click=save_row_changes).props("flat")
                ui.button("Save all", on_click=persist_all).props("color=primary")
