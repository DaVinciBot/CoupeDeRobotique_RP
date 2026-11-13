import itertools
from functools import reduce

import pytest

from dvb_brain.domain.match_fsm import Fault, MatchEvent, MatchState, Refused, transition

S = MatchState
E = MatchEvent

# Architecture, section 11.1, and ADR 0007. Every other (state, event) pair is refused.
ALLOWED = {
    (S.IDLE, E.LAUNCH): S.INIT,
    (S.INIT, E.CHECKS_OK): S.READY,
    (S.READY, E.CALIBRATE): S.CALIBRATING,
    (S.CALIBRATING, E.ARM): S.ARMED,
    (S.ARMED, E.DISARM): S.READY,
    (S.ARMED, E.CORD_PULLED): S.RUNNING,
    (S.RUNNING, E.END_BUDGET): S.ENDING,
    (S.RUNNING, E.T_END): S.FINISHED,
    (S.ENDING, E.T_END): S.FINISHED,
}


@pytest.mark.parametrize(
    ("state", "event"), list(itertools.product(S, E)), ids=lambda value: value.name
)
def test_each_pair_has_its_expected_result(state: MatchState, event: MatchEvent) -> None:
    result = transition(state, event)

    if (state, event) in ALLOWED:
        assert result is ALLOWED[(state, event)]
    else:
        assert result == Refused(f"{event.name} in {state.name}")


@pytest.mark.parametrize("state", S, ids=lambda state: state.name)
def test_fault_is_reached_from_every_state(state: MatchState) -> None:
    assert transition(state, Fault("motor board silent")) is S.FAULT


def test_the_cord_starts_the_match_only_when_armed() -> None:
    # RG F.6: start by the cord only; RG H.4: a false start costs points.
    started_from = [state for state in S if transition(state, E.CORD_PULLED) is S.RUNNING]

    assert started_from == [S.ARMED]


def test_armed_only_accepts_disarm_and_the_cord() -> None:
    accepted = [event for event in E if not isinstance(transition(S.ARMED, event), Refused)]

    assert accepted == [E.DISARM, E.CORD_PULLED]


@pytest.mark.parametrize("state", [S.FAULT, S.FINISHED], ids=lambda state: state.name)
def test_nothing_leaves_a_final_state(state: MatchState) -> None:
    # A new match, or a restart after a fault, is a new launch of the brain (ADR 0007).
    assert all(isinstance(transition(state, event), Refused) for event in E)


@pytest.mark.parametrize("state", [S.RUNNING, S.ENDING], ids=lambda state: state.name)
def test_the_end_of_the_match_stops_a_running_match(state: MatchState) -> None:
    # RG H.3: everything stops at the end, even without END_BUDGET from the strategy.
    assert transition(state, E.T_END) is S.FINISHED


def test_a_whole_match() -> None:
    events = [E.LAUNCH, E.CHECKS_OK, E.CALIBRATE, E.ARM, E.CORD_PULLED, E.END_BUDGET, E.T_END]

    def step(state: MatchState, event: MatchEvent) -> MatchState:
        result = transition(state, event)
        assert isinstance(result, MatchState), result
        return result

    assert reduce(step, events, S.IDLE) is S.FINISHED
