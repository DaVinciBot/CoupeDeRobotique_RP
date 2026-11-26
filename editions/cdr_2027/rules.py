"""Guards of the game rules: allowed actions, forbidden zones, end zones (TODO 2.7, 7.2)."""

from dataclasses import dataclass

from shapely import Polygon

from dvb_brain.domain.arena import Arena, Side, Zone, ZoneKind
from dvb_brain.domain.world import WorldSnapshot


@dataclass(frozen=True, slots=True)
class Rules:
    """Rules of the 2027 game (RJ v1.0)."""

    arena: Arena

    def end_zones(self, side: Side) -> tuple[Zone, ...]:
        # RJ E.3, D.3: the robot ends the match in its throne room, its start area.
        return self.arena.zones_of(ZoneKind.END, side)

    def forbidden_zones(self, side: Side, world: WorldSnapshot) -> tuple[Polygon, ...]:
        # RJ E.2.b: while the robot carries the Grail, it must not leave its castle (TODO 7.2).
        return ()
