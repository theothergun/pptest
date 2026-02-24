from __future__ import annotations

import time
from services.automation_runtime.context import PublicAutomationContext


def main(ctx: PublicAutomationContext):
    """
    Example script for the new packaging view (form with buttons).
    Uses ctx.view.packaging (alias: ctx.view.packagin).
    """
    ctx.set_cycle_time(1)

    step = ctx.step
    print(step)
    if step == 0:
        res = ctx.worker.plc_value("packaging_station", "step")
        if res:
            print(res)
            #ctx.worker.plc_write("packaging_station", "MAIN.module.DMCReader.ProfinetState" , 6)
        ctx.goto(1)
    elif step == 1:
        res = ctx.worker.opcua_value("local", "Watchdog", default="")
        if res:
            print("#" * 20)
            print(res)
            print("#" * 20)

            ctx.worker.plc_write("packaging_station", "step", str(res))
            #ctx.worker.plc_write("packaging_station", "MAIN.module.DMCReader.ProfinetState" , 6)
        ctx.goto(2)
    elif step == 2:
        res = ctx.worker.opcua_read("local", alias="Watchdog", timeout_s=2.0)
        res = res.get("value")
        if res:
            print(res)
            #ctx.worker.plc_write("packaging_station", "MAIN.module.DMCReader.ProfinetState" , 6)
        import datetime
        res = ctx.worker.opcua_write("local",alias="Watchdog",value=str(datetime.datetime.now()) )
        print("**************")
        print (res)

        print("**************")
        ctx.goto(0)


# Export
main = main
