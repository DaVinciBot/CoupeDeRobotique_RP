import itertools
from functools import reduce

import pytest

from dvb_brain.domain.match_fsm import Fault, MatchEvent, MatchState, Refused, transition

S = MatchState
E = MatchEvent
FAULT = Fault("motor board silent")
FINAL = {S.FINISHED, S.FAULT}

# Architecture, section 11.1, and ADR 0007. A Fault leads to FAULT from every state that is not
# final. Every other (state, event) pair is refused.
ALLOWED = {
    (S.IDLE, E.LAUNCH): S.INIT,
    (S.INIT, E.CHECKS_OK): S.READY,
    (S.READY, E.CALIBRATE): S.CALIBRATING,
    (S.CALIBRATING, E.CALIBRATE): S.CALIBRATING,
    (S.CALIBRATING, E.ARM): S.ARMED,
    (S.ARMED, E.DISARM): S.READY,
    (S.ARMED, E.CORD_PULLED): S.RUNNING,
    (S.RUNNING, E.END_BUDGET): S.ENDING,
    (S.RUNNING, E.T_END): S.FINISHED,
    (S.ENDING, E.T_END): S.FINISHED,
}


def expected(state: MatchState, event: MatchEvent | Fault) -> MatchState | None:
    """The next state, or None when the event is refused."""
    if state in FINAL:
        return None
    if isinstance(event, Fault):
        return S.FAULT
    return ALLOWED.get((state, event))


@pytest.mark.parametrize(("state", "event"), list(itertools.product(S, [*E, FAULT])), ids=str)
def test_each_pair_has_its_expected_result(state: MatchState, event: MatchEvent | Fault) -> None:
    result = transition(state, event)

    if (next_state := expected(state, event)) is not None:
        assert result is next_state
    else:
        assert isinstance(result, Refused)


def test_the_cord_starts_the_match_only_when_armed() -> None:
    # RG F.6: start by the cord only; RG H.4: a false start costs points.
    started_from = [state for state in S if transition(state, E.CORD_PULLED) is S.RUNNING]

    assert started_from == [S.ARMED]


def test_armed_only_accepts_disarm_the_cord_and_a_fault() -> None:
    accepted = [e for e in [*E, FAULT] if not isinstance(transition(S.ARMED, e), Refused)]

    assert accepted == [E.DISARM, E.CORD_PULLED, FAULT]


@pytest.mark.parametrize("state", sorted(FINAL), ids=str)
def test_nothing_leaves_a_final_state(state: MatchState) -> None:
    # A new match, or a restart after a fault, is a new launch of the brain (ADR 0007). After
    # the end of the match, nothing is commanded any more (RG H.3), even on a fault.
    assert all(isinstance(transition(state, event), Refused) for event in [*E, FAULT])


@pytest.mark.parametrize("state", [S.RUNNING, S.ENDING], ids=str)
def test_the_end_of_the_match_stops_a_running_match(state: MatchState) -> None:
    # RG H.3: everything stops at the end, even without END_BUDGET from the strategy.
    assert transition(state, E.T_END) is S.FINISHED


def test_a_failed_calibration_can_be_started_again() -> None:
    assert transition(S.CALIBRATING, E.CALIBRATE) is S.CALIBRATING


def test_states_and_events_are_stable_strings_in_logs() -> None:
    assert [state.value for state in S] == [state.name.lower() for state in S]
    assert [event.value for event in E] == [event.name.lower() for event in E]


def test_a_whole_match() -> None:
    events = [E.LAUNCH, E.CHECKS_OK, E.CALIBRATE, E.ARM, E.CORD_PULLED, E.END_BUDGET, E.T_END]

    def step(state: MatchState, event: MatchEvent) -> MatchState:
        result = transition(state, event)
        assert isinstance(result, MatchState), result
        return result

    assert reduce(step, events, S.IDLE) is S.FINISHED
