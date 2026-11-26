"""Configuration of the robot, config/robot.json (architecture, section 5.6; ADR 0008).

The file is decoded at startup into SI dataclasses of the domain, which the services receive.
For now it holds the geometry and the navigation (TODO 5.1, 5.3, ADR 0013, 0014) and the
lifetimes of the world model (TODO 4); TODO 9.1 adds the rest.
"""

from dataclasses import dataclass
from typing import Literal

import msgspec

from dvb_brain.domain.decoding import Id, NonNegative, Positive, decode_json, field_error
from dvb_brain.domain.navmap import NavigationSettings
from dvb_brain.domain.robot import RobotGeometry
from dvb_brain.domain.units import deg_to_rad, mm_to_m
from dvb_brain.domain.world import WorldLifetimes


@dataclass(frozen=True, slots=True)
class RobotConfig:
    geometry: RobotGeometry
    navigation: NavigationSettings
    world: WorldLifetimes
    # Fields whose value is not known yet, e.g. "geometry.radius_mm": TODO 9.1 refuses them in
    # the match profile.
    provisional: frozenset[str]


def parse_robot_config(data: bytes) -> RobotConfig:
    """Decode the content of a robot.json file and convert it to SI.

    Raise a SchemaError that names the field and the value.
    """
    raw = decode_json(data, _RobotFile)
    for i, path in enumerate(raw.provisional):
        _check_field(raw, f"$.provisional[{i}]", path)
    return RobotConfig(
        geometry=RobotGeometry(
            radius=mm_to_m(raw.geometry.radius_mm), rear=mm_to_m(raw.geometry.rear_mm)
        ),
        navigation=NavigationSettings(
            margin=mm_to_m(raw.navigation.margin_mm),
            turn_penalty=mm_to_m(raw.navigation.turn_penalty_mm),
            reverse_max_distance=mm_to_m(raw.navigation.reverse_max_distance_mm),
            reverse_min_gain=deg_to_rad(raw.navigation.reverse_min_gain_deg),
            reverse_max_speed=raw.navigation.reverse_max_speed_mps,
        ),
        world=WorldLifetimes(
            lidar_tracks=raw.world.lidar_tracks_ttl_s,
            remote=raw.world.remote_ttl_s,
            element_seen=raw.world.element_seen_ttl_s,
            odometry_history=raw.world.odometry_history_s,
        ),
        provisional=frozenset(raw.provisional),
    )


def _check_field(raw: _RobotFile, at: str, path: str) -> None:
    """Check that path, such as "geometry.radius_mm", names a value of the file."""
    node: object = raw
    for name in path.split("."):
        if not isinstance(node, msgspec.Struct) or name not in node.__struct_fields__:
            raise field_error(at, "no such field", path)
        node = getattr(node, name)
    if isinstance(node, msgspec.Struct):
        raise field_error(at, "names a section, not a value", path)


# Schema of robot.json: lengths in mm, angles in degrees, times in s, speeds in m/s.


class _GeometrySection(msgspec.Struct, forbid_unknown_fields=True):
    radius_mm: Positive
    rear_mm: Positive


class _NavigationSection(msgspec.Struct, forbid_unknown_fields=True):
    margin_mm: NonNegative
    turn_penalty_mm: NonNegative
    reverse_max_distance_mm: Positive
    reverse_min_gain_deg: NonNegative
    reverse_max_speed_mps: Positive


class _WorldSection(msgspec.Struct, forbid_unknown_fields=True):
    lidar_tracks_ttl_s: Positive
    remote_ttl_s: Positive
    element_seen_ttl_s: Positive
    odometry_history_s: Positive


class _RobotFile(msgspec.Struct, forbid_unknown_fields=True):
    schema_version: Literal[1]
    kind: Literal["cdr.robot"]
    geometry: _GeometrySection
    navigation: _NavigationSection
    world: _WorldSection
    provisional: list[Id] = []
