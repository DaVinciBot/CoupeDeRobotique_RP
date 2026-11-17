"""Match time, counted from the start cord (RG H.2).

The domain reads no clock (ADR 0008): the caller gives the time of the Clock port.
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatchClock:
    """Created when the start cord is pulled. The MatchManager keeps the only instance."""

    t0: float  # s, time of the Clock port when the cord was pulled
    duration: float  # s, MatchConstants.duration
    phase_starts: Mapping[str, float]  # s from t0, Scoring.phase_starts of the edition

    def elapsed(self, now: float) -> float:
        return now - self.t0

    def remaining(self, now: float) -> float:
        """Return the time left until the end of the match, 0 once it is over."""
        return max(0.0, self.duration - self.elapsed(now))

    def in_phase(self, phase_id: str, now: float) -> bool:
        """Tell whether a phase of the edition is on: from its start to the end of the match.

        Raise KeyError for a phase the edition does not define.
        """
        return self.phase_starts[phase_id] <= self.elapsed(now) < self.duration
