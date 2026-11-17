import asyncio

import pytest

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.ports.clock import Clock

# The tasks are checked after advance() instead of awaited: a broken clock fails an assertion
# instead of hanging the test. The test loop cancels the tasks left at the end.
pytestmark = pytest.mark.asyncio


async def test_time_only_moves_with_advance() -> None:
    fake = FakeClock(start=12.0)
    clock: Clock = fake
    assert clock.now() == 12.0

    await fake.advance(0.5)

    assert clock.now() == 12.5


async def test_advance_wakes_sleepers_in_deadline_order_at_their_deadline() -> None:
    clock = FakeClock()
    woken: list[tuple[str, float]] = []

    async def sleeper(name: str, t: float) -> None:
        await clock.sleep_until(t)
        woken.append((name, clock.now()))

    tasks = [
        asyncio.create_task(sleeper(name, t))
        for name, t in (("late", 0.3), ("early", 0.1), ("middle", 0.2))
    ]
    await clock.advance(1.0)

    assert all(task.done() for task in tasks)
    assert woken == [("early", 0.1), ("middle", 0.2), ("late", 0.3)]
    assert clock.now() == 1.0


async def test_sleepers_with_the_same_deadline_wake_first_come_first_served() -> None:
    clock = FakeClock()
    woken: list[str] = []

    async def sleeper(name: str) -> None:
        await clock.sleep(0.1)
        woken.append(name)

    tasks = [asyncio.create_task(sleeper(name)) for name in ("first", "second", "third")]
    await clock.advance(0.1)

    assert all(task.done() for task in tasks)
    assert woken == ["first", "second", "third"]


async def test_advance_does_not_wake_a_sleeper_before_its_deadline() -> None:
    clock = FakeClock()
    task = asyncio.create_task(clock.sleep_until(0.3))

    await clock.advance(0.2)
    assert not task.done()

    await clock.advance(0.1)
    assert task.done()


async def test_a_periodic_task_wakes_at_each_period_within_one_advance() -> None:
    clock = FakeClock()
    ticks: list[float] = []

    async def heartbeat() -> None:
        while True:
            await clock.sleep(0.05)
            ticks.append(clock.now())

    task = asyncio.create_task(heartbeat())
    await clock.advance(0.2)

    assert not task.done()  # asleep until the next period
    assert ticks == [0.05, 0.1, 0.15, 0.2]


@pytest.mark.parametrize(("period", "window", "wakes"), [(0.05, 1.0, 20), (0.1, 0.3, 3)])
async def test_a_periodic_task_does_not_drift_with_rounding(
    period: float, window: float, wakes: int
) -> None:
    clock = FakeClock()
    ticks: list[float] = []

    async def periodic() -> None:
        while True:
            await clock.sleep(period)
            ticks.append(clock.now())

    task = asyncio.create_task(periodic())
    await clock.advance(window)
    await clock.advance(100.0 - window)

    assert not task.done()
    assert len(ticks) == round(100.0 / period)
    assert ticks[wakes - 1] == window
    assert ticks[-1] == 100.0


async def test_a_task_created_just_before_advance_sleeps_from_the_time_before_the_jump() -> None:
    clock = FakeClock()
    woken_at: list[float] = []

    async def sleeper() -> None:
        await clock.sleep(0.1)
        woken_at.append(clock.now())

    task = asyncio.create_task(sleeper())
    await clock.advance(0.2)

    assert task.done()
    assert woken_at == [0.1]


async def test_a_long_chain_of_woken_tasks_runs_before_the_next_deadline() -> None:
    clock = FakeClock()
    links = [asyncio.Event() for _ in range(200)]
    seen_at: list[float] = []

    async def first() -> None:
        await clock.sleep_until(0.1)
        links[0].set()

    async def link(i: int) -> None:
        await links[i].wait()
        seen_at.append(clock.now())
        if i + 1 < len(links):
            links[i + 1].set()

    async def late() -> None:
        await clock.sleep_until(0.2)
        seen_at.append(clock.now())

    tasks = [
        asyncio.create_task(first()),
        *(asyncio.create_task(link(i)) for i in range(len(links))),
        asyncio.create_task(late()),
    ]
    await clock.advance(1.0)

    assert all(task.done() for task in tasks)
    assert seen_at == [0.1] * len(links) + [0.2]


async def test_sleep_until_never_wakes_before_its_time() -> None:
    clock = FakeClock(start=0.1)
    t = clock.now() + 0.2  # 0.30000000000000004, between two nanoseconds
    woken_at: list[float] = []

    async def sleeper() -> None:
        await clock.sleep_until(t)
        woken_at.append(clock.now())

    task = asyncio.create_task(sleeper())
    await clock.advance(0.3)

    assert task.done()
    assert woken_at[0] >= t  # else "wait while time is left" loops would spin at once


async def test_a_positive_sleep_below_one_nanosecond_still_moves_the_time() -> None:
    clock = FakeClock(start=0.1)
    deadline = clock.now() + 0.2  # 0.30000000000000004, between two nanoseconds

    async def wait_until_deadline() -> None:
        while (left := deadline - clock.now()) > 0:
            await clock.sleep(left)  # the last left is about 5.5e-17 s

    task = asyncio.create_task(wait_until_deadline())
    await clock.advance(0.3)

    assert task.done()
    assert clock.now() >= deadline


async def test_sleep_until_a_past_time_returns_without_advance() -> None:
    clock = FakeClock(start=5.0)

    await asyncio.wait_for(clock.sleep_until(4.0), timeout=1.0)
    await asyncio.wait_for(clock.sleep(0.0), timeout=1.0)

    assert clock.now() == 5.0


async def test_a_cancelled_sleeper_is_skipped() -> None:
    clock = FakeClock()
    cancelled = asyncio.create_task(clock.sleep(0.1))
    kept = asyncio.create_task(clock.sleep(0.2))
    await asyncio.sleep(0)

    cancelled.cancel()
    await clock.advance(0.3)

    assert cancelled.cancelled()
    assert kept.done()
    assert not kept.cancelled()


async def test_advance_refuses_to_go_back_in_time() -> None:
    clock = FakeClock()

    with pytest.raises(ValueError, match=r"dt = -0\.1"):
        await clock.advance(-0.1)


async def test_advance_fails_loudly_on_a_task_that_never_blocks() -> None:
    clock = FakeClock()

    async def spin() -> None:
        for _ in range(1_000_000):
            await asyncio.sleep(0)

    task = asyncio.create_task(spin())

    with pytest.raises(RuntimeError, match="never blocks"):
        await clock.advance(0.1)
    assert not task.done()
