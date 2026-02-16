from __future__ import annotations

from nicegui import ui

from layout.context import PageContext
from services.app_config import get_app_config, save_app_config


def render(container: ui.element, _ctx: PageContext) -> None:
	with container.classes("w-full"):
		cfg = get_app_config()
		nav = cfg.ui.navigation

		routes = list(nav.custom_routes or [])
		options: dict[str, str] = {}
		for r in routes:
			key = str(r.get("key") or "").strip()
			if not key:
				continue
			label = str(r.get("label") or key).strip()
			options[key] = f"{label} ({key})"

		# fallback in case custom_routes is empty
		if not options:
			options["home"] = "Home (home)"

		current = str(nav.main_route or "home")
		if current not in options:
			options[current] = f"{current} ({current})"

		with ui.card().classes("w-full"):
			ui.label("Startup Page").classes("text-xl font-semibold")
			ui.label("Choose which page should open by default.").classes("text-sm text-gray-500")

			startup_route = ui.select(
				options=options,
				value=current,
				label="Startup route",
			).props("outlined").classes("w-full")

			ui.label(
				"Note: if a browser has a previously saved current route, that can override startup route for that user."
			).classes("text-xs text-gray-500")

			def save_startup() -> None:
				cfg = get_app_config()
				cfg.ui.navigation.main_route = str(startup_route.value or "home")
				save_app_config(cfg)
				ui.notify("Startup page updated.", type="positive")

			with ui.row().classes("w-full justify-end"):
				ui.button("Save", on_click=save_startup).props("color=primary")

