# services/workers/tcp_client_worker.py
from __future__ import annotations

import time
import socket
import selectors
import queue
import codecs
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
		log.info("TcpClientWorker started")

		selector = selectors.DefaultSelector()
		clients: Dict[str, TcpClientState] = {}

		last_status_log_ts = 0.0

		try:
			while not self.should_stop():
				self._execute_cmds(log, selector, clients)
				self._poll_sockets(log, selector, clients)
				self._handle_reconnects(log, selector, clients)

				any_connected = any(st.connected for st in clients.values())
				self.set_connected(any_connected)

				now = time.time()
				if now - last_status_log_ts >= 5.0:
					last_status_log_ts = now
					total = len(clients)
					connected = sum(1 for st in clients.values() if st.connected)
					connecting = sum(1 for st in clients.values() if st.connecting)
					log.debug(f"status: clients={total} connected={connected} connecting={connecting}")

				time.sleep(0.02)
		finally:
			log.info("TcpClientWorker stopping")
			for cid in list(clients.keys()):
				self._disconnect_client(log, selector, clients, cid, "shutdown")
			selector.close()
			self.close_subscriptions()
			self.mark_stopped()
			log.info("TcpClientWorker stopped")

	# ------------------------------------------------------------------ Commands

	def _execute_cmds(self, log, selector, clients):
		for _ in range(50):
			try:
				cmd, payload = self.commands.get_nowait()
			except queue.Empty:
				return

			if cmd in ("__stop__", Commands.STOP):
				log.info("received stop command")
				return

			if cmd == Commands.ADD_CLIENT:
				cfg = _parse_add_client_payload(payload)
				if not cfg.client_id:
					log.warning(f"ADD_CLIENT ignored: missing client_id payload={payload!r}")
					continue

				clients[cfg.client_id] = TcpClientState(cfg)
				log.info(f"client added: client_id={cfg.client_id} host={cfg.host}:{cfg.port} mode={cfg.mode}")

				if payload.get("connect"):
					log.info(f"client connect requested on add: client_id={cfg.client_id}")
					self._connect_client(log, selector, clients, cfg.client_id)

			elif cmd == Commands.CONNECT:
				cid = payload.get("client_id")
				log.info(f"CONNECT requested: client_id={cid}")
				self._connect_client(log, selector, clients, cid)

			elif cmd == Commands.DISCONNECT:
				cid = payload.get("client_id")
				log.info(f"DISCONNECT requested: client_id={cid}")
				self._disconnect_client(log, selector, clients, cid, "cmd")

			elif cmd == Commands.SEND:
				cid = payload.get("client_id")
				data = payload.get("data")
				size = 0
				try:
					if isinstance(data, str):
						size = len(data.encode("utf-8"))
					elif data is not None:
						size = len(bytes(data))
				except Exception:
					size = 0
				log.debug(f"SEND requested: client_id={cid} bytes~={size}")
				self._queue_send(log, selector, clients, cid, data)

			elif cmd == Commands.RESET:
				cid = payload.get("client_id")
				log.info(f"RESET requested: client_id={cid}")
				self._reset_client(log, selector, clients, cid)

			else:
				log.debug(f"unknown command ignored: cmd={cmd} payload={payload!r}")

	# ------------------------------------------------------------------ Connect

	def _connect_client(self, log, selector, clients, client_id):
		if not client_id:
			log.warning("connect ignored: missing client_id")
			return

		st = clients.get(client_id)
		if not st:
			log.warning(f"connect ignored: unknown client_id={client_id}")
			return
		if st.connected:
			log.debug(f"connect ignored: already connected client_id={client_id}")
			return
		if st.connecting:
			log.debug(f"connect ignored: already connecting client_id={client_id}")
			return

		try:
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.setblocking(False)

			try:
				if st.cfg.keepalive:
					sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
			except Exception as e:
				log.debug(f"keepalive set failed: client_id={client_id} err={e!r}")

			try:
				if st.cfg.tcp_nodelay:
					sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
			except Exception as e:
				log.debug(f"tcp_nodelay set failed: client_id={client_id} err={e!r}")

			rc = sock.connect_ex((st.cfg.host, st.cfg.port))

			st.sock = sock
			st.connecting = rc != 0

			_try_register(selector, sock, selectors.EVENT_WRITE, client_id)

			if rc == 0:
				st.connecting = False
				st.connected = True
				self.publish_connected_as(client_id)
				log.info(f"connected immediately: client_id={client_id} host={st.cfg.host}:{st.cfg.port}")
			else:
				log.info(f"connecting: client_id={client_id} host={st.cfg.host}:{st.cfg.port} rc={rc}")

		except Exception as e:
			self.publish_error_as(client_id, None, "connect", str(e))
			log.error(f"connect failed: client_id={client_id} host={st.cfg.host}:{st.cfg.port} err={e!r}")
			self._schedule_reconnect(log, st, client_id, reason="connect_exception")

	# ------------------------------------------------------------------ Disconnect

	def _disconnect_client(self, log, selector, clients, client_id, reason):
		if not client_id:
			return

		st = clients.get(client_id)
		if not st:
			return

		if st.sock:
			try:
				try:
					selector.unregister(st.sock)
				except Exception:
					pass
				try:
					st.sock.close()
				except Exception:
					pass
			except Exception:
				pass

		was_connected = st.connected
		st.sock = None
		st.connected = False
		st.connecting = False

		if was_connected:
			self.publish_disconnected_as(client_id, reason)
			log.info(f"disconnected: client_id={client_id} reason={reason} bytes_rx={st.bytes_rx} bytes_tx={st.bytes_tx}")
		else:
			log.debug(f"disconnect: client_id={client_id} reason={reason} (was not connected)")

		self._schedule_reconnect(log, st, client_id, reason=f"disconnect_{reason}")

	def _reset_client(self, log, selector, clients, client_id):
		if not client_id:
			log.warning("reset ignored: missing client_id")
			return
		st = clients.get(client_id)
		if not st:
			log.warning(f"reset ignored: unknown client_id={client_id}")
			return
		self._disconnect_client(log, selector, clients, client_id, "reset")
		st.rx_buf = bytearray()
		st.tx_buf = bytearray()
		st.bytes_rx = 0
		st.bytes_tx = 0
		st.last_error = ""
		st.reconnect_backoff_s = 0.0
		st.next_reconnect_at = 0.0
		self._connect_client(log, selector, clients, client_id)

	# ------------------------------------------------------------------ Poll

	def _poll_sockets(self, log, selector, clients):
		if not selector.get_map():
			return

		for key, mask in selector.select():
			cid = key.data
			st = clients.get(cid)
			if not st or not st.sock:
				continue

			if st.connecting:
				try:
					err = st.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
				except Exception as e:
					self.publish_error_as(cid, None, "connect_failed", str(e))
					log.error(f"connect check failed: client_id={cid} err={e!r}")
					self._disconnect_client(log, selector, clients, cid, "connect_failed")
					continue

				if err == 0:
					st.connecting = False
					st.connected = True
					self.publish_connected_as(cid)
					log.info(f"connected: client_id={cid} host={st.cfg.host}:{st.cfg.port}")
					_try_register(selector, st.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, cid)
				else:
					self.publish_error_as(cid, None, "connect_failed", str(err))
					log.error(f"connect failed: client_id={cid} host={st.cfg.host}:{st.cfg.port} so_error={err}")
					self._disconnect_client(log, selector, clients, cid, "connect_failed")
				continue

			if mask & selectors.EVENT_READ and st.connected:
				try:
					data = st.sock.recv(4096)
					if not data:
						log.warning(f"remote closed: client_id={cid}")
						self._disconnect_client(log, selector, clients, cid, "remote_closed")
						continue

					st.bytes_rx += len(data)

					self.publish_value_as(cid, "message", data)
					log.debug(f"rx: client_id={cid} bytes={len(data)} total_rx={st.bytes_rx}")

				except Exception as e:
					self.publish_error_as(cid, None, "rx_error", str(e))
					log.error(f"rx error: client_id={cid} err={e!r}")
					self._disconnect_client(log, selector, clients, cid, "rx_error")

			if (mask & selectors.EVENT_WRITE) and st.connected and st.tx_buf:
				try:
					sent = st.sock.send(st.tx_buf)
					if sent > 0:
						st.bytes_tx += sent
						del st.tx_buf[:sent]
						log.debug(f"tx: client_id={cid} bytes={sent} pending={len(st.tx_buf)} total_tx={st.bytes_tx}")
				except Exception as e:
					self.publish_error_as(cid, None, "tx_error", str(e))
					log.error(f"tx error: client_id={cid} err={e!r}")
					self._disconnect_client(log, selector, clients, cid, "tx_error")

	# ------------------------------------------------------------------ Send

	def _queue_send(self, log, selector, clients, client_id, data):
		if not client_id:
			log.warning("send ignored: missing client_id")
			return

		st = clients.get(client_id)
		if not st:
			log.warning(f"send ignored: unknown client_id={client_id}")
			return
		if not st.connected:
			log.warning(f"send ignored: not connected client_id={client_id}")
			return

		try:
			out = data.encode(st.cfg.encoding) if isinstance(data, str) else bytes(data)
		except Exception as e:
			self.publish_error_as(client_id, None, "send_encode_error", str(e))
			log.error(f"send encode failed: client_id={client_id} err={e!r} data_type={type(data)}")
			return

		st.tx_buf.extend(out)

		if st.sock:
			_try_register(selector, st.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, client_id)

		self.publish_write_finished_as(client_id, "send")
		log.debug(f"queued send: client_id={client_id} bytes={len(out)} pending={len(st.tx_buf)}")

	# ------------------------------------------------------------------ Reconnect

	def _handle_reconnects(self, log, selector, clients):
		now = time.time()
		for cid, st in clients.items():
			if st.connected or st.connecting or not st.next_reconnect_at:
				continue
			if not st.cfg.auto_reconnect:
				continue
			if now >= st.next_reconnect_at:
				log.info(f"reconnect due: client_id={cid}")
				self._connect_client(log, selector, clients, cid)

	def _schedule_reconnect(self, log, st, client_id, reason):
		if not st.cfg.auto_reconnect:
			st.next_reconnect_at = 0.0
			log.debug(f"reconnect disabled: client_id={client_id} reason={reason}")
			return

		delay_s = float(st.cfg.reconnect_min_s or 1.0)
		st.next_reconnect_at = time.time() + delay_s

		sig = (client_id, "reconnect", int(delay_s), int(st.next_reconnect_at))
		if st._last_log_sig != sig:
			st._last_log_sig = sig
			log.info(f"scheduled reconnect: client_id={client_id} in_s={delay_s} reason={reason}")


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
		try:
			selector.modify(sock, events, client_id)
		except Exception:
			pass
	except Exception:
		pass
