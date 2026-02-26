from nicegui import ui, app

from layout.context import PageContext
from layout.router import get_visible_routes, navigate, Route
from services.app_config import get_app_config


@ui.refreshable
def _render_drawer_content(ctx: PageContext) -> None:
    """Rebuild the drawer buttons from current visible routes."""
    ctx.nav_buttons.clear()
    ctx.drawer_content.clear()
    active_key = app.storage.user.get("current_route", "")
    routes = get_visible_routes()
    if ctx.dummy_controller.is_feature_enabled():
        routes["start_dummy_test"] = Route(icon="rocket_launch", label="Dummy Test")

    with ctx.drawer_content:
        with ui.column().classes("w-full p-2 gap-1"):
            for key, route in routes.items():
                if key == "errors":
                    btn = _add_error_button(ctx, route, key)
                elif key == "start_dummy_test":
                    btn = _add_dummy_test_button(ctx, route, key)
                else:
                    btn = _add_standard_button(ctx, route, key)

                if key == active_key:
                    btn.classes(add="app-nav-item-active")
                    btn.props("unelevated color=primary")
                else:
                    btn.props("flat color=grey-7")


def build_drawer(ctx: PageContext) -> ui.left_drawer:
    hide_on_startup = bool(getattr(get_app_config().ui.navigation, "hide_nav_on_startup", False))
    drawer = ui.left_drawer(value=not hide_on_startup, bordered=True).props("width=220").classes(
        "app-drawer border-r border-[var(--input-border)]"
    )
    ctx.drawer = drawer

    with drawer:
        ctx.drawer_content = ui.column().classes("w-full")
        _render_drawer_content(ctx)

    def refresh_drawer() -> None:
        _render_drawer_content.refresh(ctx)

    ctx.refresh_drawer = refresh_drawer
    return drawer


def _add_standard_button(ctx: PageContext, route: Route, key: str):
    btn = ui.button(route.label, icon=route.icon, on_click=lambda k=key: navigate(ctx, k)).props(
        "flat no-caps align=left"
    ).classes("w-full app-nav-item")
    ctx.nav_buttons[key] = btn
    return btn


def _add_error_button(ctx: PageContext, route: Route, key: str):
    with ui.row().classes("w-full items-center"):
        btn = ui.button(on_click=lambda k=key: navigate(ctx, k)).props("flat no-caps align=left").classes(
            "w-full app-nav-item px-3"
        )

        with btn:
            with ui.row().classes("items-center gap-2 no-wrap"):
                with ui.element("div").classes("relative inline-flex") as icon_wrap:
                    ui.icon(route.icon)
                    errors_badge = ui.badge().props("color=negative").classes(
                        "absolute -top-3 -right-2 text-[11px] min-w-[16px] h-[16px] flex items-center justify-center"
                    )
                    errors_badge.classes(add="error-badge-pulse")
                    errors_badge.bind_text_from(ctx.state, "error_count", backward=lambda n: str(n))
                    errors_badge.bind_visibility_from(ctx.state, "error_count", backward=lambda n: int(n) > 0)
            ui.label(route.label)

        ctx.errors_icon_wrap = icon_wrap
        ctx.nav_buttons[key] = btn
    return btn


def _add_dummy_test_button(ctx: PageContext, route: Route, key: str):
    btn = ui.button(route.label, icon=route.icon, on_click=ctx.dummy_controller.start_dummy_test).props(
        "flat no-caps align=left"
    ).classes("w-full app-nav-item")
    ctx.nav_buttons[key] = btn
    return btn
