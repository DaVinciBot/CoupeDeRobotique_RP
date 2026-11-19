"""Fixtures of the brain tests: fake clock, fake hardware and the template edition (TODO 3.5).

The values below describe the fakes, not the robot, which is described in config/robot.json.
The fakes that publish on their own run in a task, cancelled at the end of the test.
"""

import asyncio
import math
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path

import pytest
import pytest_asyncio

from dvb_brain.adapters.fake.actuators import FakeActuators
from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.adapters.fake.lidar import FakeLidar
from dvb_brain.adapters.fake.motion import FakeMotion
from dvb_brain.adapters.fake.remote_vision import FakeRemoteVision
from dvb_brain.adapters.fake.start_switch import FakeStartSwitch
from dvb_brain.adapters.fake.telemetry import FakeTelemetry
from dvb_brain.domain.arena import Arena, parse_arena
from dvb_brain.domain.geometry import Pose
from dvb_brain.domain.strategy_model import Strategy, parse_strategy
from dvb_brain.ports import Ports

TEMPLATE = Path(__file__).parents[3] / "editions" / "_template"

START_POSE = Pose(0.25, 0.25, 0.0)  # m, rad
ROTATION_SPEED = math.pi  # rad/s
ROTATION_ACCEL = 2 * math.pi  # rad/s²
STOP_DECEL = 1.0  # m/s²
MOTION_STATUS_PERIOD = 0.05  # s
LIDAR_PERIOD = 0.1  # s
ACTUATOR_DURATIONS = {"gripper": 0.5, "lift": 1.0}  # s
SENSORS = ("gripper_loaded",)


async def _cancel(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def arena() -> Arena:
    return parse_arena((TEMPLATE / "arena.json").read_bytes())


@pytest.fixture
def strategy() -> Strategy:
    return parse_strategy((TEMPLATE / "strategies" / "homologation.strategy.json").read_bytes())


@pytest_asyncio.fixture
async def fake_motion(clock: FakeClock) -> AsyncIterator[FakeMotion]:
    fake = FakeMotion(
        clock,
        pose=START_POSE,
        rotation_speed=ROTATION_SPEED,
        rotation_accel=ROTATION_ACCEL,
        stop_decel=STOP_DECEL,
        status_period=MOTION_STATUS_PERIOD,
    )
    task = asyncio.create_task(fake.run())
    yield fake
    await _cancel(task)


@pytest_asyncio.fixture
async def fake_lidar(clock: FakeClock) -> AsyncIterator[FakeLidar]:
    fake = FakeLidar(clock, period=LIDAR_PERIOD, tracks_at=lambda _t: ())
    task = asyncio.create_task(fake.run())
    yield fake
    await _cancel(task)


@pytest.fixture
def fake_actuators(clock: FakeClock) -> FakeActuators:
    return FakeActuators(clock, durations=ACTUATOR_DURATIONS, sensors=SENSORS)


@pytest.fixture
def fake_start_switch(clock: FakeClock) -> FakeStartSwitch:
    return FakeStartSwitch(clock, inserted=True)


@pytest.fixture
def fake_remote_vision(clock: FakeClock) -> FakeRemoteVision:
    return FakeRemoteVision(clock)


@pytest.fixture
def fake_telemetry() -> FakeTelemetry:
    return FakeTelemetry()


@pytest.fixture
def ports(
    clock: FakeClock,
    fake_motion: FakeMotion,
    fake_actuators: FakeActuators,
    fake_lidar: FakeLidar,
    fake_remote_vision: FakeRemoteVision,
    fake_start_switch: FakeStartSwitch,
    fake_telemetry: FakeTelemetry,
) -> Ports:
    return Ports(
        clock=clock,
        motion=fake_motion,
        actuators=fake_actuators,
        lidar=fake_lidar,
        remote_vision=fake_remote_vision,
        start_switch=fake_start_switch,
        telemetry=fake_telemetry,
    )
