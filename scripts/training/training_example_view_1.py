from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from services.script_api import PublicAutomationContext

VIEW_ID = "training_example_view"
TCP_CLIENT_ID = "training_scanner"
CSV_PATH = Path("training/output/training_scans.csv")


def _init_defaults(ctx: PublicAutomationContext) -> None:
    ctx.set_state_many(
        training_active_script="training_example_view_1",
        training_status="Ready (mode 1)",
        training_mode="standard",
        training_last_scan="",
        training_scan_count=0,
        training_confirm_result="-",
        training_csv_count=0,
        training_csv_last_status="-",
        training_csv_path=CSV_PATH.as_posix(),
        training_last_button="-",
    )
    ctx.ui.set_buttons_enabled(
        {
            "btn_a": True,
            "btn_b": False,
            "show_popup": True,
            "ask_confirm": True,
            "write_csv": True,
            "reset_state": True,
        },
        view_id=VIEW_ID,
    )


def _append_csv_row(last_scan: str, counter: int) -> tuple[bool, str]:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not CSV_PATH.exists()
    with CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "scan_code", "counter"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), last_scan, int(counter)])
    return True, f"CSV row written to {CSV_PATH.as_posix()}"


def _consume_command(ctx: PublicAutomationContext) -> dict[str, Any] | None:
    cmd = ctx.values.state("training_command", {})
    if not isinstance(cmd, dict):
        return None
    event_id = str(cmd.get("event_id") or "")
    if not event_id:
        return None
    if event_id == str(ctx.get_data("last_command_event_id", "")):
        return None
    ctx.set_data("last_command_event_id", event_id)
    return cmd


def _handle_scan(ctx: PublicAutomationContext) -> None:
    raw = ctx.read_tcp(TCP_CLIENT_ID, default=None, decode=True)
    if raw is None:
        return
    scan = str(raw).strip()
    if not scan:
        return
    if scan == str(ctx.get_data("last_tcp_scan", "")):
        return

    ctx.set_data("last_tcp_scan", scan)
    ctx.log_info(f"[training_example_view_1] scan received: {scan}")

    if not scan.startswith("TRN-"):
        ctx.set_state("training_status", f"Rejected scan (expected TRN-): {scan}")
        ctx.notify_warning(f"Rejected scan: {scan}")
        return

    count = int(ctx.get_state("training_scan_count", 0) or 0) + 1
    ctx.set_state_many(
        training_last_scan=scan,
        training_scan_count=count,
        training_status=f"Accepted scan: {scan}",
    )


def _handle_write_csv(ctx: PublicAutomationContext) -> None:
    scan = str(ctx.get_state("training_last_scan", "") or "")
    counter = int(ctx.get_state("training_scan_count", 0) or 0)
    if not scan:
        ctx.notify_warning("Scan something first before writing CSV.")
        ctx.set_state("training_csv_last_status", "Skipped: no scan available")
        return

    try:
        _, message = _append_csv_row(scan, counter)
        csv_count = int(ctx.get_state("training_csv_count", 0) or 0) + 1
        ctx.set_state_many(training_csv_count=csv_count, training_csv_last_status=message)
        ctx.notify_positive("CSV row written")
        ctx.log_info(f"[training_example_view_1] file write success: {message}")
    except Exception as ex:
        error_msg = f"CSV write failed: {ex}"
        ctx.set_state("training_csv_last_status", error_msg)
        ctx.notify_negative(error_msg)
        ctx.log_error(f"[training_example_view_1] file write failed: {ex}")


def main(ctx: PublicAutomationContext):
    ctx.set_cycle_time(0.1)

    if ctx.step == 0:
        _init_defaults(ctx)
        ctx.goto(10)
        return

    if ctx.step == 10:
        _handle_scan(ctx)
        cmd = _consume_command(ctx)
        if not cmd:
            return

        action = str(cmd.get("action") or "")
        ctx.set_state("training_last_button", action)
        ctx.log_info(f"[training_example_view_1] button click: {action}")

        if action == "btn_a":
            ctx.set_state("training_status", "Action A pressed")
            ctx.ui.set_buttons_enabled({"btn_a": False, "btn_b": True}, view_id=VIEW_ID)
            return

        if action == "btn_b":
            ctx.set_state("training_status", "Action B pressed")
            ctx.ui.set_buttons_enabled({"btn_a": True, "btn_b": False}, view_id=VIEW_ID)
            return

        if action == "show_popup":
            ctx.goto(20)
            return

        if action == "ask_confirm":
            ctx.goto(30)
            return

        if action == "reset_state":
            _init_defaults(ctx)
            ctx.notify_info("Training state reset")
            return

        if action == "write_csv":
            _handle_write_csv(ctx)
            return

    if ctx.step == 20:
        result = ctx.ui.popup_message(
            "training_popup",
            "This popup comes from training_example_view_1.",
            title="Training Popup",
            status="info",
            buttons=[{"id": "ok", "text": "OK"}],
        )
        if result is None:
            return
        ctx.log_info(f"[training_example_view_1] popup result: {result}")
        ctx.set_state("training_status", "Popup closed")
        ctx.goto(10)
        return

    if ctx.step == 30:
        answer = ctx.ui.popup_confirm(
            "training_confirm",
            "Enable Action B and disable Action A?",
            title="Training Confirm",
            ok_text="Yes",
            cancel_text="No",
        )
        if answer is None:
            return
        ctx.log_info(f"[training_example_view_1] confirm result: {answer}")
        if answer:
            ctx.ui.set_buttons_enabled({"btn_a": False, "btn_b": True}, view_id=VIEW_ID)
            ctx.set_state_many(training_confirm_result="yes", training_status="Confirmed: A disabled, B enabled")
        else:
            ctx.ui.set_buttons_enabled({"btn_a": True, "btn_b": False}, view_id=VIEW_ID)
            ctx.set_state_many(training_confirm_result="no", training_status="Cancelled: defaults restored")
        ctx.goto(10)


main = main
