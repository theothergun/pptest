from __future__ import annotations

import time
from services.workers.stepchain.context import PublicStepChainContext


def main(ctx: PublicStepChainContext):
    """
    Example script for the new packaging view (form with buttons).
    Uses ctx.view.packaging (alias: ctx.view.packagin).
    """
    ctx.set_cycle_time(1)

    step = ctx.step
    print(step)
    if step == 0:
        print("*" * 50)
        ctx.view.set_operator_device_panel_visible(True)

        ctx.view.upsert_operator_device_state(
            name="Scanner Proxy",
            status="connection lost",
            state="error",
            connected=True,
            source="test",
        )
        ctx.view.upsert_operator_device_state(
            name="MES Mirror",
            status="OK",
            state="success",  # success|warn|error|info (plus common aliases)
            connected=False,
            source="custom_api",
        )
        curr_qty =  ctx.get_state("current_container_qty" ,0)
        max_qty =    ctx.get_state("max_container_qty" ,0)
        if curr_qty >= max_qty:
            ctx.ui.show(feedback="Waiting for new Box", feedback_state="warning", instruction_state="info",
                        instruction="Please scan a new Boxlabel...")
            return

        ctx.ui.show(feedback="waiting for rail in...",feedback_state="warning",instruction_state="info",instruction="Please scan a part...")
        from datetime import datetime
        ctx.set_state("current_serialnumber",datetime.now())
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
        current =  ctx.get_state("current_container_qty" ,0)
        ctx.set_state("current_container_qty" , current+1 )

        current = ctx.get_state("part_good", 0)
        ctx.set_state("part_good", current + 1)
        ctx.goto(0)
# Export
main = main
