# services/workers/itac_worker.py
from __future__ import annotations

import json
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
	connected: bool = False
	last_error: str = ""


# ------------------------------------------------------------------ Shared session manager (ONE session for the whole worker)

class ItacSessionManager:
	"""
	Worker-global session storage.

	Requirement from you:
	- Once login is successful, reuse the session for all calls, regardless of connection_id.
	"""

	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._session = ItacSessionContext()
		self._login_cfg_sig = ""  # for debugging only (which cfg created the session)

	def has_session(self) -> bool:
		with self._lock:
			return bool(self._session.session_id)

	def get(self) -> ItacSessionContext:
		with self._lock:
			return ItacSessionContext(
				session_id=str(self._session.session_id or ""),
				pers_id=int(self._session.pers_id or 0),
				locale=str(self._session.locale or ""),
			)

	def set(self, sess: ItacSessionContext, cfg_sig: str) -> None:
		with self._lock:
			self._session = sess
			self._login_cfg_sig = str(cfg_sig or "")

	def clear(self, reason: str = "") -> None:
		with self._lock:
			logger.info(f"iTAC session cleared: reason={reason!r} prev_cfg_sig={self._login_cfg_sig!r}")
			self._session = ItacSessionContext()
			self._login_cfg_sig = ""

	def cfg_signature(self) -> str:
		with self._lock:
			return self._login_cfg_sig


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
		session_mgr = ItacSessionManager()

		connections: Dict[str, ItacConnectionState] = {}
		exec_ = ThreadPoolExecutor(max_workers=8, thread_name_prefix="itac")
		pending: Dict[Future, Tuple[str, str, str]] = {}
		# future -> (connection_id, action, publish_key)

		try:
			while not self.should_stop():
				self._execute_cmds(log, http, session_mgr, connections, exec_, pending)
				self._poll_futures(log, session_mgr, connections, pending)

				self.set_connected(any(st.connected for st in connections.values()))
				time.sleep(0.02)

		finally:
			log.info("ItacWorker stopping")
			try:
				exec_.shutdown(wait=False, cancel_futures=True)
			except Exception as ex:
				log.warning(f"ThreadPool shutdown failed: {ex!r}")
			self.close_subscriptions()
			self.mark_stopped()
			log.info("ItacWorker stopped")

	# ------------------------------------------------------------------ Commands

	def _execute_cmds(
		self,
		log,
		http: _ThreadLocalHttp,
		session_mgr: ItacSessionManager,
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
					log.warning(f"ADD_CONNECTION ignored: missing base_url or station_number (id={cfg.connection_id!r})")
					continue

				connections[cfg.connection_id] = ItacConnectionState(cfg=cfg)
				log.info(
					f"connection added: id={cfg.connection_id} base_url={cfg.base_url} station={cfg.station_number} "
					f"auto_login={cfg.auto_login} verify_ssl={cfg.verify_ssl} timeout_s={cfg.timeout_s}"
				)

				if cfg.auto_login:
					self._schedule_login(log, http, session_mgr, connections, exec_, pending, cfg.connection_id)

			elif cmd == Commands.REMOVE_CONNECTION:
				cid = str(payload.get("connection_id") or "")
				if cid in connections:
					del connections[cid]
					log.info(f"connection removed: id={cid}")
				else:
					log.debug(f"REMOVE_CONNECTION ignored: unknown id={cid!r}")

			elif cmd == Commands.LOGIN:
				cid = str(payload.get("connection_id") or "")
				self._schedule_login(log, http, session_mgr, connections, exec_, pending, cid)

			elif cmd == Commands.LOGOUT:
				# logout clears the shared session
				cid = str(payload.get("connection_id") or "")
				self._schedule_logout(log, http, session_mgr, connections, exec_, pending, cid)

			elif cmd == Commands.CALL_CUSTOM_FUNCTION:
				cid = str(payload.get("connection_id") or "")
				method_name = payload.get("method_name")
				in_args = payload.get("in_args", [])
				request_id = str(payload.get("request_id") or uuid.uuid4())
				log.info(f"cmd CALL_CUSTOM_FUNCTION: id={cid} request_id={request_id} method_name={method_name!r} in_args={in_args!r}")
				self._schedule_custom_function(log, http, session_mgr, connections, exec_, pending, cid, method_name, in_args, request_id)

			elif cmd == Commands.GET_STATION_SETTING:
				cid = str(payload.get("connection_id") or "")
				keys = payload.get("station_setting_keys", [])
				request_id = str(payload.get("request_id") or uuid.uuid4())
				log.info(f"cmd GET_STATION_SETTING: id={cid} request_id={request_id} keys={keys!r}")
				self._schedule_tr_get_station_setting(log, http, session_mgr, connections, exec_, pending, cid, keys, request_id)

			elif cmd == Commands.RAW_CALL:
				cid = str(payload.get("connection_id") or "")
				function_name = payload.get("function_name")
				body = payload.get("body", {})
				request_id = str(payload.get("request_id") or uuid.uuid4())
				log.info(f"cmd RAW_CALL: id={cid} request_id={request_id} function={function_name!r} body={_shorten_json(_redact_body(body), 1200)}")
				self._schedule_raw_call(log, http, session_mgr, connections, exec_, pending, cid, function_name, body, request_id)

			else:
				log.debug(f"unknown command ignored: cmd={cmd!r} payload={payload!r}")

	# ------------------------------------------------------------------ Scheduling (async)

	def _schedule_login(self, log, http, session_mgr, connections, exec_, pending, connection_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning(f"LOGIN ignored: unknown connection_id={connection_id!r}")
			return

		cfg_sig = _cfg_signature(st.cfg)
		log.info(f"schedule login: id={connection_id} cfg_sig={cfg_sig}")

		def job() -> dict:
			res = _reg_login(http, st.cfg)
			sess = _extract_session_from_login_response(st.cfg, res)
			if not sess.session_id:
				raise Exception(f"regLogin did not return a sessionId (cfg_sig={cfg_sig})")
			session_mgr.set(sess, cfg_sig)
			return res

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "login", f"itac.{connection_id}.session")

	def _schedule_logout(self, log, http, session_mgr, connections, exec_, pending, connection_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning(f"LOGOUT ignored: unknown connection_id={connection_id!r}")
			return

		log.info(f"schedule logout: id={connection_id}")

		def job() -> dict:
			sess = session_mgr.get()
			if not sess.session_id:
				logger.info("regLogout skipped: no active session")
				session_mgr.clear(reason="logout(no_session)")
				return {"ok": True, "note": "no active session"}

			res = _reg_logout(http, st.cfg, sess)
			session_mgr.clear(reason="logout")
			return res

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "logout", f"itac.{connection_id}.logout")

	def _schedule_custom_function(self, log, http, session_mgr, connections, exec_, pending, connection_id: str, method_name: Any, in_args: Any, request_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning(f"CALL_CUSTOM_FUNCTION ignored: unknown connection_id={connection_id!r}")
			return

		log.info(f"schedule custom_function: id={connection_id} request_id={request_id} method_name={method_name!r} in_args={in_args!r}")

		def job() -> dict:
			_ensure_session(http, session_mgr, st.cfg)
			res = _custom_function(http, st.cfg, session_mgr.get(), method_name, in_args)
			if _extract_return_code(res) == -3:
				logger.info("customFunction returned -3 (session invalid) -> relogin once and retry")
				session_mgr.clear(reason="session_invalid(-3)")
				_ensure_session(http, session_mgr, st.cfg)
				res = _custom_function(http, st.cfg, session_mgr.get(), method_name, in_args)
			return res

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "custom_function", f"itac.{connection_id}.custom_function.{request_id}")

	def _schedule_tr_get_station_setting(self, log, http, session_mgr, connections, exec_, pending, connection_id: str, keys: Any, request_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning(f"GET_STATION_SETTING ignored: unknown connection_id={connection_id!r}")
			return

		log.info(f"schedule station_setting: id={connection_id} request_id={request_id} keys={keys!r}")

		def job() -> dict:
			_ensure_session(http, session_mgr, st.cfg)
			res = _tr_get_station_setting(http, st.cfg, session_mgr.get(), keys)
			if _extract_return_code(res) == -3:
				logger.info("trGetStationSetting returned -3 (session invalid) -> relogin once and retry")
				session_mgr.clear(reason="session_invalid(-3)")
				_ensure_session(http, session_mgr, st.cfg)
				res = _tr_get_station_setting(http, st.cfg, session_mgr.get(), keys)
			return res

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "tr_get_station_setting", f"itac.{connection_id}.station_setting.{request_id}")

	def _schedule_raw_call(self, log, http, session_mgr, connections, exec_, pending, connection_id: str, function_name: Any, body: Any, request_id: str) -> None:
		st = connections.get(connection_id)
		if not st:
			log.warning(f"RAW_CALL ignored: unknown connection_id={connection_id!r}")
			return

		log.info(f"schedule raw_call: id={connection_id} request_id={request_id} function={function_name!r} body={_shorten_json(_redact_body(body), 1200)}")

		def job() -> dict:
			_ensure_session(http, session_mgr, st.cfg)
			res = _post_action(http, st.cfg, str(function_name or ""), body)
			if _extract_return_code(res) == -3:
				logger.info("raw_call returned -3 (session invalid) -> relogin once and retry")
				session_mgr.clear(reason="session_invalid(-3)")
				_ensure_session(http, session_mgr, st.cfg)
				res = _post_action(http, st.cfg, str(function_name or ""), body)
			return res

		fut = exec_.submit(job)
		pending[fut] = (connection_id, "raw_call", f"itac.{connection_id}.raw.{request_id}")

	# ------------------------------------------------------------------ Future polling

	def _poll_futures(self, log, session_mgr: ItacSessionManager, connections: Dict[str, ItacConnectionState], pending: Dict[Future, Tuple[str, str, str]]) -> None:
		done: list[Future] = []
		for fut, meta in list(pending.items()):
			if not fut.done():
				continue
			done.append(fut)

			connection_id, action, publish_key = meta
			st = connections.get(connection_id)

			try:
				res = fut.result()
				log.info(f"result: id={connection_id} action={action} publish_key={publish_key} response={_shorten_json(_redact_body(res), 2000)}")

				if st and action == "login":
					st.connected = session_mgr.has_session()
					st.last_error = ""
					if st.connected:
						self.publish_connected_as(connection_id)
					else:
						self.publish_disconnected_as(connection_id, reason="login_no_session")
					self.publish_value_as(connection_id, publish_key, res)
					log.info(f"login state: id={connection_id} connected={st.connected} session_id={session_mgr.get().session_id!r} cfg_sig={session_mgr.cfg_signature()!r}")

				elif st and action == "logout":
					st.connected = False
					st.last_error = ""
					self.publish_disconnected_as(connection_id, reason="logout")
					self.publish_value_as(connection_id, publish_key, res)
					log.info(f"logout ok: id={connection_id}")

				else:
					if st:
						st.connected = session_mgr.has_session()
					self.publish_value_as(connection_id, publish_key, res)

			except Exception as ex:
				err = str(ex)
				if st:
					st.last_error = err
					if action == "login":
						st.connected = False
						self.publish_disconnected_as(connection_id, reason=err)

				self.publish_error_as(connection_id, key=connection_id, action=action, error=err)
				log.error(f"request failed: id={connection_id} action={action} err={ex!r}")

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


def _cfg_signature(cfg: ItacConnectionConfig) -> str:
	# For logging/debug only. Do NOT include passwords.
	return f"{cfg.base_url}|station={cfg.station_number}|client={cfg.client}|reg={cfg.registration_type}|sys={cfg.system_identifier}|user={cfg.user}"


# ------------------------------------------------------------------ IMSApi REST calls

def _actions_url(cfg: ItacConnectionConfig, function_name: str) -> str:
	base = (cfg.base_url or "").rstrip("/")
	return f"{base}/{function_name.lstrip('/')}"


def _post_action(http: _ThreadLocalHttp, cfg: ItacConnectionConfig, function_name: str, body: Any) -> dict:
	if not function_name:
		raise ValueError("missing function_name")

	url = _actions_url(cfg, function_name)
	sess = http.session()

	body_dict = body if isinstance(body, dict) else {}
	redacted = _redact_body(body_dict)

	logger.info(
		f"HTTP POST iTAC: connection_id={cfg.connection_id} function={function_name} url={url} "
		f"timeout_s={cfg.timeout_s} verify_ssl={cfg.verify_ssl} body={_shorten_json(redacted, 2000)}"
	)

	start = time.time()
	resp = sess.post(
		url,
		json=body_dict,
		timeout=cfg.timeout_s,
		verify=cfg.verify_ssl,
		headers={"Content-Type": "application/json"},
	)
	elapsed_ms = round((time.time() - start) * 1000.0, 2)

	logger.info(
		f"HTTP RESP iTAC: connection_id={cfg.connection_id} function={function_name} status={resp.status_code} "
		f"elapsed_ms={elapsed_ms} text={_shorten_str(resp.text or '', 2000)}"
	)

	resp.raise_for_status()

	try:
		data = resp.json()
	except Exception:
		data = {"raw": resp.text}

	if not isinstance(data, dict):
		out = {"data": data}
		logger.info(f"HTTP JSON iTAC: connection_id={cfg.connection_id} function={function_name} json={_shorten_json(_redact_body(out), 2000)}")
		return out

	logger.info(f"HTTP JSON iTAC: connection_id={cfg.connection_id} function={function_name} json={_shorten_json(_redact_body(data), 2000)}")
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
	logger.info(f"call regLogin: connection_id={cfg.connection_id} station_number={cfg.station_number!r} client={cfg.client!r} reg_type={cfg.registration_type!r} sys_id={cfg.system_identifier!r} user={cfg.user!r}")
	return _post_action(http, cfg, "regLogin", body)


def _reg_logout(http: _ThreadLocalHttp, cfg: ItacConnectionConfig, session: ItacSessionContext) -> dict:
	body = {
		"sessionContext": {
			"sessionId": str(session.session_id),
			"persId": int(session.pers_id),
			"locale": str(session.locale),
		}
	}
	logger.info(f"call regLogout: connection_id={cfg.connection_id} session_id={session.session_id!r} pers_id={session.pers_id} locale={session.locale!r}")
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
	logger.info(f"call customFunction: connection_id={cfg.connection_id} session_id={session.session_id!r} method_name={method_name!r} in_args={body.get('inArgs')!r}")
	return _post_action(http, cfg, "customFunction", body)


def _tr_get_station_setting(http: _ThreadLocalHttp, cfg: ItacConnectionConfig, session: ItacSessionContext, keys: Any) -> dict:
	keys_list = keys if isinstance(keys, list) else []
	body = {
		"sessionContext": {
			"sessionId": str(session.session_id),
			"persId": int(session.pers_id),
			"locale": str(session.locale),
		},
		"stationNumber": cfg.station_number,
		"stationSettingResultKeys": keys_list,
	}
	logger.info(f"call trGetStationSetting: connection_id={cfg.connection_id} session_id={session.session_id!r} station_number={cfg.station_number!r} keys={keys_list!r}")
	return _post_action(http, cfg, "trGetStationSetting", body)


# ------------------------------------------------------------------ Session handling (shared)

def _ensure_session(http: _ThreadLocalHttp, session_mgr: ItacSessionManager, cfg: ItacConnectionConfig) -> None:
	if session_mgr.has_session():
		return

	cfg_sig = _cfg_signature(cfg)
	logger.info(f"ensure_session: missing session -> regLogin now (cfg_sig={cfg_sig})")

	res = _reg_login(http, cfg)
	sess = _extract_session_from_login_response(cfg, res)
	if not sess.session_id:
		# Fail hard. Do NOT proceed with empty sessionContext.
		raise Exception(f"regLogin returned no sessionId (cfg_sig={cfg_sig})")

	session_mgr.set(sess, cfg_sig)
	logger.info(f"ensure_session: session ready session_id={sess.session_id!r} pers_id={sess.pers_id} locale={sess.locale!r} cfg_sig={cfg_sig}")


def _extract_session_from_login_response(cfg: ItacConnectionConfig, res: dict) -> ItacSessionContext:
	# login response can be:
	# 1) {"sessionContext": {...}}
	# 2) {"result": {"return_value": 0, "sessionContext": {...}}}
	ctx = None

	if isinstance(res, dict):
		if isinstance(res.get("sessionContext"), dict):
			ctx = res.get("sessionContext")
		elif isinstance(res.get("session_context"), dict):
			ctx = res.get("session_context")
		else:
			result = res.get("result")
			if isinstance(result, dict):
				if isinstance(result.get("sessionContext"), dict):
					ctx = result.get("sessionContext")
				elif isinstance(result.get("session_context"), dict):
					ctx = result.get("session_context")

	if not isinstance(ctx, dict):
		ctx = {}

	sid = str(ctx.get("sessionId") or ctx.get("session_id") or "")
	pid_raw = ctx.get("persId") if "persId" in ctx else ctx.get("pers_id", 0)

	try:
		pid = int(pid_raw or 0)
	except Exception:
		pid = 0

	loc = str(ctx.get("locale") or "")
	if cfg.force_locale:
		loc = cfg.force_locale

	logger.info(
		f"login sessionContext parsed: session_id={sid!r} pers_id={pid} locale={loc!r} "
		f"raw_ctx={_shorten_json(_redact_body(ctx), 1200)}"
	)
	return ItacSessionContext(session_id=sid, pers_id=pid, locale=loc)



# ------------------------------------------------------------------ Return code extraction (best-effort)

def _extract_return_code(res: Any) -> Optional[int]:
	"""
	iTAC responses usually include some return/result code.
	Exact key depends on function/version. This is best-effort.
	"""
	if not isinstance(res, dict):
		return None

	# common candidates seen across APIs
	candidates = [
		"returnCode", "return_code",
		"resultCode", "result_code",
		"errorCode", "error_code",
		"code",
	]

	for k in candidates:
		if k in res:
			try:
				return int(res.get(k))
			except Exception:
				return None

	# sometimes nested
	for nk in ["result", "error", "status"]:
		val = res.get(nk)
		if isinstance(val, dict):
			for k in candidates:
				if k in val:
					try:
						return int(val.get(k))
					except Exception:
						return None

	return None


# ------------------------------------------------------------------ Logging helpers

def _redact_body(value: Any) -> Any:
	"""
	Redact secrets while still logging "every params".
	Passwords / tokens should never be written to logs in plain text.
	"""
	SENSITIVE_KEYS = set([
		"password", "pass", "pwd",
		"stationPassword",
		"token", "access_token", "refresh_token", "authorization", "auth",
	])

	if isinstance(value, dict):
		out = {}
		for k, v in value.items():
			ks = str(k)
			if ks in SENSITIVE_KEYS or ks.lower() in SENSITIVE_KEYS:
				out[k] = "***REDACTED***"
			else:
				out[k] = _redact_body(v)
		return out

	if isinstance(value, list):
		return [_redact_body(v) for v in value]

	return value


def _shorten_str(s: str, n: int) -> str:
	s = s or ""
	if len(s) <= n:
		return s
	return s[:n] + "..."


def _shorten_json(value: Any, n: int) -> str:
	try:
		s = json.dumps(value, ensure_ascii=False, sort_keys=True)
	except Exception:
		try:
			s = repr(value)
		except Exception:
			s = "<unserializable>"
	return _shorten_str(s, n)
