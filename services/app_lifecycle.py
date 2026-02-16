from __future__ import annotations

import os
import sys
import threading
import time


def request_app_restart(delay_s: float = 0.8) -> None:
	"""
	Restart current Python process after a short delay.

	Uses os.execv to replace the running process with the same command line.
	If execv fails, exits the process so an external supervisor can restart it.
	"""
	def _restart() -> None:
		time.sleep(max(0.0, float(delay_s)))
		try:
			exe = sys.executable
			argv = [exe, *sys.argv]
			os.execv(exe, argv)
		except Exception:
			os._exit(0)

	threading.Thread(target=_restart, daemon=True, name="app-restart").start()

