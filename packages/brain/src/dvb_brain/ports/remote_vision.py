"""Remote vision port: the computer outside the playing area that reads the ArUco tags."""

from typing import Protocol

from dvb_brain.domain.remote_vision import RemoteEvent, RemoteObservations
from dvb_brain.ports.watch import Watch


class RemoteVisionPort(Protocol):
    def observations(self) -> Watch[RemoteObservations]:
        """Return the last observations, and the next ones."""
        ...

    async def send(self, event: RemoteEvent) -> None:
        """Send the event once, without waiting for an answer. Never raises."""
        ...
