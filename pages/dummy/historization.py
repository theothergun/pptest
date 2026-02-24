from __future__ import annotations

import json
from dataclasses import is_dataclass, asdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from datetime import timedelta  # only used for days/weeks retention


HISTORY_ROOT = Path("dummy_results")  # configurable if you want


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(dt_str: str) -> datetime:
    s = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _month_key(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _add_months(year: int, month: int, delta: int) -> Tuple[int, int]:
    total = (year * 12 + (month - 1)) + delta
    new_year = total // 12
    new_month = (total % 12) + 1
    return new_year, new_month


def history_path_for(started_at_iso: str) -> Path:
    started = _parse_iso(started_at_iso)
    return HISTORY_ROOT / f"{started.year:04d}" / f"{started.month:02d}.jsonl"


def append_history_record(record: Dict[str, Any]) -> Path:
    """
    Append one execution record as JSONL line to YYYY/MM.jsonl based on record['started_at'].
    Returns the file path written to.
    """
    started_at = record.get("started_at")
    if not isinstance(started_at, str) or not started_at:
        raise ValueError("record['started_at'] must be a non-empty ISO string")

    path = history_path_for(started_at)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _default(o: Any) -> Any:
        if is_dataclass(o):
            return asdict(o)
        return str(o)

    # normalize: ensure JSON-serializable
    normalized = json.loads(json.dumps(record, default=_default))

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(normalized, ensure_ascii=False) + "\n")

    return path


# ---------------- CLEANUP ----------------

_UNIT_TO_DAYS = {
    "Days": 1,
    "Day": 1,
    "Weeks": 7,
    "Week": 7,
}


def compute_cutoff_month(now: datetime, older_value: int, older_unit: str) -> Tuple[int, int]:
    """
    Returns (year, month) for the cutoff bucket.
    Files strictly older than that month are deleted.
    """
    now = now.astimezone(timezone.utc)
    unit = (older_unit or "").strip()

    if unit in ("Months", "Month"):
        return _add_months(now.year, now.month, -older_value)

    if unit in ("Years", "Year"):
        return _add_months(now.year, now.month, -(older_value * 12))

    # Days/Weeks fallback -> approximate by datetime arithmetic, then use that month as cutoff
    days = older_value * _UNIT_TO_DAYS.get(unit, 1)
    cutoff_dt = now - timedelta(days=days)
    return cutoff_dt.year, cutoff_dt.month


def cleanup_history_if_needed(*, clean_enabled: bool, older_value: int, older_unit: str) -> None:
    """
    Deletes whole monthly jsonl files older than the cutoff month.
    Removes empty year folders.
    """
    if not clean_enabled:
        return
    if older_value <= 0:
        return

    now = _utc_now()
    cutoff_y, cutoff_m = compute_cutoff_month(now, older_value, older_unit)
    cutoff_key = _month_key(cutoff_y, cutoff_m)

    if not HISTORY_ROOT.exists():
        return

    for year_dir in sorted([p for p in HISTORY_ROOT.iterdir() if p.is_dir() and p.name.isdigit()]):
        year = int(year_dir.name)

        for file in sorted(year_dir.glob("*.jsonl")):
            stem = file.stem  # "02"
            if not stem.isdigit():
                continue
            month = int(stem)
            if not (1 <= month <= 12):
                continue

            key = _month_key(year, month)
            if key < cutoff_key:
                try:
                    file.unlink()
                except Exception:
                    pass

        # remove empty year folder
        try:
            if not any(year_dir.iterdir()):
                year_dir.rmdir()
        except Exception:
            pass

# ------------------- LOAD TEST RESULT -----------------------------

def _month_iter(start_y: int, start_m: int, end_y: int, end_m: int) -> List[Tuple[int, int]]:
    """Inclusive month iteration from (start_y,start_m) .. (end_y,end_m)."""
    out: List[Tuple[int, int]] = []
    start_key = _month_key(start_y, start_m)
    end_key = _month_key(end_y, end_m)
    if end_key < start_key:
        return out

    y, m = start_y, start_m
    while _month_key(y, m) <= end_key:
        out.append((y, m))
        y, m = _add_months(y, m, 1)
    return out


def load_history_records(
    *,
    date_from: date,
    date_to: date,
    set_name: Optional[str],                # None means "All"
    max_records: int = 5000,                # hard cap
    time_field: str = "started_at",         # "started_at" or "finished_at"
) -> List[Dict[str, Any]]:
    """
    Reads only the monthly jsonl files overlapping [date_from, date_to] (inclusive),
    and filters records by the chosen timestamp field.

    Notes:
    - Files are bucketed by started_at in your writer, but for finished_at filtering
      we still only scan months overlapping the date range to keep this fast.
    """
    if max_records <= 0:
        return []
    if date_to < date_from:
        return []
    if time_field not in {"started_at", "finished_at"}:
        raise ValueError("time_field must be 'started_at' or 'finished_at'")

    # inclusive date range as UTC datetimes
    dt_from = datetime.combine(date_from, time.min).replace(tzinfo=timezone.utc)
    dt_to = datetime.combine(date_to, time.max).replace(tzinfo=timezone.utc)

    # We choose months based on the filter range (fast path)
    months = _month_iter(dt_from.year, dt_from.month, dt_to.year, dt_to.month)

    records: List[Dict[str, Any]] = []

    for y, m in months:
        path = HISTORY_ROOT / f"{y:04d}" / f"{m:02d}.jsonl"
        if not path.exists():
            continue

        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if len(records) >= max_records:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue

                    # optional set filter
                    if set_name is not None and str(rec.get("set_name", "")) != set_name:
                        continue

                    ts = rec.get(time_field)
                    if not isinstance(ts, str) or not ts:
                        continue

                    try:
                        ts_dt = _parse_iso(ts)
                    except Exception:
                        continue

                    # date filter (inclusive)
                    if ts_dt < dt_from or ts_dt > dt_to:
                        continue

                    records.append(rec)
        except Exception:
            continue

        if len(records) >= max_records:
            break

    # sort newest first by the chosen time_field
    def _key(rec: Dict[str, Any]) -> datetime:
        try:
            return _parse_iso(str(rec.get(time_field, "")))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    records.sort(key=_key, reverse=True)
    return records


def get_last_finished_at(*, set_name: str | None = None) -> Optional[datetime]:
    """
    Scan history files newest-first and return the newest finished_at datetime.
    If set_name is provided, only consider records matching that set.
    """
    if not HISTORY_ROOT.exists():
        return None

    # iterate year/month newest-first
    years = sorted([p for p in HISTORY_ROOT.iterdir() if p.is_dir() and p.name.isdigit()], reverse=True)
    for year_dir in years:
        files = sorted([f for f in year_dir.glob("*.jsonl") if f.stem.isdigit()], reverse=True)
        for file in files:
            try:
                # read lines from end for speed
                with file.open("r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec: dict[str, Any] = json.loads(line)
                    except Exception:
                        continue

                    if set_name is not None and rec.get("set_name") != set_name:
                        continue

                    finished = rec.get("finished_at")
                    if isinstance(finished, str) and finished:
                        try:
                            return _parse_iso(finished)
                        except Exception:
                            continue
            except Exception:
                continue

    return None