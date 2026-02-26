# Automation Runtime Programmer's Manual

> Historical filename note: this file path still contains `stepchain` for backward compatibility, but the current engine name is **Automation Runtime**.

This manual documents the current scripting runtime contract in this repository.

## 1) Runtime architecture

A script runs with a public context object `ctx` of type `PublicAutomationContext`.

Core components:

- Runtime service: `services/automation_runtime/runtime.py`
- Internal chain context: `services/automation_runtime/context.py` (`AutomationContext`)
- Public script context: `PublicAutomationContext`
- Script loader: `services/automation_runtime/loader.py`

Script files are loaded from `scripts/`.

## 2) Script entry points

Preferred entry point:

- `main(ctx)`

Supported compatibility names (loader accepts these):

- `chain`
- `step_chain`
- `stepchain`
- `<filename>`
- `<filename>_chain`

## 3) Public context overview

Common properties:

- `ctx.chain_id`
- `ctx.step`
- `ctx.cycle_count`
- `ctx.error_flag`
- `ctx.error_message`
- `ctx.step_desc`

Common helpers:

- `ctx.goto(step, desc="")`
- `ctx.wait(seconds, next_step, desc="")`
- `ctx.set_cycle_time(seconds)`
- `ctx.notify_*()`
- `ctx.set_state(...)`
- `ctx.values.state(...)`

## 4) Namespaced APIs on `ctx`

- `ctx.values` → read mirrored bus/app values
- `ctx.vars` → persistent script-local memory
- `ctx.ui` → UI state + popups + view command consumption
- `ctx.flow` → goto/fail/pause/resume
- `ctx.timing` → timeout and cycle-time helpers
- `ctx.workers` / `ctx.worker` → typed worker integrations (TCP, COM, TwinCAT, OPC UA, REST, iTAC)

## 5) App state interaction

Write:

```python
ctx.set_state("training_status", "Ready")
ctx.set_state_many(training_scan_count=0, training_last_scan="")
```

Read:

```python
status = ctx.values.state("training_status", "")
```

## 6) Popup/confirm interaction (non-blocking)

Popup methods return `None` while waiting for operator response.

```python
ans = ctx.ui.popup_confirm("my_confirm", "Continue?")
if ans is None:
    return
if ans:
    ...
```

## 7) TCP input pattern

Read latest TCP message from a configured client:

```python
scan = ctx.read_tcp("training_scanner", default=None, decode=True)
```

Training page can simulate the same bus message path by publishing `WorkerTopics.VALUE_CHANGED` with key `message` for source `tcp_client`.

## 8) Logging from scripts

Use context logging helpers:

- `ctx.log_info(...)`
- `ctx.log_warning(...)`
- `ctx.log_error(...)`
- `ctx.log_debug(...)`
- `ctx.log_success(...)`

## 9) Script discovery and Script Lab

Scripts are discovered recursively under `scripts/` (excluding underscored files/folders).

Scripts Lab page:

- `pages/settings/scripts_lab.py`

Use it to:

- list scripts,
- start/stop chains,
- reload scripts,
- inspect chain logs/state.

## 10) Config hooks

Config sets are loaded from:

- `config/sets/<set_name>.json`

Script worker section:

```json
{
  "workers": {
    "configs": {
      "script_worker": {
        "auto_start_chains": [
          {"script_name": "path/to/script", "instance_id": "default"}
        ]
      }
    }
  }
}
```

Use empty `auto_start_chains` if scripts should be started manually from Scripts Lab.
