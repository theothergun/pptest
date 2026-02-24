# services/workers/stepchain/apis/workers_api.py
from __future__ import annotations

import time
import uuid
import queue
from typing import Any, Callable, Optional

from loguru import logger

from services.worker_commands import TcpClientCommands, TwinCatCommands, RestApiCommands

from services.worker_commands import ItacCommands
from services.worker_commands import OpcUaCommands
from services.worker_topics import WorkerTopics
from services.worker_commands import ComDeviceCommands
from services.automation_runtime.apis.api_utils import to_int

ITAC_NO_USER_LOGGED_RV = -104
ITAC_USER_ALREADY_LOGGED_RV = -106

class WorkersApi:
	"""
	Simple worker I/O helpers for non-programmer Automation Runtime scripts.

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
		worker_s = str(worker)
		source_id_s = str(source_id)
		key_s = str(key)

		bucket = self._ctx.data.get(worker_s, {}).get(source_id_s)

		if isinstance(bucket, dict) and bucket.get("key") == key_s:
			return bucket.get("value", default)

		if isinstance(bucket, dict) and key_s in bucket:
			entry = bucket.get(key_s)
			if isinstance(entry, dict) and "value" in entry:
				return entry.get("value", default)
			return entry

		if isinstance(bucket, dict):
			for entry in bucket.values():
				if isinstance(entry, dict) and entry.get("key") == key_s:
					return entry.get("value", default)

		return default

	def latest(self, worker: str, source_id: str, default: Any = None) -> Any:
		bucket = self._ctx.data.get(str(worker), {}).get(str(source_id), default)
		if isinstance(bucket, dict) and "__last__" in bucket:
			bucket = bucket.get("__last__")
		if isinstance(bucket, dict) and "value" in bucket:
			return bucket.get("value", default)
		return bucket

	# -------------------------- bus wait helper --------------------------

	def _wait_for_bus_value(
		self,
		*,
		source: str,
		source_id: str,
		key_predicate: Callable[[str], bool],
		timeout_s: float,
	) -> dict:
		if timeout_s <= 0:
			timeout_s = 0.01
		# Blocking waits are intentional in scripts; suppress one slow-tick warning.
		try:
			self._ctx._suppress_slow_tick_warning_once = True
		except Exception:
			pass

		bus = getattr(self._ctx, "worker_bus", None)
		if bus is None or not hasattr(bus, "subscribe_many"):
			return {
				"error": "no_worker_bus",
				"detail": "ctx.worker_bus missing or does not support subscribe_many()",
			}

		sub = None
		deadline = time.time() + float(timeout_s)

		try:
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

				if msg_topic == WorkerTopics.ERROR:
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

	def tcp_wait(
		self,
		client_id: str,
		default: Any = None,
		timeout_s: float = 1.0,
		decode: bool = True,
		encoding: str = "utf-8",
	) -> Any:
		cid = str(client_id or "")
		if not cid:
			return default

		msg_payload = self._wait_for_bus_value(
			source="tcp_client",
			source_id=cid,
			key_predicate=lambda k: k == "message",
			timeout_s=float(timeout_s),
		)

		if msg_payload.get("error") in ("worker_error", "timeout"):
			return default

		value = msg_payload.get("value", default)
		if decode and isinstance(value, (bytes, bytearray)):
			try:
				return bytes(value).decode(encoding, errors="replace")
			except Exception:
				return default
		return value

	# -------------------------- TwinCAT helpers -------------------------

	def plc_write(
		self,
		client_id: str,
		name: str,
		value: Any,
		*,
		plc_type: str | None = None,
		string_len: int | None = None,
	) -> None:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return
		self._ctx.send_cmd("twincat", TwinCatCommands.WRITE, {
			"client_id": str(client_id),
			"name": str(name),
			"value": value,
			"plc_type": plc_type,
			"string_len": string_len,
		})

	def plc_value(self, client_id: str, name: str, default: Any = None) -> Any:
		return self.get("twincat", str(client_id), str(name), default)

	def plc_wait_value(self, client_id: str, name: str, default: Any = None, timeout_s: float = 1.0) -> Any:
		cid = str(client_id or "")
		var = str(name or "")
		if not cid or not var:
			return default

		cached = self.get("twincat", cid, var, default=None)
		if cached is not None:
			return cached

		msg_payload = self._wait_for_bus_value(
			source="twincat",
			source_id=cid,
			key_predicate=lambda k: k == var,
			timeout_s=float(timeout_s),
		)

		if msg_payload.get("error") in ("worker_error", "timeout"):
			return default

		return msg_payload.get("value", default)

	# --------------------------- OPC UA helpers --------------------------

	def opcua_value(self, endpoint: str, name_or_alias: str, default: Any = None) -> Any:
		return self.get("opcua", str(endpoint), str(name_or_alias), default)

	def opcua_wait_value(self, endpoint: str, name_or_alias: str, default: Any = None, timeout_s: float = 1.0) -> Any:
		ep = str(endpoint or "")
		key = str(name_or_alias or "")
		if not ep or not key:
			return default

		cached = self.get("opcua", ep, key, default=None)
		if cached is not None:
			return cached

		msg_payload = self._wait_for_bus_value(
			source="opcua",
			source_id=ep,
			key_predicate=lambda k: k == key,
			timeout_s=float(timeout_s),
		)

		if msg_payload.get("error") in ("worker_error", "timeout"):
			return default

		return msg_payload.get("value", default)

	def opcua_read(
		self,
		endpoint: str,
		*,
		node_id: str | None = None,
		alias: str | None = None,
		timeout_s: float = 1.0,
	) -> dict:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return {"error": "no_send_cmd"}

		ep = str(endpoint or "")
		if not ep:
			return {"error": "missing_endpoint"}

		request_id = uuid.uuid4().hex
		self._ctx.send_cmd("opcua", OpcUaCommands.READ, {
			"name": ep,
			"node_id": node_id,
			"alias": alias,
			"request_id": request_id,
		})

		expected_key = f"opcua.{ep}.read.{request_id}"

		msg_payload = self._wait_for_bus_value(
			source="opcua",
			source_id=ep,
			key_predicate=lambda k: k == expected_key,
			timeout_s=float(timeout_s),
		)

		if msg_payload.get("error") == "worker_error":
			return msg_payload

		if msg_payload.get("error") == "timeout":
			msg_payload["expected_key"] = expected_key
			msg_payload["request_id"] = request_id
			msg_payload["endpoint"] = ep
			return msg_payload

		value = msg_payload.get("value")
		if isinstance(value, dict):
			value.setdefault("_meta", {})
			if isinstance(value.get("_meta"), dict):
				value["_meta"].update({
					"endpoint": ep,
					"request_id": request_id,
					"key": expected_key,
				})
			return value

		return {
			"value": value,
			"_meta": {"endpoint": ep, "request_id": request_id, "key": expected_key},
		}

	def opcua_write(
		self,
		endpoint: str,
		*,
		node_id: str | None = None,
		alias: str | None = None,
		name_or_alias: str | None = None,
		value: Any = None,
	) -> None:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return
		ep = str(endpoint or "")
		if not ep:
			return
		self._ctx.send_cmd("opcua", OpcUaCommands.WRITE, {
			"name": ep,
			"node_id": str(node_id) if node_id else None,
			"alias": alias,
			"name_or_alias": name_or_alias,
			"value": value,
		})

	# ----------------------------- REST sync ----------------------------

	def rest_request(
		self,
		endpoint: str,
		*,
		method: str = "GET",
		path: str | None = None,
		url: str | None = None,
		params: dict[str, Any] | None = None,
		headers: dict[str, Any] | None = None,
		json_body: Any = None,
		data: Any = None,
		timeout_s: float = 10.0,
	) -> dict:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return {"error": "no_send_cmd"}

		if RestApiCommands is None:
			return {"error": "no_rest_commands"}

		ep = str(endpoint or "")
		if not ep:
			return {"error": "missing_endpoint"}

		request_id = uuid.uuid4().hex
		self._ctx.send_cmd("rest_api", RestApiCommands.REQUEST, {
			"endpoint": ep,
			"request_id": request_id,
			"method": str(method or "GET").upper(),
			"path": path,
			"url": url,
			"params": params if isinstance(params, dict) else None,
			"headers": headers if isinstance(headers, dict) else None,
			"json": json_body,
			"data": data,
			"timeout_s": float(timeout_s),
		})

		expected_key = "rest.%s.result.%s" % (ep, request_id)

		msg_payload = self._wait_for_bus_value(
			source="rest_api",
			source_id=ep,
			key_predicate=lambda k: k == expected_key,
			timeout_s=float(timeout_s),
		)

		if msg_payload.get("error") == "worker_error":
			return msg_payload

		if msg_payload.get("error") == "timeout":
			msg_payload["expected_key"] = expected_key
			msg_payload["request_id"] = request_id
			msg_payload["endpoint"] = ep
			return msg_payload

		value = msg_payload.get("value")
		if isinstance(value, dict):
			value.setdefault("_meta", {})
			if isinstance(value.get("_meta"), dict):
				value["_meta"].update({
					"endpoint": ep,
					"request_id": request_id,
					"key": expected_key,
				})
			return value

		return {
			"value": value,
			"_meta": {"endpoint": ep, "request_id": request_id, "key": expected_key},
		}

	def rest_get(self, endpoint: str, path: str, params: dict[str, Any] | None = None, timeout_s: float = 10.0) -> dict:
		return self.rest_request(endpoint, method="GET", path=path, params=params, timeout_s=timeout_s)

	def rest_post_json(self, endpoint: str, path: str, body: Any, timeout_s: float = 10.0) -> dict:
		return self.rest_request(endpoint, method="POST", path=path, json_body=body, timeout_s=timeout_s)

	# ----------------------------- iTAC sync ----------------------------

	def itac_station_setting(self, connection_id: str, keys: list[str], timeout_s: float = 5.0) -> dict:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return {"error": "no_send_cmd"}

		cid = str(connection_id or "")
		if not cid:
			return {"error": "missing_connection_id"}

		request_id = uuid.uuid4().hex
		if ItacCommands is None:
			return {"error": "no_itac_commands"}

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

	def itac_custom_function(self, connection_id: str, method_name: str, in_args: list[Any], timeout_s: float = 10.0) -> dict:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return {"error": "no_send_cmd"}

		cid = str(connection_id or "")
		if not cid:
			return {"error": "missing_connection_id"}

		request_id = uuid.uuid4().hex
		if ItacCommands is None:
			return {"error": "no_itac_commands"}

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
		if ItacCommands is None:
			return {"error": "no_itac_commands"}

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

	def _itac_result_dict(self, res: Any) -> dict[str, Any]:
		if not isinstance(res, dict):
			return {}
		result = res.get("result")
		return result if isinstance(result, dict) else {}

	def _itac_return_value(self, res: Any) -> int | None:
		result = self._itac_result_dict(res)
		for key in ("return_value", "returnCode", "return_code", "resultCode", "result_code", "code"):
			if key in result:
				try:
					return int(result.get(key))
				except Exception:
					return None

		if isinstance(res, dict):
			for key in ("returnCode", "return_code", "resultCode", "result_code", "code"):
				if key in res:
					try:
						return int(res.get(key))
					except Exception:
						return None

		return None

	def _itac_user_name(self, res: Any) -> str:
		result = self._itac_result_dict(res)
		if not result:
			return ""
		return str(result.get("userName") or result.get("username") or "").strip()

	def itac_login_user(
		self,
		connection_id: str,
		*,
		station_number: str,
		username: str,
		password: str | None = None,
		client: str = "01",
		timeout_s: float = 10.0,
	) -> dict:
		"""
		Performs iTAC user login flow in one call:
		1) regGetRegisteredUser
		2) regUnregisterUser (when a user is already logged in)
		3) regRegisterUser
		"""
		cid = str(connection_id or "").strip()
		station = str(station_number or "").strip()
		user = str(username or "").strip()
		pwd = str(password if password is not None else username or "")
		client_id = str(client or "01").strip() or "01"

		if not cid:
			return {"ok": False, "stage": "validate", "error": "missing_connection_id"}
		if not station:
			return {"ok": False, "stage": "validate", "error": "missing_station_number"}
		if not user:
			return {"ok": False, "stage": "validate", "error": "missing_username"}
		if not pwd:
			return {"ok": False, "stage": "validate", "error": "missing_password"}

		logger.info(
			"itac_login_user start: connection_id='{}' station='{}' username='{}' client='{}'",
			cid,
			station,
			user,
			client_id,
		)

		get_registered = self.itac_raw_call(
			cid,
			"regGetRegisteredUser",
			{"stationNumber": station},
			timeout_s=timeout_s,
		)
		if not isinstance(get_registered, dict) or get_registered.get("error"):
			return {
				"ok": False,
				"stage": "get_registered_user",
				"error": str((get_registered or {}).get("error") or "worker_error"),
				"responses": {"get_registered_user": get_registered},
			}

		get_rv = self._itac_return_value(get_registered)
		registered_user = self._itac_user_name(get_registered)
		if get_rv == ITAC_NO_USER_LOGGED_RV:
			registered_user = ""
			logger.info(
				"itac_login_user get_registered_user: connection_id='{}' station='{}' return_value={} => no user logged in, skip unregister",
				cid,
				station,
				get_rv,
			)
		elif get_rv != 0:
			logger.warning(
				"itac_login_user get_registered_user failed: connection_id='{}' station='{}' return_value={}",
				cid,
				station,
				get_rv,
			)
			return {
				"ok": False,
				"stage": "get_registered_user",
				"error": "itac_return_value_%s" % str(get_rv),
				"responses": {"get_registered_user": get_registered},
			}
		else:
			logger.info(
				"itac_login_user get_registered_user: connection_id='{}' station='{}' registered_user='{}'",
				cid,
				station,
				registered_user,
			)

		unregister_res: dict[str, Any] | None = None
		if registered_user and registered_user.lower() == user.lower():
			logger.info(
				"itac_login_user same user already registered: connection_id='{}' station='{}' user='{}' -> skip unregister",
				cid,
				station,
				registered_user,
			)
		elif registered_user:
			logger.info(
				"itac_login_user unregister_user: connection_id='{}' station='{}' user='{}'",
				cid,
				station,
				registered_user,
			)
			unregister_res = self.itac_raw_call(
				cid,
				"regUnregisterUser",
				{
					"stationNumber": station,
					"userName": registered_user,
					"password": registered_user,
					"client": client_id,
				},
				timeout_s=timeout_s,
			)
			if not isinstance(unregister_res, dict) or unregister_res.get("error"):
				return {
					"ok": False,
					"stage": "unregister_user",
					"error": str((unregister_res or {}).get("error") or "worker_error"),
					"responses": {
						"get_registered_user": get_registered,
						"unregister_user": unregister_res,
					},
				}
			unregister_rv = self._itac_return_value(unregister_res)
			if unregister_rv != 0:
				logger.warning(
					"itac_login_user unregister_user failed: connection_id='{}' station='{}' user='{}' return_value={}",
					cid,
					station,
					registered_user,
					unregister_rv,
				)
				return {
					"ok": False,
					"stage": "unregister_user",
					"error": "itac_return_value_%s" % str(unregister_rv),
					"responses": {
						"get_registered_user": get_registered,
						"unregister_user": unregister_res,
					},
				}
			logger.info(
				"itac_login_user unregister_user success: connection_id='{}' station='{}' user='{}'",
				cid,
				station,
				registered_user,
			)

		register_res = self.itac_raw_call(
			cid,
			"regRegisterUser",
			{
				"stationNumber": station,
				"userName": user,
				"password": pwd,
				"client": client_id,
			},
			timeout_s=timeout_s,
		)
		if not isinstance(register_res, dict) or register_res.get("error"):
			return {
				"ok": False,
				"stage": "register_user",
				"error": str((register_res or {}).get("error") or "worker_error"),
				"responses": {
					"get_registered_user": get_registered,
					"unregister_user": unregister_res,
					"register_user": register_res,
				},
			}

		register_rv = self._itac_return_value(register_res)
		ok = register_rv in (0, ITAC_USER_ALREADY_LOGGED_RV)
		profile_res = register_res
		register_res2: dict[str, Any] | None = None
		if register_rv == ITAC_USER_ALREADY_LOGGED_RV:
			logger.info(
				"itac_login_user register_user: connection_id='{}' station='{}' username='{}' return_value={} => already logged in (treated as success)",
				cid,
				station,
				user,
				register_rv,
			)
		if ok:
			register_res2 = self.itac_raw_call(
				cid,
				"regRegisterUser",
				{
					"stationNumber": station,
					"userName": user,
					"password": pwd,
					"client": client_id,
				},
				timeout_s=timeout_s,
			)
			if isinstance(register_res2, dict) and not register_res2.get("error"):
				register_rv2 = self._itac_return_value(register_res2)
				if register_rv2 in (0, ITAC_USER_ALREADY_LOGGED_RV):
					profile_res = register_res2
				else:
					logger.warning(
						"itac_login_user second register_user returned error: connection_id='{}' station='{}' username='{}' return_value={}",
						cid,
						station,
						user,
						register_rv2,
					)
			else:
				logger.warning(
					"itac_login_user second register_user failed: connection_id='{}' station='{}' username='{}' error='{}'",
					cid,
					station,
					user,
					str((register_res2 or {}).get("error") if isinstance(register_res2, dict) else "worker_error"),
				)

			# Retrieve profile fields from regGetRegisteredUser after login.
			post_get_res = self.itac_raw_call(
				cid,
				"regGetRegisteredUser",
				{"stationNumber": station},
				timeout_s=timeout_s,
			)
			if isinstance(post_get_res, dict) and not post_get_res.get("error"):
				post_get_rv = self._itac_return_value(post_get_res)
				if post_get_rv == 0:
					profile_res = post_get_res
				else:
					logger.warning(
						"itac_login_user post-login get_registered_user returned error: connection_id='{}' station='{}' username='{}' return_value={}",
						cid,
						station,
						user,
						post_get_rv,
					)
			else:
				logger.warning(
					"itac_login_user post-login get_registered_user failed: connection_id='{}' station='{}' username='{}' error='{}'",
					cid,
					station,
					user,
					str((post_get_res or {}).get("error") if isinstance(post_get_res, dict) else "worker_error"),
				)
		if ok:
			logger.success(
				"itac_login_user register_user success: connection_id='{}' station='{}' username='{}'",
				cid,
				station,
				user,
			)
		else:
			logger.warning(
				"itac_login_user register_user failed: connection_id='{}' station='{}' username='{}' return_value={}",
				cid,
				station,
				user,
				register_rv,
			)
		return {
			"ok": ok,
			"stage": "register_user",
			"error": "" if ok else "itac_return_value_%s" % str(register_rv),
			"registered_user_before": registered_user,
			"responses": {
				"get_registered_user": get_registered,
				"unregister_user": unregister_res,
				"register_user": register_res,
				"register_user_profile": register_res2,
				"get_registered_user_profile": post_get_res if ok else None,
			},
			"profile_response": profile_res,
		}

	# ---------------------- iTAC ergonomics helpers ----------------------

	def itac_expect_ok(self, res: Any) -> dict:
		"""
		Normalize common iTAC worker response shape into:
		{
			"ok": bool,
			"return_value": int,
			"out_args": list,
			"error": str|None,
			"raw": <original dict>
		}

		Expected success shape (typical):
			{ "result": { "return_value": 0, "outArgs": [...] } }
		"""
		out = {
			"ok": False,
			"return_value": -1,
			"out_args": [],
			"error": None,
			"raw": res,
		}

		if not isinstance(res, dict):
			out["error"] = "itac_response_not_dict"
			return out

		# worker-level error/timeout passthrough
		if "error" in res and res.get("error"):
			out["error"] = str(res.get("error"))
			return out

		result = res.get("result")
		if not isinstance(result, dict):
			out["error"] = "missing_result"
			return out

		rv = to_int(result.get("return_value", -1), -1)
		out["return_value"] = rv

		args = result.get("outArgs")
		if isinstance(args, list):
			out["out_args"] = args
		elif args is None:
			out["out_args"] = []
		else:
			out["out_args"] = [args]

		out["ok"] = (rv == 0)
		if not out["ok"]:
			out["error"] = "itac_return_value_%s" % str(rv)

		return out



	def com_last(self, device_id: str, default: Any = None) -> Any:
		return self.get("com_device", str(device_id), "line", default)

	def com_wait(self, device_id: str, timeout_s: float = 2.0, default: Any = None) -> Any:
		did = str(device_id or "")
		if not did:
			return default

		msg = self._wait_for_bus_value(
			source="com_device",
			source_id=did,
			key_predicate=lambda k: k == "line",
			timeout_s=float(timeout_s),
		)

		if msg.get("error") in ("worker_error", "timeout"):
			return default

		return msg.get("value", default)

	def com_send(self, device_id: str, data: Any, add_delimiter: bool = False) -> None:
		if not callable(getattr(self._ctx, "send_cmd", None)):
			return
		self._ctx.send_cmd("com_device", ComDeviceCommands.SEND, {
			"device_id": str(device_id),
			"data": data,
			"add_delimiter": bool(add_delimiter),
		})
