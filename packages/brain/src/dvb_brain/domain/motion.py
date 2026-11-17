"""Moves the brain asks of the motor board, and the status it reports, in SI units.

The motor board turns each move into a trapezoid (architecture, section 7.1). Its wire format is
the business of the Teensy adapter (ADR 0003); these types stay in SI (ADR 0008, ADR 0010).
Rotations take the limits sent to the board at start-up; translations carry their own, so
that the brain can slow down a move backwards or near the opponent.
"""

from dataclasses import dataclass
from enum import StrEnum, auto

from dvb_brain.domain.geometry import Pose, Vec2


@dataclass(frozen=True, slots=True)
class RotateBy:
    angle: float  # rad, counter-clockwise


@dataclass(frozen=True, slots=True)
class RotateTo:
    heading: float  # rad, on the table


@dataclass(frozen=True, slots=True)
class Straight:
    distance: float  # m, negative backwards
    max_speed: float  # m/s
    max_accel: float  # m/s²


@dataclass(frozen=True, slots=True)
class GoToPoint:
    """Turn to face the target, then go straight to it."""

    target: Vec2  # m, on the table
    max_speed: float  # m/s
    max_accel: float  # m/s²


@dataclass(frozen=True, slots=True)
class PushUntilBlocked:
    """Go straight until the robot is blocked, against a border for instance.

    Ends BLOCKED on contact, STOPPED when max_distance is covered without contact.
    """

    max_distance: float  # m, negative backwards
    max_speed: float  # m/s
    max_accel: float  # m/s²


type MoveCommand = RotateBy | RotateTo | Straight | GoToPoint | PushUntilBlocked


class MotionState(StrEnum):
    MOVING = auto()
    ARRIVED = auto()
    BLOCKED = auto()
    STOPPED = auto()


class StopMode(StrEnum):
    SMOOTH = auto()  # trapezoid deceleration of the stop, the one of the safety zone
    URGENT = auto()  # command and integrators to zero at once; final (MotionPort.stop)


@dataclass(frozen=True, slots=True)
class MotionStatus:
    """Status the motor board sends at a fixed rate."""

    move_id: int  # id of the last move, given by the motion port
    state: MotionState
    pose: Pose  # absolute pose from the odometry, the one RESET_POSE sets
    v: float  # m/s, linear speed
    omega: float  # rad/s, angular speed
    emergency_stop: bool  # the emergency stop button cut the power of the drivers
    teensy_time: float  # s, clock of the board when it measured this status
    boot_id: int  # changes when the board restarts: the pose is then lost
