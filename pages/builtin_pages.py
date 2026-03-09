from __future__ import annotations

from layout.action_bar.models import Action
from layout.page_registry import PageDefinition, register_pages


_INITIALIZED = False


def register_builtin_pages() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    from pages import docs_viewer, errors
    from pages.page_designer import render as render_page_designer
    from pages.settings import settings_page

    register_pages(
        PageDefinition(
            key="errors",
            label="Errors",
            icon="warning",
            render=errors.render,
            actions=[
                Action(id="acknowledge", text="Acknowledge", icon="check", default_color="primary"),
                Action(id="clear_all", text="Clear All", icon="delete", default_color="primary", is_active=True),
                Action(id="add_random", text="Generate Test Error", icon="add", default_color="secondary"),
            ],
        ),
        PageDefinition(
            key="docs",
            label="Docs",
            icon="menu_book",
            render=docs_viewer.render,
        ),
        PageDefinition(
            key="settings",
            label="Settings",
            icon="settings",
            render=settings_page.render,
            actions=[Action(id="apply", text="Apply", icon="check", default_color="positive")],
        ),
        PageDefinition(
            key="page_designer",
            label="Page Designer",
            icon="construction",
            render=render_page_designer,
            roles=("admin",),
        ),
    )
    _INITIALIZED = True
