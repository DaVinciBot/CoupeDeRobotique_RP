"""The navigation on the 2027 table, with the settings of config/robot.json (TODO 5.2, ADR 0013).

The benchmarks measure on the machine that runs them: the target, below 10 ms on the Pi 5, is
checked on the Pi (TODO 5.2, 21.1).
"""

from pathlib import Path

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from dvb_brain.app.config import RobotConfig, parse_robot_config
from dvb_brain.app.files import load_file
from dvb_brain.domain.arena import Arena, Side, parse_arena
from dvb_brain.domain.geometry import Vec2
from dvb_brain.domain.planner import NoPath, NoPathReason, Planner
from dvb_brain.domain.planner import Path as PlannedPath
from dvb_brain.domain.world import Track, WorldModel, WorldSnapshot

EDITION = Path(__file__).parents[1]
ROBOT_CONFIG = EDITION.parents[1] / "config" / "robot.json"


@pytest.fixture(scope="module")
def arena() -> Arena:
    return load_file(EDITION / "arena.json", parse_arena)


@pytest.fixture(scope="module")
def config() -> RobotConfig:
    return load_file(ROBOT_CONFIG, parse_robot_config)


@pytest.fixture(scope="module")
def world(arena: Arena, config: RobotConfig) -> WorldSnapshot:
    return WorldModel(arena.elements, config.world, now=0.0).snapshot(0.0)


def centre_of(arena: Arena, zone_id: str) -> Vec2:
    centroid = arena.zone(zone_id).polygon.centroid
    return Vec2(centroid.x, centroid.y)


def table_centre(arena: Arena) -> Vec2:
    return Vec2(arena.width / 2, arena.depth / 2)


def planner(arena: Arena, config: RobotConfig, world: WorldSnapshot, side: Side) -> Planner:
    return Planner(arena, side, config.geometry, config.navigation, world)


def opponent(x: float, y: float) -> Track:
    return Track(id=1, center=Vec2(x, y), radius=0.2, velocity=Vec2(0, 0), confirmed=True)


@pytest.mark.parametrize("side", [Side.BLUE, Side.YELLOW])
def test_robot_goes_from_its_throne_room_to_the_centre_and_back(
    arena: Arena, config: RobotConfig, world: WorldSnapshot, side: Side
) -> None:
    navigation = planner(arena, config, world, side)
    throne_room = centre_of(arena, f"{side.value}_throne_room")

    assert isinstance(navigation.plan(throne_room, table_centre(arena)), PlannedPath)
    assert isinstance(navigation.plan(table_centre(arena), throne_room), PlannedPath)


def test_opponent_castle_is_out_of_reach(
    arena: Arena, config: RobotConfig, world: WorldSnapshot
) -> None:
    # RG H.4: entering an exclusive area of the opponent is a forfeit.
    navigation = planner(arena, config, world, Side.BLUE)

    result = navigation.plan(
        centre_of(arena, "blue_throne_room"), centre_of(arena, "yellow_throne_room")
    )

    assert result == NoPath(NoPathReason.GOAL_IN_OBSTACLE)


def test_benchmark_static_part(
    benchmark: BenchmarkFixture, arena: Arena, config: RobotConfig, world: WorldSnapshot
) -> None:
    # Rebuilt each time we take an element or build (ADR 0013).
    benchmark(planner, arena, config, world, Side.BLUE)


def test_benchmark_request_with_two_opponents(
    benchmark: BenchmarkFixture, arena: Arena, config: RobotConfig, world: WorldSnapshot
) -> None:
    navigation = planner(arena, config, world, Side.BLUE)
    # One opponent on each side of the direct line: the path goes around the upper one.
    opponents = [opponent(2.0, 0.6), opponent(1.9, 1.5)]

    start = centre_of(arena, "blue_throne_room")

    result = benchmark(navigation.plan, start, Vec2(1.1, 1.6), opponents)

    assert isinstance(result, PlannedPath)
    assert len(result.points) > 2
