from __future__ import annotations

import time
import queue
from dataclasses import dataclass, field
from ctypes import sizeof
from typing import Any, Optional, Callable, Dict, Tuple

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
	alias: str = ""
	plc_type: str = "UINT"
	string_len: int = 80
	notification_handle: int = 0
	user_handle: int = 0
	callback: Optional[Callable[..., Any]] = None


@dataclass(slots=True)
class PlcConfig:
	client_id: str
	ams_net_id: str
	ip: str
	port: int = 851
	timeout_ms: int = 2000
	auto_reconnect: bool = True
	reconnect_s: float = 1.0
	subscriptions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class PlcState:
	cfg: PlcConfig
	subs: Dict[str, SubDef] = field(default_factory=dict)
	conn: Optional["pyads.Connection"] = None
	connected: bool = False
	connecting: bool = False
	next_reconnect_at: float = 0.0
	last_error: str = ""
	values: Dict[str, Any] = field(default_factory=dict)
	_last_log_sig: Tuple[Any, ...] = field(default_factory=tuple)


# ------------------------------------------------------------------ Worker

class TwinCatWorker(BaseWorker):

	def run(self) -> None:
		self.start()
		log = logger.bind(worker="twincat")
		log.info("TwinCatWorker started")

		plcs: Dict[str, PlcState] = {}
		last_status_log_ts = 0.0

		try:
			while not self.should_stop():
				self._execute_cmds(log, plcs)
				self._health_and_reconnect(log, plcs)

				any_connected = any(st.connected for st in plcs.values())
				self.set_connected(any_connected)

				now = time.time()
				if now - last_status_log_ts >= 5.0:
					last_status_log_ts = now
					total = len(plcs)
					connected = sum(1 for st in plcs.values() if st.connected)
					connecting = sum(1 for st in plcs.values() if st.connecting)
					log.debug(f"status: plcs={total} connected={connected} connecting={connecting}")

				time.sleep(0.02)

		finally:
			log.info("TwinCatWorker stopping")
			for cid in list(plcs.keys()):
				self._disconnect(log, plcs, cid, reason="shutdown")
			self.close_subscriptions()
			self.mark_stopped()
			log.info("TwinCatWorker stopped")

	# ------------------------------------------------------------------ Commands

	def _execute_cmds(self, log, plcs: Dict[str, PlcState]) -> None:
		for _ in range(50):
			try:
				cmd, payload = self.commands.get_nowait()
			except queue.Empty:
				return

			if cmd in ("__stop__", Commands.STOP):
				log.info("received stop command")
				return

			if cmd == Commands.ADD_PLC:
				cfg = _parse_add_plc_payload(payload)

				if not cfg.client_id:
					log.warning(f"ADD_PLC ignored: missing client_id payload={payload!r}")
					continue
				if not cfg.ams_net_id or not cfg.ip:
					log.warning(f"ADD_PLC ignored: missing ams_net_id or ip client_id={cfg.client_id!r}")
					continue

				if cfg.client_id in plcs:
					self._disconnect(log, plcs, cfg.client_id, reason="replace")

				st = PlcState(cfg=cfg)
				_build_subs(st)
				plcs[cfg.client_id] = st

				log.info(
					f"plc added: client_id={cfg.client_id} ams_net_id={cfg.ams_net_id} ip={cfg.ip} "
					f"port={cfg.port} timeout_ms={cfg.timeout_ms} auto_reconnect={cfg.auto_reconnect} reconnect_s={cfg.reconnect_s}"
				)

				self._connect_and_subscribe(log, st)

			elif cmd == Commands.WRITE:
				self._write(log, plcs, payload)

			else:
				log.debug(f"unknown command ignored: cmd={cmd!r} payload={payload!r}")

	# ------------------------------------------------------------------ Connection

	def _connect_and_subscribe(self, log, st: PlcState) -> None:
		if st.connected or st.connecting:
			return

		if pyads is None:
			st.last_error = "pyads not installed/importable"
			log.error(f"connect failed: client_id={st.cfg.client_id} err={st.last_error}")
			self.publish_error_as(st.cfg.client_id, key=None, action="connect", error=st.last_error)
			self._schedule_reconnect(log, st, reason="pyads_missing")
			return

		st.connecting = True
		try:
			conn = pyads.Connection(st.cfg.ams_net_id, st.cfg.port, st.cfg.ip)
			conn.open()
			conn.set_timeout(int(st.cfg.timeout_ms))

			st.conn = conn
			st.connected = True
			st.connecting = False
			st.next_reconnect_at = 0.0
			st.last_error = ""

			self.publish_connected_as(st.cfg.client_id)
			log.info(f"connected: client_id={st.cfg.client_id} ams_net_id={st.cfg.ams_net_id} ip={st.cfg.ip}:{st.cfg.port}")

			self._subscribe_all(log, st)

		except Exception as e:
			st.last_error = str(e)
			st.connected = False
			st.connecting = False
			self.publish_error_as(st.cfg.client_id, key=None, action="connect", error=st.last_error)
			log.error(f"connect failed: client_id={st.cfg.client_id} err={e!r}")
			self._schedule_reconnect(log, st, reason="connect_exception")

	def _disconnect(self, log, plcs: Dict[str, PlcState], client_id: str, reason: str) -> None:
		st = plcs.get(client_id)
		if not st:
			return

		conn = st.conn
		if conn:
			for sub in list(st.subs.values()):
				try:
					if sub.notification_handle and sub.user_handle:
						conn.del_device_notification(sub.notification_handle, sub.user_handle)
				except Exception:
					pass
				sub.notification_handle = 0
				sub.user_handle = 0
				sub.callback = None

			try:
				conn.close()
			except Exception:
				pass

		was_connected = st.connected

		st.conn = None
		st.connected = False
		st.connecting = False

		if was_connected:
			self.publish_disconnected_as(client_id, reason=reason)
			log.info(f"disconnected: client_id={client_id} reason={reason}")
		else:
			log.debug(f"disconnect: client_id={client_id} reason={reason} (was not connected)")

		self._schedule_reconnect(log, st, reason=f"disconnect_{reason}")

	# ------------------------------------------------------------------ Health + Reconnect

	def _schedule_reconnect(self, log, st: PlcState, reason: str) -> None:
		if not st.cfg.auto_reconnect:
			st.next_reconnect_at = 0.0
			sig = (st.cfg.client_id, "reconnect_disabled", reason)
			if st._last_log_sig != sig:
				st._last_log_sig = sig
				log.debug(f"reconnect disabled: client_id={st.cfg.client_id} reason={reason}")
			return

		delay_s = max(0.2, float(st.cfg.reconnect_s or 1.0))
		st.next_reconnect_at = time.time() + delay_s

		sig = (st.cfg.client_id, "reconnect", int(delay_s), int(st.next_reconnect_at))
		if st._last_log_sig != sig:
			st._last_log_sig = sig
			log.info(f"scheduled reconnect: client_id={st.cfg.client_id} in_s={delay_s} reason={reason}")

	def _health_and_reconnect(self, log, plcs: Dict[str, PlcState]) -> None:
		now = time.time()

		for st in plcs.values():
			if st.connected and st.conn:
				try:
					st.conn.read_state()
				except Exception as e:
					self.publish_error_as(st.cfg.client_id, key=None, action="health_check", error=str(e))
					log.error(f"health check failed: client_id={st.cfg.client_id} err={e!r}")
					self._disconnect(log, plcs, st.cfg.client_id, reason="connection_lost")
					continue

			if (not st.connected) and (not st.connecting) and st.next_reconnect_at and (now >= st.next_reconnect_at):
				st.next_reconnect_at = 0.0
				log.info(f"reconnect due: client_id={st.cfg.client_id}")
				self._connect_and_subscribe(log, st)

	# ------------------------------------------------------------------ Subscribe

	def _subscribe_all(self, log, st: PlcState) -> None:
		for sub in st.subs.values():
			self._subscribe_one(log, st, sub)

	def _subscribe_one(self, log, st: PlcState, sub: SubDef) -> None:
		if pyads is None:
			return
		if not st.conn:
			return

		conn = st.conn
		client_id = st.cfg.client_id
		name = sub.name
		publish_key = sub.alias or sub.name

		data_type, byte_size, is_string, is_wstring = _ads_datatype_and_size(sub.plc_type, sub.string_len)
		attr = pyads.NotificationAttrib(byte_size)

		def _callback(notification, _user):
			try:
				_, _, value = conn.parse_notification(notification, data_type)
			except Exception as e:
				self.publish_error_as(client_id, key=publish_key, action="notify_parse", error=str(e))
				return

			if is_string:
				# value is a ctypes BYTE array -> make raw bytes
				try:
					raw = bytes(value)
				except Exception:
					raw = value if isinstance(value, (bytes, bytearray)) else b""

				# Heuristic: if it looks like UTF-16-LE (zero bytes at odd positions), decode as utf-16-le
				looks_utf16 = (len(raw) >= 4 and raw[1:2] == b"\x00")
				if is_wstring or looks_utf16:
					try:
						raw = raw.split(b"\x00\x00", 1)[0]
						value = raw.decode("utf-16-le", "ignore")
					except Exception:
						pass
				else:
					try:
						value = raw.split(b"\x00", 1)[0].decode("latin1", "ignore")
					except Exception:
						pass

			st.values[publish_key] = value
			self.publish_value_as(client_id, publish_key, value)

		sub.callback = _callback

		try:
			notification_handle, user_handle = conn.add_device_notification(name, attr, _callback)
			sub.notification_handle = int(notification_handle or 0)
			sub.user_handle = int(user_handle or 0)
			log.info(f"subscribed: client_id={client_id} name={name} plc_type={sub.plc_type} byte_size={byte_size}")
		except Exception as e:
			self.publish_error_as(client_id, key=name, action="subscribe", error=str(e))
			log.error(f"subscribe failed: client_id={client_id} name={name} err={e!r}")


	# ------------------------------------------------------------------ Write

	def _write(self, log, plcs: Dict[str, PlcState], payload: Dict[str, Any]) -> None:
		client_id = str(payload.get("client_id") or "")
		name = str(payload.get("name") or "")
		value = payload.get("value")

		if not client_id:
			log.warning(f"WRITE ignored: missing client_id payload={payload!r}")
			return

		st = plcs.get(client_id)
		if not st or not st.conn or not st.connected:
			self.publish_error_as(client_id, key=name, action="write", error="not_connected")
			return

		try:
			target_name = name
			for sub in st.subs.values():
				if name == sub.alias:
					target_name = sub.name
					break
			st.conn.write_by_name(target_name, value)
			self.publish_write_finished_as(client_id, f"write:{name}")
			log.debug(f"write ok: client_id={client_id} name={name!r} target={target_name!r} value_type={type(value)}")
		except Exception as e:
			self.publish_error_as(client_id, key=name, action="write", error=str(e))
			log.error(f"write failed: client_id={client_id} name={name!r} err={e!r}")


# ------------------------------------------------------------------ Helpers

def _parse_add_plc_payload(payload: Dict[str, Any]) -> PlcConfig:
	return PlcConfig(
		client_id=str(payload.get("client_id") or ""),
		ams_net_id=str(payload.get("plc_ams_net_id") or payload.get("ams_net_id") or ""),
		ip=str(payload.get("plc_ip") or payload.get("ip") or ""),
		port=int(payload.get("ads_port", payload.get("port", 851)) or 851),
		timeout_ms=int(payload.get("timeout_ms", 2000) or 2000),
		auto_reconnect=bool(payload.get("auto_reconnect", True)),
		reconnect_s=float(payload.get("reconnect_s", 1.0) or 1.0),
		subscriptions=payload.get("subscriptions", []) if isinstance(payload.get("subscriptions", []), list) else [],
	)


def _build_subs(st: PlcState) -> None:
	st.subs = {}
	for entry in st.cfg.subscriptions:
		try:
			name = str(entry.get("name") or "")
			if not name:
				continue
			st.subs[name] = SubDef(
				name=name,
				alias=str(entry.get("alias") or "").strip(),
				plc_type=str(entry.get("plc_type", "UINT") or "UINT"),
				string_len=int(entry.get("string_len", 80) or 80),
			)
		except Exception:
			continue


import re
from ctypes import sizeof

def _ensure_ads_type_class(dt):
	# pyads versions differ: sometimes PLCTYPE_STRING returns an instance
	# parse_notification needs a *class* for issubclass(...)
	if isinstance(dt, type):
		return dt
	return type(dt)

def _ads_datatype_and_size(plc_type_raw: str, string_len: int):
	t_raw = str(plc_type_raw or "").strip().upper()

	if pyads is None:
		return None, 0, False, False  # dt_class, byte_size, is_string, is_wstring

	m = re.match(r"^(W?STRING)(?:\s*[\(\[]\s*(\d+)\s*[\)\]])?$", t_raw)
	if m:
		base = m.group(1)
		n = int(m.group(2) or string_len or 80)

		if base == "WSTRING":
			byte_size = (n + 1) * 2
			dt_cls = _ensure_ads_type_class(pyads.PLCTYPE_BYTE * byte_size)
			return dt_cls, int(sizeof(dt_cls)), True, True

		# STRING
		byte_size = (n + 1)
		dt_cls = _ensure_ads_type_class(pyads.PLCTYPE_BYTE * byte_size)
		return dt_cls, int(sizeof(dt_cls)), True, False

	# non-strings
	dt = getattr(pyads, "PLCTYPE_%s" % t_raw, pyads.PLCTYPE_UINT)
	dt_cls = _ensure_ads_type_class(dt)
	return dt_cls, int(sizeof(dt_cls)), False, False

