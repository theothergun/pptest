# twincat_worker.py
from __future__ import annotations

import time
import queue
from dataclasses import dataclass, field
from ctypes import sizeof
from typing import Any, Optional, Callable

from loguru import logger

try:
	import pyads
except Exception:
	pyads = None  # type: ignore

from services.worker_commands import TwinCatCommands as Commands
from services.workers.base_worker import BaseWorker


# ------------------------------------------------------------------ Models

@dataclass(slots=True)
class SubDef:
	name: str
	plc_type: str = "UINT"
	string_len: int = 80
	notification_handle: int = 0
	user_handle: int = 0
	callback: Optional[Callable[..., Any]] = None


@dataclass(slots=True)
class PlcState:
	client_id: str
	ams_net_id: str
	ip: str
	port: int = 851
	timeout_ms: int = 2000
	auto_reconnect: bool = True
	reconnect_s: float = 1.0
	subs: dict[str, SubDef] = field(default_factory=dict)
	conn: Optional["pyads.Connection"] = None
	connected: bool = False
	connecting: bool = False
	next_reconnect_at: float = 0.0
	last_error: str = ""
	values: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------ Worker

class TwinCatWorker(BaseWorker):

	def run(self) -> None:
		self.start()
		log = logger.bind(worker="twincat")
		plcs: dict[str, PlcState] = {}

		while not self.should_stop():
			self._process_commands(log, plcs)
			self._reconnect_if_needed(log, plcs)
			self.set_connected(any(st.connected for st in plcs.values()))
			time.sleep(0.02)

		for st in list(plcs.values()):
			self._disconnect(log, st, "shutdown")

		self.mark_stopped()

	# ------------------------------------------------------------------ Commands

	def _process_commands(self, log, plcs: dict[str, PlcState]) -> None:
		for _ in range(100):
			try:
				cmd, payload = self.commands.get_nowait()
			except queue.Empty:
				return

			if cmd == Commands.ADD_PLC:
				client_id = payload["client_id"]
				try:
					st = PlcState(
						client_id=client_id,
						ams_net_id=payload["plc_ams_net_id"],
						ip=payload["plc_ip"],
						port=int(payload.get("ads_port", 851)),
						timeout_ms=int(payload.get("timeout_ms", 2000)),
						auto_reconnect=bool(payload.get("auto_reconnect", True)),
						reconnect_s=float(payload.get("reconnect_s", 1.0)),
					)
					self._build_subs(st, payload)

				except Exception as e:
					self.current_source_id = client_id
					self.publish_error(None, "add_plc", str(e))
					continue

				if client_id in plcs:
					self._disconnect(log, plcs[client_id], "replace")

				plcs[client_id] = st
				self._connect_and_subscribe(log, st)

			elif cmd == Commands.WRITE:
				self._write(log, plcs, payload)

	# ------------------------------------------------------------------ Connection

	def _connect_and_subscribe(self, log, st: PlcState) -> None:
		if st.connected or st.connecting:
			return

		st.connecting = True
		try:
			conn = pyads.Connection(st.ams_net_id, st.port, st.ip)
			conn.open()
			conn.set_timeout(st.timeout_ms)

			st.conn = conn
			st.connected = True
			st.connecting = False
			st.next_reconnect_at = 0.0

			self.current_source_id = st.client_id
			self.publish_connected()

			self._subscribe_all(log, st)

		except Exception as e:
			st.last_error = str(e)
			st.connected = False
			st.connecting = False
			self.current_source_id = st.client_id
			self.publish_error(None, "connect", st.last_error)
			self._schedule_reconnect(st)

	def _disconnect(self, log, st: PlcState, reason: str) -> None:
		if st.conn:
			try:
				st.conn.close()
			except Exception:
				pass

		st.conn = None
		st.connected = False
		st.connecting = False

		self.current_source_id = st.client_id
		self.publish_disconnected(reason)

	# ------------------------------------------------------------------ Reconnect

	def _schedule_reconnect(self, st: PlcState) -> None:
		if st.auto_reconnect:
			st.next_reconnect_at = time.time() + max(0.2, st.reconnect_s)

	def _reconnect_if_needed(self, log, plcs: dict[str, PlcState]) -> None:
		now = time.time()
		for st in plcs.values():
			if st.connected and st.conn:
				try:
					st.conn.read_state()
				except Exception as e:
					self.current_source_id = st.client_id
					self.publish_error(None, "health_check", str(e))
					self._disconnect(log, st, "connection_lost")
					self._schedule_reconnect(st)

			if not st.connected and not st.connecting and st.next_reconnect_at and now >= st.next_reconnect_at:
				st.next_reconnect_at = 0.0
				self._connect_and_subscribe(log, st)

	# ------------------------------------------------------------------ Subscribe

	def _subscribe_all(self, log, st: PlcState) -> None:
		for sub in st.subs.values():
			self._subscribe_one(log, st, sub)

	def _subscribe_one(self, log, st: PlcState, sub: SubDef) -> None:
		data_type, byte_size, is_string = _ads_datatype_and_size(sub.plc_type, sub.string_len)
		attr = pyads.NotificationAttrib(byte_size)

		conn = st.conn
		client_id = st.client_id
		name = sub.name

		def _callback(notification, _):
			try:
				_, _, value = conn.parse_notification(notification, data_type)
			except Exception as e:
				self.current_source_id = client_id
				self.publish_error(name, "notify_parse", str(e))
				return

			if is_string and isinstance(value, (bytes, bytearray)):
				value = bytes(value).split(b"\x00", 1)[0].decode("utf-8", "ignore")

			st.values[name] = value
			self.current_source_id = client_id
			self.publish_value(name, value)

		sub.callback = _callback
		conn.add_device_notification(name, attr, _callback)

	# ------------------------------------------------------------------ Write

	def _write(self, log, plcs: dict[str, PlcState], payload: dict[str, Any]) -> None:
		client_id = payload.get("client_id")
		name = payload.get("name")
		value = payload.get("value")

		st = plcs.get(client_id)
		if not st or not st.conn or not st.connected:
			self.current_source_id = client_id
			self.publish_write_error(name, "not_connected")
			return

		try:
			st.conn.write_by_name(name, value)
			self.current_source_id = client_id
			self.publish_write_finished(name)
		except Exception as e:
			self.current_source_id = client_id
			self.publish_write_error(name, str(e))

	# ------------------------------------------------------------------ Sub config

	def _build_subs(self, st: PlcState, payload: dict[str, Any]) -> None:
		for entry in payload.get("subscriptions", []):
			st.subs[entry["name"]] = SubDef(
				name=entry["name"],
				plc_type=entry.get("plc_type", "UINT"),
				string_len=entry.get("string_len", 80),
			)


# ------------------------------------------------------------------ Helper

def _ads_datatype_and_size(plc_type_raw: str, string_len: int):
	t = plc_type_raw.upper()
	if t == "STRING":
		return pyads.PLCTYPE_STRING(string_len), string_len + 1, True
	return getattr(pyads, f"PLCTYPE_{t}", pyads.PLCTYPE_UINT), sizeof(pyads.PLCTYPE_UINT), False
