"""World model of the brain (architecture, section 5.5; ADR 0008).

For now it holds the opponent tracks the lidar process publishes; the world model itself comes
with TODO 4.
"""

from dataclasses import dataclass

from dvb_brain.domain.geometry import Vec2


@dataclass(frozen=True, slots=True)
class Track:
    """An object the lidar follows from scan to scan, an opponent most likely (section 8.3)."""

    id: int
    center: Vec2  # m, on the table
    radius: float  # m
    velocity: Vec2  # m/s, on the table
    confirmed: bool  # confirmed by an opponent ArUco tag of the remote vision (RG G.6)


@dataclass(frozen=True, slots=True)
class TrackSet:
    """The tracks of one lidar scan; empty when nothing is seen (ADR 0011)."""

    stamp: float  # s, on the brain clock: time of the scan
    tracks: tuple[Track, ...]
