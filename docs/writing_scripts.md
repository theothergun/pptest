# Writing Scripts

Automation scripts run inside `AutomationRuntime` and must expose a `main(ctx)` function.

The recommended import is:

```python
from services.script_api import PublicAutomationContext
```

## Minimal Script

```python
from services.script_api import PublicAutomationContext


def main(ctx: PublicAutomationContext) -> None:
    if ctx.step == 0:
        ctx.set_step_desc("Initialize")
        ctx.goto(10, "Running")
        return

    if ctx.step == 10:
        ctx.set_step_desc("Running")
        if ctx.wait(1.0, 20, "Loop complete"):
            return
        return

    if ctx.step == 20:
        ctx.set_step_desc("Loop complete")
        ctx.goto(10, "Running")
```

## Recommended Pattern

Use step-based logic. Do not block the runtime thread with long sleeps.

```python
from services.script_api import PublicAutomationContext


def main(ctx: PublicAutomationContext) -> None:
    ctx.publish_changes(True)

    if ctx.step == 0:
        ctx.set_step_desc("Prepare")
        ctx.set_state("station_status", "preparing")
        ctx.goto(10, "Wait for scanner")
        return

    if ctx.step == 10:
        ctx.set_step_desc("Wait for scanner")
        code = ctx.read_tcp("PACK_NOX_SCANNER", default="")
        if code:
            ctx.set_data("last_code", code)
            ctx.goto(20, "Process data")
        return

    if ctx.step == 20:
        ctx.set_step_desc("Process data")
        ctx.notify_positive("Code received")
        ctx.goto(10, "Wait for scanner")
```

## `SCRIPT_META`

If a page should render buttons directly from the script, define `SCRIPT_META`.

```python
SCRIPT_META = {
    "title": "Station Overview",
    "description": "Example script for a generated station page.",
    "buttons": [
        {
            "id": "start",
            "label": "Start",
            "icon": "play_arrow",
            "color": "positive",
            "command": "script.start_chain",
        },
        {
            "id": "stop",
            "label": "Stop",
            "icon": "stop",
            "color": "negative",
            "command": "script.stop_chain",
        },
    ],
}
```

Supported button fields:

- `id`
- `label`
- `icon`
- `color`
- `command`
- `script_name` (optional override)
- `instance_id` (optional)
- `payload` (optional dict)
- `outline` (optional bool)

A page can render these with:

```python
from layout.script_controls import script_metadata_buttons

script_metadata_buttons(ctx, "examples/page_designer_demo")
```

## Useful Context APIs

The public context is grouped into focused APIs:

- `ctx.ui`: notifications, modal helpers, UI state writes
- `ctx.flow`: step changes and error handling
- `ctx.timing`: timers and cycle settings
- `ctx.workers`: TCP, PLC, REST, iTAC, COM, OPC UA access
- `ctx.vars`: script-local persistent values
- `ctx.values`: app state and published worker values

Common shortcuts already exist on `ctx`:

- `ctx.goto(step, desc="")`
- `ctx.wait(seconds, next_step, desc="")`
- `ctx.set_state(key, value)`
- `ctx.set_state_many(...)`
- `ctx.set_data(key, value)`
- `ctx.get_data(key, default=None)`
- `ctx.notify_positive(message)`
- `ctx.notify_warning(message)`
- `ctx.read_tcp(client_id)`
- `ctx.write_plc(client_id, name, value)`
- `ctx.rest_get(endpoint, path)`

## Starting Scripts From Views

The new preferred UI binding paths are:

### Declarative button

```python
from layout.script_controls import ScriptButtonSpec, script_action_button
from services.worker_commands import ScriptWorkerCommands as ScriptCommands

script_action_button(
    ctx,
    ScriptButtonSpec(
        label="Start",
        command=ScriptCommands.START_CHAIN,
        script_name="generated/station_overview",
        color="positive",
        icon="play_arrow",
    ),
)
```

### Helper service

```python
from services.script_actions import start_script, stop_script

start_script(ctx, "generated/station_overview")
stop_script(ctx, script_name="generated/station_overview")
```

## Development Workflow

1. Generate a page and script: `python scripts/create_page.py --name station_overview`
2. Adjust the generated script logic in `scripts/generated/station_overview.py`
3. Bind the generated script in the page with `ScriptButtonSpec`
4. Register the route
5. Open `Page Designer` if you want to test blocks or buttons before polishing the final page
