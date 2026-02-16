# layout/modal_manager.py
from __future__ import annotations

import queue
from typing import Any, Optional, List, Dict
from services.worker_topics import WorkerTopics
from nicegui import ui


class ModalManager(object):
    """
    Single-client modal manager.

    Supports:
    - type="confirm": returns bool via ui.modal.response
    - type="input": returns {"ok": bool, "value": str} via ui.modal.response
    - type="message": no waiting, optional buttons that emit ui.modal.response as events
    - close: ui.modal.close with {"key": "..."} closes the modal if active

    One active modal at a time.
    """

    def __init__(self, worker_bus: Any) -> None:
        self._bus = worker_bus
        self._sub_req = self._bus.subscribe(WorkerTopics.TOPIC_MODAL_REQUEST)
        self._sub_close = self._bus.subscribe(WorkerTopics.TOPIC_MODAL_CLOSE)

        self._active: Optional[Dict[str, Any]] = None  # active request payload
        self._active_key: Optional[str] = None

        self._dlg = ui.dialog()
        with self._dlg:
            with ui.card().classes("w-[560px] max-w-[95vw]"):
                self._title = ui.label("").classes("text-lg font-semibold")
                self._msg = ui.label("").classes("text-base whitespace-pre-wrap mt-2")

                self._input_text = ui.input(label="").classes("w-full mt-3")
                self._input_text.visible = False

                self._input_number = ui.number(label="").classes("w-full mt-3")
                self._input_number.visible = False

                self._select = ui.select(options={}, label="").classes("w-full mt-3")
                self._select.visible = False

                # input row (hidden unless type=input)
                self._input = ui.input(label="").classes("w-full mt-3")
                self._input.visible = False

                with ui.row().classes("w-full justify-end gap-2 mt-4"):
                    self._btn_secondary = ui.button("", on_click=self._on_secondary).props("outline")
                    self._btn_primary = ui.button("", on_click=self._on_primary)

        ui.timer(0.1, self._poll)

    def _hide_inputs(self) -> None:
        self._input_text.visible = False
        self._input_number.visible = False
        self._select.visible = False

    def _poll(self) -> None:
        # close requests have priority
        self._poll_close()

        # only open new modal if none active
        if self._active is not None:
            return

        try:
            msg = self._sub_req.queue.get_nowait()
        except queue.Empty:
            return

        payload = getattr(msg, "payload", None) or {}
        if not isinstance(payload, dict) or not payload:
            return

        m_type = str(payload.get("type") or "confirm")
        key = str(payload.get("key") or "").strip()
        if not key:
            return

        # For confirm/input, require request_id+chain_id so result can be routed back
        if m_type in ("confirm", "input"):
            if not payload.get("request_id") or not payload.get("chain_id"):
                return

        self._active = payload
        self._active_key = key

        title = str(payload.get("title") or "Message")
        message = str(payload.get("message") or "")

        self._title.set_text(title)
        self._msg.set_text(message)

        # configure UI by type
        if m_type == "confirm":
            self._input.visible = False
            self._btn_primary.set_text(str(payload.get("ok_text") or "OK"))
            self._btn_secondary.set_text(str(payload.get("cancel_text") or "Cancel"))
            self._btn_secondary.visible = True

        elif m_type == "input":
            self._hide_inputs()

            kind = str(payload.get("kind") or "text")  # text|number|select

            ok_text = str(payload.get("ok_text") or "OK")
            cancel_text = str(payload.get("cancel_text") or "Cancel")
            self._btn_primary.set_text(ok_text)
            self._btn_secondary.set_text(cancel_text)
            self._btn_secondary.visible = True

            placeholder = str(payload.get("placeholder") or "")
            default = payload.get("default")

            if kind == "number":
                self._input_number.visible = True
                try:
                    self._input_number.label = placeholder
                except Exception:
                    pass
                try:
                    self._input_number.set_value(default if default is not None else None)
                except Exception:
                    self._input_number.set_value(None)

            elif kind == "select":
                self._select.visible = True
                try:
                    self._select.label = placeholder
                except Exception:
                    pass

                # options can be list[str] or list[{"id":..,"text":..}]
                raw = payload.get("options") or []
                opts = {}

                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            oid = str(item.get("id") or "")
                            txt = str(item.get("text") or oid)
                            if oid:
                                opts[oid] = txt
                        else:
                            s = str(item)
                            if s:
                                opts[s] = s

                self._select.options = opts
                try:
                    self._select.set_value(str(default) if default is not None else "")
                except Exception:
                    self._select.set_value("")

            else:
                # text
                self._input_text.visible = True
                try:
                    self._input_text.label = placeholder
                except Exception:
                    pass
                try:
                    self._input_text.set_value("" if default is None else str(default))
                except Exception:
                    self._input_text.set_value("")

        elif m_type == "message":
            self._input.visible = False
            buttons = payload.get("buttons") or []
            if not isinstance(buttons, list):
                buttons = []
            # defaults
            self._primary_btn_id = "ok"
            self._secondary_btn_id = None
            primary_text = "OK"
            secondary_text = ""
            if len(buttons) >= 1 and isinstance(buttons[0], dict):
                self._primary_btn_id = str(buttons[0].get("id") or "primary")
                primary_text = str(buttons[0].get("text") or primary_text)
            if len(buttons) >= 2 and isinstance(buttons[1], dict):
                self._secondary_btn_id = str(buttons[1].get("id") or "secondary")
                secondary_text = str(buttons[1].get("text") or "")
            self._btn_primary.set_text(primary_text)
            if secondary_text:
                self._btn_secondary.set_text(secondary_text)
                self._btn_secondary.visible = True
            else:
                self._btn_secondary.visible = False
        self._dlg.open()

    def _poll_close(self) -> None:
        """
        Process ui.modal.close messages.

        Supports:
        - close_active=True  -> closes whatever modal is currently open
        - key="some_key"     -> closes only if the active modal key matches
        """
        while True:
            try:
                msg = self._sub_close.queue.get_nowait()
            except queue.Empty:
                break

            payload = getattr(msg, "payload", None) or {}
            if not isinstance(payload, dict):
                continue

            # If caller requests to close whatever is open, do it.
            if bool(payload.get("close_active", False)):
                if self._active is not None:
                    try:
                        self._dlg.close()
                    except Exception:
                        pass
                    self._active = None
                    self._active_key = None
                continue

            # Otherwise close only by matching key
            key = str(payload.get("key") or "").strip()
            if not key:
                continue

            if self._active_key == key and self._active is not None:
                try:
                    self._dlg.close()
                except Exception:
                    pass
                self._active = None
                self._active_key = None

    def _publish_response(self, result: Any) -> None:
        req = self._active or {}
        m_type = str(req.get("type") or "confirm")

        # clear active first
        self._active = None
        self._active_key = None

        # confirm/input + message-button events can publish a response
        request_id = req.get("request_id")
        chain_id = req.get("chain_id")

        # For message, request_id/chain_id may be absent; still publish as an event if present
        payload = {
            "type": m_type,
            "key": str(req.get("key") or ""),
            "result": result,
        }
        if request_id:
            payload["request_id"] = str(request_id)
        if chain_id:
            payload["chain_id"] = str(chain_id)

        self._bus.publish(
            topic=WorkerTopics.TOPIC_MODAL_RESPONSE,
            source="ui",
            source_id="ui",
            **payload
        )

    def _on_primary(self) -> None:
        req = self._active or {}
        m_type = str(req.get("type") or "confirm")

        try:
            self._dlg.close()
        except Exception:
            pass

        if m_type == "confirm":
            self._publish_response(True)
            return

        if m_type == "input":
            kind = str(req.get("kind") or "text")

            if kind == "number":
                val = None
                try:
                    val = self._input_number.value
                except Exception:
                    val = None
                self._publish_response({"ok": True, "value": val})
                return

            if kind == "select":
                val = ""
                try:
                    val = str(self._select.value or "")
                except Exception:
                    val = ""
                self._publish_response({"ok": True, "value": val})
                return

            # text
            val = ""
            try:
                val = str(self._input_text.value or "")
            except Exception:
                val = ""
            self._publish_response({"ok": True, "value": val})
            return

        # message
        btn_id = self._primary_btn_id or "primary"
        self._publish_response({"clicked": btn_id})

    def _on_secondary(self) -> None:
        req = self._active or {}
        m_type = str(req.get("type") or "confirm")

        try:
            self._dlg.close()
        except Exception:
            pass

        if m_type == "confirm":
            self._publish_response(False)
            return

        if m_type == "input":
            self._publish_response({"ok": False})
            return

        btn_id = self._secondary_btn_id or "secondary"
        self._publish_response({"clicked": btn_id})


def install_modal_manager(worker_bus: Any) -> ModalManager:
    return ModalManager(worker_bus)
