import os
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
