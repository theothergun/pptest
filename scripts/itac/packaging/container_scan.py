from __future__ import annotations

import time
from services.workers.stepchain.context import PublicStepChainContext


def main(ctx: PublicStepChainContext):
    """
    Packaging NOX container scan, this listen on tcp worker endpoint
    PACK_NOX_SCANNER
    """
    ctx.set_cycle_time(0.01)

    step = ctx.step
    print(step)
    if step == 0:
        res = ctx.workers.tcp_wait("PACK_NOX_SCANNER", default=None, timeout_s=1)
        ctx.data["scanned_label"] = res
        if res is not None:
            ctx.goto(10)
    elif step == 10:
        box = ctx.data.get("scanned_label",None)
        station = ctx.global_var("station")
        scan_info_result = ctx.itac_custom_function(connection_id="itac_mk", method_name="NOXPackaging.RegisterPackagingContainer",  in_args= [station, box]  )
        ctx.data["scan_info_result"] = scan_info_result
        if "error" in scan_info_result:
            ctx.goto(900)
            return
        if scan_info_result["result"]["return_value"] != 0:
            ctx.goto(901)
            return
        ctx.ui.popup_clear(key="scan_success")
        ctx.ui.popup_message(key="scan_success", message="Packaging container scanned successfully", status="success")
        ctx.set_cycle_time(1)
        ctx.goto(20)
    elif step == 20:
        ctx.ui.popup_close(key="scan_success")
        ctx.ui.popup_clear(key="scan_success")
        ctx.goto(0)
    elif step == 900: # itac call execption connection?
        ctx.set_cycle_time(1)
        res = ctx.ui.popup_message(key="connection_issue" , message="Itac connection issue - box scan failed", status="error")
        if res:
            ctx.set_cycle_time(0.1)
            ctx.goto(0)
    elif step == 901: # call faild with wrong result code
        ctx.set_cycle_time(1)
        return_value = ctx.data["scan_info_result"]["result"]["return_value"]
        result_text = ctx.data["scan_info_result"]["result"]["customErrorString"]
        result_text = (f"Itac call failed with return code "
                       f"{return_value} \r\n {result_text}")
        res = ctx.ui.popup_message(key="connection_issue", message=result_text, status="error")
        if res:
            ctx.set_cycle_time(0.1)
            ctx.goto(0)
# Export
main = main
