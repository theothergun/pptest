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
from layout.device_panel import build_device_panel
from layout.errors_state import refresh_errors_count
from layout.modal_manager import install_modal_manager
from pages.dummy.dummy_service import DummyController

from services.ui_bridge import UiBridge
from services.worker_registry import WorkerRegistry
from services.worker_bus import WorkerBus
from services.worker_names import WorkerName
from services.app_config import (
	load_app_config,
	get_app_config,
	get_rest_api_endpoints,
	get_tcp_client_entries,
	get_script_auto_start_chains,
	get_twincat_plc_endpoints,
	get_itac_endpoints,
	get_com_device_entries,
	get_opcua_endpoints,
)

from services.worker_commands import (
	TcpClientCommands as TCPCommands,
	ScriptWorkerCommands as ScriptCommands,
	RestApiCommands as RestCommands,
	TwinCatCommands,
	ItacCommands,
	OpcUaCommands,

)

from services.app_state import AppState
from services.logging_setup import (
	setup_logging,
	get_error_popup_events_since,
	get_latest_error_popup_event_id,
)
from services.i18n import bootstrap_defaults
from services.ui_theme import apply_ui_theme
from loguru import logger


# ------------------------------------------------------------------
# GLOBAL BACKEND (PROCESS LIFETIME)
# ------------------------------------------------------------------

setup_logging(app_name="mes_app", log_level="DEBUG")
logger.info("Starting NiceGUI")
bootstrap_defaults()

def _apply_proxy_env(cfg) -> None:
	# process-local; affects only this app process
	try:
		p = getattr(cfg, "proxy", None)
		if not p or not getattr(p, "enabled", False):
			return

		if getattr(p, "http", ""):
			os.environ["HTTP_PROXY"] = p.http
			os.environ["http_proxy"] = p.http

		if getattr(p, "https", ""):
			os.environ["HTTPS_PROXY"] = p.https
			os.environ["https_proxy"] = p.https

		if getattr(p, "no_proxy", ""):
			os.environ["NO_PROXY"] = p.no_proxy
			os.environ["no_proxy"] = p.no_proxy

	except Exception:
		logger.exception("Failed applying proxy environment from config")
		return

APP_CONFIG = load_app_config()
_apply_proxy_env(APP_CONFIG)

GLOBAL_WORKER_BUS = WorkerBus()
GLOBAL_BRIDGE = UiBridge()
GLOBAL_APP_STATE = AppState()
DUMMY_CONTROLLER = DummyController()
GLOBAL_WORKERS = WorkerRegistry(GLOBAL_BRIDGE, GLOBAL_WORKER_BUS)


# ------------------------------------------------------------------
# Start workers ONCE
# ------------------------------------------------------------------
from services.workers.tcp_client_worker import TcpClientWorker
from services.workers.twincat_worker import TwinCatWorker
from services.workers.script_worker import ScriptWorker
from services.workers.itac_worker import ItacWorker
from services.workers.rest_api_worker import RestApiWorker
from services.workers.com_device_worker import ComDeviceWorker
from services.workers.opcua_worker import OpcUaWorker

WORKER_CATALOG = {
	WorkerName.TCP_CLIENT: TcpClientWorker,
	WorkerName.TWINCAT: TwinCatWorker,
    WorkerName.SCRIPT: ScriptWorker,
	WorkerName.ITAC : ItacWorker,
	WorkerName.REST_API : RestApiWorker,
	WorkerName.COM_DEVICE: ComDeviceWorker,
	WorkerName.OPCUA: OpcUaWorker,
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

from services.worker_commands import ComDeviceCommands

com_handle = GLOBAL_WORKERS.get(WorkerName.COM_DEVICE)
if com_handle:
		for e in get_com_device_entries(APP_CONFIG):
			try:
				com_handle.send(
					ComDeviceCommands.ADD_DEVICE,
					device_id=e.device_id,
					port=e.port,
					baudrate=e.baudrate,
					bytesize=e.bytesize,
					parity=e.parity,
					stopbits=e.stopbits,
					timeout_s=e.timeout_s,
					write_timeout_s=e.write_timeout_s,
					mode=e.mode,
					delimiter=e.delimiter,  # already decoded to real "\n" or "\r\n"
					encoding=e.encoding,
					read_chunk_size=e.read_chunk_size,
					max_line_len=e.max_line_len,
					reconnect_min_s=e.reconnect_min_s,
					reconnect_max_s=e.reconnect_max_s,
				)
			except Exception:
				logger.exception("Failed to add com device")


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

itac_handle = GLOBAL_WORKERS.get(WorkerName.ITAC)
if itac_handle:
	for endpoint in get_itac_endpoints(APP_CONFIG):
		itac_handle.send(
			ItacCommands.ADD_CONNECTION,
			connection_id=endpoint.name,
			base_url=endpoint.base_url,
			station_number=endpoint.station_number,
			client=endpoint.client,
			registration_type=endpoint.registration_type,
			system_identifier=endpoint.system_identifier,
			station_password=endpoint.station_password,
			user=endpoint.user,
			password=endpoint.password,
			timeout_s=endpoint.timeout_s,
			verify_ssl=endpoint.verify_ssl,
			auto_login=endpoint.auto_login,
			force_locale=endpoint.force_locale,
		)

opcua_handle = GLOBAL_WORKERS.get(WorkerName.OPCUA)
if opcua_handle:
	for endpoint in get_opcua_endpoints(APP_CONFIG):
		opcua_handle.send(
			OpcUaCommands.ADD_ENDPOINT,
			name=endpoint.name,
			server_url=endpoint.server_url,
			security_policy=endpoint.security_policy,
			security_mode=endpoint.security_mode,
			username=endpoint.username,
			password=endpoint.password,
			timeout_s=endpoint.timeout_s,
			auto_connect=endpoint.auto_connect,
			nodes=endpoint.nodes,
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
	cfg = get_app_config()
	apply_ui_theme(cfg)

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
	ctx.dummy_controller = DUMMY_CONTROLLER
	ctx.modal_manager = install_modal_manager(GLOBAL_WORKER_BUS)
	refresh_errors_count(ctx)

	# Only detach this UI session — NEVER stop workers
	def on_disconnect():
		ctx.dummy_controller.stop_client(ui.context.client)

	ui.context.client.on_disconnect(on_disconnect)

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
						logger.warning("Failed closing crash dialog for chain '{}'", chain_key)
				continue

			error_message = str(value.get("error_message") or "StepChain crashed.")
			_open_chain_crash_dialog(chain_key, error_message)

	crash_timer = ui.timer(0.2, _drain_script_crashes)

	def _cleanup_crash_watcher() -> None:
		try:
			sub_script_state.close()
		except Exception:
			logger.warning("Failed to close script-state subscription during cleanup")
		try:
			crash_timer.cancel()
		except Exception:
			logger.warning("Failed to cancel crash watcher timer during cleanup")

	ui.context.client.on_disconnect(_cleanup_crash_watcher)

	# Global logging popups for ERROR/CRITICAL records
	last_error_popup_id = {"value": get_latest_error_popup_event_id()}

	def _drain_error_popups() -> None:
		current_id, events = get_error_popup_events_since(last_error_popup_id["value"])
		last_error_popup_id["value"] = current_id
		for evt in events:
			level = str(evt.get("level", "ERROR")).upper()
			msg = str(evt.get("message", "")).strip()
			if not msg:
				continue
			notify_type = "negative" if level in ("ERROR", "CRITICAL") else "warning"
			ui.notify(f"{level}: {msg}", type=notify_type, multi_line=True, timeout=10000)

	error_popup_timer = ui.timer(0.25, _drain_error_popups)

	def _cleanup_error_popup_watcher() -> None:
		try:
			error_popup_timer.cancel()
		except Exception:
			logger.warning("Failed to cancel error-popup timer during cleanup")

	ui.context.client.on_disconnect(_cleanup_error_popup_watcher)

	# --------- LAYOUT ---------
	build_header(ctx)
	build_drawer(ctx)
	build_device_panel(ctx)
	ctx.dummy_controller.start(ctx)

	with ui.row().classes("w-full").style(
		f"height: calc(100vh - {HEADER_PX}px - {FOOTER_PX}px);"
	):
		with ui.column().classes("w-full h-full min-h-0 min-w-0 overflow-hidden p-4 pb-6 gap-4"):
			build_main_area(ctx)

	default_route = app.storage.user.get(
		"current_route", cfg.ui.navigation.main_route
	)
	initial = get_initial_route_from_url(default_route)
	navigate(ctx, initial)



ui.run(
	title="KE-Elektronik-Shopfloorapp",
	reload=False,
	storage_secret=os.environ["NICEGUI_STORAGE_SECRET"],
)
