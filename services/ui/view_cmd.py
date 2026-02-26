# services/ui/view_cmd.py
from __future__ import annotations

import time
import queue
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from nicegui import ui
from loguru import logger

from services.worker_topics import WorkerTopics
from services.ui.registry import (
	UiActionName,
	UiEvent,
	ViewName,
	ViewRegistryError,
	parse_view_action,
	view_wait_key,
)


def _raw_value(value: Any) -> str:
	return str(getattr(value, "value", value))


@dataclass(frozen=True)
class ViewAction:
	view: ViewName | str
	name: UiActionName | str
	event: UiEvent | str = UiEvent.CLICK.value

	def to_dict(self) -> dict[str, str]:
		return {
			"view": _raw_value(self.view),
			"name": _raw_value(self.name),
			"event": _raw_value(self.event),
		}


@dataclass(frozen=True)
class ViewCommand:
	action: ViewAction
	event_id: int
	wait_modal_key: str | None = None
	source_id: str = "ui"
	payload: dict[str, Any] = field(default_factory=dict)

	@classmethod
	def create(
		cls,
		*,
		view: str,
		name: str,
		event: str = UiEvent.CLICK.value,
		wait_key: str | None = None,
		source_id: str | None = None,
		payload: dict[str, Any] | None = None,
	) -> "ViewCommand":
		return cls(
			action=ViewAction(view=_raw_value(view), name=_raw_value(name), event=_raw_value(event)),
			event_id=int(time.time_ns()),
			wait_modal_key=str(wait_key) if wait_key else None,
			source_id=str(source_id or "ui"),
			payload=dict(payload or {}),
		)

	def to_bus_dict(self, cmd_key: str) -> dict[str, Any]:
		return {
			"view": _raw_value(self.action.view),
			"cmd_key": cmd_key,
			"action": {
				"view": _raw_value(self.action.view),
				"name": _raw_value(self.action.name),
				"event": _raw_value(self.action.event),
			},
			"event_id": self.event_id,
			"wait_modal_key": self.wait_modal_key,
			"source_id": self.source_id,
			**self.payload,
		}

	def to_cmd_value_payload(self) -> dict[str, Any]:
		cmd_payload: dict[str, Any] = {
			"action": self.action.to_dict(),
			"event_id": int(self.event_id),
		}
		if self.wait_modal_key:
			cmd_payload["wait_modal_key"] = str(self.wait_modal_key)
		if self.payload:
			cmd_payload.update(self.payload)
		return cmd_payload

	def to_view_topic_payload(self, *, cmd_key: str) -> dict[str, Any]:
		return self.to_bus_dict(cmd_key=str(cmd_key))

	@classmethod
	def from_bus_dict(cls, data: dict[str, Any]) -> "ViewCommand":
		action = data.get("action", {}) or {}
		payload = dict(data)
		for k in ("view", "cmd_key", "action", "event_id", "wait_modal_key", "source_id"):
			payload.pop(k, None)
		return cls(
			action=ViewAction(
				view=action.get("view") or data.get("view"),
				name=action.get("name", ""),
				event=action.get("event", UiEvent.CLICK.value),
			),
			event_id=int(data.get("event_id", 0)),
			wait_modal_key=data.get("wait_modal_key"),
			source_id=str(data.get("source_id", "ui")),
			payload=payload,
		)


# Backward compatible alias used by existing callers.
ViewCommandMessage = ViewCommand


def parse_view_cmd_payload(payload: Any, *, strict: bool = False) -> ViewCommand | None:
	"""Best-effort parser for incoming view command payload dictionaries."""
	if not isinstance(payload, dict):
		return None
	action_raw = payload.get("action")
	if not isinstance(action_raw, dict):
		return None
	view = str(action_raw.get("view") or payload.get("view") or "").strip()
	name = str(action_raw.get("name") or "").strip()
	event = str(action_raw.get("event") or UiEvent.CLICK.value).strip() or UiEvent.CLICK.value
	if not view or not name:
		return None
	try:
		event_id = int(payload.get("event_id") or 0)
	except Exception:
		event_id = 0
	data = dict(payload)
	data["event_id"] = event_id
	data["source_id"] = str(payload.get("source_id", "ui"))
	wait_modal_key = payload.get("wait_modal_key")
	data["wait_modal_key"] = str(wait_modal_key) if wait_modal_key is not None else None
	if strict:
		parse_view_action(view=view, name=name, event=event, strict=True)
	return ViewCommand.from_bus_dict(data)


def parse_view_cmd_payload_or_error(payload: Any) -> ViewCommand:
	cmd = parse_view_cmd_payload(payload, strict=True)
	if cmd is None:
		raise ViewRegistryError("invalid view command payload: missing action/view/name")
	return cmd



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
	name: str,
	event: str = UiEvent.CLICK.value,
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

	source_id = str(source_id or view or "")
	wait_key_value = str(wait_key or view_wait_key(view)).strip()
	msg = ViewCommandMessage.create(
		view=str(view),
		name=str(name),
		event=str(event),
		wait_key=wait_key_value or None,
		source_id=source_id,
		payload=extra if isinstance(extra, dict) else None,
	)
	payload = msg.to_cmd_value_payload()

	publish_fn(
		topic=WorkerTopics.VALUE_CHANGED,
		source="ui",
		source_id=source_id,
		key=str(cmd_key),
		value=payload,
	)

	view_payload = msg.to_view_topic_payload(cmd_key=str(cmd_key))
	view_payload.pop("source_id", None)
	publish_fn(
		topic="view.cmd.%s" % str(view),
		source="ui",
		source_id=source_id,
		**view_payload,
	)
