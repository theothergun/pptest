# services/ui/view_cmd.py
from __future__ import annotations

import time
import queue
from typing import Any, Callable, Optional

from nicegui import ui
from loguru import logger

from services.worker_topics import WorkerTopics


def view_wait_key(view: str) -> str:
	return "view.wait.%s" % str(view or "").strip()


def install_wait_dialog(
	*,
	ctx,
	worker_bus,
	wait_key: str,
	title: str = "Please wait",
	message: str = "Working ...",
	add_timer: Optional[Callable[..., Any]] = None,
) -> dict:
	"""
	Install a standard wait dialog that opens on VALUE_CHANGED(open) and closes on TOPIC_MODAL_CLOSE.

	Returns:
	{
		"open": callable,
		"close": callable,
		"subs": [sub_wait_open, sub_wait_close],
		"timers": [timer_open, timer_close],
	}
	"""
	ui.add_head_html("""
<style>
@keyframes pack-wait-spin {
	from { transform: rotate(0deg); }
	to { transform: rotate(360deg); }
}
.pack-wait-spin {
	animation: pack-wait-spin 1s linear infinite;
}
</style>
""")

	sub_wait_close = worker_bus.subscribe(WorkerTopics.TOPIC_MODAL_CLOSE)
	sub_wait_open = worker_bus.subscribe(WorkerTopics.VALUE_CHANGED)

	wait_state = {"open": False}
	wait_text_refs = {"title": None, "message": None}
	with ui.dialog().props("persistent") as wait_dialog:
		with ui.card().classes("w-72 items-center gap-3 py-6"):
			ui.icon("hourglass_top").classes("text-primary text-4xl pack-wait-spin")
			wait_text_refs["title"] = ui.label(str(title)).classes("text-base font-semibold")
			wait_text_refs["message"] = ui.label(str(message)).classes("text-sm font-medium")

	def _set_wait_dialog_text(title_text: Optional[str] = None, message_text: Optional[str] = None) -> None:
		title_ref = wait_text_refs.get("title")
		msg_ref = wait_text_refs.get("message")
		if title_ref is not None and title_text is not None:
			title_ref.set_text(str(title_text))
		if msg_ref is not None and message_text is not None:
			msg_ref.set_text(str(message_text))

	def _open_wait_dialog() -> None:
		if wait_state["open"]:
			return
		wait_state["open"] = True
		wait_dialog.open()

	def _close_wait_dialog() -> None:
		if not wait_state["open"]:
			return
		wait_state["open"] = False
		wait_dialog.close()

	def _drain_wait_open_signal() -> None:
		while True:
			try:
				msg = sub_wait_open.queue.get_nowait()
			except queue.Empty:
				break
			payload = getattr(msg, "payload", None) or {}
			if not isinstance(payload, dict):
				continue
			key = str(payload.get("key") or "").strip()
			if key != str(wait_key or "").strip():
				continue
			value = payload.get("value")
			if not isinstance(value, dict):
				continue
			action = str(value.get("action") or "").strip().lower()
			if action == "open":
				_set_wait_dialog_text(
					title_text=str(value.get("title") or title),
					message_text=str(value.get("message") or message),
				)
				_open_wait_dialog()
			elif action == "close":
				_close_wait_dialog()

	def _drain_wait_close_signal() -> None:
		while True:
			try:
				msg = sub_wait_close.queue.get_nowait()
			except queue.Empty:
				break
			payload = getattr(msg, "payload", None) or {}
			if not isinstance(payload, dict):
				continue
			if bool(payload.get("close_active", False)):
				_close_wait_dialog()
				continue
			key = str(payload.get("key") or "").strip()
			if key == str(wait_key or "").strip():
				_close_wait_dialog()

	timer_open = (add_timer or ui.timer)(0.1, _drain_wait_open_signal)
	timer_close = (add_timer or ui.timer)(0.1, _drain_wait_close_signal)

	return {
		"open": _open_wait_dialog,
		"close": _close_wait_dialog,
		"subs": [sub_wait_open, sub_wait_close],
		"timers": [timer_open, timer_close],
	}


def publish_view_cmd(
	*,
	worker_bus,
	view: str,
	cmd_key: str,
	cmd: str,
	wait_key: Optional[str] = None,
	open_wait: Optional[Callable[[], Any]] = None,
	extra: Optional[dict] = None,
	source_id: Optional[str] = None,
) -> None:
	"""
	Publish the standard command payload to:
	- WorkerTopics.VALUE_CHANGED with key=cmd_key (legacy)
	- topic "view.cmd.<view>" (new, wildcard-friendly)
	"""
	publish_fn = getattr(worker_bus, "publish", None)
	if not callable(publish_fn):
		logger.warning("View command publish skipped: worker_bus.publish is not callable")
		return

	if callable(open_wait):
		open_wait()

	payload = {
		"cmd": str(cmd),
		"event_id": int(time.time_ns()),
	}
	wait_key_value = str(wait_key or view_wait_key(view))
	if wait_key_value:
		payload["wait_modal_key"] = wait_key_value
	if isinstance(extra, dict):
		payload.update({k: v for k, v in extra.items()})

	source_id = str(source_id or view or "")
	publish_fn(
		topic=WorkerTopics.VALUE_CHANGED,
		source="ui",
		source_id=source_id,
		key=str(cmd_key),
		value=payload,
	)

	view_payload = dict(payload)
	view_payload.update({
		"view": str(view),
		"cmd_key": str(cmd_key),
	})
	publish_fn(
		topic="view.cmd.%s" % str(view),
		source="ui",
		source_id=source_id,
		**view_payload,
	)
