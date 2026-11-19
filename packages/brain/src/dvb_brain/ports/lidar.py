"""Lidar port: the opponent tracks of the lidar process (architecture, section 8.3)."""

from typing import Protocol

from dvb_brain.domain.world import TrackSet
from dvb_brain.ports.watch import Watch


class LidarPort(Protocol):
    def tracks(self) -> Watch[TrackSet]:
        """Return the tracks of the last scan, and the next ones.

        One TrackSet per scan, empty when nothing is seen: only silence means that the lidar is
        mute (section 8.5).
        """
        ...
