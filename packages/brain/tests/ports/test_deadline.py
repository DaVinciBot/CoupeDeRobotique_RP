import asyncio

import pytest

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.ports.deadline import until

# As in test_watch.py: the tasks are checked after advance() instead of awaited.
pytestmark = pytest.mark.asyncio


async def answer_after(clock: FakeClock, dt: float, value: str) -> str:
    await clock.sleep(dt)
    return value


async def stop_on_cancel(clock: FakeClock, log: list[str]) -> str:
    """Wait long, and clean up on cancellation with an await, as a move() that sends its stop."""
    try:
        await clock.sleep(10.0)
    except asyncio.CancelledError:
        await asyncio.sleep(0)
        log.append("stopped")
        raise
    return "arrived"


async def test_until_gives_the_result_before_the_deadline() -> None:
    clock = FakeClock()

    task = asyncio.create_task(until(clock, answer_after(clock, 0.5, "done"), deadline=1.0))
    await clock.advance(0.5)

    assert task.result() == "done"


async def test_until_gives_nothing_at_the_deadline_and_cancels_the_wait() -> None:
    clock = FakeClock()
    wait = asyncio.create_task(answer_after(clock, 2.0, "late"))

    task = asyncio.create_task(until(clock, wait, deadline=1.0))
    await clock.advance(0.999)
    assert not task.done()
    await clock.advance(0.001)

    assert task.result() is None
    assert wait.cancelled()


async def test_until_returns_once_the_cancelled_wait_has_cleaned_up() -> None:
    clock = FakeClock()
    log: list[str] = []

    async def caller() -> str | None:
        result = await until(clock, stop_on_cancel(clock, log), deadline=1.0)
        log.append("returned")
        return result

    task = asyncio.create_task(caller())
    await clock.advance(1.0)

    assert task.result() is None
    assert log == ["stopped", "returned"]


async def test_until_passes_on_an_error_of_the_wait() -> None:
    clock = FakeClock()

    async def fail() -> str:
        await clock.sleep(0.1)
        raise RuntimeError("one move at a time")

    task = asyncio.create_task(until(clock, fail(), deadline=1.0))
    await clock.advance(0.1)

    with pytest.raises(RuntimeError, match="one move at a time"):
        task.result()


async def test_a_cancelled_caller_cancels_the_wait_and_waits_for_its_end() -> None:
    # The end of the match cancels a step, then sends the robot home at once (TODO 7.4): the
    # cancelled move must have ended by then, or the port would refuse the next one.
    clock = FakeClock()
    log: list[str] = []

    async def caller() -> str | None:
        try:
            return await until(clock, stop_on_cancel(clock, log), deadline=5.0)
        except asyncio.CancelledError:
            log.append("caller cancelled")
            raise

    task = asyncio.create_task(caller())
    await clock.advance(0.1)
    task.cancel()
    await clock.advance(0)

    assert task.cancelled()
    assert log == ["stopped", "caller cancelled"]
