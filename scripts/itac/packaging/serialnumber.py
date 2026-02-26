from __future__ import annotations
from services.script_api import PublicAutomationContext, UiActionName, ViewName, StateKeys

import time


def main(ctx: PublicAutomationContext):
    """
    Example script using generic automation APIs.
    """
    ctx.set_cycle_time(1)
    msg = ctx.ui.consume_view_cmd("view.cmd.%s" % ViewName.PACKAGING_NOX.value, command=UiActionName.RESET.value)

    return
    step = ctx.step
    if step == 0:
        curr_qty =  ctx.get_state(StateKeys.current_container_qty ,0)
        max_qty =    ctx.get_state(StateKeys.max_container_qty ,0)
        if curr_qty >= max_qty:
            ctx.ui.show(feedback="Waiting for new Box", feedback_state="warning", instruction_state="info",
                        instruction="Please scan a new Boxlabel...")
            return

        ctx.ui.show(feedback="waiting for rail in...",feedback_state="warning",instruction_state="info",instruction="Please scan a part...")
        from datetime import datetime
        ctx.set_state(StateKeys.current_serialnumber,datetime.now())
        ctx.goto(10)
    elif step == 10:
        ctx.ui.show(feedback="Checking Serialnumber", feedback_state="warning", instruction_state="info",
                    instruction="Please wait")

        ctx.goto(20)
    elif step == 20:
        ctx.ui.show(feedback="Checking Material Setup", feedback_state="warning", instruction_state="info",
                    instruction="Please wait")
        ctx.goto(30)
    elif step == 30:
        ctx.ui.show(feedback="Wait for mounting locking..", feedback_state="warning", instruction_state="info",
                    instruction="Please mount locking..")
        ctx.goto(40)
    elif step == 40:
        ctx.ui.show(feedback="Book Part", feedback_state="warning", instruction_state="info",
                    instruction="Please wait")
        ctx.goto(50)
    elif step == 50:
        ctx.ui.show(feedback="Success..", feedback_state="ok", instruction_state="info",
                    instruction="Please wait")
        current =  ctx.get_state(StateKeys.current_container_qty ,0)
        ctx.set_state(StateKeys.current_container_qty , current+1 )

        current = ctx.get_state(StateKeys.part_good, 0)
        ctx.set_state(StateKeys.part_good, current + 1)
        ctx.goto(0)
# Export
main = main
