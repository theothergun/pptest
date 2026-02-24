from __future__ import annotations

import time
from services.workers.stepchain.context import PublicStepChainContext


def main(ctx: PublicStepChainContext):
    """
    Example script for the new packaging view (form with buttons).
    Uses ctx.view.packaging (alias: ctx.view.packagin).
    """
    ctx.set_cycle_time(0.1)

    step = ctx.step
    msg = ctx.ui.consume_view_cmd(
        "view.cmd.packaging_nox",
        commands=["start", "stop", "refresh", "reset"],
    )
    step = ctx.worker.plc_value("packaging_station" , "MAIN.module.zenonVisu.Stop")
    action =  (msg or {}).get("action", {}) if msg else {}
    cmd = str(action.get("name") or "")

    if cmd == "start":
        ctx.ui.popup_wait_close(key="view.wait.packaging_nox")
        ctx.view.set_button_enabled(button_key="start",enabled=False)
        ctx.view.set_button_enabled(button_key="stop", enabled=True)
        ctx.worker.plc_write("packaging_station", "MAIN.module.zenonVisu.Stop", False)
    if cmd == "stop":
        ctx.ui.popup_wait_close(key="view.wait.packaging_nox")
        ctx.view.set_button_enabled(button_key="stop",enabled=False)
        ctx.view.set_button_enabled(button_key="start", enabled=True)
        ctx.worker.plc_write("packaging_station", "MAIN.module.zenonVisu.Stop", True)
    if cmd == "refresh":
        ctx.set_state("update_container", True)
    if cmd == "reset":
        ctx.worker.plc_write("packaging_station", "MAIN.module.zenonVisu.Reset", True)
        wait = ctx.wait(seconds=3,next_step=2)
        ctx.set_state("update_container", True)

    dummy_enabled = ctx.get_state("dummy_is_enabled")
    enabled = ctx.worker.plc_value("packaging_station", "Dummy_enabled")
    if enabled != dummy_enabled:
        ctx.worker.plc_write("packaging_station", "Dummy_enabled", dummy_enabled)

    step_text = ctx.worker.plc_value("packaging_station", "StepText")
    ctx.ui.set_state("work_instruction",step_text)

    error_text = ctx.worker.plc_value("packaging_station", "ErrorText")
    ctx.ui.set_state("work_feedback",error_text)

    if step == 0:
        pass
# Export
main = main
