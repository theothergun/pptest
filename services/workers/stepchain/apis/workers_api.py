# services/workers/stepchain/apis/workers_api.py
from __future__ import annotations

import time
import uuid
import queue
from typing import Any, Callable, Optional

from services.worker_commands import TcpClientCommands, TwinCatCommands

# If your iTAC worker uses a different enum name/path, adjust this import only.
from services.worker_commands import ItacCommands  # type: ignore

from services.worker_topics import WorkerTopics


class WorkersApi:
	"""
	Simple worker I/O helpers for non-programmer StepChain scripts.

	Important:
	- Fast "latest values" can be read from ctx.data via get()/latest().
	- True synchronous calls (waiting for a worker reply) MUST NOT wait on ctx.data,
	  because the ScriptWorker thread may be the one that normally pumps bus messages
	  into ctx.data. Instead, we wait on a dedicated WorkerBus subscription queue.
	"""

	def __init__(self, ctx: Any) -> None:
		self._ctx = ctx

	# --------------------------- generic reads ---------------------------

	def get(self, worker: str, source_id: str, key: str, default: Any = None) -> Any:
		payload = self._ctx.data.get(str(worker), {}).get(str(source_id))
		if isinstance(payload, dict) and payload.get("key") == str(key):
			return payload.get("value", default)

		# Fallback: scan this worker/source cache for the requested key.
		source_data = self._ctx.data.get(str(worker), {})
		for entry in source_data.values():
			if isinstance(entry, dict) and entry.get("key") == str(key):
				return entry.get("value", default)
		return default

	def latest(self, worker: str, source_id: str, default: Any = None) -> Any:
		payload = self._ctx.data.get(str(worker), {}).get(str(source_id), default)
		if isinstance(payload, dict) and "value" in payload:
			return payload.get("value", default)
		return payload

	# -------------------------- bus wait helper --------------------------

	def _wait_for_bus_value(
		self,
		*,
		source: str,
		source_id: str,
		key_predicate: Callable[[str], bool],
		timeout_s: float,
	) -> dict:
		"""
		Block until we receive a WorkerTopics.VALUE_CHANGED from (source, source_id)
		where key_predicate(payload["key"]) is True.

		Returns the message payload dict (usually {"key":..., "value":...}).
		On timeout returns {"error":"timeout", ... }.
		"""
		if timeout_s <= 0:
			timeout_s = 0.01

		bus = getattr(self._ctx, "worker_bus", None)
		if bus is None or not hasattr(bus, "subscribe_many"):
			return {
				"error": "no_worker_bus",
				"detail": "ctx.worker_bus missing or does not support subscribe_many()",
			}

		sub = None
		deadline = time.time() + float(timeout_s)

		try:
			# Subscribe to VALUE_CHANGED (and ERROR for better diagnostics)
			sub = bus.subscribe_many([WorkerTopics.VALUE_CHANGED, WorkerTopics.ERROR])

			while True:
				remaining = deadline - time.time()
				if remaining <= 0:
					return {
						"error": "timeout",
						"timeout_s": float(timeout_s),
						"source": str(source),
						"source_id": str(source_id),
					}

				try:
					msg = sub.queue.get(timeout=min(0.2, remaining))
				except queue.Empty:
					continue

				# Defensive: ignore unknown shapes
				msg_source = getattr(msg, "source", None)
				msg_source_id = getattr(msg, "source_id", None)
				msg_topic = getattr(msg, "topic", None)
				msg_payload = getattr(msg, "payload", None)

				if str(msg_source or "") != str(source):
					continue
				if str(msg_source_id or "") != str(source_id):
					continue
				if not isinstance(msg_payload, dict):
					continue

				# If the worker reports an error for this source_id while waiting, surface it.
				if msg_topic == WorkerTopics.ERROR:
					# Payload contract: { "key": str|None, "action": str, "error": str }
					return {
						"error": "worker_error",
						"source": str(source),
						"source_id": str(source_id),
						"payload": msg_payload,
					}

				if msg_topic != WorkerTopics.VALUE_CHANGED:
					continue

				k = str(msg_payload.get("key") or "")
				if not k:
					continue

				if key_predicate(k):
					return msg_payload

		finally:
			if sub is not None:
				try:
					sub.close()
				except Exception:
					pass

	# --------------------------- TCP helpers ----------------------------

	def tcp_send(self, client_id: str, data: Any) -> None:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return
		self._ctx.send_cmd("tcp_client", TcpClientCommands.SEND, {
			"client_id": str(client_id),
			"data": data,
		})

	def tcp_connect(self, client_id: str) -> None:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return
		self._ctx.send_cmd("tcp_client", TcpClientCommands.CONNECT, {
			"client_id": str(client_id),
		})

	def tcp_disconnect(self, client_id: str) -> None:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return
		self._ctx.send_cmd("tcp_client", TcpClientCommands.DISCONNECT, {
			"client_id": str(client_id),
		})

	def tcp_message(self, client_id: str, default: Any = None, decode: bool = True, encoding: str = "utf-8") -> Any:
		value = self.get("tcp_client", str(client_id), "message", default)
		if decode and isinstance(value, (bytes, bytearray)):
			try:
				return bytes(value).decode(encoding, errors="replace")
			except Exception:
				return default
		return value

	# -------------------------- TwinCAT helpers -------------------------

	def plc_write(self, client_id: str, name: str, value: Any) -> None:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return
		self._ctx.send_cmd("twincat", TwinCatCommands.WRITE, {
			"client_id": str(client_id),
			"name": str(name),
			"value": value,
		})

	def plc_value(self, client_id: str, name: str, default: Any = None) -> Any:
		return self.get("twincat", str(client_id), str(name), default)

	# ----------------------------- iTAC sync ----------------------------

	def itac_station_setting(self, connection_id: str, keys: list[str], timeout_s: float = 5.0) -> dict:
		"""
		Synchronous wrapper:
			res = ctx.itac_station_setting("itac_main", ["WORKORDER_NUMBER"])
			# res is the raw JSON dict returned by iTAC (your worker's parsed resp.json()).

		This blocks on a WorkerBus subscription queue (NOT ctx.data) to avoid deadlocks/timeouts.
		"""
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return {"error": "no_send_cmd"}

		cid = str(connection_id or "")
		if not cid:
			return {"error": "missing_connection_id"}

		request_id = uuid.uuid4().hex
		self._ctx.send_cmd("itac", ItacCommands.GET_STATION_SETTING, {
			"connection_id": cid,
			"station_setting_keys": keys if isinstance(keys, list) else [],
			"request_id": request_id,
		})

		expected_key = "itac.%s.station_setting.%s" % (cid, request_id)

		msg_payload = self._wait_for_bus_value(
			source="itac",
			source_id=cid,
			key_predicate=lambda k: k == expected_key,
			timeout_s=float(timeout_s),
		)

		# Worker error surfaced
		if msg_payload.get("error") == "worker_error":
			return msg_payload

		# Timeout surfaced
		if msg_payload.get("error") == "timeout":
			msg_payload["expected_key"] = expected_key
			msg_payload["request_id"] = request_id
			msg_payload["connection_id"] = cid
			return msg_payload

		# Normal VALUE_CHANGED payload: {"key":..., "value":...}
		value = msg_payload.get("value")
		if isinstance(value, dict):
			# Optionally enrich without losing raw response
			value.setdefault("_meta", {})
			if isinstance(value["_meta"], dict):
				value["_meta"].update({
					"connection_id": cid,
					"request_id": request_id,
					"key": expected_key,
				})
			return value

		return {
			"value": value,
			"_meta": {
				"connection_id": cid,
				"request_id": request_id,
				"key": expected_key,
			},
		}

	def itac_custom_function(self, connection_id: str, method_name: str, in_args: list[Any], timeout_s: float = 10.0) -> dict:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return {"error": "no_send_cmd"}

		cid = str(connection_id or "")
		if not cid:
			return {"error": "missing_connection_id"}

		request_id = uuid.uuid4().hex
		self._ctx.send_cmd("itac", ItacCommands.CALL_CUSTOM_FUNCTION, {
			"connection_id": cid,
			"method_name": str(method_name or ""),
			"in_args": in_args if isinstance(in_args, list) else [],
			"request_id": request_id,
		})

		expected_key = "itac.%s.custom_function.%s" % (cid, request_id)

		msg_payload = self._wait_for_bus_value(
			source="itac",
			source_id=cid,
			key_predicate=lambda k: k == expected_key,
			timeout_s=float(timeout_s),
		)

		if msg_payload.get("error") == "worker_error":
			return msg_payload

		if msg_payload.get("error") == "timeout":
			msg_payload["expected_key"] = expected_key
			msg_payload["request_id"] = request_id
			msg_payload["connection_id"] = cid
			return msg_payload

		value = msg_payload.get("value")
		if isinstance(value, dict):
			value.setdefault("_meta", {})
			if isinstance(value["_meta"], dict):
				value["_meta"].update({
					"connection_id": cid,
					"request_id": request_id,
					"key": expected_key,
				})
			return value

		return {
			"value": value,
			"_meta": {
				"connection_id": cid,
				"request_id": request_id,
				"key": expected_key,
			},
		}

	def itac_raw_call(self, connection_id: str, function_name: str, body: dict, timeout_s: float = 10.0) -> dict:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return {"error": "no_send_cmd"}

		cid = str(connection_id or "")
		if not cid:
			return {"error": "missing_connection_id"}

		request_id = uuid.uuid4().hex
		self._ctx.send_cmd("itac", ItacCommands.RAW_CALL, {
			"connection_id": cid,
			"function_name": str(function_name or ""),
			"body": body if isinstance(body, dict) else {},
			"request_id": request_id,
		})

		expected_key = "itac.%s.raw.%s" % (cid, request_id)

		msg_payload = self._wait_for_bus_value(
			source="itac",
			source_id=cid,
			key_predicate=lambda k: k == expected_key,
			timeout_s=float(timeout_s),
		)

		if msg_payload.get("error") == "worker_error":
			return msg_payload

		if msg_payload.get("error") == "timeout":
			msg_payload["expected_key"] = expected_key
			msg_payload["request_id"] = request_id
			msg_payload["connection_id"] = cid
			return msg_payload

		value = msg_payload.get("value")
		if isinstance(value, dict):
			value.setdefault("_meta", {})
			if isinstance(value["_meta"], dict):
				value["_meta"].update({
					"connection_id": cid,
					"request_id": request_id,
					"key": expected_key,
				})
			return value

		return {
			"value": value,
			"_meta": {
				"connection_id": cid,
				"request_id": request_id,
				"key": expected_key,
			},
		}
