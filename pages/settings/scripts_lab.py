from __future__ import annotations

import logging
import queue
import json
from pathlib import Path

from nicegui import ui

from layout.context import PageContext
from services.app_config import DEFAULT_CONFIG_PATH, load_app_config, save_app_config
from services.worker_commands import ScriptWorkerCommands as Commands
from pages.utils.safe_json import safe_format_data



def render(container: ui.element, ctx: PageContext) -> None:
	"""Render function matching router signature."""
	with container:
		build_page(ctx)


def _build_tree_from_script_paths(script_paths: list[str]) -> tuple[list[dict], set[str]]:
	"""
	Convert ["a", "tools/report", "tools/cleanup", "x/y/z"] into NiceGUI ui.tree nodes.
	Returns (nodes, leaf_ids).
	"""
	root: dict[str, dict] = {}

	for raw in script_paths or []:
		if not raw:
			continue

		path = str(raw).replace("\\", "/").strip("/")
		if not path:
			continue

		parts = [p for p in path.split("/") if p]
		cur = root
		for part in parts:
			cur = cur.setdefault(part, {})

	leaf_ids: set[str] = set()

	def to_nodes(subtree: dict, prefix: str = "") -> list[dict]:
		nodes: list[dict] = []
		for name in sorted(subtree.keys(), key=str.lower):
			child = subtree[name]
			node_id = "%s/%s" % (prefix, name) if prefix else name

			if child:
				nodes.append(
					{
						"id": node_id,
						"label": name,
						"icon": "folder",
						"children": to_nodes(child, node_id),
					}
				)
			else:
				leaf_ids.add(node_id)
				nodes.append(
					{
						"id": node_id,
						"label": name,
						"icon": "description",
					}
				)
		return nodes

	return to_nodes(root), leaf_ids


def build_page(ctx: PageContext) -> None:
	"""Scripts Lab page: bus-driven, stable cards, editor, and auto-scrolling logs."""

	worker_handle = ctx.workers.get("script_worker")
	bus = ctx.workers.worker_bus

	# --- lifecycle management ---
	page_timers: list = []
	page_subs: list = []

	def add_timer(*args, **kwargs):
		t = ui.timer(*args, **kwargs)
		page_timers.append(t)
		return t

	def cleanup() -> None:
		for sub in page_subs:
			try:
				sub.close()
			except Exception:
				pass
		page_subs[:] = []

		for t in page_timers:
			try:
				t.cancel()
			except Exception:
				pass
		page_timers[:] = []

	ctx.state._page_cleanup = cleanup
	ui.context.client.on_disconnect(cleanup)
	# --------------------------

	# Icon color styling (tree icons)
	ui.add_head_html("""
	<style>
	#scripts_tree .q-tree__node-header i.q-icon { color: #3b82f6 !important; }
	</style>
	""")

	# --------------------------
	# UI refs (filled during layout build)
	# --------------------------
	ui_refs: dict[str, object] = {
		"script_list_container": None,
		"chains_container": None,
		"empty_container": None,
		"empty_deleted": {"done": False},
		"log_view": None,
		"startup_container": None,
	}

	# --------------------------
	# Editor state
	# --------------------------
	scripts_tree = {"leaf_ids": set(), "selected_id": None, "selected_label": None}
	last_scripts_sig = {"sig": ""}
	startup_state = {"checkboxes": {}}

	scripts_dir = Path("scripts")
	editor = {"dialog": None, "textarea": None, "path": None, "script_name": None, "title": None}

	def _script_to_file(script_name: str) -> Path:
		script_name = (script_name or "").replace("\\", "/").strip("/")
		return scripts_dir / ("%s.py" % script_name)

	def _open_editor(script_name: str) -> None:
		if not script_name:
			ui.notify("Select a script first", type="negative")
			return

		path = _script_to_file(script_name)
		if not path.exists():
			ui.notify("Script file not found: %s" % str(path), type="negative")
			return

		try:
			text = path.read_text(encoding="utf-8")
		except Exception as e:
			ui.notify("Read failed: %s" % str(e), type="negative")
			return

		editor["path"] = path
		editor["script_name"] = script_name

		if editor["dialog"] is None:
			dlg = ui.dialog().props("maximized")
			editor["dialog"] = dlg
			with dlg, ui.card().classes("w-full h-full"):
				with ui.row().classes("w-full items-center gap-2"):
					title = ui.label("Edit Script").classes("text-lg font-bold")
					ui.space()
					ui.button("Save", icon="save").props("color=green").on("click", lambda: _save_editor())
					ui.button("Save + Reload", icon="refresh").props("color=blue").on("click", lambda: _save_editor(reload_after=True))
					ui.button("Close", icon="close").props("flat").on("click", lambda: dlg.close())

				editor["title"] = title

				ta = ui.codemirror(value="", language="Python").classes("w-full h-full")
				ta.props("autogrow=true")
				ta.style("height: calc(100vh - 140px); font-family: monospace;")
				editor["textarea"] = ta

		editor["title"].text = "Edit Script: %s" % script_name

		ta = editor["textarea"]
		try:
			ta.set_value(text)
		except Exception:
			ta.value = text

		editor["dialog"].open()

		try:
			ui.run_javascript("""
				setTimeout(() => {
					const cms = document.querySelectorAll('.cm-editor, .CodeMirror');
					cms.forEach(el => {
						if (el.CodeMirror) { el.CodeMirror.refresh(); }
					});
				}, 50);
			""")
		except Exception:
			pass

	def _save_editor(reload_after: bool = False) -> None:
		nonlocal editor
		path = editor.get("path")
		script_name = editor.get("script_name")
		ta = editor.get("textarea")
		if not path or not script_name or ta is None:
			ui.notify("Nothing to save", type="negative")
			return

		try:
			path.parent.mkdir(parents=True, exist_ok=True)
			path.write_text(ta.value or "", encoding="utf-8")
			ui.notify("Saved: %s" % str(path), type="positive")
		except Exception as e:
			ui.notify("Save failed: %s" % str(e), type="negative")
			return

		# Close editor state (forces rebuild next time)
		editor = {"dialog": None, "textarea": None, "path": None, "script_name": None, "title": None}

		# Reload + refresh list
		worker_handle.send(Commands.RELOAD_SCRIPT, script_name=script_name)
		worker_handle.send(Commands.LIST_SCRIPTS)

	def _start_chain(script_path: str) -> None:
		script = (script_path or "").strip()
		if not script:
			ui.notify("Please select a script", type="negative")
			return
		worker_handle.send(Commands.START_CHAIN, script_name=script, instance_id="default")
		ui.notify("Starting %s (default)" % script, type="info")

	def _load_config_data() -> dict:
		if not Path(DEFAULT_CONFIG_PATH).exists():
			cfg = load_app_config(DEFAULT_CONFIG_PATH)
			save_app_config(cfg, DEFAULT_CONFIG_PATH)
		with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
			return json.load(f)

	def _write_config_data(data: dict) -> None:
		Path(DEFAULT_CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
		with open(DEFAULT_CONFIG_PATH, "w", encoding="utf-8") as f:
			json.dump(data, f, indent=2, sort_keys=True)

	def _get_auto_start_scripts() -> list[str]:
		data = _load_config_data()
		chains = (
			data.get("workers", {})
			.get("configs", {})
			.get("script_worker", {})
			.get("auto_start_chains", [])
		)
		return [
			entry.get("script_name", "")
			for entry in chains
			if isinstance(entry, dict) and entry.get("script_name")
		]

	def _set_auto_start_scripts(scripts: list[str]) -> None:
		data = _load_config_data()
		data.setdefault("workers", {})
		data["workers"].setdefault("configs", {})
		data["workers"]["configs"].setdefault("script_worker", {})
		data["workers"]["configs"]["script_worker"]["auto_start_chains"] = [
			{"script_name": script, "instance_id": "default"} for script in scripts
		]
		_write_config_data(data)

	def _save_startup_scripts() -> None:
		selected = [
			script
			for script, checkbox in startup_state["checkboxes"].items()
			if getattr(checkbox, "value", False)
		]
		_set_auto_start_scripts(selected)
		ui.notify("Startup scripts updated.", type="positive")

	# --------------------------
	# Chain cards (stable, no recreate)
	# --------------------------
	chain_cards: dict[str, dict] = {}

	def _status_text(active: bool, paused: bool, crashed: bool = False) -> str:
		if crashed:
			return "Crashed"
		if not active:
			return "Stopped"
		if paused:
			return "Paused"
		return "Running"

	def _status_color(active: bool, paused: bool, crashed: bool = False) -> str:
		if crashed:
			return "red"
		if not active:
			return "red"
		if paused:
			return "orange"
		return "green"

	def _start_chain_for_card(chain_key: str) -> None:
		w = chain_cards.get(chain_key)
		if not w:
			ui.notify("Chain not found", type="negative")
			return
		script_name = (w.get("script") or "").strip()
		instance_id = (w.get("instance") or "default").strip() or "default"
		if not script_name:
			ui.notify("Missing script name for start", type="negative")
			return
		worker_handle.send(Commands.START_CHAIN, script_name=script_name, instance_id=instance_id)
		ui.notify("Starting %s (%s)" % (script_name, instance_id), type="info")

	def _format_step_time(step_time_val) -> str:
		if step_time_val is None:
			return ""
		try:
			if isinstance(step_time_val, (int, float)):
				if step_time_val < 0:
					return ""
				if step_time_val == int(step_time_val):
					return "%sms" % int(step_time_val)
				return "%sms" % step_time_val
			s = str(step_time_val).strip()
			if not s or s == "-1":
				return ""
			return s
		except Exception:
			return ""

	def _ensure_chain_card(chain: dict) -> None:
		chains_container = ui_refs.get("chains_container")
		if chains_container is None:
			return

		chain_key = chain.get("key", "unknown")
		if chain_key in chain_cards:
			return

		with chains_container:
			card = ui.card().classes()
			card2 = ui.card().classes()

		with card:
			with ui.row().classes("w-full items-center gap-2 mb-2"):
				ui.icon("code")
				ui.label("%s" % chain.get("script", "unknown")).classes("text-lg font-bold flex-grow")
				badge = ui.badge("", color="green")

			with ui.grid(columns=2).classes("w-full gap-2 mb-2"):
				ui.label("Instance:").classes("font-semibold")
				ui.label(chain.get("instance", "default"))

				ui.label("Current Step:").classes("font-semibold")
				with ui.row().classes("items-center gap-2"):
					step_label = ui.label("").classes("text-blue-600 font-mono text-lg")
					step_time_label = ui.label("").classes("text-gray-500 font-mono text-lg")

				ui.label("Step Text:").classes("font-semibold")
				step_text = ui.label("").classes("text-blue-600 font-mono text-lg")

				ui.label("Cycles:").classes("font-semibold")
				cycles_label = ui.label("").classes("text-gray-600")

			with ui.row().classes("w-full gap-2"):
				btn_pause = ui.button(
					"Pause",
					icon="pause",
					on_click=lambda ck=chain_key: worker_handle.send(Commands.PAUSE_CHAIN, chain_key=ck),
				).props("color=orange flat dense")

				btn_resume = ui.button(
					"Resume",
					icon="play_arrow",
					on_click=lambda ck=chain_key: worker_handle.send(Commands.RESUME_CHAIN, chain_key=ck),
				).props("color=green flat dense")

				btn_retry = ui.button(
					"Retry",
					icon="replay",
					on_click=lambda ck=chain_key: worker_handle.send(Commands.RETRY_CHAIN, chain_key=ck),
				).props("color=primary unelevated dense")

				btn_start = ui.button(
					"Start",
					icon="play_arrow",
					on_click=lambda ck=chain_key: _start_chain_for_card(ck),
				).props("color=green flat dense")

				btn_stop = ui.button(
					"Stop",
					icon="stop",
					on_click=lambda ck=chain_key: worker_handle.send(Commands.STOP_CHAIN, chain_key=ck),
				).props("color=red flat dense")

				ui.button(
					"Reload Script",
					icon="refresh",
					on_click=lambda sn=chain.get("script", "unknown"): worker_handle.send(Commands.RELOAD_SCRIPT, script_name=sn),
				).props("color=blue flat dense").tooltip("Hot-reload this script")

		with card2:
			data = ui.json_editor({
				"content": {"json": {}},
				"readOnly": True,
				"mode": "tree",  # or "view" / "text"
			})

		chain_cards[chain_key] = {
			"card": card,
			"card2": card2,
			"badge": badge,
			"step_label": step_label,
			"step_time_label": step_time_label,
			"cycles_label": cycles_label,
			"step_desc": step_text,
			"data": data,

			"btn_pause": btn_pause,
			"btn_resume": btn_resume,
			"btn_retry": btn_retry,
			"btn_start": btn_start,
			"btn_stop": btn_stop,

			"script": chain.get("script", "unknown"),
			"instance": chain.get("instance", "default"),
		}

	def _set_visible(el, is_visible: bool) -> None:
		# NiceGUI supports .visible on newer versions; keep a style fallback.
		try:
			el.visible = bool(is_visible)
			return
		except Exception:
			pass
		try:
			el.style("display: %s;" % ("inline-flex" if is_visible else "none"))
		except Exception:
			pass

	def _update_chain_card(chain: dict) -> None:
		chain_key = chain.get("key", "unknown")
		w = chain_cards.get(chain_key)
		if not w:
			return
		active = bool(chain.get("active", False))
		paused = bool(chain.get("paused", False))
		error_flag = bool(chain.get("error_flag", False))
		step = chain.get("step", 0)
		data = chain.get("data", {})
		cycle_count = chain.get("cycle_count", 0)
		step_desc = chain.get("step_desc", "")
		step_time = chain.get("step_time", None)

		# keep script/instance updated for "Start" button usage
		if "script" in chain and chain.get("script") is not None:
			w["script"] = chain.get("script", w.get("script", "unknown"))
		if "instance" in chain and chain.get("instance") is not None:
			w["instance"] = chain.get("instance", w.get("instance", "default"))

		status_text = _status_text(active, paused, error_flag)
		status_color = _status_color(active, paused, error_flag)

		w["badge"].text = status_text
		try:
			w["badge"].props("color=%s" % status_color)
		except Exception:
			pass

		# Show as "[ 5 , 6ms ]" (no extra label inside the value field)
		st_str = _format_step_time(step_time)
		if st_str:
			w["step_label"].text = " %s - " % step
			w["step_time_label"].text = "%s " % st_str
		else:
			w["step_label"].text = "[ %s ]" % step
			w["step_time_label"].text = ""

		w["cycles_label"].text = str(cycle_count)
		w["step_desc"].text = step_desc
		je = w["data"]
		payload = data # safe_format_data(data)
		if len(payload) < 1:
			return
		print (payload)
		try:
			#je.properties.setdefault("content", {})
			je.properties["content"]["json"] = payload
		except Exception:
			pass

		# refresh widget (version dependent)
		try:
			pass
			# NiceGUI 2.x typically works:
			#je.update()
		except Exception:
			# NiceGUI 3.x workaround:
			try:
				pass
				#je.run_editor_method("update", payload)
			except Exception:
				pass

		# Button visibility rules:
		# - Resume hidden unless paused
		# - Start shown only when stopped
		show_pause = active and (not paused) and (not error_flag)
		show_resume = active and paused and (not error_flag)
		show_retry = active and paused and error_flag
		show_start = not active
		show_stop = active

		_set_visible(w["btn_pause"], show_pause)
		_set_visible(w["btn_resume"], show_resume)
		_set_visible(w["btn_retry"], show_retry)
		_set_visible(w["btn_start"], show_start)
		_set_visible(w["btn_stop"], show_stop)

	def _apply_chains_snapshot(chains: list[dict]) -> None:
		empty_container = ui_refs.get("empty_container")
		empty_deleted = ui_refs.get("empty_deleted")
		if empty_container is None or empty_deleted is None:
			return

		keys_now = set([(c.get("key", "unknown")) for c in (chains or [])])

		for old_key in list(chain_cards.keys()):
			if old_key not in keys_now:
				try:
					chain_cards[old_key]["card"].delete()
					chain_cards[old_key]["card2"].delete()
				except Exception:
					pass
				chain_cards.pop(old_key, None)

		if not chains:
			if not chain_cards:
				empty_container.clear()
				with empty_container:
					ui.label("No running chains").classes("text-gray-500")
					ui.label("Start a chain by selecting a script on the left").classes("text-xs text-gray-400")
			return

		if not empty_deleted["done"]:
			empty_container.clear()
			empty_deleted["done"] = True

		for chain in chains:
			chain_key = chain.get("key", "unknown")
			if chain_key not in chain_cards:
				_ensure_chain_card(chain)
			_update_chain_card(chain)

	# --------------------------
	# Logs (ui.log auto-scroll + last 100 lines)
	# --------------------------
	def _clear_logs() -> None:
		log_view = ui_refs.get("log_view")
		if log_view is None:
			return
		try:
			log_view.clear()
		except Exception:
			pass

	def _append_log(line: str) -> None:
		log_view = ui_refs.get("log_view")
		if log_view is None:
			return
		try:
			log_view.push(line)
		except Exception:
			pass

	# --------------------------
	# Render scripts tree only when scripts list changes
	# --------------------------
	def _render_scripts_tree(script_paths: list[str]) -> None:
		container = ui_refs.get("script_list_container")
		if container is None:
			return

		sig = "|".join(script_paths or [])
		if sig == last_scripts_sig["sig"]:
			return
		last_scripts_sig["sig"] = sig

		container.clear()

		with container:
			scripts = script_paths or []
			if not scripts:
				ui.label("No scripts found").classes("text-gray-500")
				ui.label("(Add .py files to 'scripts/' directory)").classes("text-xs text-gray-400")
				return

			nodes, leaf_ids = _build_tree_from_script_paths(scripts)
			scripts_tree["leaf_ids"] = leaf_ids

			scripts_tree["selected_label"] = ui.label("Select a script from the tree").classes("text-xs text-gray-500")

			def on_select(e) -> None:
				node_id = getattr(e, "value", None)
				if node_id and node_id in scripts_tree["leaf_ids"]:
					scripts_tree["selected_id"] = node_id
					scripts_tree["selected_label"].text = "Selected: %s" % node_id
				else:
					scripts_tree["selected_id"] = None
					scripts_tree["selected_label"].text = "Select a script from the tree"

			with ui.element("div").props("id=scripts_tree").classes("w-full"):
				tree = ui.tree(nodes, label_key="label", on_select=on_select).classes("w-full")
				tree.props("dense")

		startup_container = ui_refs.get("startup_container")
		if startup_container is not None:
			startup_container.clear()
			startup_state["checkboxes"] = {}
			auto_start = set(_get_auto_start_scripts())
			with startup_container:
				ui.label("Start on startup").classes("text-sm font-semibold")
				ui.label("Select scripts to auto-start (default instance).").classes("text-xs text-gray-500")
				for script in scripts:
					startup_state["checkboxes"][script] = ui.checkbox(script, value=script in auto_start)
				ui.button("Save startup scripts", on_click=_save_startup_scripts).props("color=primary").classes("mt-2")

	# --------------------------
	# Hot reload toggle (UI -> worker)
	# --------------------------
	def _send_hot_reload_setting(enabled: bool) -> None:
		try:
			worker_handle.send(Commands.SET_HOT_RELOAD, enabled=bool(enabled), interval=1.0)
		except Exception:
			pass

	# --------------------------
	# Layout
	# --------------------------
	with ui.column().classes("w-full h-full flex flex-col min-h-0"):
		# Header
		with ui.row().classes("w-full items-center gap-4 mb-4"):
			ui.label("📜 Scripts Lab").classes("text-2xl font-bold")
			ui.space()

			hot_reload_toggle = ui.switch("Hot Reload (1s)", value=False)
			hot_reload_toggle.on_value_change(lambda e: _send_hot_reload_setting(bool(getattr(e, "value", False))))

			ui.button(
				"Reload All Scripts",
				icon="refresh",
				on_click=lambda: worker_handle.send(Commands.RELOAD_ALL),
			).props("color=blue outline")

		# Content area that can grow
		with ui.column().classes("w-full flex-1 min-h-0 gap-4"):
			# Top two cards
			with ui.grid().classes("w-full gap-4").style("grid-template-columns: max-content 1fr;"):
				# Available scripts
				with ui.card().classes("w-full"):
					ui.label("Available Scripts").classes("text-lg font-bold mb-2")
					ui_refs["script_list_container"] = ui.column().classes("w-full gap-2")
					ui_refs["startup_container"] = ui.column().classes("w-full gap-2 mt-4")

					def start_selected() -> None:
						node_id = scripts_tree["selected_id"]
						if not node_id:
							ui.notify("Please select a script leaf first", type="negative")
							return
						_start_chain(node_id)

					def edit_selected() -> None:
						node_id = scripts_tree["selected_id"]
						if not node_id:
							ui.notify("Please select a script leaf first", type="negative")
							return
						_open_editor(node_id)

					with ui.row().classes("w-full gap-2"):
						ui.button("Start Selected", icon="play_arrow", on_click=start_selected).props("color=green").classes("w-full")
						ui.button("Edit", icon="edit", on_click=edit_selected).props("color=blue outline").classes("w-full")

					ui.button(
						"Refresh List",
						icon="refresh",
						on_click=lambda: worker_handle.send(Commands.LIST_SCRIPTS),
					).props("color=blue flat").classes("w-full")

				# Running chains
				with ui.card().classes("w-full"):
					ui.label("Running Chains").classes("text-lg font-bold mb-2")

					ui_refs["empty_deleted"] = {"done": False}
					ui_refs["empty_container"] = ui.column().classes("w-full gap-2")
					chains_container = ui.column().classes("w-full grid grid-cols-2 gap-4 items-start")
					ui_refs["chains_container"] = chains_container

					with ui.row().classes("w-full items-center gap-2"):
						ui.button(
							"Refresh Now",
							icon="refresh",
							on_click=lambda: worker_handle.send(Commands.LIST_CHAINS),
						).props("flat color=blue")

			# Bottom logs
			with ui.card().classes("w-full flex-1 min-h-100"):
				with ui.column().classes("w-full h-full"):
					with ui.row().classes("w-full items-center"):
						ui.label("Script Logs (last 100)").classes("text-lg font-bold")
						ui.space()
						ui.button(
							"Clear logs",
							icon="delete",
							on_click=_clear_logs,
						).props("flat color=grey")

					ui_refs["log_view"] = (
						ui.log(max_lines=100)
						.classes("w-full flex-1 min-h-50 max-h-50")
						.style("overflow-y: auto")
					)

	# initial empty hint
	_apply_chains_snapshot([])

	# --------------------------
	# Bus subscription (NEW CONTRACT)
	#   - subscribe("*")
	#   - msg.payload: { key, source_id, value }
	# --------------------------
	sub_all = bus.subscribe("*")
	page_subs.append(sub_all)

	latest_scripts = {"value": None}
	latest_chains = {"value": None}
	crash_dialog_seen: dict[str, str] = {}
	active_crash_dialogs: dict[str, ui.dialog] = {}

	def _show_crash_dialog(chain_key: str, message: str) -> None:
		msg = str(message or "StepChain crashed.")
		if chain_key in active_crash_dialogs:
			return
		sig = "%s|%s" % (chain_key, msg)
		if crash_dialog_seen.get(chain_key) == sig:
			return
		crash_dialog_seen[chain_key] = sig

		dlg = ui.dialog()
		active_crash_dialogs[chain_key] = dlg
		with dlg, ui.card().classes("w-[520px] max-w-full"):
			ui.label("⚠️ StepChain stopped due to an error").classes("text-lg font-bold text-red-700")
			ui.label("Chain: %s" % chain_key).classes("text-sm text-gray-700")
			ui.label(msg).classes("text-sm")
			ui.label("What should the operator do?").classes("text-sm font-semibold mt-2")
			with ui.row().classes("w-full gap-2 mt-2"):
				ui.button("Retry", icon="replay", on_click=lambda ck=chain_key, d=dlg: (worker_handle.send(Commands.RETRY_CHAIN, chain_key=ck), d.close())).props("color=primary")
				ui.button("Stop chain", icon="stop", on_click=lambda ck=chain_key, d=dlg: (worker_handle.send(Commands.STOP_CHAIN, chain_key=ck), d.close())).props("color=negative")
				ui.button("Close", on_click=dlg.close).props("flat")
		dlg.on("hide", lambda e=None, ck=chain_key: active_crash_dialogs.pop(ck, None))
		dlg.open()

	def _drain_bus() -> None:
		while True:
			try:
				msg = sub_all.queue.get_nowait()
			except queue.Empty:
				break
			key = msg.payload.get("key")

			# scripts list snapshot
			if key == Commands.LIST_SCRIPTS:
				latest_scripts["value"] = msg.payload.get("value")

			# chains list snapshot
			elif key == Commands.LIST_CHAINS:
				latest_chains["value"] = msg.payload.get("value")

			# per-chain state updates (optional; you already have list snapshots)
			elif key == Commands.UPDATE_CHAIN_STATE:
				try:
					val = msg.payload.get("value") or {}
					chain_key = val.get("chain_key") or val.get("chain_id") or "unknown"
					state = val

					error_message = state.get("error_message", "") or ""
					step_desc = state.get("step_desc", "") or ""
					merged_step_desc = ("%s %s" % (error_message, step_desc)).strip()

					error_flag = bool(state.get("error_flag", False))
					if error_flag:
						_show_crash_dialog(chain_key, error_message)
					else:
						crash_dialog_seen.pop(chain_key, None)
						dlg = active_crash_dialogs.pop(chain_key, None)
						if dlg is not None:
							try:
								dlg.close()
							except Exception:
								pass

					if chain_key in chain_cards:
						_update_chain_card(
							{
								"key": chain_key,
								"script": state.get("script_name", chain_key.split(":")[0] if ":" in chain_key else chain_key),
								"instance": state.get("instance_id", "default"),
								"active": bool(state.get("active", True)),
								"paused": bool(state.get("paused", False)),
								"error_flag": bool(state.get("error_flag", False)),
								"error_message": state.get("error_message", ""),
								"step": state.get("step", 0),
								"cycle_count": state.get("cycle_count", 0),
								"step_desc": merged_step_desc,
								"data": state.get("data", {}),
								"step_time": state.get("step_time", None),
							}
						)
				except Exception as ex:
					logging.error(ex)

			# log lines
			elif key == Commands.UPDATE_LOG:
				payload = msg.payload.get("value") or {}
				step = payload.get("step", "?")
				step_desc = payload.get("step_desc", "?")
				level = payload.get("level", "info")
				message = payload.get("message", "")
				line = "[%s] %s:%s step=%s - %s" % (str(level).upper(), step, step_desc, step, message)
				_append_log(line)

		# Apply snapshots once per tick (use last seen)
		if latest_scripts["value"] is not None:
			val = latest_scripts["value"]
			if isinstance(val, list):
				_render_scripts_tree(val)
			else:
				_render_scripts_tree([])
			latest_scripts["value"] = None

		if latest_chains["value"] is not None:
			val = latest_chains["value"]
			if isinstance(val, list):
				_apply_chains_snapshot(val)
			else:
				_apply_chains_snapshot([])
			latest_chains["value"] = None

	# drains local queues only (no worker polling)
	add_timer(0.1, _drain_bus)

	# initial snapshots
	worker_handle.send(Commands.LIST_SCRIPTS)
	worker_handle.send(Commands.LIST_CHAINS)

	# Ensure worker matches initial UI toggle state (default OFF)
	_send_hot_reload_setting(False)
