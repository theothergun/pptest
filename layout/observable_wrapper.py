from collections import defaultdict
from typing import Any, Callable, DefaultDict, Optional

Callback = Callable[[str, Any, Any], None]

class ObservableWrapper:
    def __init__(self, target: Any):
        object.__setattr__(self, "_target", target)
        # field -> owner -> token -> callback
        object.__setattr__(self, "_subs", defaultdict(lambda: defaultdict(dict)))
        # owner -> token -> callback
        object.__setattr__(self, "_any_subs", defaultdict(dict))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)

    def __setattr__(self, name: str, value: Any) -> None:
        old = getattr(self._target, name, None)
        setattr(self._target, name, value)
        if old == value:
            return

        # field-specific subscribers
        field_owners = self._subs.get(name, {})
        for owner_map in list(field_owners.values()):
            for cb in list(owner_map.values()):
                cb(name, old, value)

        # any-field subscribers
        for owner_map in list(self._any_subs.values()):
            for cb in list(owner_map.values()):
                cb(name, old, value)

    def subscribe(self, fields, callback: Callback, *, owner: Optional[str] = None) -> Callable[[], None]:
        """Subscribe to one or more fields. Returns an unsubscribe() handle."""
        if isinstance(fields, str):
            fields = {fields}
        owner = owner or "__default__"
        token = object()

        for f in fields:
            self._subs[f][owner][token] = callback

        def unsubscribe():
            for f in fields:
                self._subs.get(f, {}).get(owner, {}).pop(token, None)

        return unsubscribe

    def subscribe_any(self, callback: Callback, *, owner: Optional[str] = None) -> Callable[[], None]:
        owner = owner or "__default__"
        token = object()
        self._any_subs[owner][token] = callback

        def unsubscribe():
            self._any_subs.get(owner, {}).pop(token, None)

        return unsubscribe

    def unsubscribe_owner(self, owner: str) -> None:
        """Remove all subscriptions registered under this owner."""
        # remove any-field subs
        self._any_subs.pop(owner, None)
        # remove field subs
        for field in list(self._subs.keys()):
            self._subs[field].pop(owner, None)
            if not self._subs[field]:  # cleanup empty
                self._subs.pop(field, None)

    def unsubscribe_all(self) -> None:
        """Remove ALL subscriptions (use sparingly!)."""
        self._subs.clear()
        self._any_subs.clear()
