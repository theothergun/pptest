# pages/scripts_lab.py  (adjust module path to where your page file is)
from __future__ import annotations

import queue
import json

from nicegui import ui
from layout.context import PageContext

from services.worker_topics import WorkerTopics
from services.worker_commands import ScriptWorkerCommands as Commands


KEY_SCRIPTS_LIST = "script.scripts_list"
KEY_CHAINS_LIST = "script.chains_list"
KEY_CHAIN_STATE = "script.chain_state"
KEY_LOG = "script.log"


def _safe_json(value: object) -> str:
	try:
		return json.dumps(value, indent=2, ensure_ascii=False, default=str)
	except Exception:
		try:
			return str(value)
		except Exception:
			return "<unprintable>"


def render(container: ui.element, ctx: PageContext) -> None:
	with container:
		build_page(ctx)


def build_page(ctx: PageContext) -> None:
	worker_handle = ctx.workers.get("script_worker") if ctx.workers else None
	bus = ctx.workers.worker_bus if ctx.workers else None

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
	# ----------------------------

	ui.label("Scripts Lab").classes("text-2xl font-bold")

	with ui.row().classes("w-full gap-4"):
		with ui.card().classes("w-1/3"):
			ui.label("Scripts").classes("text-lg font-semibold")
			scripts_list = ui.list().classes("w-full")

		with ui.card().classes("w-2/3"):
			ui.label("Chains").classes("text-lg font-semibold")
			chains_col = ui.column().classes("w-full gap-2")

	with ui.card().classes("mt-4 w-full"):
		ui.label("Log").classes("text-lg font-semibold")
		log_area = ui.textarea(value="", label="").props("rows=10").classes("w-full")

	def _append_log(line: str) -> None:
		cur = log_area.value or ""
		if cur:
			cur = cur + "\n" + line
		else:
			cur = line
		lines = cur.splitlines()[-400:]
		log_area.set_value("\n".join(lines))

	def _render_scripts(items: list[str]) -> None:
		scripts_list.clear()
		with scripts_list:
			for s in items or []:
				ui.item(s)

	def _render_chains(items: list[dict]) -> None:
		chains_col.clear()
		if not items:
			with chains_col:
				ui.label("No running chains.").classes("text-sm text-gray-500")
			return

		with chains_col:
			for it in items:
				chain_key = str(it.get("key") or "")
				script = str(it.get("script") or "")
				instance = str(it.get("instance") or "")

				active = bool(it.get("active"))
				paused = bool(it.get("paused"))
				step = it.get("step", 0)
				cycle = it.get("cycle_count", 0)

				with ui.card().classes("w-full"):
					ui.label(chain_key).classes("font-semibold")
					ui.label("script=%s  instance=%s" % (script, instance)).classes("text-sm text-gray-600")
					ui.label("active=%s  paused=%s  step=%s  cycle=%s" % (active, paused, step, cycle)).classes("text-sm")

					with ui.row().classes("gap-2"):
						ui.button(
							"Stop",
							on_click=lambda ck=chain_key: worker_handle.send(Commands.STOP_CHAIN, chain_key=ck)
							if worker_handle
							else None,
						).props("color=negative")
						ui.button(
							"Pause",
							on_click=lambda ck=chain_key: worker_handle.send(Commands.PAUSE_CHAIN, chain_key=ck)
							if worker_handle
							else None,
						).props("color=warning")
						ui.button(
							"Resume",
							on_click=lambda ck=chain_key: worker_handle.send(Commands.RESUME_CHAIN, chain_key=ck)
							if worker_handle
							else None,
						).props("color=primary")

	# --------------------------
	# Bus subscription + drain
	# --------------------------
	if bus:
		sub_values = bus.subscribe(WorkerTopics.VALUE_CHANGED)
		page_subs.append(sub_values)
	else:
		sub_values = None

	def _drain_bus() -> None:
		if not sub_values:
			return
		while True:
			try:
				msg = sub_values.queue.get_nowait()
			except queue.Empty:
				break

			key = msg.payload.get("key")
			value = msg.payload.get("value")

			if key == KEY_SCRIPTS_LIST:
				_render_scripts(value or [])

			elif key == KEY_CHAINS_LIST:
				_render_chains(value or [])

			elif key == KEY_LOG:
				_append_log(_safe_json(value))

			# KEY_CHAIN_STATE is available if you want live per-chain state panels

	add_timer(0.2, _drain_bus)

	# initial snapshot request
	if worker_handle:
		worker_handle.send(Commands.LIST_SCRIPTS)
		worker_handle.send(Commands.LIST_CHAINS)
	else:
		ui.label("Script worker is not running.").classes("text-sm text-gray-500")
