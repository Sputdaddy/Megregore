"""SSE event bus for Megregore V11. Simple in-process pub/sub for real-time dashboard updates."""

import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("megregore.events")


class EventBus:
    """Simple in-process event bus using asyncio.Queue per subscriber."""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        """Create a new subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        logger.debug("New subscriber (total: %d)", len(self._subscribers))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)
            logger.debug("Subscriber removed (total: %d)", len(self._subscribers))

    def publish(self, event_type: str, data: dict) -> None:
        """Publish an event to all subscribers."""
        event = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(queue)
                logger.warning("Subscriber queue full, dropping")

        for q in dead_queues:
            self._subscribers.remove(q)


def format_sse(event_type: str, data: dict) -> str:
    """Format an event as an SSE string."""
    json_data = json.dumps(data)
    return f"event: {event_type}\ndata: {json_data}\n\n"


# Global singleton bus
event_bus = EventBus()


def emit(event_type: str, data: dict) -> None:
    """Convenience function to publish to the global bus."""
    event_bus.publish(event_type, data)
