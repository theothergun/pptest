
# services/workers/stepchain/api_utils.py
from __future__ import annotations

import copy
from typing import Any


def safe_deepcopy(value: Any) -> Any:
	"""Best-effort deep copy for values that may not be deepcopy-able."""
	try:
		return copy.deepcopy(value)
	except Exception:
		return value


def values_equal(a: Any, b: Any) -> bool:
	"""Best-effort equality check; returns False if comparison fails."""
	try:
		return a == b
	except Exception:
		return False


def to_int(value: Any, default: int = 0) -> int:
	"""
	Robust int conversion for typical MES payloads.

	Supports:
	- int/float -> int
	- "111" -> 111
	- "111.0" -> 111
	- " 111,0 " -> 111
	- None / "" -> default
	"""
	try:
		if value is None:
			return int(default)

		if isinstance(value, bool):
			return int(value)

		if isinstance(value, int):
			return value

		if isinstance(value, float):
			return int(value)

		if isinstance(value, (bytes, bytearray)):
			try:
				value = bytes(value).decode("utf-8", errors="replace")
			except Exception:
				return int(default)

		if isinstance(value, str):
			s = value.strip()
			if not s:
				return int(default)
			s = s.replace(",", ".")
			if "." in s:
				return int(float(s))
			return int(s)

		return int(value)
	except Exception:
		return int(default)


def to_float(value: Any, default: float = 0.0) -> float:
	try:
		if value is None:
			return float(default)
		if isinstance(value, bool):
			return float(int(value))
		if isinstance(value, (int, float)):
			return float(value)
		if isinstance(value, (bytes, bytearray)):
			try:
				value = bytes(value).decode("utf-8", errors="replace")
			except Exception:
				return float(default)
		if isinstance(value, str):
			s = value.strip()
			if not s:
				return float(default)
			s = s.replace(",", ".")
			return float(s)
		return float(value)
	except Exception:
		return float(default)


def to_str(value: Any, default: str = "") -> str:
	try:
		if value is None:
			return str(default)
		if isinstance(value, (bytes, bytearray)):
			try:
				return bytes(value).decode("utf-8", errors="replace")
			except Exception:
				return str(default)
		return str(value)
	except Exception:
		return str(default)
