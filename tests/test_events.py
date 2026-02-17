import pytest
import asyncio
import json

pytestmark = pytest.mark.asyncio


class TestEventBus:
    async def test_subscribe_and_publish(self):
        from megregore.events import EventBus
        bus = EventBus()
        queue = bus.subscribe()

        bus.publish("memory_created", {"id": 1, "type": "experience"})

        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event["event"] == "memory_created"
        assert event["data"]["id"] == 1

    async def test_multiple_subscribers(self):
        from megregore.events import EventBus
        bus = EventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()

        bus.publish("test_event", {"value": 42})

        e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert e1["data"]["value"] == 42
        assert e2["data"]["value"] == 42

    async def test_unsubscribe(self):
        from megregore.events import EventBus
        bus = EventBus()
        queue = bus.subscribe()
        bus.unsubscribe(queue)

        bus.publish("test_event", {"value": 1})

        assert queue.empty()

    async def test_full_queue_drops(self):
        from megregore.events import EventBus
        bus = EventBus()
        queue = bus.subscribe()

        # Fill the queue (maxsize=100)
        for i in range(100):
            bus.publish("fill", {"i": i})

        # Next publish should drop the subscriber
        bus.publish("overflow", {"i": 100})
        assert queue not in bus._subscribers


class TestFormatSSE:
    async def test_format(self):
        from megregore.events import format_sse
        result = format_sse("memory_created", {"id": 5})
        assert "event: memory_created" in result
        assert '"id": 5' in result
        assert result.endswith("\n\n")


class TestGlobalBus:
    async def test_global_bus_exists(self):
        from megregore.events import event_bus
        assert event_bus is not None

    async def test_emit_convenience(self):
        from megregore.events import event_bus, emit
        queue = event_bus.subscribe()
        emit("memory_created", {"id": 99})
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event["data"]["id"] == 99
        event_bus.unsubscribe(queue)
