"""
Built-in revenue streams.

Importing this package registers every stream with the shared
:data:`src.revenue.registry`, so the ``RevenueAgent`` can build them from
configuration without importing each module by hand.
"""

from src.revenue import registry
from src.revenue.streams.dunning import DunningStream
from src.revenue.streams.expansion import ExpansionStream
from src.revenue.streams.one_time import OneTimeStream
from src.revenue.streams.subscriptions import SubscriptionStream
from src.revenue.streams.usage_based import UsageBasedStream

ALL_STREAMS = (
    SubscriptionStream,
    UsageBasedStream,
    OneTimeStream,
    DunningStream,
    ExpansionStream,
)

for _stream_cls in ALL_STREAMS:
    registry.register(_stream_cls.id, _stream_cls)

__all__ = [
    "ALL_STREAMS",
    "DunningStream",
    "ExpansionStream",
    "OneTimeStream",
    "SubscriptionStream",
    "UsageBasedStream",
]
