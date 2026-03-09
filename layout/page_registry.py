from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from nicegui import ui

from layout.action_bar.models import Action
from layout.context import PageContext


RenderFn = Callable[[ui.element, PageContext], None]
OnEnterFn = Callable[[PageContext], None]


@dataclass(frozen=True)
class PageDefinition:
    key: str
    label: str
    icon: str
    render: RenderFn
    actions: list[Action] = field(default_factory=list)
    on_enter: OnEnterFn | None = None
    always_visible: bool = False
    roles: tuple[str, ...] = ()


_PAGE_REGISTRY: dict[str, PageDefinition] = {}


def register_page(definition: PageDefinition) -> PageDefinition:
    _PAGE_REGISTRY[definition.key] = definition
    return definition


def register_pages(*definitions: PageDefinition) -> None:
    for definition in definitions:
        register_page(definition)


def get_registered_pages() -> dict[str, PageDefinition]:
    return dict(_PAGE_REGISTRY)


def get_registered_page(key: str) -> PageDefinition | None:
    return _PAGE_REGISTRY.get(str(key or ""))
