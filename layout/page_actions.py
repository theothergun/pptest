from __future__ import annotations

from typing import Callable

from layout.action_bar.models import Action
from layout.context import PageContext


PageActionHandler = Callable[[PageContext, str, Action], None]


def bind_action_map(ctx: PageContext, action_map: dict[str, PageActionHandler], *, fallback: PageActionHandler | None = None):
    def _handler(action_id: str, action: Action) -> None:
        handler = action_map.get(action_id)
        if handler is not None:
            handler(ctx, action_id, action)
            return
        if fallback is not None:
            fallback(ctx, action_id, action)

    return _handler
