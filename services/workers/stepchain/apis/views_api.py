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
	def __init__(self, ctx: Any, *, cmd_key: str) -> None:
		self._ctx = ctx
		self._ui = UiApi(ctx)
		self._cmd_key = str(cmd_key or "").strip()

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


class PackagingViewApi(_BaseViewApi):
	def __init__(self, ctx: Any) -> None:
		super().__init__(ctx, cmd_key="packaging.cmd")

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
		super().__init__(ctx, cmd_key="packaging.cmd")

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
		super().__init__(ctx, cmd_key="container_management.cmd")

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
		self.packaging = PackagingViewApi(ctx)
		self.packaging_nox = PackagingNoxViewApi(ctx)
		self.container_management = ContainerManagementViewApi(ctx)
		self.packagin = self.packaging  # alias (requested)
