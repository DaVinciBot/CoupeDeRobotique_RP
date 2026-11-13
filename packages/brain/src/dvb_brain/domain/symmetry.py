"""Symmetry between the two sides of the table (architecture, section 9.5).

The axis is the vertical line x = width / 2: x becomes width - x and a heading theta becomes
pi - theta. Zones and elements find their symmetric through their mirror_id.
"""

import math

from shapely import Polygon
from shapely.affinity import scale

from dvb_brain.domain.arena import Arena, Side
from dvb_brain.domain.geometry import Pose, Vec2, normalize_angle


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
