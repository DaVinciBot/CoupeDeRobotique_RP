"""Checks of the 2027 table against the rules (RJ D, RG G.6) and the plan of RJ G.1."""

import math
from collections import Counter
from pathlib import Path

import pytest
from shapely import Polygon

from dvb_brain.app.files import load_file
from dvb_brain.domain.arena import Arena, ElementSpec, Side, Zone, ZoneKind, parse_arena
from dvb_brain.domain.geometry import Vec2

ARENA = Path(__file__).parents[1] / "arena.json"
TOLERANCE = 1e-9  # rounding of the mm to m conversion


@pytest.fixture(scope="module")
def arena() -> Arena:
    return load_file(ARENA, parse_arena)


def tagged(arena: Arena, tag: str, side: Side | None) -> list[Zone]:
    return [zone for zone in arena.zones.values() if tag in zone.tags and zone.owner is side]


def only(zones: list[Zone]) -> Zone:
    (zone,) = zones
    return zone


def footprint(element: ElementSpec) -> Polygon:
    half_length, half_width = element.size.length / 2, element.size.width / 2
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    points = [element.pose.to_world(Vec2(u * half_length, v * half_width)) for u, v in corners]
    return Polygon([(p.x, p.y) for p in points])


def rectangle_sides(zone: Zone) -> tuple[float, float]:
    """Sides of a zone drawn as a rectangle, shortest first."""
    corners = list(zone.polygon.exterior.coords)
    assert len(corners) == 5, zone.id
    sides = sorted(math.dist(corners[i], corners[i + 1]) for i in range(4))
    assert sides[0] == pytest.approx(sides[1]) and sides[2] == pytest.approx(sides[3]), zone.id
    return sides[0], sides[2]


def test_table_size(arena: Arena) -> None:
    # RJ D.2: 3000 x 2000 mm, borders 70 mm high and 22 mm thick.
    assert (arena.width, arena.depth) == (3.0, 2.0)
    assert (arena.border_thickness, arena.border_height) == pytest.approx((0.022, 0.07))


def test_aruco_tags(arena: Arena) -> None:
    # RG G.6 for the robots, RJ D.4 for the stones.
    assert arena.aruco_tags == {Side.BLUE: {1, 2, 3, 4, 5}, Side.YELLOW: {6, 7, 8, 9, 10}}
    assert arena.element_aruco_tags == {"stone": {13}}


def test_thirty_stones_three_per_quarry(arena: Arena) -> None:
    # RJ D.4: 30 stones of 320 x 110 x 110 mm, 3 in each quarry.
    stones = [element for element in arena.elements.values() if element.kind == "stone"]
    assert len(stones) == len(arena.elements) == 30
    for stone in stones:
        size = (stone.size.length, stone.size.width, stone.size.height)
        assert size == pytest.approx((0.32, 0.11, 0.11))
    quarries = tagged(arena, "quarry", None)
    assert len(quarries) == 10
    holders = {
        stone.id: [
            quarry.id
            for quarry in quarries
            if quarry.polygon.buffer(TOLERANCE).covers(footprint(stone))
        ]
        for stone in stones
    }
    assert all(len(ids) == 1 for ids in holders.values()), holders  # each stone in one quarry
    assert Counter(ids[0] for ids in holders.values()) == dict.fromkeys(
        (quarry.id for quarry in quarries), 3
    )


@pytest.fixture(params=[Side.BLUE, Side.YELLOW], ids=lambda side: side.value)
def side(request: pytest.FixtureRequest) -> Side:
    return request.param


def test_throne_room(arena: Arena, side: Side) -> None:
    # RJ D.3: a 500 x 500 mm start and end area, on the side of the table.
    throne_room = only(tagged(arena, "throne_room", side))
    assert throne_room.kinds == {ZoneKind.START, ZoneKind.END, ZoneKind.EXCLUSIVE_OPPONENT}
    assert rectangle_sides(throne_room) == pytest.approx((0.5, 0.5))
    min_x, _, max_x, _ = throne_room.polygon.bounds
    assert (min_x == 0.0) if side is Side.YELLOW else (max_x == pytest.approx(arena.width))


def test_start_and_end_zones_are_the_throne_room(arena: Arena, side: Side) -> None:
    throne_room = only(tagged(arena, "throne_room", side))
    assert arena.zones_of(ZoneKind.START, side) == (throne_room,)
    assert arena.zones_of(ZoneKind.END, side) == (throne_room,)


def test_courtyard_holds_the_throne_room(arena: Arena, side: Side) -> None:
    # RJ D.4: the courtyard includes the throne room.
    courtyard = only(tagged(arena, "courtyard", side))
    throne_room = only(tagged(arena, "throne_room", side))
    assert courtyard.polygon.covers(throne_room.polygon)


def test_ramparts(arena: Arena, side: Side) -> None:
    # RJ D.4: walls of 200 x 400 mm and towers of 200 mm diameter.
    walls = tagged(arena, "wall", side)
    assert len(walls) == 5
    for wall in walls:
        assert rectangle_sides(wall) == pytest.approx((0.2, 0.4)), wall.id
    towers = tagged(arena, "tower", side)
    assert len(towers) == 4
    for tower in towers:
        min_x, min_y, max_x, max_y = tower.polygon.bounds
        assert (max_x - min_x, max_y - min_y) == pytest.approx((0.2, 0.2)), tower.id
        assert tower.polygon.area == pytest.approx(math.pi * 0.1**2, rel=1e-2), tower.id
    for rampart in walls + towers:
        assert ZoneKind.CONSTRUCTION in rampart.kinds, rampart.id


def test_moats_and_stables(arena: Arena, side: Side) -> None:
    # RJ D.4: 200 x 300 mm stables; the moats are drawn as 200 x 400 mm areas on the plan.
    moats = tagged(arena, "moat", side)
    assert len(moats) == 3
    for moat in moats:
        assert rectangle_sides(moat) == pytest.approx((0.2, 0.4)), moat.id
    stables = tagged(arena, "stable", side)
    assert len(stables) == 2
    for stable in stables:
        assert rectangle_sides(stable) == pytest.approx((0.2, 0.3)), stable.id


def test_exclusive_areas_are_the_castle(arena: Arena, side: Side) -> None:
    # Architecture 8.1: throne room, courtyard and ramparts are exclusive areas (RG H.4).
    # The list is still to be confirmed by the organizers (TODO, points to validate).
    castle = {
        zone.id
        for tag in ("throne_room", "courtyard", "wall", "tower")
        for zone in tagged(arena, tag, side)
    }
    assert {zone.id for zone in arena.zones_of(ZoneKind.EXCLUSIVE_OPPONENT, side)} == castle


def test_end_poses_are_in_the_throne_room(arena: Arena, side: Side) -> None:
    # Provisional: whether the whole robot fits (RJ E.3) needs its footprint (TODO 2.4, 7.4).
    throne_room = only(tagged(arena, "throne_room", side))
    assert throne_room.robot_poses
    for pose in throne_room.robot_poses:
        assert arena.contains(throne_room.id, pose.position)
