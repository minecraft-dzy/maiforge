"""
EventBus – Forge-style pub/sub event bus.

Supports:
- @SubscribeEvent decorator
- Priority ordering (HIGHEST → LOWEST)
- Cancelable events

Usage in mods:
    from maiforge.api import SubscribeEvent, Event

    class MyEvent(Event):
        def __init__(self, message: str):
            self.message = message

    @SubscribeEvent
    def on_my_event(event: MyEvent):
        print(event.message)
"""
from __future__ import annotations

import enum
import traceback
from typing import Any, Callable


class EventPriority(enum.IntEnum):
    HIGHEST = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    LOWEST = 4


class Event:
    """Base event.  Set `canceled = True` to cancel (if cancelable)."""

    def __init__(self) -> None:
        self._canceled = False

    @property
    def is_cancelable(self) -> bool:
        return False

    @property
    def is_canceled(self) -> bool:
        return self._canceled

    def set_canceled(self, value: bool = True) -> None:
        if not self.is_cancelable:
            raise RuntimeError("Event is not cancelable")
        self._canceled = value


class CancelableEvent(Event):
    """An event that can be canceled by listeners."""

    @property
    def is_cancelable(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Marker for the subscriber registry
# ---------------------------------------------------------------------------
_SUBSCRIBER_REGISTRY: dict[type[Event], list[tuple[int, Callable]]] = {}


def SubscribeEvent(func: Callable = None, *, priority: EventPriority = EventPriority.NORMAL):
    """Decorator / bare callable marker.  Used in mod classes."""
    if func is None:
        def dec(f: Callable):
            _store_subscriber(f, priority)
            return f
        return dec
    _store_subscriber(func, priority)
    return func


def _store_subscriber(fn: Callable, priority: EventPriority) -> None:
    import inspect
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    if len(params) != 1:
        raise TypeError(
            f"@SubscribeEvent handler must accept exactly one argument (the event), got {len(params)}"
        )
    event_type = params[0].annotation
    if event_type is inspect.Parameter.empty:
        raise TypeError("Event handler must have a type annotation for the event parameter")
    _SUBSCRIBER_REGISTRY.setdefault(event_type, []).append((int(priority), fn))


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class EventBus:
    """Central event dispatcher.  One instance per MaiForge."""

    def __init__(self) -> None:
        self._listeners: dict[type[Event], list[tuple[int, Callable]]] = {}
        # Copy over the static registry
        for evt_type, handlers in _SUBSCRIBER_REGISTRY.items():
            self._listeners[evt_type] = sorted(handlers, key=lambda x: x[0])

    def register(self, obj: object) -> None:
        """Register all @SubscribeEvent methods on an object."""
        for attr_name in dir(obj):
            try:
                attr = getattr(obj, attr_name)
            except Exception:
                continue
            if not callable(attr):
                continue
            if not getattr(attr, "_is_subscriber", False):
                # We store directly; the decorator already populated _SUBSCRIBER_REGISTRY
                # But for objects registered late, scan their type annots
                import inspect
                try:
                    sig = inspect.signature(attr)
                    params = list(sig.parameters.values())
                    if len(params) == 1 and params[0].annotation is not inspect.Parameter.empty:
                        evt_type = params[0].annotation
                        if issubclass(evt_type, Event):
                            self._listeners.setdefault(evt_type, []).append(
                                (int(EventPriority.NORMAL), attr)
                            )
                except Exception:
                    pass

    def unregister(self, obj: object) -> None:
        """Remove all handlers owned by obj."""
        for evt_type in list(self._listeners.keys()):
            self._listeners[evt_type] = [
                (pri, fn) for pri, fn in self._listeners[evt_type]
                if getattr(fn, "__self__", None) is not obj
            ]

    def post(self, event: Event) -> Event:
        """Fire an event to all registered listeners. Returns the event (may be canceled)."""
        evt_type = type(event)
        handlers = self._listeners.get(evt_type, [])
        for _pri, handler in sorted(handlers, key=lambda x: x[0]):
            try:
                handler(event)
            except Exception:
                traceback.print_exc()
            if event.is_cancelable and event.is_canceled:
                break
        return event

    def clear(self) -> None:
        self._listeners.clear()
