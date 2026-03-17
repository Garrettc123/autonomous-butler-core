"""Shared pytest fixtures."""

import pytest

from src.bus import EventBus


@pytest.fixture
def event_bus():
    return EventBus()
