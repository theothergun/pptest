from __future__ import annotations

from enum import StrEnum


class WorkerTopics(StrEnum):
	"""
	Allowed topics for ALL workers.

	Payload contracts:

	ERROR:
		{ "key": str | None, "action": str, "error": str }

	CLIENT_CONNECTED:
		{ }

	CLIENT_DISCONNECTED:
		{ "reason": str }

	VALUE_CHANGED:
		{ "key": str, "value": Any }

	WRITE_FINISHED:
		{ "key": str }

	WRITE_ERROR:
		{ "key": str | None, "error": str, "action": "write" }
	"""

	ERROR = "ERROR"
	CLIENT_CONNECTED = "CLIENT_CONNECTED"
	CLIENT_DISCONNECTED = "CLIENT_DISCONNECTED"
	VALUE_CHANGED = "VALUE_CHANGED"
	WORKER_STATUS_CHANGED = "WORKER_STATUS_CHANGED"
	WRITE_FINISHED = "WRITE_FINISHED"
	WRITE_ERROR = "WRITE_ERROR"
