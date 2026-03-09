# Building Views

This project now has a small page toolkit to make new views faster to build.

## Quick Start

Generate a new page and matching script template:

```bash
python scripts/create_page.py --name station_overview
```

This creates:

- `pages/station_overview.py`
- `scripts/generated/station_overview.py`

Then register the route in one of two ways:

1. Add a built-in page definition in `pages/builtin_pages.py`
2. Or add a config entry in `ui.navigation.custom_routes`

## Recommended Page Structure

A normal page should only need:

- `build_page(...)` from `layout/page_scaffold.py`
- `section_card(...)` and `kpi_tile(...)` from `layout/page_blocks.py`
- `ScriptButtonSpec` and `script_action_row(...)` from `layout/script_controls.py`

Example:

```python
from nicegui import ui

from layout.context import PageContext
from layout.page_blocks import section_card, kpi_tile
from layout.page_scaffold import build_page
from layout.script_controls import ScriptButtonSpec, script_action_row
from services.worker_commands import ScriptWorkerCommands as ScriptCommands


SCRIPT_NAME = "generated/station_overview"


def render(container: ui.element, ctx: PageContext) -> None:
    def build_content(_parent: ui.element) -> None:
        with ui.column().classes("w-full gap-4"):
            with section_card("Station Overview", "Short operator explanation", icon="dashboard"):
                with ui.row().classes("w-full flex-wrap gap-4"):
                    kpi_tile("Status", "Ready", hint="Bind real values later", icon="check_circle")
                    kpi_tile("Order", "4711", hint="Example value", icon="assignment")

            with section_card("Actions", "Buttons bound to the runtime", icon="smart_display"):
                script_action_row(
                    ctx,
                    [
                        ScriptButtonSpec(label="Start", command=ScriptCommands.START_CHAIN, script_name=SCRIPT_NAME, color="positive", icon="play_arrow"),
                        ScriptButtonSpec(label="Stop", command=ScriptCommands.STOP_CHAIN, script_name=SCRIPT_NAME, color="negative", icon="stop", outline=True),
                    ],
                )

    build_page(ctx, container, title="Station Overview", content=build_content, show_action_bar=False)
```

## Page Registration

### Built-in Python registration

Register directly in `pages/builtin_pages.py`:

```python
from layout.page_registry import PageDefinition, register_pages
from pages.station_overview import render as render_station_overview

register_pages(
    PageDefinition(
        key="station_overview",
        label="Station Overview",
        icon="dashboard",
        render=render_station_overview,
    ),
)
```

### Config registration

Add a custom route entry:

```json
{
  "key": "station_overview",
  "label": "Station Overview",
  "icon": "dashboard",
  "path": "station_overview.py"
}
```

## Reusable Building Blocks

### `section_card(...)`

Use for every major page section. It gives you a consistent title, subtitle, and icon layout.

### `kpi_tile(...)`

Use for small operational counters or current values.

### `status_badge(...)`

Use for compact status chips such as `ok`, `warning`, or `error`.

## Script Buttons

### One button

```python
from layout.script_controls import ScriptButtonSpec, script_action_button
from services.worker_commands import ScriptWorkerCommands as ScriptCommands

script_action_button(
    ctx,
    ScriptButtonSpec(
        label="Reload Demo",
        command=ScriptCommands.RELOAD_SCRIPT,
        script_name="examples/page_designer_demo",
        icon="refresh",
        color="info",
        outline=True,
    ),
)
```

### A row of buttons

```python
script_action_row(ctx, [
    ScriptButtonSpec(label="Start", command=ScriptCommands.START_CHAIN, script_name="generated/station_overview"),
    ScriptButtonSpec(label="Stop", command=ScriptCommands.STOP_CHAIN, script_name="generated/station_overview"),
])
```

### Buttons from script metadata

If the script exposes `SCRIPT_META`, you can render its declared buttons directly:

```python
from layout.script_controls import script_metadata_buttons

script_metadata_buttons(ctx, "examples/page_designer_demo")
```

## Playground

Use the built-in `Page Designer` route to preview:

- page blocks
- script-bound buttons
- metadata-driven buttons
- the current recommended structure

That page is intended as a developer sandbox before you build a production view.
