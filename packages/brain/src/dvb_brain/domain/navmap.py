"""Navigation map: the free space of the robot centre on the table (architecture 8.1, ADR 0013).

Each obstacle is inflated by the clearance, the robot radius plus a margin: the robot becomes a
point, and the free space is what is left of the table. The inflated shapes are polygons that
cover the true inflated shapes, with few vertices: these are the nodes of the planner (5.2).
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

import shapely
from shapely import MultiPolygon, Point, Polygon, box, unary_union
from shapely.geometry.base import BaseGeometry

from dvb_brain.domain.arena import Arena, Side, ZoneKind
from dvb_brain.domain.geometry import Vec2
from dvb_brain.domain.symmetry import mirror_side
from dvb_brain.domain.world import Track, WorldSnapshot

# A disc becomes the regular polygon with 4 * DISC_QUAD_SEGS sides circumscribed to it.
DISC_QUAD_SEGS = 2


@dataclass(frozen=True, slots=True)
class NavigationSettings:
    """Settings of the navigation, in SI (config/robot.json)."""

    margin: float  # m, kept between the robot and any obstacle, on top of its radius
    turn_penalty: float  # m, added to the length of a path for each stop to turn
    # Backwards, the lidar sees nothing (270 degrees): short and slow only (ADR 0014)
    reverse_max_distance: float  # m, longest straight line backwards
    reverse_min_gain: float  # rad, rotation that auto must save to go backwards
    reverse_max_speed: float  # m/s


def inflate(shape: BaseGeometry, distance: float) -> BaseGeometry:
    """Grow a polygon by distance, never less.

    The sides move out by distance exactly; each corner is cut by a line tangent to its arc
    (a mitre limited to distance), so that a corner gives two vertices instead of an arc.
    """
    return shape.buffer(distance, join_style="mitre", mitre_limit=1.0)


def disc(center: Vec2, radius: float) -> Polygon:
    """Return the regular polygon circumscribed to a disc: it covers the whole disc."""
    circumradius = radius / math.cos(math.pi / (4 * DISC_QUAD_SEGS))
    return Point(center.x, center.y).buffer(circumradius, quad_segs=DISC_QUAD_SEGS)


def static_obstacles(arena: Arena, side: Side, world: WorldSnapshot) -> tuple[Polygon, ...]:
    """Return what the robot of side must keep clear of, apart from the opponents.

    The zones forbidden to side, the exclusive areas of the opponent (forfeit, RG H.4), the
    obstacle zones of both sides, the elements still in place by our own state (ADR 0013) and
    our constructions.
    """
    zones = [
        *arena.zones_of(ZoneKind.FORBIDDEN, side),
        *arena.zones_of(ZoneKind.EXCLUSIVE_OPPONENT, mirror_side(side)),
        *(zone for zone in arena.zones.values() if ZoneKind.OBSTACLE in zone.kinds),
    ]
    elements = [arena.elements[element_id].footprint() for element_id in elements_in_place(world)]
    constructions = [c.value.footprint for c in world.our_constructions.values()]
    return (*(zone.polygon for zone in zones), *elements, *constructions)


def elements_in_place(world: WorldSnapshot) -> tuple[str, ...]:
    """Return the ids of the elements still at their place by our own state, in table order.

    Our own state changes only by our actions (ADR 0013): a view of the remote vision that goes
    stale does not change the static obstacles. An element the opponent took stays an obstacle.
    """
    return tuple(i for i, element in world.our_elements.items() if element.value.present)


def dynamic_obstacles(
    clearance: float, opponents: Iterable[Track], forbidden: Iterable[Polygon]
) -> BaseGeometry:
    """Return the inflated opponents and conditional forbidden zones, as one shape.

    forbidden comes from MatchRules.forbidden_zones(side, world) (ADR 0014).
    """
    discs = [disc(track.center, track.radius + clearance) for track in opponents]
    zones = [inflate(polygon, clearance) for polygon in forbidden]
    return unary_union([*discs, *zones])


@dataclass(frozen=True, slots=True, eq=False)
class NavMap:
    """Where the centre of our robot may go on the table, apart from the dynamic obstacles."""

    clearance: float  # m, robot radius + margin
    free: Polygon | MultiPolygon  # closed: its boundary is free too

    @staticmethod
    def build(arena: Arena, side: Side, clearance: float, world: WorldSnapshot) -> NavMap:
        """Inflate the static obstacles of side and remove them from the table.

        The borders keep the clearance too: the table shrinks by it (ADR 0013).
        """
        table = box(0.0, 0.0, arena.width, arena.depth).buffer(-clearance, join_style="mitre")
        obstacles = inflate(unary_union(static_obstacles(arena, side, world)), clearance)
        free = table.difference(obstacles)
        assert isinstance(free, Polygon | MultiPolygon)  # an overlay of areas gives areas
        shapely.prepare(free)
        return NavMap(clearance, free)

    def is_free(self, point: Vec2) -> bool:
        return self.free.covers(Point(point.x, point.y))
