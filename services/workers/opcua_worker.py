from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from loguru import logger

from services.worker_commands import OpcUaCommands as Commands
from services.workers.base_worker import BaseWorker

try:
	# opcua-asyncio package (import name: asyncua)
	# Use sync wrapper to fit current threaded worker design.
	from asyncua.sync import Client as OpcUaClient  # type: ignore
except Exception:
	OpcUaClient = None  # type: ignore



@dataclass
class OpcUaEndpointConfig:
	name: str
	server_url: str
	security_policy: str = "None"
	security_mode: str = "None"
	username: str = ""
	password: str = ""
	timeout_s: float = 5.0
	auto_connect: bool = False
	nodes: list[dict[str, Any]] = field(default_factory=list)  # [{"node_id": "...", "alias": "CurrentIp", "poll_ms": 500}]


@dataclass
class OpcUaEndpointState:
	cfg: OpcUaEndpointConfig
	client: Any = None
	connected: bool = False
	last_error: str = ""
	next_poll_at: Dict[str, float] = field(default_factory=dict)

	def __post_init__(self) -> None:
		if self.cfg.nodes is None:
			self.cfg.nodes = []


class OpcUaWorker(BaseWorker):

	def run(self) -> None:
		self.start()
		log = logger.bind(worker="opcua")
		log.info("OpcUaWorker started")

		endpoints: Dict[str, OpcUaEndpointState] = {}

		try:
			while not self.should_stop():
				self._execute_cmds(log, endpoints)
				self._poll_nodes(log, endpoints)
				self.set_connected(any(st.connected for st in endpoints.values()))
				time.sleep(0.02)
		finally:
			log.info("OpcUaWorker stopping")
			for name in list(endpoints.keys()):
				self._disconnect_endpoint(log, endpoints, name, reason="shutdown")
			self.close_subscriptions()
			self.mark_stopped()
			log.info("OpcUaWorker stopped")

	def _execute_cmds(self, log, endpoints: Dict[str, OpcUaEndpointState]) -> None:
		for _ in range(50):
			try:
				cmd, payload = self.commands.get_nowait()
			except queue.Empty:
				return

			if cmd in ("__stop__", Commands.STOP):
				log.info("received stop command")
				return

			if cmd == Commands.ADD_ENDPOINT:
				cfg = _parse_add_endpoint_payload(payload)
				if not cfg.name or not cfg.server_url:
					self.publish_error_as("opcua", key="", action="add_endpoint", error="invalid endpoint config")
					log.warning(f"ADD_ENDPOINT ignored: invalid payload={payload!r}")
					continue

				if cfg.name in endpoints:
					self._disconnect_endpoint(log, endpoints, cfg.name, reason="replace")

				endpoints[cfg.name] = OpcUaEndpointState(cfg=cfg)
				self.publish_value_as("opcua", "endpoints", _endpoint_listing(endpoints))
				log.info(f"endpoint added: name={cfg.name} url={cfg.server_url}")

				if cfg.auto_connect:
					self._connect_endpoint(log, endpoints, cfg.name)

			elif cmd == Commands.REMOVE_ENDPOINT:
				name = str(payload.get("name") or "").strip()
				if not name:
					continue
				self._disconnect_endpoint(log, endpoints, name, reason="remove")
				endpoints.pop(name, None)
				self.publish_value_as("opcua", "endpoints", _endpoint_listing(endpoints))
				log.info(f"endpoint removed: name={name}")

			elif cmd == Commands.CONNECT:
				name = str(payload.get("name") or "").strip()
				self._connect_endpoint(log, endpoints, name)

			elif cmd == Commands.DISCONNECT:
				name = str(payload.get("name") or "").strip()
				self._disconnect_endpoint(log, endpoints, name, reason="cmd")

			elif cmd == Commands.READ:
				self._read_node(log, endpoints, payload)

			elif cmd == Commands.WRITE:
				self._write_node(log, endpoints, payload)

	def _connect_endpoint(self, log, endpoints: Dict[str, OpcUaEndpointState], name: str) -> None:
		if not name:
			return
		st = endpoints.get(name)
		if not st:
			return
		if st.connected:
			return

		if OpcUaClient is None:
			err = "opcua-asyncio package is not installed (pip install asyncua)"
			st.last_error = err
			self.publish_error_as(name, key=name, action="connect", error=err)
			log.error(f"connect failed: endpoint={name} err={err}")
			return

		try:
			client = _create_opcua_client(st.cfg.server_url, float(st.cfg.timeout_s))
			_set_client_auth(client, st.cfg.username, st.cfg.password)
			client.connect()
			st.client = client
			st.connected = True
			st.last_error = ""
			self.publish_connected_as(name)
			self.publish_value_as(name, f"opcua.{name}.connected", True)
			log.info(f"connected: endpoint={name} url={st.cfg.server_url}")
		except Exception as ex:
			st.connected = False
			st.client = None
			st.last_error = str(ex)
			self.publish_error_as(name, key=name, action="connect", error=st.last_error)
			log.exception(f"connect failed: endpoint={name} err={ex!r}")

	def _disconnect_endpoint(self, log, endpoints: Dict[str, OpcUaEndpointState], name: str, reason: str) -> None:
		if not name:
			return
		st = endpoints.get(name)
		if not st:
			return

		was_connected = st.connected
		if st.client is not None:
			try:
				st.client.disconnect()
			except Exception:
				pass
		st.client = None
		st.connected = False

		if was_connected:
			self.publish_disconnected_as(name, reason=reason)
			self.publish_value_as(name, f"opcua.{name}.connected", False)
			log.info(f"disconnected: endpoint={name} reason={reason}")

	def _read_node(self, log, endpoints: Dict[str, OpcUaEndpointState], payload: Dict[str, Any]) -> None:
		name = str(payload.get("name") or "").strip()
		node_id = _resolve_node_id(payload, endpoints.get(name))
		request_id = str(payload.get("request_id") or "")
		if not name or not node_id:
			return
		st = endpoints.get(name)
		if not st or not st.connected or st.client is None:
			self.publish_error_as(name or "opcua", key=node_id, action="read", error="endpoint not connected")
			return
		try:
			node = st.client.get_node(node_id)
			value = node.get_value()
			alias = _resolve_alias(node_id, st)
			base_key = alias or node_id
			key = f"opcua.{name}.read.{request_id}" if request_id else base_key
			self.publish_value_as(name, key, {"node_id": node_id, "value": value, "ts": time.time()})
		except Exception as ex:
			self.publish_error_as(name, key=node_id, action="read", error=str(ex))
			log.error(f"read failed: endpoint={name} node={node_id} err={ex!r}")

	def _write_node(self, log, endpoints: Dict[str, OpcUaEndpointState], payload: Dict[str, Any]) -> None:
		name = str(payload.get("name") or "").strip()
		node_id = _resolve_node_id(payload, endpoints.get(name))
		value = payload.get("value")
		if not name or not node_id:
			return
		st = endpoints.get(name)
		if not st or not st.connected or st.client is None:
			self.publish_error_as(name or "opcua", key=node_id, action="write", error="endpoint not connected")
			return
		try:
			node = st.client.get_node(node_id)
			node.set_value(value)
			self.publish_write_finished_as(name, key=node_id)
		except Exception as ex:
			self.publish_write_error_as(name, key=node_id, error=str(ex))
			log.error(f"write failed: endpoint={name} node={node_id} err={ex!r}")

	def _poll_nodes(self, log, endpoints: Dict[str, OpcUaEndpointState]) -> None:
		now = time.time()
		for endpoint_name, st in endpoints.items():
			if not st.connected or st.client is None:
				continue
			for nd in st.cfg.nodes or []:
				try:
					node_id = str(nd.get("node_id") or "").strip()
					if not node_id:
						continue
					alias = str(nd.get("alias") or "").strip() or node_id
					poll_ms = int(nd.get("poll_ms", 500) or 500)
					next_ts = st.next_poll_at.get(node_id, 0.0)
					if now < next_ts:
						continue
					st.next_poll_at[node_id] = now + max(0.05, poll_ms / 1000.0)

					value = st.client.get_node(node_id).get_value()
					self.publish_value_as(endpoint_name, alias, value)
				except Exception as ex:
					self.publish_error_as(endpoint_name, key=str(nd.get("alias") or nd.get("node_id") or ""), action="poll", error=str(ex))
					log.debug(f"opcua poll failed: endpoint={endpoint_name} node={nd!r} err={ex!r}")


def _parse_add_endpoint_payload(payload: Dict[str, Any]) -> OpcUaEndpointConfig:
	return OpcUaEndpointConfig(
		name=str(payload.get("name") or "").strip(),
		server_url=str(payload.get("server_url") or "").strip(),
		security_policy=str(payload.get("security_policy") or "None"),
		security_mode=str(payload.get("security_mode") or "None"),
		username=str(payload.get("username") or ""),
		password=str(payload.get("password") or ""),
		timeout_s=float(payload.get("timeout_s", 5.0)),
		auto_connect=bool(payload.get("auto_connect", False)),
		nodes=payload.get("nodes", []) if isinstance(payload.get("nodes", []), list) else [],
	)


def _endpoint_listing(endpoints: Dict[str, OpcUaEndpointState]) -> list[dict[str, Any]]:
	out: list[dict[str, Any]] = []
	for st in endpoints.values():
		out.append(
			{
				"name": st.cfg.name,
				"server_url": st.cfg.server_url,
				"connected": st.connected,
				"last_error": st.last_error,
				"nodes": st.cfg.nodes or [],
			}
		)
	return out


def _resolve_node_id(payload: Dict[str, Any], st: Optional[OpcUaEndpointState]) -> str:
	node_id = str(payload.get("node_id") or "").strip()
	if node_id:
		return node_id
	alias = str(payload.get("alias") or payload.get("name_or_alias") or "").strip()
	if not alias or st is None:
		return ""
	for nd in st.cfg.nodes or []:
		if str(nd.get("alias") or "").strip() == alias:
			return str(nd.get("node_id") or "").strip()
	return ""


def _resolve_alias(node_id: str, st: Optional[OpcUaEndpointState]) -> str:
	if st is None:
		return ""
	for nd in st.cfg.nodes or []:
		if str(nd.get("node_id") or "").strip() == node_id:
			return str(nd.get("alias") or "").strip()
	return ""


def _create_opcua_client(url: str, timeout_s: float) -> Any:
	"""
	Construct an asyncua sync Client with best-effort compatibility across versions.
	"""
	# Preferred ctor in most asyncua versions.
	try:
		return OpcUaClient(url, timeout=timeout_s)
	except TypeError:
		pass

	# Some wrappers only accept positional args.
	try:
		return OpcUaClient(url, timeout_s)
	except TypeError:
		pass

	# Minimal ctor fallback.
	client = OpcUaClient(url)
	try:
		if hasattr(client, "timeout"):
			client.timeout = timeout_s
	except Exception:
		pass
	return client


def _set_client_auth(client: Any, username: str, password: str) -> None:
	user = (username or "").strip()
	pwd = password or ""

	if not user and not pwd:
		return

	# asyncua sync client usually supports set_user / set_password
	if user and hasattr(client, "set_user"):
		try:
			client.set_user(user)
		except Exception:
			pass
	if pwd and hasattr(client, "set_password"):
		try:
			client.set_password(pwd)
		except Exception:
			pass

	# Compatibility aliases on some versions/wrappers.
	if user and hasattr(client, "set_username"):
		try:
			client.set_username(user)
		except Exception:
			pass
