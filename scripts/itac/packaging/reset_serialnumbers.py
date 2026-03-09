from __future__ import annotations

from services.script_api import PublicAutomationContext

from services.script_metadata import default_script_meta

SCRIPT_META = default_script_meta(__file__)

ITAC_SERVER_ID = "itac_mk"
SERIAL_NUMBERS = [
    "2F58C11005",
    "2F58C11002",
    "2F58C10994",
    "2F58C10977",
]


def _call_tr_switch_serial_number(ctx: PublicAutomationContext, serial: str) -> None:
    import datetime
    ctx.itac_raw_call(
        connection_id=ITAC_SERVER_ID,
        function_name="trSwitchSerialNumber",
        body={
            "stationNumber": 6000000007,
            "serialNumberRef": serial,
            "serialNumberRefPos": 0,
            "serialNumberArray": [
                {
                    "class": "com.itac.mes.imsapi.domain.container.SwitchSerialNumberData",
                    "index": 0,
                    "serialNumberNew": f"{serial}_{datetime.datetime.now()}",
                    "serialNumberPos": 0,
                    "serialNumberAct": serial,
                    "returnCode": 0,
                }
            ],
        },
    )


def _call_tr_assign_workorder(ctx: PublicAutomationContext, serial: str) -> None:
    ctx.itac_raw_call(
        connection_id=ITAC_SERVER_ID,
        function_name="trAssignSerialNumberForProductOrWorkOrder",
        body={
            "stationNumber": 6410400821,
            "workOrderNumber": 35598,
            "partNumber": -1,
            "bomVersion": -1,
            "serialNumberRef": serial,
            "serialNumberRefPos": 0,
            "processLayer": 2,
            "serialNumberArray.length": 0,
            "activateWorkOrder": 1,
        },
    )


def _call_tr_assign_upload(ctx: PublicAutomationContext, serial: str) -> None:
    ctx.itac_raw_call(
        connection_id=ITAC_SERVER_ID,
        function_name="trAssignSerialNumberForProductOrWorkOrder",
        body={
            "stationNumber": 6000000007,
            "processLayer": 2,
            "serialNumberRef": serial,
            "serialNumberRefPos": -1,
            "serialNumberState": 0,
            "duplicateSerialNumber": 0,
            "bookDate": -1,
            "cycleTime": 0,
            "serialNumberUploadKeys": [
                "ERROR_CODE",
                "SERIAL_NUMBER",
                "SERIAL_NUMBER_STATE",
            ],
        },
    )


def _call_tr_upload_state(ctx: PublicAutomationContext, serial: str) -> None:
    ctx.itac_raw_call(
        connection_id=ITAC_SERVER_ID,
        function_name="trUploadState",
        body={
            "stationNumber": 6000000007,
            "processLayer": 2,
            "serialNumberRef": serial,
            "serialNumberRefPos": -1,
            "serialNumberState": 0,
            "duplicateSerialNumber": 0,
            "bookDate": -1,
            "cycleTime": 0,
            "serialNumberUploadKeys": [
                "ERROR_CODE",
                "SERIAL_NUMBER",
                "SERIAL_NUMBER_STATE",
            ],
        },
    )


def _run_chain_for_serial(ctx: PublicAutomationContext, serial: str) -> None:
    _call_tr_switch_serial_number(ctx, serial)
    _call_tr_assign_workorder(ctx, serial)
    _call_tr_assign_upload(ctx, serial)
    _call_tr_upload_state(ctx, serial)


def main(ctx: PublicAutomationContext):
    ctx.set_cycle_time(0.2)
    step = ctx.step

    if step == 0:
        if bool(ctx.get_data("reset_serialnumbers_done", False)):
            return
        ctx.goto(10)
        return

    if step != 10:
        ctx.goto(10)
        return

    if bool(ctx.get_data("reset_serialnumbers_done", False)):
        ctx.goto(0)
        return

    for serial in SERIAL_NUMBERS:
        _run_chain_for_serial(ctx, serial)

    ctx.set_data("reset_serialnumbers_done", True)
    ctx.goto(0)


# Export
