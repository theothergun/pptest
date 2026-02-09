from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import os
from typing import Callable, Dict, Optional
from nicegui import ui, app

from auth.session import get_user
from layout.context import PageContext
from layout.action_bar import ActionBar, Action, EventBus, ACTIONS_BY_ROUTE

from services.app_config import get_app_config


# All pages get (container, ctx) so they can use ctx.bus/action_bar, etc.
RenderFn = Callable[[ui.element, PageContext], None]
OnEnterFn = Callable[[PageContext],None]


@dataclass(frozen=True)
class Route:
    label: str
    icon: str
    render: RenderFn
    actions: list[Action] = None
    on_enter: Optional[OnEnterFn] = None


BASE_ROUTES: Dict[str, Route] = {}


def _resolve_route_path(route_path: str) -> str:
    if os.path.isabs(route_path):
        return route_path
    return os.path.join(os.getcwd(), "pages", route_path)


def _render_custom_route(route_path: str) -> RenderFn:
    def _render(container: ui.element, ctx: PageContext) -> None:
        target = _resolve_route_path(route_path)
        if not os.path.exists(target):
            ui.label(f"Route file not found: {route_path}").classes("text-red-600")
            return
        module_name = f"custom_route_{hash(target)}"
        spec = importlib.util.spec_from_file_location(module_name, target)
        if not spec or not spec.loader:
            ui.label(f"Failed to load route: {route_path}").classes("text-red-600")
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        render_fn = getattr(module, "render", None)
        if not callable(render_fn):
            ui.label(f"Route file missing render(): {route_path}").classes("text-red-600")
            return
        render_fn(container, ctx)
    return _render


def get_routes() -> Dict[str, Route]:
    config = get_app_config()
    routes = dict(BASE_ROUTES)
    for entry in config.ui.navigation.custom_routes:
        key = entry.get("key")
        label = entry.get("label", key or "Custom")
        icon = entry.get("icon", "insert_drive_file")
        path = entry.get("path")
        if not key or not path:
            continue
        routes[key] = Route(label, icon, _render_custom_route(path), actions=ACTIONS_BY_ROUTE.get(key, []))
    return routes


def _is_route_allowed_for_user(route_key: str) -> bool:
    config = get_app_config()
    allowed_roles = config.ui.navigation.route_roles.get(route_key, [])
    if not allowed_roles:
        return True
    user = get_user()
    if not user:
        return False
    return any(role in user.roles for role in allowed_roles)


def get_visible_routes() -> Dict[str, Route]:
    config = get_app_config()
    visible = config.ui.navigation.visible_routes
    routes = get_routes()
    visible_routes = routes if not visible else {key: route for key, route in routes.items() if key in visible}
    return {key: route for key, route in visible_routes.items() if _is_route_allowed_for_user(key)}


def is_route_visible(key: str) -> bool:
    return key in get_visible_routes()


def _apply_drawer_highlight(ctx: PageContext, active_key: str) -> None:
    """Update drawer button styles so the active one looks selected."""
    for key, btn in ctx.nav_buttons.items():
        if key == active_key:
            # Selected look:
            btn.props("unelevated")
            btn.props("color=primary")
        else:
            # Normal look:
            btn.props("flat")
            btn.props("color=grey-8")


#supports visiting: http://localhost:8080/?page=reports
def get_initial_route_from_url(default: str = "home") -> str:
    """Read ?page=... from the current request (deep link)."""
    try:
        page = ui.context.request.query_params.get("page")
    except Exception:
        page = None
    if page and is_route_visible(page):
        return page
    return default if is_route_visible(default) else next(iter(get_visible_routes()), "home")

def navigate(ctx: PageContext, route_key: str) -> None:
    route = get_routes().get(route_key)
    if not route or not is_route_visible(route_key):
        ui.notify(f"Unknown route: {route_key}", type="negative")
        return

    # per-user state (persists if storage_secret stays the same)
    app.storage.user["current_route"] = route_key

    # update the URL (deep-link) without reloading
    ui.run_javascript(f"history.replaceState(null, '', '?page={route_key}')")

    _apply_drawer_highlight(ctx, route_key)

    # IMPORTANT: new bus per navigation avoids "duplicate handlers" when you revisit a page
    ctx.bus = EventBus()

    # Create a fresh action bar for this route (uses ctx.bus internally)
    ctx.action_bar = ActionBar(ctx, route_key, route.actions or [])

    if ctx.breadcrumb:
        ctx.breadcrumb.set_text(f"/{route_key}")

    if ctx.main_area:
        ctx.main_area.clear()
        route.render(ctx.main_area, ctx)

    if route.on_enter:
        route.on_enter(ctx)
