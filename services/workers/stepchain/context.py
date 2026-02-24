# services/workers/stepchain/context.py
from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, Optional

from loguru import logger

from services.workers.stepchain.apis.values_api import ValuesApi
from services.workers.stepchain.apis.vars_api import VarsApi
from services.workers.stepchain.apis.ui_api import UiApi
from services.workers.stepchain.apis.flow_api import FlowApi
from services.workers.stepchain.apis.timing_api import TimingApi
from services.workers.stepchain.apis.workers_api import WorkersApi
from services.workers.stepchain.apis.views_api import ViewsApi


class StepChainContext:
    """
    Internal engine context for one running step chain instance.

    IMPORTANT:
    - This object is owned by the runtime.
    - User scripts MUST NOT receive this object directly.
    - Scripts should receive `public`, which exposes a stable, limited API.
    """

    def __init__(
        self,
        chain_id: str,
        worker_bus: Any,
        bridge: Any,
        state: Any,
        send_cmd: Any = None,
    ) -> None:
        self.chain_id = str(chain_id or uuid.uuid4())
        self.worker_bus = worker_bus
        self.bridge = bridge
        self.state = state
        self.send_cmd = send_cmd

        self.data: Dict[str, Dict[str, Any]] = {}

        self.step = 0
        self.next_step = 0
        self.step_time = 0.0
        self.step_elapsed_s = 0.0
        self.cycle_time = 0.1
        self.cycle_count = 0
        self.paused = False
        self._step_started_ts = 0.0

        self.error_flag = False
        self.error_message = ""
        self.step_desc = ""
        self._suppress_slow_tick_warning_once = False

        self._vars: Dict[str, Any] = {}
        self._ui_state: Optional[Dict[str, Any]] = None
        self._app_state: Dict[str, Any] = {}
        self._last_seen_by_source: Dict[str, str] = {}
        self._public: Optional[PublicStepChainContext] = None

        self._modal_pending = {}  # key -> request_id
        self._modal_result_by_key = {}  # key -> ANY result (bool/dict/str/...)
        self._modal_key_by_request_id = {}  # request_id -> key

        logger.bind(component="StepChainContext", chain_id=self.chain_id).debug("created")

    def _modal_is_pending(self, key: str) -> bool:
        return str(key) in self._modal_pending

    def _modal_mark_pending(self, key: str, request_id: str) -> None:
        k = str(key)
        rid = str(request_id)
        self._modal_pending[k] = rid
        self._modal_key_by_request_id[rid] = k

    def _modal_clear_pending(self, key: str) -> None:
        k = str(key)
        rid = self._modal_pending.pop(k, None)
        if rid:
            self._modal_key_by_request_id.pop(rid, None)

    def _modal_get_result_for_key(self, key: str):
        k = str(key)
        if k in self._modal_result_by_key:
            return self._modal_result_by_key.pop(k)
        return None


    def _modal_set_result_for_request(self, request_id: str, result) -> None:
        key = self._modal_key_by_request_id.get(str(request_id))
        if not key:
            return

        # store whatever came back (bool, dict, ...)
        self._modal_result_by_key[key] = result
        self._modal_clear_pending(key)

    def _modal_reset(self, key: Optional[str] = None) -> None:
        """
        Clear modal pending/result state.

        If key is None: clears ALL modal state.
        If key is provided: clears only that key.

        Does not talk to UI. Use UiApi.popup_clear(...) to also close UI popup.
        """
        if key is None:
            self._modal_pending.clear()
            self._modal_result_by_key.clear()
            self._modal_key_by_request_id.clear()
            return

        k = str(key or "").strip()
        if not k:
            return

        # clear pending mapping
        req_id = self._modal_pending.pop(k, None)
        if req_id:
            self._modal_key_by_request_id.pop(req_id, None)

        # clear any stored result
        self._modal_result_by_key.pop(k, None)

    @property
    def public(self) -> "PublicStepChainContext":
        """Public, script-safe API wrapper."""
        if self._public is None:
            self._public = PublicStepChainContext(self)
        return self._public

    def _update_bus_value(self, source: str, source_id: str, payload: Any) -> None:
        source = str(source or "unknown")
        source_id = str(source_id or "")

        if source not in self.data:
            self.data[source] = {}

        if isinstance(payload, dict) and "key" in payload and "value" in payload:
            k = str(payload.get("key") or "")
            if k:
                existing = self.data[source].get(source_id)
                if not isinstance(existing, dict) or ("key" in existing and "value" in existing):
                    existing = {}
                existing[k] = payload
                existing["__last__"] = payload
                self.data[source][source_id] = existing
            else:
                self.data[source][source_id] = payload
        else:
            self.data[source][source_id] = payload

        self._last_seen_by_source[source] = source_id

    def _update_app_state(self, key: str, value: Any) -> None:
        key_s = str(key or "").strip()
        if not key_s:
            return
        self._app_state[key_s] = value

    def _replace_app_state(self, values: Dict[str, Any]) -> None:
        if not isinstance(values, dict):
            return
        self._app_state = dict(values)

    def get_state(self) -> Dict[str, Any]:
        """State exported to UI; includes runtime state, vars, and ui_state."""
        ui_state = self._ui_state if isinstance(self._ui_state, dict) else {}

        return {
            "chain_id": self.chain_id,
            "step": self.step,
            "step_time": self.step_time,
            "step_elapsed_s": self.step_elapsed_s,
            "cycle_count": self.cycle_count,
            "error_flag": self.error_flag,
            "error_message": self.error_message,
            "step_desc": self.public.step_desc,
            "paused": self.paused,
            "data": copy.deepcopy(self._vars),
            "ui_state": copy.deepcopy(ui_state),
            "app_state": copy.deepcopy(self._app_state),
        }


class PublicStepChainContext:
    """Stable, script-facing context (public API)."""

    def __init__(self, ctx: StepChainContext) -> None:
        self._ctx = ctx

        self.values = ValuesApi(ctx)
        self.vars = VarsApi(ctx)
        self.ui = UiApi(ctx)
        self.flow = FlowApi(ctx)
        self.timing = TimingApi(ctx)
        self.workers = WorkersApi(ctx)
        self.worker = self.workers  # alias
        self.view = ViewsApi(ctx)

    @property
    def chain_id(self) -> str:
        return self._ctx.chain_id

    @property
    def cycle_count(self) -> int:
        return int(self._ctx.cycle_count)

    @property
    def paused(self) -> bool:
        return bool(self._ctx.paused)

    @property
    def error_flag(self) -> bool:
        return bool(self._ctx.error_flag)

    @property
    def error_message(self) -> str:
        return str(self._ctx.error_message or "")

    @property
    def step(self) -> int:
        return int(self._ctx.step)

    @property
    def data(self) -> Dict[str, Any]:
        """Compatibility alias for legacy scripts (mapped to vars)."""
        return self._ctx._vars

    @property
    def step_desc(self) -> str:
        return str(self._ctx.step_desc or "")

    def goto(self, step: int, desc: str = "") -> None:
        self.flow.goto(step=step, desc=desc)

    # -------------------- ergonomics: non-blocking wait --------------------

    def wait(self, seconds: float, next_step: int, desc: str = "") -> bool:
        """
        Non-blocking wait using the engine's step timer.

        Usage pattern:
            # In a dedicated WAIT step:
            if ctx.wait(1.0, STEP.NEXT):
                return  # optional; once it jumps you're done

        Returns True if the jump happened.
        """
        if self.timing.timeout(seconds):
            self.flow.goto(next_step, desc=desc)
            return True
        return False

    def notify(self, message: str, type_: str = "info") -> None:
        self.ui.notify(message, type_)

    def notify_positive(self, message: str) -> None:
        self.ui.notify(message, "positive")

    def notify_negative(self, message: str) -> None:
        self.ui.notify(message, "negative")

    def notify_warning(self, message: str) -> None:
        self.ui.notify(message, "warning")

    def notify_info(self, message: str) -> None:
        self.ui.notify(message, "info")

    def set_state(self, key: str, value: Any) -> None:
        self.ui.set_state(key, value)

    def get_state_var(self, key: str, default: Any = None) -> Any:
        return self.values.state(key, default)

    def get_state(self, key: str, default: Any = None) -> Any:
        return self.get_state_var(key, default)

    def state(self, key: str, default: Any = None) -> Any:
        return self.get_state_var(key, default)

    def set_state_many(self, **values: Any) -> None:
        self.ui.set_state_many(**values)

    def update_state(self, key: str, value: Any) -> None:
        self.set_state(key, value)

    # -------------------- iTAC (IMSApi REST) helpers --------------------

    def itac_station_setting(self, connection_id: str, keys: Any, timeout_s: float = 5.0) -> Any:
        return self.workers.itac_station_setting(connection_id, keys, timeout_s=timeout_s)

    def itac_custom_function(self, connection_id: str, method_name: str, in_args: Any = None, timeout_s: float = 10.0) -> Any:
        return self.workers.itac_custom_function(connection_id, method_name, in_args=in_args, timeout_s=timeout_s)

    def itac_raw_call(self, connection_id: str, function_name: str, body: Any = None, timeout_s: float = 10.0) -> Any:
        return self.workers.itac_raw_call(connection_id, function_name, body=body, timeout_s=timeout_s)

    def itac_login_user(
        self,
        connection_id: str,
        *,
        station_number: str,
        username: str,
        password: str | None = None,
        client: str = "01",
        timeout_s: float = 10.0,
    ) -> Any:
        return self.workers.itac_login_user(
            connection_id,
            station_number=station_number,
            username=username,
            password=password,
            client=client,
            timeout_s=timeout_s,
        )

    # -------------------- simplified worker IO for non-programmers --------------------

    def read_com(self, client_id: str, default: Any = None) -> Any:
        return self.workers.com_last(client_id, default=default)

    def send_com(self, client_id: str, data:str , add_delimiter:bool=True) -> Any:
         self.workers.com_send(client_id, data , add_delimiter=add_delimiter)

    def com_wait(self, client_id: str, timeout_s: float = 10.0,default: Any = None) -> Any:
         self.workers.com_wait(client_id, timeout_s=timeout_s ,default=default)

    def send_tcp(self, client_id: str, data: Any) -> None:
        self.workers.tcp_send(client_id, data)

    def read_tcp(self, client_id: str, default: Any = None, decode: bool = True) -> Any:
        return self.workers.tcp_message(client_id, default=default, decode=decode)

    def wait_tcp(self, client_id: str, timeout_s: float = 1.0, default: Any = None, decode: bool = True) -> Any:
        return self.workers.tcp_wait(client_id, default=default, timeout_s=timeout_s, decode=decode)

    def write_plc(self, client_id: str, name: str, value: Any) -> None:
        self.workers.plc_write(client_id, name, value)

    def read_plc(self, client_id: str, name: str, default: Any = None) -> Any:
        return self.workers.plc_value(client_id, name, default)

    def wait_plc(self, client_id: str, name: str, default: Any = None, timeout_s: float = 1.0) -> Any:
        return self.workers.plc_wait_value(client_id, name, default=default, timeout_s=timeout_s)

    def rest_request(
        self,
        endpoint: str,
        method: str = "GET",
        path: str | None = None,
        url: str | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        json_body: Any = None,
        data: Any = None,
        timeout_s: float = 10.0,
    ) -> dict:
        return self.workers.rest_request(
            endpoint,
            method=str(method or "GET"),
            path=path,
            url=url,
            params=params,
            headers=headers,
            json_body=json_body,
            data=data,
            timeout_s=timeout_s,
        )

    def rest_get(self, endpoint: str, path: str, params: dict[str, Any] | None = None, timeout_s: float = 10.0) -> dict:
        return self.workers.rest_get(endpoint, path, params=params, timeout_s=timeout_s)

    def rest_post_json(self, endpoint: str, path: str, body: Any, timeout_s: float = 10.0) -> dict:
        return self.workers.rest_post_json(endpoint, path, body, timeout_s=timeout_s)

    def read_worker_value(self, worker: str, source_id: str, key: str, default: Any = None) -> Any:
        return self.workers.get(worker, source_id, key, default)

    def error(self, message: str) -> None:
        self.flow.fail(message)

    def log_error(self, message: str) -> None:
        logger.error(message)

    def log_success(self, message: str) -> None:
        logger.success(message)

    def log_info(self, message: str) -> None:
        logger.info(message)

    def log_debug(self, message: str) -> None:
        logger.debug(message)

    def log_warning(self, message: str) -> None:
        logger.warning(message)

    def camera_capture(self, key: str, default: Any = None) -> Any:
        return self.values.by_key(key, default)

    def global_var(self, key: str, default: Any = None) -> Any:
        return self.values.global_var(key, default)

    def global_vars(self) -> Dict[str, Any]:
        return self.values.global_all()

    def set_cycle_time(self, seconds: float) -> None:
        self.timing.set_cycle_time(seconds)

    def set_step_desc(self, value: str) -> None:
        self._ctx.step_desc = value

    def snapshot(self) -> Dict[str, Any]:
        ui_state = self._ctx._ui_state if isinstance(self._ctx._ui_state, dict) else {}
        return {
            "chain_id": self._ctx.chain_id,
            "step": self._ctx.step,
            "cycle_count": self._ctx.cycle_count,
            "step_elapsed_s": self._ctx.step_elapsed_s,
            "error_flag": self._ctx.error_flag,
            "error_message": self._ctx.error_message,
            "step_desc": self.step_desc,
            "paused": self._ctx.paused,
            "vars": self.vars.as_dict(),
            "ui_state": dict(ui_state),
            "app_state": self.values.state_all(),
        }
