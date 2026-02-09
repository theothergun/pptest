from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar

from nicegui import ui

from pages.utils.scroll_fx import ScrollFx, generate_wrapper_id

T = TypeVar("T")


@dataclass(frozen=True)
class ExpandableList(Generic[T]):
    """
    Practical runtime helper that wires toggle/delete and refresh.

    You create one instance per page, and call .render(...) inside your refreshable.

    Page provides:
      - items
      - key extractor
      - summary/editor render fns
      - delete handler
      - refresh function (usually the refreshable itself)
    """

    scroller_id: str
    id_prefix: str
    expanded_storage_key: str
    get_key: Callable[[T], str]
    fx: Optional[ScrollFx] = None

    def _fx(self) -> ScrollFx:
        return self.fx or ScrollFx(scroller_id=self.scroller_id)

    def get_expanded_key(self) -> Optional[str]:
        return ui.context.client.storage.get(self.expanded_storage_key)

    def set_expanded_key(self, key: Optional[str]) -> None:
        ui.context.client.storage[self.expanded_storage_key] = key

    def toggle(self, key: str) -> None:
        current = self.get_expanded_key()
        self.set_expanded_key(None if current == key else key)

    def row_wrapper_id(self, key: str) -> str:
        return generate_wrapper_id(self.id_prefix, key)

    def render(
        self,
        items: list[T],
        *,
        render_summary: Callable[[T, int, Callable[[], None], Callable[[], None]], None],
        render_editor: Callable[[T, int, Callable[[], None], Callable[[], None]], None],
        on_delete: Callable[[int], None],
        refresh: Callable[[], None],
        scroll_to: str | None = None,
        highlight: str | None = None,
    ) -> None:
        expanded = self.get_expanded_key()
        fx = self._fx()
        client = ui.context.client

        for idx, item in enumerate(items):
            k = self.get_key(item)
            wid = self.row_wrapper_id(k)
            is_open = (expanded == k)

            def _toggle(k=k) -> None:
                self.toggle(k)
                refresh()

            def _delete(i=idx, k=k) -> None:
                # if deleting the open row, close it
                if self.get_expanded_key() == k:
                    self.set_expanded_key(None)
                on_delete(i)
                refresh()

            with ui.element("div").props(f"id={wid}").classes("w-full"):
                with ui.card().classes("w-full p-3"):
                    if is_open:
                        render_editor(item, idx, _toggle, _delete)
                    else:
                        render_summary(item, idx, _toggle, _delete)

            if scroll_to == wid:
                js = fx.js(wid, highlight=(highlight == wid))
                ui.timer(0.05, lambda c=client, j=js: c.run_javascript(j), once=True)
