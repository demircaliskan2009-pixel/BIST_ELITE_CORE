"""EventRouter — typed event dispatcher.

Routes validated typed event objects to registered handlers by event type.
One handler per event type per instance. Handlers are registered at startup
and not changed at runtime (deterministic dispatch table).

Design:
- No queuing: synchronous dispatch (caller blocks until handler returns).
- No threading: concurrency is the caller's responsibility.
- Type dispatch via isinstance to avoid string-based type registries.

PRD reference: §4 (data layer pipeline), integrated with message bus (§crypto-message-bus) later.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional, Type

logger = logging.getLogger(__name__)

# Generic handler type: callable that accepts any typed event and returns None.
EventHandler = Callable[[object], None]


class EventRouter:
    """Dispatches typed event objects to registered handlers.

    Registration:
        router.register(TradeEvent, handle_trade)
        router.register(OrderBookEvent, handle_order_book)

    Dispatch:
        router.route(event)   ← called by DataIngestor/DataValidator for every event

    Unregistered event types: logged at DEBUG level and silently dropped.
    Handler exceptions: propagated to the caller (fail-closed: exceptions surface).
    """

    def __init__(self) -> None:
        self._handlers: Dict[Type, EventHandler] = {}

    def register(self, event_type: Type, handler: EventHandler) -> None:
        """Register a handler for the given event type.

        Raises ValueError if a handler is already registered for this type.
        Re-registration is not allowed — prevents accidental overwrites.
        """
        if event_type in self._handlers:
            raise ValueError(
                f"Handler already registered for event type '{event_type.__name__}'. "
                "Unregister first or use a new EventRouter instance."
            )
        self._handlers[event_type] = handler
        logger.debug("EventRouter: registered handler for %s", event_type.__name__)

    def unregister(self, event_type: Type) -> None:
        """Remove the handler for the given event type.

        Raises KeyError if no handler is registered for this type.
        """
        if event_type not in self._handlers:
            raise KeyError(f"No handler registered for event type '{event_type.__name__}'")
        del self._handlers[event_type]

    def route(self, event: object) -> None:
        """Dispatch an event to its registered handler.

        Uses exact type match (type(), not isinstance) for deterministic dispatch.
        Subtypes are NOT matched — register each type explicitly.

        If no handler is registered → DEBUG log, event dropped.
        Handler exceptions → propagated immediately (fail-closed).
        """
        handler = self._handlers.get(type(event))
        if handler is None:
            logger.debug("EventRouter: no handler for %s — event dropped", type(event).__name__)
            return
        handler(event)

    def has_handler(self, event_type: Type) -> bool:
        """Returns True if a handler is registered for the given type."""
        return event_type in self._handlers

    def registered_types(self) -> frozenset:
        """Returns frozenset of all registered event types."""
        return frozenset(self._handlers.keys())
