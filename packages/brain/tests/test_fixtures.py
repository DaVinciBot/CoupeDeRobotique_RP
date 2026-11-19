"""The shared fixtures of conftest.py: fake hardware on one fake clock, template edition."""

import pytest

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.domain.arena import Arena
from dvb_brain.domain.motion import MotionState
from dvb_brain.domain.strategy_model import Strategy
from dvb_brain.ports import Ports

pytestmark = pytest.mark.asyncio


async def test_ports_run_the_fake_hardware_on_the_test_clock(
    ports: Ports, clock: FakeClock
) -> None:
    assert ports.clock is clock

    await clock.advance(0.1)

    status = ports.motion.status().get()
    assert status is not None
    assert status.state is MotionState.STOPPED
    tracks = ports.lidar.tracks().get()
    assert tracks is not None
    assert (tracks.stamp, tracks.tracks) == (0.1, ())
    assert ports.start_switch.inserted()


async def test_arena_and_strategy_come_from_the_template_edition(
    arena: Arena, strategy: Strategy
) -> None:
    assert (arena.width, arena.depth) == (3.0, 2.0)
    assert (strategy.name, strategy.arena_id) == ("homologation", "_template")
