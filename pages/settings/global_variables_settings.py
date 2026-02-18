from __future__ import annotations

import copy
import json
from typing import Any

from nicegui import ui

from layout.context import PageContext
from services.app_config import get_app_config, save_app_config


def _extract_json_object(content: Any) -> dict[str, Any] | None:
	if isinstance(content, dict):
		json_obj = content.get("json")
		if isinstance(json_obj, dict):
			return dict(json_obj)
		text_obj = content.get("text")
		if isinstance(text_obj, str):
			try:
				parsed = json.loads(text_obj)
				if isinstance(parsed, dict):
					return parsed
			except Exception:
				return None
	return None


def render(container: ui.element, _ctx: PageContext) -> None:
	with container.classes("w-full"):
		cfg = get_app_config()
		current = cfg.global_vars if isinstance(cfg.global_vars, dict) else {}
		state: dict[str, Any] = {"json": copy.deepcopy(current)}

		with ui.card().classes("w-full gap-3"):
			ui.label("Global Variables").classes("text-xl font-semibold")
			ui.label("Edit config-backed variables available to scripts. Root must be a JSON object.").classes("text-sm text-gray-500")
			ui.label("Script API: ctx.global_var('key'), ctx.global_vars(), ctx.values.global_var('key')").classes("text-xs text-gray-500")

			editor = ui.json_editor({
				"content": {"json": state["json"]},
				"mode": "tree",
				"mainMenuBar": True,
				"navigationBar": True,
				"statusBar": True,
			}).classes("w-full")
			editor.style("min-height: 420px;")

			def on_change(e: Any) -> None:
				parsed = _extract_json_object(getattr(e, "content", None))
				if parsed is not None:
					state["json"] = parsed

			editor.on_change(on_change)

			def reload_from_config() -> None:
				cfg_local = get_app_config()
				reloaded = cfg_local.global_vars if isinstance(cfg_local.global_vars, dict) else {}
				state["json"] = copy.deepcopy(reloaded)
				editor.properties["content"] = {"json": state["json"]}
				editor.update()
				ui.notify("Reloaded global variables from config.", type="info")

			async def save_variables() -> None:
				latest = state.get("json", {})
				try:
					content = await editor.run_editor_method("get", timeout=2)
					parsed = _extract_json_object(content)
					if parsed is not None:
						latest = parsed
				except Exception:
					pass

				if not isinstance(latest, dict):
					ui.notify("Global variables must be a JSON object.", type="negative")
					return

				cfg_local = get_app_config()
				cfg_local.global_vars = dict(latest)
				save_app_config(cfg_local)
				state["json"] = copy.deepcopy(latest)
				ui.notify("Global variables saved.", type="positive")

			with ui.row().classes("w-full justify-end gap-2"):
				ui.button("Reload", on_click=reload_from_config).props("outline")
				ui.button("Save", on_click=save_variables).props("color=primary")
