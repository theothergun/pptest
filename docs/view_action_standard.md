# View Action Standard

Use a consistent action payload for route/view button events.

## Action envelope

```json
{
  "view": "packaging",
  "name": "refresh",
  "event": "click"
}
```

When published via `publish_standard_view_action(...)`, handlers receive:

- `action.view`
- `action.name`
- `action.event`

## Implementation files

- Action helpers: `services/ui/view_action.py`
- Registry enums and validation: `services/ui/registry.py`
- Example page: `pages/operator/view_action_example.py`

## Usage example

```python
from services.ui.view_action import publish_standard_view_action

publish_standard_view_action(
    worker_bus=ctx.worker_bus,
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

## Recommendations

- Keep action names stable (`start`, `stop`, `reset`, `refresh`, ...).
- Prefer semantic names over page-specific ids.
- Use `event` for intent (`click`, `submit`, `change`, ...).
