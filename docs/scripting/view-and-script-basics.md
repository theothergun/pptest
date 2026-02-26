# View and Script Basics

This page explains how **views** and **scripts** work together in the current app.

## What is a View?

A **View** is a NiceGUI page module rendered by the router.

- View files are under `pages/`.
- Example: `pages/training/training_example_view.py`.
- Views build UI (cards, buttons, inputs, tables) and publish state/events.

In this app, routes are configured from config set JSON:

- `ui.navigation.custom_routes[].path` points to a `pages/...` python file.

## What is a Script?

A **Script** is a Python file loaded by `AutomationRuntime` from the `scripts/` directory.

- Scripts are discovered automatically from `scripts/**/*.py`.
- Each script exposes an entry function such as `main(ctx)` (or `chain`, `step_chain`, `stepchain`).
- Script API context type is `PublicAutomationContext`.

## How scripts are loaded

Runtime loader path and behavior:

- Loader: `services/automation_runtime/loader.py`
- Runtime: `services/automation_runtime/runtime.py`
- Script import helper: `services/script_api.py`

Scripts appear in **Settings → Scripts Lab** because the runtime publishes discovered script names.

## How script and UI state interact

### Write UI/app state from script

Scripts write state with:

```python
ctx.set_state("training_status", "Ready")
ctx.set_state_many(training_scan_count=0, training_last_scan="")
```

### Read UI/app state from script

Scripts read with:

```python
mode = ctx.values.state("training_mode", "standard")
```

### Show popup and confirm dialogs

Scripts open non-blocking dialogs:

```python
ans = ctx.ui.popup_confirm("confirm_key", "Proceed?")
if ans is True:
    ...
```

### Handle incoming TCP scan data

Scripts can read TCP client values:

```python
scan = ctx.read_tcp("training_scanner", default=None, decode=True)
```

The training view can also simulate scanner events by publishing `WorkerTopics.VALUE_CHANGED` with:

- `source="tcp_client"`
- `source_id="training_scanner"`
- `key="message"`

This mirrors the same worker-bus path used by real scanner messages.

## Where files live

- Views: `pages/...`
- Scripts: `scripts/...`
- Config sets: `config/sets/...`
- Docs: `docs/...`
