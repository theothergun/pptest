# tcp_client_worker.py
from __future__ import annotations

import time
import socket
import selectors
import queue
import codecs
import errno
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from services.worker_commands import TcpClientCommands as Commands
from services.workers.base_worker import BaseWorker


# ------------------------------------------------------------------ Models

@dataclass
class TcpClientConfig:
	client_id: str
	host: str
	port: int
	mode: str = "line"
	delimiter: bytes = b"\n"
	encoding: str = "utf-8"
	auto_reconnect: bool = True
	reconnect_min_s: float = 1.0
	reconnect_max_s: float = 10.0
	keepalive: bool = True
	tcp_nodelay: bool = True


@dataclass
class TcpClientState:
	cfg: TcpClientConfig
	sock: Optional[socket.socket] = None
	connected: bool = False
	connecting: bool = False
	rx_buf: bytearray = field(default_factory=bytearray)
	tx_buf: bytearray = field(default_factory=bytearray)
	last_error: str = ""
	next_reconnect_at: float = 0.0
	reconnect_backoff_s: float = 0.0
	bytes_rx: int = 0
	bytes_tx: int = 0
	_last_log_sig: Tuple[Any, ...] = field(default_factory=tuple)


# ------------------------------------------------------------------ Worker

class TcpClientWorker(BaseWorker):

	def run(self) -> None:
		self.start()
		log = logger.bind(worker="tcp")

		selector = selectors.DefaultSelector()
		clients: Dict[str, TcpClientState] = {}

		try:
			while not self.should_stop():
				self._execute_cmds(log, selector, clients)
				self._poll_sockets(log, selector, clients)
				self._handle_reconnects(log, selector, clients)
				self.set_connected(any(st.connected for st in clients.values()))
				time.sleep(0.02)
		finally:
			for cid in list(clients.keys()):
				self._disconnect_client(log, selector, clients, cid, "shutdown")
			selector.close()
			self.mark_stopped()

	# ------------------------------------------------------------------ Commands

	def _execute_cmds(self, log, selector, clients):
		for _ in range(50):
			try:
				cmd, payload = self.commands.get_nowait()
			except queue.Empty:
				return

			if cmd in ("__stop__", Commands.STOP):
				return

			if cmd == Commands.ADD_CLIENT:
				cfg = _parse_add_client_payload(payload)
				clients[cfg.client_id] = TcpClientState(cfg)
				if payload.get("connect"):
					self._connect_client(log, selector, clients, cfg.client_id)

			elif cmd == Commands.CONNECT:
				self._connect_client(log, selector, clients, payload.get("client_id"))

			elif cmd == Commands.DISCONNECT:
				self._disconnect_client(log, selector, clients, payload.get("client_id"), "cmd")

			elif cmd == Commands.SEND:
				self._queue_send(log, selector, clients, payload.get("client_id"), payload.get("data"))

	# ------------------------------------------------------------------ Connect

	def _connect_client(self, log, selector, clients, client_id):
		st = clients.get(client_id)
		if not st or st.connected or st.connecting:
			return

		try:
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.setblocking(False)
			rc = sock.connect_ex((st.cfg.host, st.cfg.port))

			st.sock = sock
			st.connecting = rc != 0

			_try_register(selector, sock, selectors.EVENT_WRITE, client_id)

		except Exception as e:
			self.current_source_id = client_id
			self.publish_error(None, "connect", str(e))
			self._schedule_reconnect(st)

	# ------------------------------------------------------------------ Disconnect

	def _disconnect_client(self, log, selector, clients, client_id, reason):
		st = clients.get(client_id)
		if not st:
			return

		if st.sock:
			try:
				selector.unregister(st.sock)
				st.sock.close()
			except Exception:
				pass

		was_connected = st.connected
		st.sock = None
		st.connected = False
		st.connecting = False

		if was_connected:
			self.current_source_id = client_id
			self.publish_disconnected(reason)

		self._schedule_reconnect(st)

	# ------------------------------------------------------------------ Poll

	def _poll_sockets(self, log, selector, clients):
		if not selector.get_map():
			return
		for key, mask in selector.select():
			cid = key.data
			st = clients.get(cid)
			if not st or not st.sock:
				continue

			# finish connect
			if st.connecting:
				err = st.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
				if err == 0:
					st.connecting = False
					st.connected = True
					self.current_source_id = cid
					self.publish_connected()
				else:
					self.current_source_id = cid
					self.publish_error(None, "connect_failed", str(err))
					self._disconnect_client(log, selector, clients, cid, "connect_failed")
				continue

			# RX
			if mask & selectors.EVENT_READ and st.connected:
				try:
					data = st.sock.recv(4096)
					if not data:
						self._disconnect_client(log, selector, clients, cid, "remote_closed")
						continue

					self.current_source_id = cid
					self.publish_value("message", data)

				except Exception as e:
					self.current_source_id = cid
					self.publish_error(None, "rx_error", str(e))
					self._disconnect_client(log, selector, clients, cid, "rx_error")

			# TX
			if mask & selectors.EVENT_WRITE and st.tx_buf:
				try:
					sent = st.sock.send(st.tx_buf)
					del st.tx_buf[:sent]
				except Exception as e:
					self.current_source_id = cid
					self.publish_error(None, "tx_error", str(e))
					self._disconnect_client(log, selector, clients, cid, "tx_error")

	# ------------------------------------------------------------------ Send

	def _queue_send(self, log, selector, clients, client_id, data):
		st = clients.get(client_id)
		if not st or not st.connected:
			return

		out = data.encode(st.cfg.encoding) if isinstance(data, str) else bytes(data)
		st.tx_buf.extend(out)

		self.current_source_id = client_id
		self.publish_write_finished("send")

	# ------------------------------------------------------------------ Reconnect

	def _handle_reconnects(self, log, selector, clients):
		now = time.time()
		for cid, st in clients.items():
			if st.connected or st.connecting or not st.next_reconnect_at:
				continue
			if now >= st.next_reconnect_at:
				self._connect_client(log, selector, clients, cid)

	def _schedule_reconnect(self, st):
		st.next_reconnect_at = time.time() + st.cfg.reconnect_min_s


# ------------------------------------------------------------------ Helpers

def _parse_add_client_payload(p):
	delimiter = p.get("delimiter", b"\n")
	if isinstance(delimiter, str):
		delimiter = codecs.decode(delimiter, "unicode_escape").encode("utf-8")

	return TcpClientConfig(
		client_id=p.get("client_id", ""),
		host=p.get("host", ""),
		port=int(p.get("port", 0)),
		mode=p.get("mode", "line"),
		delimiter=delimiter,
		encoding=p.get("encoding", "utf-8"),
		auto_reconnect=bool(p.get("auto_reconnect", True)),
		reconnect_min_s=float(p.get("reconnect_min_s", 1.0)),
		reconnect_max_s=float(p.get("reconnect_max_s", 10.0)),
		keepalive=bool(p.get("keepalive", True)),
		tcp_nodelay=bool(p.get("tcp_nodelay", True)),
	)


def _try_register(selector, sock, events, client_id):
	try:
		selector.register(sock, events, client_id)
	except KeyError:
		selector.modify(sock, events, client_id)
	except Exception:
		pass
