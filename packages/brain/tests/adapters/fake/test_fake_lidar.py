import asyncio

import pytest

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.adapters.fake.lidar import FakeLidar
from dvb_brain.domain.geometry import Vec2
from dvb_brain.domain.world import Track, TrackSet
from dvb_brain.ports.lidar import LidarPort

pytestmark = pytest.mark.asyncio

OPPONENT = Track(id=1, center=Vec2(1.5, 1.0), radius=0.2, velocity=Vec2(0.0, 0.0), confirmed=False)


async def test_publishes_the_scripted_tracks_once_per_period() -> None:
    clock = FakeClock()
    fake = FakeLidar(clock, period=0.1, tracks_at=lambda t: (OPPONENT,) if t >= 0.2 else ())
    lidar: LidarPort = fake
    received: list[TrackSet] = []

    async def read() -> None:
        while True:
            value = await lidar.tracks().wait_next(timeout=1.0)
            assert value is not None
            received.append(value)

    reader = asyncio.create_task(read())
    runner = asyncio.create_task(fake.run())
    await clock.advance(0.3)
    reader.cancel()
    runner.cancel()

    assert received == [
        TrackSet(stamp=0.0, tracks=()),
        TrackSet(stamp=0.1, tracks=()),
        TrackSet(stamp=0.2, tracks=(OPPONENT,)),
        TrackSet(stamp=0.3, tracks=(OPPONENT,)),
    ]


async def test_is_mute_while_the_script_gives_nothing() -> None:
    clock = FakeClock()
    fake = FakeLidar(clock, period=0.1, tracks_at=lambda t: None if t >= 0.15 else ())
    runner = asyncio.create_task(fake.run())
    await clock.advance(0.1)

    wait = asyncio.create_task(fake.tracks().wait_next(timeout=0.3))
    await clock.advance(0.3)
    runner.cancel()

    assert wait.result() is None
