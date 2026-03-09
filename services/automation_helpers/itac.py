from __future__ import annotations

from services.script_api import PublicAutomationContext, t


ITAC_ERROR_FALLBACK_CODE = -99999


def result_code(response: dict) -> int:
    result = response.get("result", {}) if isinstance(response, dict) else {}
    try:
        return int(result.get("return_value", ITAC_ERROR_FALLBACK_CODE))
    except Exception:
        return ITAC_ERROR_FALLBACK_CODE


def show_itac_error(
    ctx: PublicAutomationContext,
    connection_id: str,
    popup_key: str,
    result_code_value: int,
    fallback: str,
) -> None:
    error = ctx.itac_get_error_text(connection_id, result_code_value)
    error_text = str(error.get("errorString") or "")
    msg_text = t(fallback, fallback)
    if error_text:
        msg_text = msg_text + "\r\n" + error_text
    ctx.ui.popup_message(key=popup_key, message=msg_text, status="error")
