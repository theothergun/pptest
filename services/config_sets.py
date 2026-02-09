from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

CONFIG_SETS_DIR = "config/sets"
ACTIVE_SET_FILE = "config/active_set.json"

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_set_name(name: str) -> str:
    name = (name or "").strip()
    name = _SAFE_NAME.sub("-", name).strip("-")
    return name or "default"


def _ensure_dirs() -> None:
    os.makedirs(CONFIG_SETS_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(ACTIVE_SET_FILE), exist_ok=True)


def list_sets() -> list[str]:
    _ensure_dirs()
    sets = []
    for fn in os.listdir(CONFIG_SETS_DIR):
        if fn.endswith(".json"):
            sets.append(fn[:-5])
    return sorted(sets)


def set_path(set_name: str) -> str:
    _ensure_dirs()
    return os.path.join(CONFIG_SETS_DIR, f"{_safe_set_name(set_name)}.json")


def get_active_set() -> str:
    _ensure_dirs()
    if not os.path.exists(ACTIVE_SET_FILE):
        set_active_set("default")
    try:
        with open(ACTIVE_SET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        name = _safe_set_name(data.get("active", "default"))
    except Exception:
        name = "default"
    if not os.path.exists(set_path(name)):
        # if pointer exists but file missing, fall back
        name = "default"
        if not os.path.exists(set_path(name)):
            create_set_from_template("default", template=None)
        set_active_set(name)
    return name


def set_active_set(set_name: str) -> None:
    _ensure_dirs()
    name = _safe_set_name(set_name)
    with open(ACTIVE_SET_FILE, "w", encoding="utf-8") as f:
        json.dump({"active": name}, f, indent=2)


def create_set_from_template(new_name: str, template: str | None) -> str:
    _ensure_dirs()
    new_name = _safe_set_name(new_name)
    dst = set_path(new_name)
    if os.path.exists(dst):
        raise ValueError(f"Config set '{new_name}' already exists")

    data: dict[str, Any] = {}
    if template:
        src = set_path(template)
        if os.path.exists(src):
            with open(src, "r", encoding="utf-8") as f:
                data = json.load(f)

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return new_name
