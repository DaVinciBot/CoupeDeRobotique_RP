"""The navigator on the fake motor board and the fake clock (TODO 5.4, ADR 0014).

The fake board starts at START_POSE of conftest.py, on the empty table of the template edition.
"""

import asyncio
import math
from collections.abc import Coroutine
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import pytest
from shapely import LineString, Point, Polygon, box

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.adapters.fake.motion import FakeMotion
from dvb_brain.domain.arena import Arena, Side, Zone
from dvb_brain.domain.geometry import Pose, Vec2
from dvb_brain.domain.motion import MotionState, MotionStatus, MoveCommand, MoveKind, StopMode
from dvb_brain.domain.motion_plan import Border
from dvb_brain.domain.navmap import NavigationSettings
from dvb_brain.domain.robot import RobotGeometry
from dvb_brain.domain.strategy_model import Move, MoveMode, Tolerance
from dvb_brain.domain.world import (
    Construction,
    Track,
    TrackSet,
    WorldLifetimes,
    WorldModel,
    WorldSnapshot,
)
from dvb_brain.services.navigator import Navigator, NavResult

pytestmark = pytest.mark.asyncio

GEOMETRY = RobotGeometry(radius=0.15, rear=0.1)
SETTINGS = NavigationSettings(
    margin=0.02,
    turn_penalty=0.1,
    reverse_max_distance=0.3,
    reverse_min_gain=math.radians(45),
    reverse_max_speed=0.2,
)
LIFETIMES = WorldLifetimes(lidar_tracks=0.3, remote=0.3, element_seen=2.0, odometry_history=2.0)
SPEED = 0.5  # m/s, max speed of the steps
DEADLINE = 20.0  # s, far beyond every move of these tests


@dataclass
class FakeRules:
    forbidden: tuple[Polygon, ...] = ()

    def end_zones(self, side: Side) -> tuple[Zone, ...]:
        return ()

    def forbidden_zones(self, side: Side, world: WorldSnapshot) -> tuple[Polygon, ...]:
        return self.forbidden


@pytest.fixture
def world(arena: Arena) -> WorldModel:
    return WorldModel(arena.elements, LIFETIMES, now=0.0)


@pytest.fixture
def rules() -> FakeRules:
    return FakeRules()


@pytest.fixture
def navigator(
    clock: FakeClock, fake_motion: FakeMotion, world: WorldModel, arena: Arena, rules: FakeRules
) -> Navigator:
    return Navigator(fake_motion, clock, world, arena, Side.BLUE, rules, GEOMETRY, SETTINGS)


def target(
    x: float, y: float, theta: float | None = None, mode: MoveMode = MoveMode.FORWARD
) -> Move:
    return Move(Vec2(x, y), theta, SPEED, mode, Tolerance(position=0.02, angle=math.radians(3)))


async def run[T](clock: FakeClock, coroutine: Coroutine[Any, Any, T], dt: float = DEADLINE) -> T:
    """Run coroutine while the clock moves dt seconds on; it must be over by then."""
    task = asyncio.create_task(coroutine)
    await clock.advance(dt)
    return task.result()


def last(motion: FakeMotion) -> MotionStatus:
    status = motion.status().get()
    assert status is not None
    return status


def assert_pose(pose: Pose, x: float, y: float, theta: float) -> None:
    assert (pose.x, pose.y, pose.theta) == pytest.approx((x, y, theta), abs=1e-6)


def lines(start: Pose, moves: list[MoveCommand]) -> list[LineString]:
    points = [(start.x, start.y), *((move.x, move.y) for move in moves)]
    return [LineString([a, b]) for a, b in pairwise(points)]


# go_to


async def test_goes_straight_to_the_target_and_turns_to_its_heading(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    result = await run(clock, navigator.go_to(target(1.25, 0.25, math.pi / 2), DEADLINE))

    assert result is NavResult.ARRIVED
    assert fake_motion.moves == [
        MoveCommand(
            MoveKind.GOTO, x=1.25, y=0.25, theta=math.pi / 2, max_speed=SPEED, has_heading=True
        )
    ]
    assert_pose(last(fake_motion).pose, 1.25, 0.25, math.pi / 2)


async def test_goes_around_an_opponent_of_the_world(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator, world: WorldModel
) -> None:
    start = Pose(0.25, 0.25, 0.0)
    opponent = Track(id=1, center=Vec2(0.75, 0.25), radius=0.1, velocity=Vec2(0, 0), confirmed=True)
    world.update_tracks(TrackSet(stamp=0.0, tracks=(opponent,)))

    result = await run(clock, navigator.go_to(target(1.25, 0.25), DEADLINE))

    assert result is NavResult.ARRIVED
    assert len(fake_motion.moves) >= 2
    for line in lines(start, fake_motion.moves):
        assert line.distance(Point(0.75, 0.25)) >= opponent.radius + GEOMETRY.radius
    end = last(fake_motion).pose
    assert (end.x, end.y) == pytest.approx((1.25, 0.25))


async def test_goes_around_a_forbidden_zone_of_the_rules(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator, rules: FakeRules
) -> None:
    zone = box(0.6, 0.0, 0.9, 0.6)
    rules.forbidden = (zone,)

    result = await run(clock, navigator.go_to(target(1.25, 0.25), DEADLINE))

    assert result is NavResult.ARRIVED
    for line in lines(Pose(0.25, 0.25, 0.0), fake_motion.moves):
        assert line.distance(zone) >= GEOMETRY.radius


async def test_plans_around_a_construction_added_after_its_start(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator, world: WorldModel
) -> None:
    wall = box(0.6, 0.0, 0.9, 0.6)
    world.add_construction(Construction("wall", wall), stamp=0.0)

    result = await run(clock, navigator.go_to(target(1.25, 0.25), DEADLINE))

    assert result is NavResult.ARRIVED
    for line in lines(Pose(0.25, 0.25, 0.0), fake_motion.moves):
        assert line.distance(wall) >= GEOMETRY.radius


async def test_a_target_in_an_opponent_has_no_path_and_nothing_moves(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator, world: WorldModel
) -> None:
    opponent = Track(id=1, center=Vec2(1.25, 0.25), radius=0.1, velocity=Vec2(0, 0), confirmed=True)
    world.update_tracks(TrackSet(stamp=0.0, tracks=(opponent,)))

    result = await run(clock, navigator.go_to(target(1.25, 0.25), DEADLINE))

    assert result is NavResult.NO_PATH
    assert fake_motion.moves == []


async def test_times_out_at_the_deadline_and_stops_the_robot(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    result = await run(clock, navigator.go_to(target(2.5, 0.25), deadline=1.0), dt=1.0)

    assert result is NavResult.TIMEOUT
    assert fake_motion.stops == [(1.0, StopMode.SMOOTH)]
    await clock.advance(1.0)
    assert last(fake_motion).state is MotionState.STOPPED


async def test_a_deadline_already_over_sends_nothing(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    await clock.advance(1.0)

    result = await run(clock, navigator.go_to(target(1.25, 0.25), deadline=clock.now()))

    assert result is NavResult.TIMEOUT
    assert fake_motion.moves == []


async def test_a_blocked_move_is_a_motion_fault(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    fake_motion.block_after(0.2)

    result = await run(clock, navigator.go_to(target(1.25, 0.25), DEADLINE))

    assert result is NavResult.MOTION_FAULT
    assert len(fake_motion.moves) == 1


async def test_a_missed_arrival_is_corrected_towards_the_absolute_target(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    fake_motion.miss_next_gotos(1, Vec2(0.03, 0.0))

    result = await run(clock, navigator.go_to(target(1.25, 0.25, math.pi / 2), DEADLINE))

    assert result is NavResult.ARRIVED
    assert [(move.x, move.y) for move in fake_motion.moves] == [(1.25, 0.25), (1.25, 0.25)]
    assert_pose(last(fake_motion).pose, 1.25, 0.25, math.pi / 2)


async def test_a_second_miss_is_a_motion_fault_after_one_correction_only(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    fake_motion.miss_next_gotos(3, Vec2(0.03, 0.0))

    result = await run(clock, navigator.go_to(target(1.25, 0.25), DEADLINE))

    assert result is NavResult.MOTION_FAULT
    assert len(fake_motion.moves) == 2


async def test_a_robot_already_there_does_not_move(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    result = await run(clock, navigator.go_to(target(0.26, 0.25, 0.01), DEADLINE))

    assert result is NavResult.ARRIVED
    assert fake_motion.moves == []


async def test_only_the_heading_is_corrected_on_the_spot(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    result = await run(clock, navigator.go_to(target(0.26, 0.25, math.pi / 2), DEADLINE))

    assert result is NavResult.ARRIVED
    assert fake_motion.moves == [MoveCommand(MoveKind.ROTATE_TO, theta=math.pi / 2)]


async def test_reverse_backs_up_the_end_of_a_long_line_only(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    result = await run(clock, navigator.go_to(target(1.25, 0.25, mode=MoveMode.REVERSE), DEADLINE))

    assert result is NavResult.ARRIVED
    forward, backward = fake_motion.moves
    assert (forward.x, forward.y, forward.reverse) == pytest.approx((0.95, 0.25, False))
    assert (backward.x, backward.y, backward.reverse) == (1.25, 0.25, True)
    assert backward.max_speed == SETTINGS.reverse_max_speed
    assert_pose(last(fake_motion).pose, 1.25, 0.25, math.pi)


async def test_a_cancelled_go_to_lets_the_next_one_start_once_the_robot_is_still(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    # The end of the match cancels the step, then sends the robot home at once (TODO 7.4).
    step = asyncio.create_task(navigator.go_to(target(2.5, 0.25), DEADLINE))
    await clock.advance(1.0)
    step.cancel()
    await clock.advance(0)
    assert step.cancelled()

    result = await run(clock, navigator.go_to(target(0.5, 1.0), DEADLINE))

    assert result is NavResult.ARRIVED
    assert fake_motion.stops == [(1.0, StopMode.SMOOTH)]
    assert (last(fake_motion).pose.x, last(fake_motion).pose.y) == pytest.approx((0.5, 1.0))


async def test_a_go_to_after_a_cancelled_one_reads_the_pose_once_the_robot_is_still(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    # Cancelled at 1 s, at 0.5 m/s and x = 0.625 m: the robot brakes to x = 0.75 m (1 m/s²).
    step = asyncio.create_task(navigator.go_to(target(2.5, 0.25), DEADLINE))
    await clock.advance(1.0)
    step.cancel()

    result = await run(clock, navigator.go_to(target(0.75, 0.25), DEADLINE))

    assert result is NavResult.ARRIVED
    assert len(fake_motion.moves) == 1  # already there once still: no second move


# Push and recalibration


async def test_push_until_blocked_ends_on_contact_slowly_when_backwards(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    fake_motion.block_after(0.05)

    status = await run(clock, navigator.push_until_blocked(-0.2, DEADLINE))

    assert status is not None
    assert status.state is MotionState.BLOCKED
    assert fake_motion.moves == [
        MoveCommand(MoveKind.PUSH_UNTIL_BLOCKED, distance=-0.2, max_speed=0.2)
    ]


async def test_push_until_blocked_ends_arrived_without_contact(
    clock: FakeClock, navigator: Navigator
) -> None:
    status = await run(clock, navigator.push_until_blocked(0.1, DEADLINE))

    assert status is not None
    assert status.state is MotionState.ARRIVED


@pytest.mark.parametrize("distance", [0.0, math.nan, -0.31])
async def test_push_until_blocked_refuses_a_push_the_board_ignores_or_too_long_backwards(
    navigator: Navigator, distance: float
) -> None:
    with pytest.raises(ValueError, match="distance"):
        await navigator.push_until_blocked(distance, DEADLINE)


@pytest.mark.parametrize(
    ("border", "block_after", "expected"),
    [
        # The odometry says x = 0.13 m at contact: the border says x = rear
        (Border.X_MIN, 0.12, Pose(0.1, 0.25, 0.0)),
        # The odometry says y = 0.45 m at contact: the border says y = depth - rear
        (Border.Y_MAX, 0.2, Pose(0.25, 1.9, -math.pi / 2)),
    ],
)
async def test_recalibrate_sets_the_pose_given_by_the_border(
    clock: FakeClock,
    fake_motion: FakeMotion,
    navigator: Navigator,
    border: Border,
    block_after: float,
    expected: Pose,
) -> None:
    fake_motion.block_after(block_after)

    result = await run(clock, navigator.recalibrate(border, 0.3, DEADLINE))

    assert result is NavResult.ARRIVED
    assert_pose(last(fake_motion).pose, expected.x, expected.y, expected.theta)


async def test_recalibrate_without_contact_keeps_the_odometry(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator
) -> None:
    result = await run(clock, navigator.recalibrate(Border.X_MIN, 0.1, DEADLINE))

    assert result is NavResult.MOTION_FAULT
    assert_pose(last(fake_motion).pose, 0.15, 0.25, 0.0)


@pytest.mark.parametrize("max_distance", [-0.1, 0.0, math.nan, 0.31])
async def test_recalibrate_refuses_a_push_that_is_not_backwards_or_too_long(
    clock: FakeClock, fake_motion: FakeMotion, navigator: Navigator, max_distance: float
) -> None:
    with pytest.raises(ValueError, match="max_distance"):
        await run(clock, navigator.recalibrate(Border.X_MIN, max_distance, DEADLINE))
    assert fake_motion.moves == []


@pytest.mark.parametrize("deadline", [math.inf, math.nan])
@pytest.mark.parametrize("call", ["go_to", "push_until_blocked", "recalibrate"])
async def test_a_deadline_that_is_not_finite_is_refused(
    fake_motion: FakeMotion, navigator: Navigator, call: str, deadline: float
) -> None:
    # On the robot, the clock would wait for ever (ADR 0010: no wait without a bound).
    with pytest.raises(ValueError, match="deadline"):
        match call:
            case "go_to":
                await navigator.go_to(target(1.25, 0.25), deadline)
            case "push_until_blocked":
                await navigator.push_until_blocked(-0.1, deadline)
            case _:
                await navigator.recalibrate(Border.X_MIN, 0.1, deadline)
    assert fake_motion.moves == []
