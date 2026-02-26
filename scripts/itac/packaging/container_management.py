from __future__ import annotations

from services.script_api import PublicAutomationContext, t, UiActionName, ViewName, ViewButtons, StateKeys
from datetime import datetime

ITAC_SERVER_ID = "itac_mk"

def main(ctx: PublicAutomationContext):
    ctx.set_cycle_time(0.2)
    step = ctx.step
    if step == 0:
        # refresh not available on itac
        ctx.ui.set_button_visible(ViewButtons.REMOVE_ALL, False, view_id=ViewName.CONTAINER_MANAGEMENT)
        ctx.ui.set_button_visible(ViewButtons.REFRESH, False, view_id=ViewName.CONTAINER_MANAGEMENT)
        ctx.goto(10)
        return
    if step != 10:
        ctx.goto(10)
        return

    current_container = ctx.get_state(StateKeys.container_mgmt_container_selected)
    enabled = bool(current_container)
    if ctx.set_data_if_changed("container_selected", enabled,default=False):
        ctx.ui.set_button_enabled(
        ViewButtons.REMOVE_SERIAL,
        enabled,
        view_id=ViewName.CONTAINER_MANAGEMENT)

    if ctx.set_data_if_changed("current_container", current_container, default=False):
        ctx.set_state(StateKeys.container_mgmt_serial_rows, [])


    def _result_code(res: dict) -> int:
        result = res.get("result", {}) if isinstance(res, dict) else {}
        try:
            return int(result.get("return_value", -99999))
        except Exception:
            return -99999

    def _show_itac_error(popup_key: str, result_code: int, fallback: str) -> None:
        error = ctx.itac_get_error_text(ITAC_SERVER_ID, result_code)
        error_text = str(error.get("errorString") or "")
        msg_text = t(fallback, fallback)
        if error_text:
            msg_text = msg_text + "\r\n" + error_text
        ctx.ui.popup_message(popup_key, message=msg_text, status="error")

    # Pending non-blocking confirmation flow for remove serial.
    pending_action = str(ctx.get_data("container_mgmt_pending_action", "") or "")
    if pending_action == "remove_serial":
        confirm = ctx.ui.popup_confirm(
            "container_mgmt_remove_serial_confirm",
            t("container_management.confirm_remove_serial", "Remove selected serial number?"),
            title=t("common.confirm", "Confirm"),
            ok_text=t("common.remove", "Remove"),
            cancel_text=t("common.cancel", "Cancel"),
            wait_step_desc=t("container_management.waiting_confirmation", "Waiting for confirmation..."),
        )
        if confirm is None:
            return
        if not confirm:
            ctx.set_data("container_mgmt_pending_action", "")
            return

        station = ctx.global_var("station")
        serial_number = str(ctx.get_state(StateKeys.container_mgmt_serial_selected, "") or "").upper()
        container = str(ctx.get_state(StateKeys.container_mgmt_container_selected, "") or "").upper()
        if not serial_number or not container:
            ctx.ui.popup_message(
                "remove_failed_missing_selection",
                message=t("container_management.remove_missing_selection", "Please select container and serial"),
                status="error",
            )
            ctx.set_data("container_mgmt_pending_action", "")
            return

        res = ctx.itac_raw_call(
            connection_id=ITAC_SERVER_ID,
            function_name="shipRemoveSerialNumberFromShippingLot",
            body={
                "stationNumber": station,
                "lotNumber": container,
                "serialNumber": serial_number,
                "serialNumberPos": "-1",
                "bookDate": -1,
            },
            timeout_s=5,
        )
        result_code = _result_code(res)
        if result_code >= 0:
            ctx.ui.popup_message("remove_success", message=t("packaging.serial_removed", "Serial Removed"), status="success")
        else:
            _show_itac_error("remove_success", result_code, "packaging.serial_removed_failed")
        ctx.set_data("container_mgmt_pending_action", "")
        return
    if pending_action == "activate_container":
        confirm = ctx.ui.popup_confirm(
            "container_mgmt_activate_confirm",
            t("container_management.confirm_activate", "Activate selected container?"),
            title=t("common.confirm", "Confirm"),
            ok_text=t("container_management.activate", "Activate"),
            cancel_text=t("common.cancel", "Cancel"),
            wait_step_desc=t("container_management.waiting_confirmation", "Waiting for confirmation..."),
        )
        if confirm is None:
            return
        if not confirm:
            ctx.set_data("container_mgmt_pending_action", "")
            return

        station = ctx.global_var("station")
        container = str(ctx.get_state(StateKeys.container_mgmt_container_selected, "") or "").upper()
        if not container:
            ctx.ui.popup_message(
                "activate_missing_container",
                message=t("container_management.no_container_selected", "No container selected"),
                status="error",
            )
            ctx.set_data("container_mgmt_pending_action", "")
            return

        res = ctx.itac_raw_call(
            connection_id=ITAC_SERVER_ID,
            function_name="shipActivateShippingLotAtKap",
            body={
                "stationNumber": station,
                "lotNumber": container,
            },
            timeout_s=5,
        )
        result_code = _result_code(res)
        if result_code >= 0:
            ctx.set_state(StateKeys.container_mgmt_active_container, container)
            ctx.ui.popup_message("activate_success", message=t("container_management.activate_success", "Container activated"), status="success")
        else:
            _show_itac_error("activate_failed", result_code, "container_management.activate_failed")
        ctx.set_data("container_mgmt_pending_action", "")
        return

    msg = ctx.ui.consume_view_command_payload("container_management.cmd")
    if not msg:
        return

    action_name = msg.action.name

    if action_name == UiActionName.SEARCH:
        station = ctx.global_var("station")
        container = ctx.get_state(StateKeys.container_mgmt_container_selected).upper()
        ctx.set_state(StateKeys.container_mgmt_serial_rows, [])
        res = ctx.itac_raw_call(connection_id=ITAC_SERVER_ID,
                        function_name="shipGetSerialNumberDataForShippingLot",
                        body={"stationNumber" : station ,
                              "serialNumberResultKeys" : [ "SERIAL_NUMBER","SHIPPING_DATE" ],
                              "lotNumber": container
                              }
                          , timeout_s=5 )
        rows = []
        result_code = _result_code(res)
        if result_code == 0:
            values = res["result"]["serialNumberResultValues"]
            for i in range(0, len(values), 2):
                serial_number = values[i]
                shipping_date_ms = values[i + 1]
                formatted_date = datetime.fromtimestamp(float(shipping_date_ms) / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
                rows.append({
                    "serial_number": serial_number,
                    "created_on": formatted_date
                })
            ctx.set_state(StateKeys.container_mgmt_serial_rows, rows)
        else:
            _show_itac_error("search_container_serial_error", result_code, "Search failed")

    if action_name == UiActionName.SEARCH_CONTAINER:
        station = ctx.global_var("station")
        container = ctx.get_state(StateKeys.container_mgmt_search_query).upper()
        ctx.set_state(StateKeys.container_mgmt_serial_rows, [])
        ctx.set_state(StateKeys.container_mgmt_container_rows, [])
        if len(container )< 5 :
            ctx.ui.popup_close(msg.wait_modal_key)
            ctx.ui.popup_message("search_conition_to_short",message=t("view.search_conition_to_short", "Type in at least %s chars" ) %5   )
            return

        container = (lambda x: (("*" + x.strip() + "*") if x and x.strip() else x))(container)
        res = ctx.itac_raw_call(connection_id=ITAC_SERVER_ID,
                                function_name="mlGetMaterialBinData",
                                body={"stationNumber": station,
                                      "materialBinFilters": [
                                          { "key": "INCLUDE_EMPTY_BIN" ,  "value" : 0  } ,
                                          { "key": "MATERIAL_BIN_NUMBER" , "value" :  container } ,
                                          { "key": "MATERIAL_BIN_PART_NUMBER", "value" : "PackagingContainer" } ,
                                          { "key": "MAX_ROWS" , "value" : 5 }
                                          ] ,
                                      "materialBinResultKeys": [ "MATERIAL_BIN_NUMBER",
                                                                 "MATERIAL_BIN_QTY_ACTUAL",
                                                                 "MATERIAL_BIN_QTY_TOTAL"
                                                                 ]
                                      }
                                , timeout_s=999)
        rows = []
        result_code = _result_code(res)
        if result_code >= 0 :
            values = res["result"]["materialBinResultValues"]
            if len(values) ==0:
                ctx.ui.popup_close(msg.wait_modal_key)
                ctx.ui.popup_message("search_conition_to_short",
                                     message=t("view.no_data_found", "No Data found."))
            for i in range(0, len(values), 3):
                mat_bin = values[i]
                max_qty = values[i + 2].replace(".0", "")
                current_qty = values[i + 1].replace(".0", "")
                rows.append({
                    "material_bin": mat_bin,
                    "part_number": "-",
                    "current_qty" : f"{current_qty}/{max_qty}"
                })
            ctx.set_state(StateKeys.container_mgmt_container_rows, rows)
        else:
            _show_itac_error("search_container_error", result_code, "Container search failed")
        ctx.ui.popup_close(msg.wait_modal_key)
        return
    if action_name == UiActionName.SEARCH_SERIAL:
        station = ctx.global_var("station")
        serial_number = ctx.get_state(StateKeys.container_mgmt_search_query).upper()
        res = ctx.itac_raw_call(connection_id=ITAC_SERVER_ID,
                        function_name="shipGetLotFromSerialNumber",
                        body={"stationNumber" : station ,
                              "lotResultKeys" : [ "MATERIAL_BIN_NUMBER","MATERIAL_BIN_QTY_ACTUAL" , "MATERIAL_BIN_QTY_TOTAL" ],
                              "serialNumber": serial_number,
                              "serialNumberPos" : "-1"
                              }
                          , timeout_s=5 )
        rows = []
        result_code = _result_code(res)
        if result_code >= 0 :
            values = res["result"]["lotResultValues"]
            if len(values) ==0:
                ctx.ui.popup_close(msg.wait_modal_key)
                ctx.ui.popup_message("search_serialnumber_no_lot_found",
                                     message=t("view.no_data_found", "No Data found."))
            for i in range(0, len(values), 3):
                mat_bin = values[i]
                max_qty = values[i + 2].replace(".0", "")
                current_qty = values[i + 1].replace(".0", "")
                rows.append({
                    "material_bin": mat_bin,
                    "part_number": "-",
                    "current_qty" : f"{current_qty}/{max_qty}"
                })
            ctx.set_state(StateKeys.container_mgmt_container_rows, rows)
        else:
            _show_itac_error("search_serial_error", result_code, "Serial search failed")
    if action_name == UiActionName.ACTIVATE:
        # Start confirmation flow; actual call happens via pending_action handling above.
        ctx.set_data("container_mgmt_pending_action", "activate_container")
        if msg.wait_modal_key:
            ctx.ui.popup_close(msg.wait_modal_key)
        return
    if action_name == UiActionName.REMOVE_SERIAL:
        # Start confirmation flow; actual call happens via pending_action handling above.
        ctx.set_data("container_mgmt_pending_action", "remove_serial")
        if msg.wait_modal_key:
            ctx.ui.popup_close(msg.wait_modal_key)
        return
    if msg.wait_modal_key:
        ctx.ui.popup_close(msg.wait_modal_key)

# Export
main = main
