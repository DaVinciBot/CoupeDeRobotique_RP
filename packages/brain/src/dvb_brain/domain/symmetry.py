"""Symmetry between the two sides of the table (architecture, section 9.5).

The axis is the vertical line x = width / 2: x becomes width - x and a heading theta becomes
pi - theta. Zones and elements find their symmetric through their mirror_id.
"""

import math

from shapely import Polygon
from shapely.affinity import scale

from dvb_brain.domain.arena import Arena, Side
from dvb_brain.domain.geometry import Pose, Vec2, angle_diff, normalize_angle
from dvb_brain.domain.json_schema import SchemaError

# Rounding error of the mm to m conversion, not a property of the table.
_TOLERANCE = 1e-6


def mirror_side(side: Side | None) -> Side | None:
    """Return the other side; a shared owner (None) stays shared."""
    match side:
        case Side.BLUE:
            return Side.YELLOW
        case Side.YELLOW:
            return Side.BLUE
        case None:
            return None


def mirror_point(point: Vec2, table_width: float) -> Vec2:
    return Vec2(table_width - point.x, point.y)


def mirror_pose(pose: Pose, table_width: float) -> Pose:
    return Pose(table_width - pose.x, pose.y, normalize_angle(math.pi - pose.theta))


def mirror_polygon(polygon: Polygon, table_width: float) -> Polygon:
    return scale(polygon, xfact=-1.0, yfact=1.0, origin=(table_width / 2, 0.0))


def mirror_zone_id(arena: Arena, zone_id: str) -> str:
    return arena.zone(zone_id).mirror_id


def mirror_element_id(arena: Arena, element_id: str) -> str:
    return arena.elements[element_id].mirror_id


def check_symmetry(arena: Arena) -> None:
    """Check that each zone and element is the geometric mirror of its mirror_id.

    Raise a SchemaError that names the zone or the element. An element is a box: its heading
    is compared modulo pi, since a half turn leaves it unchanged.
    """
    for zone in arena.zones.values():
        mirror = arena.zone(zone.mirror_id)
        name = f"zone {zone.id!r} and its mirror {mirror.id!r}"
        distance = mirror_polygon(zone.polygon, arena.width).hausdorff_distance(mirror.polygon)
        if distance > _TOLERANCE:
            raise SchemaError(f"{name}: polygons are not symmetric (off by {distance:.6f} m)")
        if mirror.owner != mirror_side(zone.owner):
            raise SchemaError(f"{name}: owners {zone.owner} and {mirror.owner} are not swapped")
        if (mirror.kinds, mirror.height, mirror.tags) != (zone.kinds, zone.height, zone.tags):
            raise SchemaError(f"{name}: kinds, height or tags differ")
    for element in arena.elements.values():
        mirror = arena.elements[element.mirror_id]
        name = f"element {element.id!r} and its mirror {mirror.id!r}"
        expected = mirror_pose(element.pose, arena.width)
        distance = (expected.position - mirror.pose.position).norm()
        if distance > _TOLERANCE:
            raise SchemaError(f"{name}: positions are not symmetric (off by {distance:.6f} m)")
        if abs(normalize_angle(2 * angle_diff(expected.theta, mirror.pose.theta))) > _TOLERANCE:
            raise SchemaError(f"{name}: headings are not symmetric")
        if (mirror.kind, mirror.size) != (element.kind, element.size):
            raise SchemaError(f"{name}: kind or size differ")
