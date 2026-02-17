# services/workers/stepchain/apis/ui_api.py
from __future__ import annotations

from typing import Any, Optional, Union

from services.worker_topics import WorkerTopics
from services.worker_commands import ScriptWorkerCommands as Commands

from services.workers.stepchain.apis.api_utils import to_int, to_str
import uuid


# 1=Green, 2=Yellow, 3=Red, 4=Blue, 5=Grey
_STATE_NAME_TO_CODE = {
	"ok": 1,
	"green": 1,
	"warn": 2,
	"warning": 2,
	"yellow": 2,
	"error": 3,
	"red": 3,
	"info": 4,
	"blue": 4,
	"idle": 5,
	"grey": 5,
	"gray": 5,
}


class UiApi:
	"""UI/log/event helpers exposed to scripts."""

	def __init__(self, ctx: Any) -> None:
		self._ctx = ctx

	def set(self, key: str, value: Any) -> None:
		if not isinstance(self._ctx._ui_state, dict):
			self._ctx._ui_state = {}
		self._ctx._ui_state[str(key)] = value

	def merge(self, patch: dict[str, Any]) -> None:
		if not isinstance(patch, dict):
			return
		if not isinstance(self._ctx._ui_state, dict):
			self._ctx._ui_state = {}
		self._ctx._ui_state.update(patch)

	def clear(self) -> None:
		self._ctx._ui_state = {}

	def _value_by_key(self, key: str, default: Any = None) -> Any:
		target = str(key or "").strip()
		if not target:
			return default

		# Search most recent payload per source first.
		for source in list(self._ctx.data.keys()):
			source_data = self._ctx.data.get(source, {})
			last_id = self._ctx._last_seen_by_source.get(source, "")
			payload = source_data.get(last_id) if last_id else None
			if isinstance(payload, dict) and "__last__" in payload:
				payload = payload.get("__last__")
			if isinstance(payload, dict) and payload.get("key") == target:
				return payload.get("value", default)

		# Fallback full scan.
		for source_data in self._ctx.data.values():
			for payload in source_data.values():
				if isinstance(payload, dict) and "__last__" in payload:
					payload = payload.get("__last__")
				if isinstance(payload, dict) and payload.get("key") == target:
					return payload.get("value", default)

		return default

	def consume_command(
		self,
		key: str,
		*,
		value_field: str = "cmd",
		dedupe: bool = True,
		normalize: bool = True,
	) -> Optional[str]:
		"""
		Read a command-style UI bus value once and optionally deduplicate by event id.

		Expected payload examples:
		- {"cmd": "start", "event_id": 123}
		- "start"

		Returns:
		- command string (e.g. "start")
		- None if not present / already consumed
		"""
		k = str(key or "").strip()
		if not k:
			return None

		raw = self._value_by_key(k, default=None)
		if raw is None:
			return None

		cmd: Optional[str] = None
		event_id = None

		if isinstance(raw, dict):
			cmd = str(raw.get(value_field) or "").strip()
			event_id = raw.get("event_id")
		else:
			cmd = str(raw).strip()

		if not cmd:
			return None
		if normalize:
			cmd = cmd.lower()

		if not dedupe:
			return cmd

		last_event_key = "__ui_cmd_last_event_id:%s" % k
		last_fallback_key = "__ui_cmd_last_fallback:%s" % k

		if event_id is not None:
			last_event_id = self._ctx._vars.get(last_event_key)
			if last_event_id == event_id:
				return None
			self._ctx._vars[last_event_key] = event_id
			return cmd

		# Fallback dedupe for payloads without event_id.
		if self._ctx._vars.get(last_fallback_key) == cmd:
			return None
		self._ctx._vars[last_fallback_key] = cmd
		return cmd

	def consume_payload(
		self,
		key: str,
		*,
		dedupe: bool = True,
	) -> Optional[dict]:
		"""
		Read a raw UI bus payload once and optionally deduplicate by event id.

		Returns:
		- dict payload (original if dict, else {"value": raw})
		- None if not present / already consumed
		"""
		k = str(key or "").strip()
		if not k:
			return None

		raw = self._value_by_key(k, default=None)
		if raw is None:
			return None

		payload = raw if isinstance(raw, dict) else {"value": raw}
		event_id = payload.get("event_id") if isinstance(payload, dict) else None

		if not dedupe:
			return payload

		last_event_key = "__ui_payload_last_event_id:%s" % k
		last_fallback_key = "__ui_payload_last_fallback:%s" % k

		if event_id is not None:
			last_event_id = self._ctx._vars.get(last_event_key)
			if last_event_id == event_id:
				return None
			self._ctx._vars[last_event_key] = event_id
			return payload

		fallback = repr(payload)
		if self._ctx._vars.get(last_fallback_key) == fallback:
			return None
		self._ctx._vars[last_fallback_key] = fallback
		return payload

	# -------- AppState bridge helpers (persisted UI variables) --------

	def set_state(self, key: str, value: Any) -> None:
		"""Write one value into AppState via UiBridge.emit_patch."""
		k = str(key or "").strip()
		if not k:
			return
		try:
			self._ctx._update_app_state(k, value)
		except Exception:
			pass
		try:
			self._ctx.bridge.emit_patch(k, value)
		except Exception:
			pass

	def set_state_many(self, **values: Any) -> None:
		"""Write multiple AppState keys (patch-per-key to avoid full-state replacement)."""
		for k, v in values.items():
			self.set_state(str(k), v)

	def inc_state_int(self, key: str, amount: int = 1, default: int = 0) -> int:
		"""
		Increment an AppState key interpreted as int.
		Returns the new value.
		"""
		cur = to_int(self._ctx._app_state.get(str(key), default), default)
		nxt = int(cur) + int(amount)
		self.set_state(str(key), nxt)
		return nxt

	def _normalize_state(self, state: Union[int, str, None], default: int = 5) -> int:
		if state is None:
			return int(default)

		if isinstance(state, int):
			return int(state)

		try:
			# allow "1", "2", ...
			s = str(state).strip().lower()
			if not s:
				return int(default)
			if s.isdigit():
				return int(s)
			return int(_STATE_NAME_TO_CODE.get(s, default))
		except Exception:
			return int(default)

	def show(
		self,
		*,
		instruction_key: str = "work_instruction",
		feedback_key: str = "work_feedback",
		instruction_state_key: str = "work_instruction_state",
		feedback_state_key: str = "work_feedback_state",
		instruction: Optional[str] = None,
		feedback: Optional[str] = None,
		instruction_state: Union[int, str, None] = None,
		feedback_state: Union[int, str, None] = None,
	) -> None:
		"""
		Common UI pattern in one call.

		States accept: 1..5 OR "ok/warn/error/info/idle".
		"""
		patch = {}

		if instruction is not None:
			patch[str(instruction_key)] = to_str(instruction, "")

		if feedback is not None:
			patch[str(feedback_key)] = to_str(feedback, "")

		if instruction_state is not None:
			patch[str(instruction_state_key)] = self._normalize_state(instruction_state)

		if feedback_state is not None:
			patch[str(feedback_state_key)] = self._normalize_state(feedback_state)

		if patch:
			self.set_state_many(**patch)

	def notify(self, message: str, type_: str = "info") -> None:
		try:
			self._ctx.bridge.emit_notify(str(message), str(type_))
		except Exception:
			pass

	def event(self, name: str, **payload: Any) -> None:
		event_key = "script.event.%s" % str(name or "unnamed")
		try:
			self._ctx.worker_bus.publish(
				topic=WorkerTopics.VALUE_CHANGED,
				source="ScriptWorker",
				source_id=self._ctx.chain_id,
				key=event_key,
				value=dict(payload),
			)
		except Exception:
			pass

	def popup_confirm(
		self,
		key: str,
		message: str,
		*,
		title: str = "Confirm",
		ok_text: str = "OK",
		cancel_text: str = "Cancel",
		wait_step_desc: str = "Waiting for confirmation...",
	) -> Optional[bool]:
		"""
		Non-blocking confirm popup.

		Return:
		- None  -> waiting (popup requested once, no result yet)
		- True  -> confirmed
		- False -> cancelled

		Important:
		- Does NOT block.
		- If result is None, it also sets step_desc so operators see it's waiting.
		"""

		k = str(key or "").strip()
		if not k:
			raise ValueError("popup_confirm() requires non-empty key")

		# If result already exists, return and allow re-use later
		res = self._ctx._modal_get_result_for_key(k)
		if res is not None:
			return bool(res)

		# If pending, just keep waiting
		if self._ctx._modal_is_pending(k):
			try:
				self._ctx.step_desc = str(wait_step_desc or "")
			except Exception:
				pass
			return None

		# Emit new request
		request_id = str(uuid.uuid4())
		self._ctx._modal_mark_pending(k, request_id)

		payload = {
			"request_id": request_id,
			"chain_id": self._ctx.chain_id,
			"instance_id": getattr(self._ctx, "instance_id", "") or "",
			"key": k,
			"title": str(title or "Confirm"),
			"message": str(message or ""),
			"ok_text": str(ok_text or "OK"),
			"cancel_text": str(cancel_text or "Cancel"),
		}

		try:
			self._ctx.worker_bus.publish(
				topic=WorkerTopics.TOPIC_MODAL_REQUEST,
				source="ScriptWorker",
				source_id=self._ctx.chain_id,
				**payload
			)
		except Exception:
			# allow retry next cycle
			self._ctx._modal_clear_pending(k)
			return None

		try:
			self._ctx.step_desc = str(wait_step_desc or "")
		except Exception:
			pass

		return None

	def popup_message(
		self,
		key: str,
		message: str,
		*,
		title: str = "Message",
		buttons: Optional[list] = None,
		wait_step_desc: str = "Waiting for operator...",
	) -> Optional[dict]:
		"""
		Sticky message popup with buttons that returns the click back to the stepchain.

		Return:
		- None                 -> still waiting
		- {"clicked": "retry"} -> user clicked a button
		- {"closed": True}     -> popup was closed programmatically via popup_close()
		"""
		k = str(key or "").strip()
		if not k:
			raise ValueError("popup_message() requires non-empty key")

		# finished?
		res = self._ctx._modal_get_result_for_key(k)
		if res is not None:
			# normalize: ensure dict
			if isinstance(res, dict):
				return res
			return {"result": res}

		# pending?
		if self._ctx._modal_is_pending(k):
			try:
				self._ctx.step_desc = str(wait_step_desc or "")
			except Exception:
				pass
			return None

		# create request
		request_id = str(uuid.uuid4())
		self._ctx._modal_mark_pending(k, request_id)

		btns = buttons if isinstance(buttons, list) else []
		payload = {
			"type": "message",
			"request_id": request_id,
			"chain_id": self._ctx.chain_id,
			"instance_id": getattr(self._ctx, "instance_id", "") or "",
			"key": k,
			"title": str(title or "Message"),
			"message": str(message or ""),
			"buttons": btns,
		}

		try:
			self._ctx.worker_bus.publish(
				topic=WorkerTopics.TOPIC_MODAL_REQUEST,
				source="ScriptWorker",
				source_id=self._ctx.chain_id,
				**payload
			)
		except Exception:
			self._ctx._modal_clear_pending(k)
			return None

		try:
			self._ctx.step_desc = str(wait_step_desc or "")
		except Exception:
			pass

		return None


	def popup_close(self, key: str) -> None:
		"""
		Close a popup by key (if active) and unblock the stepchain.

		This will:
		- close the UI dialog (best effort)
		- set a local result {"closed": True} so popup_message() stops returning None
		"""
		k = str(key or "").strip()
		if not k:
			return

		# unblock locally (important even if UI close fails)
		try:
			# Only set if it was pending; otherwise don't overwrite real result
			if self._ctx._modal_is_pending(k):
				self._ctx._modal_result_by_key[k] = {"closed": True}
				self._ctx._modal_clear_pending(k)
		except Exception:
			pass

		# close UI (best effort)
		try:
			self._ctx.worker_bus.publish(
				topic=WorkerTopics.TOPIC_MODAL_CLOSE,
				source="ScriptWorker",
				source_id=self._ctx.chain_id,
				key=k,
			)
		except Exception:
			pass

	def _popup_input_base(
		self,
		key: str,
		message: str,
		*,
		title: str,
		ok_text: str,
		cancel_text: str,
		kind: str,
		placeholder: str = "",
		default: Any = None,
		options: Any = None,
		wait_step_desc: str = "Waiting for input...",
	) -> Optional[dict]:

		k = str(key or "").strip()
		if not k:
			raise ValueError("popup_input requires non-empty key")

		# finished?
		res = self._ctx._modal_get_result_for_key(k)
		if res is not None:
			if isinstance(res, dict):
				return res
			return {"ok": True, "value": res}

		# pending?
		if self._ctx._modal_is_pending(k):
			try:
				self._ctx.step_desc = str(wait_step_desc or "")
			except Exception:
				pass
			return None

		request_id = str(uuid.uuid4())
		self._ctx._modal_mark_pending(k, request_id)

		payload = {
			"type": "input",
			"kind": str(kind or "text"),
			"request_id": request_id,
			"chain_id": self._ctx.chain_id,
			"instance_id": getattr(self._ctx, "instance_id", "") or "",
			"key": k,
			"title": str(title or "Input"),
			"message": str(message or ""),
			"ok_text": str(ok_text or "OK"),
			"cancel_text": str(cancel_text or "Cancel"),
			"placeholder": str(placeholder or ""),
			"default": default,
			"options": options,
		}

		try:
			self._ctx.worker_bus.publish(
				topic=WorkerTopics.TOPIC_MODAL_REQUEST,
				source="ScriptWorker",
				source_id=self._ctx.chain_id,
				**payload
			)
		except Exception:
			self._ctx._modal_clear_pending(k)
			return None

		try:
			self._ctx.step_desc = str(wait_step_desc or "")
		except Exception:
			pass

		return None

	def popup_input_text(
		self,
		key: str,
		message: str,
		*,
		title: str = "Input",
		ok_text: str = "OK",
		cancel_text: str = "Cancel",
		placeholder: str = "",
		default: Optional[str] = None,
	) -> Optional[dict]:
		return self._popup_input_base(
			key,
			message,
			title=title,
			ok_text=ok_text,
			cancel_text=cancel_text,
			kind="text",
			placeholder=placeholder,
			default=default,
		)

	def popup_input_number(
		self,
		key: str,
		message: str,
		*,
		title: str = "Input",
		ok_text: str = "OK",
		cancel_text: str = "Cancel",
		placeholder: str = "",
		default: Optional[float] = None,
	) -> Optional[dict]:
		return self._popup_input_base(
			key,
			message,
			title=title,
			ok_text=ok_text,
			cancel_text=cancel_text,
			kind="number",
			placeholder=placeholder,
			default=default,
		)

	def popup_choose(
		self,
		key: str,
		message: str,
		*,
		title: str = "Choose",
		ok_text: str = "OK",
		cancel_text: str = "Cancel",
		placeholder: str = "",
		options: list = None,
		default: Optional[str] = None,
	) -> Optional[dict]:
		return self._popup_input_base(
			key,
			message,
			title=title,
			ok_text=ok_text,
			cancel_text=cancel_text,
			kind="select",
			placeholder=placeholder,
			default=default,
			options=(options or []),
		)

	def popup_clear(self, key: Optional[str] = None) -> None:
		"""
		Hard reset popup state so a new popup can be created again immediately.
		Works even if _modal_reset() does not exist.
		"""
		# --- local reset (this is the important part) ---
		try:
			if key is None:
				# full reset
				try:
					self._ctx._modal_pending.clear()
				except Exception:
					pass
				try:
					self._ctx._modal_result_by_key.clear()
				except Exception:
					pass
				try:
					self._ctx._modal_key_by_request_id.clear()
				except Exception:
					pass
			else:
				k = str(key or "").strip()
				if k:
					# clear pending request_id mapping + result
					try:
						self._ctx._modal_clear_pending(k)
					except Exception:
						pass
					try:
						self._ctx._modal_result_by_key.pop(k, None)
					except Exception:
						pass
		except Exception:
			pass

		# --- UI close (best effort) ---
		try:
			if key is None:
				self._ctx.worker_bus.publish(
					topic=WorkerTopics.TOPIC_MODAL_CLOSE,
					source="ScriptWorker",
					source_id=self._ctx.chain_id,
					close_active=True,
				)
			else:
				k = str(key or "").strip()
				if k:
					self._ctx.worker_bus.publish(
						topic=WorkerTopics.TOPIC_MODAL_CLOSE,
						source="ScriptWorker",
						source_id=self._ctx.chain_id,
						key=k,
					)
		except Exception:
			pass
