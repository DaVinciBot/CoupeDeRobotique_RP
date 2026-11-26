"""Path to moves: the motor board moves that run a path of the planner (TODO 5.3, ADR 0014).

Each point after the start becomes a GOTO, absolute: the avoidance can send it again with another
max speed (ADR 0010), and a new plan starts again from the absolute target. Backwards, the lidar
sees nothing (270 degrees, architecture 8.4): no GOTO backs up over more than
reverse_max_distance, nor faster than reverse_max_speed, whatever the mode.
"""

import math
from collections.abc import Sequence
from enum import StrEnum, auto
from itertools import pairwise

from dvb_brain.domain.geometry import Pose, Vec2, angle_diff
from dvb_brain.domain.motion import MoveCommand, MoveKind
from dvb_brain.domain.navmap import NavigationSettings
from dvb_brain.domain.planner import Path
from dvb_brain.domain.strategy_model import Move, MoveMode


def moves_along(
    path: Path,
    heading: float,
    mode: MoveMode,
    theta: float | None,
    max_speed: float,
    settings: NavigationSettings,
) -> tuple[MoveCommand, ...]:
    """Return the moves that run path, for a robot at its first point with this heading.

    theta is the final heading, if any; max_speed the max speed of the step (architecture 9.4).
    """
    if not (math.isfinite(max_speed) and max_speed > 0.0):
        # 0 would mean "the board limit", full speed; the board ignores a non-finite one (ADR 0003)
        raise ValueError(f"max_speed must be finite and > 0, got {max_speed}")
    points = path.points
    if len(points) == 1:
        return () if theta is None else (MoveCommand(MoveKind.ROTATE_TO, theta=theta),)
    match mode:
        case MoveMode.FORWARD:
            backwards = [False] * (len(points) - 1)
        case MoveMode.REVERSE:
            points = _cut_last_line(points, settings.reverse_max_distance)
            backwards = [False] * (len(points) - 2) + [True]
        case MoveMode.AUTO:
            backwards = _auto(points, heading, theta, settings)
    reverse_speed = min(max_speed, settings.reverse_max_speed)
    last = len(points) - 1
    return tuple(
        MoveCommand(
            MoveKind.GOTO,
            x=point.x,
            y=point.y,
            theta=theta if i == last and theta is not None else 0.0,
            max_speed=reverse_speed if backwards_line else max_speed,
            reverse=backwards_line,
            has_heading=i == last and theta is not None,
        )
        for i, (point, backwards_line) in enumerate(zip(points[1:], backwards, strict=True), 1)
    )


def _cut_last_line(points: Sequence[Vec2], max_distance: float) -> tuple[Vec2, ...]:
    """Cut the last line where max_distance of it is left: forwards there, then backwards."""
    a, b = points[-2], points[-1]
    length = (b - a).norm()
    if length <= max_distance:
        return tuple(points)
    return (*points[:-1], b + (a - b) * (max_distance / length), b)


def _auto(
    points: Sequence[Vec2], heading: float, theta: float | None, settings: NavigationSettings
) -> list[bool]:
    """Choose the direction of each line: backwards if short and saving enough rotation.

    A line is compared with the turn before it and the turn after it, towards the next line,
    taken forwards, or towards theta after the last one (ADR 0014).
    """
    directions = [(b - a).angle() for a, b in pairwise(points)]
    lengths = [(b - a).norm() for a, b in pairwise(points)]
    backwards: list[bool] = []
    for i, (direction, length) in enumerate(zip(directions, lengths, strict=True)):
        then = directions[i + 1] if i + 1 < len(directions) else theta
        saved = _turns(heading, direction, then) - _turns(heading, direction + math.pi, then)
        backwards_line = (
            length <= settings.reverse_max_distance and saved > settings.reverse_min_gain
        )
        backwards.append(backwards_line)
        heading = direction + math.pi if backwards_line else direction
    return backwards


def _turns(heading: float, facing: float, then: float | None) -> float:
    """Return the rotation to face this way before a line, plus the one towards then after it."""
    after = 0.0 if then is None else abs(angle_diff(then, facing))
    return abs(angle_diff(facing, heading)) + after


def position_reached(pose: Pose, target: Move) -> bool:
    return (pose.position - target.position).norm() <= target.tolerance.position


def reached(pose: Pose, target: Move) -> bool:
    """Tell whether the robot has arrived: position and heading in their tolerance (9.3)."""
    if not position_reached(pose, target):
        return False
    return (
        target.theta is None or abs(angle_diff(pose.theta, target.theta)) <= target.tolerance.angle
    )


class Border(StrEnum):
    """A border of the playing area (ADR 0002)."""

    X_MIN = auto()  # x = 0
    X_MAX = auto()  # x = width
    Y_MIN = auto()  # y = 0, on the side of the public
    Y_MAX = auto()  # y = depth


def border_heading(border: Border) -> float:
    """Return the heading that shows the rear of the robot to border."""
    match border:
        case Border.X_MIN:
            return 0.0
        case Border.X_MAX:
            return math.pi
        case Border.Y_MIN:
            return math.pi / 2
        case Border.Y_MAX:
            return -math.pi / 2


def calibrated_pose(border: Border, pose: Pose, width: float, depth: float, rear: float) -> Pose:
    """Return the pose of the robot pushed with its rear against border (architecture 7.2).

    The border gives one coordinate and the heading; the odometry pose keeps the other one. rear
    is the distance from the centre of the robot to its rear face.
    """
    heading = border_heading(border)
    match border:
        case Border.X_MIN:
            return Pose(rear, pose.y, heading)
        case Border.X_MAX:
            return Pose(width - rear, pose.y, heading)
        case Border.Y_MIN:
            return Pose(pose.x, rear, heading)
        case Border.Y_MAX:
            return Pose(pose.x, depth - rear, heading)
