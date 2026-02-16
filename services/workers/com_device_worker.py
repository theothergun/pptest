# services/workers/com_device_worker.py
from __future__ import annotations

import time
import queue
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from loguru import logger

import serial  # pyserial
from serial import SerialException

from services.workers.base_worker import BaseWorker
from services.worker_topics import WorkerTopics
from services.worker_commands import ComDeviceCommands as Commands


KEY_STATUS = "status"
KEY_LINE = "line"
KEY_RX_RAW = "rx_raw"
KEY_TX = "tx"


@dataclass
class ComDeviceEntry:
	device_id: str
	port: str
	baudrate: int = 115200
	bytesize: int = 8
	parity: str = "N"			# N/E/O/M/S
	stopbits: float = 1.0		# 1, 1.5, 2
	timeout_s: float = 0.2
	write_timeout_s: float = 0.5

	mode: str = "line"			# "line" or "raw"
	delimiter: bytes = b"\n"	# only used in mode="line"
	encoding: str = "utf-8"		# only used for decoding lines

	read_chunk_size: int = 256
	max_line_len: int = 4096	# safety clamp in case delimiter never arrives

	reconnect_min_s: float = 0.5
	reconnect_max_s: float = 5.0


@dataclass
class _Runtime:
	cfg: ComDeviceEntry
	ser: Optional[serial.Serial] = None
	connected: bool = False
	last_error: str = ""
	reconnect_s: float = 0.5
	rx_buf: bytearray = field(default_factory=bytearray)
	_last_status_sig: str = ""


class ComDeviceWorker(BaseWorker):
	"""
	Generic COM/Serial device worker.

	Publishes (WorkerTopics.VALUE_CHANGED) with payload:
		{"key": "<KEY_...>", "value": <...>}

	- KEY_STATUS: dict {device_id, port, connected, error, ...}
	- KEY_LINE:   decoded string (mode="line")
	- KEY_RX_RAW: list[int] raw bytes (optional debug)
	- KEY_TX:     dict {len, ok}

	ERROR topic payload:
		{"key": str|None, "action": str, "error": str}

	Commands:
	- ADD_DEVICE: add/replace device
	- REMOVE_DEVICE: remove device
	- LIST_DEVICES: publish device list
	- SEND: write bytes/text to a device
	"""

	def __init__(
		self,
		name: str,
		bridge: Any,
		worker_bus: Any,
		commands: "queue.Queue[tuple[str, dict[str, Any]]]",
		stop: Any,
		send_cmd: Any,
	) -> None:
		super(ComDeviceWorker, self).__init__(
			name=name,
			bridge=bridge,
			worker_bus=worker_bus,
			commands=commands,
			stop=stop,
			send_cmd=send_cmd,
		)

		self._log = logger.bind(component="ComDeviceWorker", worker=name)
		self._devices: Dict[str, _Runtime] = {}

	# ------------------------------------------------------------------ helpers

	def _format_exc(self) -> str:
		try:
			return traceback.format_exc()
		except Exception:
			return "<traceback unavailable>"

	def _publish_value(self, device_id: str, key: str, value: Any) -> None:
		self.worker_bus.publish(
			WorkerTopics.VALUE_CHANGED,
			source="com_device",
			source_id=str(device_id),
			payload={"key": str(key), "value": value},
		)

	def _publish_error(self, device_id: str, action: str, error: str, key: Optional[str] = None) -> None:
		self.worker_bus.publish(
			WorkerTopics.ERROR,
			source="com_device",
			source_id=str(device_id),
			payload={
				"key": key,
				"action": str(action),
				"error": str(error),
			},
		)

	def _status_payload(self, rt: _Runtime) -> dict:
		cfg = rt.cfg
		return {
			"device_id": str(cfg.device_id),
			"port": str(cfg.port),
			"connected": bool(rt.connected),
			"error": str(rt.last_error or ""),
			"baudrate": int(cfg.baudrate),
			"bytesize": int(cfg.bytesize),
			"parity": str(cfg.parity),
			"stopbits": float(cfg.stopbits),
			"mode": str(cfg.mode),
		}

	def _publish_status_if_changed(self, rt: _Runtime, force: bool = False) -> None:
		payload = self._status_payload(rt)
		sig = "%s|%s|%s|%s|%s|%s|%s|%s" % (
			payload.get("device_id"),
			payload.get("port"),
			payload.get("connected"),
			payload.get("error"),
			payload.get("baudrate"),
			payload.get("bytesize"),
			payload.get("parity"),
			payload.get("stopbits"),
		)
		if force or sig != rt._last_status_sig:
			rt._last_status_sig = sig
			self._publish_value(rt.cfg.device_id, KEY_STATUS, payload)

	def _coerce_bytes(self, cfg: ComDeviceEntry, data: Any) -> bytes:
		if data is None:
			return b""

		if isinstance(data, bytes):
			return data

		if isinstance(data, bytearray):
			return bytes(data)

		if isinstance(data, list) or isinstance(data, tuple):
			try:
				return bytes(bytearray([int(x) & 0xFF for x in data]))
			except Exception:
				return b""

		# fallback: string
		try:
			s = str(data)
		except Exception:
			return b""

		try:
			return s.encode(cfg.encoding or "utf-8", errors="replace")
		except Exception:
			return s.encode("utf-8", errors="replace")

	# ------------------------------------------------------------------ connect/close/read

	def _connect(self, rt: _Runtime) -> None:
		cfg = rt.cfg
		ser = serial.Serial(
			port=str(cfg.port),
			baudrate=int(cfg.baudrate),
			bytesize=int(cfg.bytesize),
			parity=str(cfg.parity),
			stopbits=float(cfg.stopbits),
			timeout=float(cfg.timeout_s),
			write_timeout=float(cfg.write_timeout_s),
		)

		rt.ser = ser
		rt.connected = True
		rt.last_error = ""
		rt.reconnect_s = float(cfg.reconnect_min_s)
		rt.rx_buf = bytearray()

		self._log.info("[connect] device_id=%s port=%s" % (cfg.device_id, cfg.port))
		self._publish_status_if_changed(rt, True)

	def _close(self, rt: _Runtime, reason: str) -> None:
		rt.connected = False
		rt.last_error = str(reason or "")
		try:
			if rt.ser is not None:
				rt.ser.close()
		except Exception:
			pass
		rt.ser = None
		rt.rx_buf = bytearray()

		self._publish_status_if_changed(rt, True)

	def _read_chunk(self, rt: _Runtime) -> Optional[bytes]:
		if not rt.connected or rt.ser is None:
			return None

		try:
			chunk = rt.ser.read(int(rt.cfg.read_chunk_size))
			if not chunk:
				return None
			return chunk
		except SerialException:
			raise
		except Exception:
			raise

	def _drain_lines(self, rt: _Runtime, chunk: bytes) -> None:
		cfg = rt.cfg

		rt.rx_buf.extend(chunk)

		# safety clamp: if we never see delimiter, buffer can grow forever
		if len(rt.rx_buf) > int(cfg.max_line_len):
			rt.rx_buf = rt.rx_buf[-int(cfg.max_line_len):]

		delim = cfg.delimiter or b"\n"

		while True:
			idx = rt.rx_buf.find(delim)
			if idx < 0:
				return

			raw = bytes(rt.rx_buf[:idx])
			del rt.rx_buf[:idx + len(delim)]

			# publish raw for debugging (optional, but useful)
			try:
				self._publish_value(cfg.device_id, KEY_RX_RAW, list(bytearray(raw)))
			except Exception:
				pass

			try:
				text = raw.decode(cfg.encoding or "utf-8", errors="replace").strip()
			except Exception:
				text = ""

			if text:
				# global loguru (your requirement style)
				logger.bind(worker=self.name, device_id=cfg.device_id).info("rx: %s" % text)
				self._publish_value(cfg.device_id, KEY_LINE, text)

	# ------------------------------------------------------------------ command handlers

	def _cmd_add_device(self, payload: dict[str, Any]) -> None:
		device_id = str(payload.get("device_id") or payload.get("id") or "").strip()
		port = str(payload.get("port") or "").strip()

		if not device_id:
			self._publish_error("com_device", "add_device", "missing device_id")
			return
		if not port:
			self._publish_error(device_id, "add_device", "missing port")
			return

		cfg = ComDeviceEntry(
			device_id=device_id,
			port=port,
			baudrate=int(payload.get("baudrate", 115200)),
			bytesize=int(payload.get("bytesize", 8)),
			parity=str(payload.get("parity", "N")),
			stopbits=float(payload.get("stopbits", 1.0)),
			timeout_s=float(payload.get("timeout_s", 0.2)),
			write_timeout_s=float(payload.get("write_timeout_s", 0.5)),
			mode=str(payload.get("mode", "line")),
			delimiter=self._coerce_bytes(ComDeviceEntry(device_id=device_id, port=port), payload.get("delimiter") or "\n"),
			encoding=str(payload.get("encoding", "utf-8")),
			read_chunk_size=int(payload.get("read_chunk_size", 256)),
			max_line_len=int(payload.get("max_line_len", 4096)),
			reconnect_min_s=float(payload.get("reconnect_min_s", 0.5)),
			reconnect_max_s=float(payload.get("reconnect_max_s", 5.0)),
		)

		# replace existing
		old = self._devices.get(device_id)
		if old is not None:
			try:
				self._close(old, "replaced")
			except Exception:
				pass

		rt = _Runtime(cfg=cfg, reconnect_s=float(cfg.reconnect_min_s))
		self._devices[device_id] = rt
		self._publish_status_if_changed(rt, True)
		self._log.info("[add_device] device_id=%s port=%s" % (device_id, port))

	def _cmd_remove_device(self, payload: dict[str, Any]) -> None:
		device_id = str(payload.get("device_id") or payload.get("id") or "").strip()
		if not device_id:
			return

		rt = self._devices.pop(device_id, None)
		if rt is None:
			return

		try:
			self._close(rt, "removed")
		except Exception:
			pass

		self._log.info("[remove_device] device_id=%s" % device_id)

	def _cmd_list_devices(self, payload: dict[str, Any]) -> None:
		items = []
		for device_id, rt in self._devices.items():
			p = self._status_payload(rt)
			items.append(p)

		# publish under synthetic source_id
		self.worker_bus.publish(
			WorkerTopics.VALUE_CHANGED,
			source="com_device",
			source_id="com_device",
			payload={"key": "devices", "value": items},
		)

	def _cmd_send(self, payload: dict[str, Any]) -> None:
		device_id = str(payload.get("device_id") or payload.get("id") or "").strip()
		if not device_id:
			self._publish_error("com_device", "send", "missing device_id")
			return

		rt = self._devices.get(device_id)
		if rt is None:
			self._publish_error(device_id, "send", "unknown device_id")
			return

		if not rt.connected or rt.ser is None:
			self._publish_error(device_id, "send", "device not connected")
			return

		cfg = rt.cfg
		data = payload.get("data")
		add_delimiter = bool(payload.get("add_delimiter", False))

		b = self._coerce_bytes(cfg, data)
		if add_delimiter and cfg.mode == "line":
			b = b + (cfg.delimiter or b"\n")

		if not b:
			return

		try:
			n = rt.ser.write(b)
			try:
				rt.ser.flush()
			except Exception:
				pass

			self._publish_value(device_id, KEY_TX, {"len": int(n), "ok": True})
		except Exception as ex:
			err = "send failed: %s" % str(ex)
			self._publish_error(device_id, "send", err)
			self._close(rt, err)

	# ------------------------------------------------------------------ loop

	def run(self) -> None:
		self.start()
		self._log.info("[run] started")

		handlers = {
			Commands.ADD_DEVICE: self._cmd_add_device,
			Commands.REMOVE_DEVICE: self._cmd_remove_device,
			Commands.LIST_DEVICES: self._cmd_list_devices,
			Commands.SEND: self._cmd_send,
		}

		try:
			while not self.should_stop():
				# quick command handling
				self.dispatch_commands(handlers, limit=50, unknown_handler=None)

				for device_id, rt in list(self._devices.items()):
					if not rt.connected or rt.ser is None:
						try:
							self._connect(rt)
						except Exception as ex:
							err = "connect failed: %s" % str(ex)
							self._publish_error(device_id, "connect", err)
							self._close(rt, err)

							time.sleep(rt.reconnect_s)
							rt.reconnect_s = min(float(rt.cfg.reconnect_max_s), rt.reconnect_s * 1.5)
							continue

					try:
						chunk = self._read_chunk(rt)
						if not chunk:
							continue

						if rt.cfg.mode == "raw":
							self._publish_value(device_id, KEY_RX_RAW, list(bytearray(chunk)))
						else:
							self._drain_lines(rt, chunk)

					except Exception as ex:
						err = "read failed: %s" % str(ex)
						self._publish_error(device_id, "read", err)
						self._close(rt, err)

				time.sleep(0.005)

		except Exception:
			self._log.error("[run] crashed\n%s" % self._format_exc())
		finally:
			for rt in list(self._devices.values()):
				try:
					self._close(rt, "stopped")
				except Exception:
					pass

			self.mark_stopped()
			self._log.info("[run] stopped")
