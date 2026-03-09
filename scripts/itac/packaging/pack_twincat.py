from __future__ import annotations
import pages.operator.packaging.packaging_nox
from services.script_api import PublicAutomationContext, UiActionName, ViewName, view_wait_key, StateKeys, t

from services.script_metadata import default_script_meta

SCRIPT_META = default_script_meta(__file__)

ITAC_SERVER_ID = "itac_mk"
PLC_ID = "Beckhoff-PLC"
SCANNER_ID = "Cognex-Scanner"
PLC_STOP_PATHS = (
    "MAIN.module.zenonVisu.Stop",
    "MAIN.module.fbStepChainAutomatic.zenonVisu.Stop",
)
PLC_AUTOMATIC_PATHS = (
    "MAIN.module.zenonVisu.Automatic",
    "MAIN.module.fbStepChainAutomatic.zenonVisu.Automatic",
)
PLC_RESET_PATHS = (
    "MAIN.module.zenonVisu.Reset",
    "MAIN.module.fbStepChainAutomatic.zenonVisu.Reset",
)


def _result_code(res: dict) -> int:
    result = res.get("result", {}) if isinstance(res, dict) else {}
    try:
        return int(result.get("return_value", -99999))
    except Exception:
        return -99999


def _show_itac_error(ctx: PublicAutomationContext, result_code: int, fallback: str) -> str:
    error = ctx.itac_get_error_text(ITAC_SERVER_ID, result_code)
    error_text = str(error.get("errorString") or "")
    msg_text = t(fallback, fallback)
    if error_text:
        msg_text = msg_text + "\r\n" + error_text
    return msg_text


def _set_run_buttons(ctx: PublicAutomationContext, *, running: bool) -> None:
    ctx.ui.set_button_enabled(button_key="start", enabled=not running, view_id=ViewName.PACKAGING_NOX.value)
    ctx.ui.set_button_enabled(button_key="stop", enabled=running, view_id=ViewName.PACKAGING_NOX.value)


def _plc_write_many(ctx: PublicAutomationContext, paths: tuple[str, ...], value: object) -> None:
    for path in paths:
        ctx.worker.plc_write(PLC_ID, path, value)


def _normalize_plc_text(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("@"):
        text = text[1:].strip()
    return text


def _map_plc_error_text(ctx: PublicAutomationContext, text: str) -> str:
    """
    PLC sometimes reports a raw MES result code (e.g. "@-110" or "202") as ErrorText.
    When we detect this short numeric payload and it's non-zero, replace it with
    the actual iTAC error text.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    # Normalize leading "@", but keep the original for fallback.
    normalized = raw[1:].strip() if raw.startswith("@") else raw
    # Only attempt override on short, numeric-only payloads.
    if len(normalized) <= 8:
        try:
            code = int(normalized)
        except Exception:
            code = 0
        if code != 0:
            error = ctx.itac_get_error_text(ITAC_SERVER_ID, code)
            error_text = str(error.get("errorString") or "").strip()
            if error_text:
                return t("packaging.mes_error_code_text", "{code}: {text}", code=code, text=error_text)
    return raw


def _map_plc_error_text_cached(ctx: PublicAutomationContext, text: str) -> str:
    """
    Avoid calling iTAC error lookup on every cycle by caching mapped results
    per distinct PLC error text value.
    """
    if ctx.set_data_if_changed("twincat_error_text_raw", text, ""):
        mapped = _map_plc_error_text(ctx, text)
        ctx.set_data("twincat_error_text_mapped", mapped)
        return mapped
    return str(ctx.get_data("twincat_error_text_mapped", text) or "")


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return int(default)


def _device_feedback_error(ctx: PublicAutomationContext) -> str:
    plc_connected = ctx.device_is_connected("twincat", source_id=PLC_ID)
    scanner_connected = ctx.device_is_connected("tcp_client", source_id=SCANNER_ID)
    if not plc_connected:
        return t("device.plc_beckhoff_disconnected", "Beckhoff is not connected")
    if not scanner_connected:
        return t("device.packaging.package_scanner_disconnected", "Packaging Scanner is not connected")
    return ""


def _instruction_state_for_text(text: str, *, has_feedback_error: bool, container_full_gate: bool) -> int:
    if text == "Please insert Part":
        return 4

    if container_full_gate:
        return 2  # warning
    if has_feedback_error:
        return 2  # warning
    if text:
        return 4  # info
    return 5  # idle


def _feedback_state_for_text(text: str) -> int:
    if text == "Good part":
        return 1
    if text:
        return 3  # error

    return 5  # idle


def _clear_packaging_states(ctx: PublicAutomationContext) -> None:
    ctx.set_state(StateKeys.container_number, "-")
    ctx.set_state(StateKeys.part_number, "-")
    ctx.set_state(StateKeys.description, "-")
    ctx.set_state(StateKeys.current_container_qty, 0)
    ctx.set_state(StateKeys.max_container_qty, 0)
    ctx.set_state(StateKeys.last_serial_number, "-")
    ctx.set_state(StateKeys.current_serialnumber, "-")


def _plc_stop_active(ctx: PublicAutomationContext) -> bool:
    # Prefer subscribed alias; fallback to direct symbol reads.
    alias_stop = ctx.worker.plc_value(PLC_ID, "stop", None)
    if alias_stop is not None:
        return bool(alias_stop)
    for path in PLC_STOP_PATHS:
        value = ctx.worker.plc_value(PLC_ID, path, None)
        if value is not None:
            return bool(value)
    return False


def _handle_device_status(ctx: PublicAutomationContext) -> None:
    plc_connected = ctx.device_is_connected("twincat", source_id=PLC_ID)
    scanner_connected = ctx.device_is_connected("tcp_client", source_id=SCANNER_ID)

    if ctx.set_data_if_changed("hand_scanner", scanner_connected):
        if not scanner_connected:
            ctx.ui.show(
                feedback=t("device.packaging.package_scanner_disconnected", "Packaging Scanner is not connected"),
                feedback_state="error",
                instruction_state="warning",
                instruction=t("device.packaging.package_scanner_connectivity", "Check Scanner connectivity"),
            )
            _plc_write_many(ctx, PLC_STOP_PATHS, True)
            _plc_write_many(ctx, PLC_AUTOMATIC_PATHS, False)
            _set_run_buttons(ctx, running=False)
            return

        ctx.ui.show(
            feedback=t("device.packaging.package_scanner_connected", "Packaging Scanner is connected"),
            feedback_state=1,
            instruction_state=1,
            instruction=t("common.press_start", "Press Start to continue"),
        )
        _set_run_buttons(ctx, running=False)
        return

    if ctx.set_data_if_changed("plc_connected", plc_connected):
        if not plc_connected:
            ctx.ui.show(
                feedback=t("device.plc_beckhoff_disconnected", "Beckhoff is not connected"),
                feedback_state="error",
                instruction_state="warning",
                instruction=t("device.plc.connectivity", "Check Beckhoff connectivity"),
            )
            _set_run_buttons(ctx, running=False)
            return

        ctx.ui.show(
            feedback=t("device.plc_beckhoff_connected", "Beckhoff is connected"),
            feedback_state=1,
            instruction_state=1,
            instruction=t("common.press_start", "Press Start to continue"),
        )
        _set_run_buttons(ctx, running=False)


def _handle_ui_commands(ctx: PublicAutomationContext, cmd_key: str) -> None:
    msg = ctx.ui.consume_view_command_payload(cmd_key)
    if not msg:
        return

    cmd = str(msg.action.name or "")
    if cmd == UiActionName.START.value:
        ctx.ui.popup_wait_close(key=view_wait_key(ViewName.PACKAGING_NOX))
        _set_run_buttons(ctx, running=True)
        _plc_write_many(ctx, PLC_STOP_PATHS, False)
        _plc_write_many(ctx, PLC_AUTOMATIC_PATHS, True)
        return

    if cmd == UiActionName.STOP.value:
        ctx.ui.popup_wait_close(key=view_wait_key(ViewName.PACKAGING_NOX))
        _set_run_buttons(ctx, running=False)
        _plc_write_many(ctx, PLC_STOP_PATHS, True)
        _plc_write_many(ctx, PLC_AUTOMATIC_PATHS, False)
        return

    if cmd == UiActionName.REFRESH.value:
        ctx.set_state(StateKeys.update_container, True)
        ctx.ui.popup_close_all()
        return

    if cmd == UiActionName.RESET.value:
        _plc_write_many(ctx, PLC_RESET_PATHS, True)
        ctx.set_data("plc_reset_pulse", True)
        ctx.set_state(StateKeys.update_container, True)


def _handle_reset_pulse(ctx: PublicAutomationContext) -> None:
    if not bool(ctx.get_data("plc_reset_pulse", False)):
        return
    _plc_write_many(ctx, PLC_RESET_PATHS, False)
    ctx.set_data("plc_reset_pulse", False)


def _handle_mes_request(ctx: PublicAutomationContext) -> None:
    start_mes = bool(ctx.worker.plc_value(PLC_ID, "Start_mes", False))
    prev_start_mes = bool(ctx.get_data("mes_start_prev", False))

    if not start_mes:
        if prev_start_mes or bool(ctx.get_data("mes_ack_active", False)):
            ctx.worker.plc_write(PLC_ID, "Ack_mes", False)
            ctx.set_data("mes_ack_active", False)
        ctx.set_data("mes_start_prev", False)
        return

    # Rising edge: process exactly once per PLC request.
    if prev_start_mes:
        return
    ctx.set_data("mes_start_prev", True)

    station = ctx.global_var("station")
    function = str(ctx.worker.plc_value(PLC_ID, "Function_mes", "") or "").strip()
    req_1 = str(ctx.worker.plc_value(PLC_ID, "MES_Request_1", "") or "").strip()
    req_2 = str(ctx.worker.plc_value(PLC_ID, "MES_Request_2", "") or "").strip()

    if not function:
        result_code = -99999
        result_text = t("packaging.mes_no_function", "MES function name missing")
    else:
        call_info = ctx.itac_custom_function(
            connection_id=ITAC_SERVER_ID,
            method_name=function,
            in_args=[station, req_1, req_2],
            timeout_s=10.0,
        )
        result_code = _result_code(call_info)
        if result_code == 0:
            if  function == "NOXPackaging.PackPartToCurrentLot":
                qty = ctx.get_state(StateKeys.current_container_qty)
                ctx.set_state(StateKeys.current_container_qty, qty + 1)
                part_good = ctx.get_state(StateKeys.part_good)
                ctx.set_state(StateKeys.part_good, part_good + 1)
            elif function == "NOXPackaging.UploadFailure":
                part_bad = ctx.get_state(StateKeys.part_bad)
                ctx.set_state(StateKeys.part_bad, part_bad + 1)
            result_text = ""
        else:
            result_text = _show_itac_error(ctx, result_code, "MES request failed")

    ctx.worker.plc_write(PLC_ID, "Result_code_mes", result_code)
    ctx.worker.plc_write(PLC_ID, "Result_text_mes", result_text)
    ctx.worker.plc_write(PLC_ID, "Ack_mes", True)
    ctx.set_data("mes_ack_active", True)

    if result_text:
        ctx.ui.show(feedback=result_text, feedback_state="error")


def _sync_ui_from_plc(ctx: PublicAutomationContext) -> None:
    ctx.worker.plc_write(PLC_ID, "Counter_ACK", True)

    dummy_enabled = bool(ctx.get_state(StateKeys.dummy_is_enabled))
    if ctx.set_data_if_changed("dummy_enabled", dummy_enabled, False):
        ctx.worker.plc_write(PLC_ID, "Dummy_enabled", dummy_enabled)

    step_text_raw = _normalize_plc_text(ctx.worker.plc_value(PLC_ID, "StepText", ""))
    plc_is_stopped = _plc_stop_active(ctx)
    step_text = (
        t("packaging.stopped_press_start", "System stopped. Press Start to continue.")
        if plc_is_stopped
        else step_text_raw
    )
    ctx.set_data_if_changed("twincat_step_text", step_text, "")
    _set_run_buttons(ctx, running=not plc_is_stopped)

    plc_error_text = _normalize_plc_text(ctx.worker.plc_value(PLC_ID, "ErrorText", ""))
    plc_error_text = _map_plc_error_text_cached(ctx, plc_error_text)
    device_error_text = _device_feedback_error(ctx)
    feedback_text = device_error_text if device_error_text else plc_error_text
    ctx.set_data_if_changed("twincat_error_text", feedback_text, "")

    instruction_state = _instruction_state_for_text(
        step_text,
        has_feedback_error=bool(feedback_text),
        container_full_gate=False,
    )
    feedback_state = _feedback_state_for_text(feedback_text)
    ui_sig = (step_text, feedback_text, instruction_state, feedback_state)
    if ctx.set_data_if_changed("pack_twincat_ui_sig", ui_sig, ("", "", 5, 5)):
        ctx.ui.show(
            instruction=step_text,
            feedback=feedback_text,
            instruction_state=instruction_state,
            feedback_state=feedback_state,
        )

    dmc_barcode = str(ctx.worker.plc_value(PLC_ID, "Part_Result_DMC", "") or "")
    if ctx.set_data_if_changed("dmc_barcode", dmc_barcode, ""):
        ctx.ui.set_state(StateKeys.current_serialnumber, dmc_barcode)


def _handle_container_full_gate(ctx: PublicAutomationContext) -> None:
    current_qty = _to_int(ctx.get_state(StateKeys.current_container_qty, 0), 0)
    max_qty = _to_int(ctx.get_state(StateKeys.max_container_qty, 0), 0)
    container_number = str(ctx.get_state(StateKeys.container_number, "") or "").strip()
    is_full = max_qty > 0 and current_qty >= max_qty

    full_active = bool(ctx.vars.get("container_full_active", False))
    base_container = str(ctx.vars.get("container_full_base_container", "") or "").strip()

    if is_full and not full_active:
        # Enter full-container mode once.
        full_active = True
        ctx.vars.set("container_full_active", True)
        ctx.vars.set("container_full_base_container", container_number)
        _clear_packaging_states(ctx)
        _plc_write_many(ctx, PLC_STOP_PATHS, True)
        _plc_write_many(ctx, PLC_AUTOMATIC_PATHS, False)

    if full_active:
        # Stay in full mode until a different, valid container is loaded.
        now_container = str(ctx.get_state(StateKeys.container_number, "") or "").strip()
        now_max_qty = _to_int(ctx.get_state(StateKeys.max_container_qty, 0), 0)
        new_container_ready = bool(now_container) and now_container not in ("-", base_container) and now_max_qty > 0
        if new_container_ready:
            ctx.vars.set("container_full_active", False)
            ctx.vars.set("container_full_base_container", "")
            _plc_write_many(ctx, PLC_STOP_PATHS, False)
            _plc_write_many(ctx, PLC_AUTOMATIC_PATHS, True)
            _set_run_buttons(ctx, running=True)
            # Trigger a fresh UI render from PLC text/feedback in the next cycle.
            ctx.set_data("pack_twincat_ui_sig", None)
            return

        _plc_write_many(ctx, PLC_STOP_PATHS, True)
        _plc_write_many(ctx, PLC_AUTOMATIC_PATHS, False)
        ctx.ui.set_button_enabled(button_key="start", enabled=False, view_id=ViewName.PACKAGING_NOX.value)
        ctx.ui.set_button_enabled(button_key="stop", enabled=False, view_id=ViewName.PACKAGING_NOX.value)
        ctx.ui.show(
            feedback="Container Full",
            feedback_state="warning",
            instruction="Please scan new Container",
            instruction_state="warning",
        )


def main(ctx: PublicAutomationContext):
    """
    NOX packaging runtime around Beckhoff TwinCAT stepchain:
    - PLC handles machine sequence.
    - Python handles UI controls and iTAC calls on ZenonMes.Start requests.
    """
    ctx.set_cycle_time(0.02)
    key = pages.operator.packaging.packaging_nox.PACKAGING_CMD_KEY

    _handle_device_status(ctx)
    _handle_ui_commands(ctx, key)
    _handle_reset_pulse(ctx)
    _handle_mes_request(ctx)
    _sync_ui_from_plc(ctx)
    _handle_container_full_gate(ctx)



# Export
