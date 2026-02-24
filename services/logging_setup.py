from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Any
from loguru import logger
import traceback


LOG_FORMAT = (
	"{level.icon} <green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
	"<blue>{thread.name:^10}-{thread.id:^8}</blue> | "
	"[<level>{level:<8}</level>] | "
	"<white>{name}.{function}:{line}</white> | "
	"<level>{message}</level>"
)

DEFAULT_FILE_LEVEL = "DEBUG"


_ERROR_EVENTS_MAX = 500
_error_events_lock = threading.Lock()
_error_events: deque[dict[str, Any]] = deque(maxlen=_ERROR_EVENTS_MAX)
_error_event_id = 0


def _error_popup_sink(message) -> None:
	"""Capture ERROR+ records so UI sessions can show toast popups."""
	global _error_event_id
	record = message.record
	level_name = str(record.get("level").name)
	text = str(record.get("message") or "").strip()

	exc = record.get("exception")
	if exc and getattr(exc, "value", None):
		exc_text = str(exc.value)
		if exc_text:
			text = f"{text} | {exc_text}" if text else exc_text

	if not text:
		text = "An unknown error was logged."

	with _error_events_lock:
		_error_event_id += 1
		_error_events.append(
			{
				"id": _error_event_id,
				"level": level_name,
				"message": text,
			}
		)


def get_latest_error_popup_event_id() -> int:
	with _error_events_lock:
		return int(_error_event_id)


def get_error_popup_events_since(last_seen_id: int) -> tuple[int, list[dict[str, Any]]]:
	with _error_events_lock:
		current = int(_error_event_id)
		events = [evt for evt in _error_events if int(evt.get("id", 0)) > int(last_seen_id)]
	return current, events


def _install_global_exception_hooks() -> None:
	"""Ensure uncaught exceptions always end up in logs."""
	def _sys_hook(exc_type, exc_value, exc_tb):
		try:
			logger.opt(exception=(exc_type, exc_value, exc_tb)).critical("Uncaught exception")
		except Exception:
			try:
				sys.stderr.write("Uncaught exception:\n")
				traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)
			except Exception:
				pass

	def _thread_hook(args):
		try:
			thread_name = getattr(args.thread, "name", "unknown")
			logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).critical(
				f"[_thread_hook] - uncaught_thread_exception - thread={thread_name}"
			)
		except Exception:
			try:
				sys.stderr.write("Uncaught thread exception:\n")
				traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=sys.stderr)
			except Exception:
				pass

	sys.excepthook = _sys_hook
	threading.excepthook = _thread_hook


def _parse_level(level_value) -> str:
	"""
	Accepts:
	- int (logging.INFO style)
	- str ("INFO")
	Returns a Loguru level name.
	"""
	if isinstance(level_value, int):
		mapping = {
			logging.CRITICAL: "CRITICAL",
			logging.ERROR: "ERROR",
			logging.WARNING: "WARNING",
			logging.INFO: "INFO",
			logging.DEBUG: "DEBUG",
		}
		return mapping.get(level_value, "INFO")

	if isinstance(level_value, str):
		val = level_value.strip().upper()
		if val in ("TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"):
			return val

	return "INFO"


def setup_logging(
	app_name: str = "app",
	log_dir: str = "log",
	log_level: str | int | None = None,
	file_level: str | int | None = None,
) -> None:
	"""
	Loguru config similar to your reference script:
	- console colored
	- rotating file (10 MB) with zip compression
	- retention count (50 files)
	- custom level colors
	"""

	configured_level = log_level if log_level is not None else os.getenv("LOG_LEVEL", "INFO")
	console_level = _parse_level(configured_level)
	configured_file_level = file_level if file_level is not None else os.getenv("LOG_FILE_LEVEL", DEFAULT_FILE_LEVEL)
	resolved_file_level = _parse_level(configured_file_level)

	if not os.path.exists(log_dir):
		os.makedirs(log_dir)

	log_path = os.path.join(log_dir, f"{app_name}.log")

	logger.remove()

	# Configure sinks similar to your `logger.configure(**config)` pattern
	logger.configure(
		handlers=[
			{
				"sink": sys.stdout,
				"format": LOG_FORMAT,
				"colorize": True,
				"level": console_level,
			},
			{
				"sink": log_path,
				"format": LOG_FORMAT,
				"rotation": "10 MB",
				"compression": "zip",
				"retention": 50,      # keep 50 rotated files
				"colorize": False,
				"level": resolved_file_level,
			},
		]
	)

	# In-memory sink for UI error popups (all ERROR/CRITICAL records).
	logger.add(_error_popup_sink, level="ERROR", catch=True, enqueue=True, format="{message}")
	_install_global_exception_hooks()

	# Define/override level colors (Loguru default exists, but you want explicit)
	logger.level("ERROR", color="<fg #ff0000>")
	logger.level("WARNING", color="<fg #f9ff5c>")
	logger.level("INFO", color="<cyan>")
	logger.level("DEBUG", color="<fg #1cfc03>")
	logger.level("CRITICAL", color="<fg #960000>")
	logger.level("TRACE", color="<white>")
	logger.level("SUCCESS", color="<fg #00ff22>")

	logger.info(
		f"[setup_logging] - logger_initialized - app_name={app_name} console_level={console_level} file_level={resolved_file_level} log_path={log_path}"
	)


def get_log_file_path(app_name: str = "app", log_dir: str = "log") -> str:
	return os.path.join(log_dir, f"{app_name}.log")


def read_log_tail(*, app_name: str = "app", log_dir: str = "log", max_lines: int = 400) -> str:
	path = get_log_file_path(app_name=app_name, log_dir=log_dir)
	if not os.path.exists(path):
		return f"Log file not found: {path}"
	try:
		with open(path, "r", encoding="utf-8", errors="replace") as f:
			lines = f.readlines()
		return "".join(lines[-max(1, int(max_lines)):])
	except Exception as ex:
		return f"Failed reading log file: {ex}"


def get_logger(component: str):
	return logger.bind(component=component)


def summarize_for_log(payload: Any, *, max_items: int = 10, max_text: int = 140) -> Any:
	if payload is None:
		return None
	if isinstance(payload, dict):
		items = list(payload.items())[:max_items]
		return {str(k): summarize_for_log(v, max_items=max_items, max_text=max_text) for k, v in items}
	if isinstance(payload, (list, tuple, set)):
		limited = list(payload)[:max_items]
		return [summarize_for_log(v, max_items=max_items, max_text=max_text) for v in limited]
	text = str(payload)
	if len(text) > max_text:
		return f"{text[:max_text]}...({len(text)} chars)"
	return text


@contextmanager
def log_timing(method_name: str, **context: Any):
	start = time.perf_counter()
	context_txt = " ".join([f"{k}={summarize_for_log(v)}" for k, v in context.items()])
	logger.debug(f"[{method_name}] - start {context_txt}".strip())
	try:
		yield
		duration_ms = round((time.perf_counter() - start) * 1000, 2)
		logger.debug(f"[{method_name}] - end - duration_ms={duration_ms} {context_txt}".strip())
	except Exception:
		duration_ms = round((time.perf_counter() - start) * 1000, 2)
		logger.exception(f"[{method_name}] - failed - duration_ms={duration_ms} {context_txt}".strip())
		raise
