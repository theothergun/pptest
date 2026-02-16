from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, Future

import requests
from loguru import logger

from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus
from services.worker_commands import RestApiCommands as Commands
from services.worker_registry import SendCmdFn
from services.workers.base_worker import BaseWorker


# ------------------------------------------------------------------ Models

@dataclass
class RestApiEndpoint:
	name: str
	base_url: str
	headers: Dict[str, str] = field(default_factory=dict)
	timeout_s: float = 10.0
	verify_ssl: bool = True


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

class RestApiWorker(BaseWorker):

	def run(self) -> None:
		self.start()
		log = logger.bind(worker="rest")
		log.info("RestApiWorker started")

		http = _ThreadLocalHttp()
		endpoints: Dict[str, RestApiEndpoint] = {}

		exec_ = ThreadPoolExecutor(max_workers=8, thread_name_prefix="rest")
		pending: Dict[Future, Tuple[str, str]] = {}
		# future -> (source_id, publish_key)

		last_status_log_ts = 0.0

		try:
			while not self.should_stop():
				self._execute_cmds(log, http, endpoints, exec_, pending)
				self._poll_futures(log, pending)

				# REST has no persistent connection; mark worker alive.
				self.set_connected(True)

				now = time.time()
				if now - last_status_log_ts >= 5.0:
					last_status_log_ts = now
					log.debug(f"status: endpoints={len(endpoints)} pending={len(pending)}")

				time.sleep(0.02)

		finally:
			log.info("RestApiWorker stopping")
			try:
				exec_.shutdown(wait=False, cancel_futures=True)
			except Exception as ex:
				log.warning(f"ThreadPool shutdown failed: {ex!r}")
			self.close_subscriptions()
			self.set_connected(False)
			self.mark_stopped()
			log.info("RestApiWorker stopped")

	# ------------------------------------------------------------------ Commands

	def _execute_cmds(
		self,
		log,
		http: _ThreadLocalHttp,
		endpoints: Dict[str, RestApiEndpoint],
		exec_: ThreadPoolExecutor,
		pending: Dict[Future, Tuple[str, str]],
	) -> None:
		for _ in range(50):
			try:
				cmd, payload = self.commands.get_nowait()
			except queue.Empty:
				return

			if cmd in ("__stop__", Commands.STOP):
				log.info("received stop command")
				return

			if cmd == Commands.ADD_ENDPOINT:
				ep = _parse_endpoint_payload(payload)
				if not ep.name or not ep.base_url:
					log.warning(f"ADD_ENDPOINT ignored: invalid config payload={payload!r}")
					self.publish_error_as("rest", key=ep.name or "", action="add_endpoint", error="invalid endpoint config")
					continue

				endpoints[ep.name] = ep
				log.info(f"endpoint added: name={ep.name} base_url={ep.base_url} timeout_s={ep.timeout_s} verify_ssl={ep.verify_ssl}")

				self.publish_value_as("rest", "endpoints", _endpoint_listing(endpoints))

			elif cmd == Commands.REMOVE_ENDPOINT:
				name = str(payload.get("name") or "").strip()
				if not name:
					log.warning(f"REMOVE_ENDPOINT ignored: missing name payload={payload!r}")
					continue

				endpoints.pop(name, None)
				log.info(f"endpoint removed: name={name}")
				self.publish_value_as("rest", "endpoints", _endpoint_listing(endpoints))

			elif cmd == Commands.REQUEST:
				request_id = str(payload.get("request_id") or uuid.uuid4().hex)
				endpoint_name = str(payload.get("endpoint") or "").strip()
				source_id = endpoint_name or "rest"
				publish_key = f"rest.{source_id}.result.{request_id}"

				log.info(
					f"cmd REQUEST: request_id={request_id} endpoint={endpoint_name!r} "
					f"method={str(payload.get('method', 'GET')).upper()} "
					f"url={str(payload.get('url') or '')!r} path={str(payload.get('path') or '')!r}"
				)

				def job() -> Dict[str, Any]:
					return _do_request(http, endpoints.get(endpoint_name), payload, request_id)

				fut = exec_.submit(job)
				pending[fut] = (source_id, publish_key)

			else:
				log.debug(f"unknown command ignored: cmd={cmd!r} payload={payload!r}")

	# ------------------------------------------------------------------ Future polling

	def _poll_futures(self, log, pending: Dict[Future, Tuple[str, str]]) -> None:
		done: list[Future] = []

		for fut, meta in list(pending.items()):
			if not fut.done():
				continue

			done.append(fut)
			source_id, publish_key = meta

			try:
				res = fut.result()
				self.publish_value_as(source_id, publish_key, res)
				log.debug(f"result: source_id={source_id} publish_key={publish_key} ok={res.get('ok')} status={res.get('status')} elapsed_ms={res.get('elapsed_ms')}")

			except Exception as ex:
				err = str(ex)
				self.publish_error_as(source_id, key=publish_key, action="request", error=err)
				log.error(f"request failed: source_id={source_id} publish_key={publish_key} err={ex!r}")

		for fut in done:
			try:
				del pending[fut]
			except Exception:
				pass


# ------------------------------------------------------------------ Request implementation

def _do_request(http: _ThreadLocalHttp, endpoint: Optional[RestApiEndpoint], payload: Dict[str, Any], request_id: str) -> Dict[str, Any]:
	method = str(payload.get("method", "GET")).upper()

	url = str(payload.get("url") or "").strip()
	path = payload.get("path")
	params = payload.get("params")

	if endpoint and not url:
		url = _build_url(endpoint.base_url, path, params)
	elif url:
		url = _build_url(url, None, params)

	if not url:
		return {
			"request_id": request_id,
			"ok": False,
			"error": "missing url or endpoint",
			"ts": time.time(),
		}

	headers: Dict[str, str] = {}
	timeout_s = float(payload.get("timeout_s", endpoint.timeout_s if endpoint else 10.0))
	verify_ssl = bool(payload.get("verify_ssl", endpoint.verify_ssl if endpoint else True))

	if endpoint:
		headers.update(endpoint.headers)
	headers.update(_normalize_headers(payload.get("headers")))

	json_body = payload.get("json")
	data_body = payload.get("data")

	log_body = _shorten_json(_redact_for_log({"json": json_body, "data": data_body}), 1200)
	log_headers = _shorten_json(_redact_for_log(headers), 800)

	logger.info(
		f"HTTP REQ: request_id={request_id} method={method} url={url} timeout_s={timeout_s} verify_ssl={verify_ssl} "
		f"headers={log_headers} body={log_body}"
	)

	sess = http.session()
	start = time.time()

	try:
		resp = sess.request(
			method=method,
			url=url,
			params=None,
			headers=headers,
			json=json_body if json_body is not None else None,
			data=_encode_body(data_body) if (json_body is None and data_body is not None) else None,
			timeout=timeout_s,
			verify=verify_ssl,
		)

		elapsed_ms = round((time.time() - start) * 1000.0, 2)

		content_type = resp.headers.get("Content-Type", "")
		text = resp.text or ""
		parsed_json = _maybe_parse_json(text, content_type)

		logger.info(
			f"HTTP RESP: request_id={request_id} status={resp.status_code} elapsed_ms={elapsed_ms} "
			f"content_type={content_type!r} text={_shorten_str(text, 2000)}"
		)

		ok = 200 <= int(resp.status_code) < 300

		return {
			"request_id": request_id,
			"ok": ok,
			"status": int(resp.status_code),
			"url": url,
			"method": method,
			"headers": dict(resp.headers),
			"body": text,
			"json": parsed_json,
			"elapsed_ms": elapsed_ms,
			"ts": time.time(),
		}

	except Exception as exc:
		elapsed_ms = round((time.time() - start) * 1000.0, 2)
		return {
			"request_id": request_id,
			"ok": False,
			"url": url,
			"method": method,
			"error": str(exc),
			"elapsed_ms": elapsed_ms,
			"ts": time.time(),
		}


def _build_url(base_url: str, path: Optional[str], params: Optional[Dict[str, Any]]) -> str:
	base = str(base_url or "").strip()
	if not base:
		return ""

	url = base
	if path:
		if not url.endswith("/"):
			url += "/"
		url += str(path).lstrip("/")

	if params and isinstance(params, dict):
		from urllib.parse import urlencode, urlparse

		query = urlencode(params, doseq=True)
		sep = "&" if urlparse(url).query else "?"
		url = f"{url}{sep}{query}"

	return url


def _normalize_headers(raw: Any) -> Dict[str, str]:
	if isinstance(raw, dict):
		return {str(k): str(v) for k, v in raw.items()}
	return {}


def _encode_body(data: Any) -> Any:
	return data


def _maybe_parse_json(text: str, content_type: str) -> Any:
	if "application/json" in str(content_type or ""):
		try:
			return json.loads(text)
		except Exception:
			return None
	return None


def _endpoint_listing(endpoints: Dict[str, RestApiEndpoint]) -> Dict[str, Any]:
	return {
		name: {
			"base_url": ep.base_url,
			"timeout_s": ep.timeout_s,
			"verify_ssl": ep.verify_ssl,
			"headers": dict(ep.headers),
		}
		for name, ep in endpoints.items()
	}


def _redact_for_log(value: Any) -> Any:
	SENSITIVE_KEYS = set([
		"authorization", "Authorization",
		"token", "access_token", "refresh_token",
		"password", "pwd", "pass",
	])

	if isinstance(value, dict):
		out = {}
		for k, v in value.items():
			ks = str(k)
			if ks in SENSITIVE_KEYS or ks.lower() in SENSITIVE_KEYS:
				out[k] = "***REDACTED***"
			else:
				out[k] = _redact_for_log(v)
		return out

	if isinstance(value, list):
		return [_redact_for_log(v) for v in value]

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


def _parse_endpoint_payload(payload: Dict[str, Any]) -> RestApiEndpoint:
	return RestApiEndpoint(
		name=str(payload.get("name", "")).strip(),
		base_url=str(payload.get("base_url", "")).strip(),
		headers=_normalize_headers(payload.get("headers")),
		timeout_s=float(payload.get("timeout_s", 10.0)),
		verify_ssl=bool(payload.get("verify_ssl", True)),
	)


# ------------------------------------------------------------------ Factory (keep to avoid breaking your worker registry)

def rest_api_worker(
	bridge: UiBridge,
	worker_bus: WorkerBus,
	commands: "queue.Queue[tuple[str, dict[str, Any]]]",
	stop: threading.Event,
	send_cmd: SendCmdFn
) -> None:
	RestApiWorker(
		name="RestApiWorker",
		bridge=bridge,
		worker_bus=worker_bus,
		commands=commands,
		stop=stop,
		send_cmd=send_cmd,
	).run()
