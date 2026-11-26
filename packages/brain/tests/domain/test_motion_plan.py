import math
from itertools import pairwise

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from dvb_brain.domain.geometry import Pose, Vec2
from dvb_brain.domain.motion import MoveCommand, MoveKind
from dvb_brain.domain.motion_plan import (
    Border,
    border_heading,
    calibrated_pose,
    moves_along,
    position_reached,
    reached,
)
from dvb_brain.domain.navmap import NavigationSettings
from dvb_brain.domain.planner import Path
from dvb_brain.domain.strategy_model import Move, MoveMode, Tolerance

SETTINGS = NavigationSettings(
    margin=0.02,
    turn_penalty=0.1,
    reverse_max_distance=0.3,
    reverse_min_gain=math.radians(45),
    reverse_max_speed=0.2,
)
SPEED = 0.5  # m/s, max speed of the step


def path(*points: tuple[float, float]) -> Path:
    return Path(tuple(Vec2(x, y) for x, y in points))


def goto(
    x: float, y: float, *, speed: float = SPEED, reverse: bool = False, theta: float | None = None
) -> MoveCommand:
    return MoveCommand(
        MoveKind.GOTO,
        x=x,
        y=y,
        theta=0.0 if theta is None else theta,
        max_speed=speed,
        reverse=reverse,
        has_heading=theta is not None,
    )


def plan(
    route: Path,
    mode: MoveMode,
    *,
    heading: float = 0.0,
    theta: float | None = None,
    speed: float = SPEED,
) -> tuple[MoveCommand, ...]:
    return moves_along(route, heading, mode, theta, speed, SETTINGS)


# Forward and reverse


def test_forward_gives_one_goto_per_point_and_the_heading_at_the_last() -> None:
    moves = plan(path((0, 0), (1, 0), (1, 1)), MoveMode.FORWARD, theta=math.pi / 2)

    assert moves == (goto(1, 0), goto(1, 1, theta=math.pi / 2))


def test_forward_without_heading_ends_without_a_rotation() -> None:
    moves = plan(path((0, 0), (1, 0), (1, 1)), MoveMode.FORWARD)

    assert moves == (goto(1, 0), goto(1, 1))


def test_reverse_backs_up_the_last_line_only_and_slowly() -> None:
    moves = plan(path((0, 0), (1, 0), (1, 0.2)), MoveMode.REVERSE, theta=0.0)

    assert moves == (goto(1, 0), goto(1, 0.2, speed=0.2, reverse=True, theta=0.0))


def test_reverse_cuts_a_long_last_line_and_backs_up_its_end_only() -> None:
    moves = plan(path((0, 0), (1, 0)), MoveMode.REVERSE)

    assert len(moves) == 2
    forward, backward = moves
    assert (forward.x, forward.y) == pytest.approx((0.7, 0.0))
    assert not forward.reverse
    assert forward.max_speed == SPEED
    assert backward == goto(1, 0, speed=0.2, reverse=True)


def test_reverse_keeps_a_step_speed_below_the_reverse_limit() -> None:
    moves = plan(path((0, 0), (0.2, 0)), MoveMode.REVERSE, speed=0.1)

    assert moves == (goto(0.2, 0, speed=0.1, reverse=True),)


@pytest.mark.parametrize("speed", [0.0, -0.1, math.nan, math.inf])
def test_a_max_speed_that_is_not_finite_and_positive_is_refused(speed: float) -> None:
    # 0 would mean "the board limit": full speed (ADR 0003); a non-finite one is ignored.
    with pytest.raises(ValueError, match="max_speed"):
        plan(path((0, 0), (1, 0)), MoveMode.FORWARD, speed=speed)


# Auto


@pytest.mark.parametrize(
    ("goal", "backwards"),
    [
        ((0.2, 0.0), True),  # short, right behind: backs up instead of a half turn
        ((1.0, 0.0), False),  # behind but far: the lidar sees nothing backwards
    ],
)
def test_auto_backs_up_only_a_short_line_behind(goal: tuple[float, float], backwards: bool) -> None:
    (move,) = plan(path((0, 0), goal), MoveMode.AUTO, heading=math.pi)

    assert move.reverse is backwards
    assert move.max_speed == (0.2 if backwards else SPEED)


@pytest.mark.parametrize(
    ("heading_deg", "backwards"),
    [
        (108, False),  # saves 108 - 72 = 36 degrees, under the 45 degrees threshold
        (126, True),  # saves 126 - 54 = 72 degrees
    ],
)
def test_auto_backs_up_only_when_it_saves_enough_rotation(
    heading_deg: float, backwards: bool
) -> None:
    (move,) = plan(path((0, 0), (0.2, 0)), MoveMode.AUTO, heading=math.radians(heading_deg))

    assert move.reverse is backwards


def test_auto_counts_the_turn_towards_the_next_line() -> None:
    # Backing up from A to B saves a half turn, but the robot would then face away from the next
    # line, 10 degrees off: 190 - 170 = 20 degrees saved only.
    next_point = (0.2 + math.cos(math.radians(10)), math.sin(math.radians(10)))
    moves = plan(path((0, 0), (0.2, 0), next_point), MoveMode.AUTO, heading=math.pi)

    assert [move.reverse for move in moves] == [False, False]


def test_auto_never_backs_up_more_than_the_limit_in_a_row() -> None:
    # Facing away, two short lines then a final heading rear first: each line alone would back
    # up, both together would go 0.56 m blind.
    route = path((1.0, 1.0), (1.28, 1.0), (1.522, 1.14))
    moves = plan(route, MoveMode.AUTO, heading=math.pi, theta=math.radians(-150))

    assert [move.reverse for move in moves] == [True, False]


@pytest.mark.parametrize(("theta", "backwards"), [(None, False), (math.pi, True)])
def test_auto_counts_the_final_heading(theta: float | None, backwards: bool) -> None:
    # Facing +y, the line to +x needs a quarter turn either way: the final heading decides.
    (move,) = plan(path((0, 0), (0.2, 0)), MoveMode.AUTO, heading=math.pi / 2, theta=theta)

    assert move.reverse is backwards


# A path reduced to its start


def test_a_single_point_with_a_heading_only_rotates() -> None:
    moves = plan(path((1, 1)), MoveMode.FORWARD, theta=1.0)

    assert moves == (MoveCommand(MoveKind.ROTATE_TO, theta=1.0),)


def test_a_single_point_without_heading_gives_no_move() -> None:
    assert plan(path((1, 1)), MoveMode.AUTO) == ()


# Properties of every plan


points = st.tuples(st.floats(0.0, 3.0), st.floats(0.0, 2.0))


@given(
    st.lists(points, min_size=2, max_size=5),
    st.floats(-math.pi, math.pi),
    st.sampled_from(MoveMode),
    st.none() | st.floats(-math.pi, math.pi),
    st.floats(0.05, 2.0),
)
def test_no_plan_backs_up_far_or_fast(
    route: list[tuple[float, float]],
    heading: float,
    mode: MoveMode,
    theta: float | None,
    speed: float,
) -> None:
    assume(all(math.dist(a, b) > 1e-3 for a, b in pairwise(route)))
    moves = moves_along(path(*route), heading, mode, theta, speed, SETTINGS)

    starts = [Vec2(*route[0]), *(Vec2(move.x, move.y) for move in moves)]
    backed = 0.0  # m, backwards in a row
    for start, move in zip(starts, moves, strict=False):
        assert move.kind is MoveKind.GOTO
        assert move.max_speed <= speed
        backed = backed + (Vec2(move.x, move.y) - start).norm() if move.reverse else 0.0
        assert backed <= SETTINGS.reverse_max_distance + 1e-9
        if move.reverse:
            assert move.max_speed <= SETTINGS.reverse_max_speed
    last = moves[-1]
    assert (last.x, last.y) == route[-1]
    assert last.has_heading is (theta is not None)
    assert not any(move.has_heading for move in moves[:-1])


# Arrival


TARGET = Move(
    position=Vec2(1.0, 1.0),
    theta=math.pi,
    max_speed=SPEED,
    mode=MoveMode.FORWARD,
    tolerance=Tolerance(position=0.02, angle=math.radians(3)),
)


@pytest.mark.parametrize(
    ("pose", "expected"),
    [
        (Pose(1.0, 1.0, math.pi), True),
        (Pose(1.019, 1.0, math.pi), True),
        (Pose(1.0, 0.979, math.pi), False),
        (Pose(1.0, 1.0, math.pi - math.radians(2.9)), True),
        (Pose(1.0, 1.0, math.pi - math.radians(3.1)), False),
        (Pose(1.0, 1.0, -math.pi + 0.01), True),  # the same heading, wrapped
    ],
)
def test_reached_checks_the_position_and_the_heading(pose: Pose, expected: bool) -> None:
    assert reached(pose, TARGET) is expected


def test_reached_ignores_the_heading_of_a_move_without_one() -> None:
    target = Move(TARGET.position, None, SPEED, MoveMode.FORWARD, TARGET.tolerance)

    assert reached(Pose(1.0, 1.0, 0.0), target)


def test_position_reached_ignores_the_heading() -> None:
    assert position_reached(Pose(1.01, 1.0, 0.0), TARGET)
    assert not position_reached(Pose(1.03, 1.0, math.pi), TARGET)


# Recalibration against a border


@pytest.mark.parametrize(
    ("border", "expected"),
    [
        (Border.X_MIN, Pose(0.15, 0.5, 0.0)),
        (Border.X_MAX, Pose(2.85, 0.5, math.pi)),
        (Border.Y_MIN, Pose(1.0, 0.15, math.pi / 2)),
        (Border.Y_MAX, Pose(1.0, 1.85, -math.pi / 2)),
    ],
)
def test_calibrated_pose_takes_one_coordinate_and_the_heading_from_the_border(
    border: Border, expected: Pose
) -> None:
    pose = calibrated_pose(border, Pose(1.0, 0.5, 0.1), width=3.0, depth=2.0, rear=0.15)

    assert (pose.x, pose.y, pose.theta) == pytest.approx((expected.x, expected.y, expected.theta))
    assert pose.theta == border_heading(border)
