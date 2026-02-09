from __future__ import annotations

import json
import queue
import ssl
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus
from services.worker_commands import RestApiCommands as Commands
from services.worker_registry import SendCmdFn
from services.worker_topics import RestApiTopics as Topics
from services.workers.base_worker import BaseWorker


@dataclass
class RestApiEndpoint:
    name: str
    base_url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout_s: float = 10.0
    verify_ssl: bool = True


class RestApiWorker(BaseWorker):
    def run(self) -> None:
        self.start()
        self.set_connected(True)
        self.notify("REST API worker started", "info")
        endpoints: dict[str, RestApiEndpoint] = {}
        endpoints_lock = threading.Lock()

        try:
            while not self.should_stop():
                _execute_cmds(self.log, self.worker_bus, self.commands, self.stop_event, endpoints, endpoints_lock)
                time.sleep(0.01)
        finally:
            self.notify("REST API worker stopped", "info")
            self.set_connected(False)
            self.mark_stopped()


def _execute_cmds(log, worker_bus, commands, stop, endpoints, endpoints_lock):
    for _ in range(50):
        try:
            cmd, payload = commands.get_nowait()
        except queue.Empty:
            return

        if cmd in ("__stop__", Commands.STOP):
            log.info("stop requested")
            stop.set()
            return

        if cmd == Commands.ADD_ENDPOINT:
            endpoint = _parse_endpoint_payload(payload)
            if not endpoint.name or not endpoint.base_url:
                _publish_error(worker_bus, endpoint.name, "invalid endpoint config")
                continue
            log.info("endpoint added: %s base_url=%s", endpoint.name, endpoint.base_url)
            with endpoints_lock:
                endpoints[endpoint.name] = endpoint
            _publish_endpoints(worker_bus, endpoints, endpoints_lock)

        elif cmd == Commands.REMOVE_ENDPOINT:
            name = payload.get("name", "")
            log.info("endpoint removed: %s", name)
            with endpoints_lock:
                endpoints.pop(name, None)
            _publish_endpoints(worker_bus, endpoints, endpoints_lock)

        elif cmd == Commands.REQUEST:
            log.info("request queued: endpoint=%s url=%s method=%s", payload.get("endpoint"), payload.get("url"), payload.get("method"))
            _handle_request(worker_bus, payload, endpoints, endpoints_lock)


def _handle_request(worker_bus, payload, endpoints, endpoints_lock):
    request_id = payload.get("request_id") or uuid.uuid4().hex
    method = str(payload.get("method", "GET")).upper()
    endpoint_name = payload.get("endpoint")
    path = payload.get("path")
    url = payload.get("url")

    endpoint = None
    if endpoint_name:
        with endpoints_lock:
            endpoint = endpoints.get(endpoint_name)
    if endpoint and not url:
        url = _build_url(endpoint.base_url, path, payload.get("params"))
    elif url:
        url = _build_url(url, None, payload.get("params"))

    if not url:
        _publish_error(worker_bus, request_id, "missing url or endpoint")
        return

    headers = {}
    timeout_s = float(payload.get("timeout_s", endpoint.timeout_s if endpoint else 10.0))
    verify_ssl = bool(payload.get("verify_ssl", endpoint.verify_ssl if endpoint else True))

    if endpoint:
        headers.update(endpoint.headers)
    headers.update(_normalize_headers(payload.get("headers")))

    json_body = payload.get("json")
    data_body = payload.get("data")
    body = None
    if json_body is not None:
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        body = json.dumps(json_body).encode("utf-8")
    elif data_body is not None:
        body = _encode_body(data_body, headers)

    context = None
    if not verify_ssl:
        context = ssl._create_unverified_context()

    try:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout_s, context=context) as resp:
            raw = resp.read()
            status = getattr(resp, "status", resp.getcode())
            content_type = resp.headers.get("Content-Type", "")
            charset = resp.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            parsed_json = _maybe_parse_json(text, content_type)
            worker_bus.publish(
                Topics.REQUEST_RESULT,
                request_id=request_id,
                ok=True,
                status=status,
                url=url,
                method=method,
                headers=dict(resp.headers),
                body=text,
                json=parsed_json,
                ts=time.time(),
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        text = raw.decode("utf-8", errors="replace") if raw else ""
        worker_bus.publish(
            Topics.REQUEST_RESULT,
            request_id=request_id,
            ok=False,
            status=exc.code,
            url=url,
            method=method,
            headers=dict(exc.headers or {}),
            body=text,
            json=_maybe_parse_json(text, exc.headers.get("Content-Type", "") if exc.headers else ""),
            error=str(exc),
            ts=time.time(),
        )
    except Exception as exc:
        _publish_error(worker_bus, request_id, str(exc), url=url, method=method)


def _build_url(base_url: str, path: str | None, params: dict[str, Any] | None) -> str:
    url = base_url
    if path:
        url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if params:
        query = urllib.parse.urlencode(params, doseq=True)
        separator = "&" if urllib.parse.urlparse(url).query else "?"
        url = f"{url}{separator}{query}"
    return url


def _normalize_headers(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    return {}


def _encode_body(data: Any, headers: dict[str, str]) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, dict):
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        return urllib.parse.urlencode(data, doseq=True).encode("utf-8")
    return str(data).encode("utf-8")


def _maybe_parse_json(text: str, content_type: str) -> Any:
    if "application/json" in content_type:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


def _publish_endpoints(worker_bus, endpoints, endpoints_lock):
    with endpoints_lock:
        listing = {
            name: {
                "base_url": endpoint.base_url,
                "timeout_s": endpoint.timeout_s,
                "verify_ssl": endpoint.verify_ssl,
                "headers": dict(endpoint.headers),
            }
            for name, endpoint in endpoints.items()
        }
    worker_bus.publish(Topics.ENDPOINTS, endpoints=listing, ts=time.time())


def _publish_error(worker_bus, request_id, message, url=None, method=None):
    worker_bus.publish(
        Topics.REQUEST_ERROR,
        request_id=request_id,
        message=message,
        url=url,
        method=method,
        ts=time.time(),
    )


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


def _parse_endpoint_payload(payload: dict[str, Any]) -> RestApiEndpoint:
    return RestApiEndpoint(
        name=str(payload.get("name", "")).strip(),
        base_url=str(payload.get("base_url", "")).strip(),
        headers=_normalize_headers(payload.get("headers")),
        timeout_s=float(payload.get("timeout_s", 10.0)),
        verify_ssl=bool(payload.get("verify_ssl", True)),
    )
