"""State machine of the match (architecture, section 11.1; ADR 0007).

Pure: transition() says where an event leads from a state. The MatchManager (TODO 8.1) checks
the conditions of each event (TODO 8.3), applies the transition and acts. FAULT and FINISHED
are final: a new match, or a restart after a fault, is a new launch of the brain.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Final


class MatchState(Enum):
    IDLE = auto()
    INIT = auto()
    READY = auto()
    CALIBRATING = auto()
    ARMED = auto()
    RUNNING = auto()
    ENDING = auto()
    FINISHED = auto()
    FAULT = auto()


class MatchEvent(Enum):
    LAUNCH = auto()
    CHECKS_OK = auto()
    CALIBRATE = auto()
    ARM = auto()
    DISARM = auto()
    CORD_PULLED = auto()
    END_BUDGET = auto()  # time left to come back to the end zone
    T_END = auto()  # end of the match, whatever the strategy (RG H.3)


@dataclass(frozen=True, slots=True)
class Fault:
    """Serious failure: stop, default posture, manual restart (architecture, section 11)."""

    reason: str


@dataclass(frozen=True, slots=True)
class Refused:
    """The event changes nothing in this state."""

    reason: str


_TRANSITIONS: Final[Mapping[tuple[MatchState, MatchEvent], MatchState]] = {
    (MatchState.IDLE, MatchEvent.LAUNCH): MatchState.INIT,
    (MatchState.INIT, MatchEvent.CHECKS_OK): MatchState.READY,
    (MatchState.READY, MatchEvent.CALIBRATE): MatchState.CALIBRATING,
    (MatchState.CALIBRATING, MatchEvent.ARM): MatchState.ARMED,
    # From ARMED, only these two: the start cord is read only here (RG F.6, false start RG H.4).
    (MatchState.ARMED, MatchEvent.DISARM): MatchState.READY,
    (MatchState.ARMED, MatchEvent.CORD_PULLED): MatchState.RUNNING,
    (MatchState.RUNNING, MatchEvent.END_BUDGET): MatchState.ENDING,
    (MatchState.RUNNING, MatchEvent.T_END): MatchState.FINISHED,
    (MatchState.ENDING, MatchEvent.T_END): MatchState.FINISHED,
}


def transition(state: MatchState, event: MatchEvent | Fault) -> MatchState | Refused:
    """Return the next state, or Refused when the event does nothing in this state."""
    match event:
        case Fault():
            return MatchState.FAULT
        case MatchEvent():
            next_state = _TRANSITIONS.get((state, event))
            if next_state is None:
                return Refused(f"{event.name} in {state.name}")
            return next_state
