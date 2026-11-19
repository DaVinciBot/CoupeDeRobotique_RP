from types import MappingProxyType

import pytest

from dvb_brain.domain.match_clock import MatchClock

# Started at the cord pull, 1000 s on the monotonic clock. The phase is an id of the edition.
CLOCK = MatchClock(t0=1000.0, duration=100.0, phase_starts=MappingProxyType({"late": 85.0}))


def test_elapsed_counts_from_the_start() -> None:
    assert CLOCK.elapsed(1000.0) == 0.0
    assert CLOCK.elapsed(1042.5) == 42.5


def test_remaining_counts_down_to_zero_and_stays_there() -> None:
    assert CLOCK.remaining(1000.0) == 100.0
    assert CLOCK.remaining(1090.0) == 10.0
    assert CLOCK.remaining(1100.0) == 0.0
    assert CLOCK.remaining(1250.0) == 0.0


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (1084.999, False),
        (1085.0, True),  # the phase starts at its start time
        (1099.999, True),
        (1100.0, False),  # and lasts until the end of the match
    ],
)
def test_in_phase_from_its_start_to_the_end_of_the_match(now: float, expected: bool) -> None:
    assert CLOCK.in_phase("late", now) is expected


def test_in_phase_refuses_an_unknown_phase() -> None:
    with pytest.raises(KeyError, match="early"):
        CLOCK.in_phase("early", 1050.0)
