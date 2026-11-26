"""Navigation map: the free space of the robot centre on the table (architecture 8.1, ADR 0013)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavigationSettings:
    """Settings of the navigation, in SI (config/robot.json)."""

    margin: float  # m, kept between the robot and any obstacle, on top of its radius
    turn_penalty: float  # m, added to the length of a path for each stop to turn
