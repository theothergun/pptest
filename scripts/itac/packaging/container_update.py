from __future__ import annotations

import time

from services.script_api import PublicAutomationContext, ViewName, view_wait_key, StateKeys
from services.automation_helpers.itac import ITAC_ERROR_FALLBACK_CODE, result_code, show_itac_error

from services.script_metadata import default_script_meta

SCRIPT_META = default_script_meta(__file__)

WAIT_MODAL_KEY = view_wait_key(ViewName.PACKAGING_NOX)
ITAC_SERVER_ID = "itac_mk"
FULL_CONTAINER_POPUP_KEY = "packaging_container_full_info"
FULL_CONTAINER_MESSAGE = "Container is full. Please scan a new container."

def main(ctx: PublicAutomationContext):
    """
    This script listens on several events, and when they appear it updates
    the container information on Packaging NOX view.
    """
    ctx.set_cycle_time(0.1)
    step = ctx.step
    if step == 0:
        container = ctx.get_state(StateKeys.container_number)
        if not container:
            ctx.goto(10)
            return
        update_container = ctx.get_state(StateKeys.update_container)
        if update_container:
            ctx.goto(10)
            return
        ctx.goto(0)


    if step == 10:
        station = ctx.global_var("station")
        pack_info_result = ctx.itac_custom_function(
            connection_id=ITAC_SERVER_ID,
            method_name="NOXPackaging.getPackInfo",
            in_args=[station, "true"],
        )
        result_code_value = result_code(pack_info_result)
        ctx.set_data("pack_info_result", pack_info_result)

        if result_code_value == -421:
            ctx.goto(20)
            return
        if result_code_value == 0:
            ctx.ui.popup_close(WAIT_MODAL_KEY)
            ctx.goto(30)
            return
        if result_code_value == ITAC_ERROR_FALLBACK_CODE:
            ctx.goto(900)
            return

        show_itac_error(
            ctx,
            connection_id=ITAC_SERVER_ID,
            popup_key="container_update_get_pack_info_error",
            result_code_value=result_code_value,
            fallback="container_update.get_pack_info_failed",
        )
        ctx.goto(0)
        return

    if step == 20:
        ctx.set_state(StateKeys.container_number, "-")
        ctx.set_state(StateKeys.current_container_qty, 0)
        ctx.set_state(StateKeys.max_container_qty, 0)
        ctx.set_state(StateKeys.part_number, "-")
        ctx.set_state(StateKeys.description, "-")
        ctx.set_state(StateKeys.update_container, False)
        ctx.ui.popup_wait_close(key=WAIT_MODAL_KEY)
        ctx.ui.popup_message(
            key=FULL_CONTAINER_POPUP_KEY,
            message=FULL_CONTAINER_MESSAGE,
            status="info",
        )
        ctx.set_data("container_full_popup_until", float(time.time()) + 5.0)
        ctx.goto(21)
        return

    if step == 21:
        until_ts = float(ctx.get_data("container_full_popup_until", 0.0) or 0.0)
        if time.time() < until_ts:
            return
        ctx.ui.popup_close(key=FULL_CONTAINER_POPUP_KEY, clear=True)
        ctx.goto(0)
        return

    if step == 30:
        result = ctx.get_data("pack_info_result", {})
        out_args = ((result or {}).get("result") or {}).get("outArgs") or []
        if not isinstance(out_args, list) or len(out_args) < 5:
            show_itac_error(
                ctx,
                connection_id=ITAC_SERVER_ID,
                popup_key="container_update_invalid_response",
                result_code_value=-1,
                fallback="container_update.invalid_response",
            )
            ctx.goto(0)
            return

        ctx.set_state(StateKeys.container_number, out_args[0])
        ctx.set_state(StateKeys.part_number, out_args[1])
        ctx.set_state(StateKeys.description, out_args[2])
        ctx.set_state(StateKeys.current_container_qty, int(str(out_args[3]).replace(".0", "")))
        ctx.set_state(StateKeys.max_container_qty, int(str(out_args[4]).replace(".0", "")))
        ctx.set_state(StateKeys.update_container, False)
        ctx.ui.popup_wait_close(key=WAIT_MODAL_KEY)
        ctx.goto(0)
        return

    if step == 900:  # connection error
        result_popup = ctx.ui.popup_confirm(
            key="confirm_retry",
            message="Connection to ITAC lost",
            ok_text="retry?",
        )
        if result_popup is None:
            return
        if result_popup:
            ctx.goto(10)
            return
        ctx.goto(0)
        return


# Export
