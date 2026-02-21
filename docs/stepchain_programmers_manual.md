# StepChain Programmer's Manual

> Beginner-friendly API + UI reference for writing StepChain scripts.

If you are **not a professional programmer**, this guide is for you. It explains what to call, when to call it, and gives copy/paste examples.

---

## Table of Contents

1. [What StepChain is](#1-what-stepchain-is)
2. [How a script runs (simple mental model)](#2-how-a-script-runs-simple-mental-model)
3. [Your `ctx` object (the thing you use)](#3-your-ctx-object-the-thing-you-use)
4. [How to build steps safely](#4-how-to-build-steps-safely)
5. [Read and write variables](#5-read-and-write-variables)
6. [Update the UI](#6-update-the-ui)
7. [React to UI buttons](#7-react-to-ui-buttons)
8. [Show popups (confirm/input/message)](#8-show-popups-confirminputmessage)
9. [Talk to workers (TCP, PLC, OPCUA, REST, iTAC, COM)](#9-talk-to-workers-tcp-plc-opcua-rest-itac-com)
10. [View helpers (`ctx.view.*`)](#10-view-helpers-ctxview)
11. [UI buttons and command values in this project](#11-ui-buttons-and-command-values-in-this-project)
12. [State keys used by screens](#12-state-keys-used-by-screens)
13. [Common patterns (copy/paste recipes)](#13-common-patterns-copypaste-recipes)
14. [Troubleshooting](#14-troubleshooting)
15. [Full method reference](#15-full-method-reference)

---

## 1) What StepChain is

A StepChain script is a loop that runs many times per second.

- Each loop checks the current step (`ctx.step`)
- You perform logic for that step
- You jump to next step with `ctx.goto(...)`

Think of it like a flowchart where each block is a step number.

---

## 2) How a script runs (simple mental model)

Use this structure:

```python
def chain(ctx):
    STEP_IDLE = 0
    STEP_WORK = 10

    if ctx.step == STEP_IDLE:
        # wait for something
        return

    if ctx.step == STEP_WORK:
        # do something
        return
```

### Important rule

Do **not block forever** in one call. Prefer:

- check input
- save progress in `ctx.vars`
- return
- continue next cycle

This keeps UI responsive.

---

## 3) Your `ctx` object (the thing you use)

`ctx` is your public API object (`PublicStepChainContext`).

### Useful properties

- `ctx.chain_id` - unique id of this chain instance
- `ctx.step` - current step number
- `ctx.step_desc` - text shown to operator
- `ctx.cycle_count` - loop count
- `ctx.paused` - paused state
- `ctx.error_flag` / `ctx.error_message` - error status

### Namespaces available on `ctx`

- `ctx.values` - read mirrored data/state
- `ctx.vars` - your script memory
- `ctx.ui` - UI state, notifications, popups, command reads
- `ctx.flow` - goto/fail/pause/resume
- `ctx.timing` - timeout helpers
- `ctx.workers` (alias: `ctx.worker`) - worker IO
- `ctx.view` - view-specific shortcuts

---

## 4) How to build steps safely

## Pattern A: wait with timeout (recommended)

```python
def chain(ctx):
    STEP_START = 0
    STEP_WAIT = 10

    if ctx.step == STEP_START:
        ctx.set_step_desc("Starting")
        ctx.goto(STEP_WAIT, "Waiting 2 seconds")
        return

    if ctx.step == STEP_WAIT:
        if ctx.wait(2.0, STEP_START, desc="Loop again"):
            return
```

## Pattern B: manual timeout

```python
if ctx.timing.timeout(5.0):
    ctx.flow.goto(100, desc="Timeout reached")
```

---

## 5) Read and write variables

You have **two common variable places**:

1. `ctx.vars` → private script memory
2. `ctx.ui.set_state(...)` / AppState → shared UI state

## 5.1 Script memory (`ctx.vars`)

```python
# save
ctx.vars.set("retry_count", 0)

# read
retries = ctx.vars.get("retry_count", 0)

# increment
ctx.vars.inc("retry_count", 1)

# remove
ctx.vars.delete("retry_count")
```

Use this for internal flags like `waiting_for_scan`, `last_cmd`, counters, etc.

## 5.2 Read mirrored values (`ctx.values`)

```python
# latest payload by key name found in worker data
scan = ctx.values.by_key("scanner.serial", default="")

# app state value
part = ctx.values.state("part_number", "")

# all state
all_state = ctx.values.state_all()
```

---

## 6) Update the UI

## 6.1 Quick notification toast

```python
ctx.notify_info("Ready")
ctx.notify_warning("Check container")
ctx.notify_negative("Print failed")
ctx.notify_positive("Container created")
```

## 6.2 Write UI/App state keys

```python
ctx.set_state("work_instruction", "Scan serial number")
ctx.set_state("work_feedback", "Waiting for scanner")
ctx.set_state("work_instruction_state", 4)  # info
```

Batch write:

```python
ctx.set_state_many(
    container_number="BOX-001",
    part_number="PN-123",
    current_container_qty=5,
    max_container_qty=20,
)
```

## 6.3 Color/status helper (`ctx.ui.show`)

```python
ctx.ui.show(
    instruction="Place part in fixture",
    feedback="Operator action required",
    instruction_state="info",   # also: ok/warn/error/idle or 1..5
    feedback_state="warn",
)
```

---

## 7) React to UI buttons

Operator pages publish commands (like `start`, `refresh`, `remove`) to the bus.

Read them with:

```python
cmd = ctx.ui.consume_command("packaging.cmd")
if cmd == "refresh":
    ctx.notify_info("Refreshing data")
```

Or using view helper:

```python
cmd = ctx.view.packaging.wait_cmd(expected=["new", "remove", "refresh"])
if cmd == "new":
    ctx.goto(100, "Creating new container")
```

### Why commands are not repeated every cycle

The API deduplicates by `event_id`, so one button click is consumed once.

---

## 8) Show popups (confirm/input/message)

All popup calls are **non-blocking**.

- First call: sends popup request, returns `None`
- While waiting: returns `None`
- After operator action: returns result

## 8.1 Confirm popup

```python
def chain(ctx):
    STEP_CONFIRM = 10

    if ctx.step == STEP_CONFIRM:
        res = ctx.ui.popup_confirm(
            key="confirm_remove",
            title="Confirm remove",
            message="Remove current container?",
            ok_text="Yes",
            cancel_text="No",
        )

        if res is None:
            return  # still waiting

        if res:
            ctx.notify_positive("Removing...")
            ctx.goto(20)
        else:
            ctx.notify_info("Cancelled")
            ctx.goto(0)
```

## 8.2 Text input popup

```python
res = ctx.ui.popup_input_text(
    key="ask_serial",
    title="Serial",
    message="Please scan serial",
    placeholder="SN...",
)
if res is None:
    return
if not res.get("ok", False):
    ctx.goto(0)
    return
serial = str(res.get("value") or "")
```

## 8.3 Message popup with custom buttons

```python
res = ctx.ui.popup_message(
    key="retry_popup",
    title="Printer error",
    message="Printer did not respond",
    status="error",
    buttons=[
        {"label": "Retry", "value": "retry", "color": "primary"},
        {"label": "Abort", "value": "abort", "color": "negative"},
    ],
)
if res is None:
    return
clicked = res.get("clicked")
if clicked == "retry":
    ctx.goto(50)
else:
    ctx.error("Aborted by operator")
```

---

## 9) Talk to workers (TCP, PLC, OPCUA, REST, iTAC, COM)

Use `ctx.workers` (or shortcuts on `ctx`).

## 9.1 TCP example

```python
ctx.workers.tcp_send("scanner01", "HELLO\n")
reply = ctx.workers.tcp_wait("scanner01", timeout_s=1.5, default="")
if not reply:
    ctx.notify_warning("No TCP reply")
```

## 9.2 TwinCAT PLC example

```python
ctx.workers.plc_write("plc01", "MAIN.Start", True)
running = ctx.workers.plc_wait_value("plc01", "MAIN.Running", timeout_s=2.0, default=False)
if not running:
    ctx.error("PLC did not start")
```

## 9.3 OPC UA example

```python
read_res = ctx.workers.opcua_read("opc_server_1", alias="MachineState", timeout_s=2.0)
if read_res.get("error"):
    ctx.notify_negative(f"OPCUA read error: {read_res.get('error')}")
else:
    value = read_res.get("value")
    ctx.log_info(f"MachineState={value}")
```

## 9.4 REST example

```python
res = ctx.rest_post_json(
    endpoint="mes_api",
    path="/containers/create",
    body={"part_number": "PN-123", "qty": 20},
    timeout_s=5.0,
)
if res.get("error"):
    ctx.notify_negative("MES create failed")
    return
ctx.notify_positive("MES create OK")
```

## 9.5 iTAC login flow example

```python
res = ctx.itac_login_user(
    "itac_conn_1",
    station_number="1001",
    username="operator1",
    password="operator1",
)
if not res.get("ok"):
    ctx.error(f"iTAC login failed: {res.get('error')}")
```

## 9.6 COM device example

```python
ctx.send_com("scale01", "READ", add_delimiter=True)
line = ctx.com_wait("scale01", timeout_s=2.0, default="")
if line:
    ctx.log_info(f"Scale reply: {line}")
```

---

## 10) View helpers (`ctx.view.*`)

These helpers write/read the exact state keys each page uses.

## 10.1 Packaging

```python
ctx.view.packaging.set_form(
    container_number="BOX-101",
    part_number="PN-ABC",
    description="Widget",
    current_qty=2,
    max_qty=10,
    last_serial_number="SN0002",
)
```

## 10.2 Packaging NOX

```python
ctx.view.packaging_nox.set_totals(good=120, bad=3)
ctx.view.packaging_nox.show_instruction(
    instruction="Insert part",
    feedback="Vision check pending",
    instruction_state="info",
    feedback_state="warn",
)
```

## 10.3 Container management

```python
ctx.view.container_management.set_tables(
    container_rows=[{"material_bin": "B-1", "part_number": "PN1", "current_qty": 10}],
    serial_rows=[{"serial_number": "SN1", "created_on": "2026-01-01"}],
)
```

---

## 11) UI buttons and command values in this project

## 11.1 Packaging page (`packaging.cmd`)

Buttons send command values:

- `remove`
- `print`
- `new`
- `refresh`
- `reset`

## 11.2 Packaging NOX page (`packaging.cmd`)

Buttons send command values:

- `reset_counters`
- `start`
- `stop`
- `reset`
- `refresh`

## 11.3 Container management (`container_management.cmd`)

Buttons send command values:

- `search_container`
- `search_serial`
- `activate`
- `search`
- `refresh`
- `remove_all`
- `remove_selected_serial` (includes selected row data)

---

## 12) State keys used by screens

## Packaging / Packaging NOX

Common keys you usually update:

- `container_number`
- `part_number`
- `description`
- `current_container_qty`
- `max_container_qty`
- `last_serial_number`
- `part_good`
- `part_bad`
- `work_instruction`
- `work_feedback`
- `work_instruction_state`
- `work_feedback_state`

## Container management

- `container_mgmt_search_query`
- `container_mgmt_container_rows`
- `container_mgmt_container_selected`
- `container_mgmt_serial_rows`
- `container_mgmt_active_container`

---

## 13) Common patterns (copy/paste recipes)

## Recipe A: Start/Stop buttons

```python
def chain(ctx):
    STEP_IDLE = 0
    STEP_RUNNING = 10

    if ctx.step == STEP_IDLE:
        cmd = ctx.view.packaging_nox.consume_cmd()
        if cmd == "start":
            ctx.notify_positive("Started")
            ctx.goto(STEP_RUNNING, "Running")
        return

    if ctx.step == STEP_RUNNING:
        cmd = ctx.view.packaging_nox.consume_cmd()
        if cmd == "stop":
            ctx.notify_warning("Stopped")
            ctx.goto(STEP_IDLE, "Idle")
        return
```

## Recipe B: Refresh command + REST fetch

```python
if ctx.step == 0:
    cmd = ctx.ui.consume_command("packaging.cmd")
    if cmd == "refresh":
        ctx.goto(100, "Loading from MES")
    return

if ctx.step == 100:
    res = ctx.rest_get("mes_api", "/pack/info", params={"line": "L1"}, timeout_s=3.0)
    if res.get("error"):
        ctx.notify_negative("Refresh failed")
        ctx.goto(0)
        return

    data = res.get("data", {}) if isinstance(res.get("data"), dict) else {}
    ctx.set_state_many(
        part_number=data.get("part_number", ""),
        description=data.get("description", ""),
    )
    ctx.notify_positive("Refresh done")
    ctx.goto(0)
```

## Recipe C: Wait popup while long action is running

```python
if ctx.step == 20:
    ctx.ui.popup_wait_open(key="view.wait.packaging", title="Please wait", message="Printing label...")
    ctx.goto(21)
    return

if ctx.step == 21:
    # do work...
    done = True
    if done:
        ctx.ui.popup_wait_close(key="view.wait.packaging")
        ctx.goto(0)
```

---

## 14) Troubleshooting

### Problem: button click does nothing

Checklist:

1. Are you reading the correct command key? (`packaging.cmd` or `container_management.cmd`)
2. Are you normalizing command names? (default is lower-case)
3. Are you stuck in another step and never reaching your command-reading step?

### Problem: popup never returns result

Checklist:

1. Keep calling the same popup method every cycle in same step until result is not `None`.
2. Use stable `key` string per popup workflow.
3. Don’t change key each cycle.

### Problem: worker wait always timeout

Checklist:

1. Verify `client_id` / `endpoint` / `connection_id` exactly matches worker config.
2. Increase `timeout_s`.
3. Check worker emits expected key (`message`, PLC variable name, REST/iTAC response key).

### Problem: UI colors not changing

Checklist:

1. Set both text and state keys (`work_instruction` + `work_instruction_state`).
2. Use valid states: `1..5` or names `ok/warn/error/info/idle`.

---

## 15) Full method reference

This section is a compact list for quick lookup.

## `ctx` convenience methods

- `goto(step, desc="")`
- `wait(seconds, next_step, desc="")`
- `notify(message, type_="info")`
- `notify_positive/negative/warning/info(message)`
- `set_state(key, value)`
- `set_state_many(**values)`
- `state/get_state/get_state_var(key, default=None)`
- `update_state(key, value)`
- `error(message)`
- `set_cycle_time(seconds)`
- `set_step_desc(value)`
- `snapshot()`

Worker shortcuts on `ctx`:

- COM: `read_com`, `send_com`, `com_wait`
- TCP: `send_tcp`, `read_tcp`, `wait_tcp`
- PLC: `write_plc`, `read_plc`, `wait_plc`
- REST: `rest_request`, `rest_get`, `rest_post_json`
- iTAC: `itac_station_setting`, `itac_custom_function`, `itac_raw_call`, `itac_login_user`
- Generic: `read_worker_value`

## `ctx.values`

- `source`, `all`, `last`, `get`, `by_key`, `state`, `state_all`, `global_var`, `global_all`

## `ctx.vars`

- `get`, `set`, `has`, `pop`, `delete`, `clear`, `inc`, `as_dict`

## `ctx.flow`

- `goto`, `fail`, `clear_error`, `pause`, `resume`

## `ctx.timing`

- `set_cycle_time`, `step_seconds`, `timeout`

## `ctx.ui`

- UI state: `set`, `merge`, `clear`
- command/payload: `consume_command`, `consume_payload`, `consume_view_cmd`, `subscribe_view_cmd`
- app state: `set_state`, `set_state_many`, `inc_state_int`, `show`
- notify/event: `notify`, `event`
- popups: `popup_confirm`, `popup_message`, `popup_input_text`, `popup_input_number`, `popup_choose`, `popup_close`, `popup_clear`, `popup_close_all`
- wait popup: `popup_wait_open`, `popup_wait_close`

## `ctx.workers`

- generic: `get`, `latest`
- tcp: `tcp_send`, `tcp_connect`, `tcp_disconnect`, `tcp_message`, `tcp_wait`
- plc: `plc_write`, `plc_value`, `plc_wait_value`
- opcua: `opcua_value`, `opcua_wait_value`, `opcua_read`, `opcua_write`
- rest: `rest_request`, `rest_get`, `rest_post_json`
- itac: `itac_station_setting`, `itac_custom_function`, `itac_raw_call`, `itac_login_user`, `itac_expect_ok`
- com: `com_last`, `com_wait`, `com_send`

## `ctx.view`

- `packaging`: field setters + `set_form` + shared command helpers
- `packaging_nox`: packaging setters + `set_totals` + `show_instruction`
- `container_management`: table/query setters + `set_tables`

---

## Bonus: Minimal starter template

```python
def chain(ctx):
    STEP_IDLE = 0
    STEP_WAIT_SCAN = 10

    if ctx.step == STEP_IDLE:
        ctx.set_state("work_instruction", "Press New to start")
        cmd = ctx.view.packaging.wait_cmd(expected=["new", "refresh"])
        if cmd == "new":
            ctx.set_state("work_feedback", "Waiting for serial")
            ctx.goto(STEP_WAIT_SCAN)
        elif cmd == "refresh":
            ctx.notify_info("Refresh requested")
        return

    if ctx.step == STEP_WAIT_SCAN:
        serial = ctx.values.by_key("scanner.serial", "")
        if not serial:
            return

        ctx.set_state_many(
            last_serial_number=serial,
            work_feedback=f"Scanned {serial}",
            work_feedback_state="ok",
        )
        ctx.goto(STEP_IDLE)
```

