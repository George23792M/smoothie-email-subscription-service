"""Tests for process-local delivery controls, independent of application wiring."""

import asyncio
from types import SimpleNamespace

import pytest

import app.services.email.delivery_limits as limits


@pytest.mark.parametrize("count", [0, -1, 4, True, 1.5])
def test_batch_bound_rejects_invalid_counts(count):
    """Reject invalid batch sizes independently of rate and concurrency."""
    limiter = limits.DeliveryLimits(3, 1, 2, 60)
    with pytest.raises(ValueError):
        limiter.validate_batch_size(count)


def test_batch_bound_accepts_both_endpoints():
    """The minimum and configured maximum batch counts are valid."""
    limiter = limits.DeliveryLimits(3, 1, 2, 60)
    assert limiter.validate_batch_size(1) is None
    assert limiter.validate_batch_size(3) is None


@pytest.mark.parametrize("args", [(0, 1, 1, 1), (1, 51, 1, 1), (1, 1, 0, 1),
                                  (1, 1, 1, float("nan")), (True, 1, 1, 1)])
def test_invalid_limiter_configuration_is_rejected(args):
    """Out-of-range, non-finite, and boolean settings fail closed."""
    with pytest.raises(ValueError):
        limits.DeliveryLimits(*args)


@pytest.mark.asyncio
async def test_concurrent_callers_share_the_in_flight_limit():
    """A second caller cannot enter while the sole in-flight slot is occupied."""
    limiter = limits.DeliveryLimits(2, 1, 10, 60)
    first_entered, release, second_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def first():
        async with limiter.send_slot():
            first_entered.set()
            await release.wait()

    async def second():
        async with limiter.send_slot():
            second_entered.set()

    first_task = asyncio.create_task(first())
    await first_entered.wait()
    second_task = asyncio.create_task(second())
    await asyncio.sleep(0)
    assert not second_entered.is_set()
    release.set()
    await asyncio.gather(first_task, second_task)
    assert second_entered.is_set()


@pytest.mark.asyncio
async def test_rolling_rate_waits_until_oldest_reservation_expires(monkeypatch):
    """The second reservation waits exactly until the window boundary."""
    limiter = limits.DeliveryLimits(2, 2, 1, 10)
    clock = [100.0]
    delays = []

    async def advance(delay):
        delays.append(delay)
        clock[0] += delay

    monkeypatch.setattr(limits, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(limits, "asyncio", SimpleNamespace(sleep=advance))
    async with limiter.send_slot():
        pass
    async with limiter.send_slot():
        pass
    assert delays == [10.0]
    assert list(limiter._timestamps) == [110.0]


def test_default_disabled_deployment_mode_fails_closed(monkeypatch):
    """The cached process-local limiter is not provided in disabled mode."""
    limits.get_delivery_limits.cache_clear()
    monkeypatch.setattr(limits.settings, "DELIVERY_LIMIT_MODE", "disabled")
    try:
        with pytest.raises(ValueError):
            limits.get_delivery_limits()
    finally:
        limits.get_delivery_limits.cache_clear()
