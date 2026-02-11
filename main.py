import os
import queue
from nicegui import ui, app

from auth.middleware import AuthMiddleware
from auth.login_page import register_login_page

from layout.context import PageContext
from layout.main_area import build_main_area
from layout.router import navigate, get_initial_route_from_url
from layout.header import build_header
from layout.drawer import build_drawer
from layout.errors_state import refresh_errors_count

from services.ui_bridge import UiBridge
from services.worker_registry import WorkerRegistry
from services.worker_bus import WorkerBus
from services.worker_names import WorkerName
from services.app_config import (
	load_app_config,
	get_rest_api_endpoints,
	get_tcp_client_entries,
	get_script_auto_start_chains,
	get_twincat_plc_endpoints,
)

from services.worker_commands import (
	TcpClientCommands as TCPCommands,
	ScriptWorkerCommands as ScriptCommands,
	RestApiCommands as RestCommands,
	TwinCatCommands,
)

from services.app_state import AppState
from services.logging_setup import setup_logging
from loguru import logger


# ------------------------------------------------------------------
# GLOBAL BACKEND (PROCESS LIFETIME)
# ------------------------------------------------------------------

setup_logging(app_name="mes_app", log_level="DEBUG")
logger.info("Starting NiceGUI")

APP_CONFIG = load_app_config()

GLOBAL_WORKER_BUS = WorkerBus()
GLOBAL_BRIDGE = UiBridge()
GLOBAL_APP_STATE = AppState()

GLOBAL_WORKERS = WorkerRegistry(GLOBAL_BRIDGE, GLOBAL_WORKER_BUS)


# ------------------------------------------------------------------
# Start workers ONCE
# ------------------------------------------------------------------
from services.workers.tcp_client_worker import TcpClientWorker
from services.workers.twincat_worker import TwinCatWorker
from services.workers.script_worker import ScriptWorker


WORKER_CATALOG = {
	WorkerName.TCP_CLIENT: TcpClientWorker,
	WorkerName.TWINCAT: TwinCatWorker,
    WorkerName.SCRIPT: ScriptWorker,
}

for worker_name in APP_CONFIG.workers.enabled_workers:
	target = WORKER_CATALOG.get(worker_name)
	if not target:
		logger.warning("Unknown worker in config: {}", worker_name)
		continue
	GLOBAL_WORKERS.start_worker(worker_name, target)


# ------------------------------------------------------------------
# Bootstrap worker configs
# ------------------------------------------------------------------

tcp_handle = GLOBAL_WORKERS.get(WorkerName.TCP_CLIENT)
if tcp_handle:
	for client in get_tcp_client_entries(APP_CONFIG):
		tcp_handle.send(
			TCPCommands.ADD_CLIENT,
			client_id=client.client_id,
			host=client.host,
			port=client.port,
			connect=client.connect,
			mode=client.mode,
			delimiter=client.delimiter,
			encoding=client.encoding,
			auto_reconnect=client.auto_reconnect,
			reconnect_min_s=client.reconnect_min_s,
			reconnect_max_s=client.reconnect_max_s,
			keepalive=client.keepalive,
			tcp_nodelay=client.tcp_nodelay,
		)

script_handle = GLOBAL_WORKERS.get(WorkerName.SCRIPT)
if script_handle:
	for chain in get_script_auto_start_chains(APP_CONFIG):
		script_handle.send(
			ScriptCommands.START_CHAIN,
			script_name=chain.get("script_name"),
			instance_id=chain.get("instance_id", "default"),
		)

rest_handle = GLOBAL_WORKERS.get(WorkerName.REST_API)
if rest_handle:
	for endpoint in get_rest_api_endpoints(APP_CONFIG):
		rest_handle.send(
			RestCommands.ADD_ENDPOINT,
			name=endpoint.name,
			base_url=endpoint.base_url,
			headers=endpoint.headers,
			timeout_s=endpoint.timeout_s,
			verify_ssl=endpoint.verify_ssl,
		)

twincat_handle = GLOBAL_WORKERS.get(WorkerName.TWINCAT)
if twincat_handle:
	for client in get_twincat_plc_endpoints(APP_CONFIG):
		twincat_handle.send(
			TwinCatCommands.ADD_PLC,
			client_id=client.client_id,
			plc_ip=client.plc_ip,
			plc_ams_net_id=client.plc_ams_net_id,
			ads_port=client.ads_port,
			subscriptions=client.subscriptions,
			default_trans_mode=client.default_trans_mode,
			default_cycle_ms=client.default_cycle_ms,
			default_string_len=client.default_string_len,
		)


# ------------------------------------------------------------------
# UI
# ------------------------------------------------------------------

HEADER_PX = 64
FOOTER_PX = 0

register_login_page()
if APP_CONFIG.auth.login_required:
	app.add_middleware(AuthMiddleware)


@ui.page("/")
def index():
	ui.colors(primary="#3b82f6")

	ui.add_head_html("""
	<style>
		html, body { height: 100%; margin: 0; overflow: hidden; }
		@keyframes error-pulse {
			0%, 100% { transform: scale(1); opacity: 1; }
			50% { transform: scale(1.15); opacity: 0.7; }
		}
		.error-badge-pulse { animation: error-pulse 1s infinite; }
	</style>
	""")

	# --------- PER SESSION CONTEXT ---------
	ctx = PageContext()
	ctx.state = GLOBAL_APP_STATE
	ctx.worker_bus = GLOBAL_WORKER_BUS
	ctx.workers = GLOBAL_WORKERS
	ctx.bridge = GLOBAL_BRIDGE

	refresh_errors_count(ctx)

	# UI flush loop
	ui.timer(0.5, lambda: ctx.bridge.flush(ctx))

	# Global StepChain crash dialog (works on every route/view)
	sub_script_state = ctx.worker_bus.subscribe("VALUE_CHANGED")
	crash_dialog_seen: dict[str, str] = {}
	active_crash_dialogs: dict[str, ui.dialog] = {}

	def _open_chain_crash_dialog(chain_key: str, message: str) -> None:
		msg = str(message or "StepChain crashed.")
		if chain_key in active_crash_dialogs:
			return
		sig = "%s|%s" % (chain_key, msg)
		if crash_dialog_seen.get(chain_key) == sig:
			return
		crash_dialog_seen[chain_key] = sig

		dlg = ui.dialog()
		active_crash_dialogs[chain_key] = dlg
		with dlg, ui.card().classes("w-[540px] max-w-full"):
			ui.label("⚠️ StepChain stopped due to an error").classes("text-lg font-bold text-red-700")
			ui.label("Chain: %s" % chain_key).classes("text-sm text-gray-700")
			ui.label(msg).classes("text-sm")
			ui.label("Choose an action:").classes("text-sm font-semibold mt-2")
			with ui.row().classes("w-full gap-2 mt-2"):
				ui.button(
					"Retry",
					icon="replay",
					on_click=lambda ck=chain_key, d=dlg: (_send_retry(ck), d.close()),
				).props("color=primary")
				ui.button(
					"Stop chain",
					icon="stop",
					on_click=lambda ck=chain_key, d=dlg: (_send_stop(ck), d.close()),
				).props("color=negative")
				ui.button("Close", on_click=dlg.close).props("flat")
		dlg.on("hide", lambda e=None, ck=chain_key: active_crash_dialogs.pop(ck, None))
		dlg.open()

	def _send_retry(chain_key: str) -> None:
		h = ctx.workers.get(WorkerName.SCRIPT) if ctx.workers else None
		if not h:
			ui.notify("Script worker not available", type="negative")
			return
		h.send(ScriptCommands.RETRY_CHAIN, chain_key=chain_key)

	def _send_stop(chain_key: str) -> None:
		h = ctx.workers.get(WorkerName.SCRIPT) if ctx.workers else None
		if not h:
			ui.notify("Script worker not available", type="negative")
			return
		h.send(ScriptCommands.STOP_CHAIN, chain_key=chain_key)

	def _drain_script_crashes() -> None:
		while True:
			try:
				msg = sub_script_state.queue.get_nowait()
			except queue.Empty:
				break

			payload = getattr(msg, "payload", None) or {}
			if payload.get("key") != ScriptCommands.UPDATE_CHAIN_STATE:
				continue
			value = payload.get("value") or {}
			if not isinstance(value, dict):
				continue
			chain_key = str(value.get("chain_key") or value.get("chain_id") or "unknown")
			if not bool(value.get("error_flag", False)):
				# Clear dedupe state when chain recovered, so next crash opens popup again
				crash_dialog_seen.pop(chain_key, None)
				dlg = active_crash_dialogs.pop(chain_key, None)
				if dlg is not None:
					try:
						dlg.close()
					except Exception:
						pass
				continue

			error_message = str(value.get("error_message") or "StepChain crashed.")
			_open_chain_crash_dialog(chain_key, error_message)

	crash_timer = ui.timer(0.2, _drain_script_crashes)

	def _cleanup_crash_watcher() -> None:
		try:
			sub_script_state.close()
		except Exception:
			pass
		try:
			crash_timer.cancel()
		except Exception:
			pass

	ui.context.client.on_disconnect(_cleanup_crash_watcher)

	# --------- LAYOUT ---------
	build_header(ctx)
	build_drawer(ctx)

	with ui.row().classes("w-full").style(
		f"height: calc(100vh - {HEADER_PX}px - {FOOTER_PX}px);"
	):
		with ui.column().classes("w-full h-full min-h-0 min-w-0 overflow-hidden p-4 pb-6 gap-4"):
			build_main_area(ctx)

	default_route = app.storage.user.get(
		"current_route", APP_CONFIG.ui.navigation.main_route
	)
	initial = get_initial_route_from_url(default_route)
	navigate(ctx, initial)


ui.run(
	title="KE-Elektronik-Shopfloorapp",
	reload=False,
	storage_secret=os.environ["NICEGUI_STORAGE_SECRET"],
)
