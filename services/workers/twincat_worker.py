from __future__ import annotations

import os
import time
import queue
import sys
from dataclasses import dataclass, field
from ctypes import sizeof
from typing import Any, Optional, Callable, Dict, Tuple

from loguru import logger

def _import_pyads_with_dll_dirs():
	"""
	Import pyads with Windows DLL search path bootstrap.

	Python 3.8+ tightened DLL loading; `TcAdsDll.dll` may be present but not found
	unless its directory is explicitly added via `os.add_dll_directory`.
	"""
	try:
		import pyads as _pyads  # type: ignore
		return _pyads
	except Exception:
		pass

	if sys.platform != "win32":
		return None

	candidates: list[str] = []

	# Optional explicit override.
	for env_key in ("TCADSDLL_DIR", "TCADSDLL_PATH"):
		raw = str(os.environ.get(env_key, "") or "").strip()
		if raw:
			candidates.append(raw)

	# Project root often contains TcAdsDll.dll in this repository.
	try:
		project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
		candidates.append(project_root)
	except Exception:
		pass

	# Common TwinCAT install locations.
	candidates.extend([
		r"C:\TwinCAT\AdsApi\TcAdsDll\x64",
		r"C:\TwinCAT\AdsApi\TcAdsDll\x86",
	])

	# Current process working directory as a last resort.
	candidates.append(os.getcwd())

	seen: set[str] = set()
	for entry in candidates:
		d = os.path.abspath(str(entry or "").strip())
		if not d or d in seen or not os.path.isdir(d):
			continue
		seen.add(d)

		dll_file = os.path.join(d, "TcAdsDll.dll")
		if not os.path.exists(dll_file):
			continue

		try:
			os.add_dll_directory(d)
		except Exception:
			# Fallback for environments where add_dll_directory is unavailable/restricted.
			if d not in str(os.environ.get("PATH", "")):
				os.environ["PATH"] = d + os.pathsep + str(os.environ.get("PATH", ""))

		try:
			import pyads as _pyads  # type: ignore
			return _pyads
		except Exception:
			continue

	return None


pyads = _import_pyads_with_dll_dirs()  # type: ignore

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
		log.info("[run] - worker_started - worker=TwinCatWorker")

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
					# heartbeat publish so UI status pages can sync even if they open later
					for st in plcs.values():
						if st.connected:
							self.publish_connected_as(st.cfg.client_id)
							# Re-publish cached values so late subscribers (e.g. newly opened UI panel)
							# receive current data even without a fresh PLC value change event.
							for k, v in list(st.values.items()):
								try:
									self.publish_value_as(st.cfg.client_id, str(k), v)
								except Exception:
									pass
						else:
							reason = st.last_error or "not_connected"
							self.publish_disconnected_as(st.cfg.client_id, reason=reason)

				time.sleep(0.02)

		finally:
			log.info("[run] - worker_stopping - worker=TwinCatWorker")
			for cid in list(plcs.keys()):
				self._disconnect(log, plcs, cid, reason="shutdown")
			self.close_subscriptions()
			self.mark_stopped()
			log.info("[run] - worker_stopped - worker=TwinCatWorker")

	# ------------------------------------------------------------------ Commands

	def _execute_cmds(self, log, plcs: Dict[str, PlcState]) -> None:
		for _ in range(50):
			try:
				cmd, payload = self.commands.get_nowait()
			except queue.Empty:
				return

			if cmd in ("__stop__", Commands.STOP):
				log.info("[_execute_cmds] - received_stop_command")
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

			elif cmd == Commands.RESET:
				client_id = str(payload.get("client_id") or "").strip()
				self._reset_plc(log, plcs, client_id)

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
			# open() only opens the local ADS port. Verify remote target is reachable.
			conn.read_device_info()

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

	def _reset_plc(self, log, plcs: Dict[str, PlcState], client_id: str) -> None:
		if not client_id:
			log.warning("RESET ignored: missing client_id")
			return
		st = plcs.get(client_id)
		if not st:
			log.warning(f"RESET ignored: unknown client_id={client_id}")
			return
		self._disconnect(log, plcs, client_id, reason="reset")
		st.values.clear()
		st.last_error = ""
		st.next_reconnect_at = 0.0
		self._connect_and_subscribe(log, st)

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

		def _normalize_ads_value(value: Any) -> Any:
			if not is_string:
				return value
			# value is typically a ctypes BYTE array for STRING/WSTRING
			try:
				raw = bytes(value)
			except Exception:
				raw = value if isinstance(value, (bytes, bytearray)) else b""
			looks_utf16 = (len(raw) >= 4 and raw[1:2] == b"\x00")
			if is_wstring or looks_utf16:
				try:
					raw = raw.split(b"\x00\x00", 1)[0]
					return raw.decode("utf-16-le", "ignore")
				except Exception:
					return value
			try:
				return raw.split(b"\x00", 1)[0].decode("latin1", "ignore")
			except Exception:
				return value

		def _callback(notification, _user):
			try:
				_, _, value = conn.parse_notification(notification, data_type)
			except Exception as e:
				self.publish_error_as(client_id, key=publish_key, action="notify_parse", error=str(e))
				return
			value = _normalize_ads_value(value)

			st.values[publish_key] = value
			self.publish_value_as(client_id, publish_key, value)
			# also publish under full name for compatibility
			if publish_key != name:
				self.publish_value_as(client_id, name, value)

		sub.callback = _callback

		try:
			notification_handle, user_handle = conn.add_device_notification(name, attr, _callback)
			sub.notification_handle = int(notification_handle or 0)
			sub.user_handle = int(user_handle or 0)
			log.info(f"subscribed: client_id={client_id} name={name} plc_type={sub.plc_type} byte_size={byte_size}")
			# Publish an initial snapshot so UI doesn't stay at None until value changes.
			try:
				initial = conn.read_by_name(name, data_type)
				initial = _normalize_ads_value(initial)
				st.values[publish_key] = initial
				self.publish_value_as(client_id, publish_key, initial)
				if publish_key != name:
					self.publish_value_as(client_id, name, initial)
			except Exception as init_err:
				log.debug(f"initial read failed: client_id={client_id} name={name} err={init_err!r}")
		except Exception as e:
			hint = _ads_error_hint(e)
			err_text = str(e)
			if hint:
				err_text = f"{err_text} ({hint})"
			self.publish_error_as(client_id, key=name, action="subscribe", error=err_text)
			if hint:
				log.error(f"subscribe failed: client_id={client_id} name={name} err={e!r} hint={hint}")
			else:
				log.error(f"subscribe failed: client_id={client_id} name={name} err={e!r}")


	# ------------------------------------------------------------------ Write

	def _write(self, log, plcs: Dict[str, PlcState], payload: Dict[str, Any]) -> None:
		client_id = str(payload.get("client_id") or "")
		name = str(payload.get("name") or "")
		value = payload.get("value")
		payload_type = str(payload.get("plc_type") or "").strip()
		payload_strlen = int(payload.get("string_len", 80) or 80)

		if not client_id:
			log.warning(f"WRITE ignored: missing client_id payload={payload!r}")
			return

		st = plcs.get(client_id)
		if not st or not st.conn or not st.connected:
			self.publish_error_as(client_id, key=name, action="write", error="not_connected")
			return

		try:
			target_name = name
			sub_plc_type = ""
			sub_strlen = 0
			for sub in st.subs.values():
				if name == sub.alias:
					target_name = sub.name
					sub_plc_type = sub.plc_type
					sub_strlen = sub.string_len
					break
				if name == sub.name:
					sub_plc_type = sub.plc_type
					sub_strlen = sub.string_len

			plc_type = payload_type or sub_plc_type
			string_len = payload_strlen if payload_type else (sub_strlen or payload_strlen)

			if plc_type and plc_type.upper().startswith(("STRING", "WSTRING")):
				if value is None:
					value = ""
				if not isinstance(value, str):
					value = str(value)

			if plc_type:
				dt_cls, byte_size, is_string, is_wstring = _ads_datatype_and_size(plc_type, string_len)
				if is_string:
					if value is None:
						value = ""
					if not isinstance(value, str):
						value = str(value)
					if is_wstring:
						raw = value.encode("utf-16-le", "ignore")
						raw = raw.split(b"\x00\x00", 1)[0]
						raw = raw[: max(0, byte_size - 2)]
						raw = raw + b"\x00\x00"
					else:
						raw = value.encode("latin1", "ignore")
						raw = raw.split(b"\x00", 1)[0]
						raw = raw[: max(0, byte_size - 1)]
						raw = raw + b"\x00"
					if byte_size > 0:
						raw = raw.ljust(byte_size, b"\x00")
					value = raw
				st.conn.write_by_name(target_name, value, dt_cls)
			else:
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
	used_aliases: set[str] = set()
	for entry in st.cfg.subscriptions:
		try:
			name = str(entry.get("name") or "")
			if not name:
				continue
			alias = str(entry.get("alias") or "").strip()
			if not alias:
				# auto-generate a short alias from the last segment if unique
				short_alias = name.split(".")[-1].replace("[", "_").replace("]", "").strip("_")
				if short_alias and short_alias not in used_aliases:
					alias = short_alias
			if alias:
				used_aliases.add(alias)
			st.subs[name] = SubDef(
				name=name,
				alias=alias,
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


def _ads_error_hint(err: Exception) -> str:
	text = f"{err!r}"
	if "ADSError(7)" in text:
		return "possible AMS Net ID/route mismatch (target not reachable)"
	return ""

