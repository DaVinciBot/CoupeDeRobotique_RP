import copy
import math
from pathlib import Path
from typing import Any

import msgspec
import pytest
from shapely import Polygon

from dvb_brain.domain.arena import Arena, Side, Zone, ZoneKind, load_arena, parse_arena
from dvb_brain.domain.geometry import Vec2
from dvb_brain.domain.json_schema import SchemaError

TEMPLATE_ARENA = Path(__file__).parents[4] / "editions" / "_template" / "arena.json"


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
        make_zone("blue_start", start, Side.BLUE, square(0.0, 0.0, 0.4), "yellow_start"),
        make_zone("yellow_start", start, Side.YELLOW, square(2.6, 0.0, 0.4), "blue_start"),
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
        (Vec2(0.2, 0.2), True),
        (Vec2(0.4, 0.2), True),  # on the boundary
        (Vec2(0.0, 0.0), True),  # on a corner
        (Vec2(0.41, 0.2), False),
        (Vec2(2.8, 0.2), False),  # in the other start zone
    ],
)
def test_contains(arena: Arena, point: Vec2, expected: bool) -> None:
    assert arena.contains("blue_start", point) is expected


@pytest.mark.parametrize(
    ("footprint", "expected"),
    [
        ([Vec2(0.1, 0.1), Vec2(0.3, 0.1), Vec2(0.3, 0.3), Vec2(0.1, 0.3)], True),
        ([Vec2(0.1, 0.0), Vec2(0.4, 0.0), Vec2(0.4, 0.3), Vec2(0.1, 0.3)], True),  # in a corner
        ([Vec2(0.3, 0.1), Vec2(0.5, 0.1), Vec2(0.5, 0.3), Vec2(0.3, 0.3)], False),  # across
        ([Vec2(1.0, 1.0), Vec2(1.2, 1.0), Vec2(1.2, 1.2)], False),  # outside
    ],
)
def test_polygon_inside(arena: Arena, footprint: list[Vec2], expected: bool) -> None:
    assert arena.polygon_inside("blue_start", footprint) is expected


# arena.json loading


def valid_document() -> dict[str, Any]:
    start = ["start", "end", "exclusive_opponent"]
    size = {"length_mm": 200, "width_mm": 100, "height_mm": 50}
    return {
        "width_mm": 3000,
        "depth_mm": 2000,
        "border_thickness_mm": 22,
        "border_height_mm": 70,
        "aruco_tags": {"blue": [1, 2], "yellow": [6, 7], "elements": {"crate": [20]}},
        "zones": [
            {
                "id": "blue_start",
                "kinds": start,
                "owner": "blue",
                "polygon_mm": [[0, 0], [400, 0], [400, 400], [0, 400]],
                "tags": ["dock"],
                "mirror_id": "yellow_start",
                "robot_poses": [{"x_mm": 200, "y_mm": 200, "theta_deg": 0}],
            },
            {
                "id": "yellow_start",
                "kinds": start,
                "owner": "yellow",
                "polygon_mm": [[2600, 0], [3000, 0], [3000, 400], [2600, 400]],
                "tags": ["dock"],
                "mirror_id": "blue_start",
                "robot_poses": [{"x_mm": 2800, "y_mm": 200, "theta_deg": 180}],
            },
            {
                "id": "middle",
                "kinds": ["obstacle"],
                "owner": None,
                "polygon_mm": [[1400, 900], [1600, 900], [1600, 1100], [1400, 1100]],
                "height_mm": 120,
                "mirror_id": "middle",
            },
        ],
        "elements": [
            {
                "id": "crate_blue",
                "kind": "crate",
                "pose": {"x_mm": 700, "y_mm": 1500, "theta_deg": 90},
                "size": size,
                "mirror_id": "crate_yellow",
            },
            {
                "id": "crate_yellow",
                "kind": "crate",
                "pose": {"x_mm": 2300, "y_mm": 1500, "theta_deg": 90},
                "size": size,
                "mirror_id": "crate_blue",
            },
        ],
    }


def encode(document: dict[str, Any]) -> bytes:
    return msgspec.json.encode(document)


def test_parse_arena_converts_to_si() -> None:
    arena = parse_arena(encode(valid_document()))

    assert (arena.width, arena.depth) == (3.0, 2.0)
    assert arena.border_thickness == pytest.approx(0.022)
    assert arena.border_height == pytest.approx(0.07)
    assert arena.aruco_tags == {Side.BLUE: frozenset({1, 2}), Side.YELLOW: frozenset({6, 7})}
    assert arena.element_aruco_tags == {"crate": frozenset({20})}
    assert list(arena.zones) == ["blue_start", "yellow_start", "middle"]
    assert list(arena.elements) == ["crate_blue", "crate_yellow"]


def test_parse_arena_reads_zones() -> None:
    arena = parse_arena(encode(valid_document()))

    start = arena.zone("blue_start")
    assert start.kinds == {ZoneKind.START, ZoneKind.END, ZoneKind.EXCLUSIVE_OPPONENT}
    assert start.owner is Side.BLUE
    assert start.polygon.bounds == pytest.approx((0.0, 0.0, 0.4, 0.4))
    assert start.tags == {"dock"}
    assert start.mirror_id == "yellow_start"
    middle = arena.zone("middle")
    assert middle.owner is None
    assert middle.height == pytest.approx(0.12)
    assert middle.tags == frozenset()
    assert start.height == 0.0


def test_parse_arena_reads_robot_poses() -> None:
    arena = parse_arena(encode(valid_document()))

    (pose,) = arena.zone("yellow_start").robot_poses
    assert (pose.x, pose.y, pose.theta) == pytest.approx((2.8, 0.2, math.pi))
    assert arena.zone("middle").robot_poses == ()


def test_parse_arena_reads_a_circle() -> None:
    document = valid_document()
    del document["zones"][2]["polygon_mm"]
    document["zones"][2]["circle_mm"] = {"x": 1500, "y": 1000, "radius": 100}

    polygon = parse_arena(encode(document)).zone("middle").polygon

    assert polygon.bounds == pytest.approx((1.4, 0.9, 1.6, 1.1))
    assert polygon.area == pytest.approx(math.pi * 0.1**2, rel=1e-2)


def test_parse_arena_reads_a_rotated_rectangle() -> None:
    document = valid_document()
    del document["zones"][2]["polygon_mm"]
    rect = {"x": 1500, "y": 1000, "length": 400, "width": 200, "theta_deg": 90}
    document["zones"][2]["rect_mm"] = rect

    polygon = parse_arena(encode(document)).zone("middle").polygon

    assert polygon.bounds == pytest.approx((1.4, 0.8, 1.6, 1.2))
    assert polygon.area == pytest.approx(0.08)


def test_parse_arena_rectangle_at_45_degrees() -> None:
    document = valid_document()
    del document["zones"][2]["polygon_mm"]
    rect = {"x": 1500, "y": 1000, "length": 400, "width": 200, "theta_deg": 45}
    document["zones"][2]["rect_mm"] = rect

    polygon = parse_arena(encode(document)).zone("middle").polygon

    half_diagonal = 0.3 / math.sqrt(2)  # (length + width) / 2 projected on an axis
    expected = (1.5 - half_diagonal, 1.0 - half_diagonal, 1.5 + half_diagonal, 1.0 + half_diagonal)
    assert polygon.bounds == pytest.approx(expected)
    assert polygon.area == pytest.approx(0.08)


def test_parse_arena_reads_elements() -> None:
    element = parse_arena(encode(valid_document())).elements["crate_blue"]

    assert element.kind == "crate"
    assert (element.pose.x, element.pose.y) == pytest.approx((0.7, 1.5))
    assert element.pose.theta == pytest.approx(math.pi / 2)
    assert (element.size.length, element.size.width, element.size.height) == pytest.approx(
        (0.2, 0.1, 0.05)
    )
    assert element.mirror_id == "crate_yellow"


def test_parse_arena_normalizes_element_heading() -> None:
    document = valid_document()
    document["elements"][0]["pose"]["theta_deg"] = 270

    element = parse_arena(encode(document)).elements["crate_blue"]

    assert element.pose.theta == pytest.approx(-math.pi / 2)


DELETE = object()


@pytest.mark.parametrize(
    ("location", "value", "expected"),
    [
        (("width_mm",), -1, ["$.width_mm: Expected `float` > 0.0, got -1"]),
        (("depth_mm",), "big", ["$.depth_mm: Expected `float`, got 'big'"]),
        (
            ("zones", 0, "kinds"),
            ["start", "lake"],
            ["$.zones[0].kinds[1]: Invalid enum value 'lake'"],
        ),
        (("zones", 0, "kinds"), [], ["$.zones[0].kinds:", "got []"]),
        (("zones", 0, "owner"), "green", ["$.zones[0].owner:", "'green'"]),
        (("zones", 1, "colour"), "red", ["$.zones[1]:", "colour"]),
        (("zones", 2, "owner"), DELETE, ["$.zones[2]:", "owner"]),
        (("zones", 2, "height_mm"), -5, ["$.zones[2].height_mm:", "got -5"]),
        (("zones", 2, "id"), "blue_start", ["$.zones[2].id: duplicate id", "got 'blue_start'"]),
        (("zones", 2, "mirror_id"), "elsewhere", ["$.zones[2].mirror_id:", "got 'elsewhere'"]),
        (("zones", 0, "mirror_id"), "middle", ["$.zones[0].mirror_id: not mutual", "'middle'"]),
        (("zones", 0, "polygon_mm"), [[0, 0], [400, 0]], ["$.zones[0].polygon_mm:", "[400, 0]"]),
        (
            ("zones", 0, "polygon_mm"),
            [[0, 0], [400, 400], [400, 0], [0, 400]],
            ["$.zones[0].polygon_mm: invalid polygon", "Self-intersection"],
        ),
        (
            ("zones", 2, "kinds"),
            ["exclusive_opponent"],
            ["$.zones[2].owner: exclusive_opponent needs an owner", "got None"],
        ),
        (
            ("zones", 2, "polygon_mm"),
            DELETE,
            ["$.zones[2]: needs exactly one of polygon_mm, circle_mm, rect_mm", "got []"],
        ),
        (
            ("zones", 2, "circle_mm"),
            {"x": 1500, "y": 1000, "radius": 100},
            ["$.zones[2]: needs exactly one", "got ['polygon_mm', 'circle_mm']"],
        ),
        (
            ("zones", 2, "circle_mm"),
            {"x": 1500, "y": 1000, "radius": 0},
            ["$.zones[2].circle_mm.radius:", "got 0"],
        ),
        (
            ("zones", 2, "rect_mm"),
            {"x": 1500, "y": 1000, "length": 400, "width": 200},
            ["$.zones[2].rect_mm:", "theta_deg"],
        ),
        (("elements", 1, "id"), "crate_blue", ["$.elements[1].id: duplicate id"]),
        (("elements", 0, "mirror_id"), "middle", ["$.elements[0].mirror_id:", "got 'middle'"]),
        (("elements", 0, "size", "length_mm"), 0, ["$.elements[0].size.length_mm:", "got 0"]),
        (("elements", 0, "pose", "theta_deg"), DELETE, ["$.elements[0].pose:", "theta_deg"]),
        (("aruco_tags", "yellow"), DELETE, ["$.aruco_tags:", "yellow"]),
        (
            ("aruco_tags", "elements"),
            {"barrel": [20]},
            ["$.aruco_tags.elements: no element of this kind", "got 'barrel'"],
        ),
        (
            ("aruco_tags", "elements"),
            {"crate": [-1]},
            ["$.aruco_tags.elements[...][0]: Expected `int` >= 0"],  # msgspec hides dict keys
        ),
        (
            ("zones", 0, "robot_poses"),
            [{"x_mm": 200, "y_mm": 200}],
            ["$.zones[0].robot_poses[0]:", "theta_deg"],
        ),
        (("aruco_tags", "blue"), [1, -2], ["$.aruco_tags.blue", "-2"]),
    ],
)
def test_parse_arena_error_names_field_and_value(
    location: tuple[str | int, ...], value: object, expected: list[str]
) -> None:
    document = copy.deepcopy(valid_document())
    *parents, last = location
    node: Any = document
    for key in parents:
        node = node[key]
    if value is DELETE:
        del node[last]
    else:
        node[last] = value

    with pytest.raises(SchemaError) as error:
        parse_arena(encode(document))

    for text in expected:
        assert text in str(error.value)


def test_parse_arena_rejects_invalid_json() -> None:
    with pytest.raises(SchemaError, match="invalid JSON"):
        parse_arena(encode(valid_document())[:-5])


def test_load_arena_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "arena.json"
    path.write_bytes(encode(valid_document()))

    assert list(load_arena(path).zones) == ["blue_start", "yellow_start", "middle"]


def test_load_arena_error_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "arena.json"
    document = valid_document()
    document["width_mm"] = 0
    path.write_bytes(encode(document))

    with pytest.raises(SchemaError) as error:
        load_arena(path)

    assert str(error.value).startswith(f"{path}: $.width_mm:")


def test_template_arena_loads() -> None:
    arena = load_arena(TEMPLATE_ARENA)

    assert (arena.width, arena.depth) == (3.0, 2.0)
    assert arena.zones == {}
    assert arena.element_aruco_tags == {}
