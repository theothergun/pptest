# Automation Runtime Programmer's Manual (API + UI + Context Reference)

> This document describes the Automation Runtime contract in this repository: script context, available APIs, worker I/O, view/UI command buttons, and state conventions.

---

## 1) Runtime architecture in one page

A Automation Runtime script runs with a **public context object** (`ctx`) that wraps an internal runtime context:

- Internal runtime: `AutomationContext` (engine-owned, not for direct script use).
- Script-facing wrapper: `PublicAutomationContext`.
- Namespaced APIs exposed on `ctx`:
  - `ctx.values`
  - `ctx.vars`
  - `ctx.ui`
  - `ctx.flow`
  - `ctx.timing`
  - `ctx.workers` (alias: `ctx.worker`)

The runtime continuously mirrors:

- bus values into `ctx.data`
- app state into `ctx._app_state` (read via `ctx.values.state(...)`)
- script variables into `ctx._vars` (read/write via `ctx.vars`)

---

## 2) Public script context (`PublicAutomationContext`)

### 2.1 Properties

- `ctx.chain_id: str`
- `ctx.cycle_count: int`
- `ctx.paused: bool`
- `ctx.error_flag: bool`
- `ctx.error_message: str`
- `ctx.step: int`
- `ctx.data: dict` (legacy alias to vars dictionary)
- `ctx.step_desc: str`

### 2.2 Flow & timing convenience

- `ctx.goto(step: int, desc: str = "")`
- `ctx.wait(seconds: float, next_step: int, desc: str = "") -> bool`
  - non-blocking timeout helper using step elapsed time
- `ctx.set_cycle_time(seconds: float)`
- `ctx.set_step_desc(value: str)`

### 2.3 Notifications, state, logs

- `ctx.notify(message, type_="info")`
- `ctx.notify_positive(message)`
- `ctx.notify_negative(message)`
- `ctx.notify_warning(message)`
- `ctx.notify_info(message)`

App state shortcuts:

- `ctx.set_state(key, value)`
- `ctx.set_state_many(**values)`
- `ctx.update_state(key, value)`
- `ctx.get_state_var(key, default=None)`
- `ctx.get_state(key, default=None)`
- `ctx.state(key, default=None)`

Logging shortcuts:

- `ctx.log_error(...)`, `ctx.log_warning(...)`, `ctx.log_info(...)`, `ctx.log_debug(...)`, `ctx.log_success(...)`

### 2.4 Worker convenience wrappers on `ctx`

- COM: `read_com`, `send_com`, `com_wait`
- TCP: `send_tcp`, `read_tcp`, `wait_tcp`
- PLC/TwinCAT: `write_plc`, `read_plc`, `wait_plc`
- REST: `rest_request`, `rest_get`, `rest_post_json`
- Generic worker value: `read_worker_value(worker, source_id, key, default=None)`
- iTAC: `itac_station_setting`, `itac_custom_function`, `itac_raw_call`, `itac_login_user`

Other:

- `ctx.error(message)` (marks chain failed)
- `ctx.camera_capture(key, default=None)` (key-based value lookup)
- `ctx.global_var(key, default=None)` / `ctx.global_vars()`
- `ctx.snapshot() -> dict`

---

## 3) `ctx.values` API (read-only mirrored values)

- `source(source)` → deep copy of one source bucket
- `all()` → deep copy of full mirrored data
- `last(source, default=None)` → most recent payload from source
- `get(source, source_id, default=None)`
- `by_key(key, default=None)` → scans latest payloads for matching `{"key": ...}`
- `state(key, default=None)` / `state_all()` → mirrored AppState
- `global_var(key, default=None)` / `global_all()` → global vars from app config

---

## 4) `ctx.vars` API (persistent per-chain script vars)

- `get(key, default=None)`
- `set(key, value)`
- `has(key)`
- `pop(key, default=None)`
- `delete(key)`
- `clear()`
- `inc(key, amount=1.0, default=0.0) -> float`
- `as_dict() -> dict`

Use `ctx.vars` for script-local memory across cycles.

---

## 5) `ctx.flow` API

- `goto(step, desc="")`
- `fail(message)`
- `clear_error()`
- `pause()`
- `resume()`

Notes:
- `goto()` sets `next_step`; runtime performs transition.
- Changing to a different step resets step-start timing internally.

---

## 6) `ctx.timing` API

- `set_cycle_time(seconds)`
- `step_seconds() -> float`
- `timeout(seconds) -> bool`

`timeout(seconds <= 0)` returns `True` immediately.

---

## 7) `ctx.ui` API (UI/event/modal layer)

## 7.1 Lightweight UI state (chain-owned)

- `set(key, value)`
- `merge(patch: dict)`
- `clear()`

This is chain-owned `ui_state` included in exported chain state.

## 7.2 Command/payload consumption from UI bus

- `consume_command(key, value_field="cmd", dedupe=True, normalize=True) -> Optional[str]`
- `consume_payload(key, dedupe=True) -> Optional[dict]`
- `consume_view_cmd(pattern="view.cmd.*", command=None, commands=None, event=None, events=None, dedupe=True, normalize=True) -> Optional[dict]`
- `subscribe_view_cmd(pattern="view.cmd.*") -> Subscription|None`

Dedupe strategy uses `event_id` when present and falls back to payload fingerprints.

## 7.3 AppState bridge helpers (persisted UI state)

- `set_state(key, value)`
- `set_state_many(**values)`
- `inc_state_int(key, amount=1, default=0) -> int`
- `show(...)` convenience helper for instruction/feedback text+state

State severity map accepted by `show(...)`:

- `1|"ok"|"green"`
- `2|"warn"|"warning"|"yellow"`
- `3|"error"|"red"`
- `4|"info"|"blue"`
- `5|"idle"|"grey"|"gray"`

## 7.4 Toast/events

- `notify(message, type_="info")`
- `event(name, **payload)` publishes `script.event.<name>` as VALUE_CHANGED

## 7.5 Modal APIs (non-blocking)

- `popup_confirm(...) -> Optional[bool]`
- `popup_message(...) -> Optional[dict]`
- `popup_input_text(...) -> Optional[dict]`
- `popup_input_number(...) -> Optional[dict]`
- `popup_choose(...) -> Optional[dict]`
- `popup_close(key)`
- `popup_clear(key: Optional[str] = None)`
- `popup_close_all()`

Behavior pattern:

- 1st call emits modal request and returns `None`
- while waiting returns `None` and can update `step_desc`
- once response arrives returns normalized result and clears pending state

## 7.6 Wait popup helpers

- `popup_wait_open(key="packaging.wait", title="Please wait", message="Working ...")`
- `popup_wait_close(key="packaging.wait")`

---

## 8) `ctx.workers` API (typed worker I/O)

## 8.1 Generic cached reads

- `get(worker, source_id, key, default=None)`
- `latest(worker, source_id, default=None)`

## 8.2 TCP client

- `tcp_send(client_id, data)`
- `tcp_connect(client_id)`
- `tcp_disconnect(client_id)`
- `tcp_message(client_id, default=None, decode=True, encoding="utf-8")`
- `tcp_wait(client_id, default=None, timeout_s=1.0, decode=True, encoding="utf-8")`

## 8.3 TwinCAT / PLC

- `plc_write(client_id, name, value, plc_type=None, string_len=None)`
- `plc_value(client_id, name, default=None)`
- `plc_wait_value(client_id, name, default=None, timeout_s=1.0)`

## 8.4 OPC UA

- `opcua_value(endpoint, name_or_alias, default=None)`
- `opcua_wait_value(endpoint, name_or_alias, default=None, timeout_s=1.0)`
- `opcua_read(endpoint, node_id=None, alias=None, timeout_s=1.0) -> dict`
- `opcua_write(endpoint, node_id=None, alias=None, name_or_alias=None, value=None)`

`opcua_read` returns either error dict (`worker_error`, `timeout`, etc.) or payload with `_meta`.

## 8.5 REST

- `rest_request(endpoint, method="GET", path=None, url=None, params=None, headers=None, json_body=None, data=None, timeout_s=10.0) -> dict`
- `rest_get(endpoint, path, params=None, timeout_s=10.0)`
- `rest_post_json(endpoint, path, body, timeout_s=10.0)`

## 8.6 iTAC

- `itac_station_setting(connection_id, keys, timeout_s=5.0)`
- `itac_custom_function(connection_id, method_name, in_args, timeout_s=10.0)`
- `itac_raw_call(connection_id, function_name, body, timeout_s=10.0)`
- `itac_login_user(connection_id, station_number, username, password=None, client="01", timeout_s=10.0)`
- `itac_expect_ok(res) -> {ok, return_value, out_args, error, raw}`

## 8.7 COM device

- `com_last(device_id, default=None)`
- `com_wait(device_id, timeout_s=2.0, default=None)`
- `com_send(device_id, data, add_delimiter=False)`

---

## 9) `ctx.ui` API (view-agnostic helpers)

Use command/state keys, not view-bound objects:

- `ctx.ui.consume_command("packaging.cmd")`
- `ctx.ui.consume_payload("container_management.cmd")`
- `ctx.ui.consume_view_cmd("view.cmd.*", command="refresh")`
- `ctx.ui.consume_view_command("view.cmd.*", commands=[...])`
- `ctx.set_state("container_number", "...")`
- `ctx.set_state_many(current_container_qty=1, part_good=1)`
- `ctx.ui.set_button_enabled("start", True, view_id="packaging_nox")`
- `ctx.ui.set_buttons_enabled({...}, view_id="packaging_nox")`
- `ctx.ui.set_operator_device_panel_visible(True)`
- `ctx.ui.set_operator_device_states([...])`
- `ctx.ui.upsert_operator_device_state(...)`
- `ctx.ui.clear_operator_device_states()`
---

## 10) Chain exported state shape

`AutomationContext.get_state()` emits:

```json
{
  "chain_id": "...",
  "step": 0,
  "step_time": 0.0,
  "step_elapsed_s": 0.0,
  "cycle_count": 0,
  "error_flag": false,
  "error_message": "",
  "step_desc": "",
  "paused": false,
  "data": {"...": "..."},
  "ui_state": {"...": "..."},
  "app_state": {"...": "..."}
}
```

Meaning:

- `data` = script vars (`_vars`) in export
- `ui_state` = chain-owned UI state (`ctx.ui.set/merge/clear`)
- `app_state` = mirrored app state (`ctx.ui.set_state*` / bridge updates)

---

## 11) UI command contract (button -> bus -> script)

Buttons in operator pages publish standardized payloads through `publish_view_cmd(...)`:

- Legacy message: `topic=VALUE_CHANGED`, key=`<cmd_key>`, value includes `action`, `event_id`, `wait_modal_key`
- New message: `topic=view.cmd.<view>`, payload includes above + `view`, `cmd_key`

Use in scripts:

- `ctx.ui.consume_payload("packaging.cmd")` (if using cmd_key channel, then read `payload["action"]["name"]`)
- `ctx.ui.consume_command("packaging.cmd")`
- or wildcard read: `ctx.ui.consume_view_cmd("view.cmd.*", command="refresh")`

---

## 12) UI buttons and command values (current implementation)

## 12.1 Packaging page (`packaging.cmd`)

Buttons publish:

- `remove`
- `print`
- `new`
- `refresh`
- `reset`

Bound state keys shown on screen:

- `container_number`, `part_number`, `description`
- `current_container_qty`, `max_container_qty`, `last_serial_number`
- `part_good`, `part_bad`
- `work_instruction`, `work_feedback`
- `work_instruction_state`, `work_feedback_state`

## 12.2 Packaging NOX page (`packaging.cmd`)

Buttons publish:

- `reset_counters`
- `start`
- `stop`
- `reset`
- `refresh`

Bound state keys shown on screen include packaging keys plus `part_good`, `part_bad`.

## 12.3 Container management page (`container_management.cmd`)

Buttons publish:

- `search_container`
- `search_serial`
- `activate`
- `search`
- `refresh`
- `remove_all`
- `remove_selected_serial` (with extra payload: selected serial row fields)

Primary state keys:

- `container_mgmt_search_query`
- `container_mgmt_container_rows`
- `container_mgmt_container_selected`
- `container_mgmt_serial_rows`
- `container_mgmt_active_container`

---

## 13) Modal and wait topics

Topics used:

- `WorkerTopics.TOPIC_MODAL_REQUEST` = `ui.modal.request`
- `WorkerTopics.TOPIC_MODAL_RESPONSE` = `ui.modal.response`
- `WorkerTopics.TOPIC_MODAL_CLOSE` = `ui.modal.close`
- `WorkerTopics.VALUE_CHANGED`
- `WorkerTopics.ERROR`

Wait dialog contract (`install_wait_dialog`):

- open via VALUE_CHANGED key=`view.wait.<view>` and `value.action == "open"`
- close via `ui.modal.close` with matching `key` or `close_active=True`

---

## 14) Script authoring notes / best practices

- Prefer **non-blocking** step patterns (state machine + `ctx.wait`/`ctx.timing.timeout`).
- Use `ctx.vars` for durable per-chain scratch values.
- Use `ctx.ui.set_state*` for UI-bound persistent variables.
- For synchronous worker replies, prefer dedicated wait methods (`*_wait`, `rest_request`, `opcua_read`, iTAC helpers) rather than polling `ctx.data`.
- Dedupe UI commands with `event_id` aware APIs (`consume_command`, `consume_view_cmd`).
- For modal workflows, call modal API every cycle in a dedicated step until non-`None` response arrives.

---

## 15) Quick example skeleton

```python
def chain(ctx):
    STEP_IDLE = 0
    STEP_WORK = 10

    if ctx.step == STEP_IDLE:
        cmd = ctx.ui.consume_command("packaging.cmd")
        if cmd is None:
            ctx.set_step_desc("Waiting for command...")
            return
        if cmd == "new":
            ctx.set_state("work_instruction", "Create new container")
            ctx.goto(STEP_WORK, "Processing new container")
        return

    if ctx.step == STEP_WORK:
        if ctx.wait(1.0, STEP_IDLE, desc="Done"):
            return
```



