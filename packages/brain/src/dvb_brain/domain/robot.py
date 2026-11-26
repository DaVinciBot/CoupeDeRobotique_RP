"""Geometry of our robot, from config/robot.json (architecture, section 5.6; ADR 0013)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RobotGeometry:
    radius: float  # m, circumscribed circle of the footprint, actuators retracted
