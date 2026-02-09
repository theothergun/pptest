from __future__ import annotations

"""
Reusable scroll + highlight behavior for NiceGUI views.

Purpose:
- Scroll a specific element into view inside a scrollable container
- Only scroll if the element is actually outside the visible area
- Optionally flash-highlight the element
- Safe to use inside @ui.refreshable functions

How it works:
- We assign a DOM id to the scroll container (scroller_id)
- We assign DOM ids to each list item wrapper
- After refresh, we inject small JS that:
    1) Waits until DOM elements exist
    2) Checks visibility inside the scroller
    3) Scrolls smoothly if needed
    4) Optionally applies a temporary highlight class
"""

import re
from dataclasses import dataclass
from nicegui import ui


# ------------------------------------------------------------
# DOM ID helpers
# ------------------------------------------------------------

def get_safe_dom_id(value: str) -> str:
    """
    Convert any string into a safe DOM id.

    Removes characters that are invalid or unsafe in HTML id attributes.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "-", value or "")


def generate_wrapper_id(prefix: str, key: str) -> str:
    """
    Generate a predictable DOM id for list rows.

    Example:
        wrapper_id("route-card", "my/route")
        -> "route-card-my-route"

    Use a different prefix per page to avoid collisions.
    """
    return f"{prefix}-{get_safe_dom_id(key)}"


# ------------------------------------------------------------
# Scroll + Highlight engine
# ------------------------------------------------------------

@dataclass(frozen=True)
class ScrollFx:
    """
    Reusable scroll/highlight configuration.

    Parameters:
        scroller_id:
            DOM id of the scroll container.

        highlight_class:
            Tailwind class applied temporarily for highlight.

        highlight_duration_ms:
            How long the highlight stays visible.

        transition_duration_ms:
            Duration of Tailwind color transition.

        padding_px:
            Extra margin to treat as "visible boundary".

        center:
            If True -> element is centered in scroller.
            If False -> element is aligned near top.
    """

    scroller_id: str
    highlight_class: str = "bg-green-200"
    highlight_duration_ms: int = 900
    transition_duration_ms: int = 700
    padding_px: int = 12
    center: bool = True

    # --------------------------------------------------------

    def js(self, target_id: str, *, highlight: bool) -> str:
        """
        Build JavaScript snippet that:

        1) Finds scroller + target element
        2) Waits (via requestAnimationFrame) until they exist
        3) Checks if element is already visible
        4) Scrolls smoothly if not
        5) Applies optional highlight effect

        We return JS string because NiceGUI executes it client-side.
        """

        # Build highlight snippet only if requested
        highlight_js = (
            f"""
            hi.classList.add(
                'transition-colors',
                'duration-{self.transition_duration_ms}',
                '{self.highlight_class}'
            );
            setTimeout(() => hi.classList.remove('{self.highlight_class}'),
                {self.highlight_duration_ms});
            setTimeout(() => hi.classList.remove(
                'transition-colors',
                'duration-{self.transition_duration_ms}'
            ), {self.highlight_duration_ms + self.transition_duration_ms});
            """
            if highlight else ""
        )

        # Choose scroll behavior
        if self.center:
            # Center the element inside the scroll area
            scroll_calc = """
                const top = (r.top - s.top) + scroller.scrollTop;
                const target = top - (scroller.clientHeight / 2) + (el.clientHeight / 2);
            """
        else:
            # Align element near top
            scroll_calc = """
                const target = (r.top - s.top) + scroller.scrollTop - pad;
            """

        return f"""
        (function go() {{
            const scroller = document.getElementById({self.scroller_id!r});
            const el = document.getElementById({target_id!r});

            // Wait until DOM is fully ready after refresh
            if (!scroller || !el) {{
                requestAnimationFrame(go);
                return;
            }}

            // Highlight the visual card instead of outer wrapper
            const hi = el.firstElementChild || el;

            const s = scroller.getBoundingClientRect();
            const r = el.getBoundingClientRect();

            const pad = {self.padding_px};

            // Visible region boundaries inside scroll container
            const visibleTop = s.top + pad;
            const visibleBottom = s.bottom - pad;

            const isVisible =
                (r.top >= visibleTop) &&
                (r.bottom <= visibleBottom);

            // Only scroll if element is not fully visible
            if (!isVisible) {{
                {scroll_calc}
                scroller.scrollTo({{ top: target, behavior: "smooth" }});
            }}

            {highlight_js}
        }})();
        """

    # --------------------------------------------------------

    def run(self, target_id: str, *, highlight: bool, delay_s: float = 0.05) -> None:
        """
        Execute scroll/highlight JS safely from a refreshable context.

        We use ui.timer to ensure:
            - The DOM has finished rendering
            - The new element is actually mounted

        delay_s:
            Small delay after refresh (usually 0.05–0.1 works well)
        """
        client = ui.context.client
        js_code = self.js(target_id, highlight=highlight)

        ui.timer(
            delay_s,
            lambda c=client, j=js_code: c.run_javascript(j),
            once=True
        )
