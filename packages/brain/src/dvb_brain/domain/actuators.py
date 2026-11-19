"""Results and states of the actuators, by the names of the config (architecture, section 10).

The brain asks "gripper -> closed"; the actuator board answers done, blocked or timeout. Angles,
positions and speeds behind each name are the business of the actuator adapter (ADR 0011).
"""

from dataclasses import dataclass
from enum import StrEnum, auto


class ActuatorResult(StrEnum):
    DONE = auto()  # the named position is reached
    BLOCKED = auto()  # stopped before it: blocked, or released meanwhile
    TIMEOUT = auto()  # not reached within the timeout of the command


@dataclass(frozen=True, slots=True)
class ActuatorState:
    # Last named position reached; None while moving, after a failure, a timeout or a release.
    position_name: str | None
    moving: bool
