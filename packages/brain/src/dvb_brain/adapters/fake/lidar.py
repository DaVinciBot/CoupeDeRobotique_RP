"""Lidar of the tests: tracks scripted as a function of time."""

from collections.abc import Callable

from dvb_brain.domain.world import Track, TrackSet
from dvb_brain.ports.clock import Clock
from dvb_brain.ports.watch import Watch

type TrackScript = Callable[[float], tuple[Track, ...] | None]


class FakeLidar:
    """Publish tracks_at(now) once per period; nothing while it gives None (mute lidar)."""

    def __init__(self, clock: Clock, *, period: float, tracks_at: TrackScript) -> None:
        self._clock = clock
        self._period = period
        self._tracks_at = tracks_at
        self._tracks = Watch[TrackSet](clock)

    def tracks(self) -> Watch[TrackSet]:
        return self._tracks

    async def run(self) -> None:
        """Publish until cancelled, like the reader of a real adapter."""
        while True:
            now = self._clock.now()
            tracks = self._tracks_at(now)
            if tracks is not None:
                self._tracks.set(TrackSet(stamp=now, tracks=tracks))
            await self._clock.sleep(self._period)
