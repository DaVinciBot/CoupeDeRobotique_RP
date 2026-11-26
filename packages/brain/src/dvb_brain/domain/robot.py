"""Geometry of our robot, from config/robot.json (architecture, section 5.6; ADR 0013, 0014)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RobotGeometry:
    # m, circumscribed circle of the robot as it moves, carried elements and actuators included
    radius: float
    rear: float  # m, from the centre to the rear face, the one pushed against a border (ADR 0014)
