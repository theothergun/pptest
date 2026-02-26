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
        training_active_script="training_example_view_2",
        training_status="Ready (mode 2)",
        training_mode="strict",
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
            "btn_b": True,
            "show_popup": True,
            "ask_confirm": True,
            "write_csv": False,
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

    mode = str(ctx.get_state("training_mode", "strict") or "strict")
    ctx.set_data("last_tcp_scan", scan)
    ctx.log_info(f"[training_example_view_2] scan received: {scan} mode={mode}")

    accepted = scan.startswith("ALT-")
    if mode == "relaxed":
        accepted = scan.startswith("ALT-") or scan.startswith("TRN-")

    if not accepted:
        ctx.set_state("training_status", f"Rejected by mode {mode}: {scan}")
        ctx.notify_warning(f"Rejected in {mode} mode: {scan}")
        ctx.ui.set_button_enabled("write_csv", False, view_id=VIEW_ID)
        return

    count = int(ctx.get_state("training_scan_count", 0) or 0) + 1
    ctx.set_state_many(
        training_last_scan=scan,
        training_scan_count=count,
        training_status=f"Accepted ({mode}): {scan}",
    )
    ctx.ui.set_button_enabled("write_csv", True, view_id=VIEW_ID)


def _handle_write_csv(ctx: PublicAutomationContext) -> None:
    scan = str(ctx.get_state("training_last_scan", "") or "")
    counter = int(ctx.get_state("training_scan_count", 0) or 0)
    if not scan:
        ctx.notify_warning("No accepted scan available.")
        ctx.set_state("training_csv_last_status", "Skipped: no accepted scan")
        return

    answer = ctx.ui.popup_confirm(
        "training_confirm_csv_mode2",
        f"Write this scan to CSV?\n{scan}",
        title="Mode 2 CSV Confirm",
        ok_text="Write",
        cancel_text="Cancel",
    )
    if answer is None:
        return

    ctx.log_info(f"[training_example_view_2] confirm result for csv: {answer}")
    ctx.set_state("training_confirm_result", "yes" if answer else "no")

    if not answer:
        ctx.set_state("training_csv_last_status", "CSV write cancelled by user")
        return

    try:
        _, message = _append_csv_row(scan, counter)
        csv_count = int(ctx.get_state("training_csv_count", 0) or 0) + 1
        ctx.set_state_many(training_csv_count=csv_count, training_csv_last_status=message)
        ctx.notify_positive("CSV row written")
        ctx.log_info(f"[training_example_view_2] file write success: {message}")
    except Exception as ex:
        error_msg = f"CSV write failed: {ex}"
        ctx.set_state("training_csv_last_status", error_msg)
        ctx.notify_negative(error_msg)
        ctx.log_error(f"[training_example_view_2] file write failed: {ex}")


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
        ctx.log_info(f"[training_example_view_2] button click: {action}")

        if action == "btn_a":
            ctx.set_state("training_status", "Mode 2: Action A sets strict mode")
            ctx.set_state("training_mode", "strict")
            ctx.ui.set_buttons_enabled({"btn_a": False, "btn_b": True}, view_id=VIEW_ID)
            return

        if action == "btn_b":
            ctx.set_state("training_status", "Mode 2: Action B sets relaxed mode")
            ctx.set_state("training_mode", "relaxed")
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
            ctx.goto(40)
            return

    if ctx.step == 20:
        result = ctx.ui.popup_message(
            "training_popup_mode2",
            "Mode 2 tip: strict mode only accepts ALT- scans.",
            title="Training Popup (Mode 2)",
            status="info",
            buttons=[
                {"id": "strict", "text": "Set strict"},
                {"id": "relaxed", "text": "Set relaxed"},
            ],
        )
        if result is None:
            return
        clicked = str(result.get("clicked") or "")
        ctx.log_info(f"[training_example_view_2] popup result: {clicked}")
        if clicked in ("strict", "relaxed"):
            ctx.set_state("training_mode", clicked)
            ctx.set_state("training_status", f"Mode changed from popup: {clicked}")
        ctx.goto(10)
        return

    if ctx.step == 30:
        answer = ctx.ui.popup_confirm(
            "training_confirm_mode2",
            "Apply mode rules to button states now?",
            title="Mode 2 Confirm",
            ok_text="Apply",
            cancel_text="Skip",
        )
        if answer is None:
            return
        ctx.log_info(f"[training_example_view_2] confirm result: {answer}")
        if answer:
            mode = str(ctx.get_state("training_mode", "strict") or "strict")
            if mode == "strict":
                ctx.ui.set_buttons_enabled({"btn_a": False, "btn_b": True}, view_id=VIEW_ID)
            else:
                ctx.ui.set_buttons_enabled({"btn_a": True, "btn_b": False}, view_id=VIEW_ID)
            ctx.set_state("training_status", f"Rules applied for mode: {mode}")
            ctx.set_state("training_confirm_result", "yes")
        else:
            ctx.set_state("training_confirm_result", "no")
            ctx.set_state("training_status", "Mode-rule apply skipped")
        ctx.goto(10)
        return

    if ctx.step == 40:
        _handle_write_csv(ctx)
        if ctx.step == 40:
            ctx.goto(10)


main = main
