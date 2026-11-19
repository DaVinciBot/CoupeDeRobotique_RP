"""World model of the brain (architecture, section 5.5; ADR 0008, ADR 0012).

The WorldModel is the only writer: the odometry, the lidar tracks, the remote vision and the
strategy update it, each with the time of its measurement. Readers take an immutable snapshot.
Nothing here reads the clock: the caller gives the time of each measurement, and of each snapshot.

Fusion rules (section 5.5):
- the opponents come from the lidar only, which is what the avoidance trusts; the remote vision
  identifies the robots through Track.confirmed, set by the lidar process (section 8.3);
- for the game elements, a fresh view of the remote vision, newer than our own state, wins over
  it, except for what only our robot knows (carried by us, where we put it down); once stale,
  our own state counts again.
"""

import bisect
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum, auto
from types import MappingProxyType

from shapely import Polygon

from dvb_brain.domain.geometry import Pose, Vec2, angle_diff, normalize_angle
from dvb_brain.domain.remote_vision import RemoteObservations


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


class Source(StrEnum):
    ODOMETRY = auto()
    LIDAR = auto()
    REMOTE = auto()
    STRATEGY = auto()  # what our robot did: an element taken, a construction built
    CONFIG = auto()  # the table of the edition, before any measurement


@dataclass(frozen=True, slots=True)
class Observed[T]:
    value: T
    stamp: float  # s, on the brain clock: time of the measurement
    source: Source

    def age(self, now: float) -> float:
        return now - self.stamp

    def is_fresh(self, now: float, ttl: float) -> bool:
        """Return True while the value is no older than its lifetime ttl."""
        return self.age(now) <= ttl


@dataclass(frozen=True, slots=True)
class Velocity:
    v: float  # m/s, linear speed
    omega: float  # rad/s, angular speed


@dataclass(frozen=True, slots=True)
class ElementState:
    """What we know of a game element of the table; its kind and tags are the edition's."""

    present: bool  # still at its initial place
    taken: bool  # taken from there, by us or by the opponent
    placed_at: Pose | None  # where our robot put it down
    carried_by_us: bool
    confidence: float  # from 0 to 1
    tags: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Construction:
    """What our robot built on the table: an obstacle, and a mask for the lidar (8.4)."""

    id: str
    footprint: Polygon  # m, on the table


@dataclass(frozen=True, slots=True)
class WorldLifetimes:
    """How long a measurement serves to decide, in s (config/robot.json)."""

    # Beyond it, the tracks no longer serve to decide. The silence that stops the robot is read
    # on reception, by the avoidance (section 8.5, ADR 0011).
    lidar_tracks: float
    remote: float  # beyond it, the remote vision is silent
    element_seen: float  # beyond it, a view of the remote vision gives way to our own state
    odometry_history: float  # how far back pose_at goes


class PoseHistory:
    """Poses of the odometry over the last window seconds, to place a lidar scan (8.3)."""

    def __init__(self, window: float) -> None:
        self._window = window
        self._stamps: list[float] = []
        self._poses: list[Pose] = []

    def add(self, stamp: float, pose: Pose) -> None:
        """Add a pose; one at the time of the last replaces it. The brain clock is monotonic."""
        if self._stamps and stamp < self._stamps[-1]:
            raise ValueError(f"pose at {stamp} s is older than the last one, {self._stamps[-1]} s")
        if self._stamps and stamp == self._stamps[-1]:
            self._poses[-1] = pose
            return
        self._stamps.append(stamp)
        self._poses.append(pose)
        # Keep the last pose before the window too, so that pose_at covers all of it.
        kept = max(bisect.bisect_left(self._stamps, stamp - self._window) - 1, 0)
        del self._stamps[:kept]
        del self._poses[:kept]

    def pose_at(self, t: float) -> Pose | None:
        """Interpolate the pose at time t; None outside the history, never extrapolated."""
        i = bisect.bisect_left(self._stamps, t)
        if i < len(self._stamps) and self._stamps[i] == t:
            return self._poses[i]
        if i == 0 or i == len(self._stamps):
            return None
        t0, t1 = self._stamps[i - 1], self._stamps[i]
        p0, p1 = self._poses[i - 1], self._poses[i]
        r = (t - t0) / (t1 - t0)
        return Pose(
            p0.x + r * (p1.x - p0.x),
            p0.y + r * (p1.y - p0.y),
            normalize_angle(p0.theta + r * angle_diff(p1.theta, p0.theta)),
        )


@dataclass(frozen=True, slots=True)
class WorldSnapshot:
    """The world at time t. Never changes: the world model builds new collections instead."""

    t: float  # s, on the brain clock
    robot_pose: Observed[Pose] | None
    robot_velocity: Observed[Velocity] | None
    opponents: tuple[Observed[Track], ...]  # the last scan, even when stale: see lidar_alive
    our_elements: Mapping[str, Observed[ElementState]]  # config and strategy, by element id
    seen_elements: Mapping[str, Observed[ElementState]]  # remote vision, by element id
    our_constructions: Mapping[str, Observed[Construction]]  # by id
    carrying: frozenset[str]  # ids of the elements our robot carries
    remote: Observed[RemoteObservations] | None
    lidar_alive: bool
    remote_alive: bool
    element_seen_ttl: float  # s

    def element(self, element_id: str) -> Observed[ElementState]:
        """Return the state of an element, by the fusion rule of the module."""
        ours = self.our_elements[element_id]
        seen = self.seen_elements.get(element_id)
        if (
            seen is not None
            and seen.stamp > ours.stamp
            and seen.is_fresh(self.t, self.element_seen_ttl)
        ):
            # The remote vision does not see inside our robot, nor who put an element down.
            state = replace(
                seen.value,
                carried_by_us=ours.value.carried_by_us,
                placed_at=ours.value.placed_at,
            )
            return Observed(state, seen.stamp, seen.source)
        return ours


_IN_PLACE = ElementState(
    present=True, taken=False, placed_at=None, carried_by_us=False, confidence=1.0
)


class WorldModel:
    """The only writer of the world. Each update replaces its collections, never edits them."""

    def __init__(self, element_ids: Iterable[str], lifetimes: WorldLifetimes, now: float) -> None:
        """Start with every element of the table in place, e.g. WorldModel(arena.elements, ...)."""
        self._lifetimes = lifetimes
        self._history = PoseHistory(lifetimes.odometry_history)
        self._robot_pose: Observed[Pose] | None = None
        self._robot_velocity: Observed[Velocity] | None = None
        self._lidar_stamp: float | None = None
        self._opponents: tuple[Observed[Track], ...] = ()
        self._remote: Observed[RemoteObservations] | None = None
        initial = Observed(_IN_PLACE, now, Source.CONFIG)
        self._our_elements: Mapping[str, Observed[ElementState]] = MappingProxyType(
            dict.fromkeys(element_ids, initial)
        )
        self._seen_elements: Mapping[str, Observed[ElementState]] = MappingProxyType({})
        self._constructions: Mapping[str, Observed[Construction]] = MappingProxyType({})
        self._carrying: frozenset[str] = frozenset()

    def update_odometry(self, pose: Pose, velocity: Velocity, stamp: float) -> None:
        """Record a status of the motor board; one older than the last is ignored.

        Its stamp may come from the clock of the board, converted with an estimated offset that
        can step back a little: that must not stop the match.
        """
        if self._robot_pose is not None and stamp < self._robot_pose.stamp:
            return
        self._robot_pose = Observed(pose, stamp, Source.ODOMETRY)
        self._robot_velocity = Observed(velocity, stamp, Source.ODOMETRY)
        self._history.add(stamp, pose)

    def update_tracks(self, track_set: TrackSet) -> None:
        self._lidar_stamp = track_set.stamp
        self._opponents = tuple(
            Observed(track, track_set.stamp, Source.LIDAR) for track in track_set.tracks
        )

    def update_remote(self, observations: RemoteObservations) -> None:
        """Keep the observations as they are: what a tag means is not decided yet (TODO 17)."""
        self._remote = Observed(observations, observations.stamp, Source.REMOTE)

    def mark_element(
        self, element_id: str, state: ElementState, stamp: float, source: Source
    ) -> None:
        """Record the state of an element: a view of the remote vision, or our own state."""
        if element_id not in self._our_elements:
            raise ValueError(f"unknown element {element_id!r}")
        observed = Observed(state, stamp, source)
        if source is Source.REMOTE:
            self._seen_elements = MappingProxyType({**self._seen_elements, element_id: observed})
            return
        self._our_elements = MappingProxyType({**self._our_elements, element_id: observed})
        # The remote vision does not see inside our robot: what we carry is our own state.
        self._carrying = frozenset(
            i for i, element in self._our_elements.items() if element.value.carried_by_us
        )

    def add_construction(self, construction: Construction, stamp: float) -> None:
        """Add a construction, or replace the one with the same id when it grows."""
        observed = Observed(construction, stamp, Source.STRATEGY)
        self._constructions = MappingProxyType({**self._constructions, construction.id: observed})

    def snapshot(self, now: float) -> WorldSnapshot:
        """Return the world at time now, in O(1): the collections are shared, never edited."""
        return WorldSnapshot(
            t=now,
            robot_pose=self._robot_pose,
            robot_velocity=self._robot_velocity,
            opponents=self._opponents,
            our_elements=self._our_elements,
            seen_elements=self._seen_elements,
            our_constructions=self._constructions,
            carrying=self._carrying,
            remote=self._remote,
            lidar_alive=self._lidar_stamp is not None
            and now - self._lidar_stamp <= self._lifetimes.lidar_tracks,
            remote_alive=self._remote is not None
            and self._remote.is_fresh(now, self._lifetimes.remote),
            element_seen_ttl=self._lifetimes.element_seen,
        )

    def pose_at(self, t: float) -> Pose | None:
        """Interpolate the pose of the odometry at time t; None outside its history."""
        return self._history.pose_at(t)
