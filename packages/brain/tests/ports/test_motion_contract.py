"""Contract of the motion port (ADR 0010, ADR 0003), the same for every adapter.

Today the fake motor board only; the simulated base (TODO 11.2) and the Teensy adapter on the
virtual board (TODO 15.1) join the harness fixture.
"""

import asyncio
import math
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass

import pytest
import pytest_asyncio

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.adapters.fake.motion import FakeMotion
from dvb_brain.domain.geometry import Pose, angle_diff
from dvb_brain.domain.motion import MotionState, MotionStatus, MoveCommand, MoveKind, StopMode
from dvb_brain.ports.motion import MotionPort

# The tasks are checked after advance() instead of awaited: a broken port fails an assertion
# instead of hanging the test.
pytestmark = pytest.mark.asyncio

START = Pose(0.5, 0.5, 0.0)
MAX_ACCEL = 1.0  # m/s², board setting: also the deceleration of a smooth stop


@dataclass(frozen=True, slots=True)
class MotionHarness:
    port: MotionPort
    advance: Callable[[float], Awaitable[None]]  # let the time go by, fake or real
    kill_link: Callable[[], None]  # the board stops answering
    received_stops: Callable[[], list[StopMode]]  # what the board received
    received_heartbeats: Callable[[], int]
    start: Pose
    max_accel: float  # m/s², the MAX_ACCEL setting of the board (ADR 0003)


@pytest_asyncio.fixture
async def harness() -> AsyncIterator[MotionHarness]:
    clock = FakeClock()
    fake = FakeMotion(
        clock,
        pose=START,
        max_speed=1.0,
        max_accel=MAX_ACCEL,
        max_angular_speed=math.pi,
        max_angular_accel=2 * math.pi,
        vbat=16.0,
        status_period=0.05,
    )
    task = asyncio.create_task(fake.run())
    yield MotionHarness(
        port=fake,
        advance=clock.advance,
        kill_link=fake.silence,
        received_stops=lambda: [mode for _, mode in fake.stops],
        received_heartbeats=lambda: len(fake.heartbeats),
        start=START,
        max_accel=MAX_ACCEL,
    )
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def last(harness: MotionHarness) -> MotionStatus:
    status = harness.port.status().get()
    assert status is not None
    return status


def assert_refused(call: Coroutine[object, object, object]) -> None:
    """Check that the call raises RuntimeError before its first await, so that nothing else
    runs in between; a call that waits fails instead of hanging."""
    task = asyncio.create_task(call, eager_start=True)
    if not task.done():
        task.cancel()
        pytest.fail("the call waits instead of being refused")
    assert isinstance(task.exception(), RuntimeError)


async def assert_returns(harness: MotionHarness, call: Coroutine[object, object, None]) -> None:
    """Check that the call returns without waiting for the board, and does not raise."""
    task = asyncio.create_task(call)
    await harness.advance(0)
    if not task.done():
        task.cancel()
        pytest.fail("the call waits for the board")
    task.result()


async def returned(harness: MotionHarness, call: Coroutine[object, object, bool]) -> bool:
    """Return what the call returns, checking that it does not wait for the board."""
    task = asyncio.create_task(call)
    await harness.advance(0)
    if not task.done():
        task.cancel()
        pytest.fail("the call waits for the board")
    return task.result()


def straight(distance: float, max_accel: float = 0.5) -> MoveCommand:
    return MoveCommand(MoveKind.STRAIGHT, distance=distance, max_speed=0.5, max_accel=max_accel)


def goto_ahead(harness: MotionHarness, distance: float) -> MoveCommand:
    """A GOTO to a point straight ahead: no turn before the line."""
    return MoveCommand(
        MoveKind.GOTO,
        x=harness.start.x + distance,
        y=harness.start.y,
        max_speed=0.5,
        max_accel=0.5,
    )


async def test_move_ends_arrived_at_the_target_with_a_new_move_id(harness: MotionHarness) -> None:
    first = asyncio.create_task(harness.port.move(straight(0.2)))
    await harness.advance(2.0)
    second = asyncio.create_task(harness.port.move(MoveCommand(MoveKind.ROTATE_BY, theta=0.5)))
    await harness.advance(2.0)

    assert (first.result().state, second.result().state) == (MotionState.ARRIVED,) * 2
    assert first.result().pose.x == pytest.approx(harness.start.x + 0.2, abs=1e-3)
    assert second.result().pose.theta == pytest.approx(harness.start.theta + 0.5, abs=1e-3)
    assert second.result().move_id != first.result().move_id


async def test_a_second_move_is_refused_while_one_runs(harness: MotionHarness) -> None:
    first = asyncio.create_task(harness.port.move(straight(0.5)))
    await harness.advance(0.1)

    assert_refused(harness.port.move(straight(0.1)))

    await harness.advance(3.0)
    assert first.result().state is MotionState.ARRIVED


async def test_cancelling_move_stops_the_robot_short_of_the_target(harness: MotionHarness) -> None:
    task = asyncio.create_task(harness.port.move(straight(1.0)))
    await harness.advance(1.0)

    task.cancel()
    await harness.advance(1.0)

    assert task.cancelled()
    status = last(harness)
    assert (status.state, status.v) == (MotionState.STOPPED, 0.0)
    assert status.pose.x < harness.start.x + 0.9


async def test_smooth_stop_brakes_with_the_max_accel_of_the_board(harness: MotionHarness) -> None:
    # The move would brake over 0.5 m with its own max_accel; the stop uses the MAX_ACCEL setting
    # of the board, the deceleration of the safety zone (ADR 0003, ADR 0010).
    task = asyncio.create_task(harness.port.move(straight(2.0, max_accel=0.25)))
    await harness.advance(3.0)
    at_stop = last(harness)
    assert at_stop.v == pytest.approx(0.5)

    await harness.port.stop(StopMode.SMOOTH)
    await harness.advance(1.0)

    assert task.result().state is MotionState.STOPPED
    braking = task.result().pose.x - at_stop.pose.x
    assert braking == pytest.approx(0.5**2 / (2 * harness.max_accel), abs=0.02)


async def test_urgent_stop_is_immediate_and_final(harness: MotionHarness) -> None:
    task = asyncio.create_task(harness.port.move(straight(1.0)))
    await harness.advance(1.5)
    at_stop = last(harness)

    await assert_returns(harness, harness.port.stop(StopMode.URGENT))
    await harness.advance(0.5)

    assert (task.result().state, task.result().v) == (MotionState.STOPPED, 0.0)
    assert task.result().pose.x == pytest.approx(at_stop.pose.x, abs=0.01)
    assert_refused(harness.port.move(straight(0.1)))
    assert_refused(harness.port.reset_pose(harness.start))
    await assert_returns(harness, harness.port.stop(StopMode.SMOOTH))
    await assert_returns(harness, harness.port.heartbeat())
    assert harness.received_stops() == [StopMode.URGENT]  # nothing softens the urgent stop
    assert harness.received_heartbeats() == 1  # the heartbeat goes on


async def test_a_move_cancelled_after_an_urgent_stop_sends_no_smooth_stop(
    harness: MotionHarness,
) -> None:
    task = asyncio.create_task(harness.port.move(straight(1.0)))
    await harness.advance(0.5)

    await assert_returns(harness, harness.port.stop(StopMode.URGENT))
    task.cancel()
    await harness.advance(0.1)

    assert harness.received_stops() == [StopMode.URGENT]


async def test_urgent_stop_is_recorded_before_its_first_await(harness: MotionHarness) -> None:
    stop = asyncio.create_task(harness.port.stop(StopMode.URGENT))
    await asyncio.sleep(0)  # the stop starts, and may not be over

    assert_refused(harness.port.move(straight(0.1)))
    await harness.advance(0.1)
    assert stop.done()


async def test_stop_and_heartbeat_never_raise_with_a_dead_link(harness: MotionHarness) -> None:
    task = asyncio.create_task(harness.port.move(straight(1.0)))
    await harness.advance(0.5)

    harness.kill_link()
    await assert_returns(harness, harness.port.heartbeat())
    await assert_returns(harness, harness.port.stop(StopMode.SMOOTH))
    await assert_returns(harness, harness.port.stop(StopMode.URGENT))
    await harness.advance(0.5)
    task.cancel()  # move() does not see the dead link: the caller bounds its wait
    await harness.advance(0)

    assert task.cancelled()


async def test_reset_pose_waits_for_a_still_robot(harness: MotionHarness) -> None:
    new_pose = Pose(1.0, 1.0, math.pi / 2)
    task = asyncio.create_task(harness.port.move(straight(1.0)))
    await harness.advance(0)
    assert_refused(harness.port.reset_pose(new_pose))  # before any MOVING status
    await harness.advance(1.0)
    assert_refused(harness.port.reset_pose(new_pose))

    task.cancel()
    await harness.advance(0.1)
    assert last(harness).state is MotionState.MOVING  # still braking
    assert_refused(harness.port.reset_pose(new_pose))

    await harness.advance(1.0)
    reset = asyncio.create_task(harness.port.reset_pose(new_pose))
    await harness.advance(0)
    assert not reset.done()  # until a status shows the new pose

    await harness.advance(0.1)
    assert reset.done()
    reset.result()
    # float32 on the wire, theta wrapped by the board (ADR 0003): equal within a tolerance
    pose = last(harness).pose
    assert (pose.x, pose.y) == pytest.approx((new_pose.x, new_pose.y), abs=1e-6)
    assert angle_diff(pose.theta, new_pose.theta) == pytest.approx(0.0, abs=1e-6)


async def test_reset_pose_is_refused_while_a_cancelled_move_brakes_unseen(
    harness: MotionHarness,
) -> None:
    # The fake board publishes no status between 0 and 0.04 s: the last one says STOPPED.
    task = asyncio.create_task(harness.port.move(straight(1.0, max_accel=5.0)))
    await harness.advance(0.04)

    task.cancel()
    await harness.advance(0)

    assert_refused(harness.port.reset_pose(harness.start))  # it brakes from 0.2 m/s for 0.2 s


async def test_set_max_speed_slows_the_running_goto_without_stopping(
    harness: MotionHarness,
) -> None:
    task = asyncio.create_task(harness.port.move(goto_ahead(harness, 2.0)))
    await harness.advance(2.0)
    assert last(harness).v == pytest.approx(0.5, abs=0.02)

    assert await returned(harness, harness.port.set_max_speed(0.2))
    for _ in range(20):  # down to 0.2 m/s in 0.6 s at 0.5 m/s², never stopped
        await harness.advance(0.05)
        assert last(harness).state is MotionState.MOVING
        assert last(harness).v >= 0.2 - 0.02
    assert last(harness).v == pytest.approx(0.2, abs=0.02)

    await harness.advance(7.0)
    result = task.result()
    assert result.state is MotionState.ARRIVED
    assert result.pose.x == pytest.approx(harness.start.x + 2.0, abs=1e-3)


async def test_set_max_speed_needs_a_running_goto(harness: MotionHarness) -> None:
    assert not await returned(harness, harness.port.set_max_speed(0.2))

    # STRAIGHT is relative: sent again, it would start over from the measured pose (ADR 0003)
    task = asyncio.create_task(harness.port.move(straight(0.5)))
    await harness.advance(0.5)
    assert not await returned(harness, harness.port.set_max_speed(0.2))

    await harness.advance(2.0)
    assert task.result().state is MotionState.ARRIVED
    assert task.result().pose.x == pytest.approx(harness.start.x + 0.5, abs=1e-3)


async def test_set_max_speed_never_starts_a_stopped_goto_again(harness: MotionHarness) -> None:
    task = asyncio.create_task(harness.port.move(goto_ahead(harness, 2.0)))
    await harness.advance(1.0)
    await harness.port.stop(StopMode.SMOOTH)

    assert not await returned(harness, harness.port.set_max_speed(0.2))
    await harness.advance(1.0)
    assert task.result().state is MotionState.STOPPED
    stopped = task.result().pose

    await harness.advance(1.0)
    assert last(harness).pose == stopped

    await assert_returns(harness, harness.port.stop(StopMode.URGENT))
    assert not await returned(harness, harness.port.set_max_speed(0.2))


async def test_set_max_speed_is_false_once_the_goto_has_ended(harness: MotionHarness) -> None:
    task = asyncio.create_task(harness.port.move(goto_ahead(harness, 0.5)))
    await harness.advance(3.0)
    assert task.result().state is MotionState.ARRIVED

    assert not await returned(harness, harness.port.set_max_speed(0.2))


@pytest.mark.parametrize("max_speed", [0.0, -0.1, math.nan, math.inf])
async def test_set_max_speed_refuses_a_speed_the_board_would_not_apply(
    harness: MotionHarness, max_speed: float
) -> None:
    # 0 or less: the board limit; not finite: the board ignores the MOVE (ADR 0003)
    task = asyncio.create_task(harness.port.move(goto_ahead(harness, 1.0)))
    await harness.advance(0.5)

    with pytest.raises(ValueError, match="max_speed"):
        await harness.port.set_max_speed(max_speed)
    task.cancel()
    await harness.advance(0)
