"""
Garcar Enterprise Universal Event Bus SDK
Connects any of the 200+ Garcar systems to the shared event fabric.

Topic schema: garcar.{system_name}.{event_type}
Broker: NATS (primary) / Redis Streams (fallback)

Usage:
    from event_bus_sdk import EventBus
    bus = EventBus(system_name="garcar-payments")
    bus.publish("payment.completed", {"amount": 4999, "customer": "cus_123"})
    bus.subscribe("revenue.updated", handler_fn)
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

try:
    import nats
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class EventBus:
    def __init__(self, system_name: str, broker_url: Optional[str] = None):
        self.system_name = system_name
        self.broker_url = broker_url or os.environ.get("GARCAR_EVENT_BROKER_URL", "nats://localhost:4222")
        self._redis_fallback_url = os.environ.get("GARCAR_REDIS_URL", "redis://localhost:6379")
        self._nc = None
        self._redis_client = None
        self._connected = False

    def connect(self):
        if NATS_AVAILABLE:
            try:
                import asyncio
                self._nc = asyncio.get_event_loop().run_until_complete(nats.connect(self.broker_url))
                self._connected = True
                return
            except Exception:
                pass
        if REDIS_AVAILABLE:
            self._redis_client = redis.Redis.from_url(self._redis_fallback_url)
            self._connected = True

    def _topic(self, event_type: str) -> str:
        return f"garcar.{self.system_name}.{event_type}"

    def publish(self, event_type: str, payload: dict):
        if not self._connected:
            self.connect()
        envelope = {
            "event_id": str(uuid.uuid4()),
            "system": self.system_name,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        topic = self._topic(event_type)
        message = json.dumps(envelope).encode("utf-8")

        if self._nc:
            import asyncio
            asyncio.get_event_loop().run_until_complete(self._nc.publish(topic, message))
        elif self._redis_client:
            self._redis_client.xadd(topic, {"data": message})
        else:
            print(f"[EventBus:offline] {topic} -> {envelope}")

    def subscribe(self, event_pattern: str, handler: Callable[[dict], None]):
        if not self._connected:
            self.connect()
        topic = f"garcar.*.{event_pattern}" if not event_pattern.startswith("garcar.") else event_pattern

        if self._redis_client:
            last_id = "$"
            while True:
                resp = self._redis_client.xread({topic: last_id}, block=5000)
                for _, messages in resp or []:
                    for msg_id, data in messages:
                        last_id = msg_id
                        envelope = json.loads(data[b"data"])
                        handler(envelope)
                time.sleep(0.1)
        else:
            print(f"[EventBus:offline] Would subscribe to {topic}")


def health_check(system_name: str) -> dict:
    return {
        "system": system_name,
        "event_bus_connected": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "note": "Wire GARCAR_EVENT_BROKER_URL env var to activate live connection",
    }
