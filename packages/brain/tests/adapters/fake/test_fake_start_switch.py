import asyncio

import pytest

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.adapters.fake.start_switch import FakeStartSwitch
from dvb_brain.ports.start_switch import StartSwitchPort

pytestmark = pytest.mark.asyncio


async def test_wait_pulled_gives_the_time_of_the_pull() -> None:
    clock = FakeClock()
    fake = FakeStartSwitch(clock, inserted=True)
    switch: StartSwitchPort = fake

    task = asyncio.create_task(switch.wait_pulled())
    await clock.advance(2.5)
    assert not task.done()

    fake.pull()
    await clock.advance(0.1)

    assert task.result() == 2.5
    assert not switch.inserted()


async def test_a_cord_already_out_does_not_count() -> None:
    clock = FakeClock()
    fake = FakeStartSwitch(clock, inserted=False)

    task = asyncio.create_task(fake.wait_pulled())
    fake.pull()  # nothing to pull
    await clock.advance(1.0)
    assert not task.done()

    fake.insert()
    assert fake.inserted()
    await clock.advance(1.0)
    fake.pull()
    await clock.advance(0)

    assert task.result() == 2.0


async def test_a_pull_before_the_wait_does_not_count() -> None:
    clock = FakeClock()
    fake = FakeStartSwitch(clock, inserted=True)
    fake.pull()

    task = asyncio.create_task(fake.wait_pulled())
    await clock.advance(1.0)

    assert not task.done()
