"""Pytest configuration for async tests."""

import pytest

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
