"""Generic table model: sides, zones and game elements, in SI units.

Each edition describes its table in its own arena.json; this module knows nothing of the
theme of the year (architecture, section 0).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum, auto

from shapely import Point, Polygon

from dvb_brain.domain.geometry import Pose, Vec2


class Side(Enum):
    BLUE = "blue"
    YELLOW = "yellow"


class ZoneKind(StrEnum):
    """Generic role of a zone. A zone can have several roles.

    EXCLUSIVE_OPPONENT is an exclusive-access area of the zone owner: the robot of the
    other side must never enter it (forfeit, RG H.4).
    """

    START = auto()
    END = auto()
    FORBIDDEN = auto()
    EXCLUSIVE_OPPONENT = auto()
    CONSTRUCTION = auto()
    STORAGE = auto()
    OBSTACLE = auto()
    OTHER = auto()


@dataclass(frozen=True, slots=True)
class Zone:
    """Area of the table, in metres. A zone without owner is shared by both sides."""

    id: str
    kinds: frozenset[ZoneKind]
    owner: Side | None
    polygon: Polygon
    height: float
    tags: frozenset[str]
    mirror_id: str  # id of the symmetric zone; its own id when on the axis


@dataclass(frozen=True, slots=True)
class Size:
    """Bounding box of a game element, in metres; length is along the heading of its pose."""

    length: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class ElementSpec:
    """Game element at its initial place. Its kind is defined by the edition."""

    id: str
    kind: str
    pose: Pose
    size: Size
    mirror_id: str  # id of the symmetric element; its own id when on the axis


@dataclass(frozen=True, slots=True)
class Arena:
    """Table of an edition: x from 0 to width, y from 0 to depth, in metres."""

    width: float
    depth: float
    border_thickness: float
    border_height: float
    zones: Mapping[str, Zone]  # by id, in file order
    elements: Mapping[str, ElementSpec]  # by id, in file order
    aruco_tags: Mapping[Side, frozenset[int]]

    def zones_of(self, kind: ZoneKind, side: Side) -> tuple[Zone, ...]:
        """Return the zones with this role that belong to side or to nobody."""
        return tuple(
            zone
            for zone in self.zones.values()
            if kind in zone.kinds and zone.owner in (side, None)
        )

    def zone(self, zone_id: str) -> Zone:
        return self.zones[zone_id]

    def contains(self, zone_id: str, point: Vec2) -> bool:
        """Return True when the point is in the zone, boundary included."""
        return self.zone(zone_id).polygon.covers(Point(point.x, point.y))

    def polygon_inside(self, zone_id: str, footprint: Sequence[Vec2]) -> bool:
        """Return True when the footprint is entirely in the zone, boundary included."""
        return self.zone(zone_id).polygon.covers(Polygon([(p.x, p.y) for p in footprint]))
