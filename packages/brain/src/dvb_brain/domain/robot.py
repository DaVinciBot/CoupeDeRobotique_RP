"""Geometry of our robot, from config/robot.json (architecture, section 5.6; ADR 0013)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RobotGeometry:
    # m, circumscribed circle of the robot as it moves, carried elements and actuators included
    radius: float
