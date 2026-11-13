"""Generic table model: sides, zones and game elements, in SI units.

Each edition describes its table in its own arena.json, in mm and degrees (ADR 0002); this
module knows nothing of the theme of the year (architecture, section 0).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum, auto
from pathlib import Path
from typing import Annotated

import msgspec
from shapely import Point, Polygon
from shapely.validation import explain_validity

from dvb_brain.domain.geometry import Pose, Vec2, normalize_angle
from dvb_brain.domain.json_schema import SchemaError, decode_json, field_error
from dvb_brain.domain.units import deg_to_rad, mm_to_m


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


def parse_arena(data: bytes) -> Arena:
    """Decode the content of an arena.json file and convert it to SI.

    Raise a SchemaError that names the field and the value.
    """
    raw = decode_json(data, _ArenaFile)
    for i, zone in enumerate(raw.zones):
        shapes = {
            "polygon_mm": zone.polygon_mm,
            "circle_mm": zone.circle_mm,
            "rect_mm": zone.rect_mm,
        }
        given = [name for name, shape in shapes.items() if shape is not None]
        if len(given) != 1:
            raise field_error(f"$.zones[{i}]", f"needs exactly one of {', '.join(shapes)}", given)
        if zone.polygon_mm is not None and not (polygon := Polygon(zone.polygon_mm)).is_valid:
            reason = f"invalid polygon ({explain_validity(polygon)})"
            raise field_error(f"$.zones[{i}].polygon_mm", reason, zone.polygon_mm)
        if ZoneKind.EXCLUSIVE_OPPONENT in zone.kinds and zone.owner is None:
            raise field_error(f"$.zones[{i}].owner", "exclusive_opponent needs an owner", None)
    _check_ids("zones", [(zone.id, zone.mirror_id) for zone in raw.zones])
    _check_ids("elements", [(element.id, element.mirror_id) for element in raw.elements])
    return Arena(
        width=mm_to_m(raw.width_mm),
        depth=mm_to_m(raw.depth_mm),
        border_thickness=mm_to_m(raw.border_thickness_mm),
        border_height=mm_to_m(raw.border_height_mm),
        zones={zone.id: _to_zone(zone) for zone in raw.zones},
        elements={element.id: _to_element(element) for element in raw.elements},
        aruco_tags={Side.BLUE: raw.aruco_tags.blue, Side.YELLOW: raw.aruco_tags.yellow},
    )


def load_arena(path: Path) -> Arena:
    """Read an arena.json file. At startup only: this blocks on the disk."""
    try:
        return parse_arena(path.read_bytes())
    except SchemaError as error:
        raise SchemaError(f"{path}: {error}") from error


# Schema of arena.json: lengths in mm, angles in degrees.

_Id = Annotated[str, msgspec.Meta(min_length=1)]
_PositiveMm = Annotated[float, msgspec.Meta(gt=0)]
_NonNegativeMm = Annotated[float, msgspec.Meta(ge=0)]
_Tags = frozenset[Annotated[int, msgspec.Meta(ge=0)]]


class _PoseFile(msgspec.Struct, forbid_unknown_fields=True):
    x_mm: float
    y_mm: float
    theta_deg: float


class _SizeFile(msgspec.Struct, forbid_unknown_fields=True):
    length_mm: _PositiveMm
    width_mm: _PositiveMm
    height_mm: _PositiveMm


class _CircleFile(msgspec.Struct, forbid_unknown_fields=True):
    x: float
    y: float
    radius: _PositiveMm


class _RectFile(msgspec.Struct, forbid_unknown_fields=True):
    """Rectangle centred on (x, y); its length is along theta_deg."""

    x: float
    y: float
    length: _PositiveMm
    width: _PositiveMm
    theta_deg: float


class _ZoneFile(msgspec.Struct, forbid_unknown_fields=True):
    id: _Id
    kinds: Annotated[frozenset[ZoneKind], msgspec.Meta(min_length=1)]
    owner: Side | None  # required: null for a shared zone, never by omission
    mirror_id: _Id
    # Exactly one shape.
    polygon_mm: Annotated[list[tuple[float, float]], msgspec.Meta(min_length=3)] | None = None
    circle_mm: _CircleFile | None = None
    rect_mm: _RectFile | None = None
    height_mm: _NonNegativeMm = 0.0
    tags: frozenset[str] = frozenset()


class _ElementFile(msgspec.Struct, forbid_unknown_fields=True):
    id: _Id
    kind: _Id
    pose: _PoseFile
    size: _SizeFile
    mirror_id: _Id


class _ArucoTagsFile(msgspec.Struct, forbid_unknown_fields=True):
    blue: _Tags
    yellow: _Tags


class _ArenaFile(msgspec.Struct, forbid_unknown_fields=True):
    width_mm: _PositiveMm
    depth_mm: _PositiveMm
    border_thickness_mm: _NonNegativeMm
    border_height_mm: _NonNegativeMm
    aruco_tags: _ArucoTagsFile
    zones: list[_ZoneFile]
    elements: list[_ElementFile]


def _check_ids(collection: str, entries: list[tuple[str, str]]) -> None:
    """Check that ids are unique and that each mirror_id points to an entry that points back."""
    mirror_of: dict[str, str] = {}
    for i, (entry_id, mirror_id) in enumerate(entries):
        if entry_id in mirror_of:
            raise field_error(f"$.{collection}[{i}].id", "duplicate id", entry_id)
        mirror_of[entry_id] = mirror_id
    for i, (entry_id, mirror_id) in enumerate(entries):
        path = f"$.{collection}[{i}].mirror_id"
        if mirror_id not in mirror_of:
            raise field_error(path, f"no such id in {collection}", mirror_id)
        if mirror_of[mirror_id] != entry_id:
            reason = f"not mutual: the mirror_id of {mirror_id!r} is {mirror_of[mirror_id]!r}"
            raise field_error(path, reason, mirror_id)


def _zone_polygon(raw: _ZoneFile) -> Polygon:
    """Convert the shape of a zone to a polygon in metres.

    A circle becomes an inscribed 64-gon: 0.12 mm inside a circle of 100 mm radius.
    """
    if raw.circle_mm is not None:
        circle = raw.circle_mm
        center = Point(mm_to_m(circle.x), mm_to_m(circle.y))
        return center.buffer(mm_to_m(circle.radius), quad_segs=16)
    if raw.rect_mm is not None:
        rect = raw.rect_mm
        frame = Pose(mm_to_m(rect.x), mm_to_m(rect.y), deg_to_rad(rect.theta_deg))
        half_length, half_width = mm_to_m(rect.length) / 2, mm_to_m(rect.width) / 2
        corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        points = [frame.to_world(Vec2(u * half_length, v * half_width)) for u, v in corners]
        return Polygon([(p.x, p.y) for p in points])
    assert raw.polygon_mm is not None  # checked by parse_arena
    return Polygon([(mm_to_m(x), mm_to_m(y)) for x, y in raw.polygon_mm])


def _to_zone(raw: _ZoneFile) -> Zone:
    return Zone(
        id=raw.id,
        kinds=raw.kinds,
        owner=raw.owner,
        polygon=_zone_polygon(raw),
        height=mm_to_m(raw.height_mm),
        tags=raw.tags,
        mirror_id=raw.mirror_id,
    )


def _to_element(raw: _ElementFile) -> ElementSpec:
    pose = Pose(
        mm_to_m(raw.pose.x_mm),
        mm_to_m(raw.pose.y_mm),
        normalize_angle(deg_to_rad(raw.pose.theta_deg)),
    )
    size = Size(
        mm_to_m(raw.size.length_mm), mm_to_m(raw.size.width_mm), mm_to_m(raw.size.height_mm)
    )
    return ElementSpec(raw.id, raw.kind, pose, size, raw.mirror_id)
