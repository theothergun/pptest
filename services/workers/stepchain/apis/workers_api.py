from __future__ import annotations

from typing import Any

from services.worker_commands import TcpClientCommands, TwinCatCommands


class WorkersApi:
    """Simple worker I/O helpers for non-programmer StepChain scripts."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    # --------------------------- generic reads ---------------------------
    def get(self, worker: str, source_id: str, key: str, default: Any = None) -> Any:
        payload = self._ctx.data.get(str(worker), {}).get(str(source_id))
        if isinstance(payload, dict) and payload.get("key") == str(key):
            return payload.get("value", default)

        # Fallback: scan this worker/source cache for the requested key.
        source_data = self._ctx.data.get(str(worker), {})
        for entry in source_data.values():
            if isinstance(entry, dict) and entry.get("key") == str(key):
                return entry.get("value", default)
        return default

    def latest(self, worker: str, source_id: str, default: Any = None) -> Any:
        payload = self._ctx.data.get(str(worker), {}).get(str(source_id), default)
        if isinstance(payload, dict) and "value" in payload:
            return payload.get("value", default)
        return payload

    # --------------------------- TCP helpers ----------------------------
    def tcp_send(self, client_id: str, data: Any) -> None:
        if not callable(getattr(self._ctx, "send_cmd", None)):
            return
        self._ctx.send_cmd("tcp_client", TcpClientCommands.SEND, {
            "client_id": str(client_id),
            "data": data,
        })

    def tcp_connect(self, client_id: str) -> None:
        if not callable(getattr(self._ctx, "send_cmd", None)):
            return
        self._ctx.send_cmd("tcp_client", TcpClientCommands.CONNECT, {
            "client_id": str(client_id),
        })

    def tcp_disconnect(self, client_id: str) -> None:
        if not callable(getattr(self._ctx, "send_cmd", None)):
            return
        self._ctx.send_cmd("tcp_client", TcpClientCommands.DISCONNECT, {
            "client_id": str(client_id),
        })

    def tcp_message(self, client_id: str, default: Any = None, decode: bool = True, encoding: str = "utf-8") -> Any:
        value = self.get("tcp_client", str(client_id), "message", default)
        if decode and isinstance(value, (bytes, bytearray)):
            try:
                return bytes(value).decode(encoding, errors="replace")
            except Exception:
                return default
        return value

    # -------------------------- TwinCAT helpers -------------------------
    def plc_write(self, client_id: str, name: str, value: Any) -> None:
        if not callable(getattr(self._ctx, "send_cmd", None)):
            return
        self._ctx.send_cmd("twincat", TwinCatCommands.WRITE, {
            "client_id": str(client_id),
            "name": str(name),
            "value": value,
        })

    def plc_value(self, client_id: str, name: str, default: Any = None) -> Any:
        return self.get("twincat", str(client_id), str(name), default)
