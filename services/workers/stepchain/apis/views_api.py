# services/workers/stepchain/apis/views_api.py
from __future__ import annotations

from typing import Any, Iterable, Optional

from services.workers.stepchain.apis.ui_api import UiApi


def _as_list(value: Any) -> list:
	if value is None:
		return []
	if isinstance(value, list):
		return value
	return list(value) if isinstance(value, (tuple, set)) else [value]


class _BaseViewApi:
	def __init__(self, ctx: Any, *, cmd_key: str, view_id: str = "") -> None:
		self._ctx = ctx
		self._ui = UiApi(ctx)
		self._cmd_key = str(cmd_key or "").strip()
		self._view_id = str(view_id or "").strip()

	def set_state(self, key: str, value: Any) -> None:
		self._ui.set_state(key, value)

	def set_state_many(self, **values: Any) -> None:
		self._ui.set_state_many(**values)

	def get_state(self, key: str, default: Any = None) -> Any:
		try:
			return self._ctx._app_state.get(str(key), default)
		except Exception:
			return default

	def consume_cmd(
		self,
		*,
		value_field: str = "cmd",
		dedupe: bool = True,
		normalize: bool = True,
	) -> Optional[str]:
		if not self._cmd_key:
			return None
		return self._ui.consume_command(
			self._cmd_key,
			value_field=value_field,
			dedupe=dedupe,
			normalize=normalize,
		)

	def consume_payload(self, *, dedupe: bool = True) -> Optional[dict]:
		if not self._cmd_key:
			return None
		return self._ui.consume_payload(self._cmd_key, dedupe=dedupe)

	def wait_cmd(
		self,
		expected: Optional[Iterable[str]] = None,
		*,
		step_desc: str = "Waiting for operator...",
		normalize: bool = True,
	) -> Optional[str]:
		cmd = self.consume_cmd(normalize=normalize)
		if cmd is None:
			try:
				self._ctx.step_desc = str(step_desc or "")
			except Exception:
				pass
			return None

		if expected is None:
			return cmd

		expected_list = [str(x or "").lower() for x in _as_list(expected)]
		return cmd if cmd in expected_list else None

	def _resolve_button_state_key(self, button_key: str) -> str:
		raw = str(button_key or "").strip()
		if not raw:
			return ""
		if raw.startswith("view.button."):
			raw = raw[len("view.button."):]
		if "." in raw:
			return raw
		if self._view_id:
			return f"{self._view_id}.{raw}"
		return raw

	def _normalize_enabled(self, value: Any) -> bool:
		if isinstance(value, bool):
			return value
		v = str(value or "").strip().lower()
		if v in ("disable", "disabled", "off", "0", "false", "no"):
			return False
		if v in ("enable", "enabled", "on", "1", "true", "yes"):
			return True
		return bool(value)

	def set_button_enabled(self, button_key: str, enabled: Any) -> None:
		resolved = self._resolve_button_state_key(button_key)
		if not resolved:
			return
		state = self.get_state("view_button_states", {})
		state_dict = dict(state) if isinstance(state, dict) else {}
		state_dict[resolved] = self._normalize_enabled(enabled)
		self.set_state("view_button_states", state_dict)

	def set_buttons_enabled(self, mapping: dict[str, Any]) -> None:
		if not isinstance(mapping, dict):
			return
		state = self.get_state("view_button_states", {})
		state_dict = dict(state) if isinstance(state, dict) else {}
		for key, value in mapping.items():
			resolved = self._resolve_button_state_key(str(key))
			if not resolved:
				continue
			state_dict[resolved] = self._normalize_enabled(value)
		self.set_state("view_button_states", state_dict)

	def set_operator_device_panel_visible(self, visible: bool) -> None:
		self.set_state("operator_show_device_panel", bool(visible))

	def set_operator_device_states(self, items: list[dict[str, Any]]) -> None:
		out: list[dict[str, Any]] = []
		for item in items or []:
			if not isinstance(item, dict):
				continue
			name = str(item.get("name") or "").strip()
			if not name:
				continue
			out.append({
				"name": name,
				"status": str(item.get("status") or ""),
				"state": str(item.get("state") or "info"),
				"connected": bool(item.get("connected", True)),
				"source": str(item.get("source") or ""),
			})
		self.set_state("operator_device_panel_items", out)

	def upsert_operator_device_state(
		self,
		*,
		name: str,
		status: str = "",
		state: str = "info",
		connected: Optional[bool] = None,
		source: str = "",
	) -> None:
		n = str(name or "").strip()
		if not n:
			return
		raw = self.get_state("operator_device_panel_items", [])
		items = list(raw) if isinstance(raw, list) else []
		target_index = -1
		for i, item in enumerate(items):
			if isinstance(item, dict) and str(item.get("name") or "").strip() == n:
				target_index = i
				break
		entry = {
			"name": n,
			"status": str(status or ""),
			"state": str(state or "info"),
			"connected": True if connected is None else bool(connected),
			"source": str(source or ""),
		}
		if target_index >= 0:
			items[target_index] = entry
		else:
			items.append(entry)
		self.set_state("operator_device_panel_items", items)

	def clear_operator_device_states(self) -> None:
		self.set_state("operator_device_panel_items", [])


class PackagingViewApi(_BaseViewApi):
	def __init__(self, ctx: Any) -> None:
		super().__init__(ctx, cmd_key="packaging.cmd", view_id="packaging")

	def set_container_number(self, value: str) -> None:
		self.set_state("container_number", value)

	def set_part_number(self, value: str) -> None:
		self.set_state("part_number", value)

	def set_description(self, value: str) -> None:
		self.set_state("description", value)

	def set_current_qty(self, value: Any) -> None:
		self.set_state("current_container_qty", value)

	def set_max_qty(self, value: Any) -> None:
		self.set_state("max_container_qty", value)

	def set_last_serial_number(self, value: str) -> None:
		self.set_state("last_serial_number", value)

	def set_form(
		self,
		*,
		container_number: str | None = None,
		part_number: str | None = None,
		description: str | None = None,
		current_qty: Any = None,
		max_qty: Any = None,
		last_serial_number: str | None = None,
	) -> None:
		patch: dict[str, Any] = {}
		if container_number is not None:
			patch["container_number"] = container_number
		if part_number is not None:
			patch["part_number"] = part_number
		if description is not None:
			patch["description"] = description
		if current_qty is not None:
			patch["current_container_qty"] = current_qty
		if max_qty is not None:
			patch["max_container_qty"] = max_qty
		if last_serial_number is not None:
			patch["last_serial_number"] = last_serial_number
		if patch:
			self.set_state_many(**patch)


class PackagingNoxViewApi(_BaseViewApi):
	def __init__(self, ctx: Any) -> None:
		super().__init__(ctx, cmd_key="packaging.cmd", view_id="packaging_nox")

	def set_container_number(self, value: str) -> None:
		self.set_state("container_number", value)

	def set_part_number(self, value: str) -> None:
		self.set_state("part_number", value)

	def set_description(self, value: str) -> None:
		self.set_state("description", value)

	def set_current_qty(self, value: Any) -> None:
		self.set_state("current_container_qty", value)

	def set_max_qty(self, value: Any) -> None:
		self.set_state("max_container_qty", value)

	def set_totals(self, *, good: Any = None, bad: Any = None) -> None:
		patch: dict[str, Any] = {}
		if good is not None:
			patch["part_good"] = good
		if bad is not None:
			patch["part_bad"] = bad
		if patch:
			self.set_state_many(**patch)

	def show_instruction(
		self,
		*,
		instruction: Optional[str] = None,
		feedback: Optional[str] = None,
		instruction_state: Optional[int | str] = None,
		feedback_state: Optional[int | str] = None,
	) -> None:
		self._ui.show(
			instruction=instruction,
			feedback=feedback,
			instruction_state=instruction_state,
			feedback_state=feedback_state,
		)


class ContainerManagementViewApi(_BaseViewApi):
	def __init__(self, ctx: Any) -> None:
		super().__init__(ctx, cmd_key="container_management.cmd", view_id="container_management")

	def set_search_query(self, value: str) -> None:
		self.set_state("container_mgmt_search_query", value)

	def set_container_selected(self, value: str) -> None:
		self.set_state("container_mgmt_container_selected", value)

	def set_active_container(self, value: str) -> None:
		self.set_state("container_mgmt_active_container", value)

	def set_container_rows(self, rows: list[dict[str, Any]]) -> None:
		self.set_state("container_mgmt_container_rows", rows or [])

	def set_serial_rows(self, rows: list[dict[str, Any]]) -> None:
		self.set_state("container_mgmt_serial_rows", rows or [])

	def set_tables(
		self,
		*,
		container_rows: Optional[list[dict[str, Any]]] = None,
		serial_rows: Optional[list[dict[str, Any]]] = None,
	) -> None:
		patch: dict[str, Any] = {}
		if container_rows is not None:
			patch["container_mgmt_container_rows"] = container_rows
		if serial_rows is not None:
			patch["container_mgmt_serial_rows"] = serial_rows
		if patch:
			self.set_state_many(**patch)


class ViewsApi:
	def __init__(self, ctx: Any) -> None:
		self._ctx = ctx
		self.packaging = PackagingViewApi(ctx)
		self.packaging_nox = PackagingNoxViewApi(ctx)
		self.container_management = ContainerManagementViewApi(ctx)
		self.packagin = self.packaging  # alias (requested)

	def set_button_enabled(self, button_key: str, enabled: Any) -> None:
		self.packaging_nox.set_button_enabled(button_key, enabled)

	def set_buttons_enabled(self, mapping: dict[str, Any]) -> None:
		self.packaging_nox.set_buttons_enabled(mapping)

	def set_operator_device_panel_visible(self, visible: bool) -> None:
		self.packaging_nox.set_operator_device_panel_visible(visible)

	def set_operator_device_states(self, items: list[dict[str, Any]]) -> None:
		self.packaging_nox.set_operator_device_states(items)

	def upsert_operator_device_state(
		self,
		*,
		name: str,
		status: str = "",
		state: str = "info",
		connected: Optional[bool] = None,
		source: str = "",
	) -> None:
		self.packaging_nox.upsert_operator_device_state(
			name=name,
			status=status,
			state=state,
			connected=connected,
			source=source,
		)

	def clear_operator_device_states(self) -> None:
		self.packaging_nox.clear_operator_device_states()
