from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


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

    test_new_kea: str= ""
