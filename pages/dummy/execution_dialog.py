from __future__ import annotations
from nicegui import ui

from layout.context import PageContext
from pages.dummy.dummy_service import DummyUIHandles


def _make_draggable_clamp_to_view_port(handle_id: str, dialog_id: str, *, storage_key: str = "dummy_exec_window_pos") -> None:
	ui.run_javascript(f"""
	(function() {{
	  const dlg = document.getElementById('{dialog_id}');
	  const handle = document.getElementById('{handle_id}');
	  if (!dlg || !handle) return;

	  dlg.style.position = 'fixed';
	  dlg.style.margin = '0';
	  dlg.style.zIndex = '99999';

	  const MARGIN = 12; // keep a small visible margin so it can always be grabbed

	  function clampToViewport() {{
		const rect = dlg.getBoundingClientRect();

		// current numeric pos (fallback to rect position if style is empty)
		let left = parseFloat(dlg.style.left);
		let top  = parseFloat(dlg.style.top);

		if (!Number.isFinite(left)) left = rect.left || 0;
		if (!Number.isFinite(top))  top  = rect.top  || 0;

		const maxLeft = window.innerWidth  - rect.width  - MARGIN;
		const maxTop  = window.innerHeight - rect.height - MARGIN;

		// If dialog is larger than viewport, keep its top-left at margin
		const clampedLeft = (maxLeft < MARGIN) ? MARGIN : Math.min(Math.max(left, MARGIN), maxLeft);
		const clampedTop  = (maxTop  < MARGIN) ? MARGIN : Math.min(Math.max(top,  MARGIN), maxTop);

		dlg.style.left = clampedLeft + 'px';
		dlg.style.top  = clampedTop  + 'px';
	  }}

	  function savePos() {{
		try {{
		  localStorage.setItem('{storage_key}', JSON.stringify({{
			left: parseFloat(dlg.style.left) || 0,
			top:  parseFloat(dlg.style.top)  || 0,
		  }}));
		}} catch (e) {{}}
	  }}

	  // restore saved position
	  try {{
		const raw = localStorage.getItem('{storage_key}');
		if (raw) {{
		  const p = JSON.parse(raw);
		  if (typeof p.left === 'number') dlg.style.left = p.left + 'px';
		  if (typeof p.top  === 'number') dlg.style.top  = p.top  + 'px';
		}}
	  }} catch (e) {{}}

	  // fallback if still not set
	  if (!dlg.style.left) dlg.style.left = '120px';
	  if (!dlg.style.top)  dlg.style.top  = '90px';

	  // clamp immediately after restore/fallback
	  clampToViewport();
	  savePos();

	  let dragging = false, startX=0, startY=0, startLeft=0, startTop=0;

	  handle.style.cursor = 'move';
	  handle.addEventListener('pointerdown', (e) => {{
		dragging = true;
		handle.setPointerCapture(e.pointerId);
		startX = e.clientX; startY = e.clientY;
		startLeft = parseFloat(dlg.style.left) || 0;
		startTop  = parseFloat(dlg.style.top)  || 0;
	  }});

	  handle.addEventListener('pointermove', (e) => {{
		if (!dragging) return;
		const dx = e.clientX - startX;
		const dy = e.clientY - startY;

		dlg.style.left = (startLeft + dx) + 'px';
		dlg.style.top  = (startTop  + dy) + 'px';

		// keep inside viewport while dragging
		clampToViewport();
	  }});

	  function endDrag() {{
		dragging = false;
		clampToViewport();
		savePos();
	  }}

	  handle.addEventListener('pointerup', endDrag);
	  handle.addEventListener('pointercancel', endDrag);

	  // if viewport size changes, keep window visible
	  window.addEventListener('resize', () => {{
		clampToViewport();
		savePos();
	  }});
	}})();
	""")

def _make_draggable(handle_id: str, dialog_id: str, *, storage_key: str = "dummy_exec_window_pos") -> None:
	ui.run_javascript(f"""
	(function() {{
	  const dlg = document.getElementById('{dialog_id}');
	  const handle = document.getElementById('{handle_id}');
	  if (!dlg || !handle) return;

	  dlg.style.position = 'fixed';
	  dlg.style.margin = '0';
	  dlg.style.zIndex = '99999';

	  const MARGIN = 12; // vertical margin to keep a small visible strip

	  function clampToViewport() {{
		const rect = dlg.getBoundingClientRect();

		// current numeric pos (fallback to rect position if style is empty)
		let left = parseFloat(dlg.style.left);
		let top  = parseFloat(dlg.style.top);

		if (!Number.isFinite(left)) left = rect.left || 0;
		if (!Number.isFinite(top))  top  = rect.top  || 0;

		// Allow dialog to go out of view horizontally by up to 1/3 of its width
		const offX = rect.width / 3;

		// left can go negative (off-screen) up to -offX
		const minLeft = -offX;

		// right can go past viewport by offX (i.e. left up to innerWidth - width + offX)
		const maxLeft = window.innerWidth - rect.width + offX;

		// Vertical clamping stays strict (keep it grab-able)
		const maxTop  = window.innerHeight - rect.height - MARGIN;
		const clampedTop  = (maxTop < MARGIN) ? MARGIN : Math.min(Math.max(top, MARGIN), maxTop);

		const clampedLeft = Math.min(Math.max(left, minLeft), maxLeft);

		dlg.style.left = clampedLeft + 'px';
		dlg.style.top  = clampedTop  + 'px';
	  }}

	  function savePos() {{
		try {{
		  localStorage.setItem('{storage_key}', JSON.stringify({{
			left: parseFloat(dlg.style.left) || 0,
			top:  parseFloat(dlg.style.top)  || 0,
		  }}));
		}} catch (e) {{}}
	  }}

	  // restore saved position
	  try {{
		const raw = localStorage.getItem('{storage_key}');
		if (raw) {{
		  const p = JSON.parse(raw);
		  if (typeof p.left === 'number') dlg.style.left = p.left + 'px';
		  if (typeof p.top  === 'number') dlg.style.top  = p.top  + 'px';
		}}
	  }} catch (e) {{}}

	  // fallback if still not set
	  if (!dlg.style.left) dlg.style.left = '120px';
	  if (!dlg.style.top)  dlg.style.top  = '90px';

	  // clamp immediately after restore/fallback
	  clampToViewport();
	  savePos();

	  let dragging = false, startX=0, startY=0, startLeft=0, startTop=0;

	  handle.style.cursor = 'move';
	  handle.addEventListener('pointerdown', (e) => {{
		dragging = true;
		handle.setPointerCapture(e.pointerId);
		startX = e.clientX; startY = e.clientY;
		startLeft = parseFloat(dlg.style.left) || 0;
		startTop  = parseFloat(dlg.style.top)  || 0;
	  }});

	  handle.addEventListener('pointermove', (e) => {{
		if (!dragging) return;
		const dx = e.clientX - startX;
		const dy = e.clientY - startY;

		dlg.style.left = (startLeft + dx) + 'px';
		dlg.style.top  = (startTop  + dy) + 'px';

		clampToViewport();
	  }});

	  function endDrag() {{
		dragging = false;
		clampToViewport();
		savePos();
	  }}

	  handle.addEventListener('pointerup', endDrag);
	  handle.addEventListener('pointercancel', endDrag);

	  window.addEventListener('resize', () => {{
		clampToViewport();
		savePos();
	  }});
	}})();
	""")



def create_dummy_execution_tool_window(execution_state, ctx:PageContext, *, is_predetermined = False):
	"""
	Build ONCE inside the page layout (guaranteed visible slot).
	Returns (show, hide) callables.
	"""

	dialog_id = f"exec_dlg_{id(execution_state)}"
	header_id = f"exec_header_{id(execution_state)}"
	pos_storage_key = "dummy_exec_window_pos"  # you can namespace this if you want

	def get_selected_set():
		if execution_state.selected_set_id is None:
			return None
		return next((s for s in execution_state.sets if s.id == execution_state.selected_set_id), None)

	def select_set(sid: int) -> None:
		execution_state.selected_set_id = sid
		execution_state.ensure_valid_selection()
		# keep progress/results; just update selection + UI
		execution_state.persist()
		header_sets.refresh()
		left_panel.refresh()
		right_panel.refresh()

	def select_dummy(did: int) -> None:
		execution_state.selected_dummy_id = did
		execution_state.persist()
		left_panel.refresh()
		right_panel.refresh()

	def hide() -> None:
		wrapper.classes(add='hidden')
		wrapper.update()

	def show() -> None:
		# Fix 2: refresh reference, DO NOT init_defaults (keeps progress/results)
		dummies = execution_state.dummies()
		#execution_state.set_dummy_state(dummies[0].id, True, inspection_values={})
		#execution_state.set_dummy_state(dummies[1].id, False, inspection_values={})

		wrapper.classes(remove='hidden')
		wrapper.update()

		refresh_all()

		# Fix 1: restore position + enable drag, every time it appears
		ui.timer(
			0.05,
			lambda: _make_draggable(header_id, dialog_id, storage_key=pos_storage_key),
			once=True,
		)


	@ui.refreshable
	def spinner_overlay() -> None:
		if not ctx.state.dummy_test_is_running:
			return

		with ui.element('div').classes(
				"absolute inset-0 bg-black/60 backdrop-blur-sm "
				"flex items-center justify-center z-[100000]"
		):
			# Center panel
			with ui.column().classes(
					"items-center gap-6 px-10 py-8 "
					"bg-white/10 backdrop-blur-md "
					"rounded-2xl shadow-2xl border border-white/20 "
					"animate-pulse"
			):
				ui.spinner(size='100px').props("color=orange")

				ui.label("Dummy Test Running") \
					.classes(
					"text-orange-400 text-2xl font-bold tracking-wide text-center"
				)

	@ui.refreshable
	def header_sets() -> None:
		with ui.row().classes("w-full px-3 py-2 gap-2").style(
			"background:var(--surface-muted); border-bottom:1px solid var(--input-border);"
		):
			for s in execution_state.sets:
				selected = (s.id == execution_state.selected_set_id)
				props = "unelevated color=positive text-color=white" if selected else "unelevated color=grey-4 text-color=grey-9"
				ui.button(
					s.name.upper(),
					on_click=lambda sid=s.id: select_set(sid),
				).props(props).classes("grow rounded-lg text-sm py-2 font-semibold")

	@ui.refreshable
	def left_panel() -> None:
		s = get_selected_set()
		with ui.column().classes("w-full flex-1 min-h-0 overflow-auto").style(
			"background:var(--surface); color:var(--text-primary);"
		):
			if not s or not getattr(s, "dummies", None):
				ui.label("No dummies in this set").classes("px-3 py-2 text-sm opacity-70")
				return

			for d in s.dummies:
				selected = (d.id == execution_state.selected_dummy_id)
				row = "w-full px-3 py-2 items-center border-b cursor-pointer"
				row_style = "border-color:var(--input-border);"
				if selected:
					row_style += " background:var(--surface-muted);"
				icon_name, icon_color = execution_state.get_dummy_state_icon(d.id)
				with ui.row().classes(row).style(row_style).on("click", lambda _=None, did=d.id: select_dummy(did)):
					ui.label(d.name).classes("text-sm grow")
					ui.icon(icon_name).classes(f"text-lg {icon_color}")

	@ui.refreshable
	def right_panel() -> None:
		s = get_selected_set()

		selected_dummy = None
		if s and execution_state.selected_dummy_id is not None:
			selected_dummy = next((d for d in s.dummies if d.id == execution_state.selected_dummy_id), None)

		inspections = list(getattr(selected_dummy, "inspections", []) or []) if selected_dummy else []

		with ui.card().classes("w-full h-full p-0 rounded-xl overflow-hidden flex flex-col").style(
			"background:var(--surface); border:1px solid var(--input-border);"
		):
			with ui.row().classes("w-full items-center justify-between px-3 py-2 border-b").style(
				"background:var(--surface); border-color:var(--input-border);"
			):
				ui.label("Inspection Monitoring").classes("text-sm font-semibold")

			with ui.element("div").classes("w-full px-3 py-2 border-b grid grid-cols-[44%_28%_28%] items-center text-xs font-semibold").style(
				"background:var(--surface-muted); border-color:var(--input-border);"
			):
				ui.label("Inspection Name")
				ui.label("Expected Value").classes("text-right")
				ui.label("Current Value").classes("text-right")

			with ui.column().classes("w-full flex-1 min-h-0 overflow-auto").style(
				"background:var(--surface); color:var(--text-primary);"
			):
				if not selected_dummy:
					ui.label("Select a dummy to see inspections").classes("px-3 py-3 text-sm opacity-70")
					return
				if not inspections:
					ui.label("This dummy has no inspections").classes("px-3 py-3 text-sm opacity-70")
					return

				for ins in inspections:
					with ui.element("div").classes("w-full px-3 py-2 border-b grid grid-cols-[44%_28%_28%] items-center").style(
						"border-color:var(--input-border);"
					):
						ui.label(ins.name).classes("text-sm font-medium")
						ui.label(str(ins.expected_value)).classes("text-right text-sm font-semibold text-gray-700")
						current_label = ui.label("0").classes("text-right text-sm font-semibold text-blue-600")
						current_label.bind_text_from(ctx.state, ins.state_field_name,backward=lambda x:str(x) )


	def refresh_all():
		header_sets.refresh()
		left_panel.refresh()
		right_panel.refresh()
		spinner_overlay.refresh()


	# ===================== BUILD WINDOW ONCE =====================
	wrapper = ui.element('div') \
		.classes('hidden fixed inset-0 pointer-events-none') \
		.style('z-index: 99999;')

	with wrapper:
		with ui.card().props(f"id={dialog_id}").classes(
			"pointer-events-auto relative w-[1200px] max-w-[95vw] h-[550px] p-0 rounded-2xl "
			"overflow-hidden shadow-2xl flex flex-col"
		).style("background:var(--surface); color:var(--text-primary); border:1px solid var(--input-border);"):
			# IMPORTANT: do NOT set left/top here; JS restores position.
			with ui.row().props(f"id={header_id}").classes(
				"w-full items-center justify-between px-4 py-2 bg-primary text-white select-none"
			):
				ui.label("Dummy Execution").classes("text-base font-semibold")
				if is_predetermined:
					ui.label("(Predetermined Mode)")
				#ui.button(icon="close", on_click=close_window).props("flat round dense").classes("text-white")

			header_sets()
			spinner_overlay()
			with ui.row().classes("w-full flex-1 min-h-0 p-3 gap-3").style("background:var(--app-background);"):
				with ui.card().classes("w-[260px] h-full p-0 rounded-xl overflow-hidden flex flex-col").style(
					"background:var(--surface); border:1px solid var(--input-border);"
				):
					with ui.row().classes("w-full px-3 py-2 border-b").style(
						"background:var(--surface); border-color:var(--input-border);"
					):
						ui.label("Dummy Result").classes("text-sm font-semibold")
					left_panel()

				with ui.column().classes("grow h-full min-h-0"):
					right_panel()

			#with ui.row().classes("w-full justify-end px-3 py-2 bg-[#F3F6FF] border-t border-gray-200"):
			#	ui.button("Close", on_click=close_window).props("unelevated").classes("bg-primary text-white")

	# optional: return exec_state too if you want to drive it externally
	return DummyUIHandles(show=show,
						  hide=hide,
						  refresh_sets=header_sets.refresh,
						  refresh_left=left_panel.refresh,
						  refresh_right=right_panel.refresh,
						  refresh_spinner=spinner_overlay.refresh,
						  refresh_all=refresh_all)
