from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class AppState:
    # ---- device worker ----
    device_status: str = "Disconnected"
    device_last_seen: str = "-"

    # ---- job worker ----
    job_status: str = "Idle"

    # ---- errors (ui-facing summary) ----
    error_count: int = 0

    # ---- counters ----
    part_good: int = 0
    part_bad: int = 0
    part_total: int = 0

    # ---- Operator instructions ----
    work_instruction: str = "Work instruction goes here"
    work_feedback: str = "Work feedback goes here"

    # ---- visual inspection ----
    ltc_error_status: int = 0
    ltc_dmc: str = ""
    ltc_status: str = ""
    ltc_leak_rate: Decimal = field(default_factory=lambda: Decimal("0"))
    ltc_result: str = ""
    vc_dmc: str = ""
    vc_result: str = ""
    vc_error_status: int = 0

    # ---- packaging ----
    container_number: str = ""
    part_number: str = ""
    description: str = ""
    current_container_qty: str = ""
    max_container_qty: str = ""
    last_serial_number: str = ""
    current_serialnumber: str = ""
    packaging_search_query: str = ""
    packaging_container_selected: str = ""
    packaging_active_container: str = ""
    packaging_container_rows: list[dict[str, Any]] = field(default_factory=list)
    packaging_serial_rows: list[dict[str, Any]] = field(default_factory=list)

    # ---- container management ----
    container_mgmt_search_query: str = ""
    container_mgmt_container_selected: str = ""
    container_mgmt_active_container: str = ""
    container_mgmt_container_rows: list[dict[str, Any]] = field(default_factory=list)
    container_mgmt_serial_rows: list[dict[str, Any]] = field(default_factory=list)

    test_new_kea: str= ""

    # ----- Dummy -----
    dummy_is_enabled: bool = False #True the dummy window show up
    dummy_test_is_running: bool = False # True if a dummy test start
    dummy_result_available: bool = False # True if dummy result are ready for evaluation
    dummy_program_changed: bool = False # True if program changed and dummy should be started

