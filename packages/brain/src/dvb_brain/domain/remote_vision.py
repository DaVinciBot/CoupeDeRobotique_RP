"""What the remote vision computer sees, and what the brain tells it (TODO 17, ADR 0011).

Provisional: the content of the observations is still to be agreed with the remote vision
team. Times are on the brain clock; the adapter converts them to the common clock.
"""

from dataclasses import dataclass

from dvb_brain.domain.arena import Side
from dvb_brain.domain.geometry import Pose


@dataclass(frozen=True, slots=True)
class MarkerObservation:
    tag_id: int  # ArUco tag: robots by side (RG G.6), game elements by edition
    pose: Pose  # on the table


@dataclass(frozen=True, slots=True)
class RemoteObservations:
    stamp: float  # s, on the brain clock: time of the picture
    markers: tuple[MarkerObservation, ...]


@dataclass(frozen=True, slots=True)
class SideChosen:
    side: Side


@dataclass(frozen=True, slots=True)
class MatchStarted:
    t0: float  # s, on the brain clock: time the start cord was pulled


@dataclass(frozen=True, slots=True)
class PoseEstimate:
    pose: Pose  # our robot, from the odometry
    stamp: float  # s, on the brain clock


type RemoteEvent = SideChosen | MatchStarted | PoseEstimate
