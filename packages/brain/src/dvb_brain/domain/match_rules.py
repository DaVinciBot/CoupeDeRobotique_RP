"""Game rules of an edition, as the core asks about them (architecture, section 0).

Each edition implements MatchRules in its rules.py, citing the rule of each answer. The
interface grows with the core (ADR 0006): is_action_allowed and forbidden_zones come with the
world model (TODO 4, 7.2).
"""

from typing import Protocol

from dvb_brain.domain.arena import Side, Zone


class MatchRules(Protocol):
    def end_zones(self, side: Side) -> tuple[Zone, ...]:
        """Return the zones where the robot of side ends the match."""
        ...
