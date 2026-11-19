import copy
from pathlib import Path
from typing import Any

import msgspec
import pytest

from dvb_brain.app.config import parse_robot_config
from dvb_brain.app.files import load_file
from dvb_brain.domain.decoding import SchemaError
from dvb_brain.domain.world import WorldLifetimes

ROBOT_CONFIG = Path(__file__).parents[4] / "config" / "robot.json"


def valid_document() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "cdr.robot",
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
