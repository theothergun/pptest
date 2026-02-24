from __future__ import annotations

from nicegui import ui

from layout.context import PageContext
from services.app_config import get_app_config, save_app_config
from services.app_lifecycle import request_app_restart
from services.logging_setup import setup_logging, read_log_tail


LOG_LEVELS = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def render(container: ui.element, _ctx: PageContext) -> None:
	with container.classes("w-full"):
		cfg = get_app_config()
		current = bool(getattr(cfg.ui.navigation, "hide_nav_on_startup", False))
		current_show_device_panel = bool(getattr(cfg.ui.navigation, "show_device_panel", False))
		current_dark = bool(getattr(cfg.ui.navigation, "dark_mode", False))
		proxy_enabled = bool(getattr(cfg.proxy, "enabled", False))
		proxy_http = str(getattr(cfg.proxy, "http", "") or "")
		proxy_https = str(getattr(cfg.proxy, "https", "") or "")
		proxy_no_proxy = str(getattr(cfg.proxy, "no_proxy", "") or "")
		console_level = str(getattr(cfg.logging, "console_level", "INFO") or "INFO").upper()
		file_level = str(getattr(cfg.logging, "file_level", "DEBUG") or "DEBUG").upper()

		with ui.card().classes("w-full"):
			ui.label("General Settings").classes("text-xl font-semibold")
			ui.label("General UI behavior settings.").classes("text-sm text-gray-500")

			hide_nav_switch = ui.switch("Hide nav on startup", value=current)
			show_device_panel_switch = ui.switch("Show device panel", value=current_show_device_panel)
			dark_mode_switch = ui.switch("Dark mode", value=current_dark)

			ui.separator().classes("my-2")
			ui.label("Logging").classes("text-lg font-semibold")
			ui.label("Configure console and file logging levels.").classes("text-sm text-gray-500")
			with ui.row().classes("w-full gap-4"):
				console_level_select = ui.select(LOG_LEVELS, value=console_level, label="Console log level").props("outlined").classes("min-w-[240px]")
				file_level_select = ui.select(LOG_LEVELS, value=file_level, label="File log level").props("outlined").classes("min-w-[240px]")

			def _open_logs_popup() -> None:
				text = read_log_tail(app_name="mes_app", max_lines=500)
				d = ui.dialog()
				with d, ui.card().classes("w-[1000px] max-w-[95vw]"):
					ui.label("Application Logs (latest lines)").classes("text-lg font-semibold")
					ui.textarea(value=text).props("readonly autogrow").classes("w-full").style("height:65vh; font-family:monospace;")
					with ui.row().classes("w-full justify-end"):
						ui.button("Close", on_click=d.close).props("flat")
				d.open()

			def _open_logs_in_new_tab() -> None:
				import json
				text = read_log_tail(app_name="mes_app", max_lines=1200)
				ui.run_javascript(
					"""
					const logText = __LOG_TEXT__ ;
					const escaped = logText
						.replaceAll('&', '&amp;')
						.replaceAll('<', '&lt;')
						.replaceAll('>', '&gt;');
					const w = window.open('', '_blank');
					if (w) {
						w.document.write('<html><head><title>Application Logs</title><style>body{font-family:monospace;background:#111;color:#eee;margin:0;padding:12px}pre{white-space:pre-wrap}</style></head><body><pre>' + escaped + '</pre></body></html>');
						w.document.close();
					}
					""".replace("__LOG_TEXT__", json.dumps(text))
				)

			with ui.row().classes("w-full gap-2"):
				ui.button("View logs popup", on_click=_open_logs_popup).props("outline")
				ui.button("Open logs in new tab", on_click=_open_logs_in_new_tab).props("outline")

			ui.separator().classes("my-2")
			ui.label("Proxy").classes("text-lg font-semibold")
			ui.label("Configure outbound proxy used by workers/integrations.").classes("text-sm text-gray-500")

			proxy_enabled_switch = ui.switch("Enable proxy", value=proxy_enabled)
			http_input = ui.input("HTTP proxy", value=proxy_http, placeholder="http://host:port").props("outlined").classes("w-full")
			https_input = ui.input("HTTPS proxy", value=proxy_https, placeholder="http://host:port").props("outlined").classes("w-full")
			no_proxy_input = ui.input("No proxy", value=proxy_no_proxy, placeholder="localhost,127.0.0.1,10.0.0.0/8").props("outlined").classes("w-full")

			def _apply_proxy_enabled_state() -> None:
				disabled = not bool(proxy_enabled_switch.value)
				http_input.set_enabled(not disabled)
				https_input.set_enabled(not disabled)
				no_proxy_input.set_enabled(not disabled)

			proxy_enabled_switch.on_value_change(lambda _e: _apply_proxy_enabled_state())
			_apply_proxy_enabled_state()

			def save_settings() -> None:
				cfg = get_app_config()
				cfg.ui.navigation.hide_nav_on_startup = bool(hide_nav_switch.value)
				cfg.ui.navigation.show_device_panel = bool(show_device_panel_switch.value)
				cfg.ui.navigation.dark_mode = bool(dark_mode_switch.value)
				cfg.proxy.enabled = bool(proxy_enabled_switch.value)
				cfg.proxy.http = str(http_input.value or "").strip()
				cfg.proxy.https = str(https_input.value or "").strip()
				cfg.proxy.no_proxy = str(no_proxy_input.value or "").strip()
				cfg.logging.console_level = str(console_level_select.value or "INFO").upper()
				cfg.logging.file_level = str(file_level_select.value or "DEBUG").upper()
				save_app_config(cfg)
				setup_logging(app_name="mes_app", log_level=cfg.logging.console_level, file_level=cfg.logging.file_level)
				ui.notify("General settings saved.", type="positive")
				ui.run_javascript("location.reload()")

			def open_restart_dialog() -> None:
				d = ui.dialog()
				with d, ui.card().classes("w-[520px] max-w-[95vw]"):
					ui.label("Restart application?").classes("text-lg font-semibold")
					ui.label("This will disconnect all active sessions and restart the backend process.").classes("text-sm text-gray-600")
					with ui.row().classes("w-full justify-end gap-2"):
						ui.button("Cancel", on_click=d.close).props("flat")

						def confirm_restart() -> None:
							d.close()
							ui.notify("Restarting application...", type="warning")
							request_app_restart(delay_s=1.0)

						ui.button("Restart now", on_click=confirm_restart).props("color=negative")
				d.open()

			with ui.row().classes("w-full justify-end gap-2"):
				ui.button("Restart Application", on_click=open_restart_dialog).props("outline color=negative")
				ui.button("Save", on_click=save_settings).props("color=primary")
