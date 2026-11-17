import time

import pytest

from dvb_brain.adapters.clock import SystemClock
from dvb_brain.ports.clock import Clock

pytestmark = pytest.mark.asyncio

# asyncio may fire a timer up to its clock resolution early.
EARLY = 1e-3


async def test_now_is_the_monotonic_time() -> None:
    clock: Clock = SystemClock()

    before = time.monotonic()
    now = clock.now()

    assert before <= now <= time.monotonic()


async def test_sleep_waits_dt() -> None:
    clock = SystemClock()
    start = clock.now()

    await clock.sleep(0.02)

    assert clock.now() - start >= 0.02 - EARLY


async def test_sleep_until_waits_until_t() -> None:
    clock = SystemClock()
    t = clock.now() + 0.02

    await clock.sleep_until(t)

    assert clock.now() >= t - EARLY


async def test_sleep_until_a_past_time_returns_at_once() -> None:
    clock = SystemClock()
    start = clock.now()

    await clock.sleep_until(start - 1.0)

    assert clock.now() - start < 0.01
