from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any

from services.app_config import get_app_config


_SAFE_FILE_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_STATE_DIR = "Config"


def _safe_hostname() -> str:
    host = socket.gethostname().strip() or "unknown-host"
    return _SAFE_FILE_RE.sub("_", host)


def _state_file_path() -> str:
    os.makedirs(_STATE_DIR, exist_ok=True)
    return os.path.join(_STATE_DIR, f"{_safe_hostname()}.json")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


def _selected_keys() -> set[str]:
    cfg = get_app_config()
    raw = getattr(cfg, "persistent_app_state_keys", [])
    if not isinstance(raw, list):
        return set()
    out: set[str] = set()
    for key in raw:
        key_s = str(key).strip()
        if key_s:
            out.add(key_s)
    return out


def _read_all() -> dict[str, Any]:
    path = _state_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_all(data: dict[str, Any]) -> None:
    path = _state_file_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def load_selected_state() -> dict[str, Any]:
    data = _read_all()
    selected = _selected_keys()
    if not selected:
        return {}
    return {k: v for k, v in data.items() if k in selected}


def persist_state_value(key: str, value: Any) -> None:
    key_s = str(key or "").strip()
    if not key_s:
        return
    selected = _selected_keys()
    if key_s not in selected:
        return

    data = _read_all()
    data[key_s] = _json_safe(value)
    _write_all(data)


def sync_selected_from_state_obj(state_obj: Any) -> None:
    selected = _selected_keys()
    if not selected or state_obj is None:
        return

    data = _read_all()
    for key in selected:
        if hasattr(state_obj, key):
            data[key] = _json_safe(getattr(state_obj, key))
    _write_all(data)
