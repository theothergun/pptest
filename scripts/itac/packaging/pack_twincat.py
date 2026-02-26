from __future__ import annotations
from services.script_api import PublicAutomationContext, UiActionName, ViewName, view_wait_key, StateKeys

import time


def main(ctx: PublicAutomationContext):
    """
    Example script for packaging controls using generic ctx.ui/state APIs.
    """
    ctx.set_cycle_time(0.1)

    step = ctx.step
    msg = ctx.ui.consume_view_cmd(
        "view.cmd.%s" % ViewName.PACKAGING_NOX.value,
        commands=[UiActionName.START.value, UiActionName.STOP.value, UiActionName.REFRESH.value, UiActionName.RESET.value],
    )
    step = ctx.worker.plc_value("packaging_station" , "MAIN.module.zenonVisu.Stop")
    action =  (msg or {}).get("action", {}) if msg else {}
    cmd = str(action.get("name") or "")

    if cmd == UiActionName.START.value:
        ctx.ui.popup_wait_close(key=view_wait_key(ViewName.PACKAGING_NOX))
        ctx.ui.set_button_enabled(button_key="start", enabled=False, view_id=ViewName.PACKAGING_NOX.value)
        ctx.ui.set_button_enabled(button_key="stop", enabled=True, view_id=ViewName.PACKAGING_NOX.value)
        ctx.worker.plc_write("packaging_station", "MAIN.module.zenonVisu.Stop", False)
    if cmd == UiActionName.STOP.value:
        ctx.ui.popup_wait_close(key=view_wait_key(ViewName.PACKAGING_NOX))
        ctx.ui.set_button_enabled(button_key="stop", enabled=False, view_id=ViewName.PACKAGING_NOX.value)
        ctx.ui.set_button_enabled(button_key="start", enabled=True, view_id=ViewName.PACKAGING_NOX.value)
        ctx.worker.plc_write("packaging_station", "MAIN.module.zenonVisu.Stop", True)
    if cmd == UiActionName.REFRESH.value:
        ctx.set_state(StateKeys.update_container, True)
    if cmd == UiActionName.RESET.value:
        ctx.worker.plc_write("packaging_station", "MAIN.module.zenonVisu.Reset", True)
        wait = ctx.wait(seconds=3,next_step=2)
        ctx.set_state(StateKeys.update_container, True)

    dummy_enabled = ctx.get_state(StateKeys.dummy_is_enabled)
    enabled = ctx.worker.plc_value("packaging_station", "Dummy_enabled")
    if enabled != dummy_enabled:
        ctx.worker.plc_write("packaging_station", "Dummy_enabled", dummy_enabled)

    step_text = ctx.worker.plc_value("packaging_station", "StepText")
    ctx.ui.set_state(StateKeys.work_instruction,step_text)

    error_text = ctx.worker.plc_value("packaging_station", "ErrorText")
    ctx.ui.set_state(StateKeys.work_feedback,error_text)

    if step == 0:
        pass
# Export
main = main
