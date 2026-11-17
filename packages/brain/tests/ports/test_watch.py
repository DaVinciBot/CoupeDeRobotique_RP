import asyncio

import pytest

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.ports.watch import Watch

# advance(0) lets the waiting tasks run without moving the time. The tasks are checked instead
# of awaited: a broken Watch fails an assertion instead of hanging the test.
pytestmark = pytest.mark.asyncio


def is_even(value: int) -> bool:
    return value % 2 == 0


async def test_get_gives_nothing_before_the_first_value_then_the_last_one() -> None:
    watch = Watch[int](FakeClock())
    assert watch.get() is None

    watch.set(1)
    watch.set(2)

    assert watch.get() == 2


async def test_wait_next_ignores_the_current_value() -> None:
    clock = FakeClock()
    watch = Watch[int](clock)
    watch.set(1)

    task = asyncio.create_task(watch.wait_next(timeout=1.0))
    await clock.advance(0)
    assert not task.done()

    watch.set(2)
    await clock.advance(0)

    assert task.result() == 2


async def test_wait_next_gives_nothing_once_the_timeout_is_over() -> None:
    clock = FakeClock()
    watch = Watch[int](clock)
    watch.set(1)

    task = asyncio.create_task(watch.wait_next(timeout=0.3))
    await clock.advance(0.299)
    assert not task.done()

    await clock.advance(0.001)

    assert task.result() is None


async def test_wait_next_gives_the_value_that_woke_it_even_if_overwritten() -> None:
    clock = FakeClock()
    watch = Watch[str](clock)

    task = asyncio.create_task(watch.wait_next(timeout=1.0))
    await clock.advance(0)
    watch.set("arrived")
    watch.set("moving")  # before the waiting task runs
    await clock.advance(0)

    assert task.result() == "arrived"


async def test_wait_next_can_be_cancelled() -> None:
    clock = FakeClock()
    watch = Watch[int](clock)

    task = asyncio.create_task(watch.wait_next(timeout=1.0))
    await clock.advance(0)
    task.cancel()
    await clock.advance(0)

    assert task.cancelled()


async def test_wait_for_returns_at_once_when_the_current_value_matches() -> None:
    clock = FakeClock()
    watch = Watch[int](clock)
    watch.set(4)

    task = asyncio.create_task(watch.wait_for(is_even, timeout=1.0))
    await clock.advance(0)

    assert task.result() == 4


async def test_wait_for_waits_for_a_matching_value() -> None:
    clock = FakeClock()
    watch = Watch[int](clock)
    watch.set(1)

    task = asyncio.create_task(watch.wait_for(is_even, timeout=1.0))
    for value in (3, 5):
        await clock.advance(0.1)
        watch.set(value)
    await clock.advance(0.1)
    assert not task.done()

    watch.set(6)
    await clock.advance(0)

    assert task.result() == 6


async def test_wait_for_sees_a_matching_value_even_if_overwritten() -> None:
    clock = FakeClock()
    watch = Watch[int](clock)

    task = asyncio.create_task(watch.wait_for(is_even, timeout=1.0))
    await clock.advance(0)
    watch.set(2)
    watch.set(3)  # before the waiting task runs
    await clock.advance(0)

    assert task.result() == 2


async def test_wait_for_gives_nothing_once_the_timeout_is_over() -> None:
    clock = FakeClock()
    watch = Watch[int](clock)

    task = asyncio.create_task(watch.wait_for(is_even, timeout=0.3))
    await clock.advance(0.2)
    watch.set(1)
    await clock.advance(0.099)
    assert not task.done()

    await clock.advance(0.001)

    assert task.result() is None


async def test_one_value_wakes_every_waiting_task() -> None:
    clock = FakeClock()
    watch = Watch[int](clock)

    tasks = [
        asyncio.create_task(watch.wait_next(timeout=1.0)),
        asyncio.create_task(watch.wait_next(timeout=1.0)),
        asyncio.create_task(watch.wait_for(is_even, timeout=1.0)),
    ]
    await clock.advance(0)
    watch.set(8)
    await clock.advance(0)

    assert [task.result() for task in tasks] == [8, 8, 8]
