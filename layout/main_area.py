from nicegui import ui
from layout.context import PageContext


def build_main_area(ctx: PageContext) -> None:
	ctx.breadcrumb = None

	# This must be a flex child of a height-constrained parent (usually h-screen).
	# flex-1 + min-h-0 is what allows inner overflow containers to actually scroll.
	ctx.main_area = ui.column().classes("w-full flex-1 min-h-0 min-w-0 gap-4 overflow-hidden")
