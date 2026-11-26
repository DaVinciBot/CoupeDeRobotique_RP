import copy
import math
from pathlib import Path
from typing import Any

import msgspec
import pytest

from dvb_brain.app.config import parse_robot_config
from dvb_brain.app.files import load_file
from dvb_brain.domain.decoding import SchemaError
from dvb_brain.domain.navmap import NavigationSettings
from dvb_brain.domain.robot import RobotGeometry
from dvb_brain.domain.world import WorldLifetimes

ROBOT_CONFIG = Path(__file__).parents[4] / "config" / "robot.json"


def valid_document() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "cdr.robot",
        "geometry": {"radius_mm": 250, "rear_mm": 140},
        "navigation": {
            "margin_mm": 20,
            "turn_penalty_mm": 100,
            "reverse_max_distance_mm": 250,
            "reverse_min_gain_deg": 30,
            "reverse_max_speed_mps": 0.15,
        },
        "world": {
            "lidar_tracks_ttl_s": 0.25,
            "remote_ttl_s": 0.5,
            "element_seen_ttl_s": 3,
            "odometry_history_s": 1.5,
        },
    }


def encode(document: dict[str, Any]) -> bytes:
    return msgspec.json.encode(document)


def test_parse_robot_config_gives_the_world_lifetimes() -> None:
    config = parse_robot_config(encode(valid_document()))

    assert config.world == WorldLifetimes(
        lidar_tracks=0.25, remote=0.5, element_seen=3.0, odometry_history=1.5
    )


def test_parse_robot_config_gives_the_geometry_and_navigation_in_si() -> None:
    config = parse_robot_config(encode(valid_document()))

    assert config.geometry == RobotGeometry(radius=0.25, rear=0.14)
    assert config.navigation == NavigationSettings(
        margin=0.02,
        turn_penalty=0.1,
        reverse_max_distance=0.25,
        reverse_min_gain=math.radians(30),
        reverse_max_speed=0.15,
    )
    assert config.provisional == frozenset()


def test_parse_robot_config_keeps_the_provisional_fields() -> None:
    document = valid_document()
    document["provisional"] = ["geometry.radius_mm", "navigation.margin_mm"]

    config = parse_robot_config(encode(document))

    assert config.provisional == {"geometry.radius_mm", "navigation.margin_mm"}


@pytest.mark.parametrize(
    ("provisional", "expected"),
    [
        (["geometry.diameter_mm"], "$.provisional[0]: no such field, got 'geometry.diameter_mm'"),
        (["world.remote_ttl_s", "radius_mm"], "$.provisional[1]: no such field, got 'radius_mm'"),
        (["geometry"], "$.provisional[0]: names a section, not a value, got 'geometry'"),
    ],
)
def test_parse_robot_config_refuses_a_provisional_field_that_does_not_exist(
    provisional: list[str], expected: str
) -> None:
    document = valid_document()
    document["provisional"] = provisional

    with pytest.raises(SchemaError) as error:
        parse_robot_config(encode(document))

    assert str(error.value) == expected


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("kind",), "cdr.match", "$.kind: Invalid enum value 'cdr.match'"),
        (
            ("world", "lidar_tracks_ttl_s"),
            0,
            "$.world.lidar_tracks_ttl_s: Expected `float` > 0.0, got 0",
        ),
        (("world", "remote_ttl_s"), -1, "$.world.remote_ttl_s: Expected `float` > 0.0, got -1"),
        (("world", "colour"), "red", "$.world: Object contains unknown field `colour`"),
        (("geometry", "radius_mm"), 0, "$.geometry.radius_mm: Expected `float` > 0.0, got 0"),
        (("geometry", "rear_mm"), 0, "$.geometry.rear_mm: Expected `float` > 0.0, got 0"),
        (
            ("navigation", "margin_mm"),
            -1,
            "$.navigation.margin_mm: Expected `float` >= 0.0, got -1",
        ),
        (
            ("navigation", "turn_penalty_mm"),
            -5,
            "$.navigation.turn_penalty_mm: Expected `float` >= 0.0, got -5",
        ),
        (
            ("navigation", "reverse_max_distance_mm"),
            0,
            "$.navigation.reverse_max_distance_mm: Expected `float` > 0.0, got 0",
        ),
        (
            ("navigation", "reverse_min_gain_deg"),
            -1,
            "$.navigation.reverse_min_gain_deg: Expected `float` >= 0.0, got -1",
        ),
        (
            ("navigation", "reverse_max_speed_mps"),
            0,
            "$.navigation.reverse_max_speed_mps: Expected `float` > 0.0, got 0",
        ),
    ],
)
def test_parse_robot_config_error_names_field_and_value(
    path: tuple[str, ...], value: object, expected: str
) -> None:
    document = copy.deepcopy(valid_document())
    node = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value

    with pytest.raises(SchemaError) as error:
        parse_robot_config(encode(document))

    assert str(error.value) == expected


def test_robot_config_gives_the_lifetimes_of_the_architecture() -> None:
    config = load_file(ROBOT_CONFIG, parse_robot_config)

    # Section 5.5 and TODO 4: tracks and remote vision 0.3 s, elements seen 2 s, history 2 s.
    assert config.world == WorldLifetimes(
        lidar_tracks=0.3, remote=0.3, element_seen=2.0, odometry_history=2.0
    )


def test_robot_config_gives_a_provisional_radius_and_the_margin_of_the_architecture() -> None:
    config = load_file(ROBOT_CONFIG, parse_robot_config)

    # ADR 0013: circumscribed circle of a 300 x 300 mm square, until the real footprint is known.
    assert config.geometry.radius == pytest.approx(0.212)
    assert "geometry.radius_mm" in config.provisional
    # Section 8.1: 20 mm margin around the inflated obstacles.
    assert config.navigation.margin == pytest.approx(0.02)


def test_robot_config_gives_provisional_rear_and_reverse_settings() -> None:
    config = load_file(ROBOT_CONFIG, parse_robot_config)

    # ADR 0014: half of a 300 mm square, and reverse thresholds to tune on the table (TODO 21.1).
    assert config.geometry.rear == pytest.approx(0.15)
    assert config.navigation.reverse_max_distance == pytest.approx(0.3)
    assert config.navigation.reverse_min_gain == pytest.approx(math.radians(45))
    assert config.navigation.reverse_max_speed == pytest.approx(0.2)
    assert {
        "geometry.rear_mm",
        "navigation.reverse_max_distance_mm",
        "navigation.reverse_min_gain_deg",
        "navigation.reverse_max_speed_mps",
    } <= config.provisional
