"""Tests for the inter-agent event bus."""

import asyncio
import pytest

from src.bus import Event, EventBus


@pytest.fixture
def bus():
    return EventBus()


def test_event_creation():
    evt = Event(topic="test.topic", source="agent_x", payload={"key": "value"})
    assert evt.topic == "test.topic"
    assert evt.source == "agent_x"
    assert evt.payload["key"] == "value"
    assert evt.timestamp  # not empty
    assert "agent_x" in evt.id


@pytest.mark.asyncio
async def test_publish_no_subscribers(bus):
    """Publishing to a topic with no subscribers should not raise."""
    evt = Event(topic="empty.topic", source="test", payload={})
    await bus.publish(evt)  # must not raise


@pytest.mark.asyncio
async def test_subscribe_and_receive(bus):
    received = []

    async def handler(event: Event):
        received.append(event)

    bus.subscribe("my.topic", handler)
    evt = Event(topic="my.topic", source="sender", payload={"x": 1})
    await bus.publish(evt)

    assert len(received) == 1
    assert received[0].payload["x"] == 1


@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    results = []

    async def h1(event):
        results.append("h1")

    async def h2(event):
        results.append("h2")

    bus.subscribe("shared", h1)
    bus.subscribe("shared", h2)
    await bus.publish(Event(topic="shared", source="src", payload={}))

    assert "h1" in results
    assert "h2" in results


@pytest.mark.asyncio
async def test_failing_handler_does_not_block(bus):
    """A handler that raises should not prevent other handlers from running."""
    called = []

    async def bad_handler(event):
        raise RuntimeError("intentional error")

    async def good_handler(event):
        called.append(True)

    bus.subscribe("topic", bad_handler)
    bus.subscribe("topic", good_handler)
    await bus.publish(Event(topic="topic", source="x", payload={}))

    assert called  # good_handler should still have been called


@pytest.mark.asyncio
async def test_recent_events(bus):
    for i in range(5):
        await bus.publish(Event(topic="t", source="s", payload={"i": i}))
    events = bus.recent_events(3)
    assert len(events) == 3
    assert events[-1].payload["i"] == 4


@pytest.mark.asyncio
async def test_unsubscribe(bus):
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("topic", handler)
    bus.unsubscribe("topic", handler)
    await bus.publish(Event(topic="topic", source="x", payload={}))

    assert len(received) == 0


def test_topics(bus):
    async def h(e):
        pass

    bus.subscribe("foo", h)
    bus.subscribe("bar", h)
    assert "foo" in bus.topics()
    assert "bar" in bus.topics()
