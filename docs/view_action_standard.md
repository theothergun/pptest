# View Action Standard

## Goal
Use the same action envelope on every view so handlers can react uniformly.

## Contract
Every action should include:

```json
{
  "view": "packaging",
  "name": "refresh",
  "event": "click"
}
```

When sent through `publish_standard_view_action(...)`, this is available in the payload as:

- `action.view`
- `action.name`
- `action.event`

## Reusable API
Implemented in `services/ui/view_action.py`:

- `make_action_event(view, name, event="click")`
- `publish_standard_view_action(...)`
- `STANDARD_ACTIONS` (catalog for common operator/VI actions)

## Example Page
Developer example page:

- `pages/operator/view_action_example.py`

It renders all standard buttons with descriptions and shows the emitted payload.

## Usage Pattern

```python
from services.ui.view_action import publish_standard_view_action

publish_standard_view_action(
    worker_bus=ctx.workers.worker_bus,
    view="packaging",
    cmd_key="packaging.cmd",
    name="refresh",
    event="click",
    wait_key="view.wait.packaging",
    open_wait=wait_dialog["open"],
    source_id="packaging",
    extra={"serial": "1234"},
)
```

## Notes
- Keep action names stable (`start`, `stop`, `reset`, `refresh`, etc.).
- Use event to express intent (`click`, `submit`, `toggle`, ...).
- Avoid page-specific button ids like `btn_pass`; use action names like `pass`.
