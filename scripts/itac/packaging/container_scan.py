from __future__ import annotations
import time
from services.script_api import PublicAutomationContext, StateKeys
from services.automation_helpers.itac import result_code, show_itac_error

from services.script_metadata import default_script_meta

SCRIPT_META = default_script_meta(__file__)

ITAC_SERVER_ID = "itac_mk"
SCANNER_ID = "Cognex-Pack-Scanner"
FULL_CONTAINER_POPUP_KEY = "packaging_container_full_info"
FULL_CONTAINER_MESSAGE = "Container is full. Please scan a new container."


def _is_full_container_error(res: dict, result_code: int) -> bool:
    if int(result_code) == -421:
        return True
    result = res.get("result", {}) if isinstance(res, dict) else {}
    custom_error = str(result.get("customErrorString") or "")
    custom_error_lower = custom_error.lower()
    return ("container" in custom_error_lower and "full" in custom_error_lower) or ("lot" in custom_error_lower and "full" in custom_error_lower)


def main(ctx: PublicAutomationContext):
    """
    Packaging NOX container scan, this listen on tcp worker endpoint
    PACK_NOX_SCANNER
    """
    step = ctx.step
    ctx.set_cycle_time(0.01)
    if step == 0:
        res = ctx.workers.tcp_wait(SCANNER_ID, default=None, timeout_s=1)
        ctx.data["scanned_label"] = res

        if res is not None:
            ctx.goto(10)
            return
    elif step == 10:
        box = str(ctx.data.get("scanned_label", "") or "").strip()
        if not box:
            ctx.goto(0)
            return

        station = ctx.global_var("station")
        scan_info_result = ctx.itac_custom_function(
            connection_id=ITAC_SERVER_ID,
            method_name="NOXPackaging.RegisterPackagingContainer",
            in_args=[station, box],
            timeout_s=10.0,
        )
        ctx.data["scan_info_result"] = scan_info_result
        code = result_code(scan_info_result)
        if code != 0:
            ctx.goto(901)
            return
        ctx.ui.popup_message(key="scan_success", message="Packaging container scanned successfully", status="success")
        # Close can race with async UI-open. Keep trying briefly in step 20.
        ctx.set_state(StateKeys.update_container, True)
        ctx.set_cycle_time(3)
        ctx.goto(20)
    elif step == 20:
        ctx.ui.popup_close(key="scan_success", clear=True)
        ctx.set_cycle_time(0.01)
        ctx.goto(0)
    elif step == 901: # call faild with wrong result code
        ctx.set_cycle_time(1)
        scan_info_result = ctx.data.get("scan_info_result", {})
        code = result_code(scan_info_result)
        if _is_full_container_error(scan_info_result, code):
            ctx.ui.popup_message(
                key=FULL_CONTAINER_POPUP_KEY,
                message=FULL_CONTAINER_MESSAGE,
                status="info",
            )
            ctx.set_data("container_full_popup_until", float(time.time()) + 5.0)
            ctx.goto(902)
            return
        show_itac_error(
            ctx,
            connection_id=ITAC_SERVER_ID,
            popup_key="connection_issue",
            result_code_value=code,
            fallback="Packaging container scan failed",
        )
        ctx.set_cycle_time(0.1)
        ctx.goto(0)
    elif step == 902:
        until_ts = float(ctx.get_data("container_full_popup_until", 0.0) or 0.0)
        if time.time() < until_ts:
            return
        ctx.ui.popup_close(key=FULL_CONTAINER_POPUP_KEY, clear=True)
        ctx.set_cycle_time(0.1)
        ctx.goto(0)
# Export
