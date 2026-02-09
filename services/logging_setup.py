from __future__ import annotations

import logging
import os
import sys
from loguru import logger


LOG_FORMAT = (
	"{level.icon} <green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
	"<blue>{thread.name:^10}-{thread.id:^8}</blue> | "
	"[<level>{level:<8}</level>] | "
	"<white>{name}.{function}:{line}</white> | "
	"<level>{message}</level>"
)


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
	log_level: str | int = "INFO",
) -> None:
	"""
	Loguru config similar to your reference script:
	- console colored
	- rotating file (10 MB) with zip compression
	- retention count (50 files)
	- custom level colors
	"""

	level = _parse_level(log_level)

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
				"level": level,
			},
			{
				"sink": log_path,
				"format": LOG_FORMAT,
				"rotation": "10 MB",
				"compression": "zip",
				"retention": 50,      # keep 50 rotated files
				"colorize": False,
				"level": level,
			},
		]
	)

	# Define/override level colors (Loguru default exists, but you want explicit)
	logger.level("ERROR", color="<fg #ff0000>")
	logger.level("WARNING", color="<fg #f9ff5c>")
	logger.level("INFO", color="<cyan>")
	logger.level("DEBUG", color="<fg #1cfc03>")
	logger.level("CRITICAL", color="<fg #960000>")
	logger.level("TRACE", color="<white>")
	logger.level("SUCCESS", color="<fg #00ff22>")

	logger.info("Logger initialized")
