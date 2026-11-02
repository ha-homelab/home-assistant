"""Read-only connection state and owned subscriptions across roombapy versions."""
from collections.abc import Callable

_MISSING = object()


def is_connected(robot) -> bool:
    """Prefer the async client's state without masking a disconnected session."""
    state = getattr(robot, "connected", _MISSING)
    if state is _MISSING:
        state = getattr(robot, "roomba_connected", False)
    return state is True


def subscribe_callback(robot, kind: str, callback: Callable) -> Callable[[], None]:
    """Return an owned unsubscribe handle for async and legacy clients."""
    unsubscribe = getattr(robot, f"register_on_{kind}_callback")(callback)
    if callable(unsubscribe):
        return unsubscribe

    # roombapy 1.x returns None and exposes its callback lists. Never inspect
    # the private registries of the async client or remove another listener.
    callbacks = getattr(robot, f"on_{kind}_callbacks", None)
    if unsubscribe is not None or not isinstance(callbacks, list):
        raise TypeError("Unsupported Roomba callback subscription contract")

    def detach() -> None:
        if callback in callbacks:
            callbacks.remove(callback)

    return detach
