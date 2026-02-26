from __future__ import annotations

from services.script_api import PublicAutomationContext, ViewName, view_wait_key, StateKeys, t

WAIT_MODAL_KEY = view_wait_key(ViewName.PACKAGING_NOX)
ITAC_SERVER_ID = "itac_mk"


def _result_code(res: dict) -> int:
    result = res.get("result", {}) if isinstance(res, dict) else {}
    try:
        return int(result.get("return_value", -99999))
    except Exception:
        return -99999


def _show_itac_error(ctx: PublicAutomationContext, popup_key: str, result_code: int, fallback: str) -> None:
    error = ctx.itac_get_error_text(ITAC_SERVER_ID, result_code)
    error_text = str(error.get("errorString") or "")
    msg_text = t(fallback, fallback)
    if error_text:
        msg_text = msg_text + "\r\n" + error_text
    ctx.ui.popup_message(popup_key, message=msg_text, status="error")


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
        result_code = _result_code(pack_info_result)
        ctx.set_data("pack_info_result", pack_info_result)

        if result_code == -421:
            ctx.goto(20)
            return
        if result_code == 0:
            ctx.ui.popup_close(WAIT_MODAL_KEY)
            ctx.goto(30)
            return
        if result_code == -99999:
            ctx.goto(900)
            return

        _show_itac_error(ctx, "container_update_get_pack_info_error", result_code, "container_update.get_pack_info_failed")
        ctx.goto(0)
        return

    if step == 20:
        ctx.set_state(StateKeys.container_number, "-")
        ctx.set_state(StateKeys.current_container_qty, "0")
        ctx.set_state(StateKeys.max_container_qty, "0")
        ctx.set_state(StateKeys.part_number, "-")
        ctx.set_state(StateKeys.description, "-")
        ctx.set_state(StateKeys.update_container, False)
        ctx.ui.popup_confirm(
            key="confirm_retry",
            message="Please scan a Packaging Box",
            ok_text="retry?",
        )
        ctx.goto(21)
        return

    if step == 21:
        result_popup = ctx.ui.popup_confirm(
            key="confirm_retry",
            message="Please scan a Packaging Box",
            ok_text="retry?",
        )
        if result_popup is None:
            return
        if result_popup:
            ctx.ui.popup_wait_open(key=WAIT_MODAL_KEY)
            ctx.goto(10)
            return
        ctx.ui.popup_close(WAIT_MODAL_KEY)
        ctx.goto(0)
        return

    if step == 30:
        result = ctx.get_data("pack_info_result", {})
        out_args = ((result or {}).get("result") or {}).get("outArgs") or []
        if not isinstance(out_args, list) or len(out_args) < 5:
            _show_itac_error(ctx, "container_update_invalid_response", -1, "container_update.invalid_response")
            ctx.goto(0)
            return

        ctx.set_state(StateKeys.container_number, out_args[0])
        ctx.set_state(StateKeys.part_number, out_args[1])
        ctx.set_state(StateKeys.description, out_args[2])
        ctx.set_state(StateKeys.current_container_qty, int(str(out_args[3]).replace(".0", "")))
        ctx.set_state(StateKeys.max_container_qty, int(str(out_args[4]).replace(".0", "")))
        ctx.set_state(StateKeys.update_container, False)
        ctx.ui.popup_wait_close(key="update_container")
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
main = main
