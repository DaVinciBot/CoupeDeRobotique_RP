"""Configuration of the robot, config/robot.json (architecture, section 5.6; ADR 0008).

The file is decoded at startup into SI dataclasses of the domain, which the services receive.
For now it holds the lifetimes of the world model (TODO 4); TODO 9.1 adds the rest.
"""

from dataclasses import dataclass
from typing import Literal

import msgspec

from dvb_brain.domain.decoding import Positive, decode_json
from dvb_brain.domain.world import WorldLifetimes


@dataclass(frozen=True, slots=True)
class RobotConfig:
    world: WorldLifetimes


def parse_robot_config(data: bytes) -> RobotConfig:
    """Decode the content of a robot.json file and convert it to SI.

    Raise a SchemaError that names the field and the value.
    """
    raw = decode_json(data, _RobotFile)
    return RobotConfig(
        world=WorldLifetimes(
            lidar_tracks=raw.world.lidar_tracks_ttl_s,
            remote=raw.world.remote_ttl_s,
            element_seen=raw.world.element_seen_ttl_s,
            odometry_history=raw.world.odometry_history_s,
        )
    )


# Schema of robot.json: times in s.


class _WorldSection(msgspec.Struct, forbid_unknown_fields=True):
    lidar_tracks_ttl_s: Positive
    remote_ttl_s: Positive
    element_seen_ttl_s: Positive
    odometry_history_s: Positive


class _RobotFile(msgspec.Struct, forbid_unknown_fields=True):
    schema_version: Literal[1]
    kind: Literal["cdr.robot"]
    world: _WorldSection
