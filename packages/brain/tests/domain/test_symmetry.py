import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from shapely import Polygon

from dvb_brain.domain.arena import Arena, ElementSpec, Side, Size, Zone, ZoneKind, load_arena
from dvb_brain.domain.geometry import Pose, Vec2, angle_diff
from dvb_brain.domain.json_schema import SchemaError
from dvb_brain.domain.symmetry import (
    check_symmetry,
    mirror_element_id,
    mirror_point,
    mirror_polygon,
    mirror_pose,
    mirror_side,
    mirror_zone_id,
)

WIDTH = 3.0
TEMPLATE_ARENA = Path(__file__).parents[4] / "editions" / "_template" / "arena.json"

angles = st.floats(min_value=-100.0, max_value=100.0)
xs = st.floats(min_value=0.0, max_value=WIDTH)
ys = st.floats(min_value=0.0, max_value=2.0)
points = st.builds(Vec2, xs, ys)
poses = st.builds(Pose, xs, ys, angles)
triangles = st.lists(st.tuples(xs, ys), min_size=3, max_size=3).map(Polygon)


def square(x: float, y: float, side: float) -> Polygon:
    return Polygon([(x, y), (x + side, y), (x + side, y + side), (x, y + side)])


def make_zone(
    zone_id: str, kinds: set[ZoneKind], owner: Side | None, polygon: Polygon, mirror_id: str
) -> Zone:
    return Zone(zone_id, frozenset(kinds), owner, polygon, 0.0, frozenset(), mirror_id)


def make_element(element_id: str, pose: Pose, mirror_id: str) -> ElementSpec:
    return ElementSpec(element_id, "block", pose, Size(0.3, 0.1, 0.1), mirror_id)


def make_arena(zones: list[Zone], elements: list[ElementSpec]) -> Arena:
    return Arena(
        width=WIDTH,
        depth=2.0,
        border_thickness=0.022,
        border_height=0.07,
        zones={zone.id: zone for zone in zones},
        elements={element.id: element for element in elements},
        aruco_tags={Side.BLUE: frozenset({1}), Side.YELLOW: frozenset({6})},
    )


@pytest.fixture
def arena() -> Arena:
    start = {ZoneKind.START, ZoneKind.END, ZoneKind.EXCLUSIVE_OPPONENT}
    return make_arena(
        zones=[
            make_zone("blue_start", start, Side.BLUE, square(0.0, 0.0, 0.4), "yellow_start"),
            make_zone("yellow_start", start, Side.YELLOW, square(2.6, 0.0, 0.4), "blue_start"),
            make_zone("middle", {ZoneKind.FORBIDDEN}, None, square(1.4, 0.9, 0.2), "middle"),
        ],
        elements=[
            make_element("blue_block", Pose(0.5, 1.0, 0.0), "yellow_block"),
            make_element("yellow_block", Pose(2.5, 1.0, math.pi), "blue_block"),
        ],
    )


def assert_same_pose(actual: Pose, expected: Pose) -> None:
    assert actual.x == pytest.approx(expected.x, abs=1e-9)
    assert actual.y == pytest.approx(expected.y, abs=1e-9)
    assert angle_diff(actual.theta, expected.theta) == pytest.approx(0.0, abs=1e-9)


def test_mirror_side_swaps_sides() -> None:
    assert mirror_side(Side.BLUE) is Side.YELLOW
    assert mirror_side(Side.YELLOW) is Side.BLUE


def test_mirror_side_keeps_shared_owner() -> None:
    assert mirror_side(None) is None


def test_mirror_point_flips_x() -> None:
    assert mirror_point(Vec2(0.5, 0.3), WIDTH) == Vec2(2.5, 0.3)


@pytest.mark.parametrize(
    ("theta", "expected"),
    [
        (0.0, math.pi),
        (math.pi, 0.0),
        (math.pi / 2, math.pi / 2),
        (-math.pi / 2, -math.pi / 2),
        (math.pi / 4, 3 * math.pi / 4),
        (-math.pi / 4, -3 * math.pi / 4),
    ],
)
def test_mirror_pose(theta: float, expected: float) -> None:
    assert_same_pose(mirror_pose(Pose(0.5, 0.3, theta), WIDTH), Pose(2.5, 0.3, expected))


def test_mirror_pose_heading_is_normalized() -> None:
    assert -math.pi < mirror_pose(Pose(0.5, 0.3, -3.0), WIDTH).theta <= math.pi


@given(points)
def test_mirror_point_twice_is_identity(point: Vec2) -> None:
    twice = mirror_point(mirror_point(point, WIDTH), WIDTH)
    assert twice.x == pytest.approx(point.x, abs=1e-9)
    assert twice.y == point.y


@given(poses)
def test_mirror_pose_twice_is_identity(pose: Pose) -> None:
    assert_same_pose(mirror_pose(mirror_pose(pose, WIDTH), WIDTH), pose)


@given(triangles)
def test_mirror_polygon_keeps_area(polygon: Polygon) -> None:
    assert mirror_polygon(polygon, WIDTH).area == pytest.approx(polygon.area, abs=1e-9)


@given(triangles)
def test_mirror_polygon_twice_is_identity(polygon: Polygon) -> None:
    twice = mirror_polygon(mirror_polygon(polygon, WIDTH), WIDTH)
    assert twice.hausdorff_distance(polygon) == pytest.approx(0.0, abs=1e-9)


def test_mirror_polygon_flips_around_the_middle() -> None:
    mirrored = mirror_polygon(square(0.0, 0.0, 0.4), WIDTH)
    assert mirrored.hausdorff_distance(square(2.6, 0.0, 0.4)) == pytest.approx(0.0, abs=1e-9)


def test_mirror_zone_id(arena: Arena) -> None:
    assert mirror_zone_id(arena, "blue_start") == "yellow_start"
    assert mirror_zone_id(arena, "yellow_start") == "blue_start"


def test_mirror_zone_id_on_the_axis_is_itself(arena: Arena) -> None:
    assert mirror_zone_id(arena, "middle") == "middle"


def test_mirror_element_id(arena: Arena) -> None:
    assert mirror_element_id(arena, "blue_block") == "yellow_block"
    assert mirror_element_id(arena, "yellow_block") == "blue_block"


def test_mirror_ids_unknown_raise_key_error(arena: Arena) -> None:
    with pytest.raises(KeyError, match="nowhere"):
        mirror_zone_id(arena, "nowhere")
    with pytest.raises(KeyError, match="nowhere"):
        mirror_element_id(arena, "nowhere")


def test_each_zone_has_a_mirror_of_same_area(arena: Arena) -> None:
    for zone in arena.zones.values():
        mirror = arena.zone(mirror_zone_id(arena, zone.id))
        assert mirror.polygon.area == pytest.approx(zone.polygon.area)


def test_check_symmetry_accepts_symmetric_arena(arena: Arena) -> None:
    check_symmetry(arena)


def test_check_symmetry_accepts_template_arena() -> None:
    check_symmetry(load_arena(TEMPLATE_ARENA))


def test_check_symmetry_accepts_element_heading_written_modulo_pi(arena: Arena) -> None:
    turned = replace(arena.elements["yellow_block"], pose=Pose(2.5, 1.0, 0.0))
    check_symmetry(with_element(arena, turned))


def with_zone(arena: Arena, zone: Zone) -> Arena:
    return replace(arena, zones={**arena.zones, zone.id: zone})


def with_element(arena: Arena, element: ElementSpec) -> Arena:
    return replace(arena, elements={**arena.elements, element.id: element})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"polygon": square(2.5, 0.0, 0.4)}, "polygons are not symmetric"),
        ({"owner": Side.BLUE}, "owners"),
        ({"kinds": frozenset({ZoneKind.START})}, "kinds, height or tags differ"),
        ({"height": 0.1}, "kinds, height or tags differ"),
        ({"tags": frozenset({"extra"})}, "kinds, height or tags differ"),
    ],
)
def test_check_symmetry_rejects_bad_zone_mirror(
    arena: Arena, change: dict[str, Any], message: str
) -> None:
    bad = replace(arena.zone("yellow_start"), **change)
    with pytest.raises(SchemaError, match=f"zone 'blue_start'.*'yellow_start'.*{message}"):
        check_symmetry(with_zone(arena, bad))


def test_check_symmetry_rejects_asymmetric_zone_on_the_axis(arena: Arena) -> None:
    bad = replace(arena.zone("middle"), polygon=square(1.0, 0.9, 0.2))
    with pytest.raises(SchemaError, match=r"zone 'middle'.*polygons are not symmetric"):
        check_symmetry(with_zone(arena, bad))


def test_check_symmetry_rejects_owned_zone_on_the_axis(arena: Arena) -> None:
    bad = replace(arena.zone("middle"), owner=Side.BLUE)
    with pytest.raises(SchemaError, match=r"zone 'middle'.*owners"):
        check_symmetry(with_zone(arena, bad))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"pose": Pose(2.4, 1.0, math.pi)}, "positions are not symmetric"),
        ({"pose": Pose(2.5, 1.0, math.pi / 2)}, "headings are not symmetric"),
        ({"kind": "other"}, "kind or size differ"),
        ({"size": Size(0.3, 0.1, 0.2)}, "kind or size differ"),
    ],
)
def test_check_symmetry_rejects_bad_element_mirror(
    arena: Arena, change: dict[str, Any], message: str
) -> None:
    bad = replace(arena.elements["yellow_block"], **change)
    with pytest.raises(SchemaError, match=f"element 'blue_block'.*'yellow_block'.*{message}"):
        check_symmetry(with_element(arena, bad))
