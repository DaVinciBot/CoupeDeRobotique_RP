import math
from types import MappingProxyType

import pytest
import shapely
from hypothesis import given
from hypothesis import strategies as st
from shapely import Point, Polygon, box

from dvb_brain.domain.arena import Arena, ElementSpec, Side, Size, Zone, ZoneKind
from dvb_brain.domain.geometry import Pose, Vec2
from dvb_brain.domain.navmap import (
    DISC_QUAD_SEGS,
    NavMap,
    disc,
    dynamic_obstacles,
    inflate,
    static_obstacles,
)
from dvb_brain.domain.world import (
    Construction,
    ElementState,
    Source,
    Track,
    WorldLifetimes,
    WorldModel,
    WorldSnapshot,
)

CLEARANCE = 0.1
# Largest distance from a rectangle to its inflated outline: at the ends of the cut corners.
OUTER = CLEARANCE / math.cos(math.pi / 8)
# Ratio of the circumradius of an inflated disc to its radius.
DISC_RATIO = 1 / math.cos(math.pi / (4 * DISC_QUAD_SEGS))
LIFETIMES = WorldLifetimes(lidar_tracks=0.3, remote=0.3, element_seen=2.0, odometry_history=2.0)


def zone(zone_id: str, kinds: set[ZoneKind], owner: Side | None, polygon: Polygon) -> Zone:
    return Zone(zone_id, frozenset(kinds), owner, polygon, 0.0, frozenset(), zone_id)


# A 2 x 1 m table. Each zone is a 0.1 m square, far enough from the others to be told apart.
ZONES = [
    zone("blue_nogo", {ZoneKind.FORBIDDEN}, Side.BLUE, box(0.21, 0.23, 0.31, 0.33)),
    zone("yellow_nogo", {ZoneKind.FORBIDDEN}, Side.YELLOW, box(0.61, 0.23, 0.71, 0.33)),
    zone("shared_nogo", {ZoneKind.FORBIDDEN}, None, box(1.01, 0.23, 1.11, 0.33)),
    zone(
        "blue_home",
        {ZoneKind.START, ZoneKind.EXCLUSIVE_OPPONENT},
        Side.BLUE,
        box(1.41, 0.23, 1.51, 0.33),
    ),
    zone(
        "yellow_home",
        {ZoneKind.START, ZoneKind.EXCLUSIVE_OPPONENT},
        Side.YELLOW,
        box(1.71, 0.23, 1.81, 0.33),
    ),
    zone("yellow_rock", {ZoneKind.OBSTACLE}, Side.YELLOW, box(0.21, 0.63, 0.31, 0.73)),
    zone("site", {ZoneKind.CONSTRUCTION}, None, box(0.61, 0.63, 0.71, 0.73)),
    zone("store", {ZoneKind.STORAGE}, Side.BLUE, box(1.01, 0.63, 1.11, 0.73)),
    zone("mark", {ZoneKind.OTHER}, None, box(1.41, 0.63, 1.51, 0.73)),
]
CRATE = ElementSpec("crate", "crate", Pose(1.76, 0.68, math.pi / 2), Size(0.1, 0.06, 0.05), "crate")
ARENA = Arena(
    width=2.0,
    depth=1.0,
    border_thickness=0.022,
    border_height=0.07,
    zones=MappingProxyType({z.id: z for z in ZONES}),
    elements=MappingProxyType({CRATE.id: CRATE}),
    aruco_tags=MappingProxyType({Side.BLUE: frozenset({1}), Side.YELLOW: frozenset({6})}),
)


def world() -> WorldModel:
    return WorldModel(ARENA.elements, LIFETIMES, now=0.0)


def snapshot(model: WorldModel | None = None) -> WorldSnapshot:
    return (model or world()).snapshot(1.0)


def has(obstacles: tuple[Polygon, ...], shape: Polygon) -> bool:
    return any(obstacle.equals(shape) for obstacle in obstacles)


def at(point: Vec2) -> Point:
    return Point(point.x, point.y)


# Static obstacles


def test_static_obstacles_of_blue_are_the_zones_it_must_not_enter() -> None:
    obstacles = static_obstacles(ARENA, Side.BLUE, snapshot())

    for zone_id in ("blue_nogo", "shared_nogo", "yellow_home", "yellow_rock"):
        assert has(obstacles, ARENA.zone(zone_id).polygon), zone_id
    for zone_id in ("yellow_nogo", "blue_home", "site", "store", "mark"):
        assert not has(obstacles, ARENA.zone(zone_id).polygon), zone_id


def test_static_obstacles_of_yellow_mirror_the_exclusive_zones() -> None:
    obstacles = static_obstacles(ARENA, Side.YELLOW, snapshot())

    for zone_id in ("yellow_nogo", "shared_nogo", "blue_home", "yellow_rock"):
        assert has(obstacles, ARENA.zone(zone_id).polygon), zone_id
    for zone_id in ("blue_nogo", "yellow_home"):
        assert not has(obstacles, ARENA.zone(zone_id).polygon), zone_id


def test_static_obstacles_include_an_element_in_place() -> None:
    assert has(static_obstacles(ARENA, Side.BLUE, snapshot()), CRATE.footprint())


def test_static_obstacles_drop_an_element_we_took() -> None:
    model = world()
    taken = ElementState(
        present=False, taken=True, placed_at=None, carried_by_us=True, confidence=1.0
    )
    model.mark_element("crate", taken, 0.5, Source.STRATEGY)

    assert not has(static_obstacles(ARENA, Side.BLUE, snapshot(model)), CRATE.footprint())


def test_static_obstacles_keep_an_element_the_remote_vision_saw_taken() -> None:
    # ADR 0013: our own state decides, so that a stale view does not rebuild the map.
    model = world()
    seen_taken = ElementState(
        present=False, taken=True, placed_at=None, carried_by_us=False, confidence=0.9
    )
    model.mark_element("crate", seen_taken, 0.9, Source.REMOTE)

    assert has(static_obstacles(ARENA, Side.BLUE, snapshot(model)), CRATE.footprint())


def test_static_obstacles_include_our_constructions() -> None:
    model = world()
    wall = box(1.01, 0.43, 1.31, 0.49)
    model.add_construction(Construction("wall", wall), 0.5)

    assert has(static_obstacles(ARENA, Side.BLUE, snapshot(model)), wall)


# Inflation


@given(
    x=st.floats(0.2, 1.8),
    y=st.floats(0.2, 0.8),
    length=st.floats(0.01, 0.4),
    width=st.floats(0.01, 0.4),
    theta=st.floats(-math.pi, math.pi),
)
def test_inflated_outline_keeps_the_clearance_and_stays_close(
    x: float, y: float, length: float, width: float, theta: float
) -> None:
    obstacle = ElementSpec("e", "e", Pose(x, y, theta), Size(length, width, 0.1), "e").footprint()

    inflated = inflate(obstacle, CLEARANCE)
    assert isinstance(inflated, Polygon)
    outline = shapely.segmentize(inflated.exterior, 0.002)
    distances = shapely.distance(obstacle, shapely.points(shapely.get_coordinates(outline)))

    assert distances.min() >= CLEARANCE * (1 - 1e-9)
    assert distances.max() <= OUTER * (1 + 1e-9)


def test_disc_covers_the_whole_disc() -> None:
    outline = shapely.segmentize(disc(Vec2(1.0, 0.5), 0.3).exterior, 0.001)
    distances = shapely.distance(Point(1.0, 0.5), shapely.points(shapely.get_coordinates(outline)))

    assert distances.min() >= 0.3 * (1 - 1e-9)
    assert distances.max() <= 0.3 * DISC_RATIO * (1 + 1e-9)


# Free space


def free_map(side: Side = Side.BLUE, model: WorldModel | None = None) -> NavMap:
    return NavMap.build(ARENA, side, CLEARANCE, snapshot(model))


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        (Vec2(0.5, CLEARANCE - 0.001), False),  # too close to the bottom border
        (Vec2(0.5, CLEARANCE + 0.001), True),
        (Vec2(2.0 - CLEARANCE + 0.001, 0.5), False),  # too close to the right border
        (Vec2(2.0 - CLEARANCE - 0.001, 0.5), True),
        (Vec2(CLEARANCE, CLEARANCE), True),  # the boundary is free
    ],
)
def test_free_space_keeps_the_clearance_from_the_borders(point: Vec2, expected: bool) -> None:
    assert free_map().is_free(point) is expected


def test_free_space_keeps_the_clearance_from_an_obstacle() -> None:
    rock = ARENA.zone("yellow_rock").polygon  # x from 0.21 to 0.31
    navmap = free_map()

    assert not navmap.is_free(Vec2(0.31 + CLEARANCE - 0.001, 0.68))
    assert navmap.is_free(Vec2(0.31 + CLEARANCE + 0.001, 0.68))
    assert navmap.free.distance(rock) == pytest.approx(CLEARANCE)
    # A corner is cut by a line tangent to its arc: on the diagonal, at CLEARANCE too.
    on_diagonal = CLEARANCE * math.sqrt(0.5)
    assert not navmap.is_free(Vec2(0.31 + on_diagonal - 0.001, 0.73 + on_diagonal - 0.001))
    assert navmap.is_free(Vec2(0.31 + on_diagonal + 0.001, 0.73 + on_diagonal + 0.001))


def test_free_space_depends_on_the_side() -> None:
    centre_of_yellow_home = Vec2(1.76, 0.28)

    assert not free_map(Side.BLUE).is_free(centre_of_yellow_home)
    assert free_map(Side.YELLOW).is_free(centre_of_yellow_home)


def test_free_space_follows_our_constructions() -> None:
    model = world()
    model.add_construction(Construction("wall", box(1.01, 0.43, 1.31, 0.49)), 0.5)

    assert free_map().is_free(Vec2(1.16, 0.46))
    assert not free_map(model=model).is_free(Vec2(1.16, 0.46))


def test_free_space_is_empty_when_the_robot_does_not_fit_on_the_table() -> None:
    navmap = NavMap.build(ARENA, Side.BLUE, 0.6, snapshot())

    assert navmap.free.is_empty
    assert not navmap.is_free(Vec2(1.0, 0.5))


# Dynamic obstacles


def test_dynamic_obstacles_are_inflated_discs_around_the_tracks() -> None:
    opponent = Track(id=1, center=Vec2(1.0, 0.5), radius=0.15, velocity=Vec2(0, 0), confirmed=True)

    obstacles = dynamic_obstacles(CLEARANCE, [opponent], [])

    reach = opponent.radius + CLEARANCE
    assert obstacles.contains(Point(1.0 + reach - 0.001, 0.5))
    assert not obstacles.contains(Point(1.0 + reach * DISC_RATIO + 0.001, 0.5))


def test_dynamic_obstacles_inflate_the_forbidden_polygons() -> None:
    forbidden = box(0.5, 0.4, 0.6, 0.5)

    obstacles = dynamic_obstacles(CLEARANCE, [], [forbidden])

    assert obstacles.contains(Point(0.6 + CLEARANCE - 0.001, 0.45))
    assert not obstacles.contains(Point(0.6 + CLEARANCE + 0.001, 0.45))


def test_no_dynamic_obstacle_gives_an_empty_shape() -> None:
    assert dynamic_obstacles(CLEARANCE, [], []).is_empty
