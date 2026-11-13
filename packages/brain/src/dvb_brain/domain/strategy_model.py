"""Model of a cdr.strategy file (architecture, section 9.1), in SI units.

A strategy is written for one side, in mm and degrees; the loader converts it to SI. It is
checked in two passes (ADR 0005): parse_strategy checks what the file says on its own,
check_strategy what needs the table, the actions of the edition and the match duration.
"""

from collections.abc import Collection
from dataclasses import dataclass, replace
from enum import StrEnum, auto
from pathlib import Path
from typing import Literal

import msgspec

from dvb_brain.domain.arena import Arena, Side
from dvb_brain.domain.decoding import (
    Id,
    NonNegative,
    Positive,
    SchemaError,
    check_unique_ids,
    decode_json,
    field_error,
)
from dvb_brain.domain.geometry import Pose, Vec2, normalize_angle
from dvb_brain.domain.symmetry import mirror_element_id, mirror_point, mirror_pose, mirror_side
from dvb_brain.domain.units import deg_to_rad, mm_to_m


class MoveMode(StrEnum):
    """Direction of the straight line of a move (architecture, section 9.4)."""

    AUTO = auto()
    FORWARD = auto()
    REVERSE = auto()


@dataclass(frozen=True, slots=True)
class Tolerance:
    """Distance and angle under which the robot has arrived."""

    position: float  # m
    angle: float  # rad


@dataclass(frozen=True, slots=True)
class Move:
    """Target of the centre of the robot. Without theta, no final rotation."""

    position: Vec2
    theta: float | None
    max_speed: float  # m/s
    mode: MoveMode
    tolerance: Tolerance


@dataclass(frozen=True, slots=True)
class Action:
    type: str  # name of an action of the edition
    duration: float  # s, approximate, counted in the match time
    actuator_id: str | None
    element_id: str | None
    score_delta: int  # expected points, for display only


@dataclass(frozen=True, slots=True)
class Skip:
    """Go on with the next step."""


@dataclass(frozen=True, slots=True)
class Abort:
    """Stop the strategy and go to the end of the match."""


@dataclass(frozen=True, slots=True)
class GoTo:
    """Resume at another step, once per jump."""

    step_id: str


type OnTimeout = Skip | Abort | GoTo


@dataclass(frozen=True, slots=True)
class Step:
    id: str
    label: str
    move: Move
    actions: tuple[Action, ...]
    not_before: float | None  # s, match time to wait for before the actions
    timeout: float | None  # s, for the move, the wait and the actions; None: no limit
    on_timeout: OnTimeout


@dataclass(frozen=True, slots=True)
class Strategy:
    name: str
    arena_id: str
    side: Side
    end_reserve: float  # s, added to the estimated return time at the end of the match
    steps: tuple[Step, ...]


def parse_strategy(data: bytes) -> Strategy:
    """Decode the content of a cdr.strategy file and convert it to SI.

    Check the step ids and the targets of goto. Raise a SchemaError that names the field and
    the value.
    """
    raw = decode_json(data, _StrategyFile)
    check_unique_ids("steps", (step.id for step in raw.steps))
    step_ids = {step.id for step in raw.steps}
    steps = tuple(_to_step(f"$.steps[{i}]", step) for i, step in enumerate(raw.steps))
    for i, step in enumerate(steps):
        match step.on_timeout:
            case GoTo(step_id=target) if target not in step_ids:
                raise field_error(
                    f"$.steps[{i}].on_timeout", "no such step", raw.steps[i].on_timeout
                )
            case _:
                pass
    return Strategy(
        name=raw.name,
        arena_id=raw.arena_id,
        side=raw.side,
        end_reserve=raw.end_reserve_s,
        steps=steps,
    )


def load_strategy(path: Path) -> Strategy:
    """Read a cdr.strategy file. At startup only: this blocks on the disk."""
    try:
        return parse_strategy(path.read_bytes())
    except SchemaError as error:
        raise SchemaError(f"{path}: {error}") from error


def check_strategy(
    strategy: Strategy,
    *,
    arena: Arena,
    arena_id: str,
    action_types: Collection[str],
    match_duration: float,
) -> None:
    """Check a strategy against the table, the action types of the edition and the match.

    Raise a SchemaError that names the field of the file and the value. The value is the one
    of the strategy, in SI: a check on a length or an angle must convert it back for the message.
    """
    if strategy.arena_id != arena_id:
        raise field_error("$.arena_id", f"expected {arena_id!r}", strategy.arena_id)
    for i, step in enumerate(strategy.steps):
        if step.not_before is not None and step.not_before > match_duration:
            reason = f"after the end of the match at {match_duration:g} s"
            raise field_error(f"$.steps[{i}].not_before_s", reason, step.not_before)
        for j, action in enumerate(step.actions):
            path = f"$.steps[{i}].actions[{j}]"
            if action.type not in action_types:
                raise field_error(f"{path}.type", "unknown action type", action.type)
            if action.element_id is not None and action.element_id not in arena.elements:
                raise field_error(f"{path}.element_id", "unknown element", action.element_id)


def mirror_strategy(strategy: Strategy, arena: Arena) -> Strategy:
    """Return the same strategy for the other side (architecture, section 9.5).

    Check the strategy first: each element_id must be known by the arena.
    """
    steps = tuple(
        replace(
            step,
            move=_mirror_move(step.move, arena.width),
            actions=tuple(_mirror_action(action, arena) for action in step.actions),
        )
        for step in strategy.steps
    )
    return replace(strategy, side=mirror_side(strategy.side), steps=steps)


def _mirror_move(move: Move, table_width: float) -> Move:
    if move.theta is None:
        return replace(move, position=mirror_point(move.position, table_width))
    pose = mirror_pose(Pose(move.position.x, move.position.y, move.theta), table_width)
    return replace(move, position=pose.position, theta=pose.theta)


def _mirror_action(action: Action, arena: Arena) -> Action:
    if action.element_id is None:
        return action
    return replace(action, element_id=mirror_element_id(arena, action.element_id))


# Schema of a cdr.strategy file: lengths in mm, angles in degrees, times in s, speeds in m/s.


class _UnitsFile(msgspec.Struct, forbid_unknown_fields=True):
    """Units of the file: the only ones the loader converts."""

    length: Literal["mm"]
    angle: Literal["deg"]
    time: Literal["s"]
    speed: Literal["m/s"]


class _ToleranceFile(msgspec.Struct, forbid_unknown_fields=True):
    position_mm: Positive = 20.0
    angle_deg: Positive = 3.0


class _MoveFile(msgspec.Struct, forbid_unknown_fields=True):
    x_mm: float
    y_mm: float
    speed_mps: Positive
    theta_deg: float | None = None
    mode: MoveMode = MoveMode.FORWARD
    tolerance: _ToleranceFile = msgspec.field(default_factory=_ToleranceFile)


class _ActionFile(msgspec.Struct, forbid_unknown_fields=True):
    type: Id
    duration_s: NonNegative
    actuator_id: Id | None = None
    element_id: Id | None = None
    score_delta: int = 0


class _StepFile(msgspec.Struct, forbid_unknown_fields=True):
    id: Id
    label: str
    move: _MoveFile
    actions: list[_ActionFile]
    timeout_s: NonNegative  # 0: no limit
    on_timeout: str  # skip, abort or goto:<step id>
    not_before_s: NonNegative | None = None


class _MetadataFile(msgspec.Struct, forbid_unknown_fields=True):
    """Filled by the strategy editor, never used to decide."""

    estimated_time_s: NonNegative = 0.0
    estimated_score: int = 0
    saved_at: str = ""


class _StrategyFile(msgspec.Struct, forbid_unknown_fields=True):
    schema_version: Literal[1]
    kind: Literal["cdr.strategy"]
    name: Id
    arena_id: Id
    side: Side
    units: _UnitsFile
    end_reserve_s: NonNegative
    steps: list[_StepFile]
    metadata: _MetadataFile = msgspec.field(default_factory=_MetadataFile)


def _to_step(path: str, raw: _StepFile) -> Step:
    return Step(
        id=raw.id,
        label=raw.label,
        move=_to_move(raw.move),
        actions=tuple(_to_action(action) for action in raw.actions),
        not_before=raw.not_before_s,
        timeout=raw.timeout_s or None,
        on_timeout=_parse_on_timeout(f"{path}.on_timeout", raw.on_timeout),
    )


def _to_move(raw: _MoveFile) -> Move:
    theta = None if raw.theta_deg is None else normalize_angle(deg_to_rad(raw.theta_deg))
    return Move(
        position=Vec2(mm_to_m(raw.x_mm), mm_to_m(raw.y_mm)),
        theta=theta,
        max_speed=raw.speed_mps,
        mode=raw.mode,
        tolerance=Tolerance(
            mm_to_m(raw.tolerance.position_mm), deg_to_rad(raw.tolerance.angle_deg)
        ),
    )


def _to_action(raw: _ActionFile) -> Action:
    return Action(
        type=raw.type,
        duration=raw.duration_s,
        actuator_id=raw.actuator_id,
        element_id=raw.element_id,
        score_delta=raw.score_delta,
    )


def _parse_on_timeout(path: str, text: str) -> OnTimeout:
    match text.partition(":"):
        case ("skip", "", ""):
            return Skip()
        case ("abort", "", ""):
            return Abort()
        case ("goto", ":", step_id) if step_id:
            return GoTo(step_id)
        case _:
            raise field_error(path, "expected skip, abort or goto:<step id>", text)
