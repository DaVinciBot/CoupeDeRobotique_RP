"""Moves the brain asks of the motor board, and the status it reports, in SI units.

These types follow the MOVE, STOP and MOTION_STATUS messages of the motor board contract
(ADR 0003); their wire encoding (ids, flag bits, float32) is the business of the Teensy adapter
(TODO 15.1). The board turns each move into a trapezoid (architecture, section 7.1).
"""

from dataclasses import dataclass
from enum import StrEnum, auto

from dvb_brain.domain.geometry import Pose


class MoveKind(StrEnum):
    ROTATE_BY = auto()  # rotation on the spot by theta
    ROTATE_TO = auto()  # rotation on the spot to the heading theta
    STRAIGHT = auto()  # straight line over distance
    GOTO = auto()  # turn to (x, y), straight line, then to the heading theta if has_heading
    PUSH_UNTIL_BLOCKED = auto()  # straight line at a limited voltage until both wheels block


@dataclass(frozen=True, slots=True)
class MoveCommand:
    """One MOVE of the motor board (ADR 0003): the kind tells which fields count.

    PUSH_UNTIL_BLOCKED ends BLOCKED on contact, ARRIVED when it covers distance without contact.
    """

    kind: MoveKind
    x: float = 0.0  # m, target of a GOTO on the table
    y: float = 0.0  # m
    theta: float = 0.0  # rad: angle of ROTATE_BY, heading of ROTATE_TO, final heading of a GOTO
    distance: float = 0.0  # m, STRAIGHT and PUSH_UNTIL_BLOCKED (at most), negative backwards
    max_speed: float = 0.0  # m/s, translations only; 0 or above the board limit: the board limit
    max_accel: float = 0.0  # m/s², the same
    reverse: bool = False  # GOTO backwards: the rear faces the target, then the robot backs up
    has_heading: bool = False  # GOTO ends with a rotation to theta


class MotionState(StrEnum):
    MOVING = auto()
    ARRIVED = auto()
    BLOCKED = auto()
    STOPPED = auto()


class StopMode(StrEnum):
    SMOOTH = auto()  # brakes at the MAX_ACCEL setting, the one of the safety zone; holds there
    URGENT = auto()  # command and integrators to zero at once, motors free; final (MotionPort.stop)


@dataclass(frozen=True, slots=True)
class MotionStatus:
    """MOTION_STATUS, sent by the motor board every 50 ms (ADR 0003)."""

    move_id: int  # last MOVE the board accepted: a refused MOVE leaves it unchanged
    state: MotionState
    pose: Pose  # absolute pose from the odometry, the one RESET_POSE sets
    v: float  # m/s, measured linear speed
    omega: float  # rad/s, measured angular speed
    vbat: float  # V, battery voltage of the compensation (a default value if vbat_missing)
    teensy_time: float  # s, clock of the board when it measured this status
    boot_id: int  # random at start-up: it changes when the board restarts, the pose is then lost
    heartbeat: int  # counter of the last HEARTBEAT received
    configured: bool  # every control setting received: until then, the board ignores MOVE
    emergency_stop: bool  # the emergency stop button cut the power of the drivers
    heartbeat_lost: bool  # no HEARTBEAT for 200 ms: the board stopped and ignores MOVE
    vbat_missing: bool  # battery sensor not wired in the firmware: vbat is a default value
    estop_sensor_missing: bool  # emergency stop sensor not wired: the button is not seen
    trace_running: bool  # a control test (START_TRACE) runs
