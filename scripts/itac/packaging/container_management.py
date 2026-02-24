from __future__ import annotations

from services.automation_runtime.context import PublicAutomationContext
from services.ui.view_cmd import parse_view_cmd_payload
from services.ui.registry import UiActionName


def _extract_cmd_and_payload(raw_payload: dict | None) -> tuple[str, dict]:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    parsed = parse_view_cmd_payload(payload)
    if parsed is not None:
        return str(parsed.action.name or "").lower(), payload
    # Backward-compatible fallback for legacy payloads.
    return str(payload.get("cmd", "") or "").lower(), payload


def main(ctx: PublicAutomationContext):
    ctx.set_cycle_time(0.2)

    step = ctx.step
    if step == 0:
        pass

    if step != 10:
        ctx.goto(10)
        return

    msg = ctx.view.container_management.consume_view_command()
    if msg and str(msg.action.name) == UiActionName.REMOVE_SERIAL.value:
        serial = msg.payload.get("serial")
    print(msg)


# Export
main = main
