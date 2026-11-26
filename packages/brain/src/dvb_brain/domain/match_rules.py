"""Game rules of an edition, as the core asks about them (architecture, section 0).

Each edition implements MatchRules in its rules.py, citing the rule of each answer. The
interface grows with the core (ADR 0006): forbidden_zones came with the navigator (ADR 0014),
is_action_allowed comes with TODO 7.2.
"""

from typing import Protocol

from shapely import Polygon

from dvb_brain.domain.arena import Side, Zone
from dvb_brain.domain.world import WorldSnapshot


class MatchRules(Protocol):
    def end_zones(self, side: Side) -> tuple[Zone, ...]:
        """Return the zones where the robot of side ends the match."""
        ...

    def forbidden_zones(self, side: Side, world: WorldSnapshot) -> tuple[Polygon, ...]:
        """Return the areas the robot of side must not enter now, by the state of the match.

        The planner inflates them and keeps out of them, like the opponents (ADR 0013, 0014).
        """
        ...
