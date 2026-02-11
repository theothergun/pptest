# services/workers/itac_worker.py
from __future__ import annotations

import time
import uuid
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, Future

import requests
from loguru import logger

from services.worker_commands import ItacCommands as Commands
from services.workers.base_worker import BaseWorker


# ------------------------------------------------------------------ Models

@dataclass
class ItacConnectionConfig:
	connection_id: str
	base_url: str  # e.g. http://<host>:<port>/mes/imsapi/rest/actions
	station_number: str

	# regLogin extras (defaults can be empty, but client/registrationType often required)
	client: str = "01"
	registration_type: str = "S"  # S=Station, T=Token, U=User
	system_identifier: str = "nicegui"

	station_password: str = ""
	user: str = ""
	password: str = ""

	timeout_s: float = 10.0
	verify_ssl: bool = True
	auto_login: bool = True

	# optional: override locale after login (if you want)
	force_locale: str = ""


@dataclass
class ItacSessionContext:
	session_id: str = ""
	pers_id: int = 0
	locale: str = ""


@dataclass
class ItacConnectionState:
	cfg: ItacConnectionConfig
	session: ItacSessionContext = field(default_factory=ItacSessionContext)
	connected: bool = False
	last_error: str = ""


# ------------------------------------------------------------------ HTTP client (thread-local session)

class _ThreadLocalHttp:
	def __init__(self) -> None:
		self._local = threading.local()

	def session(self) -> requests.Session:
		sess = getattr(self._local, "session", None)
		if sess is None:
			sess = requests.Session()
			setattr(self._local, "session", sess)
		return sess


# ------------------------------------------------------------------ Worker

class ItacWorker(BaseWorker):

	def run(self) -> None:
		self.start()
		log = logger.bind(worker="itac")
		log.info("ItacWorker started")

		http = _ThreadLocalHttp()
		connections: Dict[str, ItacConnectionState] = {}
		exec_ = ThreadPoolExecutor(max_workers=8, thread_name_prefix="itac")
		pending: Dict[Future, Tuple[str, str, str]] = {}
		# future -> (connection_id, action, publish_key)

		try:
			while not self.should_stop():
				self._execute_cmds(log, http, connections, exec_, pending)
				self._poll_futures(log, connections, pending)

				self.set_connected(any(st.connected for st in connections.values()))
				time.sleep(0.02)

		finally:
			log.info("ItacWorker stopping")
			try:
				exec_.shutdown(wait=False, cancel_futures=True)
			except Exception:
				pass
			self.close_subscriptions()
			self.mark_stopped()
			log.info("ItacWorker stopped")

	# ------------------------------------------------------------------ Commands

	def _execute_cmds(
		self,
		log,
		http: _ThreadLocalHttp,
		connections: Dict[str, ItacConnectionState],
		exec_: ThreadPoolExecutor,
		pending: Dict[Future, Tuple[str, str, str]],
	) -> None:
		for _ in range(50):
			try:
				cmd, payload = self.commands.get_nowait()
			except queue.Empty:
				return

			if cmd in ("__stop__", Commands.STOP):
				log.info("received stop command")
				return

			if cmd == Commands.ADD_CONNECTION:
				cfg = _parse_add_connection_payload(payload)
				if not cfg.connection_id:
					log.warning("ADD_CONNECTION ignored: missing connection_id")
					continue
				if not cfg.base_url or not cfg.station_number:
					log.warning("ADD_CONNECTION ignored: missing base_url or station_number")
					continue

				connections[cfg.connection_id] = ItacConnectionState(cfg=cfg)
				log.info("connection added: id=%s base_url=%s station=%s" % (cfg.connection_id, cfg.base_url, cfg.station_number))

				if cfg.auto_login:
					self._schedule_login(log, http, connections, exec_, pending, cfg.connection_id)

			elif cmd == Commands.REMOVE_CONNECTION:
				cid = str(payload.get("connection_id") or "")
				if cid in connections:
					del connections[cid]
					log.info("connection removed: id=%s" % cid)

			elif cmd == Commands.LOGIN:
				cid = str(payload.get("connection_id") or "")
				self._schedule_login(log, http, connections, exec_, pending, cid)

			elif cmd == Commands.LOGOUT:
				cid = str(payload.get("connection_id") or "")
				self._schedule_logout(log, http, connections, exec_, pending, cid)

			elif cmd == Commands.CALL_CUSTOM_FUNCTION:
				cid = str(payload.get("connection_id") or "")
				method_name = payload.get("method_name")
				in_args = payload.get("in_args", [])
				request_id = str(payload.get("request_id") or uuid.uuid4())
				self._schedule_custom_function(log, http, connections, exec_, pending, cid, method_name, in_args, request_id)

			elif cmd == Commands.GET_STATION_SETTING:
				cid = str(payload.get("connection_id") or "")
				keys = payload.get("station_setting_keys", [])
				request_id = str(payload.get("request_id") or uuid.uuid4())
				self._schedule_tr_get_station_setting(log, http, connections, exec_, pending, cid, keys, request_id)

			elif cmd == Commands.RAW_CALL:
				cid = str(payload.get("connection_id") or "")
				function_name = payload.get("function_name")
				body = payload.get("body", {})
				request_id = str(payload.get("request_id") or uuid.uuid4())
				self._schedule_raw_call(log, http, connections, exec_, pending, cid, function_name, body, request_id)

			else:
				log.debug("unknown command ignored: cmd=%s payload=%r" % (cmd, payload))

	# ------------------------------------------------------------------ Scheduling (async)

	def _schedule_login(self, log, http, connections, exec_, pending, connection_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning("LOGIN ignored: unknown connection_id=%s" % connection_id)
			return

		def job() -> dict:
			return _reg_login(http, st.cfg)

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "login", "itac.%s.session" % connection_id)

	def _schedule_logout(self, log, http, connections, exec_, pending, connection_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning("LOGOUT ignored: unknown connection_id=%s" % connection_id)
			return

		def job() -> dict:
			return _reg_logout(http, st.cfg, st.session)

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "logout", "itac.%s.logout" % connection_id)

	def _schedule_custom_function(self, log, http, connections, exec_, pending, connection_id: str, method_name: Any, in_args: Any, request_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning("CALL_CUSTOM_FUNCTION ignored: unknown connection_id=%s" % connection_id)
			return

		def job() -> dict:
			_ensure_session(http, st)
			return _custom_function(http, st.cfg, st.session, method_name, in_args)

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "custom_function", "itac.%s.custom_function.%s" % (connection_id, request_id))

	def _schedule_tr_get_station_setting(self, log, http, connections, exec_, pending, connection_id: str, keys: Any, request_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning("GET_STATION_SETTING ignored: unknown connection_id=%s" % connection_id)
			return

		def job() -> dict:
			_ensure_session(http, st)
			return _tr_get_station_setting(http, st.cfg, st.session, keys)

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "tr_get_station_setting", "itac.%s.station_setting.%s" % (connection_id, request_id))

	def _schedule_raw_call(self, log, http, connections, exec_, pending, connection_id: str, function_name: Any, body: Any, request_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning("RAW_CALL ignored: unknown connection_id=%s" % connection_id)
			return

		def job() -> dict:
			_ensure_session(http, st)
			return _post_action(http, st.cfg, str(function_name or ""), body)

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "raw_call", "itac.%s.raw.%s" % (connection_id, request_id))

	# ------------------------------------------------------------------ Future polling

	def _poll_futures(self, log, connections: Dict[str, ItacConnectionState], pending: Dict[Future, Tuple[str, str, str]]) -> None:
		done: list[Future] = []
		for fut, meta in pending.items():
			if not fut.done():
				continue
			done.append(fut)

			connection_id, action, publish_key = meta
			st = connections.get(connection_id)

			try:
				res = fut.result()
				if st and action == "login":
					_update_session_from_login_response(st, res)
					st.connected = True
					st.last_error = ""
					self.publish_connected_as(connection_id)
					self.publish_value_as(connection_id, publish_key, res)

				elif st and action == "logout":
					st.connected = False
					st.session = ItacSessionContext()
					self.publish_disconnected_as(connection_id, reason="logout")
					self.publish_value_as(connection_id, publish_key, res)

				else:
					self.publish_value_as(connection_id, publish_key, res)

			except Exception as ex:
				err = str(ex)
				if st:
					st.last_error = err
					if action == "login":
						st.connected = False
						self.publish_disconnected_as(connection_id, reason=err)
				self.publish_error_as(connection_id, key=connection_id, action=action, error=err)
				log.error("request failed: id=%s action=%s err=%r" % (connection_id, action, ex))

		for fut in done:
			try:
				del pending[fut]
			except Exception:
				pass


# ------------------------------------------------------------------ Payload parsing

def _parse_add_connection_payload(payload: dict) -> ItacConnectionConfig:
	return ItacConnectionConfig(
		connection_id=str(payload.get("connection_id") or payload.get("name") or ""),
		base_url=str(payload.get("base_url") or ""),
		station_number=str(payload.get("station_number") or ""),
		client=str(payload.get("client") or "01"),
		registration_type=str(payload.get("registration_type") or "S"),
		system_identifier=str(payload.get("system_identifier") or "nicegui"),
		station_password=str(payload.get("station_password") or ""),
		user=str(payload.get("user") or ""),
		password=str(payload.get("password") or ""),
		timeout_s=float(payload.get("timeout_s") or 10.0),
		verify_ssl=bool(payload.get("verify_ssl", True)),
		auto_login=bool(payload.get("auto_login", True)),
		force_locale=str(payload.get("force_locale") or ""),
	)


# ------------------------------------------------------------------ IMSApi REST calls

def _actions_url(cfg: ItacConnectionConfig, function_name: str) -> str:
	base = (cfg.base_url or "").rstrip("/")
	return "%s/%s" % (base, function_name.lstrip("/"))


def _post_action(http: _ThreadLocalHttp, cfg: ItacConnectionConfig, function_name: str, body: Any) -> dict:
	if not function_name:
		raise ValueError("missing function_name")

	url = _actions_url(cfg, function_name)
	sess = http.session()

	resp = sess.post(
		url,
		json=body if isinstance(body, dict) else {},
		timeout=cfg.timeout_s,
		verify=cfg.verify_ssl,
		headers={"Content-Type": "application/json"},
	)
	resp.raise_for_status()

	try:
		data = resp.json()
	except Exception:
		data = {"raw": resp.text}

	if not isinstance(data, dict):
		return {"data": data}
	return data


def _reg_login(http: _ThreadLocalHttp, cfg: ItacConnectionConfig) -> dict:
	body = {
		"sessionValidationStruct": {
			"stationNumber": cfg.station_number,
			"stationPassword": cfg.station_password,
			"user": cfg.user,
			"password": cfg.password,
			"client": cfg.client,
			"registrationType": cfg.registration_type,
			"systemIdentifier": cfg.system_identifier,
		}
	}
	return _post_action(http, cfg, "regLogin", body)


def _reg_logout(http: _ThreadLocalHttp, cfg: ItacConnectionConfig, session: ItacSessionContext) -> dict:
	body = {
		"sessionContext": {
			"sessionId": str(session.session_id),
			"persId": int(session.pers_id),
			"locale": str(session.locale),
		}
	}
	return _post_action(http, cfg, "regLogout", body)


def _custom_function(http: _ThreadLocalHttp, cfg: ItacConnectionConfig, session: ItacSessionContext, method_name: Any, in_args: Any) -> dict:
	body = {
		"sessionContext": {
			"sessionId": str(session.session_id),
			"persId": int(session.pers_id),
			"locale": str(session.locale),
		},
		"methodName": str(method_name or ""),
		"inArgs": in_args if isinstance(in_args, list) else [],
	}
	return _post_action(http, cfg, "customFunction", body)


def _tr_get_station_setting(http: _ThreadLocalHttp, cfg: ItacConnectionConfig, session: ItacSessionContext, keys: Any) -> dict:
	body = {
		"sessionContext": {
			"sessionId": str(session.session_id),
			"persId": int(session.pers_id),
			"locale": str(session.locale),
		},
		"stationNumber": cfg.station_number,
		"stationSettingResultKeys": keys if isinstance(keys, list) else [],
	}
	return _post_action(http, cfg, "trGetStationSetting", body)


def _ensure_session(http: _ThreadLocalHttp, st: ItacConnectionState) -> None:
	# If no session, login once (docs recommend only re-login when session is invalid). :contentReference[oaicite:4]{index=4}
	if st.session and st.session.session_id:
		return
	res = _reg_login(http, st.cfg)
	_update_session_from_login_response(st, res)
	st.connected = True


def _update_session_from_login_response(st: ItacConnectionState, res: dict) -> None:
	# Most likely: {"sessionContext": {"sessionId": "...", "persId": 0, "locale": "de_DE"}, ...}
	ctx = res.get("sessionContext")
	if not isinstance(ctx, dict):
		# some servers might flatten
		ctx = res.get("session_context") if isinstance(res.get("session_context"), dict) else {}

	sid = str(ctx.get("sessionId") or ctx.get("session_id") or "")
	pid_raw = ctx.get("persId") if "persId" in ctx else ctx.get("pers_id", 0)

	try:
		pid = int(pid_raw or 0)
	except Exception:
		pid = 0

	loc = str(ctx.get("locale") or "")

	if st.cfg.force_locale:
		loc = st.cfg.force_locale

	st.session = ItacSessionContext(session_id=sid, pers_id=pid, locale=loc)
