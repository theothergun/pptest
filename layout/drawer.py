from nicegui import ui, app
from layout.context import PageContext
from layout.router import get_visible_routes, navigate, Route
from services.app_config import get_app_config



@ui.refreshable
def _render_drawer_content(ctx: PageContext) -> None:
	"""Rebuild the drawer buttons from current visible routes."""
	# Clear old buttons + content
	ctx.nav_buttons.clear()
	ctx.drawer_content.clear()
	active_key = app.storage.user.get("current_route", "")
	is_dark = bool(getattr(get_app_config().ui.navigation, "dark_mode", False))
	inactive_color = "grey-3" if is_dark else "grey-8"
	# Build buttons
	for key, route in get_visible_routes().items():
		if key == "errors":
			btn = _add_error_button(ctx, route, key)
		else:
			btn = _add_standard_button(ctx, route, key)
		if key == active_key:
			# Selected look:
			btn.props("unelevated")
			btn.props("color=primary")
		else:
			# Normal look:
			btn.props("flat")
			btn.props(f"color={inactive_color}")


def build_drawer(ctx: PageContext) -> ui.left_drawer:
	is_dark = bool(getattr(get_app_config().ui.navigation, "dark_mode", False))
	hide_on_startup = bool(getattr(get_app_config().ui.navigation, "hide_nav_on_startup", False))
	drawer_classes = "bg-slate-900 text-gray-100" if is_dark else "bg-gray-50"
	drawer = ui.left_drawer(value=not hide_on_startup, bordered=True).props("width=180").classes(drawer_classes)
	ctx.drawer = drawer

	with drawer:
		# All dynamic content goes into this column (so we can clear/rebuild it)
		ctx.drawer_content = ui.column().classes("w-full")

		# Initial render
		_render_drawer_content(ctx)

	# Convenience function for other modules
	def refresh_drawer() -> None:
		_render_drawer_content.refresh(ctx)
	ctx.refresh_drawer = refresh_drawer

	return drawer

def _add_standard_button(ctx: PageContext, route: Route, key:str):
	btn = ui.button(
		route.label,
		icon=route.icon,
		on_click=lambda k=key: navigate(ctx, k),
	).props("flat no-caps").classes(
		"w-full justify-start px-4")  # w-full justify-start makes the icon/text stay left, even with full width.
	ctx.nav_buttons[key] = btn
	return btn

def _add_error_button(ctx: PageContext, route: Route, key:str):
	with ui.row().classes("w-full items-center px-2"):
		# Create a flat button with custom content
		btn = ui.button(on_click=lambda k=key: navigate(ctx, k)) \
			.props("flat no-caps") \
			.classes("flex-1 justify-start px-2 gap-2")

		with btn:
			with ui.row().classes("items-center gap-2 no-wrap"):
				# Icon wrapper (relative) so badge can be absolutely positioned
				with ui.element("div").classes("relative inline-flex") as icon_wrap:
					ui.icon(route.icon)  # e.g. "error"

					# Badge floating on top-right of the icon
					errors_badge = ui.badge().props("color=negative") \
						.classes("absolute -top-3 -right-2 text-[11px] min-w-[16px] h-[16px]"
							"flex items-center justify-center")
					#add pulse class
					errors_badge.classes(add="error-badge-pulse")
					# text
					errors_badge.bind_text_from(ctx.state, "error_count", backward= lambda n: str(n))
					#visibility (show only if > 0)
					errors_badge.bind_visibility_from(ctx.state, "error_count",
													  backward= lambda n: int(n) > 0)
				# the error label
				ui.label(route.label)

		ctx.errors_icon_wrap = icon_wrap
		ctx.nav_buttons[key] = btn
	return btn

