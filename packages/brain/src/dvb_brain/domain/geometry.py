"""Planar geometry in SI units: metres and radians, counter-clockwise angles."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vec2:
    """Point or displacement on the table, in metres."""

    x: float
    y: float

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, factor: float) -> Vec2:
        return Vec2(self.x * factor, self.y * factor)

    def __rmul__(self, factor: float) -> Vec2:
        return self * factor

    def norm(self) -> float:
        return math.hypot(self.x, self.y)

    def dot(self, other: Vec2) -> float:
        return self.x * other.x + self.y * other.y

    def cross(self, other: Vec2) -> float:
        """Return the z component: positive when other is counter-clockwise from self."""
        return self.x * other.y - self.y * other.x

    def rotate(self, angle: float) -> Vec2:
        """Rotate counter-clockwise around the origin."""
        c, s = math.cos(angle), math.sin(angle)
        return Vec2(c * self.x - s * self.y, s * self.x + c * self.y)

    def angle(self) -> float:
        """Return the direction of the vector, in (-pi, pi]."""
        return math.atan2(self.y, self.x)


def normalize_angle(angle: float) -> float:
    """Wrap an angle into (-pi, pi]."""
    wrapped = math.remainder(angle, math.tau)
    return math.pi if wrapped == -math.pi else wrapped


def angle_diff(a: float, b: float) -> float:
    """Return a - b wrapped into (-pi, pi]."""
    return normalize_angle(a - b)


def shortest_rotation(a: float, b: float) -> float:
    """Return the signed rotation that goes from heading a to heading b."""
    return normalize_angle(b - a)


@dataclass(frozen=True, slots=True)
class Pose:
    """Position (metres) and heading (radians) on the table."""

    x: float
    y: float
    theta: float

    @property
    def position(self) -> Vec2:
        return Vec2(self.x, self.y)

    @property
    def heading_vector(self) -> Vec2:
        return Vec2(math.cos(self.theta), math.sin(self.theta))

    def compose(self, other: Pose) -> Pose:
        """Return other, given in the frame of self, in the frame self is given in."""
        position = self.to_world(other.position)
        return Pose(position.x, position.y, normalize_angle(self.theta + other.theta))

    def inverse(self) -> Pose:
        position = (self.position * -1.0).rotate(-self.theta)
        return Pose(position.x, position.y, normalize_angle(-self.theta))

    def to_local(self, point: Vec2) -> Vec2:
        """Express a table point in the frame of this pose."""
        return (point - self.position).rotate(-self.theta)

    def to_world(self, point: Vec2) -> Vec2:
        """Express a point of the frame of this pose on the table."""
        return self.position + point.rotate(self.theta)
