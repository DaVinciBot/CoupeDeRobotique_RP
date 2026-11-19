"""Guards of the game rules: allowed actions, forbidden zones, end zones (TODO 2.7, 7.2)."""

from dataclasses import dataclass

from dvb_brain.domain.arena import Arena, Side, Zone, ZoneKind


@dataclass(frozen=True, slots=True)
class Rules:
    """Rules of the edition. Cite the article of the rules for each answer."""

    arena: Arena

    def end_zones(self, side: Side) -> tuple[Zone, ...]:
        # Rule of the year: where the robot must be at the end of the match.
        return self.arena.zones_of(ZoneKind.END, side)
