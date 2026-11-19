"""The fake motor board: ideal trapezoids, and the failures a test injects (TODO 3.5).

The contract of the motion port is tested once for every adapter in tests/ports.
"""

import asyncio
import math
from collections.abc import AsyncIterator
from contextlib import suppress

import pytest
import pytest_asyncio

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.adapters.fake.motion import FakeMotion
from dvb_brain.domain.geometry import Pose, Vec2
from dvb_brain.domain.motion import (
    GoToPoint,
    MotionState,
    MotionStatus,
    PushUntilBlocked,
    RotateBy,
    RotateTo,
    StopMode,
    Straight,
)

# The tasks are checked after advance() instead of awaited: a broken fake fails an assertion
# instead of hanging the test.
pytestmark = pytest.mark.asyncio

START = Pose(0.5, 0.5, 0.0)
PERIOD = 0.05  # s
STOP_DECEL = 1.0  # m/s²
ROTATION_SPEED = math.pi  # rad/s
ROTATION_ACCEL = 2 * math.pi  # rad/s²


@pytest_asyncio.fixture
async def motion(clock: FakeClock) -> AsyncIterator[FakeMotion]:
    fake = FakeMotion(
        clock,
        pose=START,
        rotation_speed=ROTATION_SPEED,
        rotation_accel=ROTATION_ACCEL,
        stop_decel=STOP_DECEL,
        status_period=PERIOD,
    )
    task = asyncio.create_task(fake.run())
    yield fake
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def last(motion: FakeMotion) -> MotionStatus:
    status = motion.status().get()
    assert status is not None
    return status


def assert_pose(pose: Pose, x: float, y: float, theta: float) -> None:
    assert (pose.x, pose.y, pose.theta) == pytest.approx((x, y, theta), abs=1e-9)


async def test_publishes_a_status_every_period(clock: FakeClock, motion: FakeMotion) -> None:
    times: list[float] = []

    async def record() -> None:
        while (status := await motion.status().wait_next(timeout=1.0)) is not None:
            times.append(status.teensy_time)

    reader = asyncio.create_task(record())
    await clock.advance(0.1)
    reader.cancel()

    assert times == [0.05, 0.1]
    status = last(motion)
    assert (status.move_id, status.state, status.pose) == (0, MotionState.STOPPED, START)
    assert (status.v, status.omega, status.emergency_stop) == (0.0, 0.0, False)


async def test_a_straight_follows_a_trapezoid(clock: FakeClock, motion: FakeMotion) -> None:
    # 1 s to reach 0.5 m/s over 0.25 m, 1 s at 0.5 m/s, 1 s to stop.
    task = asyncio.create_task(motion.move(Straight(1.0, max_speed=0.5, max_accel=0.5)))
    await clock.advance(1.0)
    status = last(motion)
    assert (status.move_id, status.state) == (1, MotionState.MOVING)
    assert (status.pose.x, status.v) == pytest.approx((0.75, 0.5))

    await clock.advance(1.0)
    assert last(motion).pose.x == pytest.approx(1.25)
    assert not task.done()

    await clock.advance(1.0)
    result = task.result()
    assert (result.move_id, result.state, result.v) == (1, MotionState.ARRIVED, 0.0)
    assert_pose(result.pose, 1.5, 0.5, 0.0)


async def test_a_short_straight_follows_a_triangle(clock: FakeClock, motion: FakeMotion) -> None:
    # Too short to reach 0.5 m/s: 0.447 s up to 0.224 m/s, 0.447 s down.
    task = asyncio.create_task(motion.move(Straight(0.1, max_speed=0.5, max_accel=0.5)))
    await clock.advance(0.85)
    assert not task.done()

    await clock.advance(0.1)

    assert task.result().state is MotionState.ARRIVED
    assert_pose(task.result().pose, 0.6, 0.5, 0.0)


async def test_a_negative_straight_goes_backwards(clock: FakeClock, motion: FakeMotion) -> None:
    task = asyncio.create_task(motion.move(Straight(-0.2, max_speed=0.5, max_accel=0.5)))
    await clock.advance(0.3)
    assert last(motion).v < 0

    await clock.advance(1.0)

    assert_pose(task.result().pose, 0.3, 0.5, 0.0)


async def test_rotate_to_takes_the_shortest_way(clock: FakeClock, motion: FakeMotion) -> None:
    # A quarter turn clockwise: 0.5 s up to pi rad/s, 0.5 s down.
    task = asyncio.create_task(motion.move(RotateTo(3 * math.pi / 2)))
    await clock.advance(0.5)
    status = last(motion)
    assert (status.v, status.omega) == pytest.approx((0.0, -math.pi))

    await clock.advance(0.5)

    assert task.result().state is MotionState.ARRIVED
    assert_pose(task.result().pose, 0.5, 0.5, -math.pi / 2)


async def test_rotate_by_turns_by_the_angle(clock: FakeClock, motion: FakeMotion) -> None:
    task = asyncio.create_task(motion.move(RotateBy(math.pi)))
    await clock.advance(1.45)
    assert not task.done()

    await clock.advance(0.05)

    assert_pose(task.result().pose, 0.5, 0.5, math.pi)


async def test_go_to_point_turns_then_goes_straight(clock: FakeClock, motion: FakeMotion) -> None:
    # A quarter turn in 1 s, then 0.5 m in 2 s.
    task = asyncio.create_task(motion.move(GoToPoint(Vec2(0.5, 1.0), max_speed=0.5, max_accel=0.5)))
    await clock.advance(0.5)
    assert (last(motion).v, last(motion).omega) == pytest.approx((0.0, math.pi))

    await clock.advance(1.5)
    status = last(motion)
    assert (status.pose.y, status.pose.theta, status.v) == pytest.approx((0.75, math.pi / 2, 0.5))

    await clock.advance(1.0)

    assert task.result().state is MotionState.ARRIVED
    assert_pose(task.result().pose, 0.5, 1.0, math.pi / 2)


async def test_push_until_blocked_ends_stopped_without_contact(
    clock: FakeClock, motion: FakeMotion
) -> None:
    task = asyncio.create_task(motion.move(PushUntilBlocked(0.2, max_speed=0.2, max_accel=0.5)))
    await clock.advance(2.0)

    assert task.result().state is MotionState.STOPPED
    assert_pose(task.result().pose, 0.7, 0.5, 0.0)


async def test_push_until_blocked_ends_blocked_on_contact(
    clock: FakeClock, motion: FakeMotion
) -> None:
    motion.block_after(0.05)
    task = asyncio.create_task(motion.move(PushUntilBlocked(0.2, max_speed=0.2, max_accel=0.5)))
    await clock.advance(2.0)

    assert (task.result().state, task.result().v) == (MotionState.BLOCKED, 0.0)
    assert_pose(task.result().pose, 0.55, 0.5, 0.0)


async def test_a_block_stops_the_next_translation_only(
    clock: FakeClock, motion: FakeMotion
) -> None:
    motion.block_after(0.1)
    turn = asyncio.create_task(motion.move(RotateBy(0.1)))
    await clock.advance(1.0)
    assert turn.result().state is MotionState.ARRIVED

    blocked = asyncio.create_task(motion.move(Straight(0.5, max_speed=0.5, max_accel=0.5)))
    await clock.advance(2.0)
    assert blocked.result().state is MotionState.BLOCKED
    assert blocked.result().pose.x == pytest.approx(0.5 + 0.1 * math.cos(0.1))

    free = asyncio.create_task(motion.move(Straight(0.1, max_speed=0.5, max_accel=0.5)))
    await clock.advance(2.0)
    assert free.result().state is MotionState.ARRIVED


async def test_smooth_stop_brakes_a_rotation_with_the_rotation_accel(
    clock: FakeClock, motion: FakeMotion
) -> None:
    task = asyncio.create_task(motion.move(RotateBy(2 * math.pi)))
    await clock.advance(1.0)  # at pi rad/s
    at_stop = last(motion)

    await motion.stop(StopMode.SMOOTH)
    await clock.advance(1.0)

    # pi² / (2 · 2 pi) = pi / 4 to stop
    assert task.result().state is MotionState.STOPPED
    assert task.result().pose.theta == pytest.approx(at_stop.pose.theta + math.pi / 4)


async def test_keeps_the_heartbeats_and_the_stops_sent(
    clock: FakeClock, motion: FakeMotion
) -> None:
    await motion.heartbeat()
    await clock.advance(0.05)
    await motion.heartbeat()
    await motion.stop(StopMode.SMOOTH)
    await motion.stop(StopMode.URGENT)
    await motion.stop(StopMode.SMOOTH)  # after an urgent stop, nothing is sent

    assert motion.heartbeats == [0.0, 0.05]
    assert motion.stops == [(0.05, StopMode.SMOOTH), (0.05, StopMode.URGENT)]


async def test_a_cancelled_move_sends_a_smooth_stop(clock: FakeClock, motion: FakeMotion) -> None:
    move = asyncio.create_task(motion.move(Straight(1.0, max_speed=0.5, max_accel=0.5)))
    await clock.advance(0.5)

    move.cancel()
    await clock.advance(0)

    assert move.cancelled()
    assert motion.stops == [(0.5, StopMode.SMOOTH)]


async def test_a_move_cancelled_after_an_urgent_stop_sends_nothing(
    clock: FakeClock, motion: FakeMotion
) -> None:
    move = asyncio.create_task(motion.move(Straight(1.0, max_speed=0.5, max_accel=0.5)))
    await clock.advance(0.5)

    await motion.stop(StopMode.URGENT)
    move.cancel()
    await clock.advance(0.05)

    assert move.cancelled()
    assert motion.stops == [(0.5, StopMode.URGENT)]


async def test_a_silent_board_publishes_nothing_and_loses_the_commands(
    clock: FakeClock, motion: FakeMotion
) -> None:
    motion.silence()
    waiting = asyncio.create_task(motion.status().wait_next(timeout=0.3))
    move = asyncio.create_task(motion.move(Straight(0.1, max_speed=0.5, max_accel=0.5)))

    await motion.heartbeat()
    await motion.stop(StopMode.SMOOTH)
    await clock.advance(1.0)

    assert waiting.result() is None
    assert not move.done()
    assert motion.link_ok()
    assert (motion.heartbeats, motion.stops) == ([0.0], [(0.0, StopMode.SMOOTH)])
    move.cancel()


async def test_a_restart_gives_a_new_boot_id_and_loses_the_pose(
    clock: FakeClock, motion: FakeMotion
) -> None:
    move = asyncio.create_task(motion.move(Straight(1.0, max_speed=0.5, max_accel=0.5)))
    await clock.advance(0.5)
    before = last(motion)

    motion.restart()
    await clock.advance(0.05)

    after = last(motion)
    assert after.boot_id != before.boot_id
    assert (after.move_id, after.state, after.pose) == (0, MotionState.STOPPED, Pose(0, 0, 0))
    assert after.teensy_time == pytest.approx(0.05)
    await clock.advance(3.0)
    assert not move.done()  # the brain sees the new boot_id (SafetyMonitor)
    move.cancel()


async def test_the_emergency_stop_stops_the_robot_at_once(
    clock: FakeClock, motion: FakeMotion
) -> None:
    move = asyncio.create_task(motion.move(Straight(1.0, max_speed=0.5, max_accel=0.5)))
    await clock.advance(1.0)

    motion.press_emergency_stop()
    await clock.advance(0.05)

    result = move.result()
    assert (result.state, result.v, result.emergency_stop) == (MotionState.STOPPED, 0.0, True)
    assert result.pose.x == pytest.approx(0.75)

    again = asyncio.create_task(motion.move(Straight(0.5, max_speed=0.5, max_accel=0.5)))
    await clock.advance(0.05)
    assert again.result().state is MotionState.STOPPED
    assert again.result().pose.x == pytest.approx(0.75)

    motion.release_emergency_stop()
    await clock.advance(0.05)
    assert not last(motion).emergency_stop
