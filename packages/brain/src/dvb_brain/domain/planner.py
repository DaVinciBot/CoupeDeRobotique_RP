"""Planner: visibility graph and A* on the navigation map (architecture 8.2, ADR 0013).

The nodes are the corners of the inflated obstacles; two nodes are linked when the segment
between them stays in the free space, boundary included. The static part, corners of the static
obstacles and segments between them, is computed once per Planner. Each request adds the start,
the goal and the corners of the dynamic obstacles, and drops the static segments they cut.
"""

import heapq
import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum, auto
from itertools import pairwise
from typing import cast

import numpy as np
import shapely
from numpy.typing import NDArray
from shapely import LineString, Point, Polygon, STRtree
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from dvb_brain.domain.arena import Arena, Side
from dvb_brain.domain.geometry import Vec2, angle_diff
from dvb_brain.domain.navmap import (
    NavigationSettings,
    NavMap,
    dynamic_obstacles,
    elements_in_place,
)
from dvb_brain.domain.robot import RobotGeometry
from dvb_brain.domain.world import Track, WorldSnapshot

# A start in an obstacle leaves it for a point this far inside the free space: on its very
# boundary, the point falls outside about one time in five, by rounding (ADR 0013).
_EXIT_INSET = 1e-4  # m

# DE-9IM pattern: the interior of a dynamic obstacle meets the interior of a segment.
_CUTS = "T********"

type _Points = NDArray[np.float64]  # shape (n, 2), in m


class NoPathReason(StrEnum):
    GOAL_IN_OBSTACLE = auto()  # the goal is in an inflated obstacle, an opponent included
    UNREACHABLE = auto()  # no path in the free space


@dataclass(frozen=True, slots=True)
class NoPath:
    reason: NoPathReason


@dataclass(frozen=True, slots=True)
class Path:
    """Straight lines from the start to the goal; the robot stops and turns at each point."""

    points: tuple[Vec2, ...]

    @property
    def length(self) -> float:
        return sum(((b - a).norm() for a, b in pairwise(self.points)), 0.0)

    def estimated_duration(self, speed: float, accel: float, rot_speed: float) -> float:
        """Time to run the path, in s: a speed trapezoid per line, a rotation at each inner point.

        The rotation before the first line and the final heading are not counted (ADR 0013).
        """
        lines = sum(_line_duration((b - a).norm(), speed, accel) for a, b in pairwise(self.points))
        turns = sum(
            abs(angle_diff((c - b).angle(), (b - a).angle())) / rot_speed
            for a, b, c in zip(self.points, self.points[1:], self.points[2:], strict=False)
        )
        return lines + turns


class Planner:
    """Paths of our robot for one side. The static part is computed once (architecture 8.2)."""

    def __init__(
        self,
        arena: Arena,
        side: Side,
        geometry: RobotGeometry,
        settings: NavigationSettings,
        world: WorldSnapshot,
    ) -> None:
        self._arena = arena
        self._side = side
        self._geometry = geometry
        self._settings = settings
        self.clearance = geometry.radius + settings.margin
        self.navmap = NavMap.build(arena, side, self.clearance, world)
        self._constructions = world.our_constructions
        self._elements_in_place = elements_in_place(world)
        self._nodes = _corners(self.navmap.free, convex=False)
        i, j = np.triu_indices(len(self._nodes), 1)
        lines = _segments(self._nodes[i], self._nodes[j])
        free = shapely.covers(self.navmap.free, lines)
        self._edges = np.stack([i[free], j[free]], axis=1)
        self._edge_lines = lines[free]
        self._edge_tree = STRtree(self._edge_lines)

    def updated(self, world: WorldSnapshot) -> Planner:
        """Return this planner while the static obstacles stay the same, else a new one.

        The mapping of our constructions is replaced at each change, a construction that grows
        included (ADR 0012); the elements in place change when we take one (ADR 0013).
        """
        if (
            world.our_constructions is self._constructions
            and elements_in_place(world) == self._elements_in_place
        ):
            return self
        return Planner(self._arena, self._side, self._geometry, self._settings, world)

    def plan(
        self,
        start: Vec2,
        goal: Vec2,
        opponents: Iterable[Track] = (),
        forbidden: Iterable[Polygon] = (),
    ) -> Path | NoPath:
        """Return the cheapest path from start to goal: length plus a penalty per turn.

        The path always begins at start, even in an obstacle: it then leaves it first (ADR 0013).
        forbidden are the conditional forbidden zones of the rules (MatchRules.forbidden_zones,
        TODO 7.2).
        """
        dynamic = dynamic_obstacles(self.clearance, opponents, forbidden)
        shapely.prepare(dynamic)
        goal_point = Point(goal.x, goal.y)
        if not self.navmap.free.covers(goal_point) or dynamic.contains_properly(goal_point):
            return NoPath(NoPathReason.GOAL_IN_OBSTACLE)
        if start == goal:
            return Path((start,))
        exit_points = self._exit(start, dynamic)
        if exit_points is None:
            return NoPath(NoPathReason.UNREACHABLE)

        source = exit_points[-1] if exit_points else start
        nodes, edges = self._graph(source, goal, dynamic)
        weights = np.hypot(*(nodes[edges[:, 0]] - nodes[edges[:, 1]]).T)
        weights += self._settings.turn_penalty
        route = _a_star(nodes, edges, weights, source=len(nodes) - 2, target=len(nodes) - 1)
        if route is None:
            return NoPath(NoPathReason.UNREACHABLE)
        inner = (Vec2(float(nodes[k, 0]), float(nodes[k, 1])) for k in route[1:-1])
        # An exit point within the margin of the start is dropped: the robot goes straight on, and
        # each point of its first line is then within the margin of the line from that exit
        # point, so at least its radius away from any obstacle (ADR 0013).
        kept = (p for p in exit_points if (p - start).norm() > self._settings.margin)
        return Path((start, *kept, *inner, goal))

    def _exit(self, start: Vec2, dynamic: BaseGeometry) -> tuple[Vec2, ...] | None:
        """Return the points that take start out of the obstacles: none when it is free.

        Out of a static obstacle by the nearest free point: each point of that line is closer to
        the free space than start, never deeper in an obstacle. Then out of a dynamic obstacle by
        the nearest point clear of it, but only along a line in the static free space: crossing
        an element or an exclusive area of the opponent (RG H.4) is worse than waiting. None when
        there is no such way out (ADR 0013).
        """
        points: list[Vec2] = []
        here = start
        if not self.navmap.free.covers(Point(here.x, here.y)):
            nearest = _nearest(self.navmap.free, here)
            if nearest is None:
                return None
            here = nearest
            points.append(here)
        if dynamic.contains_properly(Point(here.x, here.y)):
            out = _nearest(self.navmap.free.difference(dynamic), here)
            if out is None or not self.navmap.free.covers(_line(here, out)):
                return None
            points.append(out)
        return tuple(points)

    def _graph(
        self, start: Vec2, goal: Vec2, dynamic: BaseGeometry
    ) -> tuple[_Points, NDArray[np.intp]]:
        """Return the nodes, start and goal last, and the free segments between them."""
        ends = np.array([[start.x, start.y], [goal.x, goal.y]])
        edges = self._edges
        new_nodes = ends
        if not dynamic.is_empty:
            corners = _corners(dynamic, convex=True)
            corners = corners[shapely.covers(self.navmap.free, shapely.points(corners))]
            new_nodes = np.concatenate([corners, ends])
            near = self._edge_tree.query(dynamic, predicate="intersects")
            cut = near[shapely.relate_pattern(dynamic, self._edge_lines[near], _CUTS)]
            edges = np.delete(edges, cut, axis=0)
        nodes = np.concatenate([self._nodes, new_nodes])
        i, j = np.triu_indices(len(nodes), 1)
        new = j >= len(self._nodes)
        i, j = i[new], j[new]
        lines = _segments(nodes[i], nodes[j])
        free = shapely.covers(self.navmap.free, lines)
        if not dynamic.is_empty:
            free &= ~shapely.relate_pattern(dynamic, lines, _CUTS)
        return nodes, np.concatenate([edges, np.stack([i[free], j[free]], axis=1)])


def _nearest(region: BaseGeometry, point: Vec2) -> Vec2 | None:
    """Return the point of region nearest to point, a little inside it, or None if empty."""
    inner = region.buffer(-_EXIT_INSET)
    if inner.is_empty:
        return None
    nearest = nearest_points(inner, Point(point.x, point.y))[0]
    return Vec2(nearest.x, nearest.y)


def _line(a: Vec2, b: Vec2) -> LineString:
    return LineString([(a.x, a.y), (b.x, b.y)])


def _line_duration(distance: float, speed: float, accel: float) -> float:
    """Time of a straight line from stop to stop with a speed trapezoid, in s."""
    if distance >= speed * speed / accel:
        return distance / speed + speed / accel
    return 2.0 * math.sqrt(distance / accel)  # a triangle: the speed is never reached


def _corners(shape: BaseGeometry, convex: bool) -> _Points:
    """Return the convex, or the reflex, corners of the polygons of shape."""
    corners: list[_Points] = []
    # Exterior rings counter-clockwise, holes clockwise: the inside is always on the left, and
    # a left turn is a convex corner.
    for polygon in shapely.get_parts(shapely.orient_polygons(shape)):
        if not isinstance(polygon, Polygon):
            continue
        for ring in (polygon.exterior, *polygon.interiors):
            points = shapely.get_coordinates(ring)[:-1]
            before = points - np.roll(points, 1, axis=0)
            after = np.roll(points, -1, axis=0) - points
            turn = before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0]
            corners.append(points[turn > 0] if convex else points[turn < 0])
    return np.concatenate(corners) if corners else np.empty((0, 2))


def _segments(a: _Points, b: _Points) -> NDArray[np.object_]:
    """Return the segments from each point of a to the point of b with the same index."""
    return cast(NDArray[np.object_], shapely.linestrings(np.stack([a, b], axis=1)))


def _a_star(
    nodes: _Points,
    edges: NDArray[np.intp],
    weights: NDArray[np.float64],
    source: int,
    target: int,
) -> list[int] | None:
    """Return the cheapest route from source to target, as node indices, or None.

    The heuristic is the straight-line distance: weights are lengths plus a penalty, never less.
    """
    neighbours: list[list[tuple[int, float]]] = [[] for _ in range(len(nodes))]
    for (a, b), weight in zip(edges.tolist(), weights.tolist(), strict=True):
        neighbours[int(a)].append((int(b), float(weight)))
        neighbours[int(b)].append((int(a), float(weight)))
    heuristic = np.hypot(*(nodes - nodes[target]).T).tolist()
    best = {source: 0.0}
    parent = {source: source}
    queue = [(heuristic[source], 0.0, source)]
    done: set[int] = set()
    while queue:
        _, cost, node = heapq.heappop(queue)
        if node == target:
            route = [target]
            while route[-1] != source:
                route.append(parent[route[-1]])
            return route[::-1]
        if node in done:
            continue
        done.add(node)
        for neighbour, weight in neighbours[node]:
            reached = cost + weight
            if reached < best.get(neighbour, math.inf):
                best[neighbour] = reached
                parent[neighbour] = node
                heapq.heappush(queue, (reached + heuristic[neighbour], reached, neighbour))
    return None
