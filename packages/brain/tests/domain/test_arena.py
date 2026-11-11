import pytest
from shapely import Polygon

from dvb_brain.domain.arena import Arena, Side, Zone, ZoneKind
from dvb_brain.domain.geometry import Vec2


def square(x: float, y: float, side: float) -> Polygon:
    return Polygon([(x, y), (x + side, y), (x + side, y + side), (x, y + side)])


def make_zone(
    zone_id: str, kinds: set[ZoneKind], owner: Side | None, polygon: Polygon, mirror_id: str
) -> Zone:
    return Zone(zone_id, frozenset(kinds), owner, polygon, 0.0, frozenset(), mirror_id)


@pytest.fixture
def arena() -> Arena:
    start = {ZoneKind.START, ZoneKind.END, ZoneKind.EXCLUSIVE_OPPONENT}
    zones = [
        make_zone("blue_start", start, Side.BLUE, square(0.0, 0.0, 0.5), "yellow_start"),
        make_zone("yellow_start", start, Side.YELLOW, square(2.5, 0.0, 0.5), "blue_start"),
        make_zone("middle", {ZoneKind.FORBIDDEN}, None, square(1.4, 0.9, 0.2), "middle"),
    ]
    return Arena(
        width=3.0,
        depth=2.0,
        border_thickness=0.022,
        border_height=0.07,
        zones={zone.id: zone for zone in zones},
        elements={},
        aruco_tags={Side.BLUE: frozenset({1}), Side.YELLOW: frozenset({6})},
    )


def ids(zones: tuple[Zone, ...]) -> list[str]:
    return [zone.id for zone in zones]


def test_zones_of_returns_own_zones_only(arena: Arena) -> None:
    assert ids(arena.zones_of(ZoneKind.START, Side.BLUE)) == ["blue_start"]
    assert ids(arena.zones_of(ZoneKind.END, Side.YELLOW)) == ["yellow_start"]


def test_zones_of_includes_shared_zones(arena: Arena) -> None:
    assert ids(arena.zones_of(ZoneKind.FORBIDDEN, Side.BLUE)) == ["middle"]
    assert ids(arena.zones_of(ZoneKind.FORBIDDEN, Side.YELLOW)) == ["middle"]


def test_zones_of_gives_the_areas_forbidden_to_the_other_side(arena: Arena) -> None:
    assert ids(arena.zones_of(ZoneKind.EXCLUSIVE_OPPONENT, Side.YELLOW)) == ["yellow_start"]


def test_zones_of_without_match_is_empty(arena: Arena) -> None:
    assert arena.zones_of(ZoneKind.STORAGE, Side.BLUE) == ()


def test_zone_by_id(arena: Arena) -> None:
    assert arena.zone("middle").owner is None


def test_zone_unknown_id_raises_key_error(arena: Arena) -> None:
    with pytest.raises(KeyError, match="nowhere"):
        arena.zone("nowhere")


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        (Vec2(0.25, 0.25), True),
        (Vec2(0.5, 0.25), True),  # on the boundary
        (Vec2(0.0, 0.0), True),  # on a corner
        (Vec2(0.51, 0.25), False),
        (Vec2(2.75, 0.25), False),  # in the other start zone
    ],
)
def test_contains(arena: Arena, point: Vec2, expected: bool) -> None:
    assert arena.contains("blue_start", point) is expected


@pytest.mark.parametrize(
    ("footprint", "expected"),
    [
        ([Vec2(0.1, 0.1), Vec2(0.4, 0.1), Vec2(0.4, 0.4), Vec2(0.1, 0.4)], True),
        ([Vec2(0.2, 0.0), Vec2(0.5, 0.0), Vec2(0.5, 0.3), Vec2(0.2, 0.3)], True),  # in a corner
        ([Vec2(0.3, 0.1), Vec2(0.6, 0.1), Vec2(0.6, 0.4), Vec2(0.3, 0.4)], False),  # across
        ([Vec2(1.0, 1.0), Vec2(1.2, 1.0), Vec2(1.2, 1.2)], False),  # outside
    ],
)
def test_polygon_inside(arena: Arena, footprint: list[Vec2], expected: bool) -> None:
    assert arena.polygon_inside("blue_start", footprint) is expected
