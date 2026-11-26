import heapq
import math
import random
from collections import deque
from collections.abc import Sequence
from itertools import pairwise
from types import MappingProxyType

import numpy as np
import pytest
import shapely
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from shapely import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from dvb_brain.domain.arena import Arena, ElementSpec, Side, Size, Zone, ZoneKind
from dvb_brain.domain.geometry import Pose, Vec2
from dvb_brain.domain.navmap import NavigationSettings, dynamic_obstacles
from dvb_brain.domain.planner import NoPath, NoPathReason, Path, Planner
from dvb_brain.domain.robot import RobotGeometry
from dvb_brain.domain.world import (
    Construction,
    ElementState,
    Source,
    Track,
    TrackSet,
    WorldLifetimes,
    WorldModel,
)

RADIUS = 0.08
MARGIN = 0.02
CLEARANCE = RADIUS + MARGIN
LIFETIMES = WorldLifetimes(lidar_tracks=0.3, remote=0.3, element_seen=2.0, odometry_history=2.0)


def make_arena(
    *obstacles: Polygon,
    width: float = 2.0,
    depth: float = 1.0,
    elements: Sequence[ElementSpec] = (),
) -> Arena:
    zones = [
        Zone(
            f"rock_{i}",
            frozenset({ZoneKind.OBSTACLE}),
            None,
            polygon,
            0.0,
            frozenset(),
            f"rock_{i}",
        )
        for i, polygon in enumerate(obstacles)
    ]
    return Arena(
        width=width,
        depth=depth,
        border_thickness=0.022,
        border_height=0.07,
        zones=MappingProxyType({zone.id: zone for zone in zones}),
        elements=MappingProxyType({element.id: element for element in elements}),
        aruco_tags=MappingProxyType({Side.BLUE: frozenset({1}), Side.YELLOW: frozenset({6})}),
    )


def world_of(arena: Arena) -> WorldModel:
    return WorldModel(arena.elements, LIFETIMES, now=0.0)


def planner_for(
    arena: Arena, model: WorldModel | None = None, turn_penalty: float = 0.0
) -> Planner:
    snapshot = (model or world_of(arena)).snapshot(1.0)
    return Planner(
        arena,
        Side.BLUE,
        RobotGeometry(radius=RADIUS),
        NavigationSettings(margin=MARGIN, turn_penalty=turn_penalty),
        snapshot,
    )


def opponent(x: float, y: float, radius: float = 0.1) -> Track:
    return Track(id=1, center=Vec2(x, y), radius=radius, velocity=Vec2(0, 0), confirmed=True)


def line(a: Vec2, b: Vec2) -> LineString:
    return LineString([(a.x, a.y), (b.x, b.y)])


def assert_clear(
    planner: Planner, path: Path, opponents: Sequence[Track] = (), forbidden: Sequence[Polygon] = ()
) -> None:
    """Each segment stays in the free space and out of the inflated dynamic obstacles."""
    dynamic = dynamic_obstacles(planner.clearance, opponents, forbidden)
    for a, b in pairwise(path.points):
        segment = line(a, b)
        assert planner.navmap.free.covers(segment), (a, b)
        assert not dynamic.relate_pattern(segment, "T********"), (a, b)


def as_path(result: Path | NoPath) -> Path:
    assert isinstance(result, Path), result
    return result


# Straight lines and detours


def test_straight_line_when_nothing_is_in_the_way() -> None:
    path = as_path(planner_for(make_arena()).plan(Vec2(0.3, 0.5), Vec2(1.7, 0.5)))

    assert path.points == (Vec2(0.3, 0.5), Vec2(1.7, 0.5))
    assert path.length == pytest.approx(1.4)


def test_same_start_and_goal_gives_a_single_point() -> None:
    path = as_path(planner_for(make_arena()).plan(Vec2(0.3, 0.5), Vec2(0.3, 0.5)))

    assert path.points == (Vec2(0.3, 0.5),)
    assert path.length == 0.0


def test_detour_around_an_obstacle() -> None:
    planner = planner_for(make_arena(box(0.95, 0.3, 1.05, 0.7)))

    path = as_path(planner.plan(Vec2(0.3, 0.5), Vec2(1.7, 0.5)))

    assert len(path.points) > 2
    assert path.points[0] == Vec2(0.3, 0.5)
    assert path.points[-1] == Vec2(1.7, 0.5)
    assert path.length > 1.4
    assert_clear(planner, path)


def test_detour_around_an_opponent() -> None:
    planner = planner_for(make_arena())
    opponents = [opponent(1.0, 0.5)]

    path = as_path(planner.plan(Vec2(0.3, 0.5), Vec2(1.7, 0.5), opponents=opponents))

    assert len(path.points) > 2
    assert_clear(planner, path, opponents=opponents)


def test_opponent_closes_a_static_segment() -> None:
    # Over the obstacle is shorter, along a segment between two of its corners. The opponent
    # closes it: the path must go under.
    planner = planner_for(make_arena(box(0.95, 0.25, 1.05, 0.65)))
    opponents = [opponent(1.0, 0.8, radius=0.03)]

    path = as_path(planner.plan(Vec2(0.3, 0.5), Vec2(1.7, 0.5), opponents=opponents))

    assert_clear(planner, path, opponents=opponents)
    assert min(point.y for point in path.points) < 0.25


def test_detour_around_a_conditional_forbidden_zone() -> None:
    planner = planner_for(make_arena())
    forbidden = [box(0.95, 0.3, 1.05, 0.7)]

    path = as_path(planner.plan(Vec2(0.3, 0.5), Vec2(1.7, 0.5), forbidden=forbidden))

    assert len(path.points) > 2
    assert_clear(planner, path, forbidden=forbidden)


# Tangency


def test_segment_along_an_edge_of_an_inflated_obstacle_is_free() -> None:
    # The top side of the inflated obstacle is the line y = 0.6 + CLEARANCE, from x = 0.95 to 1.05.
    planner = planner_for(make_arena(box(0.95, 0.4, 1.05, 0.6)))
    start, goal = Vec2(0.96, 0.6 + CLEARANCE), Vec2(1.04, 0.6 + CLEARANCE)

    assert as_path(planner.plan(start, goal)).points == (start, goal)


def test_segment_through_a_vertex_of_an_inflated_opponent_is_free() -> None:
    planner = planner_for(make_arena())
    opponents = [opponent(1.0, 0.5)]
    disc = dynamic_obstacles(planner.clearance, opponents, [])
    # The top vertex of the disc: a horizontal line through it touches the disc there only.
    coordinates = shapely.get_coordinates(disc)
    top = coordinates[np.argmax(coordinates[:, 1])]
    start, goal = Vec2(0.7, float(top[1])), Vec2(1.3, float(top[1]))

    assert as_path(planner.plan(start, goal, opponents=opponents)).points == (start, goal)


@pytest.mark.parametrize(
    ("gap", "passes"), [(2 * CLEARANCE + 0.001, True), (2 * CLEARANCE - 0.001, False)]
)
def test_passage_between_two_obstacles(gap: float, passes: bool) -> None:
    # The two obstacles close the table from border to border, but for the gap between them.
    lower, upper = box(0.95, 0.15, 1.05, 0.45), box(0.95, 0.45 + gap, 1.05, 0.85)
    planner = planner_for(make_arena(lower, upper))

    result = planner.plan(Vec2(0.5, 0.55), Vec2(1.5, 0.55))

    if passes:
        assert_clear(planner, as_path(result))
    else:
        assert result == NoPath(NoPathReason.UNREACHABLE)


# Turn penalty


def zigzag_arena() -> Arena:
    return make_arena(
        box(0.55, 0.2, 0.6, 0.62),
        box(0.85, 0.38, 0.9, 0.8),
        box(1.15, 0.2, 1.2, 0.62),
        box(1.45, 0.38, 1.5, 0.8),
    )


def cost(path: Path, turn_penalty: float) -> float:
    return path.length + turn_penalty * (len(path.points) - 2)


def test_turn_penalty_trades_length_for_fewer_turns() -> None:
    arena = zigzag_arena()
    start, goal = Vec2(0.3, 0.5), Vec2(1.75, 0.5)
    shortest = as_path(planner_for(arena).plan(start, goal))
    penalised = as_path(planner_for(arena, turn_penalty=1.0).plan(start, goal))

    assert len(penalised.points) < len(shortest.points)
    assert penalised.length > shortest.length
    assert cost(penalised, 1.0) <= cost(shortest, 1.0)


# Start and goal in an obstacle


def test_start_in_an_inflated_obstacle_is_projected_on_the_free_space() -> None:
    planner = planner_for(make_arena())
    start = Vec2(0.5, 0.05)  # closer to the bottom border than the clearance

    path = as_path(planner.plan(start, Vec2(1.5, 0.55)))

    assert path.points[0] == start
    projection = path.points[1]
    assert planner.navmap.is_free(projection)
    assert projection.x == pytest.approx(0.5, abs=1e-6)
    assert projection.y == pytest.approx(CLEARANCE, abs=1e-3)
    assert_clear(planner, Path(path.points[1:]))


def test_any_start_in_an_inflated_obstacle_finds_a_path() -> None:
    planner = planner_for(make_arena(box(0.9, 0.4, 1.1, 0.6)))
    inflated = box(0.9, 0.4, 1.1, 0.6).buffer(CLEARANCE)
    rng = random.Random(4)
    starts: list[Vec2] = []
    while len(starts) < 300:
        point = Vec2(rng.uniform(0.75, 1.25), rng.uniform(0.25, 0.75))
        if inflated.contains(Point(point.x, point.y)) and not planner.navmap.is_free(point):
            starts.append(point)

    for start in starts:
        path = as_path(planner.plan(start, Vec2(1.7, 0.5)))
        assert_clear(planner, Path(path.points[1:]))


def test_start_next_to_an_opponent_is_projected_out_of_it() -> None:
    planner = planner_for(make_arena())
    opponents = [opponent(1.0, 0.5)]

    path = as_path(planner.plan(Vec2(1.15, 0.5), Vec2(1.7, 0.5), opponents=opponents))

    assert path.points[0] == Vec2(1.15, 0.5)
    assert_clear(planner, Path(path.points[1:]), opponents=opponents)


def test_start_a_hair_inside_an_inflated_obstacle_goes_straight_on() -> None:
    # A robot stopped on a line along an inflated obstacle is often a hair inside it: no
    # quarter turn to step out, and the first line keeps within the margin of the free space.
    planner = planner_for(make_arena(box(0.9, 0.3, 1.1, 0.7)))  # inflated top side at y = 0.8
    start = Vec2(1.0, 0.8 - 0.0002)

    path = as_path(planner.plan(start, Vec2(1.7, 0.85)))

    assert path.points[0] == start
    assert (path.points[1] - start).norm() > MARGIN
    assert planner.navmap.free.buffer(MARGIN).covers(line(path.points[0], path.points[1]))
    assert_clear(planner, Path(path.points[1:]))


def test_start_never_crosses_a_static_obstacle_to_leave_a_dynamic_one() -> None:
    # The nearest point out of the forbidden zone is beyond the rock: crossing it is refused.
    planner = planner_for(make_arena(box(0.95, 0.0, 1.05, 0.6)))
    forbidden = [box(0.3, 0.0, 1.0, 1.0)]

    result = planner.plan(Vec2(0.8, 0.35), Vec2(1.7, 0.5), forbidden=forbidden)

    assert result == NoPath(NoPathReason.UNREACHABLE)


def test_goal_in_an_inflated_obstacle_has_no_path() -> None:
    planner = planner_for(make_arena(box(0.95, 0.3, 1.05, 0.7)))

    assert planner.plan(Vec2(0.3, 0.5), Vec2(1.0, 0.75)) == NoPath(NoPathReason.GOAL_IN_OBSTACLE)
    # Closer to the right border than the clearance.
    assert planner.plan(Vec2(0.3, 0.5), Vec2(1.95, 0.5)) == NoPath(NoPathReason.GOAL_IN_OBSTACLE)


def test_goal_on_an_opponent_has_no_path() -> None:
    result = planner_for(make_arena()).plan(
        Vec2(0.3, 0.5), Vec2(1.0, 0.5), opponents=[opponent(1.05, 0.5)]
    )

    assert result == NoPath(NoPathReason.GOAL_IN_OBSTACLE)


def test_goal_beyond_a_wall_across_the_table_is_unreachable() -> None:
    planner = planner_for(make_arena(box(0.95, 0.0, 1.05, 1.0)))

    assert planner.plan(Vec2(0.3, 0.5), Vec2(1.7, 0.5)) == NoPath(NoPathReason.UNREACHABLE)


# Static part kept or rebuilt


CRATE = ElementSpec("crate", "crate", Pose(1.0, 0.5, 0.0), Size(0.1, 0.06, 0.05), "crate")


def test_updated_keeps_the_planner_while_nothing_static_changes() -> None:
    arena = make_arena(elements=[CRATE])
    model = world_of(arena)
    planner = planner_for(arena, model)
    model.update_tracks(TrackSet(1.5, (opponent(1.6, 0.5),)))
    seen_taken = ElementState(
        present=False, taken=True, placed_at=None, carried_by_us=False, confidence=0.9
    )
    model.mark_element("crate", seen_taken, 0.9, Source.REMOTE)

    assert planner.updated(model.snapshot(2.0)) is planner


def test_updated_rebuilds_the_planner_when_we_build() -> None:
    arena = make_arena()
    model = world_of(arena)
    planner = planner_for(arena, model)
    model.add_construction(Construction("wall", box(0.9, 0.0, 1.1, 0.8)), 1.5)

    rebuilt = planner.updated(model.snapshot(2.0))

    assert rebuilt is not planner
    assert not rebuilt.navmap.is_free(Vec2(1.0, 0.5))


def test_updated_rebuilds_the_planner_when_a_construction_grows() -> None:
    arena = make_arena()
    model = world_of(arena)
    model.add_construction(Construction("wall", box(0.9, 0.0, 1.1, 0.3)), 0.5)
    planner = planner_for(arena, model)
    model.add_construction(Construction("wall", box(0.9, 0.0, 1.1, 0.8)), 1.5)

    rebuilt = planner.updated(model.snapshot(2.0))

    assert planner.navmap.is_free(Vec2(1.0, 0.5))
    assert not rebuilt.navmap.is_free(Vec2(1.0, 0.5))


def test_updated_rebuilds_the_planner_when_we_take_an_element() -> None:
    arena = make_arena(elements=[CRATE])
    model = world_of(arena)
    planner = planner_for(arena, model)
    taken = ElementState(
        present=False, taken=True, placed_at=None, carried_by_us=True, confidence=1.0
    )
    model.mark_element("crate", taken, 1.5, Source.STRATEGY)

    rebuilt = planner.updated(model.snapshot(2.0))

    assert not planner.navmap.is_free(Vec2(1.0, 0.5))
    assert rebuilt.navmap.is_free(Vec2(1.0, 0.5))


# Duration


@pytest.mark.parametrize(
    ("points", "expected"),
    [
        ((Vec2(0, 0),), 0.0),
        # 1 m at 0.5 m/s with 1 m/s2: 0.25 s to reach the speed, 0.25 s to stop, 1.5 s cruising.
        ((Vec2(0, 0), Vec2(1, 0)), 2.5),
        # 4 cm never reach the speed: a triangle, 0.2 s up and 0.2 s down.
        ((Vec2(0, 0), Vec2(0.04, 0)), 0.4),
        # Two straight lines and a quarter turn at pi rad/s.
        ((Vec2(0, 0), Vec2(1, 0), Vec2(1, 1)), 2.5 + 2.5 + 0.5),
    ],
)
def test_estimated_duration(points: tuple[Vec2, ...], expected: float) -> None:
    assert Path(points).estimated_duration(speed=0.5, accel=1.0, rot_speed=math.pi) == (
        pytest.approx(expected)
    )


# Properties on random tables


TABLE = 1.0
STEP = 0.02  # m, cell of the grid
# m, cells closer than this to an obstacle are not used. Above half a cell, the segment between
# two neighbour cells stays in the free space: each of its points is half a cell from one end.
TOLERANCE = 0.6 * STEP


# Obstacles in the middle of the table, the start on its left and the goal on its right: the
# paths go around them. Cells closer to the borders than the clearance plus TOLERANCE are left out.
obstacle = st.builds(
    lambda x, y, w, h: box(x, y, x + w, y + h),
    st.floats(0.25, 0.65),
    st.floats(0.0, 0.9),
    st.floats(0.02, 0.15),
    st.floats(0.02, 0.5),
)
track = st.builds(
    lambda x, y, r: opponent(x, y, r),
    st.floats(0.1, 0.9),
    st.floats(0.1, 0.9),
    st.floats(0.03, 0.1),
)
free_rows = st.integers(6, 43)
left_cell = st.tuples(st.integers(6, 12), free_rows)
right_cell = st.tuples(st.integers(37, 43), free_rows)


def centre(c: tuple[int, int]) -> Vec2:
    return Vec2((c[0] + 0.5) * STEP, (c[1] + 0.5) * STEP)


def grid_connects(free: BaseGeometry, start: tuple[int, int], goal: tuple[int, int]) -> bool:
    """Breadth-first search on the cells whose centre is at least TOLERANCE inside free."""
    n = int(TABLE / STEP)
    inner = free.buffer(-TOLERANCE)
    xs = (np.arange(n) + 0.5) * STEP
    gx, gy = np.meshgrid(xs, xs, indexing="ij")
    open_cells = np.asarray(shapely.covers(inner, shapely.points(gx, gy)), dtype=np.bool_)
    if not (open_cells[start] and open_cells[goal]):
        return False
    seen = {start}
    queue = deque([start])
    while queue:
        i, j = queue.popleft()
        if (i, j) == goal:
            return True
        for neighbour in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            inside = 0 <= neighbour[0] < n and 0 <= neighbour[1] < n
            if inside and neighbour not in seen and open_cells[neighbour]:
                seen.add(neighbour)
                queue.append(neighbour)
    return False


def shortest_length(free: BaseGeometry, start: Vec2, goal: Vec2) -> float:
    """Dijkstra on the visibility graph of all the vertices of free, built from scratch.

    Without turn penalty, a shortest path only turns at vertices: this is its exact length.
    """
    points = np.unique(shapely.get_coordinates(free), axis=0)
    points = np.concatenate([points, [[start.x, start.y], [goal.x, goal.y]]])
    i, j = np.triu_indices(len(points), 1)
    visible = shapely.covers(free, shapely.linestrings(np.stack([points[i], points[j]], axis=1)))
    neighbours: list[list[tuple[int, float]]] = [[] for _ in points]
    for a, b in zip(i[visible].tolist(), j[visible].tolist(), strict=True):
        weight = math.dist(points[a], points[b])
        neighbours[a].append((b, weight))
        neighbours[b].append((a, weight))
    source, target = len(points) - 2, len(points) - 1
    best = {source: 0.0}
    queue = [(0.0, source)]
    while queue:
        cost_here, node = heapq.heappop(queue)
        if node == target:
            return cost_here
        for neighbour, weight in neighbours[node]:
            if cost_here + weight < best.get(neighbour, math.inf):
                best[neighbour] = cost_here + weight
                heapq.heappush(queue, (cost_here + weight, neighbour))
    return math.inf


@settings(max_examples=200, deadline=None)
@given(
    obstacles=st.lists(obstacle, max_size=5),
    opponents=st.lists(track, max_size=2),
    start=left_cell,
    goal=right_cell,
)
def test_paths_are_clear_shortest_and_found_when_a_fine_grid_finds_one(
    obstacles: list[Polygon],
    opponents: list[Track],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> None:
    arena = make_arena(*obstacles, width=TABLE, depth=TABLE)
    planner = planner_for(arena)
    free = planner.navmap.free.difference(dynamic_obstacles(planner.clearance, opponents, []))
    assume(free.covers(Point(centre(start).x, centre(start).y)))

    result = planner.plan(centre(start), centre(goal), opponents=opponents)

    if isinstance(result, Path):
        assert result.points[0] == centre(start)
        assert result.points[-1] == centre(goal)
        assert_clear(planner, result, opponents=opponents)
        assert result.length <= shortest_length(free, centre(start), centre(goal)) + 1e-9
    if grid_connects(free, start, goal):
        assert isinstance(result, Path), result
