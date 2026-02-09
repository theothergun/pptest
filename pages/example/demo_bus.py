from __future__ import annotations

from nicegui import ui

from layout.context import PageContext
from services.workers.example.demo_publisher_worker import Commands as PubCmd
from services.workers.example.demo_subscriber_worker import Commands as SubCmd


def render(container: ui.element, ctx: PageContext, route_key: str) -> None:
	with container:
		build_page(ctx)


def build_page(ctx: PageContext) -> None:
	# start both workers
	if not ctx.workers.is_running("demo_publisher_worker"):
		from services.workers.example.demo_publisher_worker import demo_publisher_worker
		ctx.workers.start_worker("demo_publisher_worker", demo_publisher_worker)

	if not ctx.workers.is_running("demo_subscriber_worker"):
		from services.workers.example.demo_subscriber_worker import demo_subscriber_worker
		ctx.workers.start_worker("demo_subscriber_worker", demo_subscriber_worker)

	pub = ctx.workers.get("demo_publisher_worker")
	sub = ctx.workers.get("demo_subscriber_worker")

	# init state
	if not hasattr(ctx.state, "demo_publisher_state"):
		ctx.state.demo_publisher_state = {"running": False, "counter": 0}

	if not hasattr(ctx.state, "demo_subscriber_state"):
		ctx.state.demo_subscriber_state = {"received_count": 0, "last_counter": None, "last_ts": None}

	# local timers (also cleaned up on disconnect/navigation)
	page_timers = []

	def add_timer(*args, **kwargs):
		t = ui.timer(*args, **kwargs)
		page_timers.append(t)
		return t

	def cancel_page_timers():
		for t in page_timers:
			try:
				t.cancel()
			except Exception:
				pass
		page_timers[:] = []

	ui.context.client.on_disconnect(cancel_page_timers)

	# IMPORTANT: flush pump (remove if you already have a global flush timer elsewhere)
	def flush_bridge():
		# adapt this line if your bridge is stored elsewhere on ctx
		ctx.bridge.flush(ctx)

	add_timer(0.1, flush_bridge)

	ui.label("WorkerBus Demo (Publisher -> Bus -> Subscriber -> UiBridge -> Page)").classes("text-xl font-bold mb-2")

	# UI elements
	pub_status = ui.label("")
	pub_counter = ui.label("").classes("text-2xl font-mono")

	sub_status = ui.label("")
	sub_last = ui.label("").classes("text-2xl font-mono")
	sub_count = ui.label("").classes("text-lg")

	def update_view():
		p = getattr(ctx.state, "demo_publisher_state", {}) or {}
		s = getattr(ctx.state, "demo_subscriber_state", {}) or {}

		pub_status.text = "Publisher: %s" % ("RUNNING" if p.get("running") else "STOPPED")
		pub_counter.text = "Published counter: %s" % int(p.get("counter") or 0)

		sub_status.text = "Subscriber: listening on demo.tick"
		sub_last.text = "Last received: %s" % str(s.get("last_counter"))
		sub_count.text = "Received messages: %s" % str(s.get("received_count"))

	# UI refresh (reads local state only; no worker requests)
	add_timer(0.1, update_view)
	update_view()

	with ui.row().classes("gap-2 mt-4"):
		ui.button("Start publishing", on_click=lambda: pub.send(PubCmd.START)).props("color=green")
		ui.button("Stop publishing", on_click=lambda: pub.send(PubCmd.STOP)).props("color=orange")
		ui.button("Reset publisher", on_click=lambda: pub.send(PubCmd.RESET)).props("color=blue outline")

		ui.separator().classes("mx-2")

		ui.button("Clear subscriber", on_click=lambda: sub.send(SubCmd.CLEAR)).props("color=blue flat")
