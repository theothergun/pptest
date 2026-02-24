from __future__ import annotations

import time
from services.automation_runtime.context import PublicAutomationContext

WAIT_MODAL_KEY = "view.wait.packaging_nox"

def main(ctx: PublicAutomationContext):
    """
    This script listens on serval events, and when they appear it updates
    the container informations on Packaging NOX view
    expected itac output

    {'result': {
        'return_value': 0,
        'outArgs': ['SM080000000S', '3606214205', 'Sample-KV2-EU-673mm-NOS557 P', '14.0', '80.0'],
        'customErrorString': ''},
        '_meta': {'connection_id': 'itac_mk',
        'request_id': 'e0aa4f593fd04cde89f063892bc04c26',
        'key': 'itac.itac_mk.custom_function.e0aa4f593fd04cde89f063892bc04c26'}}

    """
    ctx.set_cycle_time(0.1)
    step = ctx.step
    if step == 0:
        container= ctx.get_state("container_number")
        if not container:
            ctx.goto(10)
            return
        update_container = ctx.get_state("update_container")
        if update_container:
            ctx.goto(10)
            return
        ctx.goto(0)
    elif step == 10:
        station = ctx.global_var("station")
        pack_info_result = ctx.itac_custom_function(connection_id="itac_mk", method_name="NOXPackaging.getPackInfo",  in_args= [station, "true"]  )
        if  "error" in pack_info_result: # call has timed out, possible network connection
            ctx.goto(900)
            return
        ctx.data["pack_info_result"] = pack_info_result
        pack_info_result = pack_info_result["result"]
        if pack_info_result["return_value"] == -421:
            ctx.data["pack_info_result"] = pack_info_result
            ctx.goto(20)
        if pack_info_result["return_value"] == 0:
            ctx.ui.popup_close('view.wait.packaging_nox')
            ctx.goto(30)

    elif step == 20:
        ctx.set_state("container_number", "-")
        ctx.set_state("current_container_qty", "0")
        ctx.set_state("max_container_qty", "0")
        ctx.set_state("part_number", "-")
        ctx.set_state("description", "-")
        ctx.set_state("update_container", False)
        ctx.ui.popup_confirm(key="confirm_retry", message="Please scan a Packaging Box",
                                        ok_text="retry?")
        ctx.goto(21)
    elif step == 21:

        result_popup = ctx.ui.popup_confirm(key="confirm_retry", message="Please scan a Packaging Box",
                                            ok_text="retry?")
        if result_popup:
            ctx.ui.popup_wait_open(key="view.wait.packaging_nox")
            ctx.goto(10)
        else:
            ctx.ui.popup_close('view.wait.packaging_nox')
    elif step == 30:
        result = ctx.data.get("pack_info_result")
        result = result["result"]["outArgs"]
        ctx.set_state("container_number", result[0])
        ctx.set_state("part_number", result[1])
        ctx.set_state("description", result[2])
        ctx.set_state("current_container_qty", int(result[3].replace(".0","")))
        ctx.set_state("max_container_qty",  int(result[4].replace(".0","")))
        ctx.set_state("update_container", False)
        ctx.ui.popup_wait_close(key="update_container")
        ctx.goto(0)

    elif step == 900: #connection error
        result_popup = ctx.ui.popup_confirm(key="confirm_retry", message="Connection to ITAC lost", ok_text="retry?")
        if result_popup:
            ctx.goto(10)

# Export
main = main
