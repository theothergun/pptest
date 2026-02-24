from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path


class BarfiBridge:
    """Manage a background Streamlit + Barfi process for the NiceGUI app."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._port = 8501

    def is_running(self) -> bool:
        with self._lock:
            if self._proc is None:
                return False
            if self._proc.poll() is not None:
                self._proc = None
                return False
            return True

    def _port_open(self, host: str = "127.0.0.1") -> bool:
        try:
            with socket.create_connection((host, self._port), timeout=0.25):
                return True
        except OSError:
            return False

    def get_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def start(self, port: int = 8501) -> str:
        with self._lock:
            self._port = int(port)
            if self._proc is not None and self._proc.poll() is None:
                return self.get_url()

            repo_root = Path(__file__).resolve().parent.parent
            app_path = repo_root / "tools" / "barfi_studio.py"
            env = os.environ.copy()
            env["BARFI_EXPORT_DIR"] = str(repo_root / "scripts" / "barfi_generated")

            self._proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(app_path),
                    "--server.port",
                    str(self._port),
                    "--server.address",
                    "0.0.0.0",
                    "--server.headless",
                    "true",
                    "--browser.gatherUsageStats",
                    "false",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(repo_root),
                env=env,
            )
            return self.get_url()

    def stop(self) -> None:
        with self._lock:
            if self._proc is None:
                return
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=2)
            self._proc = None


BARFI_BRIDGE = BarfiBridge()
